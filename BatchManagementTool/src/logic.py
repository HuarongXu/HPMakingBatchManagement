"""
logic.py

存放所有核心业务逻辑和算法。
包括班次计算、MSU计算、搅拌系统分配、搭批算法、冲突检测等。
"""
import copy
import math
import re

import pandas as pd
from collections import defaultdict
from datetime import datetime, time
from itertools import count
from typing import Dict, List, Tuple, Optional

from models import ProductionOrder, MakingSystem, Batch

BATCH_TOLERANCE = 0.05
MAX_BATCH_MULTIPLIER = 3
# Shift-based batching window: number of forward shifts allowed
SHAMPOO_MAX_SHIFTS = 1       # shampoo: current + 1 next shift (e.g. 20D+20M), same day only
CONDITIONER_MAX_SHIFTS = 2   # tube conditioner (D/E/K): current + 2 next shifts (e.g. 20D+20M+21N), can cross day

SMALL_ORDER_THRESHOLD = 3.0

# Cross-line pairing rules (pairwise allowed combinations)
# Shampoo: C can pair with K, R, F; F can pair with R (but K/R, K/F cannot pair)
ALLOWED_SHAMPOO_PAIRS = {
    frozenset({'HPHCPACK', 'HPHKPACK'}),
    frozenset({'HPHCPACK', 'HPHRPACK'}),
    frozenset({'HPHCPACK', 'HPHFPACK'}),
    frozenset({'HPHFPACK', 'HPHRPACK'}),
}
# Conditioner: D/E/K can all pair with each other
ALLOWED_CONDITIONER_PAIRS = {
    frozenset({'HPHDPACK', 'HPHEPACK'}),
    frozenset({'HPHDPACK', 'HPHKPACK'}),
    frozenset({'HPHEPACK', 'HPHKPACK'}),
}
# Lines that indicate tube conditioner (3-shift window)
TUBE_CONDITIONER_LINES = {'HPHDPACK', 'HPHEPACK', 'HPHKPACK'}
GSS12_MIN_MOQ = 4.4
GSS12_HALF_MOQ = GSS12_MIN_MOQ / 2
ENABLE_SECOND_PASS_MERGE = True
SECOND_PASS_MAX_MULTIPLIER = 12

MOQ_TOLERANCE_RULES = {
    4.4: {'preferred': 0.12, 'hard': 0.50},
    2.2: {'preferred': 0.08, 'hard': 0.30},
    1.1: {'preferred': 0.05, 'hard': 0.20},
}
MULTI_MOQ_TOLERANCE_STEP = {
    4.4: {'preferred': 0.06, 'hard': 0.20},
    2.2: {'preferred': 0.00, 'hard': 0.00},
    1.1: {'preferred': 0.00, 'hard': 0.00},
}
UNDERFILL_NOTE_MIN_RATIO = 0.90


def _is_plan_order(order: ProductionOrder) -> bool:
    element = str(order.mrp_element or '').strip().lower()
    return element.startswith('pl')


def _is_gss12_system(system: MakingSystem) -> bool:
    name = (system.name or '').lower()
    return 'gss1' in name and 'gss2' in name


def _is_tandem_system(system: MakingSystem) -> bool:
    name = (system.name or '').lower()
    return 'tandem' in name


def _system_allows_target_for_orders(system: MakingSystem, target_size: float, orders: List[ProductionOrder]) -> bool:
    """判断系统是否允许该目标尺寸。
    GSS1+2 可以生产 4.4 及其倍数（任何订单）；
    GSS1+2 生产 2.2 MSU (half-batch) 仅限 WIP Code 在 12t_to_6t list 中的订单。
    """
    if not _is_gss12_system(system):
        return True
    tol = _tolerance_band(GSS12_MIN_MOQ)
    if target_size >= GSS12_MIN_MOQ - tol:
        return True
    # target < 4.4: half-batch, 需要所有订单都在 conversion list 中
    return all(order.allow_gss12_reduced_moq for order in orders)


def _all_systems_need_multi_batch(order: ProductionOrder, target_size: float, systems: List[MakingSystem]) -> bool:
    """判断所有可用系统是否都需要多个物理批次来完成该目标。
    如果是，说明该目标不是一个单次生产的 MOQ，应拆分为更小的逻辑段。"""
    category = (order.product_category or '').lower()
    for system in systems:
        if category and category not in system.product_suitability:
            continue
        if not _system_supports_target(system, target_size):
            continue
        if _calculate_physical_batches(system, target_size) <= 1:
            return False  # 至少一个系统可以单次完成
    return True  # 所有系统都需要多次


def _calculate_shift(start_time: time) -> str:
    """根据开始时间计算班次 (N/D/M)"""
    if time(8, 0) <= start_time < time(16, 0):
        return 'D'  # D班: 08:00 - 15:59
    if start_time >= time(16, 0):
        return 'M'  # M班: 16:00 - 23:59
    return 'N'  # N班: 00:00 - 07:59

def _parse_dates_flexible(date_str: pd.Series) -> pd.Series:
    """Try multiple date formats and return the first that works per value."""
    formats = [
        '%m/%d/%Y',   # 5/11/2026   (US)
        '%d/%m/%Y',   # 11/05/2026  (EU)
        '%Y/%m/%d',   # 2026/05/11
        '%Y-%m-%d',   # 2026-05-11  (ISO)
        '%d-%m-%Y',   # 11-05-2026
        '%m-%d-%Y',   # 05-11-2026
        '%Y.%m.%d',   # 2026.05.11
        '%d.%m.%Y',   # 11.05.2026
        '%m.%d.%Y',   # 05.11.2026
    ]
    result = pd.to_datetime(date_str, errors='coerce')  # pandas auto-detect
    if result.notna().all():
        return result
    # If auto-detect has gaps, try explicit formats
    for fmt in formats:
        parsed = pd.to_datetime(date_str, format=fmt, errors='coerce')
        if parsed.notna().sum() > result.notna().sum():
            result = parsed
        if result.notna().all():
            break
    return result


def _combine_date_time_columns(date_series: pd.Series, time_series: pd.Series) -> pd.Series:
    """合并日期和时间列，支持 24:00:00 跨日写法，自动识别多种日期格式。"""
    date_str = date_series.astype(str).str.strip()
    time_str = time_series.astype(str).str.strip()

    mask_24 = time_str.str.startswith('24:', na=False)
    normalized_dates = _parse_dates_flexible(date_str)
    normalized_time = time_str.copy()
    if mask_24.any():
        normalized_time.loc[mask_24] = (
            time_str.loc[mask_24]
            .str.replace('24:', '00:', n=1)
        )
        normalized_dates.loc[mask_24] = normalized_dates.loc[mask_24] + pd.Timedelta(days=1)

    time_delta = pd.to_timedelta(normalized_time, errors='coerce')
    return normalized_dates + time_delta


# Shift ordering for distance calculation
_SHIFT_INDEX = {'N': 0, 'D': 1, 'M': 2}


def _shift_distance(primary_shift: str, primary_date, candidate_shift: str, candidate_date) -> int:
    """Calculate how many shifts forward candidate is from primary.
    Same shift same day = 0, next shift same day = 1, etc."""
    days_diff = (candidate_date - primary_date).days
    p_idx = _SHIFT_INDEX.get(primary_shift, 0)
    c_idx = _SHIFT_INDEX.get(candidate_shift, 0) + days_diff * 3
    return c_idx - p_idx


def _get_max_shift_window(order: Optional[ProductionOrder]) -> int:
    """根据产品类型返回搭批窗口（班次数）。"""
    if not order:
        return SHAMPOO_MAX_SHIFTS
    category = (order.product_category or '').lower()
    work_center = (order.work_center or '').strip().upper()
    if category == 'conditioner' and work_center in TUBE_CONDITIONER_LINES:
        return CONDITIONER_MAX_SHIFTS
    return SHAMPOO_MAX_SHIFTS


def _within_batch_window(primary: ProductionOrder, candidate: ProductionOrder, allow_cross_day: bool) -> bool:
    """判断候选订单是否落在主订单的搭批窗口内（基于班次距离）。"""
    if candidate.start_datetime < primary.start_datetime:
        return False

    category = (primary.product_category or '').lower()
    work_center = (primary.work_center or '').strip().upper()
    is_tube_cond = (category == 'conditioner' and work_center in TUBE_CONDITIONER_LINES)

    # Cross-day rule: shampoo never crosses day; tube conditioner can
    if not is_tube_cond:
        if candidate.start_datetime.date() != primary.start_datetime.date():
            return False
    else:
        if not allow_cross_day and candidate.start_datetime.date() != primary.start_datetime.date():
            return False

    max_shifts = _get_max_shift_window(primary)
    dist = _shift_distance(
        primary.shift or 'N', primary.start_datetime.date(),
        candidate.shift or 'N', candidate.start_datetime.date(),
    )
    return 0 <= dist <= max_shifts


def _tolerance_band(value: float) -> float:
    """返回优选容差（软约束），用于优先级判断和贴近目标。"""
    base_key, multiplier = _resolve_tolerance_rule_key(value)
    base = MOQ_TOLERANCE_RULES[base_key]['preferred']
    step = MULTI_MOQ_TOLERANCE_STEP[base_key]['preferred']
    return base + max(0, multiplier - 1) * step


def _hard_tolerance_band(value: float) -> float:
    """返回硬边界容差（硬约束），用于可行性过滤。"""
    base_key, multiplier = _resolve_tolerance_rule_key(value)
    base = MOQ_TOLERANCE_RULES[base_key]['hard']
    step = MULTI_MOQ_TOLERANCE_STEP[base_key]['hard']
    return base + max(0, multiplier - 1) * step


