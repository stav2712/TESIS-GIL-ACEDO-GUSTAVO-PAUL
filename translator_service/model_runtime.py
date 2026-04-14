from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
import torch

@dataclass
class ModelResult:
    sql: str
    strategy: str = "model"


class NL2SQLModelRuntime:
    def __init__(self) -> None:
        self.model_name = os.getenv("MODEL_NAME", "google/mt5-base")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.max_input_tokens = int(os.getenv("MAX_INPUT_TOKENS", "2048"))
        self.max_new_tokens = int(os.getenv("MAX_NEW_TOKENS", "256"))

        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(self.model_name)
        self.model.to(self.device)
        self.model.eval()

    def build_prompt(
        self,
        nl_original: str,
        nl_normalized: str | None,
        schema_profile: str | None,
        schema_context: dict[str, Any] | None,
        resolved_terms: list[dict[str, Any]],
        resolved_values: list[dict[str, Any]],
    ) -> str:
        views = (schema_context or {}).get("views", [])
        columns = (schema_context or {}).get("columns", {})

        prompt = []
        prompt.append("Tarea: generar solo SQL PostgreSQL válido.")
        prompt.append("Usa exclusivamente las vistas del esquema reporting.")
        if schema_profile:
            prompt.append(f"Perfil de esquema: {schema_profile}")

        if views:
            prompt.append("Vistas disponibles:")
            for v in views:
                prompt.append(f"- {v}")

        if columns:
            prompt.append("Columnas por vista:")
            for view_name, cols in columns.items():
                prompt.append(f"{view_name}: {', '.join(cols)}")

        if resolved_terms:
            prompt.append("Términos clínicos resueltos:")
            for item in resolved_terms:
                prompt.append(str(item))

        if resolved_values:
            prompt.append("Valores resueltos:")
            for item in resolved_values:
                prompt.append(str(item))

        prompt.append(f"Consulta original: {nl_original}")
        if nl_normalized:
            prompt.append(f"Consulta normalizada: {nl_normalized}")

        prompt.append("Devuelve solo SQL.")
        return "\n".join(prompt)

    def generate(
        self,
        nl_original: str,
        nl_normalized: str | None,
        schema_profile: str | None,
        schema_context: dict[str, Any] | None,
        resolved_terms: list[dict[str, Any]],
        resolved_values: list[dict[str, Any]],
    ) -> ModelResult:
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
        ).to(self.device)

        with torch.no_grad():
            output_ids = self.model.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                num_beams=4,
                early_stopping=True,
            )

        text = self.tokenizer.decode(output_ids[0], skip_special_tokens=True).strip()
        return ModelResult(sql=text, strategy="model_mt5")