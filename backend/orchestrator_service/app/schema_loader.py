from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_schema_profile(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {
            "profile_name": "default",
            "views": [],
            "columns": {},
            "notes": [],
            "instructions": [],
            "preferred_schema": "reporting",
        }

    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)

    data.setdefault("profile_name", p.stem)
    data.setdefault("views", [])
    data.setdefault("columns", {})
    data.setdefault("notes", [])
    data.setdefault("instructions", [])
    data.setdefault("preferred_schema", "reporting")
    return data
