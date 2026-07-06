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
