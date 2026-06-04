from __future__ import annotations

from fastapi.routing import APIRoute

from .clinical_history import router as clinical_history_router
from .configurable_settings import router as configurable_settings_router
from .main import app


def _remove_route(path: str, methods: set[str]) -> None:
    """Reemplaza endpoints puntuales sin tocar el main.py grande del orquestador."""
    kept = []
    for route in app.router.routes:
        if isinstance(route, APIRoute) and route.path == path and route.methods and route.methods.intersection(methods):
            continue
        kept.append(route)
    app.router.routes = kept


# Se registra fuera de main.py para no tocar el orquestador grande existente.
# Procfile apunta a este módulo y conserva todos los endpoints originales.
app.include_router(clinical_history_router)

# /system/config ya existe en main.py. Lo retiramos solo para ese path y lo volvemos
# a registrar con la respuesta ampliada de configuración del sistema.
_remove_route("/system/config", {"GET", "PATCH"})
app.include_router(configurable_settings_router)
