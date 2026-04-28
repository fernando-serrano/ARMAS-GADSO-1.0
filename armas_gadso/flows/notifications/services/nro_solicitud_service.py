from __future__ import annotations

import urllib.error
from datetime import datetime
from pathlib import Path

from ..builders.nro_solicitud import build_html_body, build_subject, select_attachments
from ..graph_client import classify_graph_failure, send_mail
from ..mail_config import (
    graph_mail_enabled,
    is_multiworker_child,
    load_mail_config,
    mask_secret,
    nro_solicitud_mail_enabled,
    validate_mail_config,
)
from ..mail_logging import mail_context_summary
from ..manifest_store import load_manifest_events, write_manifest_event


def _event_key(registro: dict, hora_objetivo: str) -> str:
    idx_excel = str(registro.get("idx_excel", registro.get("_excel_index", "")) or "").strip()
    fecha = str(registro.get("fecha", "") or "").strip()
    sede = str(registro.get("sede", "") or "").strip()
    hora = str(hora_objetivo or registro.get("hora_rango", "") or "").strip()
    return "|".join([idx_excel, fecha, sede, hora])


def register_nro_solicitud_terminal(registro: dict, screenshot_path: Path | None, hora_objetivo: str) -> None:
    if not graph_mail_enabled() or not nro_solicitud_mail_enabled():
        return

    config = load_mail_config()
    config_error = validate_mail_config(config)
    if config_error:
        print(f"   [WARNING] Correo Graph nro_solicitud omitido [CONFIG_INVALID]: {config_error}")
        return

    event = {
        "key": _event_key(registro, hora_objetivo),
        "registro": dict(registro),
        "hora_objetivo": str(hora_objetivo or registro.get("hora_rango", "") or "").strip(),
        "attachment": str(screenshot_path) if isinstance(screenshot_path, Path) else "",
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    events = [dict(event)]
    events[0]["has_evidence"] = bool(event["attachment"])
    attachment_paths = select_attachments(events)

    try:
        if is_multiworker_child():
            write_manifest_event(event, env_name="GRAPH_NRO_SOLICITUD_MANIFEST_PATH")
            print(
                "   [INFO] Correo Graph nro_solicitud diferido [MULTIWORKER_DEFERRED] | "
                f"attachments={screenshot_path.name if isinstance(screenshot_path, Path) else '-'}"
            )
            return

        subject = build_subject(config, len(events))
        body = build_html_body(events)
        print(
            "   [INFO] Correo Graph nro_solicitud preparado | "
            f"{mail_context_summary(config, attachment_paths)} | "
            f"client_id={config['client_id']} | "
            f"tenant_id={config['tenant_id']} | "
            f"secret={mask_secret(config['client_secret'])}"
        )
        send_mail(config, subject, body, attachment_paths)
        print(
            "   [INFO] Correo Graph nro_solicitud enviado [SEND_OK] | "
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
            "   [WARNING] Fallo envio Graph nro_solicitud "
            f"[{error_tag}] (HTTP {exc.code}) | "
            f"{friendly_message} | "
            f"{mail_context_summary(config, attachment_paths)}"
        )
        print(f"   [WARNING] Fallo envio Graph nro_solicitud detalle bruto: {detail}")
    except Exception as exc:
        print(
            "   [WARNING] Fallo envio Graph nro_solicitud [UNEXPECTED_ERROR] | "
            f"{exc} | {mail_context_summary(config, attachment_paths)}"
        )


def send_multirun_nro_solicitud_summary(manifest_paths: list[str]) -> None:
    if not graph_mail_enabled() or not nro_solicitud_mail_enabled():
        return

    config = load_mail_config()
    config_error = validate_mail_config(config)
    if config_error:
        print(f"[WARNING] Correo Graph nro_solicitud consolidado omitido [CONFIG_INVALID]: {config_error}")
        return

    try:
        events_by_key = load_manifest_events(manifest_paths)
    except Exception as exc:
        print(f"[WARNING] No se pudo leer manifiestos Graph de nro_solicitud: {exc}")
        return

    if not events_by_key:
        print("[INFO] Correo Graph nro_solicitud consolidado omitido [NO_EVENTS]: no hay casos para resumir")
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

    attachment_paths = select_attachments(normalized_events)

    try:
        subject = build_subject(config, len(normalized_events))
        body = build_html_body(normalized_events)
        print(
            "[INFO] Correo Graph nro_solicitud consolidado preparado | "
            f"{mail_context_summary(config, attachment_paths)} | "
            f"casos={len(normalized_events)} | "
            f"client_id={config['client_id']} | "
            f"tenant_id={config['tenant_id']} | "
            f"secret={mask_secret(config['client_secret'])}"
        )
        send_mail(config, subject, body, attachment_paths)
        print(
            "[INFO] Correo Graph nro_solicitud consolidado enviado [SEND_OK] | "
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
            "[WARNING] Fallo envio Graph nro_solicitud consolidado "
            f"[{error_tag}] (HTTP {exc.code}) | "
            f"{friendly_message} | "
            f"{mail_context_summary(config, attachment_paths)} | casos={len(normalized_events)}"
        )
        print(f"[WARNING] Fallo envio Graph nro_solicitud consolidado detalle bruto: {detail}")
    except Exception as exc:
        print(
            "[WARNING] Fallo envio Graph nro_solicitud consolidado [UNEXPECTED_ERROR] | "
            f"{exc} | {mail_context_summary(config, attachment_paths)} | casos={len(normalized_events)}"
        )
