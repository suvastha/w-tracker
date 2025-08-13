# /weighty/services/json_store.py
"""
JSON storage adapter with atomic writes and simple schema versioning.
- File structure mirrors the SQL schema.
- Uses a cross-platform file lock (best-effort) to avoid race conditions.
- Writes via temp file + os.replace for atomicity.
"""

import json
import os
import tempfile
import time
from datetime import datetime
from typing import Dict, Any, List, Tuple

SCHEMA_VERSION = 1

def ensure_data_dir(path: str):
    os.makedirs(path, exist_ok=True)

# --- very small lock helper ---
class _FileLock:
    def __init__(self, path):
        self.lock_path = path + ".lock"
        self.fd = None

    def __enter__(self):
        # naive spin lock
        while True:
            try:
                self.fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
                break
            except FileExistsError:
                time.sleep(0.02)
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            os.close(self.fd)
        except Exception:
            pass
        try:
            os.remove(self.lock_path)
        except FileNotFoundError:
            pass

class JSONAdapter:
    def __init__(self, data_path: str):
        self.path = data_path
        # Initialize file if missing
        if not os.path.exists(self.path):
            ensure_data_dir(os.path.dirname(self.path))
            self._atomic_write({
                "profiles": [],
                "weights": [],
                "achievements": [],
                "metrics": {},
                "meta": {"schema_version": SCHEMA_VERSION, "next_id": {"profiles": 1, "weights": 1}}
            })
        self._ensure_schema()

    # --- internal helpers ---
    def _read(self) -> Dict[str, Any]:
        with _FileLock(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)

    def _atomic_write(self, data: Dict[str, Any]):
        tmp_fd, tmp_path = tempfile.mkstemp(prefix="weighty_", suffix=".json", dir=os.path.dirname(self.path))
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self.path)  # atomic on POSIX/Windows
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    def _write(self, data: Dict[str, Any]):
        with _FileLock(self.path):
            self._atomic_write(data)

    def _ensure_schema(self):
        data = self._read()
        sv = int(data.get("meta", {}).get("schema_version", 0))
        if sv < SCHEMA_VERSION:
            # Future migrations go here
            data["meta"]["schema_version"] = SCHEMA_VERSION
            self._write(data)

    # --- public API mirroring PostgresAdapter ---
    def ensure_schema(self):
        # already ensured by constructor; keep interface parity
        return

    # profiles
    def get_profile(self):
        data = self._read()
        return data["profiles"][0] if data["profiles"] else None

    def upsert_profile(self, p: Dict[str, Any]):
        data = self._read()
        if data["profiles"]:
            # update
            p_existing = data["profiles"][0]
            p_existing.update({
                "name": p["name"],
                "height_feet": p["height_feet"],
                "height_inches": p["height_inches"],
                "starting_weight": p["starting_weight"],
                "goal_weight": p["goal_weight"],
            })
        else:
            pid = data["meta"]["next_id"]["profiles"]
            data["meta"]["next_id"]["profiles"] += 1
            data["profiles"].append({
                "id": pid,
                "name": p["name"],
                "height_feet": p["height_feet"],
                "height_inches": p["height_inches"],
                "starting_weight": p["starting_weight"],
                "goal_weight": p["goal_weight"],
                "created_at": datetime.now().date().isoformat(),
            })
        self._write(data)
        return data["profiles"][0]

    # weights
    def list_weights(self, limit=100, offset=0) -> Tuple[List[Dict[str, Any]], int]:
        data = self._read()
        items = sorted(data["weights"], key=lambda r: r["date"], reverse=True)
        total = len(items)
        return items[offset:offset+limit], total

    def _find_profile_id(self):
        data = self._read()
        if data["profiles"]:
            return data["profiles"][0]["id"]
        # Create a default profile if nothing exists yet
        pid = data["meta"]["next_id"]["profiles"]
        data["meta"]["next_id"]["profiles"] += 1
        data["profiles"].append({
            "id": pid, "name": "You",
            "height_feet": 5, "height_inches": 7,
            "starting_weight": 90.0, "goal_weight": 78.0,
            "created_at": datetime.now().date().isoformat()
        })
        self._write(data)
        return pid

    def upsert_weight_by_date(self, profile_id: int, date: str, weight: float) -> Dict[str, Any]:
        data = self._read()
        # ensure profile exists
        if not data["profiles"]:
            self._find_profile_id()
            data = self._read()
        # Overwrite rule by (profile_id, date)
        existing = next((w for w in data["weights"]
                         if w["profile_id"] == profile_id and w["date"] == date), None)
        if existing:
            existing["weight"] = round(float(weight), 2)
        else:
            wid = data["meta"]["next_id"]["weights"]
            data["meta"]["next_id"]["weights"] += 1
            data["weights"].append({
                "id": wid, "profile_id": profile_id,
                "date": date, "weight": round(float(weight), 2),
                "created_at": datetime.now().date().isoformat()
            })
        self._write(data)
        # return the row
        return next(w for w in data["weights"] if w["profile_id"] == profile_id and w["date"] == date)

    def update_weight(self, wid: int, date: str, weight: float) -> Dict[str, Any]:
        data = self._read()
        for w in data["weights"]:
            if w["id"] == wid:
                w["date"] = date
                w["weight"] = round(float(weight), 2)
                self._write(data)
                return w
        return None

    def delete_weight(self, wid: int):
        data = self._read()
        data["weights"] = [w for w in data["weights"] if w["id"] != wid]
        self._write(data)

    def get_all_weights_for_profile(self, profile_id: int) -> List[Dict[str, Any]]:
        data = self._read()
        return sorted([w for w in data["weights"] if w["profile_id"] == profile_id], key=lambda x: x["date"])

    # achievements
    def get_achievements(self) -> List[str]:
        data = self._read()
        return data.get("achievements", [])

    def add_achievement(self, key: str):
        data = self._read()
        if key not in data.get("achievements", []):
            data["achievements"].append(key)
            self._write(data)

    def set_achievements(self, keys: List[str]):
        data = self._read()
        data["achievements"] = list(dict.fromkeys(keys))  # dedupe, preserve order
        self._write(data)

    # metrics (optional nicety)
    def bump_metric(self, name: str, inc: int = 1):
        data = self._read()
        metrics = data.get("metrics", {})
        metrics[name] = int(metrics.get(name, 0)) + inc
        data["metrics"] = metrics
        self._write(data)
