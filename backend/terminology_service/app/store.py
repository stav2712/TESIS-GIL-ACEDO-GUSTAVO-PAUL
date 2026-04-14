import csv
from pathlib import Path

def _read_csv(path_str: str) -> list[dict[str, str]]:
    path = Path(path_str)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def load_synonyms(csv_path: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for row in _read_csv(csv_path):
        term = (row.get("term") or "").strip().lower()
        canonical = (row.get("canonical") or "").strip()
        if term and canonical:
            mapping[term] = canonical
    return mapping

def _split_multi(value: str | None) -> list[str]:
    if not value:
        return []
    raw = [x.strip() for x in value.replace("|", ";").split(";")]
    return [x for x in raw if x]

def load_concepts(csv_path: str) -> list[dict]:
    items: list[dict] = []
    for row in _read_csv(csv_path):
        canonical = (row.get("canonical") or "").strip()
        if not canonical:
            continue
        item = {
            "canonical": canonical,
            "category": (row.get("category") or "").strip() or None,
            "codes": _split_multi(row.get("codes")),
            "aliases_es": _split_multi(row.get("aliases_es")),
            "aliases_en": _split_multi(row.get("aliases_en")),
        }
        item["all_terms"] = list(
            dict.fromkeys(
                [canonical.lower()]
                + [x.lower() for x in item["aliases_es"]]
                + [x.lower() for x in item["aliases_en"]]
                + [x.lower() for x in item["codes"]]
            )
        )
        items.append(item)
    return items

def load_value_map(csv_path: str) -> list[dict]:
    items: list[dict] = []
    for row in _read_csv(csv_path):
        canonical = (row.get("canonical") or "").strip()
        field = (row.get("field") or "").strip()
        if not canonical or not field:
            continue
        item = {
            "field": field,
            "canonical": canonical,
            "aliases_es": _split_multi(row.get("aliases_es")),
            "aliases_en": _split_multi(row.get("aliases_en")),
        }
        item["all_terms"] = list(
            dict.fromkeys(
                [canonical.lower()]
                + [x.lower() for x in item["aliases_es"]]
                + [x.lower() for x in item["aliases_en"]]
            )
        )
        items.append(item)
    return items