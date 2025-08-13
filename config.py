import os
import json

class Config:
    def __init__(self):
        # Load environment variables with sensible defaults
        self.DATABASE_URL = os.environ.get(
            "DATABASE_URL",
            "sqlite:///weight_tracker.db"  # Local fallback for dev
        )
        self.SECRET_KEY = os.environ.get("SECRET_KEY", "supersecretkey")
        self.PORT = int(os.environ.get("PORT", 5000))

        # Storage type: 'postgres' or 'json'
        self.WEIGHTY_STORAGE = os.environ.get("WEIGHTY_STORAGE", "json")

        # Data directory & path for JSON fallback
        self.DATA_DIR = os.environ.get("DATA_DIR", os.path.dirname(__file__))
        self.DATA_PATH = os.environ.get(
            "DATA_PATH", os.path.join(self.DATA_DIR, "weight_data.json")
        )

    @staticmethod
    def load_json_data(path):
        """Load weight data from JSON file."""
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
        return []

    @staticmethod
    def save_json_data(path, data):
        """Save weight data to JSON file."""
        with open(path, "w") as f:
            json.dump(data, f, indent=4)