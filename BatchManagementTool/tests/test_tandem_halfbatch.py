"""
验证 Tandem 1.1 超 3 批报警 和 GSS1+GSS2 half batch 超 5 批报警
"""
import sys
sys.path.insert(0, 'BatchManagementTool/src')

from datetime import datetime
from models import MakingSystem, Batch, ProductionOrder
from logic import _check_tandem_11_alerts, _check_gss12_half_batch_limit

# ---------- helpers ----------
def _make_system(name, system_id, msu_list):
    return MakingSystem(
        system_id=system_id, name=name,
        supported_msu=msu_list, capacity_tons=[],
        product_suitability=['conditioner'] if 'Tandem' in name else ['shampoo'],
        n_shift_limit=5, d_shift_limit=5, m_shift_limit=5,
    )

def _make_order(order_number, shift, dt_str):
    return ProductionOrder(
        order_number=order_number, material='TEST', work_center='HPHDPACK',
        planned_quantity=1.1, uom='MSU',
        start_datetime=datetime.fromisoformat(dt_str),
        end_datetime=datetime.fromisoformat(dt_str),
        mrp_element='PlOrd', shift=shift,
        product_category='conditioner',
    )

def _make_batch(batch_id, system, msu_size, shift, date, orders, physical=1):
    b = Batch(
        batch_id=batch_id, wip_code='TEST_WIP', msu_size=msu_size,
        assigned_system=system, shift=shift, date=date,
        orders=orders, current_load=msu_size, physical_batches=physical,
    )
    for o in orders:
        o.assigned_system = system
        o.batch_id = batch_id
    return b

TANDEM = _make_system('Tandem', 'GSS4', [1.1, 2.2, 4.4])
GSS12  = _make_system('GSS1 + GSS2', 'GSS1_2', [4.4])

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

# ============================================================
# TEST 1: Tandem 1.1 <= 3 per shift => NO alert
# ============================================================
print('\n--- Test 1: Tandem 1.1 x3 same shift (should NOT alert) ---')
batches = []
for i in range(3):
    o = _make_order(f'T1-{i}', 'D', '2026-05-26T10:00:00')
    batches.append(_make_batch(f'BT1-{i}', TANDEM, 1.1, 'D', '2026-05-26', [o]))

_check_tandem_11_alerts(batches)
alerts = [a for o in sum((b.orders for b in batches), []) for a in o.alerts]
check('No alert when exactly 3 batches', len(alerts) == 0)

# ============================================================
# TEST 2: Tandem 1.1 = 4 per shift => ALERT
# ============================================================
print('\n--- Test 2: Tandem 1.1 x4 same shift (SHOULD alert) ---')
batches = []
for i in range(4):
    o = _make_order(f'T2-{i}', 'D', '2026-05-26T10:00:00')
    batches.append(_make_batch(f'BT2-{i}', TANDEM, 1.1, 'D', '2026-05-26', [o]))

_check_tandem_11_alerts(batches)
alerts = [a for o in sum((b.orders for b in batches), []) for a in o.alerts]
check('Alert triggered when 4 batches', len(alerts) > 0)
check('Alert mentions Tandem', any('Tandem' in a for a in alerts))
check('Alert mentions 4 batches', any('4' in a for a in alerts))
check('All 4 orders get the alert', len(alerts) == 4)
print(f'  Alert text: {alerts[0] if alerts else "(none)"}')

# ============================================================
# TEST 3: Tandem 1.1 = 5 per shift => ALERT
# ============================================================
print('\n--- Test 3: Tandem 1.1 x5 same shift (SHOULD alert) ---')
batches = []
for i in range(5):
    o = _make_order(f'T3-{i}', 'N', '2026-05-27T02:00:00')
    batches.append(_make_batch(f'BT3-{i}', TANDEM, 1.1, 'N', '2026-05-27', [o]))

_check_tandem_11_alerts(batches)
alerts = [a for o in sum((b.orders for b in batches), []) for a in o.alerts]
check('Alert triggered when 5 batches', len(alerts) == 5)

# ============================================================
# TEST 4: Tandem 2.2 and 4.4 => NO 1.1 alert
# ============================================================
print('\n--- Test 4: Tandem 2.2/4.4 only (should NOT trigger 1.1 alert) ---')
batches = []
for i in range(5):
    o = _make_order(f'T4-{i}', 'D', '2026-05-26T10:00:00')
    batches.append(_make_batch(f'BT4-{i}', TANDEM, 2.2, 'D', '2026-05-26', [o]))
