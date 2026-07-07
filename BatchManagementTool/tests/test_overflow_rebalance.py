"""
验证 _rebalance_overflow_batches 扩展后的兜底回迁：
GSS3 超缸时，4.4(及倍数)批在满足系统适用性 + 产能 + MOQ 规则时回迁 GSS1+2。
对应 specs/gss3-overflow-rebalance-4400/spec.md 的 R1–R7。
独立脚本运行：python BatchManagementTool/tests/test_overflow_rebalance.py
"""
import sys
sys.path.insert(0, 'BatchManagementTool/src')

from datetime import datetime
from models import ProductionOrder, MakingSystem, Batch
from logic import _rebalance_overflow_batches, BatchCapacityTracker

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

def mk_gss12():
    return MakingSystem(
        system_id='S12', name='GSS1 + GSS2', supported_msu=[4.4],
        capacity_tons=[4.4], product_suitability=['shampoo', 'conditioner'],
        n_shift_limit=10, d_shift_limit=10, m_shift_limit=10,
    )

def mk_gss3():
    return MakingSystem(
        system_id='S3', name='GSS3', supported_msu=[2.2],
        capacity_tons=[2.2], product_suitability=['shampoo', 'conditioner'],
        n_shift_limit=5, d_shift_limit=5, m_shift_limit=5,
    )

def mk_order(num, demand, avail, allow_reduced=False):
    o = ProductionOrder(
        order_number=num, material='TEST', work_center='HPHRPACK',
        planned_quantity=demand, uom='MSU',
        start_datetime=datetime(2026, 7, 8, 1, 0),
        end_datetime=datetime(2026, 7, 8, 3, 0),
        mrp_element='PlOrd', shift='N', product_category='shampoo',
        allow_gss12_reduced_moq=allow_reduced,
    )
    o.msu_demand = demand
    o.available_systems = avail
    o.batch_count = 0.0
    return o

def mk_batch(bid, system, msu_size, physical, orders):
    return Batch(
        batch_id=bid, wip_code='W1', msu_size=msu_size,
        assigned_system=system, shift='N', date='2026-07-08',
        orders=orders, current_load=msu_size, physical_batches=physical,
    )

def filler(bid, system, physical):
    """无订单的占位批，仅用于制造班次用量。"""
    return mk_batch(bid, system, 4.4, physical, [])

def gss3_cyl(tracker, gss3):
    return tracker.get_shift_usage(gss3, '2026-07-08', 'N')

# ============================================================
# TEST A (R1/R2/R4)：GSS3 超缸 + 一个 4.4 批可回迁 + GSS1+2 有余量 => 回迁
#   GSS3: 4(filler) + 2(4.4批) = 6 > 5；GSS1+2: 7 有余量(+1=8<=10)
# ============================================================
print('\n--- Test A: 4.4 批因 GSS3 超缸回迁 GSS1+2 ---')
gss12, gss3 = mk_gss12(), mk_gss3()
o44 = mk_order('911042020', 4.4, [gss12, gss3])
mv = mk_batch('B44', gss3, 4.4, 2, [o44])
systems = [gss12, gss3]
lookup = {s.system_id: s for s in systems}
tracker = BatchCapacityTracker(systems)
batches = [filler('BF12', gss12, 7), filler('BF3', gss3, 4), mv]
_rebalance_overflow_batches(batches, tracker, lookup)
check('4.4 批 assigned_system 变为 GSS1 + GSS2', mv.assigned_system is gss12)
check('4.4 批 physical_batches 变为 1', mv.physical_batches == 1)
check('订单 assigned_system 同步为 GSS1 + GSS2', o44.assigned_system is gss12)
tracker.rebuild_usage(batches)
check('GSS3 班次缸数降至 <= 5', gss3_cyl(tracker, gss3) <= 5)
check('GSS1+2 班次缸数 <= 10', tracker.get_shift_usage(gss12, '2026-07-08', 'N') <= 10)
check('decision_explain 含再平衡说明', bool(o44.decision_explain) and '回迁' in (o44.decision_explain or ''))

# ============================================================
# TEST B (R4)：GSS1+2 无余量(已 10 缸) => 不回迁
# ============================================================
print('\n--- Test B: GSS1+2 无余量, 不回迁 ---')
gss12, gss3 = mk_gss12(), mk_gss3()
o44 = mk_order('911042020', 4.4, [gss12, gss3])
mv = mk_batch('B44', gss3, 4.4, 2, [o44])
systems = [gss12, gss3]
lookup = {s.system_id: s for s in systems}
tracker = BatchCapacityTracker(systems)
batches = [filler('BF12', gss12, 10), filler('BF3', gss3, 4), mv]
_rebalance_overflow_batches(batches, tracker, lookup)
check('4.4 批仍在 GSS3', mv.assigned_system is gss3)
check('physical_batches 仍为 2', mv.physical_batches == 2)

# ============================================================
# TEST C (R3)：4.4 批为 GSS3-only(available 不含 GSS1+2) => 不回迁
# ============================================================
print('\n--- Test C: GSS3-only 产品, 不回迁 ---')
gss12, gss3 = mk_gss12(), mk_gss3()
o44 = mk_order('OnlyG3', 4.4, [gss3])  # available 不含 gss12
mv = mk_batch('B44', gss3, 4.4, 2, [o44])
systems = [gss12, gss3]
lookup = {s.system_id: s for s in systems}
tracker = BatchCapacityTracker(systems)
batches = [filler('BF12', gss12, 7), filler('BF3', gss3, 4), mv]
_rebalance_overflow_batches(batches, tracker, lookup)
check('GSS3-only 4.4 批仍在 GSS3', mv.assigned_system is gss3)

# ============================================================
# TEST D (R7 零回归)：仅 2.2 转换单溢出 => 按原逻辑回迁 GSS1+2
# ============================================================
print('\n--- Test D: 2.2 转换单零回归回迁 ---')
gss12, gss3 = mk_gss12(), mk_gss3()
o22 = mk_order('Conv22', 2.2, [gss12, gss3], allow_reduced=True)
mv = mk_batch('B22', gss3, 2.2, 1, [o22])
systems = [gss12, gss3]
lookup = {s.system_id: s for s in systems}
tracker = BatchCapacityTracker(systems)
# GSS3: 5(filler) + 1(2.2批) = 6 > 5；GSS1+2: 3 有余量
batches = [filler('BF12', gss12, 3), filler('BF3', gss3, 5), mv]
_rebalance_overflow_batches(batches, tracker, lookup)
check('2.2 转换单回迁 GSS1 + GSS2', mv.assigned_system is gss12)

# ============================================================
print(f'\n{"="*50}')
print(f'Results: {passed} passed, {failed} failed out of {passed+failed} checks')
print('ALL TESTS PASSED!' if failed == 0 else 'SOME TESTS FAILED!')
print(f'{"="*50}')
sys.exit(0 if failed == 0 else 1)
