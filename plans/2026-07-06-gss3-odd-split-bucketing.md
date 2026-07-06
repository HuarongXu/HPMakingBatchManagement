# GSS3 奇数倍批次拆分：装桶逻辑修正 实现计划

> **执行方式：** 用 executing-tasks 技能逐任务实现。步骤用 `- [ ]` 复选框跟踪。

**目标：** 修正 `_distribute_orders_to_buckets`，让已有的"GSS3 奇数倍批次拆成 4.4(GSS1+2)×n + 2.2(GSS3)"自愈机制在批次含已拆分段时也能成功。
**架构：** 两阶段装桶——阶段一把不可再拆的整段（`segment_total > 1`）放进尺寸匹配、未占用的 bucket 并"锁桶"；阶段二对其余可拆订单沿用现有时间顺序填充逻辑，跳过已锁的桶。批次不含已拆分段时行为与原实现等价。
**技术栈：** Python 3.13、纯函数改动、无新依赖；测试为独立脚本（沿用仓库现有 `tests/*.py` 风格，自带 `check()`）。
**关联规范：** specs/gss3-odd-split-bucketing/spec.md

## 文件结构

- **修改** `BatchManagementTool/src/logic.py` —— 仅替换 `_distribute_orders_to_buckets` 一个函数（当前约在第 1917–1985 行）。不动其它函数。
- **新增** `BatchManagementTool/tests/test_bucket_distribution.py` —— 覆盖 R1/R2/R3/R4/R5 的单元测试脚本。

---

## 任务 1：写会失败的测试（RED）

**Files:**
- 创建：`BatchManagementTool/tests/test_bucket_distribution.py`

- [ ] 创建测试文件，内容如下（逐字）：

```python
"""
验证 _distribute_orders_to_buckets 的两阶段装桶：
已拆分段（segment_total>1）整段进尺寸匹配 bucket，其余可拆订单按时间填充。
对应 specs/gss3-odd-split-bucketing/spec.md 的 R1–R5。
独立脚本运行：python BatchManagementTool/tests/test_bucket_distribution.py
"""
import sys
sys.path.insert(0, 'BatchManagementTool/src')

from datetime import datetime
from models import ProductionOrder
from logic import _distribute_orders_to_buckets

passed = 0
failed = 0

def check(label, condition):
    global passed, failed
    if condition:
        print(f'  PASS: {label}')
        passed += 1
    else:
        print(f'  FAIL: {label}')
        failed += 1

def mk(order_number, demand, dt_str, seg_total=1, seg_idx=1, orig=None):
    o = ProductionOrder(
        order_number=order_number, material='TEST', work_center='HPHRPACK',
        planned_quantity=demand, uom='MSU',
        start_datetime=datetime.fromisoformat(dt_str),
        end_datetime=datetime.fromisoformat(dt_str),
        mrp_element='PlOrd', shift='N', product_category='shampoo',
    )
    o.msu_demand = demand
    o.segment_total = seg_total
    o.segment_index = seg_idx
    o.original_order_number = orig
    return o

def load_of(bucket):
    return round(sum(o.msu_demand or 0.0 for o in bucket), 3)

# ============================================================
# TEST A (R2 核心回归)：2.31 + 4.4段 + 4.4段, 目标 [4.4,4.4,2.2]
#   期望 buckets = [[4.4段],[4.4段],[2.31]]，不得为 None
# ============================================================
print('\n--- Test A: 已拆分段应各占 4.4 桶，零头单进 2.2 桶 ---')
small = mk('3344736029', 2.31, '2026-07-09T01:15:49')
seg1 = mk('3375830548-1', 4.4, '2026-07-09T02:53:55', seg_total=2, seg_idx=1, orig='3375830548')
seg2 = mk('3375830548-2', 4.4, '2026-07-09T02:53:55', seg_total=2, seg_idx=2, orig='3375830548')
g = [small, seg1, seg2]
res = _distribute_orders_to_buckets([small, seg1, seg2], [4.4, 4.4, 2.2], g)
check('不返回 None', res is not None)
if res is not None:
    check('3 个 bucket', len(res) == 3)
    check('bucket0 负载≈4.4', abs(load_of(res[0]) - 4.4) < 0.01)
    check('bucket1 负载≈4.4', abs(load_of(res[1]) - 4.4) < 0.01)
    check('bucket2 负载≈2.31', abs(load_of(res[2]) - 2.31) < 0.01)
    ids2 = [o.order_number for o in res[2]]
    check('2.31 单在 bucket2', '3344736029' in ids2)
    check('两个 4.4 段各自独占前两个 bucket',
          len(res[0]) == 1 and len(res[1]) == 1)

# ============================================================
# TEST B (R3)：不可拆段无匹配尺寸 bucket => None
# ============================================================
print('\n--- Test B: 4.4 已拆分段, 桶全是 2.2 => 无法安置, 返回 None ---')
seg = mk('X-1', 4.4, '2026-07-09T01:00:00', seg_total=2, seg_idx=1, orig='X')
resB = _distribute_orders_to_buckets([seg], [2.2, 2.2], [seg])
check('返回 None', resB is None)

# ============================================================
# TEST C (R4)：无已拆分段, 行为与预期一致
# ============================================================
print('\n--- Test C: 无已拆分段, 4.4 + 2.2 => [[4.4],[2.2]] ---')
oa = mk('A', 4.4, '2026-07-09T01:00:00')
ob = mk('B', 2.2, '2026-07-09T02:00:00')
resC = _distribute_orders_to_buckets([oa, ob], [4.4, 2.2], [oa, ob])
check('不返回 None', resC is not None)
if resC is not None:
    check('bucket0=[A]', [o.order_number for o in resC[0]] == ['A'])
    check('bucket1=[B]', [o.order_number for o in resC[1]] == ['B'])

# ============================================================
# TEST D (R5)：可拆整单跨桶应正常拆分并同步 global_orders
# ============================================================
print('\n--- Test D: 单个 6.6 可拆单, 目标 [4.4,2.2] => 拆成 4.4+2.2 ---')
big = mk('BIG', 6.6, '2026-07-09T01:00:00')
gD = [big]
resD = _distribute_orders_to_buckets([big], [4.4, 2.2], gD)
check('不返回 None', resD is not None)
if resD is not None:
    check('bucket0 负载≈4.4', abs(load_of(resD[0]) - 4.4) < 0.05)
    check('bucket1 负载≈2.2', abs(load_of(resD[1]) - 2.2) < 0.05)
    check('global_orders 已替换为两段', len(gD) == 2)

# ============================================================
print(f'\n{"="*50}')
print(f'Results: {passed} passed, {failed} failed out of {passed+failed} checks')
print('ALL TESTS PASSED!' if failed == 0 else 'SOME TESTS FAILED!')
print(f'{"="*50}')
sys.exit(0 if failed == 0 else 1)
```

