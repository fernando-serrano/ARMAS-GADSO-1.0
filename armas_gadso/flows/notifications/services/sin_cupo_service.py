from __future__ import annotations

import json
import urllib.error
from datetime import datetime
from pathlib import Path

from ..builders.sin_cupo import (
    build_html_body,
    build_multirun_html_body,
    build_multirun_subject,
    build_subject,
    select_representative_attachments,
)
from ..graph_client import classify_graph_failure, send_mail
from ..mail_config import (
    graph_mail_enabled,
    is_multiworker_child,
    load_mail_config,
    mask_secret,
    step_1_mail_enabled,
    validate_mail_config,
)
from ..mail_logging import mail_context_summary
from ..manifest_store import load_manifest_events, write_manifest_event


_STEP1_CAPTURE_STATE: dict[str, dict] = {}


def _step1_key(registro: dict, hora_objetivo: str) -> str:
    idx_excel = str(registro.get("idx_excel", registro.get("_excel_index", "")) or "").strip()
    fecha = str(registro.get("fecha", "") or "").strip()
    sede = str(registro.get("sede", "") or "").strip()
    hora = str(hora_objetivo or registro.get("hora_rango", "") or "").strip()
    return "|".join([idx_excel, fecha, sede, hora])


def _remember_step1_capture(registro: dict, screenshot_path: Path | None, hora_objetivo: str, reason: str) -> dict:
    key = _step1_key(registro, hora_objetivo)
    state = _STEP1_CAPTURE_STATE.setdefault(
        key,
        {
            "registro": dict(registro),
            "hora_objetivo": hora_objetivo,
            "tabla_inicial": None,
            "sin_cupo": None,
            "sent": False,
        },
    )
    state["registro"] = dict(registro)
    state["hora_objetivo"] = hora_objetivo
    if reason == "tabla_inicial":
        state["tabla_inicial"] = screenshot_path
    elif str(reason).startswith("sin_cupo_"):
        state["sin_cupo"] = screenshot_path
    return state


def _is_step1_no_cupo_reason(reason: str) -> bool:
    return str(reason or "").startswith("sin_cupo_")


def _send_single_event_mail(config: dict, state: dict, attachment_paths: list[Path]) -> None:
    subject = build_subject(config, state["registro"], state["hora_objetivo"])
    body = build_html_body(state["registro"], state["hora_objetivo"])
    print(
        "   [INFO] Correo Graph preparado | "
        f"{mail_context_summary(config, attachment_paths)} | "
        f"client_id={config['client_id']} | "
        f"tenant_id={config['tenant_id']} | "
        f"secret={mask_secret(config['client_secret'])}"
    )
    send_mail(config, subject, body, attachment_paths)
    state["sent"] = True
    print(
        "   [INFO] Correo Graph enviado [SEND_OK] | "
        f"{mail_context_summary(config, attachment_paths)}"
    )