def _resolve_tolerance_rule_key(value: float) -> Tuple[float, int]:
    if value >= 4.4:
        multiplier = max(1, int(math.ceil((value / 4.4) - 1e-9)))
        return 4.4, multiplier
    if value >= 2.2:
        return 2.2, 1
    return 1.1, 1


def _within_tolerance(value: float, target: float) -> bool:
    tol = _tolerance_band(target)
    return target - tol <= value <= target + tol


def _within_hard_tolerance(value: float, target: float) -> bool:
    tol = _hard_tolerance_band(target)
    return target - tol <= value <= target + tol


def _resolve_base_size(system: MakingSystem, target_size: float) -> float:
    if not system.supported_msu:
        return target_size
    sizes = list(system.supported_msu)
    if _is_gss12_system(system):
        sizes = list({*sizes, round(GSS12_MIN_MOQ / 2, 4)})
    sizes = sorted(sizes)
    tol = _tolerance_band(target_size)
    candidates = [size for size in sizes if size <= target_size + tol]
    if candidates:
        return max(candidates)
    return sizes[0]


def _calculate_physical_batches(system: MakingSystem, target_size: float) -> int:
    base_size = _resolve_base_size(system, target_size)
    if base_size <= 0:
        return 1
    ratio = target_size / base_size
    count = max(1, int(math.ceil(ratio - 1e-9)))
    return count


def _normalize_product_type(raw_value) -> Optional[str]:
    """将Parameter中的产品描述规范化为shampoo/conditioner。"""
    if raw_value is None or (isinstance(raw_value, float) and pd.isna(raw_value)):
        return None
    text = str(raw_value).strip().lower()
    if not text:
        return None

    # 常见关键字匹配
    if 'shamp' in text or 'shmp' in text:
        return 'shampoo'
    if 'cond' in text or 'cdr' in text:
        return 'conditioner'

    synonyms = {
        'shampoo': 'shampoo',
        'po shampoo': 'shampoo',
        'clear shampoo': 'shampoo',
        'non ad shampoo': 'shampoo',
        'conditioner': 'conditioner',
        'cond': 'conditioner',
        'treatment': 'conditioner',
    }
    return synonyms.get(text, None)


def _infer_category_from_name(name: str) -> Optional[List[str]]:
    lower_name = name.lower()
    categories: List[str] = []
    if 'cond' in lower_name and 'shamp' not in lower_name:
        categories.append('conditioner')
    elif 'shamp' in lower_name and 'cond' not in lower_name:
        categories.append('shampoo')
    return categories or None


def preprocess_and_create_orders(data: Dict[str, pd.DataFrame]) -> List[ProductionOrder]:
    """
    预处理数据，并将ZCPRS数据转换为ProductionOrder对象列表。
    1. 关联ZCPRS和Parameter表。
    2. 计算班次。
    3. 计算MSU需求。
    """
    zcprs_df = data['zcprs'].copy()
    parameter_df = data['parameter'].copy()
    conversion_codes: set[str] = set()
    conversion_df = data.get('conversion')
    if conversion_df is not None and not conversion_df.empty:
        wip_column = None
        for column in conversion_df.columns:
            if 'wip' in str(column).lower():
                wip_column = column
                break
        if wip_column is None and len(conversion_df.columns) > 0:
            wip_column = conversion_df.columns[0]
        if wip_column:
            codes = (
                conversion_df[wip_column]
                .dropna()
                .astype(str)
                .str.strip()
            )
            conversion_codes = {code for code in codes if code}

    # 移除以 6 开头的订单号
    order_numbers = zcprs_df['Order Number'].astype(str).str.strip()
    mask_drop = order_numbers.str.startswith('6', na=False)
    dropped_count = mask_drop.sum()
    if dropped_count:
        print(f"ZCPRS 过滤: 已移除 {dropped_count} 条以 6 开头的订单记录。")
        zcprs_df = zcprs_df.loc[~mask_drop].reset_index(drop=True)

    # 1. 数据清洗和转换
    # 将 'Material' 列的数据类型统一为字符串（去掉 .0 结尾），以便合并
    normalize_material = (
        lambda series: series.astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )
    zcprs_df['Material'] = normalize_material(zcprs_df['Material'])
    parameter_df['Material'] = normalize_material(parameter_df['Material'])
    
    # 将日期和时间合并为datetime对象
    zcprs_df['start_datetime'] = _combine_date_time_columns(zcprs_df['StartDate'], zcprs_df['StartTime'])
    zcprs_df['end_datetime'] = _combine_date_time_columns(zcprs_df['EndDate'], zcprs_df['EndTime'])

    # 2. 合并数据以获取SUF和其他参数
    # 使用左连接，保留所有生产计划，即使在参数表中没有找到匹配项
    merged_df = pd.merge(zcprs_df, parameter_df, on='Material', how='left')

    merged_df['SUF'] = pd.to_numeric(merged_df['SUF'], errors='coerce')

    orders = []
    for _, row in merged_df.iterrows():
        planned_qty = pd.to_numeric(row['Planned Quantity'], errors='coerce')
        planned_qty = float(planned_qty) if pd.notna(planned_qty) else 0.0
        raw_uom = str(row['UoM']).strip() if pd.notna(row['UoM']) else ''
        suf_value = row['SUF'] if pd.notna(row['SUF']) and row['SUF'] else None
        description_cell = row.get('Description')
        description_value = None
        if pd.notna(description_cell):
            description_value = str(description_cell).strip()
            if not description_value:
                description_value = None

        raw_wip = row.get('Matl-Comp')
        wip_code = None
        if pd.notna(raw_wip):
            candidate = str(raw_wip).strip()
            if candidate:
                wip_code = candidate
        allow_half_moq = bool(wip_code and wip_code in conversion_codes)

        raw_segment = row.get('Seg')
        segment_value = None
        if pd.notna(raw_segment):
            candidate = str(raw_segment).strip()
            if candidate:
                segment_value = candidate

        order = ProductionOrder(
            order_number=row['Order Number'],
            material=row['Material'],
            work_center=row['Work Center'],
            planned_quantity=planned_qty,
            uom=raw_uom,
            start_datetime=row['start_datetime'],
            end_datetime=row['end_datetime'],
            mrp_element=row['Mrp Element'],
            material_description=description_value,
            wip_code=wip_code,
            allow_gss12_reduced_moq=allow_half_moq,
            product_type=row.get('Type'), # 从合并后的数据中获取
            segment=segment_value,
        )
        order.original_order_number = order.order_number
        
        # 计算班次（防护 NaT）
        if pd.isna(order.start_datetime):
            order.alerts.append(f"警告: 订单 {order.order_number} 的开始时间无效，已跳过。")
            continue
        order.shift = _calculate_shift(order.start_datetime.time())
        order.product_category = _normalize_product_type(order.product_type)
        
        # 填充MSU需求
        order.msu_demand = planned_qty
        order.suf = suf_value
            
        orders.append(order)
        
    print(f"成功预处理并创建了 {len(orders)} 条生产订单对象。")
    return orders


def _split_orders_for_capacity(
    orders: List[ProductionOrder], systems: Optional[List[MakingSystem]] = None
) -> List[ProductionOrder]:
    splitted: List[ProductionOrder] = []
    for order in orders:
        splitted.extend(_split_single_order(order, systems or []))
    return splitted


def _any_system_supports_order_target(
    order: ProductionOrder,
    target_size: Optional[float],
    systems: List[MakingSystem],
) -> bool:
    if target_size is None or not systems:
        return False
    for system in systems:
        if order.product_category and order.product_category not in system.product_suitability:
            continue
        if not _system_supports_target(system, target_size):
            continue
        if not _system_allows_target_for_orders(system, target_size, [order]):
            continue
        return True
    return False


def _preferred_shampoo_chunks(
    order: ProductionOrder,
    demand: float,
    allowed_sizes: List[float],
    systems: List[MakingSystem],
) -> Optional[List[float]]:
    category = (order.product_category or '').lower()
    if category != 'shampoo' or not systems:
        return None

    preferred_size = 4.4
    preferred_tol = _tolerance_band(preferred_size)
    if demand <= preferred_size + preferred_tol:
        return None

    gss12_capable = [
        system
        for system in systems
        if _is_gss12_system(system)
        and category in system.product_suitability
        and _system_supports_target(system, preferred_size)
    ]
    if not gss12_capable:
        return None

    primary_count = int(math.floor((demand + preferred_tol) / preferred_size))
    if primary_count <= 0:
        return None

    remainder = demand - primary_count * preferred_size
    if remainder <= _tolerance_band(demand):
        return None

    smaller_sizes = [size for size in allowed_sizes if size < preferred_size - 1e-6]
    matched_remainder = None
    for size in smaller_sizes:
        if _within_tolerance(remainder, size):
            matched_remainder = size
            break
    if matched_remainder is None and smaller_sizes:
        matched_remainder = smaller_sizes[0]
    if matched_remainder is None or matched_remainder <= 0:
        return None

    non_gss12 = [
        system
        for system in systems
        if not _is_gss12_system(system)
        and category in system.product_suitability
    ]
    if not non_gss12:
        return None
    if not _any_system_supports_order_target(order, matched_remainder, non_gss12):
        return None

    chunks = [preferred_size] * primary_count
    chunks.append(matched_remainder)
    total = sum(chunks)
    if not _within_hard_tolerance(demand, total):
        return None

    return chunks