- [ ] 运行测试，确认 **Test A 失败**（当前实现对已拆分段横跨桶边界会 `return None`）：

```
cd "C:\0.Local\0.3 Project study base\4.HP Making Batch management tool"
$env:PYTHONIOENCODING="utf-8"; .\.venv\Scripts\python.exe BatchManagementTool\tests\test_bucket_distribution.py
```

预期输出含：`Test A` 下 `FAIL: 不返回 None`（以及随后依赖 res 的检查未执行），结尾 `SOME TESTS FAILED!`，退出码 1。

---

## 任务 2：实现两阶段装桶（GREEN）

**Files:**
- 修改：`BatchManagementTool/src/logic.py`（函数 `_distribute_orders_to_buckets`）

- [ ] 用下面的新实现**整体替换**现有 `_distribute_orders_to_buckets` 函数（从 `def _distribute_orders_to_buckets(` 到其 `return buckets` 结束的整段）：

```python
def _distribute_orders_to_buckets(
    batch_orders: List[ProductionOrder],
    bucket_targets: List[float],
    global_orders: List[ProductionOrder],
) -> Optional[List[List[ProductionOrder]]]:
    """把订单填入各 bucket（前面的 bucket 先填满）。
    阶段一：不可再拆的整段（segment_total > 1）先整段放入尺寸匹配、尚未占用的 bucket；
    阶段二：其余可拆订单按时间顺序填充未占用 bucket，跨桶边界时拆成两个 segment。
    批次不含已拆分段时，行为与原逐时间填充实现等价。
    返回每个 bucket 的订单列表；若遇到无法安全拆分的情况返回 None。"""
    buckets: List[List[ProductionOrder]] = [[] for _ in bucket_targets]
    loads = [0.0] * len(bucket_targets)
    reserved = [False] * len(bucket_targets)
    splits: List[Tuple[ProductionOrder, List[ProductionOrder]]] = []

    # 阶段一：把不可再拆的整段放入尺寸匹配、尚未占用的 bucket
    for order in [o for o in batch_orders if o.segment_total > 1]:
        demand = order.msu_demand or 0.0
        placed = False
        for bi, target in enumerate(bucket_targets):
            if reserved[bi]:
                continue
            if _within_hard_tolerance(demand, target):
                buckets[bi].append(order)
                loads[bi] = demand
                reserved[bi] = True
                placed = True
                break
        if not placed:
            return None  # 不可拆段无匹配 bucket，放弃拆分（维持原批）

    # 阶段二：其余可拆订单按时间顺序填充未占用 bucket
    pending = sorted(
        [o for o in batch_orders if o.segment_total <= 1],
        key=lambda o: o.start_datetime,
    )

    def _next_open_bucket(bi: int) -> int:
        while bi < len(bucket_targets) and reserved[bi]:
            bi += 1
        return bi

    bi = _next_open_bucket(0)
    i = 0
    while i < len(pending):
        if bi >= len(bucket_targets):
            return None  # 还有订单但没有 bucket 容纳，放弃
        order = pending[i]
        demand = order.msu_demand or 0.0
        target = bucket_targets[bi]
        hard_tol = _hard_tolerance_band(target)
        pref_tol = _tolerance_band(target)
        space = target + hard_tol - loads[bi]

        if demand <= space + 1e-9:
            buckets[bi].append(order)
            loads[bi] += demand
            i += 1
            if loads[bi] >= target - pref_tol and bi < len(bucket_targets) - 1:
                bi = _next_open_bucket(bi + 1)
            continue

        # 订单跨越 bucket 边界，需要拆分
        if bi >= len(bucket_targets) - 1:
            return None  # 最后一个 bucket 不能再溢出
        first_amount = target - loads[bi]
        if first_amount <= 1e-6:
            bi = _next_open_bucket(bi + 1)
            continue
        second_amount = demand - first_amount
        seg_a, seg_b = _make_order_split(order, first_amount, second_amount)
        buckets[bi].append(seg_a)
        loads[bi] += first_amount
        pending[i] = seg_b  # 余量继续向后分配
        splits.append((order, [seg_a, seg_b]))
        bi = _next_open_bucket(bi + 1)

    if any(not bucket for bucket in buckets):
        return None  # 存在空 bucket，拆分无意义

    # 将拆分结果同步到全局订单列表，保证下游报表能看到拆分行
    for original, segs in splits:
        if original in global_orders:
            pos = global_orders.index(original)
            global_orders[pos:pos + 1] = segs
        else:
            global_orders.extend(segs)

    return buckets
```

