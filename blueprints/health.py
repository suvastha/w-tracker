# /weighty/blueprints/health.py
from flask import Blueprint, jsonify, g

bp = Blueprint("health", __name__)

@bp.get("/healthz")
def healthz():
    # Quick liveness + storage mode
    ok = True
    mode = getattr(g, "storage_mode", "unknown")
    return jsonify({"ok": ok, "storage": mode})
