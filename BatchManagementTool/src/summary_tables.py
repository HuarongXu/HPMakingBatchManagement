"""Helpers for building aggregated summary tables used in reports."""
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple

import math
import pandas as pd
import re

from models import ProductionOrder

SHIFT_ORDER = ["N", "D", "M", "Other"]
PRODUCT_ORDER = ["Shampoo", "Condi"]


@dataclass
class SummaryTables:
    system_by_day: pd.DataFrame
    line_by_day: List[Tuple[str, pd.DataFrame]]
    segment_by_day: pd.DataFrame


def build_summary_tables(orders: List[ProductionOrder]) -> SummaryTables:
    base_df = _build_summary_base_dataframe(orders)
    return SummaryTables(
        system_by_day=_system_by_day_summary(base_df),
        line_by_day=_line_by_day_summaries(base_df),
        segment_by_day=_segment_by_day_summary(base_df),
    )


def _normalize_shift_label(raw_shift: Optional[str]) -> str:
    label = (raw_shift or "").strip().upper()
    return label if label in {"N", "D", "M"} else "Other"


def _normalize_category_label(raw_category: Optional[str]) -> str:
    if not raw_category:
        return "Unknown"
    text = str(raw_category).strip().lower()
    if "cond" in text:
        return "Condi"
    if "shamp" in text:
        return "Shampoo"
    return "Unknown"


def _normalize_segment_label(raw_segment: Optional[str]) -> str:
    segment = (raw_segment or "").strip()
    return segment if segment else "Unknown"


def _derive_line_label(work_center: Optional[str]) -> str:
    if not work_center:
        return "Unknown"
    text = str(work_center).strip().upper()
    match = re.match(r"HPH([A-Z])", text)
    if match:
        return f"Line {match.group(1)}"
    if "LINE" in text:
        return text.capitalize()
    return text


def _format_date_label(day: date) -> str:
    return f"{day.month}/{day.day}/{day.year}"


def _build_summary_base_dataframe(orders: List[ProductionOrder]) -> pd.DataFrame:
    rows = []
    for order in orders:
        if not order.start_datetime:
            continue
        rows.append(
            {
                "Date": order.start_datetime.date(),
                "Shift": _normalize_shift_label(order.shift),
                "Category": _normalize_category_label(order.product_category),
                "Line": _derive_line_label(order.work_center),
                "Segment": _normalize_segment_label(order.segment),
                "Value": float(order.batch_count or 0.0),
            }
        )
    if not rows:
        return pd.DataFrame(columns=["Date", "Shift", "Category", "Line", "Segment", "Value"])
    return pd.DataFrame(rows)


def _reindex_columns(pivot: pd.DataFrame, target_columns: List[Tuple]) -> pd.DataFrame:
    if pivot.empty or not target_columns:
        return pivot
    multi_index = pd.MultiIndex.from_tuples(target_columns, names=pivot.columns.names)
    return pivot.reindex(columns=multi_index, fill_value=0.0)


