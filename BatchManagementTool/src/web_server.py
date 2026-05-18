"""
web_server.py

Flask web server for the HP Batch Management Dashboard.
Serves processed data as an interactive web dashboard.
"""
import json
import webbrowser
import threading
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, render_template, request, send_from_directory

from models import Batch, MakingSystem, ProductionOrder
from summary_tables import SummaryTables, build_summary_tables

_BASE_DIR = Path(__file__).parent.parent
_TEMPLATE_DIR = _BASE_DIR / "templates"
_STATIC_DIR = _BASE_DIR / "static"

app = Flask(
    __name__,
    template_folder=str(_TEMPLATE_DIR),
    static_folder=str(_STATIC_DIR),
)

# Disable JSON key sorting to preserve column order in summary tables
app.json.sort_keys = False

# Global data store – populated by start_server()
_DATA: Dict[str, Any] = {}

# pandas imported later for NaN checks
import pandas as _pd


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_str(value, default: str = "") -> str:
    """Convert a value to str safely, treating NaN / None as *default*."""
    if value is None:
        return default
    if isinstance(value, float) and _pd.isna(value):
        return default
    try:
        if _pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    return str(value)


def _order_to_dict(order: ProductionOrder) -> dict:
    return {
        "order_number": _safe_str(order.original_order_number) or _safe_str(order.order_number),
        "order_segment": (
            f"{order.segment_index}/{order.segment_total}"
            if order.segment_total > 1
            else ""
        ),
        "material": _safe_str(order.material),
        "material_description": _safe_str(order.material_description),
        "work_center": _safe_str(order.work_center),
        "shift": _safe_str(order.shift),
        "planned_quantity": order.planned_quantity,
        "uom": _safe_str(order.uom),
        "msu_demand": round(order.msu_demand, 3) if order.msu_demand else 0,
        "suf": order.suf,
        "wip_code": _safe_str(order.wip_code),
        "product_type": _safe_str(order.product_type),
        "assigned_system": order.assigned_system.name if order.assigned_system else "",
        "batch_id": _safe_str(order.batch_id),
        "batch_note": _safe_str(order.batch_note),
        "batch_count": order.batch_count,
        "production_date": order.start_datetime.strftime("%Y-%m-%d") if order.start_datetime else "",
        "start": order.start_datetime.strftime("%Y-%m-%d %H:%M") if order.start_datetime else "",
        "end": order.end_datetime.strftime("%Y-%m-%d %H:%M") if order.end_datetime else "",
        "alerts": order.alerts or [],
        "decision_explain": _safe_str(order.decision_explain),
    }


def _batch_to_dict(batch: Batch) -> dict:
    return {
        "batch_id": _safe_str(batch.batch_id),
        "wip_code": _safe_str(batch.wip_code),
        "msu_size": batch.msu_size,
        "assigned_system": batch.assigned_system.name if batch.assigned_system else "",
        "shift": _safe_str(batch.shift),
        "date": _safe_str(batch.date),
        "current_load": round(batch.current_load, 3),
        "physical_batches": batch.physical_batches,
        "load_ratio": round(batch.current_load / batch.msu_size, 4) if batch.msu_size else 0,
        "orders": [_order_to_dict(o) for o in batch.orders],
        "order_numbers": batch.get_order_numbers(),
    }


def _build_kpi(orders: List[ProductionOrder], batches: List[Batch], alerts: List[str]) -> dict:
    total_orders = len(orders)
    total_batches = len(batches)

    # Per-day system utilisation (limits are per-day, so we must not aggregate across days)
    daily_usage: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"used": 0, "limit": 0})
    )
    for batch in batches:
        sys_name = batch.assigned_system.name if batch.assigned_system else "Unknown"
        batch_date = batch.date or "Unknown"
        daily_usage[batch_date][sys_name]["used"] += batch.physical_batches
        if batch.assigned_system:
            s = batch.assigned_system
            limit = s.total_limit
            if limit is None or _pd.isna(limit):
                limit = (s.n_shift_limit or 0) + (s.d_shift_limit or 0) + (s.m_shift_limit or 0)
            daily_usage[batch_date][sys_name]["limit"] = max(
                daily_usage[batch_date][sys_name]["limit"], int(limit or 0)
            )

    # Average daily utilisation across all production days
    daily_utils = []
    for _date_key, systems in daily_usage.items():
        day_used = sum(v["used"] for v in systems.values())
        day_limit = sum(v["limit"] for v in systems.values())
        if day_limit > 0:
            daily_utils.append(day_used / day_limit * 100)
    utilisation = round(sum(daily_utils) / len(daily_utils), 1) if daily_utils else 0

    critical_alerts = [a for a in alerts if "超出" in a or "超限" in a]
    warning_alerts = [a for a in alerts if a not in critical_alerts]

    return {
        "total_orders": total_orders,
        "total_batches": total_batches,
        "utilisation": utilisation,
        "total_alerts": len(alerts),
        "critical_alerts": len(critical_alerts),
        "warning_alerts": len(warning_alerts),
        "num_days": len(daily_usage),
    }


