from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def _env_bool(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "1" if default else "0") or ("1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "si", "sí"}


def _split_addresses(value: str) -> list[str]:
    items = []
    for part in str(value or "").replace(";", ",").split(","):
        address = part.strip()
        if address:
            items.append(address)
    return items


def _graph_mail_enabled() -> bool:
    return _env_bool("MS_GRAPH_MAIL_ENABLED", default=False)


def _step_1_mail_enabled() -> bool:
    return _env_bool("MS_GRAPH_MAIL_STEP1_ENABLED", default=False)


def _load_mail_config() -> dict:
    return {
        "tenant_id": str(os.getenv("MS_GRAPH_TENANT_ID", "") or "").strip(),
        "client_id": str(os.getenv("MS_GRAPH_CLIENT_ID", "") or "").strip(),
        "client_secret": str(os.getenv("MS_GRAPH_CLIENT_SECRET", "") or "").strip(),
        "sender": str(os.getenv("MS_GRAPH_SENDER", "") or "").strip(),
        "to": _split_addresses(os.getenv("MS_GRAPH_TO", "")),
        "subject_prefix": str(os.getenv("MS_GRAPH_SUBJECT_PREFIX", "ARMAS-GADSO") or "ARMAS-GADSO").strip(),
    }


def _validate_mail_config(config: dict) -> str | None:
    if not config["tenant_id"]:
        return "falta MS_GRAPH_TENANT_ID"
    if not config["client_id"]:
        return "falta MS_GRAPH_CLIENT_ID"
    if not config["client_secret"]:
        return "falta MS_GRAPH_CLIENT_SECRET"
    if not config["sender"]:
        return "falta MS_GRAPH_SENDER"
    if not config["to"]:
        return "falta MS_GRAPH_TO"
    return None


def _mask_secret(secret: str) -> str:
    value = str(secret or "")
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _extract_graph_error(detail: str) -> tuple[str, str]:
    raw = str(detail or "").strip()
    if not raw:
        return "", ""

    try:
        data = json.loads(raw)
    except Exception:
        return "", raw

    if isinstance(data, dict):
        if isinstance(data.get("error"), dict):
            error_code = str(data["error"].get("code", "") or "").strip()
            message = str(data["error"].get("message", "") or "").strip()
            return error_code, message
        error_code = str(data.get("error", "") or "").strip()
        message = str(data.get("error_description", "") or "").strip()
        return error_code, message

    return "", raw


def _classify_graph_failure(status_code: int, detail: str) -> tuple[str, str]:
    error_code, message = _extract_graph_error(detail)
    message_lower = message.lower()
    detail_lower = str(detail or "").lower()

    if status_code == 401 and (error_code == "invalid_client" or "invalid client secret" in message_lower):
        return (
            "AUTH_INVALID_CLIENT_SECRET",
            "Azure rechazo el client secret. Verifica que MS_GRAPH_CLIENT_SECRET use el Value del secreto y no el Secret ID.",
        )
    if status_code == 401:
        return (
            "AUTH_UNAUTHORIZED",
            "Azure rechazo la autenticacion de la aplicacion. Revisa tenant, client id y client secret.",
        )
    if status_code == 404 and (error_code == "ErrorInvalidUser" or "requested user" in message_lower):
        return (
            "SENDER_INVALID_USER",
            "Graph no reconoce el buzon remitente. Verifica MS_GRAPH_SENDER y que exista en el tenant con Exchange Online.",
        )
    if status_code == 403 and (error_code == "ErrorAccessDenied" or "access is denied" in message_lower):
        return (
            "SEND_ACCESS_DENIED",
            "La app autentica, pero no tiene permiso efectivo para enviar. Falta Mail.Send como Application permission, admin consent o autorizacion sobre el buzon.",
        )
    if "mail.send" in detail_lower or "consent" in message_lower:
        return (
            "SEND_PERMISSION_MISSING",
            "Graph reporta un problema de permisos. Revisa Mail.Send, admin consent y politicas de acceso al buzon.",
        )
    return (
        "GRAPH_REQUEST_FAILED",
        "Graph devolvio un error no clasificado. Revisa el detalle bruto para el diagnostico fino.",
    )


def _graph_token(config: dict) -> str:
    token_url = f"https://login.microsoftonline.com/{config['tenant_id']}/oauth2/v2.0/token"
    payload = urllib.parse.urlencode(
        {
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        }
    ).encode("utf-8")
    request = urllib.request.Request(token_url, data=payload, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.loads(response.read().decode("utf-8"))
    token = str(body.get("access_token", "") or "").strip()
    if not token:
        raise Exception("Microsoft Graph no devolvio access_token")
    return token


def _attachment_from_path(file_path: Path) -> dict:
    content = base64.b64encode(file_path.read_bytes()).decode("ascii")
    return {
        "@odata.type": "#microsoft.graph.fileAttachment",
        "name": file_path.name,
        "contentType": "image/png",
        "contentBytes": content,
    }


def _build_subject(config: dict, registro: dict, hora_objetivo: str) -> str:
    idx_excel = registro.get("idx_excel", registro.get("_excel_index", ""))
    fecha = str(registro.get("fecha", "") or "").strip()
    sede = str(registro.get("sede", "") or "").strip()
    hora = str(hora_objetivo or registro.get("hora_rango", "") or "").strip()
    pieces = [config["subject_prefix"], "Disponibilidad de cupos"]
    if idx_excel != "":
        pieces.append(f"idx={idx_excel}")
    if fecha:
        pieces.append(fecha)
    if sede:
        pieces.append(sede)
    if hora:
        pieces.append(hora)
    return " | ".join(pieces)


def _build_html_body(registro: dict, hora_objetivo: str) -> str:
    fecha = str(registro.get("fecha", "") or "").strip()
    sede = str(registro.get("sede", "") or "").strip()
    hora = str(hora_objetivo or registro.get("hora_rango", "") or "").strip()
    idx_excel = str(registro.get("idx_excel", registro.get("_excel_index", "")) or "").strip()

    details = []
    if idx_excel:
        details.append(f"<li><b>Indice:</b> {idx_excel}</li>")
    if sede:
        details.append(f"<li><b>Sede:</b> {sede}</li>")
    if fecha:
        details.append(f"<li><b>Fecha:</b> {fecha}</li>")
    if hora:
        details.append(f"<li><b>Hora objetivo:</b> {hora}</li>")

    detail_block = f"<ul>{''.join(details)}</ul>" if details else ""
    return (
        "<p>La disponibilidad de cupos se sintetiza en la siguiente tabla:</p>"
        f"{detail_block}"
        "<p>Se adjunta la captura generada por la automatizacion.</p>"
    )


def _send_mail(config: dict, subject: str, html_body: str, screenshot_path: Path) -> None:
    token = _graph_token(config)
    payload = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "HTML",
                "content": html_body,
            },
            "toRecipients": [
                {"emailAddress": {"address": address}}
                for address in config["to"]
            ],
            "attachments": [_attachment_from_path(screenshot_path)],
        },
        "saveToSentItems": True,
    }

    sender = urllib.parse.quote(config["sender"])
    url = f"https://graph.microsoft.com/v1.0/users/{sender}/sendMail"
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST")
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Content-Type", "application/json")

    with urllib.request.urlopen(request, timeout=60) as response:
        status_code = getattr(response, "status", 0) or 0
    if int(status_code) != 202:
        raise Exception(f"Microsoft Graph devolvio estado inesperado: {status_code}")


