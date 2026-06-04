from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

import httpx

from .config import settings

CONTROL_CHARS_RE = re.compile(r"[\x00-\x1F\x7F]")
WORD_RE = re.compile(r"[a-záéíóúüñ0-9_]+", re.IGNORECASE)

DEFAULT_REPORT_TITLE = "Nuevo reporte"
DEFAULT_MAX_TITLE_CHARS = 80

QUESTION_START_RE = re.compile(
    r"^\s*(¿|\?)?\s*(que|qué|cual|cuál|cuales|cuáles|quien|quién|quienes|quiénes|"
    r"cuanto|cuánto|cuanta|cuánta|cuantos|cuántos|cuantas|cuántas|cuando|cuándo|"
    r"donde|dónde|como|cómo)\b",
    re.IGNORECASE,
)

REQUEST_PREFIX_RE = re.compile(
    r"^\s*(¿|\?)?\s*(por\s+favor\s+)?(quiero|necesito|requiero|dame|dime|hazme|genera|"
    r"generar|muestra|mostrar|muéstrame|muestrame|lista|listar|listame|lístame|consulta|"
    r"consultar|obtén|obten|obtener|saca|sácame|sacame|busca|buscar|encuentra|analiza|"
    r"analizar|calcula|calcular)\b\s*(un|una|el|la|los|las)?\s*(reporte|informe|listado|"
    r"tabla|consulta)?\s*(de|del|sobre|con|para)?\s*",
    re.IGNORECASE,
)

STOPWORDS = {
    "a", "al", "ante", "bajo", "con", "contra", "de", "del", "desde", "durante",
    "e", "el", "en", "entre", "es", "esa", "ese", "eso", "esta", "este", "estos",
    "ha", "han", "hay", "la", "las", "le", "lo", "los", "mas", "más", "me", "mi",
    "mis", "no", "o", "para", "pero", "por", "que", "qué", "se", "sin", "sobre",
    "son", "su", "sus", "tu", "un", "una", "unas", "unos", "y",
}

LOW_COST_TERMS = {"menos", "menor", "minimo", "mínimo", "economico", "económico", "barato", "bajo", "inferior"}
HIGH_COST_TERMS = {"mas", "más", "mayor", "maximo", "máximo", "caro", "costoso", "alto", "superior"}
COST_TERMS = {"costo", "costos", "coste", "costes", "costoso", "costosa", "economico", "económico", "barato", "caro", "gasto", "gastos", "monto", "montos", "pago", "pagos", "reclamo", "reclamos"}
PATIENT_TERMS = {"paciente", "pacientes", "persona", "personas"}
TREATMENT_TERMS = {"tratamiento", "tratamientos", "procedimiento", "procedimientos", "medicamento", "medicamentos", "terapia", "terapias", "atencion", "atención"}
DIAGNOSIS_TERMS = {"diagnostico", "diagnóstico", "diagnosticos", "diagnósticos", "enfermedad", "enfermedades", "condicion", "condición", "condiciones"}
ENCOUNTER_TERMS = {"encuentro", "encuentros", "consulta", "consultas", "visita", "visitas", "cita", "citas"}
MEASUREMENT_TERMS = {"medicion", "medición", "mediciones", "observacion", "observación", "observaciones", "valor", "valores"}
PAYER_TERMS = {"pagador", "pagadores", "seguro", "seguros", "cobertura", "coberturas"}
PROVIDER_TERMS = {"profesional", "profesionales", "medico", "médico", "medicos", "médicos", "doctor", "doctores"}
CENTER_TERMS = {"centro", "centros", "clinica", "clínica", "hospital", "hospitales", "ubicacion", "ubicación", "ubicaciones"}
COUNT_TERMS = {"cuantos", "cuántos", "cuantas", "cuántas", "cantidad", "conteo", "contar", "numero", "número", "total", "totales"}
RANK_TERMS = {"top", "ranking", "rank", "mayor", "mayores", "menor", "menores", "mas", "más", "menos", "maximo", "máximo", "minimo", "mínimo"}