for i in range(3):
    o = _make_order(f'T4B-{i}', 'D', '2026-05-26T10:00:00')
    batches.append(_make_batch(f'BT4B-{i}', TANDEM, 4.4, 'D', '2026-05-26', [o]))

_check_tandem_11_alerts(batches)
alerts = [a for o in sum((b.orders for b in batches), []) for a in o.alerts]
check('No 1.1 alert for 2.2/4.4 batches', len(alerts) == 0)

# ============================================================
# TEST 5: Different shifts => each under limit => NO alert
# ============================================================
print('\n--- Test 5: Tandem 1.1 spread across shifts (should NOT alert) ---')
batches = []
shift_hours = {'N': '02', 'D': '10', 'M': '18'}
for shift in ['N', 'D', 'M']:
    for i in range(3):
        hour = shift_hours[shift]
        o = _make_order(f'T5-{shift}-{i}', shift, f'2026-05-26T{hour}:00:00')
        batches.append(_make_batch(f'BT5-{shift}-{i}', TANDEM, 1.1, shift, '2026-05-26', [o]))

_check_tandem_11_alerts(batches)
alerts = [a for o in sum((b.orders for b in batches), []) for a in o.alerts]
check('No alert when each shift has 3 batches', len(alerts) == 0)

# ============================================================
# TEST 6: GSS1+2 half batch <= 5 per shift => NO alert
# ============================================================
print('\n--- Test 6: GSS1+2 half batch x5 same shift (should NOT alert) ---')
batches = []
for i in range(5):
    o = _make_order(f'H6-{i}', 'N', '2026-05-26T02:00:00')
    o.product_category = 'shampoo'
    o.allow_gss12_reduced_moq = True
    batches.append(_make_batch(f'BH6-{i}', GSS12, 2.2, 'N', '2026-05-26', [o]))

_check_gss12_half_batch_limit(batches)
alerts = [a for o in sum((b.orders for b in batches), []) for a in o.alerts]
check('No alert when exactly 5 half batches', len(alerts) == 0)

# ============================================================
# TEST 7: GSS1+2 half batch = 6 per shift => ALERT
# ============================================================
print('\n--- Test 7: GSS1+2 half batch x6 same shift (SHOULD alert) ---')
batches = []
for i in range(6):
    o = _make_order(f'H7-{i}', 'N', '2026-05-26T02:00:00')
    o.product_category = 'shampoo'
    o.allow_gss12_reduced_moq = True
    batches.append(_make_batch(f'BH7-{i}', GSS12, 2.2, 'N', '2026-05-26', [o]))

_check_gss12_half_batch_limit(batches)
alerts = [a for o in sum((b.orders for b in batches), []) for a in o.alerts]
check('Alert triggered when 6 half batches', len(alerts) > 0)
check('Alert mentions half batch', any('half batch' in a for a in alerts))
check('Alert mentions GSS2', any('GSS2' in a for a in alerts))
check('All 6 orders get the alert', len(alerts) == 6)
print(f'  Alert text: {alerts[0] if alerts else "(none)"}')

# ============================================================
# TEST 8: GSS1+2 full batch 4.4 => NO half batch alert
# ============================================================
print('\n--- Test 8: GSS1+2 full batch 4.4 x8 (should NOT trigger half batch alert) ---')
batches = []
for i in range(8):
    o = _make_order(f'H8-{i}', 'N', '2026-05-26T02:00:00')
    o.product_category = 'shampoo'
    batches.append(_make_batch(f'BH8-{i}', GSS12, 4.4, 'N', '2026-05-26', [o]))

_check_gss12_half_batch_limit(batches)
alerts = [a for o in sum((b.orders for b in batches), []) for a in o.alerts]
check('No half batch alert for 4.4 MSU batches', len(alerts) == 0)

# ============================================================
# SUMMARY
# ============================================================
print(f'\n{"="*50}')
print(f'Results: {passed} passed, {failed} failed out of {passed+failed} checks')
if failed == 0:
    print('ALL TESTS PASSED!')
else:
    print('SOME TESTS FAILED!')
print(f'{"="*50}')
