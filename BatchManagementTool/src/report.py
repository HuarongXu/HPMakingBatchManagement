"""Output utilities for generating Excel reports."""
from collections import defaultdict
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import pandas as pd

from models import Batch, ProductionOrder
from summary_tables import SummaryTables, build_summary_tables

OUTPUT_DIR = Path(__file__).parent.parent / "output"
DEFAULT_SENSITIVITY_LABEL = "Business Use"
_LOGGER = logging.getLogger(__name__)

SummaryTable = Tuple[Optional[str], pd.DataFrame]
SummarySection = Tuple[str, Sequence[SummaryTable]]


def _apply_sensitivity_label(
    writer: pd.ExcelWriter,
    label: str = DEFAULT_SENSITIVITY_LABEL,
) -> None:
    """Set workbook metadata so downstream systems can detect the sensitivity label."""

    workbook = getattr(writer, "book", None)
    if workbook is None:
        return

    props = getattr(workbook, "properties", None)
    if props is None:
        return

    try:
        props.contentStatus = label
        props.category = "Sensitivity"
        existing_keywords = props.keywords.split(";") if props.keywords else []
        keywords = {keyword.strip() for keyword in existing_keywords if keyword.strip()}
        keywords.add(f"Sensitivity={label}")
        props.keywords = ";".join(sorted(keywords))
        if not props.description:
            props.description = f"Auto-classified as {label}."
        workbook.properties = props
    except Exception as exc:  # pragma: no cover
        _LOGGER.debug("Failed to stamp sensitivity label: %s", exc)


def _orders_dataframe(orders: List[ProductionOrder]) -> pd.DataFrame:
    rows = []
    for order in orders:
        rows.append(
            {
                "Order Number": order.original_order_number or order.order_number,
                "Order Segment": f"{order.segment_index}/{order.segment_total}" if order.segment_total > 1 else "",
                "Material": order.material,
                "Material Description": order.material_description,
                "Work Center": order.work_center,
                "Shift": order.shift,
                "Planned Quantity (CS)": order.planned_quantity,
                "UoM": order.uom,
                "MSU Demand": order.msu_demand,
                "SU Factor": order.suf,
                "WIP Code": order.wip_code,
                "Product Type": order.product_type,
                "Assigned System": order.assigned_system.name if order.assigned_system else None,
                "Batch ID": order.batch_id,
                "Batch Note": order.batch_note,
                "Batch Count": order.batch_count,
                "Start": order.start_datetime,
                "End": order.end_datetime,
                "Alerts": " | ".join(order.alerts) if order.alerts else None,
                "Decision Explain": order.decision_explain,
            }
        )
    df = pd.DataFrame(rows)
    _validate_datetime_columns(df, ["Start", "End"])
    return df


def _validate_datetime_columns(df: pd.DataFrame, columns: List[str]) -> None:
    for column in columns:
        if column not in df.columns:
            continue
        series = pd.to_datetime(df[column], errors="coerce")
        if series.isna().all():
            continue
        invalid_mask = series.notna() & ((series.dt.year < 2000) | (series.dt.year > 2100))
        if invalid_mask.any():
            sample = series[invalid_mask].iloc[0]
            raise ValueError(
                f"检测到异常时间: 列 '{column}' 出现 {sample}. 请检查输入数据的日期/时间格式。"
            )


