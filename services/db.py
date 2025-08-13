# /weighty/services/db.py
"""
PostgreSQL adapter using SQLAlchemy Core (connection pooling, simple retries).
Exposes a uniform interface used by blueprints and logic:
    - ensure_schema()
    - get_profile(), upsert_profile(profile_dict)
    - list_weights(limit, offset)
    - upsert_weight_by_date(profile_id, date, weight)
    - update_weight(id, weight, date)
    - delete_weight(id)
    - get_all_weights_for_profile(profile_id)
    - get_achievements(), set_achievements(keys), add_achievement(key)
    - bump_metric(name)
The JSON adapter mirrors the same methods.
"""

import time
from typing import Dict, Any, List, Tuple
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError

RETRY_SECONDS = [0.2, 0.5, 1.0]

class StorageUnavailableError(Exception):
    pass

class PostgresAdapter:
    def __init__(self, db_url: str):
        if not db_url:
            raise StorageUnavailableError("DATABASE_URL not provided")
        try:
            self.engine = create_engine(db_url, pool_pre_ping=True)
            # Warm-up test connection
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as e:
            raise StorageUnavailableError(str(e)) from e

    # --- schema / migrations ---
    def ensure_schema(self):
        with self.engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS profiles (
                  id SERIAL PRIMARY KEY,
                  name VARCHAR(120) NOT NULL,
                  height_feet INT NOT NULL,
                  height_inches INT NOT NULL,
                  starting_weight NUMERIC(6,2) NOT NULL,
                  goal_weight NUMERIC(6,2) NOT NULL,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS weights (
                  id SERIAL PRIMARY KEY,
                  profile_id INT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
                  date DATE NOT NULL,
                  weight NUMERIC(6,2) NOT NULL,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  UNIQUE(profile_id, date)
                );
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS meta (
                  k TEXT PRIMARY KEY,
                  v TEXT NOT NULL
                );
            """))
            # seed schema_version if absent
            r = conn.execute(text("SELECT v FROM meta WHERE k='schema_version'")).fetchone()
            if not r:
                conn.execute(text("INSERT INTO meta(k, v) VALUES ('schema_version','1')"))

            # add an achievements table (unlocked keys)
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS achievements (
                  key TEXT PRIMARY KEY,
                  unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
            # lightweight metrics
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS metrics (
                  name TEXT PRIMARY KEY,
                  value BIGINT NOT NULL DEFAULT 0
                );
            """))

    # --- helpers ---
    def _retry(self, fn):
        for delay in RETRY_SECONDS + [None]:
            try:
                return fn()
            except OperationalError:
                if delay is None:
                    raise
                time.sleep(delay)

    # --- profiles ---
    def get_profile(self) -> Dict[str, Any]:
        def _fn():
            with self.engine.begin() as conn:
                row = conn.execute(text("SELECT * FROM profiles ORDER BY id LIMIT 1")).mappings().fetchone()
                return dict(row) if row else None
        return self._retry(_fn)

    def upsert_profile(self, p: Dict[str, Any]) -> Dict[str, Any]:
        # if exists, update; else insert
        def _fn():
            with self.engine.begin() as conn:
                row = conn.execute(text("SELECT id FROM profiles ORDER BY id LIMIT 1")).fetchone()
                if row:
                    conn.execute(text("""
                        UPDATE profiles
                        SET name=:name, height_feet=:hf, height_inches=:hi,
                            starting_weight=:sw, goal_weight=:gw
                        WHERE id=:id
                    """), dict(
                        name=p["name"], hf=p["height_feet"], hi=p["height_inches"],
                        sw=p["starting_weight"], gw=p["goal_weight"], id=row[0]
                    ))
                    rid = row[0]
                else:
                    r = conn.execute(text("""
                        INSERT INTO profiles (name,height_feet,height_inches,starting_weight,goal_weight)
                        VALUES (:name,:hf,:hi,:sw,:gw)
                        RETURNING id
                    """), dict(
                        name=p["name"], hf=p["height_feet"], hi=p["height_inches"],
                        sw=p["starting_weight"], gw=p["goal_weight"]
                    ))
                    rid = r.scalar()
                out = conn.execute(text("SELECT * FROM profiles WHERE id=:id"), {"id": rid}).mappings().fetchone()
                return dict(out)
        return self._retry(_fn)

    # --- weights ---
    def list_weights(self, limit=100, offset=0) -> Tuple[List[Dict[str, Any]], int]:
        def _fn():
            with self.engine.begin() as conn:
                rows = conn.execute(text("""
                    SELECT * FROM weights
                    ORDER BY date DESC
                    LIMIT :limit OFFSET :offset
                """), {"limit": limit, "offset": offset}).mappings().all()
                total = conn.execute(text("SELECT COUNT(*) FROM weights")).scalar()
                return [dict(r) for r in rows], int(total or 0)
        return self._retry(_fn)

    def upsert_weight_by_date(self, profile_id: int, date: str, weight: float) -> Dict[str, Any]:
        def _fn():
            with self.engine.begin() as conn:
                # Upsert by unique (profile_id, date)
                try:
                    r = conn.execute(text("""
                        INSERT INTO weights (profile_id,date,weight)
                        VALUES (:pid, :d, :w)
                        ON CONFLICT (profile_id, date) DO UPDATE SET weight=EXCLUDED.weight
                        RETURNING *
                    """), {"pid": profile_id, "d": date, "w": weight})
                except ProgrammingError:
                    # For older PG, emulate
                    exists = conn.execute(text("""
                        SELECT id FROM weights WHERE profile_id=:pid AND date=:d
                    """), {"pid": profile_id, "d": date}).fetchone()
                    if exists:
                        conn.execute(text("UPDATE weights SET weight=:w WHERE id=:id"),
                                     {"w": weight, "id": exists[0]})
                    else:
                        conn.execute(text("""
                            INSERT INTO weights (profile_id,date,weight)
                            VALUES (:pid,:d,:w)
                        """), {"pid": profile_id, "d": date, "w": weight})
                    r = conn.execute(text("""
                        SELECT * FROM weights WHERE profile_id=:pid AND date=:d
                    """), {"pid": profile_id, "d": date})
                row = r.mappings().fetchone()
                return dict(row)
        return self._retry(_fn)

    def update_weight(self, wid: int, date: str, weight: float) -> Dict[str, Any]:
        def _fn():
            with self.engine.begin() as conn:
                conn.execute(text("""
                    UPDATE weights SET date=:d, weight=:w WHERE id=:id
                """), {"d": date, "w": weight, "id": wid})
                row = conn.execute(text("SELECT * FROM weights WHERE id=:id"), {"id": wid}).mappings().fetchone()
                return dict(row)
        return self._retry(_fn)

    def delete_weight(self, wid: int):
        def _fn():
            with self.engine.begin() as conn:
                conn.execute(text("DELETE FROM weights WHERE id=:id"), {"id": wid})
        return self._retry(_fn)

    def get_all_weights_for_profile(self, profile_id: int) -> List[Dict[str, Any]]:
        def _fn():
            with self.engine.begin() as conn:
                rows = conn.execute(text("""
                    SELECT * FROM weights WHERE profile_id=:pid ORDER BY date ASC
                """), {"pid": profile_id}).mappings().all()
                return [dict(r) for r in rows]
        return self._retry(_fn)

    # --- achievements ---
    def get_achievements(self) -> List[str]:
        def _fn():
            with self.engine.begin() as conn:
                rows = conn.execute(text("SELECT key FROM achievements")).fetchall()
                return [r[0] for r in rows]
        return self._retry(_fn)

    def add_achievement(self, key: str):
        def _fn():
            with self.engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO achievements(key) VALUES (:k)
                    ON CONFLICT (key) DO NOTHING
                """), {"k": key})
        return self._retry(_fn)

    def set_achievements(self, keys: List[str]):
        def _fn():
            with self.engine.begin() as conn:
                conn.execute(text("DELETE FROM achievements"))
                for k in keys:
                    conn.execute(text("INSERT INTO achievements(key) VALUES (:k) ON CONFLICT DO NOTHING"), {"k": k})
        return self._retry(_fn)

    # --- metrics (optional nicety) ---
    def bump_metric(self, name: str, inc: int = 1):
        def _fn():
            with self.engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO metrics(name, value) VALUES (:n, :v)
                    ON CONFLICT (name) DO UPDATE SET value=metrics.value + EXCLUDED.value
                """), {"n": name, "v": inc})
        return self._retry(_fn)
