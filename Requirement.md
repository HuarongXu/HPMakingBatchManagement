# HP Making Batch Management Tool 需求与实施说明

---

## 1. 文档目的

本文档用于说明当前版本工具的**真实实现逻辑**、**业务判断规则**、**数据来源**、**报表口径**与**典型应用案例**。

文档目标不是描述理想化蓝图，而是：

- 对齐当前代码已经落地的行为；
- 方便业务、计划、IT 三方统一理解；
- 作为后续优化算法与规则调整的基线文档；
- 支撑工具演示、培训与内部汇报。

当前运行入口见 [BatchManagementTool/src/main.py](BatchManagementTool/src/main.py#L20-L54)。

---

## 2. 工具定位与核心价值

本工具用于 HP 洗护生产计划的批次管理与搅拌系统分配，面向以下典型业务问题：

1. 不同产品、不同产线、不同班次，如何映射到合适的搅拌系统；
2. 如何在 1.1 / 2.2 / 4.4 及其多倍 MOQ 下，尽量形成可执行的批次；
3. 如何在班次产能限制下，避免系统过载；
4. 如何对“接近 MOQ”“低于 MOQ”“跨班次搭批”“半批白名单”等情况做统一判断；
5. 如何输出可审计的报表，让计划员能看到每个订单为什么这样分配。

该工具当前属于：

- **规则驱动 + 启发式优化**（Heuristic Scheduling）
- 不是严格的全局最优求解器
- 但已具备较强的业务可解释性与落地性

---

## 3. 系统运行总览

当前完整流程如下：

1. **读取输入数据**
2. **预处理订单数据**
3. **解析搅拌系统能力**
4. **按产品与 WIP 分组**
5. **尝试搭批与拆批**
6. **为每个目标批次选择系统**
7. **按日期 + 班次记录产能占用**
8. **执行二次合并（Second Pass Merge，可开关）**
9. **执行超限再平衡（Overflow Rebalance）**
10. **生成 Orders / Batches / Alerts 报表**
11. **输出 Decision Explain 列，提供逐单解释**

运行命令：

```bash
python src/main.py --date YYYYMMDD
```

示例：

```bash
python src/main.py --date 20260403
```

---

## 4. 数据源说明

### 4.1 输入数据表

| 数据源 | 位置 | 核心字段 | 用途 |
|---|---|---|---|
| ZCPRS | 1.DataBase / 1.DataBase/CSV | Order Number, Material, Work Center, Planned Quantity, Start/End DateTime, UoM, Mrp Element | 生产计划主表 |
| ZC228 | 1.DataBase / 1.DataBase/CSV | Parent Ord, Matl-Comp, Amt Reqd | WIP 消耗明细，当前主逻辑已加载，但核心分配主要仍以 Parameter/WIP 链路为主 |
| Parameter.csv | BatchManagementTool/data | Material, Matl-Comp, Type, SUF, Brand, Seg | 产品属性、WIP 映射、类型与汇总字段 |
| Making Capacity.xlsx | BatchManagementTool/data | 机组名称、支持规格、班次上限、产品适用性 | 定义 GSS 系统能力 |
| 12t_to_6t_conversion_list.xlsx | BatchManagementTool/data | WIP Code | 定义 GSS1+GSS2 是否允许 half batch |

### 4.2 当前工具使用的关键字段

- `Order Number`：订单唯一标识
- `Material`：物料号
- `Work Center`：包装线/产线
- `Planned Quantity`：当前实现中直接作为 `MSU Demand` 处理
- `StartDate + StartTime` / `EndDate + EndTime`：生成时间窗与班次
- `Matl-Comp / WIP Code`：搭批主键之一
- `Type`：用于识别 Shampoo / Conditioner
- `SUF`：当前主要作为展示字段保留
- `Seg`：汇总维度之一

### 4.3 重要说明：MSU 口径

需求概念上常写为：

$$
MSU = \frac{CS \times SUF}{1000}
$$

但**当前实际代码实现**中，订单的 `MSU Demand` 主要直接使用 `Planned Quantity` 数值，`SUF` 作为参考展示字段保留在报表中。

因此在对外展示时，应明确：

- 当前工具的运行口径是“输入计划量已按 MSU 使用”；
- 若未来恢复严格的 `CS × SUF / 1000` 换算，需要单独版本升级并回归验证。

---

## 5. 搅拌系统与业务对象

### 5.1 核心对象

代码中的主要对象见 [BatchManagementTool/src/models.py](BatchManagementTool/src/models.py#L1-L66)：

- `ProductionOrder`：订单对象
- `MakingSystem`：搅拌系统对象
- `Batch`：批次对象

### 5.2 系统能力概念

当前工具识别的代表性系统为：

| 系统 | 产品类型 | 常见作用 |
|---|---|---|
| GSS1 + GSS2 | Shampoo | 主力系统，优先承担 4.4 及以上目标，特定白名单可做 2.2 half batch |
| GSS3 | Shampoo | 2.2 小批的主力承接系统 |
| GSS4 (Cond) | Conditioner | 护发素专用系统，可承接 1.1 / 2.2 / 4.4 及其组合 |

系统数据来源见 [BatchManagementTool/src/data_loader.py](BatchManagementTool/src/data_loader.py) 与 [BatchManagementTool/src/logic.py](BatchManagementTool/src/logic.py#L580-L659)。

---

## 6. 计算逻辑总述

## 6.1 班次计算

班次通过开始时间决定：

- N：00:00–07:59
- D：08:00–15:59
- M：16:00–23:59

实现位置见 [BatchManagementTool/src/logic.py](BatchManagementTool/src/logic.py#L57-L63)。

## 6.2 搭批窗口

当前窗口属于**规则驱动窗口**：

- Shampoo 默认 16 小时
- Conditioner 默认 24 小时
- 特定产线 `HPHFPACK` 强制 24 小时

实现位置见 [BatchManagementTool/src/logic.py](BatchManagementTool/src/logic.py#L80-L101)。

## 6.3 允许的目标规格

当前目标规格由 `_get_allowed_msu_sizes()` 生成：

- Shampoo：以 2.2 为基础的多倍数目标
- Conditioner：以 2.2 为基础的多倍数目标，额外允许 1.1

这使得工具可以支持：

- 2.2
- 4.4
- 6.6
- 8.8
- 11.0
- 13.2
- Conditioner 另有 1.1

实现位置见 [BatchManagementTool/src/logic.py](BatchManagementTool/src/logic.py#L911-L924)。

---

## 7. 双层容差机制（当前版本）

当前版本使用**双层容差**：

- **Preferred tolerance**：优选容差
- **Hard tolerance**：硬边界容差

其目的不是无限放宽容差，而是把“理想命中”和“可接受命中”分开。

### 7.1 基础档位容差

当前基础参数：

| 基础 MOQ | Preferred | Hard |
|---|---:|---:|
| 1.1 | 0.05 | 0.20 |
| 2.2 | 0.08 | 0.30 |
| 4.4 | 0.12 | 0.50 |

### 7.2 多个 MOQ 时的放大逻辑

当前版本已对**4.4 及其多倍目标**增加放大步长：

- 每增加一个 4.4 批次：
  - `Preferred + 0.06`
  - `Hard + 0.20`

例如：

| Target | Preferred 区间 | Hard 区间 |
|---|---|---|
| 4.4 | 4.28 ~ 4.52 | 3.90 ~ 4.90 |
| 8.8 | 8.62 ~ 8.98 | 8.10 ~ 9.50 |
| 11.0 | 10.76 ~ 11.24 | 10.10 ~ 11.90 |
| 13.2 | 12.90 ~ 13.50 | 12.10 ~ 14.30 |

说明：

- 这更符合多批次累计波动的实际情况；
- 对于 2.2 和 1.1 当前暂不额外放大；
- 当前口径实现见 [BatchManagementTool/src/logic.py](BatchManagementTool/src/logic.py) 中的 `MOQ_TOLERANCE_RULES`、`MULTI_MOQ_TOLERANCE_STEP` 常量与 `_tolerance_band` / `_hard_tolerance_band` 函数。

### 7.3 命中状态说明

报表中的 `Decision Explain` 会输出以下状态：

- `IN_PREFERRED`：命中优选区间
- `IN_HARD_ONLY`：不在优选区，但在硬边界内
- `OUTSIDE_HARD`：不在硬边界内
- `ABOVE_PREFERRED`：高于优选区，但仍可能在硬边界内

---

## 8. 订单搭批与拆批逻辑

## 8.1 先分组，再规划

当前组合逻辑不是全局求最优，而是按顺序进行：

1. 按 `WIP Code` 分组；
2. 在 `_plan_batches_for_group` 内统一处理小单配对与普通搭批；
3. 小单优先按 `4.4 -> 2.2` 标准目标顺序尝试多订单组合（支持 2、3 甚至更多订单凑成一个目标）；
4. 普通单按目标从大到小降序尝试搭批，优先合成更大 MOQ；
5. 先同日，再跨日；
6. 只有规则合法时才进入系统比较。

实现位置见 [BatchManagementTool/src/logic.py](BatchManagementTool/src/logic.py)。

## 8.2 小单配对

对于小单（MSU ≤ 3.0），会优先尝试组合成标准目标，支持多订单组合，例如：

- 两个 2.0 左右订单尝试凑成 4.4
- 三个 1.1 左右订单尝试凑成 4.4（如 1.18 + 2.15 + 1.10 = 4.43）
- 两个 1.0 左右订单尝试凑成 2.2

内部调用 `_build_combo_for_target` 实现，采用贪心策略逐步添加候选订单直到总载荷落入目标硬容差范围内。

## 8.3 单单直接成批

若单个订单已经足够接近目标（满足硬边界），工具允许其直接形成单独批次。

例如：

- `2.183 -> Target 2.2`
- `4.247 -> Target 4.4`

这类订单通常不会加“未搭批”备注，因为它们已足够接近一个完整 MOQ。

## 8.4 二次合并（Second Pass Merge）

为解决“首轮已分配但仍可升级成更大合法批次”的场景，当前版本增加了二次合并阶段。

### 8.4.1 开关

- 当前通过代码常量 `ENABLE_SECOND_PASS_MERGE` 控制（默认开启）；
- 位置见 [BatchManagementTool/src/logic.py](BatchManagementTool/src/logic.py)。

### 8.4.2 触发条件（硬条件）

仅当以下条件同时满足时，才会进入候选合并：

1. 两个批次分配到同一系统；
2. `WIP Code` 相同；
3. `Product Type / Category` 相同；
4. 满足以下之一：
   - 至少一侧为"欠装单批"（即单订单批次且 `Load / Target < 0.90`）；
   - 合并后可减少物理批次数（例如两个 1.1 批次合并为一个 2.2，节省搅拌次数）；
5. 合并后总载荷能命中合法目标（按硬容差）；
6. 合并后系统仍支持该目标规格。

### 8.4.3 跨班次策略

- 候选合并允许跨班次（与现有“先同日后跨日”设计保持一致）；
- 合并完成后按订单的 `start_datetime + shift` 重新分摊 `batch_count`（始终为整数，使用整除+余数分配）；
- 再由 `BatchCapacityTracker` 按“日期 + 班次”重建占用，保证班次统计口径一致。

### 8.4.4 两条保护机制

为避免副作用，当前二次合并内置两条保护：

1. **不恶化超限**：合并后任何 `系统-日期-班次` 的超限程度不得高于合并前；
2. **防止无效合并**：仅当合并满足"至少一侧欠装/合并后减少物理批次"时才触发，避免已健康批次的无意义重组。

### 8.4.5 示例（已验证）

例如 `3019518253`（3.538）与 `2990748521`（13.821）可在同 WIP 下被二次合并为目标 `17.6`，用于修复“可做大批但首轮未合并”的场景。

---

## 8.5 超限再平衡与二次合并的顺序

当前顺序是：

1. 首轮搭批与系统分配
2. 二次合并（可开关）
3. 超限再平衡（如 GSS3 -> GSS1+GSS2 借产能）
4. 班次占用重建与告警汇总

该顺序的目的：

- 先把“本可合并”的批次做结构优化；
- 再做系统借产能，减少不必要搬移；
- 最终让 `Orders/Batches/Alerts` 三张表口径一致。

## 8.5 明显不足 MOQ 的备注策略

若单独开批且明显低于目标（当前阈值为 `Load / Target < 0.90`），则在 `Batch Note` 中加入提示，避免业务误以为漏搭批。

例如：

- `3.821 / 4.4` 会提示
- `2.076 / 2.2` 不提示

---

## 9. 系统选择逻辑：规则筛选 + 局部评分

这是当前工具最核心的设计之一。

### 9.1 先规则筛选

系统不会对所有组合做全局打分，而是先进行合法性过滤：

- 产品是否匹配该系统；
- 该系统是否支持目标规格；
- GSS1+GSS2 在小批场景下是否满足白名单规则；
- 班次/日期容量是否允许。

### 9.2 再对候选系统打分

当一组订单已经确定可以形成某个 `Target` 后，系统会对多个候选 GSS 做排序。

当前评分元组为：

$$
Score = (overflow, gss12\_small, priority, usage, closest, name)
$$

排序规则是**从左到右逐项比较，取最小值**。

各字段含义：

| 字段 | 含义 | 越小越好 |
|---|---|---|
| `overflow` | 是否会超该日期该班次上限 | 是 |
| `gss12_small` | GSS1+GSS2 做小批的惩罚 | 是 |
| `priority` | 系统优先级（GSS1+GSS2 < GSS3 < GSS4） | 是 |
| `usage` | 该日期该班次已占用批次数 | 是 |
| `closest` | 系统能力与目标规格的接近程度 | 是 |
| `name` | 最终稳定排序字段 | 是 |

### 9.3 结论

因此当前工具不是“全局统一打分器”，而是：

- **前半段**：规则驱动 + 贪心找可行组合
- **后半段**：在候选系统间做评分排序

这是典型的**启发式调度算法**（Heuristic Scheduling with Rule-based Filtering）。

---

## 10. 日期 + 班次容量控制

当前版本已修复为：

- 容量统计维度 = `系统 + 日期 + 班次`

而不是只按 `系统 + 班次`。

这意味着：

- 4/6 的 D 班和 4/7 的 D 班不再混算；
- 超限判断更符合实际生产日历；
- Alerts 的超限提示也会带具体日期。

实现位置见 [BatchManagementTool/src/logic.py](BatchManagementTool/src/logic.py#L683-L780)。

---

## 11. 报表输出说明

## 11.1 Orders

每条订单输出以下关键信息：

- 原始订单信息
- 分配系统
- 批次号
- 批次数（`Batch Count`，始终为整数。基于 `physical_batches` 计算，多订单搭批时按日期+班次桶整除分配）
- 备注
- 告警
- `Decision Explain`

`Decision Explain` 是当前版本新增的可解释列，用于展示：

- 目标 MOQ
- 当前负载
- Preferred / Hard 区间
- 命中状态
- 选中系统的评分信息

这列用于调试、培训与汇报，未来稳定后可隐藏。

## 11.2 Batches

Batches 主表按**真实物理批次**统计，维度为：

- 系统
- 日期
- 班次

## 11.3 Summary Tables

当前汇总表已同步改成按**真实批次**统计，而不是按 MSU 汇总。

包括：

1. By System × Day × Product
2. By Day × Line × System
3. By Seg × Day

## 11.4 Alerts

当前告警已做去重与格式统一。

---

## 12. 典型案例（配合公式说明）

### 案例 A：标准命中

订单：`2978480642`

- Load = 2.183
- Target = 2.2
- Preferred = [2.120, 2.280]

因为：

$$
2.120 \le 2.183 \le 2.280
$$

所以命中 `IN_PREFERRED`，属于标准优选情况。

### 案例 B：硬边界内可接受

订单组合：`2998992825 + 2994904204`

- 合计 Load = 2.060
- Target = 2.2
- Preferred = [2.120, 2.280]
- Hard = [1.900, 2.500]

因为：

$$
2.060 < 2.120
$$

没有进入优选区；但：

$$
1.900 \le 2.060 \le 2.500
$$

所以仍属于 `IN_HARD_ONLY`，允许搭批。

### 案例 C：明显不足 MOQ，需要备注

订单：`2994901924`

- Load = 3.821
- Target = 4.4
- 比例：

$$
\frac{3.821}{4.4} = 0.868
$$

因为低于 90%，所以系统会保留单独开批，并增加备注提醒。

### 案例 D：多批次容差放大

订单：`2998987389`

- Load = 11.489
- 物理批次 = 3
- 当前最合理目标 = 11.0
- Preferred = [10.760, 11.240]
- Hard = [10.300, 11.700]

因此：

$$
11.489 > 11.240
$$

高于优选上限，但：

$$
11.489 < 11.700
$$

仍然在硬边界内，可接受。

### 案例 E：靠评分取胜而不是靠规则直接决定

订单：`2998979332`

对于 `Target = 2.2` 的 shampoo 批次，两个系统都合法：

- GSS1 + GSS2：

$$
(0,1,0,0,2.2)
$$

- GSS3：

$$
(0,0,1,0,0.0)
$$

因为排序逐项比较：

- 第一位 `overflow` 相同；
- 第二位 `gss12_small`：GSS3 更优；

所以最终由 **GSS3 胜出**。

这说明：

- 当前工具的“打分”主要用于**系统选择**；
- 不是用于全局决定所有订单怎样组合。

---

## 13. 算法特征（用于展示与汇报）

若用于汇报或展示，可将当前工具描述为：

> 一个面向洗护制造场景的、具备**多源数据整合、规则驱动约束过滤、双层容差控制、局部评分排序、日期班次产能校验、可解释性输出**能力的生产批次智能辅助决策系统。

更技术化一点，可以概括为：

- **Rule-based Scheduling Engine**
- **Heuristic Batch Formation**
- **Dual-Tolerance Feasibility Control**
- **Local Multi-Criteria Scoring for System Assignment**
- **Explainable Planning Output**

---

## 14. 当前版本边界说明

当前版本仍有以下边界：

1. 组合选择阶段仍以启发式贪心为主，不是全局最优求解；
2. `closest` 在当前标准目标下多数为 0，主要起兜底排序作用；
3. `Decision Explain` 当前输出的是最终选中系统分数，不包含所有落选候选的完整对比；
4. `MSU Demand` 当前仍按输入计划量运行，而非严格实时换算；
5. GSS4 的目标已经比过去更合理，但后续仍可继续升级为“枚举所有合法组合后选最接近目标”的增强版。

---

## 15. 建议演示话术

演示时可以按以下顺序介绍：

1. 数据从哪里来；
2. 系统如何识别班次、WIP、产品类型；
3. 什么是 Preferred / Hard 双层容差；
4. 为什么有些单会搭批、有些单会单独开批；
5. 为什么两个系统都能做时，最终还是会选其中一个；
6. `Decision Explain` 如何帮助业务审阅每个订单的判断依据；
7. 汇总表和 Alerts 如何帮助管理者看整体产能与风险。

---

## 16. 文档维护说明

本文件已按照当前版本代码行为同步更新。后续若修改以下任一逻辑，应同步更新本文档：

- MOQ 容差参数
- 系统优先级
- WIP / 白名单规则
- 班次上限口径
- Orders / Batches / Summary 报表字段
- Decision Explain 字段结构
- Web Dashboard 页面布局或 API 接口

---

## 17. Web Dashboard 说明

### 17.1 架构

Web Dashboard 基于 Flask 构建，前端使用原生 JavaScript + ECharts 图表库。

- 后端：Flask 提供 HTML 模板渲染 + RESTful JSON API
- 前端：响应式布局，支持深色/浅色主题切换
- 端口：默认 8050（自动检测端口占用并切换）

### 17.2 页面结构

| 页面 | 路由 | 功能 |
|---|---|---|
| Dashboard 总览 | `/` | KPI 卡片、系统产能热力图、产品分布饼图、告警预览 |
| Orders 订单明细 | `/orders` | 全量订单表格，支持搜索/筛选/排序/分页/导出/详情面板 |
| Summary 汇总视图 | `/summary` | 每日趋势图、系统利用率图、三维交叉汇总表 |
| Alerts 告警中心 | `/alerts` | 分级告警列表，支持按严重级别过滤 |

### 17.3 API 接口

| 接口 | 返回内容 |
|---|---|
| `/api/orders` | 全量订单 JSON |
| `/api/batches` | 全量批次 JSON |
| `/api/alerts` | 分类告警 JSON |
| `/api/heatmap` | 系统产能热力图数据 |
| `/api/product_distribution` | 产品分布数据 |
| `/api/summary/*` | 各维度汇总表数据 |

---

## 18. 部署与分发

### 18.1 面向终端用户

工具以 ZIP 压缩包形式分发，用户操作流程：

1. 解压 ZIP 到任意目录
2. 双击 `install.bat`（首次安装，自动安装 Python 和依赖）
3. 双击 `启动工具.bat`（日常使用）
4. 双击 `upgrade.bat`（更新到最新版本）

### 18.2 脚本说明

| 脚本 | 用途 |
|---|---|
| `install.bat` | 一键安装：检测/安装 Python → 创建虚拟环境 → 安装依赖 |
| `启动工具.bat` | 一键启动：输入日期 → 启动 Web Dashboard |
| `upgrade.bat` | 一键升级：备份数据 → 下载最新代码 → 更新依赖 |
| `install_and_run.bat` | 旧版安装脚本（兼容保留） |

---

> 当前文档基于 2026-05-10 代码版本整理，覆盖双层容差（含 4.4 硬容差放宽至 0.50）、日期班次容量、多订单搭批组合、大目标优先搭批策略、二次合并效率优化（支持减少物理批次的合并）、真实批次汇总、单单备注策略与可解释决策输出。修复 `batch_count` 小数问题（恢复使用 `physical_batches` 整数计算，多订单搭批按整除+余数分配）。新增 Web Dashboard 交互式仪表盘（总览 / 订单明细 / 汇总视图 / 告警中心），支持搜索、筛选、排序、导出、深浅主题切换。新增一键安装 / 启动 / 升级脚本，面向零基础用户。