# HP Making Batch Management Tool

生产计划批次管理工具 —— 自动化排批、搭批、拆批，配有 Web 交互式仪表盘。

---

## 功能概览

本工具用于 HP 洗护生产计划的批次管理与搅拌系统分配，核心功能包括：

- **自动排批** — 根据 WIP Code、产品类型、MOQ 规则自动形成合法批次
- **搭批优化** — 支持多订单搭批、小单配对、跨班次组合
- **双层容差控制** — Preferred / Hard 容差机制，兼顾最优与可行
- **系统自动分配** — GSS1+2 / GSS3 / Tandem 智能选择与评分
- **Web Dashboard** — 浏览器交互式仪表盘，含总览、订单明细、汇总、告警四大视图
- **可解释输出** — Decision Explain 提供逐单决策解释

---

## 快速开始（适用于所有用户）

### 第一步：安装

1. 解压收到的 ZIP 压缩包到电脑任意位置
2. 打开 `BatchManagementTool` 文件夹
3. **双击 `install.bat`**（一键安装）
   - 自动检测并安装 Python（如未安装）
   - 自动创建虚拟环境
   - 自动安装所有依赖

> **注意**：首次安装需要联网，安装过程约 2-5 分钟。

### 第二步：准备数据

将生产数据文件放到项目根目录的 `1.DataBase` 文件夹中：
- `ZCPRS_MMDDYYYY.csv` — 生产计划主表
- `ZC228_MMDDYYYY.csv` — WIP 消耗明细

### 第三步：启动使用

**双击 `启动工具.bat`**，输入要分析的日期（格式：YYYYMMDD），浏览器将自动打开仪表盘。

### 升级到新版本

**双击 `upgrade.bat`**，自动从 GitHub 下载最新版本并更新（用户数据自动备份）。

---

## 目录结构

```
HPMakingBatchManagement/
├── 1.DataBase/              ← 数据文件目录
│   └── CSV/                 ← CSV 格式数据
├── BatchManagementTool/     ← 主程序目录
│   ├── install.bat          ← 一键安装（首次使用）
│   ├── 启动工具.bat          ← 一键启动（日常使用）
│   ├── upgrade.bat          ← 一键升级
│   ├── output/              ← 生成的报告及操作手册
│   ├── data/                ← 参数配置
│   │   └── Parameter.csv    ← 产品属性与 WIP 映射
│   ├── src/                 ← 源代码
│   │   ├── main.py          ← 主程序入口
│   │   ├── data_loader.py   ← 数据加载与预处理
│   │   ├── models.py        ← 数据模型定义
│   │   ├── logic.py         ← 核心业务逻辑与算法
│   │   ├── report.py        ← 报告生成
│   │   ├── summary_tables.py← 汇总表计算
│   │   └── web_server.py    ← Web Dashboard 服务
│   ├── static/              ← 前端静态资源
│   │   ├── css/style.css
│   │   └── js/app.js
│   ├── templates/           ← 页面模板
│   │   ├── base.html        ← 基础布局
│   │   ├── dashboard.html   ← 总览页
│   │   ├── orders.html      ← 订单明细页
│   │   ├── summary.html     ← 汇总视图页
│   │   └── alerts.html      ← 告警中心页
│   └── tests/               ← 测试用例
│       └── test_tandem_halfbatch.py ← Tandem/HalfBatch 告警测试
├── scripts/
│   └── download_tool.py     ← GitHub 下载脚本
└── Requirement.md           ← 需求与实施说明文档
```

---

## Web Dashboard 页面说明

### 1. Dashboard 总览
- **KPI 卡片** — 总订单数、总批次数、平均利用率、告警数
- **系统产能热力图 (by Day)** — 各系统按日期的使用率可视化，点击可联动右侧班次图
- **系统产能热力图 (by Shift)** — 按系统/日期/班次 (N/D/M) 分解显示产能占用
- **告警预览** — 最近的系统告警，点击 View 跳转订单页并自动筛选相关订单

### 2. Orders 订单明细
- 全量订单搜索、筛选（系统/班次/类型/产线/日期）
- 排序、分页浏览
- 点击订单查看详细信息（含 Decision Explain、Status）
- 导出 Excel/CSV
- **Batch Count 列** — 显示每个订单的批次数
- **Batch Note 列** — 显示搭批信息
- **单元格计算器** — 点击 MSU 或 Batch Count 单元格选中，Ctrl+点击追加选中，右下角实时显示求和
- **告警跳转筛选** — 从告警页点击 View 自动筛选出对应系统/日期/班次的订单

### 3. Summary 汇总视图
- **Daily Batch Count** — 每日批次数按产品类型堆叠图
- **System Utilization** — 各系统每日使用率
- **三个汇总表** — System×Day×Product / Day×Line / Segment×Day

### 4. Alerts 告警中心
- 按严重级别分类：超限（红）、警告（黄）、信息（蓝）
- 一键筛选查看各类别告警
- **三类预警**：
  - **产能超限** — 系统×日期×班次的实际批次数超过上限
  - **Tandem 1.1 过多** — 同一班次使用超过 3 批 1.1 MSU 规格，效率下降警告
  - **Half Batch 超限** — GSS1+2 半批(2.2)每班次超过 5 批（因 GSS2 不支持半批，仅 GSS1 可做）

### 操作手册
- 点击页面右上角的「操作手册」按钮可直接跳转查看完整使用说明
- 内容包括算法逻辑、容差机制、典型案例等详细文档

---

## 高级用法

### 命令行运行

```bash
# 分析指定日期数据
python src/main.py --date 20260403

# 分析并启动 Web Dashboard
python src/main.py --date 20260403 --web

# 不指定日期（自动加载最新数据）
python src/main.py --web
```

### 手动安装依赖

```bash
pip install -r requirements.txt
```

---

## 常见问题

**Q: 双击 bat 文件闪退怎么办？**
A: 右键 → "以管理员身份运行"，或在命令提示符中手动运行。

**Q: 提示"Python未找到"怎么办？**
A: 运行 `install.bat`，它会自动下载安装 Python。

**Q: 浏览器没有自动打开？**
A: 手动在浏览器中输入 `http://localhost:8050`。

**Q: 数据文件格式要求？**
A: 支持 CSV、XLS、XLSX 格式。文件名需为 `ZCPRS_MMDDYYYY` 或 `ZC228_MMDDYYYY` 格式。

**Q: 如何切换浅色/深色主题？**
A: 点击页面右上角的主题切换按钮。

---

## 技术栈

- **后端** — Python 3.8+, Flask, Pandas
- **前端** — HTML5, CSS3, JavaScript (ES6+), ECharts 5.5
- **数据格式** — CSV, Excel (XLS/XLSX)
