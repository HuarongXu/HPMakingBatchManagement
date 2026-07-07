# Plan: 扩展 GSS3 溢出再平衡，兜底 4.4 MSU 批次回迁 GSS1+2

关联 spec：`specs/gss3-overflow-rebalance-4400/spec.md`
方式：TDD（先红后绿），外科手术式改动，仅限 `_rebalance_overflow_batches`。

---

## 任务 1：写红测试 `tests/test_overflow_rebalance.py`

构造最小场景直接调用 `_rebalance_overflow_batches(batches, tracker, system_lookup)`。

- **Test A（回迁 4.4）**：GSS3 该班 physical 超上限（例如上限 5，构造 6 缸含一个 4.4 批=2缸），
  4.4 批订单的 `available_systems` 含 GSS1+2，GSS1+2 该班 usage 有余量 → 断言该批
  `assigned_system` 变为 GSS1+2，`physical_batches` 变 1，GSS3 usage 下降至 ≤ 上限。
- **Test B（产能不足不搬）**：同上但 GSS1+2 该班 usage 已接近上限，搬入会超 → 断言批次仍在 GSS3。
- **Test C（GSS3-only 不搬）**：4.4 批订单 `available_systems` 不含 GSS1+2 → 断言仍在 GSS3。
- **Test D（2.2 零回归）**：仅一个 2.2 转换单（`allow_gss12_reduced_moq=True`）在超缸 GSS3 →
  断言仍按原逻辑搬到 GSS1+2（行为不变）。

辅助：需构造 `MakingSystem`（GSS1+2、GSS3）、`ProductionOrder`、`Batch`、`BatchCapacityTracker`。
参考 `test_bucket_distribution.py` 与 `models.py` 的既有构造方式。用自定义 `check()` 风格
（与既有测试一致，非 pytest）。

**验收**：运行应 RED —— Test A 失败（当前 4.4 被 `msu_size ≤ 2.2` 过滤，不会回迁），
B/C/D 通过。

命令：
```
cd "C:\0.Local\0.3 Project study base\4.HP Making Batch management tool"
$env:PYTHONIOENCODING="utf-8"
.\.venv\Scripts\python.exe BatchManagementTool\tests\test_overflow_rebalance.py
```

---

## 任务 2：实现 —— 扩展候选条件（GREEN）

修改 `_rebalance_overflow_batches`（logic.py:1825-1874）候选过滤与产能校验：

1. 移除/替换硬编码 `batch.msu_size <= GSS12_HALF_MOQ + _tolerance_band(GSS12_HALF_MOQ)` 限制。
2. 候选批次改为满足全部：
   - `batch.assigned_system == source_system`（GSS3）、date/shift 匹配（不变）；
   - `_system_allows_target_for_orders(gss12_system, batch.msu_size, batch.orders)`（保留，R5）；
   - **新增 R3**：`all(gss12_system.system_id in {s.system_id for s in (o.available_systems or [])}
     for o in batch.orders)`——批内所有订单都能在 GSS1+2 生产。
3. 产能校验（R4）保持既有：`physical = _calculate_physical_batches(gss12_system, batch.msu_size)`；
   `if limit and usage + physical > limit: continue`。4.4 在 GSS1+2 = 1 缸，天然满足语义。
4. 执行搬迁时（R6）除既有的 `assigned_system`/`physical_batches`/`order.assigned_system` 外，
   补充：
   - 调 `_refresh_batch_notes(batch)` 刷新批注；
   - 为批内订单写 `decision_explain` 信息性说明，如：
     `f"批次再平衡: 原 GSS3 {batch.msu_size:.1f} MSU 批次因超缸回迁至 GSS1 + GSS2。"`

**注意**：保持 `while True` 单次搬一批 + `tracker.rebuild_usage` 的既有循环结构不变，
确保多次溢出可迭代解决且每步重算用量。

**验收**：`test_overflow_rebalance.py` 全过（ALL TESTS PASSED，退出码 0）。

---

## 任务 3：回归既有测试

```
.\.venv\Scripts\python.exe BatchManagementTool\tests\test_bucket_distribution.py   # 期望 15/15
.\.venv\Scripts\python.exe BatchManagementTool\tests\test_tandem_halfbatch.py      # 期望 14/14
```
两者均须 ALL TESTS PASSED（R7/R8 零回归）。

---

## 任务 4：端到端验证（--date 20260707）

```
cd "C:\0.Local\0.3 Project study base\4.HP Making Batch management tool\BatchManagementTool"
$env:PYTHONIOENCODING="utf-8"
..\.venv\Scripts\python.exe src\main.py --date 20260707
```
用 pandas 读最新 `output/batch_report_20260707_*.xlsx`：
- 911042020 三段全部 `Assigned System = GSS1 + GSS2`（段3 已回迁）；
- Alerts 中不再有 `2026-07-08 N班 GSS3 计划 7 批, 超出最大批次 5`；
- 对比修复前 Alerts，确认无新增告警；
- GSS3 2026-07-08 N 班 缸数 ≤ 5。

若 911042020 段3 仍未回迁，需进一步排查（不可乐观汇报），检查 rebuild_usage 时序与候选判定。

---

## 任务 5：git commit

只暂存本任务相关文件：
```
git add BatchManagementTool/src/logic.py BatchManagementTool/tests/test_overflow_rebalance.py specs/gss3-overflow-rebalance-4400/ plans/2026-07-07-gss3-overflow-rebalance-4400.md
```
提交信息（含 Co-authored-by trailer）：
```
fix(logic): 扩展 GSS3 溢出再平衡，兜底 4.4 批回迁 GSS1+2

high_load_flag 启发式在 GSS1+2 达 8/10 缸(0.8≥0.75)时把 4.4 批分流到
GSS3，而 4.4 在 GSS3 占 2 缸(翻倍)，反而使 GSS3 超班次上限。既有兜底
_rebalance_overflow_batches 硬编码只搬 ≤2.2 批，无法挽救 4.4 溢出。

放开该后处理的尺寸限制：GSS3 超缸时，4.4(及倍数)批在满足
- 批内所有订单 available_systems 含 GSS1+2(产品适用性守恒)
- GSS1+2 该班 usage+physical ≤ limit(产能守恒)
- 既有 MOQ 规则(_system_allows_target_for_orders)
时回迁 GSS1+2，并刷新批注与 decision_explain。不改动通用分配启发式。

验证：新增 test_overflow_rebalance.py(A回迁/B产能不足/C GSS3-only/D 2.2零回归)
全过；test_bucket_distribution、test_tandem_halfbatch 回归全过；--date 20260707
端到端确认 911042020 三段全落 GSS1+2、07-08 N班 GSS3 超缸告警消失且无新增。

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
```

推送前重跑任务 3 两套测试确认干净，再 `git push origin main`。
