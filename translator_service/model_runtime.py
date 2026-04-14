from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

@dataclass
class ModelResult:
    sql: str
    strategy: str
    prompt_preview: str | None = None

class NL2SQLModelRuntime:
    """
    Runtime de inferencia únicamente.
    El entrenamiento ocurre fuera de este proyecto. Aquí solo se carga:
    - un modelo local ya fine-tuneado (MODEL_PATH)
    - o un modelo remoto/base (MODEL_NAME) para pruebas
    """

    def __init__(self) -> None:
        self.backend = os.getenv("MODEL_BACKEND", "hf_seq2seq")
        self.model_path = os.getenv("MODEL_PATH", "").strip()
        self.model_name = os.getenv("MODEL_NAME", "google/mt5-base").strip()
        self.device_pref = os.getenv("MODEL_DEVICE", "auto").strip().lower()
        self.max_input_tokens = int(os.getenv("MAX_INPUT_TOKENS", "2048"))
        self.max_new_tokens = int(os.getenv("MAX_NEW_TOKENS", "256"))
        self.num_beams = int(os.getenv("MODEL_NUM_BEAMS", "4"))
        self.temperature = float(os.getenv("MODEL_TEMPERATURE", "0.0"))
        self.loaded = False
        self.load_error: str | None = None
        self.device = "cpu"
        self.tokenizer = None
        self.model = None

    @property
    def source(self) -> str:
        return self.model_path or self.model_name

    def ensure_loaded(self) -> None:
        if self.loaded:
            return
        if self.load_error:
            raise RuntimeError(self.load_error)

        try:
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
            import torch

            source = self.source
            if not source:
                raise RuntimeError("MODEL_PATH/MODEL_NAME no configurado")

            if self.device_pref == "auto":
                self.device = "cuda" if torch.cuda.is_available() else "cpu"
            else:
                self.device = self.device_pref

            self.tokenizer = AutoTokenizer.from_pretrained(source)
            self.model = AutoModelForSeq2SeqLM.from_pretrained(source)
            self.model.to(self.device)
            self.model.eval()
            self.loaded = True
        except Exception as e:
            self.load_error = str(e)
            raise

    def build_prompt(
        self,
        nl_original: str,
        nl_normalized: str | None,
        schema_profile: str | None,
        schema_context: dict[str, Any] | None,
        resolved_terms: list[dict[str, Any]],
        resolved_values: list[dict[str, Any]],
    ) -> str:
        schema_context = schema_context or {}
        views = schema_context.get("views", [])
        columns = schema_context.get("columns", {})
        notes = schema_context.get("notes", [])
        instructions = schema_context.get("instructions", [])
        preferred_schema = schema_context.get("preferred_schema", "reporting")

        blocks: list[str] = []
        blocks.append("Tarea: convierte la consulta clínica en lenguaje natural a SQL ejecutable.")
        blocks.append("Restricciones:")
        blocks.append(f"- Usa únicamente vistas del esquema {preferred_schema}.")
        blocks.append("- Devuelve solo SQL válido.")
        blocks.append("- No uses INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE ni CREATE.")
        blocks.append("- Prioriza filtros por códigos clínicos cuando existan códigos resueltos.")
        blocks.append("- Si debes filtrar por texto, usa columnas estandarizadas o de fuente disponibles.")
        if schema_profile:
            blocks.append(f"Perfil de esquema: {schema_profile}")

        if views:
            blocks.append("Vistas disponibles:")
            for view in views:
                blocks.append(f"- {view}")

        if columns:
            blocks.append("Columnas por vista:")
            for view_name, cols in columns.items():
                if isinstance(cols, dict):
                    for col_name, desc in cols.items():
                        blocks.append(f"- {view_name}.{col_name}: {desc}")
                else:
                    blocks.append(f"- {view_name}: {', '.join(cols)}")

        if notes:
            blocks.append("Notas semánticas:")
            for n in notes:
                blocks.append(f"- {n}")

        if instructions:
            blocks.append("Instrucciones del establecimiento:")
            for ins in instructions:
                blocks.append(f"- {ins}")

        if resolved_terms:
            blocks.append("Términos clínicos resueltos:")
            for item in resolved_terms:
                blocks.append(f"- {json.dumps(item, ensure_ascii=False)}")

        if resolved_values:
            blocks.append("Valores resueltos:")
            for item in resolved_values:
                blocks.append(f"- {json.dumps(item, ensure_ascii=False)}")

        blocks.append(f"Consulta original: {nl_original}")
        if nl_normalized:
            blocks.append(f"Consulta normalizada: {nl_normalized}")

        blocks.append("SQL:")
        return "\n".join(blocks)

    def generate(
        self,
        nl_original: str,
        nl_normalized: str | None,
        schema_profile: str | None,
        schema_context: dict[str, Any] | None,
        resolved_terms: list[dict[str, Any]],
        resolved_values: list[dict[str, Any]],
    ) -> ModelResult:
        self.ensure_loaded()

        import torch

        prompt = self.build_prompt(
            nl_original=nl_original,
            nl_normalized=nl_normalized,
            schema_profile=schema_profile,
            schema_context=schema_context,
            resolved_terms=resolved_terms,
            resolved_values=resolved_values,
        )

        inputs = self.tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=self.max_input_tokens,
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        gen_kwargs = {
            "max_new_tokens": self.max_new_tokens,
            "num_beams": self.num_beams,
            "early_stopping": True,
        }
        if self.temperature > 0:
            gen_kwargs.update({"do_sample": True, "temperature": self.temperature})

        with torch.no_grad():
            output_ids = self.model.generate(**inputs, **gen_kwargs)

        text = self.tokenizer.decode(output_ids[0], skip_special_tokens=True).strip()
        return ModelResult(
            sql=text,
            strategy=f"model::{self.source}",
            prompt_preview=prompt[:1200],
        )