def _split_single_order(order: ProductionOrder, systems: List[MakingSystem]) -> List[ProductionOrder]:
    demand = order.msu_demand or 0
    allowed_sizes = _get_allowed_msu_sizes(order.product_category)
    if not allowed_sizes or demand <= 0:
        order.segment_index = 1
        order.segment_total = 1
        return [order]

    max_allowed = max(allowed_sizes)

    single_target = _match_single_chunk(demand, allowed_sizes)
    if single_target is not None:
        if systems:
            preferred_chunks = _preferred_shampoo_chunks(order, demand, allowed_sizes, systems)
            if preferred_chunks:
                chunks = preferred_chunks
            elif _all_systems_need_multi_batch(order, single_target, systems):
                # 目标需要多个物理批次（如 conditioner 6.6 = 3×2.2），应拆分成更小的逻辑段
                chunks = _decompose_msu_into_chunks(demand, allowed_sizes)
            elif _any_system_supports_order_target(order, single_target, systems):
                order.segment_index = 1
                order.segment_total = 1
                return [order]
            else:
                chunks = _decompose_msu_into_chunks(demand, allowed_sizes)
        else:
            order.segment_index = 1
            order.segment_total = 1
            return [order]
    else:
        chunks = _preferred_shampoo_chunks(order, demand, allowed_sizes, systems) or []
        if not chunks:
            chunks = _decompose_msu_into_chunks(demand, allowed_sizes)

    chunk_total = sum(chunks)
    
    # 验证拆分后的总和是否在可接受范围内
    # chunks 量化为 MOQ 步长 (2.2/4.4)，天然会略大于 demand，
    # 因此使用 chunk_total 的 hard tolerance 来验证合理性
    if len(chunks) <= 1 or not _within_hard_tolerance(demand, chunk_total):
        order.segment_index = 1
        order.segment_total = 1
        return [order]

    segments: List[ProductionOrder] = []
    for idx, chunk in enumerate(chunks, start=1):
        new_order = copy.deepcopy(order)
        new_order.order_number = f"{order.original_order_number}-{idx}"
        new_order.msu_demand = chunk
        new_order.planned_quantity = chunk
        new_order.segment_index = idx
        new_order.segment_total = len(chunks)
        new_order.assigned_system = None
        new_order.batch_id = None
        new_order.batch_note = None
        new_order.batch_count = 0
        new_order.alerts = list(order.alerts)
        segments.append(new_order)

    return segments


def _decompose_msu_into_chunks(total: float, allowed_sizes: List[float]) -> List[float]:
    sizes = sorted({round(size, 4) for size in allowed_sizes if size > 0}, reverse=True)
    if not sizes:
        return []

    # 优先拆分表：(目标总量, 拆分方案, 需要存在的尺寸)
    _PREFERRED_SPLITS = [
        (6.6,  [4.4, 2.2],      [4.4, 2.2]),
        (8.8,  [4.4, 4.4],     [4.4]),
        (11.0, [4.4, 4.4, 2.2],[4.4, 2.2]),
        (13.2, [4.4, 4.4, 4.4],[4.4]),
        (3.3,  [2.2, 1.1],     [2.2, 1.1]),
    ]
    for split_target, split_result, required_sizes in _PREFERRED_SPLITS:
        tol = _hard_tolerance_band(split_target)
        if abs(total - split_target) < tol:
            if all(any(math.isclose(s, req, rel_tol=1e-3, abs_tol=1e-3) for s in sizes) for req in required_sizes):
                return split_result

    total_tol = _tolerance_band(total if total > 0 else sizes[-1])
    min_size = min(sizes)

    base_size = next((size for size in sizes if math.isclose(size, 4.4, rel_tol=1e-3, abs_tol=1e-3)), sizes[0])
    base_tol = _tolerance_band(base_size)

    chunks: List[float] = []
    remaining = total

    while remaining >= base_size + base_tol:
        chunks.append(base_size)
        remaining -= base_size

    if remaining >= base_size - base_tol:
        chunks.append(base_size)
        remaining -= base_size

    if remaining <= total_tol:
        return chunks

    small_sizes = [size for size in sizes if size < base_size - 1e-6]
    if not small_sizes:
        chunks.append(base_size)
        return chunks

    combo = _compose_remainder_chunks(remaining, small_sizes)
    if combo:
        if not chunks:
            combo_sum = sum(combo)
            combo_gap = abs(combo_sum - remaining)
            base_gap = abs(base_size - remaining)
            combo_len = len(combo)
            if (combo_gap < base_gap - 1e-6) or (
                math.isclose(combo_gap, base_gap, rel_tol=1e-6, abs_tol=1e-6)
                and combo_len <= 1
            ):
                chunks.extend(combo)
            else:
                chunks.append(base_size)
        else:
            chunks.extend(combo)
    else:
        chunks.append(base_size)

    return chunks


def _match_single_chunk(total: float, allowed_sizes: List[float]) -> Optional[float]:
    for size in allowed_sizes:
        if _within_tolerance(total, size):
            return size
    return None


def _compose_remainder_chunks(target: float, sizes: List[float]) -> Optional[List[float]]:
    if target <= 0:
        return []
    sizes = sorted({round(size, 4) for size in sizes if size > 0}, reverse=True)
    if not sizes:
        return None

    min_size = min(sizes)
    max_size = max(sizes)
    max_chunks = max(1, int(math.ceil((target + max_size) / min_size)) + 1)
    tolerance = _tolerance_band(target if target > 0 else min_size)
    best_combo: Optional[List[float]] = None
    best_key: Optional[Tuple[float, int, float]] = None

    def dfs(start: int, current: List[float], current_sum: float):
        nonlocal best_combo, best_key
        if current:
            gap = abs(current_sum - target)
            key = (round(gap, 6), len(current), -current_sum)
            if best_key is None or key < best_key:
                best_combo = current.copy()
                best_key = key

        if current_sum >= target + tolerance and current:
            return

        if len(current) >= max_chunks:
            return
        for idx in range(start, len(sizes)):
            size = sizes[idx]
            current.append(size)
            dfs(idx, current, current_sum + size)
            current.pop()

    dfs(0, [], 0.0)
    return best_combo

def _parse_making_systems(data: Dict[str, pd.DataFrame]) -> List[MakingSystem]:
    """解析Making Capacity数据，创建MakingSystem对象列表。"""
    capacity_df = data['making_capacity'].copy()
    systems = []

    # 重命名列以匹配模型属性，兼容不同的空格写法
    column_mapping = {
        '机组ID': 'system_id',
        '搅拌机组名称': 'name',
        '支持规格(MSU)': 'supported_msu',
        '支持规格 (MSU)': 'supported_msu',
        '对应容量(吨)': 'capacity_tons',
        '对应容量 (吨)': 'capacity_tons',
        '产品适用性': 'product_suitability',
        'N班批次上限': 'n_shift_limit',
        'D班批次上限': 'd_shift_limit',
        'M班批次上限': 'm_shift_limit',
        '共享/备注逻辑': 'shared_logic',
        'Total': 'total_limit'
    }
    capacity_df.rename(columns=lambda col: column_mapping.get(col.strip(), col.strip()), inplace=True)

    def _parse_numeric_list(value) -> List[float]:
        if pd.isna(value):
            return []
        tokens = re.findall(r"[0-9]+(?:\.[0-9]+)?", str(value))
        return [float(token) for token in tokens]

    for _, row in capacity_df.iterrows():
        # 将文本转换为数字列表，兼容 {4.4} / 4.4 / "4.4,2.2" 等格式
        supported_msu = _parse_numeric_list(row['supported_msu'])
        capacity_tons = _parse_numeric_list(row.get('capacity_tons'))
        raw_suitability = [p.strip() for p in str(row['product_suitability']).replace('{', '').replace('}', '').split(',') if p.strip()]
        product_suitability: List[str] = []
        for entry in raw_suitability:
            entry_lower = entry.lower()
            added = False
            if 'shamp' in entry_lower:
                product_suitability.append('shampoo')
                added = True
            if 'cond' in entry_lower:
                product_suitability.append('conditioner')
                added = True
            if not added:
                normalized = _normalize_product_type(entry)
                if normalized:
                    product_suitability.append(normalized)
                else:
                    product_suitability.append(entry_lower)

        name_override = _infer_category_from_name(row['name'])
        if name_override:
            product_suitability = name_override

        system = MakingSystem(
            system_id=row['system_id'],
            name=row['name'],
            supported_msu=supported_msu,
            capacity_tons=capacity_tons,
            product_suitability=product_suitability,
            n_shift_limit=int(row['n_shift_limit']),
            d_shift_limit=int(row['d_shift_limit']),
            m_shift_limit=int(row['m_shift_limit']),
            shared_logic=row.get('shared_logic'),
            total_limit=pd.to_numeric(row.get('total_limit'), errors='coerce')
        )
        systems.append(system)
    
    print(f"成功解析了 {len(systems)} 个搅拌系统。")
    return systems

def _find_available_systems_for_orders(orders: List[ProductionOrder], systems: List[MakingSystem]):
    """为每个订单找到所有可用的搅拌系统。"""
    for order in orders:
        normalized_type = order.product_category or _normalize_product_type(order.product_type)
        if not normalized_type:
            order.alerts.append("警告: 订单缺少有效产品类型，无法匹配搅拌系统。")
            continue
        order.product_category = normalized_type
        
        for system in systems:
            if normalized_type in system.product_suitability:
                if order.available_systems is None:
                    order.available_systems = []
                order.available_systems.append(system)
        
        if not order.available_systems:
            raw_desc = order.product_type or "未提供"
            order.alerts.append(f"警告: 未找到适用于产品类型 '{raw_desc}' 的搅拌系统。")