- [ ] 运行新测试，确认**全部通过**：

```
cd "C:\0.Local\0.3 Project study base\4.HP Making Batch management tool"
$env:PYTHONIOENCODING="utf-8"; .\.venv\Scripts\python.exe BatchManagementTool\tests\test_bucket_distribution.py
```

预期结尾：`ALL TESTS PASSED!`，退出码 0。

---

## 任务 3：回归——既有测试仍全绿

**Files:** 无改动（仅运行）

- [ ] 运行既有两个测试脚本，确认无回归：

```
cd "C:\0.Local\0.3 Project study base\4.HP Making Batch management tool"
$env:PYTHONIOENCODING="utf-8"; .\.venv\Scripts\python.exe BatchManagementTool\tests\test_tandem_halfbatch.py
```

预期：结尾 `ALL TESTS PASSED!`（`test_tolerance.py` 为旧的独立打印脚本，无断言，运行不报错即可，选跑）。

---

## 任务 4：端到端验证（R6）

**Files:** 无改动（仅运行与检查）

- [ ] 用今天数据跑完整流程并生成报告：

```
cd "C:\0.Local\0.3 Project study base\4.HP Making Batch management tool\BatchManagementTool"
$env:PYTHONIOENCODING="utf-8"; ..\.venv\Scripts\python.exe src\main.py --date 20260706
```

- [ ] 读取最新 `output\batch_report_*.xlsx` 的 Orders 表，确认订单 3375830548 的两段 `Assigned System` = `GSS1 + GSS2`、2.31 单在 `GSS3`、且不存在 `Decision Explain` 中 `Target=11.0` 且 `System=GSS3` 的行：

```
cd "C:\0.Local\0.3 Project study base\4.HP Making Batch management tool"
$env:PYTHONIOENCODING="utf-8"; .\.venv\Scripts\python.exe -c "import pandas as pd, glob; f=sorted(glob.glob('BatchManagementTool/output/batch_report_*.xlsx'))[-1]; d=pd.read_excel(f,'Orders'); m=d[d['Order Number'].astype(str).str.contains('3375830548')]; print(f); print(m[['Order Number','MSU Demand','Assigned System','Batch Note']].to_string()); print('has 11.0 GSS3:', d['Decision Explain'].astype(str).str.contains('Target=11.0').pipe(lambda s: (s & d['Assigned System'].astype(str).str.contains('GSS3')).any()))"
```

预期：3375830548 两段系统为 `GSS1 + GSS2`；`has 11.0 GSS3: False`。

---

## 任务 5：提交

**Files:** `BatchManagementTool/src/logic.py`、`BatchManagementTool/tests/test_bucket_distribution.py`、`specs/`、`plans/`

- [ ] 提交改动（commit message 说明"为什么"）：

```
cd "C:\0.Local\0.3 Project study base\4.HP Making Batch management tool"
git add BatchManagementTool/src/logic.py BatchManagementTool/tests/test_bucket_distribution.py specs/gss3-odd-split-bucketing plans/2026-07-06-gss3-odd-split-bucketing.md
git commit -m "fix(logic): 两阶段装桶让 GSS3 奇数倍批次自愈在含已拆分段时生效

原 _distribute_orders_to_buckets 按时间顺序填桶，零头单先占 4.4 桶，
导致已拆分的 4.4 段横跨桶边界需二次拆分而静默返回 None，
使 11.0/GSS3 批无法拆回 4.4(GSS1+2)+2.2(GSS3)、负载堆在满载的 GSS3。
改为两阶段：不可拆整段先按尺寸匹配锁桶，其余可拆单再按时间填充。

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

预期：提交成功。