PATIENT_CONDITION_RE = re.compile(
    r"\b(?:paciente|pacientes|persona|personas)\b"
    r"(?:\s+que)?\s+"
    r"(?:sufre|sufren|padece|padecen|presenta|presentan|tiene|tienen|"
    r"diagnosticado|diagnosticada|diagnosticados|diagnosticadas|con)"
    r"(?:\s+(?:de|con|diagn[oó]stico\s+de|diagnosticad[oa]s?\s+con))?\s+"
    r"(?P<condition>[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9][A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9 _.-]{1,80})",
    re.IGNORECASE,
)

UNREQUESTED_TEMPORAL_FILTER_RE = re.compile(
    r"\b(últim[oa]s?|ultim[oa]s?|recientes?|actuales?|"
    r"hoy|ayer|anteayer|semanas?|mes(?:es)?|años?|anual|mensual|"
    r"trimestral|semestral|desde|hasta|entre\s+\d{4}|20\d{2})\b",
    re.IGNORECASE,
)

TEMPORAL_CONTEXT_RE = re.compile(
    r"\b(últim[oa]s?|ultim[oa]s?|recientes?|actuales?|"
    r"hoy|ayer|anteayer|semanas?|mes(?:es)?|años?|anual|mensual|"
    r"trimestral|semestral|desde|hasta|entre|20\d{2})\b",
    re.IGNORECASE,
)


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _tokens(text: str) -> set[str]:
    plain = _strip_accents(text).lower()
    return set(m.group(0) for m in WORD_RE.finditer(plain))


def _max_title_chars() -> int:
    raw = getattr(settings, "OPENAI_TITLE_MAX_CHARS", DEFAULT_MAX_TITLE_CHARS)
    try:
        return max(30, min(int(raw), 120))
    except (TypeError, ValueError):
        return DEFAULT_MAX_TITLE_CHARS


def _cut_without_ellipsis(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rstrip()
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0].rstrip()
    return cut.rstrip(" .,;:¿?¡!-/\\") or text[:max_chars].rstrip(" .,;:¿?¡!-/\\")