def _batches_dataframe(batches: List[Batch]) -> Tuple[pd.DataFrame, List[str]]:
    if not batches:
        return pd.DataFrame(), []

    summary = defaultdict(int)
    max_limits = {}
    shift_limits = {}
    for batch in batches:
        system = batch.assigned_system
        if not system:
            continue
        summary[(system.name, batch.date, batch.shift)] += batch.physical_batches
        if system.name not in max_limits:
            limit = system.total_limit
            if limit is None or (isinstance(limit, (int, float)) and pd.isna(limit)):
                limit = (system.n_shift_limit or 0) + (system.d_shift_limit or 0) + (system.m_shift_limit or 0)
            max_limits[system.name] = limit
            shift_limits[system.name] = {
                'N': system.n_shift_limit or 0,
                'D': system.d_shift_limit or 0,
                'M': system.m_shift_limit or 0,
            }

    systems = sorted(max_limits.keys())
    dates = sorted({batch.date for batch in batches})
    shifts = ["N", "D", "M"]

    total_columns = 2 + len(dates) * len(shifts)
    header_top = ["", ""]
    for date in dates:
        header_top.extend([date] + [""] * (len(shifts) - 1))
    header_bottom = ["System", "Max Batch/Day"]
    for _ in dates:
        header_bottom.extend(shifts)

    data_rows = []
    for system in systems:
        row = [system, max_limits.get(system, "")]
        for date in dates:
            for shift in shifts:
                value = summary.get((system, date, shift), 0)
                row.append("" if value == 0 else value)
        data_rows.append(row)

    total_row = ["Total", ""]
    for date in dates:
        for shift in shifts:
            total_value = sum(summary.get((system, date, shift), 0) for system in systems)
            total_row.append("" if total_value == 0 else total_value)
    data_rows.append(total_row)

    table_rows = [header_top, header_bottom] + data_rows
    column_names = [f"col_{idx}" for idx in range(total_columns)]
    df = pd.DataFrame(table_rows, columns=column_names)
    df.attrs["manual_header"] = True

    alerts: List[str] = []
    for (system_name, date, shift), value in summary.items():
        limit = shift_limits.get(system_name, {}).get(shift, 0)
        if limit and value > limit:
            alerts.append(
                f"{date} {shift}班 {system_name} 计划 {value} 批, 超出最大批次 {limit}."
            )

    return df, alerts
def _alerts_dataframe(alerts: List[str]) -> pd.DataFrame:
    if not alerts:
        return pd.DataFrame({"Alert": ["No alerts"]})
    unique_alerts = list(dict.fromkeys(alerts))
    return pd.DataFrame({"Alert": unique_alerts})


def _start_row_for_summaries(table_rows: int, include_header: bool) -> int:
    header_rows = 1 if include_header else 0
    buffer_rows = 2
    return table_rows + header_rows + buffer_rows


def _write_text_row(writer: pd.ExcelWriter, sheet_name: str, row: int, text: str) -> int:
    pd.DataFrame([[text]]).to_excel(writer, sheet_name=sheet_name, startrow=row, index=False, header=False)
    return row + 1


def _write_table_row(writer: pd.ExcelWriter, sheet_name: str, row: int, table_df: Optional[pd.DataFrame]) -> int:
    if table_df is None or table_df.empty:
        placeholder = pd.DataFrame([["No data"]])
        placeholder.to_excel(writer, sheet_name=sheet_name, startrow=row, index=False, header=False)
        return row + 2
    table_df.to_excel(writer, sheet_name=sheet_name, startrow=row, index=False)
    return row + len(table_df) + 2


def _write_sections(
    writer: pd.ExcelWriter,
    sheet_name: str,
    start_row: int,
    sections: Sequence[SummarySection],
) -> int:
    row = start_row
    for section_title, tables in sections:
        row = _write_text_row(writer, sheet_name, row, section_title)
        for table_title, table_df in tables:
            if table_title:
                row = _write_text_row(writer, sheet_name, row, table_title)
            row = _write_table_row(writer, sheet_name, row, table_df)
        row += 1
    return row


def generate_report(
    orders: List[ProductionOrder],
    batches: List[Batch],
    alerts: List[str],
    filename: Optional[str] = None,
) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"batch_report_{timestamp}.xlsx"
    output_path = OUTPUT_DIR / filename

    orders_df = _orders_dataframe(orders)
    batches_df, batch_alerts = _batches_dataframe(batches)
    all_alerts = alerts + batch_alerts
    alerts_df = _alerts_dataframe(all_alerts)
    summaries: SummaryTables = build_summary_tables(orders)

    batch_header = True
    if hasattr(batches_df, "attrs"):
        batch_header = not batches_df.attrs.get("manual_header")

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        orders_df.to_excel(writer, sheet_name="Orders", index=False)
        batches_df.to_excel(writer, sheet_name="Batches", index=False, header=batch_header)
        alerts_df.to_excel(writer, sheet_name="Alerts", index=False)

        start_row = _start_row_for_summaries(len(batches_df), batch_header)
        line_tables: Sequence[SummaryTable]
        if summaries.line_by_day:
            line_tables = summaries.line_by_day
        else:
            line_tables = [(None, pd.DataFrame())]

        sections: Sequence[SummarySection] = [
            ("By System × Day × Product", [(None, summaries.system_by_day)]),
            ("By Day × Line × System", line_tables),
            ("By Seg × Day", [(None, summaries.segment_by_day)]),
        ]
        _write_sections(writer, "Batches", start_row, sections)
        _apply_sensitivity_label(writer)

    return output_path
