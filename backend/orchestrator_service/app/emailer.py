from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr

from fastapi import HTTPException

from .config import settings


@dataclass(frozen=True)
class EmailAttachment:
    filename: str
    content: bytes
    maintype: str
    subtype: str


def _from_address() -> str:
    return (settings.SMTP_FROM_EMAIL or settings.SMTP_USERNAME or "").strip()


def email_configured() -> bool:
    return bool(settings.SMTP_HOST and settings.SMTP_PORT and settings.SMTP_USERNAME and settings.SMTP_PASSWORD and _from_address())


def _require_email_config() -> None:
    missing: list[str] = []
    if not settings.SMTP_HOST:
        missing.append("SMTP_HOST")
    if not settings.SMTP_PORT:
        missing.append("SMTP_PORT")
    if not settings.SMTP_USERNAME:
        missing.append("SMTP_USERNAME")
    if not settings.SMTP_PASSWORD:
        missing.append("SMTP_PASSWORD")
    if not _from_address():
        missing.append("SMTP_FROM_EMAIL")

    if missing:
        raise HTTPException(
            503,
            "El envío de correo no está configurado. Faltan: " + ", ".join(missing),
        )


def send_email_with_attachments(
    *,
    to_email: str,
    subject: str,
    body: str,
    attachments: list[EmailAttachment],
) -> None:
    _require_email_config()

    clean_to = (to_email or "").strip()
    if not clean_to:
        raise HTTPException(400, "Tu usuario no tiene correo electrónico configurado")
    if not attachments:
        raise HTTPException(400, "Selecciona al menos un formato para enviar")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((settings.SMTP_FROM_NAME or "empresa REPORTS", _from_address()))
    msg["To"] = clean_to
    msg.set_content(body)

    for item in attachments:
        msg.add_attachment(
            item.content,
            maintype=item.maintype,
            subtype=item.subtype,
            filename=item.filename,
        )

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=settings.EMAIL_TIMEOUT_SECONDS) as smtp:
            if settings.SMTP_USE_TLS:
                smtp.starttls()
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError as exc:
        raise HTTPException(
            503,
            "No se pudo autenticar con el servidor SMTP. Revisa el usuario y la contraseña de aplicación.",
        ) from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise HTTPException(503, f"No se pudo enviar el correo: {exc}") from exc