def _build_heatmap_data(batches: List[Batch]) -> list:
    """Build system × date heatmap data with per-shift breakdown.

    Returns a list of dicts, each representing one (system, date) cell.
    The shifts detail is embedded so the frontend can show N/D/M in tooltip.
    """
    # {date_iso: {system: {shift: used_count}}}
    usage: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(int))
    )
    limits: Dict[str, Dict[str, int]] = {}

    for batch in batches:
        if not batch.assigned_system:
            continue
        sys_name = batch.assigned_system.name
        default_shift = batch.shift or "N"

        for order in batch.orders:
            count_val = float(order.batch_count or 0)
            if count_val <= 0:
                continue
            shift = order.shift or default_shift
            usage_date = (
                order.start_datetime.date().isoformat()
                if order.start_datetime
                else (batch.date or "Unknown")
            )
            usage[usage_date][sys_name][shift] += int(round(count_val))

        if sys_name not in limits:
            s = batch.assigned_system
            limits[sys_name] = {
                "N": s.n_shift_limit or 0,
                "D": s.d_shift_limit or 0,
                "M": s.m_shift_limit or 0,
            }

    # Order systems: GSS1+GSS2 first, then GSS3, then GSS4(Cond), others last
    def _system_sort_key(name: str) -> tuple:
        lower = name.lower()
        if 'gss1' in lower and 'gss2' in lower:
            return (0, name)
        if 'gss3' in lower:
            return (1, name)
        if 'gss4' in lower:
            return (2, name)
        return (3, name)

    all_systems = sorted(limits.keys(), key=_system_sort_key)
    result = []
    for date_str in sorted(usage.keys()):
        grand_used = 0
        grand_limit = 0
        grand_shifts = {"N": {"used": 0, "limit": 0}, "D": {"used": 0, "limit": 0}, "M": {"used": 0, "limit": 0}}
        for sys_name in all_systems:
            total_used = 0
            total_limit = 0
            shifts_detail = []
            for shift in ["N", "D", "M"]:
                used = usage[date_str].get(sys_name, {}).get(shift, 0)
                limit = limits.get(sys_name, {}).get(shift, 0)
                total_used += used
                total_limit += limit
                shifts_detail.append({"shift": shift, "used": used, "limit": limit})
                grand_shifts[shift]["used"] += used
                grand_shifts[shift]["limit"] += limit
            grand_used += total_used
            grand_limit += total_limit
            result.append({
                "date": date_str,
                "system": sys_name,
                "used": total_used,
                "limit": total_limit,
                "ratio": round(total_used / total_limit, 2) if total_limit else 0,
                "shifts": shifts_detail,
            })
        # Add Total summary row
        result.append({
            "date": date_str,
            "system": "Total",
            "used": grand_used,
            "limit": grand_limit,
            "ratio": round(grand_used / grand_limit, 2) if grand_limit else 0,
            "shifts": [
                {"shift": s, "used": grand_shifts[s]["used"], "limit": grand_shifts[s]["limit"]}
                for s in ["N", "D", "M"]
            ],
        })
    return result


def _build_product_distribution(orders: List[ProductionOrder]) -> dict:
    counts: Dict[str, int] = defaultdict(int)
    for order in orders:
        raw = order.product_type
        if raw is None or (isinstance(raw, float) and _pd.isna(raw)):
            raw = "Unknown"
        cat = str(raw).strip()
        if "shamp" in cat.lower():
            counts["Shampoo"] += 1
        elif "cond" in cat.lower():
            counts["Conditioner"] += 1
        else:
            counts["Other"] += 1
    return dict(counts)


