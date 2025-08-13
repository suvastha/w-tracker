# /weighty/app.py
"""
Weighty — Flask + Tailwind weight tracker with Postgres + JSON fallback.

- App factory that selects storage backend:
    * PostgreSQL via SQLAlchemy Core (preferred)
    * JSON file fallback, fully transparent to the UI
- Registers blueprints for profile, weights, achievements, and health.
- Ensures schema/migrations at boot.
- Ships a tiny "best practice" CSRF-ish token via meta tag (not enforced).
"""

import os
from datetime import datetime
from flask import Flask, render_template, g, jsonify, request, session

from config import Config

# Storage adapters (both expose the same interface)
from services.db import PostgresAdapter, StorageUnavailableError
from services.json_store import JSONAdapter, ensure_data_dir

# Logic utilities (BMI, streaks, charts, achievements, etc.)
from services.logic import QUOTES, pick_daily_quote

# Blueprints
from blueprints.profile import bp as profile_bp
from blueprints.weights import bp as weights_bp
from blueprints.achievements import bp as achievements_bp
from blueprints.health import bp as health_bp


def _pick_storage(config: Config):
    """
    Select storage backend based on env + availability.
    Returns (adapter_instance, mode_str)
    """
    storage_mode = (config.WEIGHTY_STORAGE or "auto").lower()
    db_url = config.DATABASE_URL

    # Force JSON (dev convenience)
    if storage_mode == "json":
        ensure_data_dir(config.DATA_DIR)
        return JSONAdapter(config.DATA_PATH), "json"

    # Force PG if asked
    if storage_mode == "pgsql":
        try:
            pg = PostgresAdapter(db_url)
            pg.ensure_schema()
            return pg, "pgsql"
        except StorageUnavailableError as e:
            # If user *forces* pgsql but it's down, we fall back anyway,
            # because the product promise is "user shouldn't feel an error".
            # We log a warning and transparently switch to JSON.
            print(f"[Weighty] WARNING: PG forced but unavailable: {e}. Falling back to JSON.")
            ensure_data_dir(config.DATA_DIR)
            return JSONAdapter(config.DATA_PATH), "json"

    # AUTO mode: try PG first, then JSON
    if db_url:
        try:
            pg = PostgresAdapter(db_url)
            pg.ensure_schema()
            return pg, "pgsql"
        except StorageUnavailableError as e:
            print(f"[Weighty] WARNING: PG unavailable: {e}. Using JSON fallback.")
    ensure_data_dir(config.DATA_DIR)
    return JSONAdapter(config.DATA_PATH), "json"


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(Config())

    # Secret key (fallback if not provided)
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = os.urandom(24)

    # Storage selection
    adapter, mode = _pick_storage(app.config["CONFIG"])
    app.config["STORAGE_MODE"] = mode
    app.config["STORAGE"] = adapter

    # Register blueprints
    app.register_blueprint(profile_bp)
    app.register_blueprint(weights_bp)
    app.register_blueprint(achievements_bp)
    app.register_blueprint(health_bp)

    @app.before_request
    def attach_storage():
        # Attach adapter to g for request lifecycle
        g.storage = app.config["STORAGE"]
        g.storage_mode = app.config["STORAGE_MODE"]

        # Cheap, friendly session token to embed as meta for writes (not enforced)
        if "csrf_token" not in session:
            session["csrf_token"] = os.urandom(16).hex()

    @app.route("/")
    def index():
        # Count dashboard opens for "graph_gazer" achievement tracking.
        session["dash_opens"] = session.get("dash_opens", 0) + 1
        # We’ll store this count in the storage via a lightweight side-channel
        try:
            g.storage.bump_metric("dashboard_opens")
        except Exception:
            pass  # metric is optional

        # Quote of the day (stable per day)
        today = datetime.now().date().isoformat()
        quote = pick_daily_quote(QUOTES, today)

        return render_template(
            "index.html",
            storage_mode=g.storage_mode,
            csrf_token=session["csrf_token"],
            quote=quote,
        )

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("error.html", code=404, message="Oops, wrong turn!"), 404

    @app.errorhandler(500)
    def server_error(e):
        # Avoid leaking internals; show friendly page
        return render_template("error.html", code=500, message="Something went squish. We’re on it!"), 500

    return app


# Export app instance for Gunicorn
app = create_app()

if __name__ == "__main__":
    # Local dev run
    port = int(os.environ.get("PORT", "5050"))
    app.run(host="0.0.0.0", port=port, debug=True)
