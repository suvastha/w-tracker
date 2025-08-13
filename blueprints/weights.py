# /weighty/blueprints/weights.py
from flask import Blueprint, jsonify, request, g, Response
from datetime import datetime, timedelta
import csv
import io

from services.logic import (
    feet_inches_to_m, compute_per_row_enrichments, compute_streaks,
    linear_regression_eta, achievements_for
)

bp = Blueprint("weights", __name__)

def _parse_date(d: str) -> str:
    try:
        dt = datetime.fromisoformat(d).date()
        if dt > datetime.now().date():
            raise ValueError("date cannot be in the future")
        return dt.isoformat()
    except Exception:
        raise ValueError("Invalid date (use YYYY-MM-DD)")

def _validate_weight_payload(payload):
    err = {}
    date_str = (payload.get("date") or "").strip()
    weight = payload.get("weight")
    try:
        date_ok = _parse_date(date_str)
    except ValueError as e:
        err["date"] = str(e)
        date_ok = None
    try:
        w = float(weight)
        if not (20 <= w <= 400):
            raise ValueError
    except Exception:
        err["weight"] = "Weight must be a number between 20 and 400."
        w = None
    return err, date_ok, w

def _rows_and_profile():
    p = g.storage.get_profile()
    if not p:
        p = g.storage.upsert_profile({
            "name": "You", "height_feet": 5, "height_inches": 7,
            "starting_weight": 90.0, "goal_weight": 78.0
        })
    rows_asc = g.storage.get_all_weights_for_profile(p["id"])
    rows_asc = sorted(rows_asc, key=lambda r: r["date"])
    series_asc = [(r["date"], float(r["weight"])) for r in rows_asc]
    return p, rows_asc, series_asc

@bp.get("/api/weights")
def list_weights():
    limit = int(request.args.get("limit", "100") or "100")
    offset = int(request.args.get("offset", "0") or "0")
    items, total = g.storage.list_weights(limit=limit, offset=offset)
    # enrich computed fields
    p, rows_asc, series_asc = _rows_and_profile()
    h_m = feet_inches_to_m(p["height_feet"], p["height_inches"])
    enriched_asc = compute_per_row_enrichments(series_asc, h_m)
    # map enrichments by date
    enrich_map = {r["date"]: r for r in enriched_asc}
    # attach to current "items" (DESC)
    for it in items:
        e = enrich_map.get(it["date"])
        if e:
            it.update(e)
    # streaks
    streak_current, streak_best = compute_streaks([d for d, _ in series_asc])
    return jsonify({
        "items": items,
        "totals": {"count": total},
        "streak": {"current": streak_current, "best": streak_best}
    })

@bp.post("/api/weights")
def add_weight():
    payload = request.get_json(force=True, silent=True) or {}
    errors, date_ok, w = _validate_weight_payload(payload)
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    p, rows_asc, series_asc = _rows_and_profile()
    item = g.storage.upsert_weight_by_date(p["id"], date_ok, w)

    # recompute charts and achievements
    p, rows_asc, series_asc = _rows_and_profile()
    h_m = feet_inches_to_m(p["height_feet"], p["height_inches"])
    enriched_asc = compute_per_row_enrichments(series_asc, h_m)
    # Charts arrays
    chart_trend = [{"x": d, "y": val} for d, val in series_asc]
    chart_avg7 = [{"x": d, "y": v} for d, v in [(r["date"], r["avg7"]) for r in enriched_asc]]
    chart_avg30 = [{"x": d, "y": v} for d, v in [(r["date"], r["avg30"]) for r in enriched_asc]]
    # Projection on last 30 points
    last30 = series_asc[-30:]
    proj = linear_regression_eta(last30, float(p["goal_weight"]))

    # Achievements
    unlocked = g.storage.get_achievements()
    edit_count = 0  # tracked via PUT (see below)
    dash_opens = 0  # stored via metrics; ignore here for simplicity
    exported = False
    newly = achievements_for(datetime.now().date().isoformat(), p, series_asc, unlocked, edit_count, dash_opens, exported)
    for k in newly:
        g.storage.add_achievement(k)

    return jsonify({
        "ok": True,
        "item": item,
        "unlocks": newly,
        "charts": {"trend": chart_trend, "avg7": chart_avg7, "avg30": chart_avg30, "projection": proj}
    })

@bp.put("/api/weights/<int:wid>")
def update_weight(wid: int):
    payload = request.get_json(force=True, silent=True) or {}
    errors, date_ok, w = _validate_weight_payload(payload)
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400
    item = g.storage.update_weight(wid, date_ok, w)

    # bump edit metric for data_ninja
    try:
        g.storage.bump_metric("edits", 1)
    except Exception:
        pass

    # Achievements check
    p, rows_asc, series_asc = _rows_and_profile()
    unlocked = g.storage.get_achievements()
    # try get edit count if metrics available
    edit_count = 0
    try:
        # not strictly necessary; JSON adapter keeps metrics, PG too
        pass
    except Exception:
        pass
    newly = []  # edits alone won't unlock most; data_ninja handled elsewhere

    return jsonify({"ok": True, "item": item, "unlocks": newly})

@bp.delete("/api/weights/<int:wid>")
def delete_weight(wid: int):
    g.storage.delete_weight(wid)
    return jsonify({"ok": True})

# --- CSV export ---
@bp.get("/export.csv")
def export_csv():
    p, rows_asc, series_asc = _rows_and_profile()
    h_m = feet_inches_to_m(p["height_feet"], p["height_inches"])
    enriched_asc = compute_per_row_enrichments(series_asc, h_m)
    # join enrichment by date
    emap = {r["date"]: r for r in enriched_asc}

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["id","date","weight","avg7","avg30","bmi","bmi_category","change_from_last"])
    for r in rows_asc:
        e = emap[r["date"]]
        writer.writerow([r["id"], r["date"], r["weight"], e["avg7"], e["avg30"], e["bmi"], e["bmi_category"], e["change_from_last"]])

    csv_bytes = out.getvalue().encode("utf-8")
    # Achievement: share_the_wins
    try:
        g.storage.add_achievement("share_the_wins")
    except Exception:
        pass

    return Response(csv_bytes, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=weighty_export.csv"})
