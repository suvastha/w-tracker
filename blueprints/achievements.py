# /weighty/blueprints/achievements.py
from flask import Blueprint, jsonify, render_template, g
from services.logic import ACHIEVEMENTS

bp = Blueprint("achievements", __name__)

@bp.get("/achievements")
def page():
    # Render a simple gallery page
    unlocked = set(g.storage.get_achievements())
    items = []
    for key, name, icon, desc in ACHIEVEMENTS:
        items.append({"key": key, "name": name, "icon": icon, "desc": desc, "done": key in unlocked})
    return render_template("achievements.html", items=items)

@bp.get("/api/achievements")
def api():
    unlocked = g.storage.get_achievements()
    return jsonify({"achievements": ACHIEVEMENTS, "unlocked": unlocked})