def _classify_alerts(alerts: List[str]) -> list:
    """Classify alerts into categories with severity."""
    import re
    classified = []
    seen = set()
    # Pattern: "2026-05-13 N班 GSS3 计划 ..."
    _alert_re = re.compile(r"^(\d{4}-\d{2}-\d{2})\s+([NDMA])班\s+(.+?)\s+计划")
    for alert_text in alerts:
        if alert_text in seen:
            continue
        seen.add(alert_text)
        if "超出" in alert_text or "超限" in alert_text:
            severity = "critical"
        elif "欠装" in alert_text or "不足" in alert_text or "低于" in alert_text or "警告" in alert_text or "缺少" in alert_text:
            severity = "warning"
        else:
            severity = "info"
        entry = {"text": alert_text, "severity": severity}
        m = _alert_re.match(alert_text)
        if m:
            entry["date"] = m.group(1)
            entry["shift"] = m.group(2)
            entry["system"] = m.group(3)
        classified.append(entry)
    # Sort: critical first
    classified.sort(key=lambda x: {"critical": 0, "warning": 1, "info": 2}[x["severity"]])
    return classified


def _summary_df_to_list(df) -> list:
    """Convert a pandas DataFrame to a list of dicts for JSON serialization."""
    if df is None or df.empty:
        return []
    import math
    records = df.to_dict(orient="records")
    # Replace NaN with None
    for row in records:
        for k, v in row.items():
            if isinstance(v, float) and math.isnan(v):
                row[k] = None
    return records


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("dashboard.html",
                           kpi=_DATA.get("kpi", {}),
                           date_label=_DATA.get("date_label", ""),
                           )

@app.route("/orders")
def orders_page():
    return render_template("orders.html", date_label=_DATA.get("date_label", ""))


@app.route("/summary")
def summary_page():
    return render_template("summary.html", date_label=_DATA.get("date_label", ""))


@app.route("/alerts")
def alerts_page():
    return render_template("alerts.html", date_label=_DATA.get("date_label", ""))


@app.route("/manual")
def manual_page():
    """Serve the tool manual / overview HTML from the output folder."""
    output_dir = _BASE_DIR / "output"
    # Find the latest tool_overview HTML
    candidates = sorted(output_dir.glob("tool_overview_*.html"), reverse=True)
    if candidates:
        return send_from_directory(str(output_dir), candidates[0].name)
    # Fallback to intro
    intro = output_dir / "HP_Batch_Tool_Intro.html"
    if intro.exists():
        return send_from_directory(str(output_dir), "HP_Batch_Tool_Intro.html")
    return "操作手册文件未找到。请检查 output/ 目录。", 404


# ---------------------------------------------------------------------------
# API endpoints (JSON)
# ---------------------------------------------------------------------------

@app.route("/api/kpi")
def api_kpi():
    return jsonify(_DATA.get("kpi", {}))


@app.route("/api/orders")
def api_orders():
    return jsonify(_DATA.get("orders_list", []))


@app.route("/api/batches")
def api_batches():
    return jsonify(_DATA.get("batches_list", []))


@app.route("/api/alerts")
def api_alerts():
    return jsonify(_DATA.get("classified_alerts", []))


@app.route("/api/heatmap")
def api_heatmap():
    return jsonify(_DATA.get("heatmap", []))


@app.route("/api/product_distribution")
def api_product_distribution():
    return jsonify(_DATA.get("product_distribution", {}))


@app.route("/api/summary/system_by_day")
def api_summary_system():
    return jsonify(_DATA.get("summary_system_by_day", []))


@app.route("/api/summary/line_by_day")
def api_summary_line():
    return jsonify(_DATA.get("summary_line_by_day", []))


@app.route("/api/summary/segment_by_day")
def api_summary_segment():
    return jsonify(_DATA.get("summary_segment_by_day", []))


@app.route("/api/summary/daily_trend")
def api_summary_daily_trend():
    """Daily batch count by product type (computed from order details)."""
    return jsonify(_DATA.get("daily_trend", []))


@app.route("/api/summary/system_daily")
def api_summary_system_daily():
    """Per-system per-day utilisation (computed from batch details)."""
    return jsonify(_DATA.get("system_daily", []))


