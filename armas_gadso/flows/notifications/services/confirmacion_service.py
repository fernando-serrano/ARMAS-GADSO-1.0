from __future__ import annotations

import urllib.error
from datetime import datetime
from pathlib import Path

from ..builders.confirmacion import (
    build_html_body,
    build_multirun_html_body,
    build_multirun_subject,
    build_subject,
    select_confirmation_attachments,
)
from ..graph_client import classify_graph_failure, send_mail
from ..mail_config import (
    confirmation_mail_enabled,
    graph_mail_enabled,
    is_multiworker_child,
    load_mail_config,
    mask_secret,
    validate_mail_config,
)
from ..mail_logging import mail_context_summary
from ..manifest_store import load_manifest_events, write_manifest_event


def _confirmation_key(registro: dict, hora_objetivo: str) -> str:
    idx_excel = str(registro.get("idx_excel", registro.get("_excel_index", "")) or "").strip()
    fecha = str(registro.get("fecha", "") or "").strip()
    sede = str(registro.get("sede", "") or "").strip()
    hora = str(hora_objetivo or registro.get("hora_rango", "") or "").strip()
    return "|".join([idx_excel, fecha, sede, hora])


def _persist_multiworker_event(registro: dict, hora_objetivo: str, screenshot_path: Path | None) -> None:
    event = {
        "key": _confirmation_key(registro, hora_objetivo),
        "registro": dict(registro),
        "hora_objetivo": hora_objetivo,
        "attachment": str(screenshot_path) if isinstance(screenshot_path, Path) else "",
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    write_manifest_event(event, env_name="GRAPH_CONFIRMATION_MANIFEST_PATH")
    print(
        "   [INFO] Correo Graph confirmacion diferido [MULTIWORKER_DEFERRED] | "
        f"attachments={screenshot_path.name if isinstance(screenshot_path, Path) else '-'}"
    )


def register_confirmation_capture(registro: dict, screenshot_path: Path | None, hora_objetivo: str) -> None:
    if not graph_mail_enabled() or not confirmation_mail_enabled():
        return

    config = load_mail_config()
    config_error = validate_mail_config(config)
    if config_error:
        print(f"   [WARNING] Correo Graph confirmacion omitido [CONFIG_INVALID]: {config_error}")
        return

    attachment_paths = []
    if isinstance(screenshot_path, Path) and screenshot_path.exists():
        attachment_paths.append(screenshot_path)

    try:
        if is_multiworker_child():
            if not attachment_paths:
                print("   [WARNING] Correo Graph confirmacion sin adjuntos [NO_ATTACHMENTS]: se diferira el caso sin evidencia")
            _persist_multiworker_event(registro, hora_objetivo, screenshot_path)
            return

        subject = build_subject(config, registro, hora_objetivo)
        body = build_html_body(registro, hora_objetivo, bool(attachment_paths))
        print(
            "   [INFO] Correo Graph confirmacion preparado | "
            f"{mail_context_summary(config, attachment_paths)} | "
            f"client_id={config['client_id']} | "
            f"tenant_id={config['tenant_id']} | "
            f"secret={mask_secret(config['client_secret'])}"
        )
        send_mail(config, subject, body, attachment_paths)
        print(
            "   [INFO] Correo Graph confirmacion enviado [SEND_OK] | "
            f"{mail_context_summary(config, attachment_paths)}"
        )
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            detail = str(exc)
        error_tag, friendly_message = classify_graph_failure(exc.code, detail)
        print(
            "   [WARNING] Fallo envio Graph confirmacion "
            f"[{error_tag}] (HTTP {exc.code}) | "
            f"{friendly_message} | "
            f"{mail_context_summary(config, attachment_paths)}"
        )
        print(f"   [WARNING] Fallo envio Graph confirmacion detalle bruto: {detail}")
    except Exception as exc:
        print(
            "   [WARNING] Fallo envio Graph confirmacion [UNEXPECTED_ERROR] | "
            f"{exc} | {mail_context_summary(config, attachment_paths)}"
        )


def send_multirun_confirmation_summary(manifest_paths: list[str]) -> None:
    if not graph_mail_enabled() or not confirmation_mail_enabled():
        return

    config = load_mail_config()
    config_error = validate_mail_config(config)
    if config_error:
        print(f"[WARNING] Correo Graph confirmacion consolidado omitido [CONFIG_INVALID]: {config_error}")
        return

    try:
        events_by_key = load_manifest_events(manifest_paths)
    except Exception as exc:
        print(f"[WARNING] No se pudo leer manifiestos Graph de confirmacion: {exc}")
        return

    if not events_by_key:
        print("[INFO] Correo Graph confirmacion consolidado omitido [NO_EVENTS]: no hay confirmaciones para resumir")
        return

    ordered_events = sorted(
        events_by_key.values(),
        key=lambda event: (
            str(event.get("registro", {}).get("fecha", "") or ""),
            str(event.get("hora_objetivo", "") or ""),
            str(event.get("registro", {}).get("idx_excel", event.get("registro", {}).get("_excel_index", "")) or ""),
        ),
    )

    normalized_events = []
    for event in ordered_events:
        normalized = dict(event)
        normalized["has_evidence"] = bool(str(event.get("attachment", "") or "").strip())
        normalized_events.append(normalized)

    attachment_paths = select_confirmation_attachments(normalized_events)

    try:
        subject = build_multirun_subject(config, len(normalized_events))
        body = build_multirun_html_body(normalized_events)
        print(
            "[INFO] Correo Graph confirmacion consolidado preparado | "
            f"{mail_context_summary(config, attachment_paths)} | "
            f"casos={len(normalized_events)} | "
            f"client_id={config['client_id']} | "
            f"tenant_id={config['tenant_id']} | "
            f"secret={mask_secret(config['client_secret'])}"
        )
        send_mail(config, subject, body, attachment_paths)
        print(
            "[INFO] Correo Graph confirmacion consolidado enviado [SEND_OK] | "
            f"{mail_context_summary(config, attachment_paths)} | casos={len(normalized_events)}"
        )
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            detail = str(exc)
        error_tag, friendly_message = classify_graph_failure(exc.code, detail)
        print(
            "[WARNING] Fallo envio Graph confirmacion consolidado "
            f"[{error_tag}] (HTTP {exc.code}) | "
            f"{friendly_message} | "
            f"{mail_context_summary(config, attachment_paths)} | casos={len(normalized_events)}"
        )
        print(f"[WARNING] Fallo envio Graph confirmacion consolidado detalle bruto: {detail}")
    except Exception as exc:
        print(
            "[WARNING] Fallo envio Graph confirmacion consolidado [UNEXPECTED_ERROR] | "
            f"{exc} | {mail_context_summary(config, attachment_paths)} | casos={len(normalized_events)}"
        )