class BatchCapacityTracker:
    """用于跟踪每台搅拌系统在各班次的批次占用情况。"""

    def __init__(self, systems: List[MakingSystem]):
        self.shift_usage: Dict[str, Dict[str, Dict[str, int]]] = {
            system.system_id: {}
            for system in systems
        }
        self.total_usage = {system.system_id: 0 for system in systems}
        self.shift_limits = {
            system.system_id: {
                'N': system.n_shift_limit,
                'D': system.d_shift_limit,
                'M': system.m_shift_limit,
            }
            for system in systems
        }
        self.system_names = {system.system_id: system.name for system in systems}

    @staticmethod
    def _resolve_shift_limit(system: MakingSystem, shift: str) -> int:
        if shift == 'N':
            return system.n_shift_limit
        if shift == 'D':
            return system.d_shift_limit
        return system.m_shift_limit

    def can_allocate(self, system: MakingSystem, shift: str) -> bool:
        return True

    @staticmethod
    def _normalize_date_key(usage_date: Optional[str]) -> str:
        if usage_date is None:
            return ''
        return str(usage_date)

    def _ensure_date_usage(self, system_id: str, usage_date: str) -> Dict[str, int]:
        system_usage = self.shift_usage.setdefault(system_id, {})
        if usage_date not in system_usage:
            system_usage[usage_date] = {'N': 0, 'D': 0, 'M': 0}
        return system_usage[usage_date]

    def record_allocation(self, system: MakingSystem, usage_date: str, shift: str, batches: int) -> None:
        date_key = self._normalize_date_key(usage_date)
        usage = self._ensure_date_usage(system.system_id, date_key)
        usage[shift] += batches
        self.total_usage[system.system_id] += batches

    def projected_overflow(self, system: MakingSystem, usage_date: str, shift: str, additional_batches: int) -> bool:
        limit = self._resolve_shift_limit(system, shift)
        if not limit:
            return False
        date_key = self._normalize_date_key(usage_date)
        current = self.shift_usage.get(system.system_id, {}).get(date_key, {}).get(shift, 0)
        return current + additional_batches > limit

    def get_shift_usage(self, system: MakingSystem, usage_date: str, shift: str) -> int:
        date_key = self._normalize_date_key(usage_date)
        return self.shift_usage.get(system.system_id, {}).get(date_key, {}).get(shift, 0)

    def get_shift_limit(self, system: MakingSystem, shift: str) -> Optional[int]:
        return self.shift_limits.get(system.system_id, {}).get(shift)

    def rebuild_usage(self, batches: List[Batch]) -> None:
        for system_id in self.shift_usage:
            self.shift_usage[system_id] = {}
        for system_id in self.total_usage:
            self.total_usage[system_id] = 0
        for batch in batches:
            system = batch.assigned_system
            if not system:
                continue
            allocations = self._extract_batch_allocations(batch)
            for usage_date, shift, count in allocations:
                if count <= 0:
                    continue
                self.record_allocation(system, usage_date, shift, count)

    def _extract_batch_allocations(self, batch: Batch) -> List[Tuple[str, str, int]]:
        explicit: Dict[Tuple[str, str], float] = defaultdict(float)
        for order in batch.orders:
            count_value = float(order.batch_count or 0.0)
            if count_value <= 0:
                continue
            shift = order.shift or batch.shift or 'N'
            usage_date = order.start_datetime.date().isoformat() if order.start_datetime else (batch.date or '')
            explicit[(usage_date, shift)] += count_value

        if explicit:
            allocations: List[Tuple[str, str, int]] = []
            for (usage_date, shift), count in explicit.items():
                allocations.append((usage_date, shift, int(math.ceil(count - 1e-9))))
            return allocations

        if not batch.shift or not batch.date:
            return []
        count = batch.physical_batches or 0
        if count <= 0:
            count = 1
        return [(batch.date, batch.shift, int(count))]

    def get_shift_overflow(self) -> List[Tuple[str, str, str, int]]:
        entries: List[Tuple[str, str, str, int]] = []
        for system_id, date_usage in self.shift_usage.items():
            for usage_date, usage in date_usage.items():
                for shift, count in usage.items():
                    limit = self.shift_limits.get(system_id, {}).get(shift)
                    if limit and count > limit:
                        entries.append((system_id, usage_date, shift, count - limit))
        return entries

    def summarize(self) -> List[str]:
        summary: List[str] = []
        for system_id, date_usage in self.shift_usage.items():
            limits = self.shift_limits.get(system_id, {})
            for usage_date, usage in date_usage.items():
                for shift, count_value in usage.items():
                    limit = limits.get(shift)
                    if limit and count_value > limit:
                        name = self.system_names.get(system_id, system_id)
                        summary.append(
                            f"{usage_date} {shift}班 {name} 计划 {count_value} 批, 超出最大批次 {limit}."
                        )
        return summary


def _group_orders_by_wip(orders: List[ProductionOrder]):
    groups = defaultdict(list)
    for order in orders:
        if not order.wip_code or pd.isna(order.wip_code):
            order.alerts.append("警告: 订单缺少 WIP Code，无法参与搭批。")
            continue
        if not order.shift:
            order.alerts.append("警告: 订单缺少班次信息，无法参与搭批。")
            continue

        groups[order.wip_code].append(order)

    for key in groups:
        groups[key].sort(key=lambda o: o.start_datetime)

    return groups


def _combination_respects_work_center(orders: List[ProductionOrder]) -> bool:
    if not orders:
        return True
    centers = {(order.work_center or '').strip() for order in orders}
    if '' in centers:
        if len(centers) > 1:
            return False
    if len(centers) <= 1:
        return True

    # Pairwise check: every pair of distinct centers must be an allowed pair
    is_conditioner = all((order.product_category or '').lower() == 'conditioner' for order in orders)
    is_shampoo = all((order.product_category or '').lower() == 'shampoo' for order in orders)

    if is_conditioner:
        allowed_pairs = ALLOWED_CONDITIONER_PAIRS
    elif is_shampoo:
        allowed_pairs = ALLOWED_SHAMPOO_PAIRS
    else:
        return False

    center_list = list(centers)
    for i in range(len(center_list)):
        for j in range(i + 1, len(center_list)):
            pair = frozenset({center_list[i], center_list[j]})
            if pair not in allowed_pairs:
                return False
    return True


def _build_batch_candidates(order: ProductionOrder):
    candidates = []
    if not order.available_systems:
        return candidates

    for system in order.available_systems:
        supported_sizes = sorted(system.supported_msu)
        if not supported_sizes:
            continue

        msu_target = None
        for size in supported_sizes:
            if order.msu_demand is not None and not pd.isna(order.msu_demand) and order.msu_demand <= size:
                msu_target = size
                break

        if msu_target is None:
            msu_target = supported_sizes[-1]

        candidates.append((msu_target, system))

    candidates.sort(key=lambda item: (item[0], item[1].name))
    return candidates


def _refresh_batch_notes(batch: Batch):
    if not batch.orders:
        return

    is_half_batch = False
    if batch.assigned_system and ('GSS1' in batch.assigned_system.name or 'GSS2' in batch.assigned_system.name):
        if batch.msu_size and abs(batch.msu_size - 2.2) < 0.01:
            is_half_batch = any(order.allow_gss12_reduced_moq for order in batch.orders)

    # 计算 batch_count：始终使用 physical_batches（整数），保证批次数为整数
    batch_equivalent = float(batch.physical_batches)

    if len(batch.orders) == 1:
        single_order = batch.orders[0]
        note = None
        if is_half_batch:
            note = "half batch"
        else:
            load = batch.current_load or 0.0
            target = batch.msu_size or 0.0
            if target > 0:
                # 仅对“明显低于一个完整 MOQ”的单独开批加备注，避免接近 MOQ 的正常波动造成噪音
                # 例如 3.821/4.4 需要提示；2.076/2.2、4.247/4.4 这类接近 MOQ 的不提示
                underfill_ratio = load / target if target else 1.0
                if batch.physical_batches <= 1 and underfill_ratio < UNDERFILL_NOTE_MIN_RATIO:
                    note = f"未找到可搭批订单，单独开批（Load {load:.3f} / Target {target:.1f}）"
        single_order.batch_note = note
        single_order.batch_count = batch_equivalent
        return

    order_numbers = batch.get_order_numbers()
    note = "搭批：" + " + ".join(order_numbers)
    
    if is_half_batch:
        note = "half batch | " + note if note else "half batch"
    
    for order in batch.orders:
        order.batch_note = note

    buckets = []
    seen = set()
    for order in sorted(batch.orders, key=lambda o: o.start_datetime):
        usage_date = order.start_datetime.date().isoformat() if order.start_datetime else (batch.date or '')
        shift = order.shift or 'N'
        key = (usage_date, shift)
        if key not in seen:
            buckets.append(key)
            seen.add(key)

    shift_allocations: Dict[Tuple[str, str], float] = {}
    if buckets:
        base = batch.physical_batches // len(buckets)
        remainder = batch.physical_batches % len(buckets)
        for idx, key in enumerate(buckets):
            shift_allocations[key] = float(base)
            if idx < remainder:
                shift_allocations[key] += 1.0

    assigned_first: Dict[Tuple[str, str], bool] = {}
    for order in batch.orders:
        usage_date = order.start_datetime.date().isoformat() if order.start_datetime else (batch.date or '')
        shift = order.shift or 'N'
        key = (usage_date, shift)
        if key not in shift_allocations:
            order.batch_count = 0.0
            continue
        if not assigned_first.get(key):
            order.batch_count = shift_allocations[key]
            assigned_first[key] = True
        else:
            order.batch_count = 0.0


def _build_second_pass_targets(total_load: float, category: Optional[str], floor_target: float) -> List[float]:
    if total_load <= 0:
        return []
    base_size = 2.2
    multiplier_floor = max(1, int(math.floor((floor_target / base_size) - 1e-9)))
    multiplier_need = max(1, int(math.ceil((total_load / base_size) - 1e-9)))
    max_multiplier = max(SECOND_PASS_MAX_MULTIPLIER, multiplier_need + 2, multiplier_floor + 1)
    targets = [round(base_size * multiplier, 4) for multiplier in range(multiplier_floor, max_multiplier + 1)]
    if (category or '').lower() == 'conditioner':
        targets.append(1.1)
    targets = sorted({target for target in targets if target > 0})
    return targets