def _persist_multiworker_event(state: dict, attachment_paths: list[Path]) -> None:
    event = {
        "key": _step1_key(state["registro"], state["hora_objetivo"]),
        "registro": state["registro"],
        "hora_objetivo": state["hora_objetivo"],
        "attachments": [str(path) for path in attachment_paths],
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    write_manifest_event(event)
    state["sent"] = True
    print(
        "   [INFO] Correo Graph diferido [MULTIWORKER_DEFERRED] | "
        f"attachments={', '.join(path.name for path in attachment_paths) or '-'}"
    )


def register_step_1_capture(registro: dict, screenshot_path: Path | None, hora_objetivo: str, reason: str) -> None:
    if not graph_mail_enabled() or not step_1_mail_enabled():
        return

    state = _remember_step1_capture(registro, screenshot_path, hora_objetivo, reason)
    if not _is_step1_no_cupo_reason(reason):
        return
    if state.get("sent"):
        return

    config = load_mail_config()
    config_error = validate_mail_config(config)
    if config_error:
        print(f"   [WARNING] Correo Graph omitido [CONFIG_INVALID]: {config_error}")
        return

    attachment_paths = []
    for candidate in [state.get("tabla_inicial"), state.get("sin_cupo")]:
        if isinstance(candidate, Path) and candidate.exists():
            attachment_paths.append(candidate)

    try:
        if is_multiworker_child():
            if not attachment_paths:
                print("   [WARNING] Correo Graph sin adjuntos [NO_ATTACHMENTS]: se diferira el caso sin evidencia")
            _persist_multiworker_event(state, attachment_paths)
        else:
            if not attachment_paths:
                print("   [WARNING] Correo Graph sin adjuntos [NO_ATTACHMENTS]: se enviara el caso sin evidencia")
            _send_single_event_mail(config, state, attachment_paths)
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            detail = str(exc)
        error_tag, friendly_message = classify_graph_failure(exc.code, detail)
        print(
            "   [WARNING] Fallo envio Graph "
            f"[{error_tag}] (HTTP {exc.code}) | "
            f"{friendly_message} | "
            f"{mail_context_summary(config, attachment_paths)}"
        )
        print(f"   [WARNING] Fallo envio Graph detalle bruto: {detail}")
    except Exception as exc:
        print(
            "   [WARNING] Fallo envio Graph [UNEXPECTED_ERROR] | "
            f"{exc} | {mail_context_summary(config, attachment_paths)}"
        )


def send_multirun_step_1_summary(manifest_paths: list[str]) -> None:
    if not graph_mail_enabled() or not step_1_mail_enabled():
        return

    config = load_mail_config()
    config_error = validate_mail_config(config)
    if config_error:
        print(f"[WARNING] Correo Graph consolidado omitido [CONFIG_INVALID]: {config_error}")
        return

    try:
        events_by_key = load_manifest_events(manifest_paths)
    except Exception as exc:
        print(f"[WARNING] No se pudo leer manifiestos Graph consolidados: {exc}")
        return

    if not events_by_key:
        print("[INFO] Correo Graph consolidado omitido [NO_EVENTS]: no hay eventos step_1 para resumir")
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
        attachments = [str(item) for item in (event.get("attachments", []) or [])]
        sin_cupo_attachment = next((item for item in attachments if "sin_cupo_" in item.lower()), "")
        tabla_inicial_attachment = next((item for item in attachments if "tabla_inicial" in item.lower()), "")
        normalized = dict(event)
        normalized["sin_cupo_attachment"] = sin_cupo_attachment
        normalized["tabla_inicial_attachment"] = tabla_inicial_attachment
        normalized["has_evidence"] = bool(sin_cupo_attachment or tabla_inicial_attachment)
        normalized_events.append(normalized)

    attachment_paths = select_representative_attachments(normalized_events)

    try:
        subject = build_multirun_subject(config, len(normalized_events))
        body = build_multirun_html_body(normalized_events)
        print(
            "[INFO] Correo Graph consolidado preparado | "
            f"{mail_context_summary(config, attachment_paths)} | "
            f"casos={len(normalized_events)} | "
            f"client_id={config['client_id']} | "
            f"tenant_id={config['tenant_id']} | "
            f"secret={mask_secret(config['client_secret'])}"
        )
        send_mail(config, subject, body, attachment_paths)
        print(
            "[INFO] Correo Graph consolidado enviado [SEND_OK] | "
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
            "[WARNING] Fallo envio Graph consolidado "
            f"[{error_tag}] (HTTP {exc.code}) | "
            f"{friendly_message} | "
            f"{mail_context_summary(config, attachment_paths)} | casos={len(normalized_events)}"
        )
        print(f"[WARNING] Fallo envio Graph consolidado detalle bruto: {detail}")
    except Exception as exc:
        print(
            "[WARNING] Fallo envio Graph consolidado [UNEXPECTED_ERROR] | "
            f"{exc} | {mail_context_summary(config, attachment_paths)} | casos={len(normalized_events)}"
        )
