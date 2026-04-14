import json
from functools import lru_cache
from pathlib import Path

from .config import settings


@lru_cache(maxsize=4)
def load_schema_profile() -> dict:
    path = Path(settings.SCHEMA_PROFILE_PATH)
    if not path.exists():
        raise FileNotFoundError(f"No existe el schema profile: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)