def _choose_second_pass_target(
    total_load: float,
    category: Optional[str],
    floor_target: float,
    system: MakingSystem,
) -> Optional[float]:
    candidates = _build_second_pass_targets(total_load, category, floor_target)
    feasible: List[float] = []
    for target in candidates:
        if target + 1e-9 < floor_target:
            continue
        if not _within_hard_tolerance(total_load, target):
            continue
        if not _system_supports_target(system, target):
            continue
        feasible.append(target)
    if not feasible:
        return None
    return min(feasible, key=lambda target: (abs(target - total_load), target))


def _is_underfill_single_batch(batch: Batch) -> bool:
    if len(batch.orders) != 1:
        return False
    target = batch.msu_size or 0.0
    load = batch.current_load or 0.0
    if target <= 0:
        return False
    return (load / target) < UNDERFILL_NOTE_MIN_RATIO


def _capture_overflow_map(tracker: BatchCapacityTracker) -> Dict[Tuple[str, str, str], int]:
    result: Dict[Tuple[str, str, str], int] = {}
    for system_id, usage_date, shift, excess in tracker.get_shift_overflow():
        result[(system_id, usage_date, shift)] = excess
    return result


def _overflow_not_worse(before: Dict[Tuple[str, str, str], int], after: Dict[Tuple[str, str, str], int]) -> bool:
    for key, excess_after in after.items():
        excess_before = before.get(key, 0)
        if excess_after > excess_before:
            return False
    return True


def _second_pass_merge_batches(
    batches: List[Batch],
    tracker: BatchCapacityTracker,
) -> None:
    if not ENABLE_SECOND_PASS_MERGE or not batches:
        return

    tracker.rebuild_usage(batches)

    while True:
        before_overflow = _capture_overflow_map(tracker)
        best_choice = None
        best_score = None

        for left_idx in range(len(batches)):
            left = batches[left_idx]
            if not left.assigned_system or not left.orders:
                continue
            left_category = (left.orders[0].product_category or '').lower()
            for right_idx in range(left_idx + 1, len(batches)):
                right = batches[right_idx]
                if not right.assigned_system or not right.orders:
                    continue
                if left.assigned_system.system_id != right.assigned_system.system_id:
                    continue
                if str(left.wip_code) != str(right.wip_code):
                    continue
                right_category = (right.orders[0].product_category or '').lower()
                if left_category != right_category:
                    continue

                merged_orders = sorted(left.orders + right.orders, key=lambda order: order.start_datetime)
                if not _combination_respects_work_center(merged_orders):
                    continue

                # 检查搭批时间窗口约束（shampoo 16h / conditioner 24h）
                earliest = merged_orders[0]
                latest = merged_orders[-1]
                if not _within_batch_window(earliest, latest, allow_cross_day=True):
                    continue

                merged_load = sum(order.msu_demand or 0.0 for order in merged_orders)
                floor_target = max(left.msu_size or 0.0, right.msu_size or 0.0)
                target_size = _choose_second_pass_target(
                    total_load=merged_load,
                    category=left_category,
                    floor_target=floor_target,
                    system=left.assigned_system,
                )
                if target_size is None:
                    continue

                merged_physical = _calculate_physical_batches(left.assigned_system, target_size)
                # 只有满足以下条件之一才值得合并：
                # 1) 至少一方存在 underfill（原有逻辑）
                # 2) 合并后可减少物理批次数（如两个 1.1 → 一个 2.2）
                reduces_batches = merged_physical < (left.physical_batches + right.physical_batches)
                has_underfill = _is_underfill_single_batch(left) or _is_underfill_single_batch(right)
                if not (reduces_batches or has_underfill):
                    continue
                merged_batch = Batch(
                    batch_id=left.batch_id,
                    wip_code=left.wip_code,
                    msu_size=target_size,
                    assigned_system=left.assigned_system,
                    shift=merged_orders[0].shift or left.shift,
                    date=merged_orders[0].start_datetime.date().isoformat() if merged_orders[0].start_datetime else left.date,
                    orders=merged_orders,
                    current_load=merged_load,
                    physical_batches=merged_physical,
                )
                _refresh_batch_notes(merged_batch)

                trial_batches = batches.copy()
                trial_batches[left_idx] = merged_batch
                trial_batches.pop(right_idx)
                tracker.rebuild_usage(trial_batches)
                after_overflow = _capture_overflow_map(tracker)
                if not _overflow_not_worse(before_overflow, after_overflow):
                    tracker.rebuild_usage(batches)
                    continue

                score = (
                    0 if merged_physical < (left.physical_batches + right.physical_batches) else 1,
                    0 if (_is_underfill_single_batch(left) ^ _is_underfill_single_batch(right)) else 1,
                    abs(target_size - merged_load),
                    target_size,
                    left_idx,
                    right_idx,
                )
                if best_score is None or score < best_score:
                    best_score = score
                    best_choice = (left_idx, right_idx, merged_batch, right.batch_id)

                tracker.rebuild_usage(batches)

        if not best_choice:
            break

        left_idx, right_idx, merged_batch, removed_batch_id = best_choice
        batches[left_idx] = merged_batch
        batches.pop(right_idx)

        for order in merged_batch.orders:
            order.assigned_system = merged_batch.assigned_system
            order.batch_id = merged_batch.batch_id
            order.alerts.append(
                f"二次合并: {merged_batch.batch_id} 与 {removed_batch_id} 合并，目标批量调整为 {merged_batch.msu_size:.1f} MSU。"
            )

        tracker.rebuild_usage(batches)

def _get_allowed_msu_sizes(category: Optional[str]) -> List[float]:
    cat = (category or 'shampoo').lower()
    sizes: set[float] = set()

    def _add_multiple(base: float, multiplier: int):
        sizes.add(round(base * multiplier, 4))

    max_multiplier = 6
    if cat == 'conditioner':
        # Conditioner 系统支持 2.2 和 1.1 两种规格，
        # 允许的目标批量应包含所有 1.1 的倍数（如 3.3=2.2+1.1, 5.5=4.4+1.1 等）
        max_units = int(round(2.2 * max_multiplier / 1.1))  # 12
        for mult in range(max_units, 0, -1):
            _add_multiple(1.1, mult)
        return sorted(sizes, reverse=True)
    else:
        for mult in range(max_multiplier, 0, -1):
            _add_multiple(2.2, mult)

    # For shampoo: prioritize 4.4-multiples (compatible with GSS1+2) before
    # GSS3-only sizes (odd multiples of 2.2 like 6.6, 11.0).
    # This ensures the planning algorithm first tries targets that can run on
    # either GSS1+2 or GSS3, maximizing system utilization balance.
    gss12_compatible = sorted([s for s in sizes if abs(round(s / 4.4) * 4.4 - s) < 0.01], reverse=True)
    gss3_only = sorted([s for s in sizes if s not in gss12_compatible], reverse=True)
    return gss12_compatible + gss3_only


def _is_sibling_segment(a: ProductionOrder, b: ProductionOrder) -> bool:
    """判断两个订单是否来自同一原始订单的拆分段，拆分段不应被重新搭批到同一批次。"""
    if a.segment_total <= 1 or b.segment_total <= 1:
        return False
    orig_a = a.original_order_number or a.order_number
    orig_b = b.original_order_number or b.order_number
    return orig_a == orig_b


def _order_fits_standard_moq(order: ProductionOrder) -> bool:
    """判断订单的MSU需求是否已匹配标准MOQ（无需搭批即可独立成批）。"""
    demand = order.msu_demand or 0
    if demand <= 0:
        return False
    allowed = _get_allowed_msu_sizes(order.product_category)
    return _match_single_chunk(demand, allowed) is not None


def _build_combo_for_target(primary: ProductionOrder, pool: List[ProductionOrder], target_size: float):
    if primary.msu_demand is None or primary.msu_demand <= 0:
        return None
    load = primary.msu_demand
    hard_tolerance = _hard_tolerance_band(target_size)
    if load > target_size + hard_tolerance:
        return None

    combo = [primary]
    if load >= target_size - hard_tolerance:
        return combo if _combination_respects_work_center(combo) else None

    candidates = [order for order in pool
                  if order.product_category == primary.product_category
                  and order.msu_demand and order.msu_demand > 0
                  and not _is_sibling_segment(primary, order)]
    candidates.sort(key=lambda o: o.msu_demand, reverse=True)

    for order in candidates:
        if order in combo:
            continue
        prospective = combo + [order]
        if not _combination_respects_work_center(prospective):
            continue
        demand = order.msu_demand
        if load + demand <= target_size + hard_tolerance:
            combo.append(order)
            load += demand
            if load >= target_size - hard_tolerance:
                return combo

    return None


def _choose_target_size_for_single(order: ProductionOrder, allowed_sizes: List[float]) -> float:
    demand = order.msu_demand or 0
    for size in sorted(allowed_sizes):
        tol = _hard_tolerance_band(size)
        if demand <= size + tol:
            return size
    return max(demand, allowed_sizes[0])


