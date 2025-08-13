# /weighty/config.py
import os
from dataclasses import dataclass

@dataclass
class Config:
    DATABASE_URL: str
    SECRET_KEY: str
    PORT: int
    WEIGHTY_STORAGE: str
    DATA_DIR: str
    DATA_PATH: str

    @staticmethod
    def from_env():
        root = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(root, "data")
        return Config(
            DATABASE_URL=os.environ.get("DATABASE_URL", ""),
            SECRET_KEY=os.environ.get("SECRET_KEY", ""),
            PORT=int(os.environ.get("PORT", "10000") or "10000"),
            WEIGHTY_STORAGE=os.environ.get("WEIGHTY_STORAGE", "auto"),
            DATA_DIR=data_dir,
            DATA_PATH=os.path.join(data_dir, "data.json"),
        )

def __call__():
    # convenience
    return Config.from_env()

class FlaskConfigAdaptor(dict):
    """Expose dataclass instance but keep under key 'CONFIG' for Flask."""
    def __init__(self):
        super().__init__()
        self["CONFIG"] = Config.from_env()

# Usage in app.py: app.config.from_object(Config())
def Config():
    return FlaskConfigAdaptor()