def clean_report_title(value: str | None, *, max_chars: int | None = None) -> str:
    limit = max_chars or _max_title_chars()
    text = CONTROL_CHARS_RE.sub(" ", value or "")
    text = text.replace("…", " ").replace("...", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = text.strip("'\"`´“”‘’«» ")
    text = text.rstrip(" .;:¿?¡!-/\\")
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return DEFAULT_REPORT_TITLE

    text = _cut_without_ellipsis(text, limit)
    return text or DEFAULT_REPORT_TITLE


def legacy_truncated_title(nl: str) -> str:
    text = CONTROL_CHARS_RE.sub(" ", nl or "")
    text = re.sub(r"\s+", " ", text).strip()
    return (text[:40] + "…") if len(text) > 40 else (text or DEFAULT_REPORT_TITLE)


def _meaningful_fragment(nl: str, *, max_words: int = 7) -> str:
    text = CONTROL_CHARS_RE.sub(" ", nl or "")
    text = re.sub(r"[¿?¡!]+", " ", text)
    text = REQUEST_PREFIX_RE.sub("", text)
    text = re.sub(r"^\s*(que|qué|cual|cuál|cuales|cuáles|cuantos|cuántos|cuantas|cuántas)\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" .;:,-")

    words: list[str] = []
    for raw in re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]+", text):
        lower = raw.lower()
        if lower in STOPWORDS:
            continue
        if len(lower) == 1 and not lower.isdigit():
            continue
        words.append(raw)
        if len(words) >= max_words:
            break

    return " ".join(words)



def _clean_condition_fragment(value: str) -> str:
    text = CONTROL_CHARS_RE.sub(" ", value or "")
    text = re.split(
        r"\b(?:en|durante|desde|hasta|del|de la|de los)\s+"
        r"(?:últim[oa]s?|ultim[oa]s?|año|años|mes|meses|semana|semanas|20\d{2})\b",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    text = re.sub(r"[¿?¡!]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .;:,-_/\\")
    words = text.split()
    if len(words) > 6:
        text = " ".join(words[:6])
    return clean_report_title(text, max_chars=50)


def _patient_condition_title(nl: str) -> str | None:
    match = PATIENT_CONDITION_RE.search(nl or "")
    if not match:
        return None
    condition = _clean_condition_fragment(match.group("condition"))
    if not condition or condition == DEFAULT_REPORT_TITLE:
        return None
    return clean_report_title(f"Pacientes con {condition}")


def _has_unrequested_temporal_filter(title: str, original_nl: str) -> bool:
    # No permitimos que el título agregue restricciones temporales que el usuario
    # no pidió. Ejemplo corregido: "qué pacientes sufren de asma?" no debe virar
    # a "Pacientes diagnosticados con asma en el último año".
    if not UNREQUESTED_TEMPORAL_FILTER_RE.search(title or ""):
        return False
    return not bool(TEMPORAL_CONTEXT_RE.search(original_nl or ""))


def fallback_report_title(nl: str) -> str:
    toks = _tokens(nl)
    has_patient = bool(toks & PATIENT_TERMS)
    has_treatment = bool(toks & TREATMENT_TERMS)
    has_cost = bool(toks & COST_TERMS)
    has_low_cost = has_cost and bool(toks & LOW_COST_TERMS)
    has_high_cost = has_cost and bool(toks & HIGH_COST_TERMS) and not has_low_cost
    has_count = bool(toks & COUNT_TERMS)
    has_rank = bool(toks & RANK_TERMS)

    if has_patient and has_treatment and has_low_cost:
        return "Pacientes con tratamientos de menor costo"
    if has_patient and has_treatment and has_high_cost:
        return "Pacientes con tratamientos de mayor costo"
    if has_treatment and has_low_cost:
        return "Tratamientos de menor costo"
    if has_treatment and has_high_cost:
        return "Tratamientos de mayor costo"
    if has_patient and has_cost and has_low_cost:
        return "Pacientes por menor costo de atención"
    if has_patient and has_cost and has_high_cost:
        return "Pacientes por mayor costo de atención"
    if has_cost:
        return "Reporte de costos de atención"

    condition_title = _patient_condition_title(nl)
    if condition_title:
        return condition_title

    if has_patient and toks & DIAGNOSIS_TERMS:
        return "Pacientes por diagnóstico"
    if has_patient and toks & ENCOUNTER_TERMS:
        return "Pacientes por encuentros médicos"
    if has_patient and toks & MEASUREMENT_TERMS:
        return "Pacientes por mediciones clínicas"
    if has_patient and toks & PAYER_TERMS:
        return "Pacientes por cobertura de pagador"
    if has_patient and has_count:
        return "Conteo de pacientes"
    if has_patient and has_rank:
        return "Ranking de pacientes"
    if has_patient:
        fragment = _meaningful_fragment(nl, max_words=5)
        if fragment:
            return clean_report_title(f"Reporte de {fragment}")
        return "Reporte de pacientes"

    if toks & DIAGNOSIS_TERMS:
        return "Reporte de diagnósticos"
    if toks & ENCOUNTER_TERMS:
        return "Reporte de encuentros médicos"
    if toks & MEASUREMENT_TERMS:
        return "Reporte de mediciones clínicas"
    if toks & PAYER_TERMS:
        return "Reporte de cobertura y pagadores"
    if toks & PROVIDER_TERMS:
        return "Reporte de profesionales de salud"
    if toks & CENTER_TERMS:
        return "Reporte de centros de atención"
    if has_count:
        return "Conteo de registros clínicos"

    fragment = _meaningful_fragment(nl, max_words=6)
    if fragment:
        return clean_report_title(f"Reporte de {fragment}")
    return DEFAULT_REPORT_TITLE


def _title_generation_enabled() -> bool:
    enabled = getattr(settings, "OPENAI_TITLE_ENABLED", True)
    return bool(enabled) and bool(getattr(settings, "OPENAI_API_KEY", "").strip())


def _title_model() -> str:
    configured = str(getattr(settings, "OPENAI_TITLE_MODEL", "") or "").strip()
    return configured or str(getattr(settings, "OPENAI_GUARD_MODEL", "gpt-4o-mini") or "gpt-4o-mini")


def _title_timeout_seconds() -> float:
    raw = getattr(settings, "OPENAI_TITLE_TIMEOUT_SECONDS", None)
    if raw is None:
        raw = getattr(settings, "OPENAI_GUARD_TIMEOUT_SECONDS", 8.0)
    try:
        return max(1.0, min(float(raw), 15.0))
    except (TypeError, ValueError):
        return 6.0


def _openai_messages(nl: str) -> list[dict[str, str]]:
    limit = _max_title_chars()
    system = (
        "Eres un redactor de títulos para reportes clínicos y administrativos. "
        "No generes SQL ni expliques nada. Devuelve SOLO JSON válido con esta forma: "
        "{\"title\": string}. "
        "El título debe estar en español, ser un título de reporte, no una pregunta, "
        "no copiar literalmente la solicitud del usuario, no terminar con signos de pregunta, "
        f"no usar puntos suspensivos y tener como máximo {limit} caracteres. "
        "CRÍTICO: no agregues filtros que el usuario no pidió: no inventes años, meses, "
        "último año, fechas, rangos, estados, géneros, conteos, rankings ni diagnósticos temporales. "
        "Conserva exactamente el alcance de la solicitud. Si el usuario pregunta "
        "'qué pacientes sufren de asma?', responde 'Pacientes con asma', no 'Pacientes "
        "diagnosticados con asma en el último año'. "
        "Usa estilo profesional y claro, por ejemplo: "
        "'Pacientes con tratamientos de menor costo', 'Pacientes con asma', "
        "'Cobertura por pagador'."
    )
    user = f"Solicitud original del usuario:\n{nl}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _parse_title_payload(payload: dict[str, Any]) -> str | None:
    choices = payload.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        return None
    message = choices[0].get("message") or {}
    content = str(message.get("content") or "").strip()
    if not content:
        return None
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return clean_report_title(content)
    if not isinstance(data, dict):
        return None
    return str(data.get("title") or "").strip() or None


def _is_bad_ai_title(title: str, original_nl: str) -> bool:
    if not title or title == DEFAULT_REPORT_TITLE:
        return True
    if "…" in title or "..." in title:
        return True
    if QUESTION_START_RE.search(title):
        return True
    if _has_unrequested_temporal_filter(title, original_nl):
        return True
    normalized_title = _strip_accents(title).lower().strip(" .;:¿?¡!")
    normalized_original = _strip_accents(original_nl).lower().strip(" .;:¿?¡!")
    if normalized_title and normalized_title == normalized_original:
        return True
    return False


async def generate_report_title(nl: str) -> str:
    fallback = clean_report_title(fallback_report_title(nl))
    if not _title_generation_enabled():
        return fallback

    url = f"{settings.OPENAI_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": _title_model(),
        "messages": _openai_messages(nl),
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }

    try:
        async with httpx.AsyncClient(timeout=_title_timeout_seconds()) as client:
            response = await client.post(url, headers=headers, json=payload)
        if response.status_code >= 400:
            return fallback
        raw_title = _parse_title_payload(response.json())
        title = clean_report_title(raw_title)
        if _is_bad_ai_title(title, nl):
            return fallback
        return title
    except Exception:
        # La generación del título nunca debe bloquear una consulta de reporte.
        return fallback