# ---------------------------------------------------------------------------
# Server start
# ---------------------------------------------------------------------------

def start_server(
    orders: List[ProductionOrder],
    batches: List[Batch],
    alerts: List[str],
    target_date: Optional[str] = None,
    port: int = 8050,
):
    """Populate data and start the Flask dev server."""

    # Build all data for templates / API
    summaries = build_summary_tables(orders)

    _DATA["orders_list"] = [_order_to_dict(o) for o in orders]
    _DATA["batches_list"] = [_batch_to_dict(b) for b in batches]
    _DATA["kpi"] = _build_kpi(orders, batches, alerts)
    _DATA["heatmap"] = _build_heatmap_data(batches)
    _DATA["product_distribution"] = _build_product_distribution(orders)
    _DATA["classified_alerts"] = _classify_alerts(alerts)
    _DATA["date_label"] = target_date or datetime.now().strftime("%Y%m%d")

    # Build batch-level alerts from report logic
    from report import _batches_dataframe
    _, batch_alerts = _batches_dataframe(batches)
    all_alerts = alerts + batch_alerts
    classified = _classify_alerts(all_alerts)
    _DATA["classified_alerts"] = classified
    # Use deduplicated count (matching what's displayed) for KPI
    _DATA["kpi"] = _build_kpi(orders, batches, [a["text"] for a in classified])

    # Summary tables
    _DATA["summary_system_by_day"] = _summary_df_to_list(summaries.system_by_day)
    _DATA["summary_line_by_day"] = [
        {"title": title, "data": _summary_df_to_list(df)}
        for title, df in summaries.line_by_day
    ]
    _DATA["summary_segment_by_day"] = _summary_df_to_list(summaries.segment_by_day)

    # --- Chart data computed from order / batch details ---
    # Daily trend: batch count by product type per day
    from collections import OrderedDict as _OD
    _daily_trend: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for order in orders:
        if not order.start_datetime:
            continue
        _d = order.start_datetime.date().isoformat()
        cat = (order.product_category or "unknown").lower()
        if "shamp" in cat:
            label = "Shampoo"
        elif "cond" in cat:
            label = "Conditioner"
        else:
            label = "Other"
        _daily_trend[_d][label] += float(order.batch_count or 0)
    _DATA["daily_trend"] = [
        {"date": d, **{k: round(v, 1) for k, v in counts.items()}}
        for d, counts in sorted(_daily_trend.items())
    ]

    # System daily utilisation
    _sys_daily: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"used": 0, "limit": 0})
    )
    for batch in batches:
        if not batch.assigned_system:
            continue
        _sn = batch.assigned_system.name
        _bd = batch.date or "Unknown"
        _sys_daily[_bd][_sn]["used"] += batch.physical_batches
        s = batch.assigned_system
        _lim = s.total_limit
        if _lim is None or _pd.isna(_lim):
            _lim = (s.n_shift_limit or 0) + (s.d_shift_limit or 0) + (s.m_shift_limit or 0)
        _sys_daily[_bd][_sn]["limit"] = max(
            _sys_daily[_bd][_sn]["limit"], int(_lim or 0)
        )
    _DATA["system_daily"] = [
        {"date": d, "system": sn, "used": u["used"], "limit": u["limit"],
         "ratio": round(u["used"] / u["limit"], 2) if u["limit"] else 0}
        for d, systems in sorted(_sys_daily.items())
        for sn, u in sorted(systems.items())
    ]

    # Auto-find free port if default is in use
    import socket
    def _is_port_free(p):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("0.0.0.0", p))
                return True
        except OSError:
            return False

    if not _is_port_free(port):
        original_port = port
        for candidate in range(port + 1, port + 50):
            if _is_port_free(candidate):
                port = candidate
                print(f"端口 {original_port} 已被占用，自动切换到端口 {port}")
                break

    def _get_local_ip():
        """Get the local network IP address of this machine."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    local_ip = _get_local_ip()
    url = f"http://{local_ip}:{port}"
    print(f"\n{'='*50}")
    print(f"  Dashboard running at: {url}")
    print(f"  (Also available at: http://localhost:{port})")
    print(f"  Share this link with colleagues on the same network")
    print(f"  Press Ctrl+C to stop")
    print(f"{'='*50}\n")

    # Auto-open browser after short delay
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