def _system_by_day_summary(summary_df: pd.DataFrame) -> pd.DataFrame:
    if summary_df.empty:
        return pd.DataFrame()

    dates = sorted(summary_df["Date"].unique())
    categories = PRODUCT_ORDER + [cat for cat in sorted(summary_df["Category"].unique()) if cat not in PRODUCT_ORDER]
    target_columns = [(day, category) for day in dates for category in categories]

    pivot = (
        summary_df.pivot_table(
            index="Shift",
            columns=["Date", "Category"],
            values="Value",
            aggfunc="sum",
            fill_value=0.0,
        )
    )
    pivot = _reindex_columns(pivot, target_columns)
    for day in dates:
        base_cols = [(day, cat) for cat in PRODUCT_ORDER if (day, cat) in pivot.columns]
        if base_cols:
            pivot[(day, "Shampoo+Condi")] = pivot[base_cols].sum(axis=1)

    ordered_columns: List[Tuple] = []
    for day in dates:
        base_sequence = [cat for cat in PRODUCT_ORDER if (day, cat) in pivot.columns]
        base_total = len(base_sequence)
        seen_base = 0
        for cat in categories:
            column_key = (day, cat)
            if column_key not in pivot.columns:
                continue
            ordered_columns.append(column_key)
            if cat in PRODUCT_ORDER:
                seen_base += 1
                if seen_base == base_total and (day, "Shampoo+Condi") in pivot.columns:
                    ordered_columns.append((day, "Shampoo+Condi"))
        if base_total and seen_base == 0 and (day, "Shampoo+Condi") in pivot.columns:
            ordered_columns.append((day, "Shampoo+Condi"))
        if not base_total and (day, "Shampoo+Condi") in pivot.columns:
            ordered_columns.append((day, "Shampoo+Condi"))

    if ordered_columns:
        pivot = pivot.reindex(columns=pd.MultiIndex.from_tuples(ordered_columns))

    order = [shift for shift in SHIFT_ORDER if shift in pivot.index]
    pivot = pivot.reindex(order)
    if pivot.empty:
        return pd.DataFrame()
    pivot.loc["Total"] = pivot.sum(axis=0)
    flat_columns = [f"{_format_date_label(day)} {category}" for day, category in pivot.columns]
    pivot.columns = flat_columns
    pivot = pivot.reset_index().rename(columns={"Shift": "System"})
    combo_columns = [col for col in pivot.columns if "Shampoo+Condi" in col]
    total_mask = pivot["System"] == "Total"
    if combo_columns and total_mask.any():
        total_values = pivot.loc[total_mask, combo_columns].iloc[0]
        extra_row = {col: (float(total_values[col]) if col in combo_columns else math.nan) for col in pivot.columns}
        extra_row["System"] = "Total Shampoo+Condi"
        pivot.loc[len(pivot)] = extra_row
    return pivot


def _line_by_day_summaries(summary_df: pd.DataFrame) -> List[Tuple[str, pd.DataFrame]]:
    if summary_df.empty:
        return []

    summaries: List[Tuple[str, pd.DataFrame]] = []
    categories = PRODUCT_ORDER + [cat for cat in sorted(summary_df["Category"].unique()) if cat not in PRODUCT_ORDER]

    for day in sorted(summary_df["Date"].unique()):
        day_df = summary_df[summary_df["Date"] == day]
        lines = sorted(day_df["Line"].unique())
        if not lines:
            continue
        column_plan = [(line, category) for line in lines for category in categories]
        pivot = (
            day_df.pivot_table(
                index="Shift",
                columns=["Line", "Category"],
                values="Value",
                aggfunc="sum",
                fill_value=0.0,
            )
        )
        pivot = _reindex_columns(pivot, column_plan)
        order = [shift for shift in SHIFT_ORDER if shift in pivot.index]
        pivot = pivot.reindex(order)
        if pivot.empty:
            continue
        if "Other" in pivot.index and (pivot.loc["Other"] == 0).all():
            pivot = pivot.drop("Other")
        pivot.loc["Total"] = pivot.sum(axis=0)
        flat_columns = [f"{line} {category}" for line, category in pivot.columns]
        pivot.columns = flat_columns
        pivot = pivot.reset_index().rename(columns={"Shift": "System"})
        summaries.append((f"By Day - {_format_date_label(day)}", pivot))
    return summaries


def _segment_by_day_summary(summary_df: pd.DataFrame) -> pd.DataFrame:
    if summary_df.empty:
        return pd.DataFrame()
    pivot = summary_df.pivot_table(
        index="Segment",
        columns="Date",
        values="Value",
        aggfunc="sum",
        fill_value=0.0,
    ).sort_index()
    if pivot.empty:
        return pd.DataFrame()
    ordered_columns = sorted(pivot.columns)
    pivot = pivot.reindex(ordered_columns, axis=1)
    pivot.loc["Total"] = pivot.sum(axis=0)
    flat_columns = ["Seg"] + [_format_date_label(day) for day in pivot.columns]
    pivot = pivot.reset_index()
    pivot.columns = flat_columns
    return pivot