def _plan_batches_for_group(
    group_orders: List[ProductionOrder], allow_cross_day: bool
) -> Tuple[List[Dict], List[ProductionOrder]]:
    remaining = [order for order in group_orders if order.msu_demand and order.msu_demand > 0]
    remaining.sort(key=lambda o: o.start_datetime)
    planned = []
    deferred: List[ProductionOrder] = []

    # 首先尝试将小订单组合成标准批次
    # 优先配对 4.4 MSU 批次
    small_orders = [
        order for order in remaining
        if order.msu_demand and order.msu_demand <= SMALL_ORDER_THRESHOLD
    ]
    
    used_order_numbers = set()
    
    # 多轮优先配对策略：只使用系统实际支持的标准 MOQ 尺寸
    # 不能使用 6.6、3.3 等非标准尺寸，必须是系统能生产的尺寸
    STANDARD_SIZES = [4.4, 2.2]  # 只允许这两个标准尺寸
    
    for target_size in STANDARD_SIZES:
        small_orders = [
            order for order in remaining
            if order.msu_demand and order.msu_demand <= SMALL_ORDER_THRESHOLD
            and order.order_number not in used_order_numbers
        ]
        small_orders.sort(key=lambda o: o.start_datetime)

        for primary in small_orders:
            if primary.order_number in used_order_numbers:
                continue
            pool = [
                o for o in small_orders
                if o.order_number not in used_order_numbers
                and o is not primary
                and _within_batch_window(primary, o, allow_cross_day)
                and not _is_sibling_segment(primary, o)
            ]
            combo = _build_combo_for_target(primary, pool, target_size)
            if combo and len(combo) > 1:
                planned.append({
                    'orders': combo,
                    'target_size': target_size
                })
                for o in combo:
                    used_order_numbers.add(o.order_number)
                    if o in remaining:
                        remaining.remove(o)
    
    while remaining:
        primary = remaining.pop(0)
        allowed_sizes = _get_allowed_msu_sizes(primary.product_category)

        # ---- 快速路径：订单已匹配标准 MOQ，直接计划，无需搭批 ----
        primary_demand = primary.msu_demand or 0
        single_moq = _match_single_chunk(primary_demand, allowed_sizes)
        if single_moq is not None:
            planned.append({'orders': [primary], 'target_size': single_moq})
            continue

        plan_orders = None
        plan_target = None
        # 允许所有时间窗口内的订单参与搭批候选（包括已匹配 MOQ 的订单），
        # 以便凑出更高效的整批次目标（如 13.2 = 4.4×3）
        window_pool = [
            order for order in remaining
            if _within_batch_window(primary, order, allow_cross_day)
        ]

        # 优先尝试大目标搭批（降序），再回退到小目标
        for target in allowed_sizes:
            combo = _build_combo_for_target(primary, window_pool, target)
            if combo:
                if len(combo) == 1:
                    # 单订单命中，尝试增补以更接近目标
                    extras = _augment_single_order_plan(primary, window_pool, target, allow_cross_day)
                    combo.extend(extras)
                plan_orders = combo
                plan_target = target
                break

        if plan_orders is None:
            if allow_cross_day:
                plan_orders = [primary]
                plan_target = _choose_target_size_for_single(primary, allowed_sizes)
            else:
                deferred.append(primary)
                continue
        elif (
            not allow_cross_day
            and len(plan_orders) == 1
            and plan_orders[0] is primary
        ):
            deferred.append(primary)
            continue
        else:
            for extra in plan_orders:
                if extra is primary:
                    continue
                if extra in remaining:
                    remaining.remove(extra)

        planned.append({
            'orders': plan_orders,
            'target_size': plan_target
        })

    return planned, deferred


def _augment_single_order_plan(
    primary: ProductionOrder,
    window_pool: List[ProductionOrder],
    target_size: float,
    allow_cross_day: bool,
) -> List[ProductionOrder]:
    if not window_pool:
        return []

    hard_tol = _hard_tolerance_band(target_size)
    preferred_tol = _tolerance_band(target_size)
    current_load = primary.msu_demand or 0.0
    gap = abs(target_size - current_load)
    extras: List[ProductionOrder] = []

    candidates = sorted(window_pool, key=lambda o: o.msu_demand or 0, reverse=True)
    for candidate in candidates:
        if candidate is primary or candidate in extras:
            continue
        if _is_sibling_segment(primary, candidate):
            continue
        if candidate.product_category != primary.product_category:
            continue
        if not allow_cross_day and candidate.start_datetime.date() != primary.start_datetime.date():
            continue
        prospective = [primary] + extras + [candidate]
        if not _combination_respects_work_center(prospective):
            continue
        added = candidate.msu_demand or 0.0
        new_load = current_load + added
        if new_load > target_size + hard_tol:
            continue
        new_gap = abs(target_size - new_load)
        if new_gap + 1e-6 < gap or (new_gap <= preferred_tol and gap > preferred_tol):
            extras.append(candidate)
            current_load = new_load
            gap = new_gap

    return extras

def _system_supports_target(system: MakingSystem, target_size: float) -> bool:
    if not system.supported_msu:
        return False
    sizes = list(system.supported_msu)
    is_gss12 = _is_gss12_system(system)
    half_moq = round(GSS12_MIN_MOQ / 2, 4)
    if is_gss12:
        sizes = list({*sizes, half_moq})
    hard_tol = _hard_tolerance_band(target_size)
    for size in sizes:
        if size <= 0:
            continue
        # GSS12 half-MOQ (2.2) is only valid as a single half-batch (multiplier=1).
        # GSS12 tanks are 4.4 MSU; 2.2 cannot be used as a building block for larger targets.
        if is_gss12 and abs(size - half_moq) < 1e-9:
            if _within_tolerance(target_size, size):
                return True
            continue
        max_multiplier = max(MAX_BATCH_MULTIPLIER, int(math.ceil((target_size + hard_tol) / size)) + 1)
        for multiplier in range(1, max_multiplier + 1):
            capacity = size * multiplier
            if _within_tolerance(target_size, capacity):
                return True
    return False


def _system_priority_score(system: Optional[MakingSystem]) -> int:
    if not system or not system.name:
        return 5
    name = system.name.lower()
    if _is_gss12_system(system):
        return 0
    if 'gss3' in name:
        return 1
    return 2


def _system_score_tuple(
    system: MakingSystem,
    target_size: float,
    tracker: BatchCapacityTracker,
    batch_date: str,
    shift: str,
) -> Tuple[int, int, int, int, float, str]:
    physical_batches = _calculate_physical_batches(system, target_size)
    usage = tracker.get_shift_usage(system, batch_date, shift)
    limit = tracker.get_shift_limit(system, shift)
    overflow_flag = 1 if limit and usage + physical_batches > limit else 0
    priority = _system_priority_score(system)

    # 核心原则：先填满大容量系统（GSS1+2 priority=0），再用小容量系统（GSS3 priority=1）。
    # 当系统接近满载时 high_load_flag 触发，将新批次分流到其他系统。
    utilization_ratio = ((usage + physical_batches) / limit) if limit and limit > 0 else 0.0
    high_load_flag = 1 if utilization_ratio >= 0.75 else 0

    closest = float('inf')
    sizes = list(system.supported_msu)
    is_gss12 = _is_gss12_system(system)
    half_moq = round(GSS12_MIN_MOQ / 2, 4)
    if is_gss12:
        sizes = list({*sizes, half_moq})
    for size in sizes:
        if size <= 0:
            continue
        # GSS12 half-MOQ: only multiplier=1 (consistent with _system_supports_target)
        if is_gss12 and abs(size - half_moq) < 1e-9:
            closest = min(closest, abs(size - target_size))
            continue
        max_multiplier = max(MAX_BATCH_MULTIPLIER, int(math.ceil((target_size + _hard_tolerance_band(target_size)) / size)) + 1)
        for multiplier in range(1, max_multiplier + 1):
            capacity = size * multiplier
            closest = min(closest, abs(capacity - target_size))

    return (
        overflow_flag,
        high_load_flag,
        priority,
        usage,
        closest,
        system.name,
    )


def _build_decision_explain(
    order: ProductionOrder,
    target_size: float,
    load_value: float,
    chosen_system: Optional[MakingSystem],
    score_tuple: Optional[Tuple[int, int, int, int, float, str]],
    batch_shift: Optional[str],
    batch_date: Optional[str],
) -> str:
    preferred_tol = _tolerance_band(target_size)
    hard_tol = _hard_tolerance_band(target_size)
    preferred_band = f"[{target_size - preferred_tol:.3f},{target_size + preferred_tol:.3f}]"
    hard_band = f"[{target_size - hard_tol:.3f},{target_size + hard_tol:.3f}]"

    if load_value < target_size - hard_tol:
        hit = "OUTSIDE_HARD"
    elif load_value < target_size - preferred_tol:
        hit = "IN_HARD_ONLY"
    elif load_value <= target_size + preferred_tol:
        hit = "IN_PREFERRED"
    else:
        hit = "ABOVE_PREFERRED"

    header = (
        f"Target={target_size:.1f};Load={load_value:.3f};Pref={preferred_band};"
        f"Hard={hard_band};Hit={hit};Shift={batch_shift or order.shift or ''};Date={batch_date or ''}"
    )
    if not chosen_system or score_tuple is None:
        return header + ";System=UNASSIGNED"

    overflow, high_load, priority, usage, closest, system_name = score_tuple
    score_text = (
        f"Score(overflow={overflow},high_load={high_load},priority={priority},"
        f"usage={usage},closest={closest:.3f});System={system_name}"
    )
    return header + ";" + score_text


