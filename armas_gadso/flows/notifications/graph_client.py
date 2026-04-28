from __future__ import annotations

import base64
import json
import urllib.parse
import urllib.request
from pathlib import Path


def extract_graph_error(detail: str) -> tuple[str, str]:
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


def classify_graph_failure(status_code: int, detail: str) -> tuple[str, str]:
    error_code, message = extract_graph_error(detail)
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


def graph_token(config: dict) -> str:
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


def attachment_from_path(file_path: Path) -> dict:
    content = base64.b64encode(file_path.read_bytes()).decode("ascii")
    return {
        "@odata.type": "#microsoft.graph.fileAttachment",
        "name": file_path.name,
        "contentType": "image/png",
        "contentBytes": content,
    }


def send_mail(config: dict, subject: str, html_body: str, attachment_paths: list[Path]) -> None:
    token = graph_token(config)
    message = {
        "subject": subject,
        "body": {
            "contentType": "HTML",
            "content": html_body,
        },
        "toRecipients": [
            {"emailAddress": {"address": address}}
            for address in config["to"]
        ],
        "ccRecipients": [
            {"emailAddress": {"address": address}}
            for address in config["cc"]
        ],
    }
    if attachment_paths:
        message["attachments"] = [attachment_from_path(path) for path in attachment_paths]

    payload = {
        "message": message,
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
