#!/usr/bin/env python3
"""
Smoke tests automatizados para tesis-nl2sql.

Objetivo:
- Detectar rápido errores 500, validaciones rotas, problemas de autenticación,
  edición, baja lógica, permisos y guardrails SQL.
- Ejecutar por API, sin depender del frontend.
- No modifica datos clínicos. Solo crea un usuario temporal en Identity y lo
  desactiva al final; crea una conversación temporal y la elimina lógicamente.

Uso básico:
  python tools/smoke_test_tesis.py --admin-user admin --admin-pass "TU_PASSWORD"

También puedes usar variables de entorno:
  SMOKE_ADMIN_USER=admin
  SMOKE_ADMIN_PASSWORD=...
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import traceback
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass
class HttpResult:
    method: str
    url: str
    status: int | None
    ok: bool
    json_data: Any | None
    text: str
    error: str | None
    elapsed_ms: int


@dataclass
class TestResult:
    name: str
    status: str  # PASS | FAIL | SKIP | WARN
    http_status: int | None = None
    detail: str = ""
    elapsed_ms: int = 0
    url: str = ""


class SmokeClient:
    def __init__(self, timeout: float = 20.0, verbose: bool = False):
        self.timeout = timeout
        self.verbose = verbose

    def request(
        self,
        method: str,
        url: str,
        *,
        token: str | None = None,
        json_body: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> HttpResult:
        body = None
        req_headers = {"Accept": "application/json"}
        if headers:
            req_headers.update(headers)
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            req_headers["Content-Type"] = "application/json"
        if token:
            req_headers["Authorization"] = f"Bearer {token}"

        start = time.perf_counter()
        req = Request(url=url, data=body, method=method.upper(), headers=req_headers)
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                elapsed = int((time.perf_counter() - start) * 1000)
                parsed = self._parse_json(raw)
                return HttpResult(method, url, resp.status, 200 <= resp.status < 300, parsed, raw, None, elapsed)
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            elapsed = int((time.perf_counter() - start) * 1000)
            parsed = self._parse_json(raw)
            return HttpResult(method, url, exc.code, False, parsed, raw, None, elapsed)
        except URLError as exc:
            elapsed = int((time.perf_counter() - start) * 1000)
            return HttpResult(method, url, None, False, None, "", f"NETWORK: {exc.reason}", elapsed)
        except Exception as exc:  # noqa: BLE001
            elapsed = int((time.perf_counter() - start) * 1000)
            return HttpResult(method, url, None, False, None, "", f"EXCEPTION: {exc}", elapsed)

    @staticmethod
    def _parse_json(raw: str) -> Any | None:
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None


class SmokeSuite:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.client = SmokeClient(timeout=args.timeout, verbose=args.verbose)
        self.results: list[TestResult] = []
        self.token: str | None = None
        self.me: dict[str, Any] | None = None
        self.temp_username: str | None = None
        self.temp_user_id: int | None = None
        self.temp_password = f"TmpSmoke-{int(time.time())}!"
        self.temp_conversation_id: str | None = None

    @staticmethod
    def join(base: str, path: str) -> str:
        return base.rstrip("/") + "/" + path.lstrip("/")

    def add(self, result: TestResult) -> None:
        self.results.append(result)
        icon = {"PASS": "✓", "FAIL": "✗", "SKIP": "-", "WARN": "!"}.get(result.status, "?")
        print(f"{icon} [{result.status:<4}] {result.name} ({result.elapsed_ms} ms) {result.detail}".rstrip())
        if self.args.verbose and result.url:
            print(f"      {result.url}")

    def check(
        self,
        name: str,
        method: str,
        url: str,
        *,
        expected: set[int] | tuple[int, ...] | list[int] | None = None,
        accepted: set[int] | tuple[int, ...] | list[int] | None = None,
        token: str | None = None,
        json_body: Any | None = None,
        skip_if_status: set[int] | tuple[int, ...] | list[int] = (),
        warn_if_status: set[int] | tuple[int, ...] | list[int] = (),
        fail_on_5xx: bool = True,
        detail: str = "",
    ) -> HttpResult:
        expected_set = set(expected or [])
        accepted_set = set(accepted or expected_set or [])
        skip_set = set(skip_if_status or [])
        warn_set = set(warn_if_status or [])
        res = self.client.request(method, url, token=token, json_body=json_body)

        status = res.status
        status_label = f"HTTP {status}" if status is not None else (res.error or "sin respuesta")

        if status is not None and fail_on_5xx and 500 <= status <= 599:
            msg = f"{status_label}. ERROR 5xx: el sistema cayó o no manejó el caso."
            if res.text:
                msg += " " + self.short(res.text)
            self.add(TestResult(name, "FAIL", status, msg, res.elapsed_ms, url))
            return res

        if status in skip_set:
            self.add(TestResult(name, "SKIP", status, f"{status_label}. {detail}".strip(), res.elapsed_ms, url))
            return res

        if status in warn_set:
            self.add(TestResult(name, "WARN", status, f"{status_label}. {detail}".strip(), res.elapsed_ms, url))
            return res

        if accepted_set:
            if status in accepted_set:
                self.add(TestResult(name, "PASS", status, f"{status_label}. {detail}".strip(), res.elapsed_ms, url))
            else:
                msg = f"Esperado {sorted(accepted_set)}, recibido {status_label}."
                if res.error:
                    msg += " " + res.error
                elif res.text:
                    msg += " " + self.short(res.text)
                self.add(TestResult(name, "FAIL", status, msg, res.elapsed_ms, url))
        else:
            # Solo valida que no haya 5xx ni error de red.
            if status is not None and status < 500:
                self.add(TestResult(name, "PASS", status, f"{status_label}. {detail}".strip(), res.elapsed_ms, url))
            else:
                msg = status_label
                if res.error:
                    msg += " " + res.error
                self.add(TestResult(name, "FAIL", status, msg, res.elapsed_ms, url))
        return res

    @staticmethod
    def short(text: str, n: int = 280) -> str:
        text = " ".join((text or "").split())
        return text if len(text) <= n else text[: n - 3] + "..."

    def run(self) -> int:
        print("\n=== Smoke tests tesis-nl2sql ===")
        print(f"Inicio: {datetime.now().isoformat(timespec='seconds')}\n")
        self.test_health()
        self.test_auth()
        if self.token:
            self.test_identity_validations_and_crud()
            self.test_orchestrator_light()
            self.test_query_service_guardrails()
            if self.args.deep_nl:
                self.test_deep_nl_to_sql()
        else:
            self.add(TestResult("Tests autenticados", "SKIP", detail="No hubo token; revisa credenciales o Identity."))

        self.write_reports()
        return self.exit_code()

    def test_health(self) -> None:
        self.check("Identity /health", "GET", self.join(self.args.identity, "/health"), accepted={200})
        self.check("Orchestrator /health", "GET", self.join(self.args.orchestrator, "/health"), accepted={200})
        self.check("Query service /health", "GET", self.join(self.args.query, "/health"), accepted={200})
        self.check("Terminology /health", "GET", self.join(self.args.terminology, "/health"), accepted={200})
        if self.args.translator:
            self.check("Translator /healthz", "GET", self.join(self.args.translator, "/healthz"), accepted={200, 503}, warn_if_status={503})

    def test_auth(self) -> None:
        bad = self.check(
            "Login inválido debe rechazar credenciales",
            "POST",
            self.join(self.args.identity, "/auth"),
            accepted={401, 422},
            json_body={"username": self.args.admin_user, "password": "__password_incorrecto__"},
        )

        res = self.check(
            "Login admin/usuario de prueba",
            "POST",
            self.join(self.args.identity, "/auth"),
            accepted={200},
            json_body={"username": self.args.admin_user, "password": self.args.admin_pass},
        )
        if res.status == 200 and isinstance(res.json_data, dict):
            self.token = res.json_data.get("access_token")
        if not self.token:
            self.add(TestResult("Token JWT presente", "FAIL", res.status, "No se recibió access_token.", res.elapsed_ms, res.url))
            return
        me = self.check("/me con Bearer token", "GET", self.join(self.args.identity, "/me"), accepted={200}, token=self.token)
        if me.status == 200 and isinstance(me.json_data, dict):
            self.me = me.json_data

    def test_identity_validations_and_crud(self) -> None:
        token = self.token
        assert token
        self.check("GET /users búsqueda con carácter regex '[' no debe caer", "GET", self.join(self.args.identity, "/users?" + urlencode({"q": "["})), accepted={200, 403}, token=token, skip_if_status={403})
        profiles = self.check("GET /profiles", "GET", self.join(self.args.identity, "/profiles"), accepted={200, 403}, token=token, skip_if_status={403})
        users = self.check("GET /users", "GET", self.join(self.args.identity, "/users"), accepted={200, 403}, token=token, skip_if_status={403})

        # Validaciones de usuario: nunca deben devolver 500.
        invalid_user_cases = [
            ("Usuario corto debe fallar", {"username": "ab", "password": "abcdef"}, {422}),
            ("Usuario con símbolo inválido debe fallar", {"username": "abc!", "password": "abcdef"}, {400}),
            ("Contraseña corta debe fallar", {"username": "smoke_bad_pwd", "password": "123"}, {422}),
            ("Correo inválido debe fallar", {"username": "smoke_bad_mail", "password": "abcdef", "email": "correo-no-valido"}, {400}),
            ("profile_id no numérico debe fallar", {"username": "smoke_bad_profile", "password": "abcdef", "profile_id": "abc"}, {422}),
            ("full_name excedido debe fallar", {"username": "smoke_bad_name", "password": "abcdef", "full_name": "A" * 121}, {422}),
        ]
        for name, body, statuses in invalid_user_cases:
            self.check(name, "POST", self.join(self.args.identity, "/users"), accepted=set(statuses) | {403}, token=token, json_body=body, skip_if_status={403})

        # Validaciones de perfil.
        self.check(
            "Perfil max_page_size > 50 debe fallar",
            "POST",
            self.join(self.args.identity, "/profiles"),
            accepted={422, 403},
            token=token,
            json_body={"name": "SmokePerfil", "max_page_size": 51},
            skip_if_status={403},
        )
        self.check(
            "Perfil con tabla inválida debe fallar controlado",
            "POST",
            self.join(self.args.identity, "/profiles"),
            accepted={400, 403},
            token=token,
            json_body={"name": "SmokePerfil2", "allowed_tables": ["reporting.vw_pacientes;drop"]},
            skip_if_status={403},
        )

        # CRUD seguro: crea un usuario temporal, edita y da de baja lógicamente.
        # Si no hay permisos de gestión, se salta.
        if users.status == 403:
            self.add(TestResult("CRUD usuario temporal", "SKIP", detail="El usuario autenticado no tiene can_manage_users."))
            return

        suffix = int(time.time())
        self.temp_username = f"smoke_{suffix}"
        create_body = {
            "username": self.temp_username,
            "password": self.temp_password,
            "full_name": "Usuario Smoke Test",
            "email": f"{self.temp_username}@example.com",
        }
        created = self.check("Crear usuario temporal", "POST", self.join(self.args.identity, "/users"), accepted={200}, token=token, json_body=create_body)
        if created.status == 200 and isinstance(created.json_data, dict):
            self.temp_user_id = int(created.json_data.get("id"))
        else:
            return

        upd = self.check(
            "Editar usuario temporal y verificar actualización",
            "PATCH",
            self.join(self.args.identity, f"/users/{self.temp_user_id}"),
            accepted={200},
            token=token,
            json_body={"full_name": "Usuario Smoke Editado", "email": f"{self.temp_username}.editado@example.com"},
        )
        if upd.status == 200 and isinstance(upd.json_data, dict):
            ok = upd.json_data.get("full_name") == "Usuario Smoke Editado" and upd.json_data.get("email") == f"{self.temp_username}.editado@example.com"
            self.add(TestResult("Verificar datos editados", "PASS" if ok else "FAIL", upd.status, "El PATCH persistió los campos." if ok else f"Respuesta inesperada: {upd.json_data}", upd.elapsed_ms, upd.url))

        self.check(
            "Login usuario temporal antes de baja",
            "POST",
            self.join(self.args.identity, "/auth"),
            accepted={200},
            json_body={"username": self.temp_username, "password": self.temp_password},
        )

        self.check(
            "Dar de baja lógica usuario temporal",
            "PATCH",
            self.join(self.args.identity, f"/users/{self.temp_user_id}"),
            accepted={200},
            token=token,
            json_body={"is_active": False},
        )
        self.check(
            "Login usuario dado de baja debe fallar",
            "POST",
            self.join(self.args.identity, "/auth"),
            accepted={401},
            json_body={"username": self.temp_username, "password": self.temp_password},
        )

    def test_orchestrator_light(self) -> None:
        token = self.token
        assert token
        self.check("Orchestrator rechaza sin token", "GET", self.join(self.args.orchestrator, "/conversations"), accepted={401, 403})
        self.check("GET /conversations", "GET", self.join(self.args.orchestrator, "/conversations"), accepted={200}, token=token)

        created = self.check(
            "Crear conversación temporal",
            "POST",
            self.join(self.args.orchestrator, "/conversations"),
            accepted={200},
            token=token,
            json_body={"title": "Smoke test temporal"},
        )
        if created.status == 200 and isinstance(created.json_data, dict):
            self.temp_conversation_id = created.json_data.get("conversation_id")

        if self.temp_conversation_id:
            cid = self.temp_conversation_id
            self.check("Obtener conversación temporal", "GET", self.join(self.args.orchestrator, f"/conversations/{cid}"), accepted={200}, token=token)
            self.check(
                "Renombrar conversación temporal",
                "POST",
                self.join(self.args.orchestrator, f"/conversations/{cid}/rename"),
                accepted={200},
                token=token,
                json_body={"title": "Smoke test editado"},
            )
            self.check(
                "Renombrar conversación con título excedido debe fallar",
                "POST",
                self.join(self.args.orchestrator, f"/conversations/{cid}/rename"),
                accepted={422},
                token=token,
                json_body={"title": "X" * 81},
            )
            self.check("Eliminar conversación temporal baja lógica", "POST", self.join(self.args.orchestrator, f"/conversations/{cid}/delete"), accepted={200}, token=token)
            self.check("Conversación eliminada no debe recuperarse", "GET", self.join(self.args.orchestrator, f"/conversations/{cid}"), accepted={404}, token=token)

        # Admin/config/auditoría: si no hay permisos, SKIP; si hay bug, aparecerá 500 FAIL.
        self.check("GET /admin/dashboard", "GET", self.join(self.args.orchestrator, "/admin/dashboard"), accepted={200, 403}, token=token, skip_if_status={403})
        self.check("GET /admin/audit/reports q='[' no debe romper regex", "GET", self.join(self.args.orchestrator, "/admin/audit/reports?" + urlencode({"page": 1, "page_size": 5, "q": "["})), accepted={200, 403}, token=token, skip_if_status={403})
        self.check("GET /system/config", "GET", self.join(self.args.orchestrator, "/system/config"), accepted={200, 403}, token=token, skip_if_status={403})
        self.check("GET /system/schema", "GET", self.join(self.args.orchestrator, "/system/schema"), accepted={200, 403, 502}, token=token, skip_if_status={403}, warn_if_status={502}, detail="502 indica que Query Service/BD no respondió, no necesariamente validación rota.")
        self.check("GET /system/status", "GET", self.join(self.args.orchestrator, "/system/status"), accepted={200, 403}, token=token, skip_if_status={403})
        self.check(
            "PATCH /system/config inválido debe fallar validado",
            "PATCH",
            self.join(self.args.orchestrator, "/system/config"),
            accepted={422, 403},
            token=token,
            json_body={"query_display_max_rows": 49},
            skip_if_status={403},
        )

        # QueryIn validations sin llamar al modelo.
        self.check(
            "POST /query con pregunta vacía debe fallar",
            "POST",
            self.join(self.args.orchestrator, "/query"),
            accepted={422, 403},
            token=token,
            json_body={"nl": "", "page": 1, "page_size": 10},
            skip_if_status={403},
        )
        self.check(
            "POST /query con page_size > 200 debe fallar",
            "POST",
            self.join(self.args.orchestrator, "/query"),
            accepted={422, 403},
            token=token,
            json_body={"nl": "Cuenta pacientes", "page": 1, "page_size": 201},
            skip_if_status={403},
        )
        self.check(
            "POST /query-jobs con conversation_id inválido debe fallar",
            "POST",
            self.join(self.args.orchestrator, "/query-jobs"),
            accepted={422, 403},
            token=token,
            json_body={"nl": "Cuenta pacientes", "conversation_id": "id con espacios !!!", "page": 1, "page_size": 10},
            skip_if_status={403},
        )

    def test_query_service_guardrails(self) -> None:
        q = self.args.query
        self.check(
            "Query /execute SELECT 1",
            "POST",
            self.join(q, "/execute"),
            accepted={200},
            json_body={"sql": "SELECT 1 AS ok", "page": 1, "page_size": 1, "max_result_window": 10},
        )
        malicious = [
            ("Bloquea DELETE", "DELETE FROM reporting.vw_pacientes"),
            ("Bloquea múltiples sentencias", "SELECT 1; SELECT 2"),
            ("Bloquea pg_sleep", "SELECT pg_sleep(1)"),
            ("Bloquea COPY", "COPY reporting.vw_pacientes TO STDOUT"),
            ("Bloquea SELECT INTO", "SELECT 1 INTO temp smoke_test"),
            ("Bloquea FOR UPDATE", "SELECT * FROM reporting.vw_pacientes FOR UPDATE"),
            ("Bloquea tabla fuera de reporting permitido", "SELECT * FROM cdm_synthea.person LIMIT 1"),
        ]
        for name, sql in malicious:
            self.check(name, "POST", self.join(q, "/execute"), accepted={400, 422}, json_body={"sql": sql, "page": 1, "page_size": 10})

        self.check(
            "Query /execute page_size texto debe fallar validado",
            "POST",
            self.join(q, "/execute"),
            accepted={422},
            json_body={"sql": "SELECT 1", "page": 1, "page_size": "abc"},
        )
        self.check(
            "Query /execute page fuera de rango debe fallar validado",
            "POST",
            self.join(q, "/execute"),
            accepted={422},
            json_body={"sql": "SELECT 1", "page": 100001, "page_size": 10},
        )

    def test_deep_nl_to_sql(self) -> None:
        token = self.token
        assert token
        print("\n--- Prueba profunda NL-to-SQL: puede tardar y depende del traductor/BD ---")
        old_timeout = self.client.timeout
        self.client.timeout = max(old_timeout, self.args.deep_timeout)
        try:
            res = self.check(
                "POST /query NL-to-SQL real",
                "POST",
                self.join(self.args.orchestrator, "/query"),
                accepted={200, 403, 502, 504},
                token=token,
                json_body={"nl": self.args.deep_question, "page": 1, "page_size": 5},
                skip_if_status={403},
                warn_if_status={502, 504},
                detail="502/504 apunta a traductor/BD externa, no a validaciones locales.",
            )
            if res.status == 200 and isinstance(res.json_data, dict):
                rid = res.json_data.get("report_id")
                if rid:
                    self.check("GET reporte generado /meta", "GET", self.join(self.args.orchestrator, f"/reports/{rid}/meta"), accepted={200}, token=token)
                    self.check("GET reporte generado /data", "GET", self.join(self.args.orchestrator, f"/reports/{rid}/data?page=1&page_size=5"), accepted={200}, token=token)
                    self.check("Feedback reporte generado", "POST", self.join(self.args.orchestrator, f"/reports/{rid}/feedback"), accepted={200}, token=token, json_body={"value": "up"})
                    self.check("Export CSV reporte generado", "GET", self.join(self.args.orchestrator, f"/reports/{rid}/export/csv"), accepted={200, 403}, token=token, skip_if_status={403})
        finally:
            self.client.timeout = old_timeout

    def write_reports(self) -> None:
        out_dir = Path(self.args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = out_dir / f"smoke_report_{stamp}.json"
        csv_path = out_dir / f"smoke_report_{stamp}.csv"
        summary = self.summary()
        with json_path.open("w", encoding="utf-8") as f:
            json.dump({"summary": summary, "results": [asdict(r) for r in self.results]}, f, ensure_ascii=False, indent=2)
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["status", "name", "http_status", "elapsed_ms", "detail", "url"])
            writer.writeheader()
            for r in self.results:
                writer.writerow({
                    "status": r.status,
                    "name": r.name,
                    "http_status": r.http_status,
                    "elapsed_ms": r.elapsed_ms,
                    "detail": r.detail,
                    "url": r.url,
                })
        print("\n=== Resumen ===")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print(f"\nReporte JSON: {json_path}")
        print(f"Reporte CSV : {csv_path}")

    def summary(self) -> dict[str, int]:
        counts = {"PASS": 0, "FAIL": 0, "WARN": 0, "SKIP": 0}
        for r in self.results:
            counts[r.status] = counts.get(r.status, 0) + 1
        return counts

    def exit_code(self) -> int:
        return 1 if any(r.status == "FAIL" for r in self.results) else 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Smoke tests para tesis-nl2sql")
    p.add_argument("--identity", default=os.getenv("SMOKE_IDENTITY_URL", "http://127.0.0.1:8002"))
    p.add_argument("--orchestrator", default=os.getenv("SMOKE_ORCHESTRATOR_URL", "http://127.0.0.1:8000"))
    p.add_argument("--query", default=os.getenv("SMOKE_QUERY_URL", "http://127.0.0.1:8003"))
    p.add_argument("--terminology", default=os.getenv("SMOKE_TERMINOLOGY_URL", "http://127.0.0.1:8004"))
    p.add_argument("--translator", default=os.getenv("SMOKE_TRANSLATOR_URL", ""), help="Opcional. URL base del traductor si quieres chequear /healthz.")
    p.add_argument("--admin-user", default=os.getenv("SMOKE_ADMIN_USER", "admin"))
    p.add_argument("--admin-pass", default=os.getenv("SMOKE_ADMIN_PASSWORD", ""))
    p.add_argument("--timeout", type=float, default=float(os.getenv("SMOKE_TIMEOUT", "20")))
    p.add_argument("--output-dir", default=os.getenv("SMOKE_OUTPUT_DIR", "smoke_reports"))
    p.add_argument("--deep-nl", action="store_true", help="Activa prueba real de /query, llama traductor y BD.")
    p.add_argument("--deep-timeout", type=float, default=float(os.getenv("SMOKE_DEEP_TIMEOUT", "240")))
    p.add_argument("--deep-question", default=os.getenv("SMOKE_DEEP_QUESTION", "Cuenta cuántos pacientes hay registrados"))
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args(argv)
    if not args.admin_pass:
        print("ERROR: falta --admin-pass o variable SMOKE_ADMIN_PASSWORD.", file=sys.stderr)
        return args
    return args


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if not args.admin_pass:
        return 2
    try:
        suite = SmokeSuite(args)
        return suite.run()
    except KeyboardInterrupt:
        print("\nInterrumpido por el usuario.")
        return 130
    except Exception:  # noqa: BLE001
        print("\nERROR inesperado en el runner, no necesariamente en tu sistema:")
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