def _mail_context_summary(config: dict, screenshot_path: Path) -> str:
    return (
        f"sender={config['sender']} | "
        f"to={', '.join(config['to'])} | "
        f"attachment={screenshot_path.name}"
    )


def notify_step_1_table_capture(registro: dict, screenshot_path: Path | None, hora_objetivo: str, reason: str) -> None:
    if reason != "tabla_inicial":
        return
    if not _graph_mail_enabled() or not _step_1_mail_enabled():
        return
    if screenshot_path is None:
        print("   [WARNING] Correo Graph omitido: la captura de step 1 no fue generada")
        return
    if not screenshot_path.exists():
        print(f"   [WARNING] Correo Graph omitido: no existe el adjunto {screenshot_path}")
        return

    config = _load_mail_config()
    config_error = _validate_mail_config(config)
    if config_error:
        print(f"   [WARNING] Correo Graph omitido [CONFIG_INVALID]: {config_error}")
        return

    try:
        subject = _build_subject(config, registro, hora_objetivo)
        body = _build_html_body(registro, hora_objetivo)
        print(
            "   [INFO] Correo Graph preparado | "
            f"{_mail_context_summary(config, screenshot_path)} | "
            f"client_id={config['client_id']} | "
            f"tenant_id={config['tenant_id']} | "
            f"secret={_mask_secret(config['client_secret'])}"
        )
        _send_mail(config, subject, body, screenshot_path)
        print(
            "   [INFO] Correo Graph enviado [SEND_OK] | "
            f"{_mail_context_summary(config, screenshot_path)}"
        )
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            detail = str(exc)
        error_tag, friendly_message = _classify_graph_failure(exc.code, detail)
        print(
            "   [WARNING] Fallo envio Graph "
            f"[{error_tag}] (HTTP {exc.code}) | "
            f"{friendly_message} | "
            f"{_mail_context_summary(config, screenshot_path)}"
        )
        print(f"   [WARNING] Fallo envio Graph detalle bruto: {detail}")
    except Exception as exc:
        print(
            "   [WARNING] Fallo envio Graph [UNEXPECTED_ERROR] | "
            f"{exc} | {_mail_context_summary(config, screenshot_path)}"
        )
