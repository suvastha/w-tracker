# /weighty/blueprints/profile.py
from flask import Blueprint, jsonify, request, g, render_template

bp = Blueprint("profile", __name__)

def _validate_profile(payload):
    errors = {}
    name = (payload.get("name") or "").strip()
    hf = int(payload.get("height_feet", 0) or 0)
    hi = int(payload.get("height_inches", 0) or 0)
    sw = float(payload.get("starting_weight", 0) or 0)
    gw = float(payload.get("goal_weight", 0) or 0)

    if not name:
        errors["name"] = "Please enter your name."
    if not (0 < hf <= 8):
        errors["height_feet"] = "Feet should be 1-8."
    if not (0 <= hi < 12):
        errors["height_inches"] = "Inches should be 0-11."
    if not (20 <= sw <= 400):
        errors["starting_weight"] = "Starting weight should be 20–400 kg."
    if not (20 <= gw <= 400):
        errors["goal_weight"] = "Goal weight should be 20–400 kg."
    return errors, dict(name=name, height_feet=hf, height_inches=hi, starting_weight=sw, goal_weight=gw)

@bp.route("/profile")
def profile_page():
    return render_template("profile_settings.html")

@bp.get("/api/profile")
def get_profile():
    p = g.storage.get_profile()
    if not p:
        # Default profile on first run
        p = g.storage.upsert_profile({
            "name": "You",
            "height_feet": 5,
            "height_inches": 7,
            "starting_weight": 90.0,
            "goal_weight": 78.0
        })
    return jsonify({"profile": p})

@bp.post("/api/profile")
def save_profile():
    payload = request.get_json(force=True, silent=True) or {}
    errors, cleaned = _validate_profile(payload)
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400
    p = g.storage.upsert_profile(cleaned)
    return jsonify({"ok": True, "profile": p})