def _select_system_for_target(
    orders: List[ProductionOrder],
    target_size: float,
    system_lookup: Dict[str, MakingSystem],
    tracker: BatchCapacityTracker,
    batch_date: str,
    shift: str,
) -> Optional[MakingSystem]:
    if not orders:
        return None

    eligible_sets: List[set] = []
    for order in orders:
        if not order.available_systems:
            return None
        eligible_ids = set()
        for system in order.available_systems:
            if _system_supports_target(system, target_size) and _system_allows_target_for_orders(system, target_size, orders):
                eligible_ids.add(system.system_id)
        if not eligible_ids:
            return None
        eligible_sets.append(eligible_ids)

    candidate_ids = set.intersection(*eligible_sets) if eligible_sets else set()
    if not candidate_ids:
        candidate_ids = eligible_sets[0]

    def _score(sid: str):
        system = system_lookup.get(sid)
        if not system or not system.supported_msu:
            return (float('inf'), sid)
        overflow_flag, high_load_flag, priority, usage, closest, _name = _system_score_tuple(
            system, target_size, tracker, batch_date, shift
        )
        return (
            overflow_flag,
            high_load_flag,
            priority,
            usage,
            closest,
            system.name,
        )

    chosen_id = sorted(candidate_ids, key=_score)[0]
    return system_lookup.get(chosen_id)


def _check_tandem_11_alerts(batches: List[Batch]) -> None:
    """当 Tandem 系统使用 1.1 MSU 批次，且同一班次超过 3 批时，添加警告。"""
    # {(date, shift): count}
    tandem_11_usage: Dict[Tuple[str, str], int] = defaultdict(int)
    tandem_11_batches: Dict[Tuple[str, str], List[Batch]] = defaultdict(list)
    for batch in batches:
        if not batch.assigned_system or not _is_tandem_system(batch.assigned_system):
            continue
        if batch.msu_size and abs(batch.msu_size - 1.1) < 0.01:
            key = (batch.date or '', batch.shift or '')
            tandem_11_usage[key] += batch.physical_batches
            tandem_11_batches[key].append(batch)

    for (usage_date, shift), count in tandem_11_usage.items():
        if count > 3:
            alert_msg = (
                f"警告: {usage_date} {shift}班 Tandem 系统使用 1.1 MSU 批次 {count} 批，超过建议上限 3 批。"
            )
            for batch in tandem_11_batches[(usage_date, shift)]:
                for order in batch.orders:
                    order.alerts.append(alert_msg)


GSS12_HALF_BATCH_SHIFT_LIMIT = 5


def _check_gss12_half_batch_limit(batches: List[Batch]) -> None:
    """GSS1+GSS2 的 half batch (2.2 MSU) 每个班次最多 5 批，
    因为 GSS2 不能做 half batch，只有 GSS1 可以（GSS1 上限 5 批/班次）。"""
    # {(date, shift): count}
    half_usage: Dict[Tuple[str, str], int] = defaultdict(int)
    half_batches: Dict[Tuple[str, str], List[Batch]] = defaultdict(list)
    for batch in batches:
        if not batch.assigned_system or not _is_gss12_system(batch.assigned_system):
            continue
        if batch.msu_size and abs(batch.msu_size - 2.2) < 0.01:
            key = (batch.date or '', batch.shift or '')
            half_usage[key] += batch.physical_batches
            half_batches[key].append(batch)

    for (usage_date, shift), count in half_usage.items():
        if count > GSS12_HALF_BATCH_SHIFT_LIMIT:
            alert_msg = (
                f"警告: {usage_date} {shift}班 GSS1+GSS2 half batch 计划 {count} 批，"
                f"超出 GSS1 单独上限 {GSS12_HALF_BATCH_SHIFT_LIMIT} 批（GSS2 不支持 half batch）。"
            )
            for batch in half_batches[(usage_date, shift)]:
                for order in batch.orders:
                    order.alerts.append(alert_msg)


def _create_and_assign_batches(orders: List[ProductionOrder], systems: List[MakingSystem]):
    tracker = BatchCapacityTracker(systems)
    batches: List[Batch] = []
    batch_id_counter = count(1)
    system_lookup = {system.system_id: system for system in systems}

    grouped_orders = _group_orders_by_wip(orders)

    for wip_code, group in grouped_orders.items():
        first_pass, deferred_orders = _plan_batches_for_group(group, allow_cross_day=False)
        second_pass: List[Dict] = []
        if deferred_orders:
            second_pass, _ = _plan_batches_for_group(deferred_orders, allow_cross_day=True)
        planned_batches = first_pass + second_pass

        for plan in planned_batches:
            plan_orders = plan['orders']
            target_size = plan['target_size']

            if not plan_orders:
                continue

            anchor_order = min(plan_orders, key=lambda o: o.start_datetime)
            batch_shift = anchor_order.shift
            batch_date = anchor_order.start_datetime.date().isoformat()

            system = _select_system_for_target(plan_orders, target_size, system_lookup, tracker, batch_date, batch_shift)
            if not system:
                failed_orders = _allocate_plan_orders_individually(
                    plan_orders,
                    system_lookup,
                    tracker,
                    batch_id_counter,
                    batches,
                )
                if failed_orders:
                    for order in failed_orders:
                        order.alerts.append("警告: 无法为搭批选择合适的搅拌系统。")
                        order.decision_explain = _build_decision_explain(
                            order=order,
                            target_size=target_size,
                            load_value=order.msu_demand or 0.0,
                            chosen_system=None,
                            score_tuple=None,
                            batch_shift=batch_shift,
                            batch_date=batch_date,
                        )
                continue

            batch_id = f"B{next(batch_id_counter):04d}"
            current_load = sum(order.msu_demand or 0 for order in plan_orders)
            batch_date = anchor_order.start_datetime.date().isoformat()
            physical_batches = _calculate_physical_batches(system, target_size)
            batch = Batch(
                batch_id=batch_id,
                wip_code=wip_code,
                msu_size=target_size,
                assigned_system=system,
                shift=batch_shift,
                date=batch_date,
                orders=plan_orders,
                current_load=current_load,
                physical_batches=physical_batches
            )
            batches.append(batch)

            for order in plan_orders:
                order.assigned_system = system
                order.batch_id = batch_id
                score_info = _system_score_tuple(system, target_size, tracker, batch_date, batch_shift)
                order.decision_explain = _build_decision_explain(
                    order=order,
                    target_size=target_size,
                    load_value=current_load,
                    chosen_system=system,
                    score_tuple=score_info,
                    batch_shift=batch_shift,
                    batch_date=batch_date,
                )

            tracker.record_allocation(system, batch_date, batch_shift, physical_batches)
            _refresh_batch_notes(batch)

    _second_pass_merge_batches(batches, tracker)
    _rebalance_overflow_batches(batches, tracker, system_lookup)
    _split_gss3_odd_multiple_batches(batches, tracker, system_lookup, orders)
    for batch in batches:
        _refresh_batch_notes(batch)
    tracker.rebuild_usage(batches)
    _check_tandem_11_alerts(batches)
    _check_gss12_half_batch_limit(batches)
    return batches, tracker.summarize()


def _allocate_plan_orders_individually(
    plan_orders: List[ProductionOrder],
    system_lookup: Dict[str, MakingSystem],
    tracker: BatchCapacityTracker,
    batch_id_counter,
    batches: List[Batch],
) -> List[ProductionOrder]:
    failed: List[ProductionOrder] = []
    sorted_orders = sorted(plan_orders, key=lambda o: o.start_datetime)
    for single_order in sorted_orders:
        allowed_sizes = _get_allowed_msu_sizes(single_order.product_category)
        if not allowed_sizes:
            failed.append(single_order)
            continue
        target_size = _choose_target_size_for_single(single_order, allowed_sizes)
        shift = single_order.shift or 'N'
        batch_date = single_order.start_datetime.date().isoformat()
        system = _select_system_for_target([single_order], target_size, system_lookup, tracker, batch_date, shift)
        if not system:
            failed.append(single_order)
            continue

        batch_id = f"B{next(batch_id_counter):04d}"
        physical_batches = _calculate_physical_batches(system, target_size)
        batch_date = single_order.start_datetime.date().isoformat()
        current_load = single_order.msu_demand or 0.0
        batch = Batch(
            batch_id=batch_id,
            wip_code=single_order.wip_code,
            msu_size=target_size,
            assigned_system=system,
            shift=shift,
            date=batch_date,
            orders=[single_order],
            current_load=current_load,
            physical_batches=physical_batches,
        )
        batches.append(batch)
        single_order.assigned_system = system
        single_order.batch_id = batch_id
        score_info = _system_score_tuple(system, target_size, tracker, batch_date, shift)
        single_order.decision_explain = _build_decision_explain(
            order=single_order,
            target_size=target_size,
            load_value=current_load,
            chosen_system=system,
            score_tuple=score_info,
            batch_shift=shift,
            batch_date=batch_date,
        )
        tracker.record_allocation(system, batch_date, shift, physical_batches)
        _refresh_batch_notes(batch)

    return failed


def _rebalance_overflow_batches(
    batches: List[Batch],
    tracker: BatchCapacityTracker,
    system_lookup: Dict[str, MakingSystem],
) -> None:
    gss12_system = None
    for system in system_lookup.values():
        if _is_gss12_system(system):
            gss12_system = system
            break
    if not gss12_system:
        return

    while True:
        tracker.rebuild_usage(batches)
        overflow_entries = tracker.get_shift_overflow()
        moved = False
        for system_id, usage_date, shift, _excess in overflow_entries:
            source_system = system_lookup.get(system_id)
            if not source_system:
                continue
            if source_system.name != 'GSS3':
                continue
            # Only move batches whose orders are in the 12t_to_6t conversion list
            # (allow_gss12_reduced_moq=True), since GSS1+2 can only do 2.2 for those.
            candidates = [
                batch for batch in batches
                if batch.assigned_system == source_system
                and batch.date == usage_date
                and batch.shift == shift
                and batch.msu_size <= GSS12_HALF_MOQ + _tolerance_band(GSS12_HALF_MOQ)
                and _system_allows_target_for_orders(gss12_system, batch.msu_size, batch.orders)
            ]
            candidates.sort(key=lambda b: (b.date, b.batch_id))
            for batch in candidates:
                physical = _calculate_physical_batches(gss12_system, batch.msu_size)
                limit = tracker.get_shift_limit(gss12_system, shift)
                usage = tracker.get_shift_usage(gss12_system, usage_date, shift)
                if limit and usage + physical > limit:
                    continue
                batch.assigned_system = gss12_system
                batch.physical_batches = physical
                for order in batch.orders:
                    order.assigned_system = gss12_system
                moved = True
                break
            if moved:
                break
        if not moved:
            break


