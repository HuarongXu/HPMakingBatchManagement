# Spec: 扩展 GSS3 溢出再平衡，兜底 4.4 MSU 批次回迁 GSS1+2

## 背景 / 问题

在 20260707 数据、2026-07-08 N 班出现告警：`GSS3 计划 7 批, 超出最大批次 5`。

根因（已用调试实测确认，非推测）：

1. **主因 — 分配启发式 `high_load_flag` 过早分流**
   订单 911042020（REJ DC COMFORTING SH，13.2 MSU = 3 段 × 4.4）：段1、2 正确进 GSS1+2；
   段3 分配时 GSS1+2 已用 7 缸，放第 8 缸 → `8/10 = 0.8 ≥ 0.75` 触发 `high_load_flag=1`
   （logic.py:1509）。评分元组 `(overflow, high_load, priority, usage, closest)` 中 high_load
   权重高于 priority，于是 GSS3 (0,0,1,...) 胜过 GSS1+2 (0,1,0,...)。
   但一个 4.4 批在 GSS3 占 **2 个物理缸**（2.2×2），在 GSS1+2 只占 **1 缸**——分流不但没减负，
   反而使 GSS3 达 7 缸（超上限 5）。

2. **次因 — 挽救后处理 `_rebalance_overflow_batches` 未兜底**
   该函数本应把 GSS3 溢出批搬回有余量的 GSS1+2，但候选过滤硬编码只接受
   `msu_size ≤ 2.2 + tol`（logic.py:1855，为旧的 12t→6t 转换单设计）。
   911042020 溢出的是 4.4 批，被直接跳过 → 兜底失效。

方向 B（用户已选）：**扩展 `_rebalance_overflow_batches` 的候选条件，让它也能把 GSS3
溢出的 4.4（及 4.4 倍数）批搬回有产能的 GSS1+2**，不改动通用分配启发式，对其他分配零影响。

## 目标

当 GSS3 某班次物理缸数超上限，且其中存在可在 GSS1+2 生产、且 GSS1+2 该班次有足够剩余
产能容纳的批次时，将该批次回迁到 GSS1+2，从而消除或缓解 GSS3 超缸。

## 需求（Requirements）

- **R1（核心回归）**：对 20260707 数据端到端运行后，订单 911042020 的第 3 段（4.4 MSU）
  应从 GSS3 回迁到 GSS1 + GSS2；2026-07-08 N 班 GSS3 的 `计划 7 批, 超出最大批次 5` 告警消失。

- **R2（放开尺寸限制）**：`_rebalance_overflow_batches` 的候选批次不再被硬编码上限
  `msu_size ≤ 2.2 + tol` 排除。4.4 及 4.4 整数倍的 GSS3 溢出批亦成为回迁候选。

- **R3（产品与系统适用性守恒）**：仅当批次内**所有订单**的 `available_systems` 都包含目标
  GSS1+2 系统（按 system_id 判定）时，该批次才可回迁。这保证不会把仅 GSS3 可生产的产品
  误搬到 GSS1+2（`available_systems` 已内含产品适用性）。

- **R4（产能守恒 / 不制造新溢出）**：回迁前必须校验 GSS1+2 该班次
  `usage + physical_after_move ≤ limit`。其中 `physical_after_move` 按 GSS1+2 上该 `msu_size`
  重新计算（4.4 在 GSS1+2 = 1 缸）。若会导致 GSS1+2 超上限，则不搬。

- **R5（MOQ 规则守恒）**：保留既有 `_system_allows_target_for_orders(gss12, msu_size, orders)`
  校验。即 2.2 half-batch 回迁仍需订单在 12t→6t 转换名单中；4.4+ 不受该限制（本就允许）。

- **R6（记账与展示一致）**：回迁后需同步更新被搬批次的 `assigned_system`、`physical_batches`、
  每个订单的 `assigned_system`、batch note，并在订单 `decision_explain` 写入信息性再平衡
  说明（非预警），使报告如实反映“原 GSS3 因超缸回迁至 GSS1+2”。

- **R7（零回归 — 既有 2.2 行为不变）**：无 4.4 候选、仅有旧式 2.2 转换单溢出时，函数行为
  与原实现等价（仍只搬符合条件的 2.2 批）。

- **R8（不影响通用分配）**：不修改 `_system_score_tuple` / `_select_system_for_target` /
  `high_load_flag`。本次改动仅限后处理 `_rebalance_overflow_batches`。

## 非目标（Out of Scope）

- 不重构 `high_load_flag` 启发式本身（方向 A，本次不做）。
- 不处理 `2026-07-08 N 班 GSS3 计划 7 批`之外的其它既有告警（如 M 班等独立问题）。
- 不改变搭批/尺寸选择/拆分等前序逻辑。

## 验证方式

1. 新增单元测试 `tests/test_overflow_rebalance.py`（TDD 先红后绿）：
   - Test A：GSS3 超缸 + 一个 4.4 批（订单可在 GSS1+2 生产）+ GSS1+2 有余量 → 该 4.4 批回迁 GSS1+2。
   - Test B：GSS3 超缸但 GSS1+2 无余量（会超上限）→ 不回迁（维持 GSS3）。
   - Test C：GSS3 超缸但 4.4 批含 GSS3-only 产品（GSS1+2 不在 available_systems）→ 不回迁。
   - Test D（零回归）：仅 2.2 转换单溢出场景，行为与原实现一致。
2. 回归既有测试 `test_bucket_distribution.py`、`test_tandem_halfbatch.py` 全过。
3. 端到端 `--date 20260707`：验证 R1（911042020 段3 落 GSS1+2，超缸告警消失，无新增告警）。
