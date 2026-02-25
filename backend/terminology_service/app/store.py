import csv
from pathlib import Path

def load_synonyms(csv_path: str) -> dict[str, str]:
    path = Path(csv_path)
    if not path.exists():
        return {}
    mapping = {}
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        # columnas esperadas: term, canonical
        for row in reader:
            term = (row.get("term") or "").strip().lower()
            canonical = (row.get("canonical") or "").strip()
            if term and canonical:
                mapping[term] = canonical
    return mapping