# GSS3 专属的 2.2 奇数倍目标（无法被 4.4 整除），如 6.6=3×2.2, 11.0=5×2.2。
# 这类目标只能在 GSS3 上多批生产；若 GSS1+2 有空余产能，
# 拆成 4.4(GSS1+2) + 2.2(GSS3) 可减少物理批次数并平衡负载。
_GSS3_ODD_SPLIT_TARGETS = (6.6, 11.0)


def _make_order_split(
    order: ProductionOrder, amount_a: float, amount_b: float
) -> Tuple[ProductionOrder, ProductionOrder]:
    """将单个订单按 MSU 量拆成两个 segment（amount_a 在前，amount_b 在后）。"""
    total = amount_a + amount_b
    base_qty = order.planned_quantity or 0.0
    base_no = order.original_order_number or order.order_number

    seg_a = copy.deepcopy(order)
    seg_b = copy.deepcopy(order)
    seg_a.order_number = f"{base_no}-1"
    seg_b.order_number = f"{base_no}-2"
    seg_a.original_order_number = base_no
    seg_b.original_order_number = base_no
    seg_a.msu_demand = amount_a
    seg_b.msu_demand = amount_b
    if total > 0:
        seg_a.planned_quantity = base_qty * amount_a / total
        seg_b.planned_quantity = base_qty * amount_b / total
    seg_a.segment_index, seg_a.segment_total = 1, 2
    seg_b.segment_index, seg_b.segment_total = 2, 2
    seg_a.alerts = list(order.alerts)
    seg_b.alerts = list(order.alerts)
    for seg in (seg_a, seg_b):
        seg.assigned_system = None
        seg.batch_id = None
        seg.batch_note = None
        seg.batch_count = 0.0
    return seg_a, seg_b


def _distribute_orders_to_buckets(
    batch_orders: List[ProductionOrder],
    bucket_targets: List[float],
    global_orders: List[ProductionOrder],
) -> Optional[List[List[ProductionOrder]]]:
    """按时间顺序把订单依次填入各 bucket（前面的 bucket 先填满）。
    当某个订单跨越 bucket 边界时拆成两个 segment。
    返回每个 bucket 的订单列表；若遇到无法安全拆分的情况返回 None。"""
    pending = sorted(batch_orders, key=lambda o: o.start_datetime)
    buckets: List[List[ProductionOrder]] = [[] for _ in bucket_targets]
    loads = [0.0] * len(bucket_targets)
    splits: List[Tuple[ProductionOrder, List[ProductionOrder]]] = []

    bi = 0
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
                bi += 1
            continue

        # 订单跨越 bucket 边界，需要拆分
        if bi >= len(bucket_targets) - 1:
            return None  # 最后一个 bucket 不能再溢出
        if order.segment_total > 1:
            return None  # 已是拆分段，避免嵌套拆分
        first_amount = target - loads[bi]
        if first_amount <= 1e-6:
            bi += 1
            continue
        second_amount = demand - first_amount
        seg_a, seg_b = _make_order_split(order, first_amount, second_amount)
        buckets[bi].append(seg_a)
        loads[bi] += first_amount
        pending[i] = seg_b  # 余量继续向后分配
        splits.append((order, [seg_a, seg_b]))
        bi += 1

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


def _is_gss3_odd_split_candidate(batch: Batch, gss3_system: MakingSystem) -> bool:
    if not batch.assigned_system or not batch.orders:
        return False
    if batch.assigned_system.system_id != gss3_system.system_id:
        return False
    if not batch.msu_size:
        return False
    if not any(abs(batch.msu_size - target) < 0.05 for target in _GSS3_ODD_SPLIT_TARGETS):
        return False
    for order in batch.orders:
        if (order.product_category or '').lower() != 'shampoo':
            return False
        if not order.available_systems:
            return False
        if not any(_is_gss12_system(system) for system in order.available_systems):
            return False
    return True


def _split_gss3_odd_multiple_batches(
    batches: List[Batch],
    tracker: BatchCapacityTracker,
    system_lookup: Dict[str, MakingSystem],
    global_orders: List[ProductionOrder],
) -> None:
    """将 GSS3 上的 6.6/11.0 奇数倍批次拆成 4.4(GSS1+2)×n + 2.2(GSS3)，
    前提是能减少物理批次数且 GSS1+2 不会因此超班次上限。"""
    gss12_system = next(
        (system for system in system_lookup.values() if _is_gss12_system(system)),
        None,
    )
    gss3_system = next(
        (
            system
            for system in system_lookup.values()
            if system.name and 'gss3' in system.name.lower()
        ),
        None,
    )
    if not gss12_system or not gss3_system:
        return

    tracker.rebuild_usage(batches)

    idx = 0
    while idx < len(batches):
        batch = batches[idx]
        if not _is_gss3_odd_split_candidate(batch, gss3_system):
            idx += 1
            continue

        n12 = int(round((batch.msu_size - 2.2) / 4.4))
        if n12 < 1:
            idx += 1
            continue

        new_physical = n12 + 1
        if new_physical >= batch.physical_batches:
            idx += 1
            continue

        # GSS1+2 班次产能检查
        limit12 = tracker.get_shift_limit(gss12_system, batch.shift)
        usage12 = tracker.get_shift_usage(gss12_system, batch.date, batch.shift)
        if limit12 and usage12 + n12 > limit12:
            idx += 1
            continue

        bucket_targets = [4.4] * n12 + [2.2]
        buckets = _distribute_orders_to_buckets(batch.orders, bucket_targets, global_orders)
        if buckets is None:
            idx += 1
            continue

        new_batches: List[Batch] = []
        for bi, (target, bucket_orders) in enumerate(zip(bucket_targets, buckets)):
            system = gss12_system if abs(target - 4.4) < 0.01 else gss3_system
            anchor = min(bucket_orders, key=lambda o: o.start_datetime)
            load = sum(order.msu_demand or 0.0 for order in bucket_orders)
            new_batch = Batch(
                batch_id=batch.batch_id if bi == 0 else f"{batch.batch_id}-S{bi}",
                wip_code=batch.wip_code,
                msu_size=target,
                assigned_system=system,
                shift=anchor.shift or batch.shift,
                date=anchor.start_datetime.date().isoformat() if anchor.start_datetime else batch.date,
                orders=bucket_orders,
                current_load=load,
                physical_batches=_calculate_physical_batches(system, target),
            )
            rebalance_note = (
                f"批次再平衡: 原 GSS3 {batch.msu_size:.1f} MSU 批次拆分为 "
                f"4.4(GSS1+2)×{n12} + 2.2(GSS3)，本段分配至 {system.name} ({target:.1f} MSU)。"
            )
            for order in bucket_orders:
                order.assigned_system = system
                order.batch_id = new_batch.batch_id
                # 信息性说明（无需 take action），写入决策说明而非预警
                order.decision_explain = rebalance_note
            _refresh_batch_notes(new_batch)
            new_batches.append(new_batch)

        batches.pop(idx)
        for offset, new_batch in enumerate(new_batches):
            batches.insert(idx + offset, new_batch)
        tracker.rebuild_usage(batches)
        idx += len(new_batches)


def process_logic(all_data: Dict[str, pd.DataFrame]) -> Tuple[List[ProductionOrder], List[Batch], List[str]]:
    """
    处理所有业务逻辑的主函数。
    
    Args:
        all_data (dict): 包含所有数据帧的字典。
        
    Returns:
        tuple: (订单列表, 批次列表, 预警信息列表)
    """
    print("正在处理核心业务逻辑...")
    
    # 步骤1: 数据预处理与关联
    production_orders = preprocess_and_create_orders(all_data)

    # 步骤2: 解析搅拌系统并为订单寻找可用系统
    making_systems = _parse_making_systems(all_data)
    production_orders = _split_orders_for_capacity(production_orders, making_systems)
    _find_available_systems_for_orders(production_orders, making_systems)

    # 打印一些示例订单以供验证
    print("\n--- 预处理后订单示例 (前5条) ---")
    for order in production_orders[:5]:
        available_system_names = [s.name for s in order.available_systems] if order.available_systems else []
        display_no = order.original_order_number or order.order_number
        if order.segment_total > 1:
            display_no = f"{display_no} (拆分 {order.segment_index}/{order.segment_total})"
        print(f"订单: {display_no}, 物料: {order.material}, "
              f"班次: {order.shift}, MSU需求: {order.msu_demand:.2f}, "
              f"可用系统: {available_system_names}, "
              f"预警: {' '.join(order.alerts) if order.alerts else '无'}")

    # 步骤3: 创建批次并执行基础校验
    batches, capacity_notes = _create_and_assign_batches(production_orders, making_systems)

    # 汇总信息
    print("\n--- 批次分配示例 (前3条) ---")
    for batch in batches[:3]:
        print(
            f"批次 {batch.batch_id}: WIP {batch.wip_code}, 系统 {batch.assigned_system.name}, "
            f"班次 {batch.shift}, 订单 {batch.get_order_numbers()}"
        )

    print("\n核心逻辑处理完成（第三阶段：基础搭批）。")
    
    processed_orders = production_orders
    alerts = [alert for order in production_orders for alert in order.alerts]
    alerts.extend(capacity_notes)
    
    return processed_orders, batches, alerts
