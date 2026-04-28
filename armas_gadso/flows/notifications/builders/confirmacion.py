from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .sin_cupo import case_label


def build_subject(config: dict, registro: dict, hora_objetivo: str) -> str:
    fecha = str(registro.get("fecha", "") or "").strip()
    sede = str(registro.get("sede", "") or "").strip()
    hora = str(hora_objetivo or registro.get("hora_rango", "") or "").strip()
    pieces = [config["subject_prefix"], "Vacantes reservadas"]
    if fecha:
        pieces.append(fecha)
    if sede:
        pieces.append(sede)
    if hora:
        pieces.append(hora)
    return " | ".join(pieces)


def build_multirun_subject(config: dict, total_cases: int) -> str:
    pieces = [config["subject_prefix"], "Vacantes reservadas"]
    if total_cases > 1:
        pieces.append(f"{total_cases} casos")
    return " | ".join(pieces)


def _format_fecha_larga(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%d/%m/%Y")
        except Exception:
            pass
    return raw


def _hora_rango(hora_objetivo: str, registro: dict) -> str:
    return str(hora_objetivo or registro.get("hora_rango", "") or "").strip()


def _intro_suffix(events: list[dict]) -> str:
    fechas = []
    for event in events:
        fecha = _format_fecha_larga(str(event.get("registro", {}).get("fecha", "") or "").strip())
        if fecha and fecha not in fechas:
            fechas.append(fecha)
    if len(fechas) == 1:
        return f" para el {fechas[0]}"
    if len(fechas) > 1:
        return " para las fechas objetivo detalladas"
    return ""


def build_html_body(registro: dict, hora_objetivo: str, has_evidence: bool) -> str:
    now = datetime.now()
    today = now.strftime("%d/%m/%Y")
    now_hhmmss = now.strftime("%H:%M:%S")
    fecha_objetivo = _format_fecha_larga(str(registro.get("fecha", "") or "").strip())
    sede = str(registro.get("sede", "") or "").strip()
    hora = _hora_rango(hora_objetivo, registro)
    evidencia = "Adjunta" if has_evidence else "No disponible"
    highlight_style = "background:#fff3b0;padding:2px 6px;border-radius:4px;"

    row = (
        "<tr>"
        f"<td style='border:1px solid #d0d7de;padding:8px;'>{case_label(registro)}</td>"
        f"<td style='border:1px solid #d0d7de;padding:8px;'>{sede}</td>"
        f"<td style='border:1px solid #d0d7de;padding:8px;'>{fecha_objetivo}</td>"
        f"<td style='border:1px solid #d0d7de;padding:8px;'>{hora}</td>"
        f"<td style='border:1px solid #d0d7de;padding:8px;'>{evidencia}</td>"
        "</tr>"
    )
    evidence_line = (
        "<p>Se adjunta la captura final de confirmacion.</p>"
        if has_evidence
        else "<p>No se genero evidencia adjunta para este caso.</p>"
    )
    return (
        "<p>Buen dia &#129302;</p>"
        f"<p><span style='font-weight:700;'>Vacantes reservadas</span> el dia "
        f"<span style='{highlight_style}'>{today}</span> a las "
        f"<span style='{highlight_style}'>{now_hhmmss} hros</span>"
        f"{f' para el {fecha_objetivo}' if fecha_objetivo else ''}.</p>"
        "<p>Caso confirmado:</p>"
        "<table style='border-collapse:collapse;border:1px solid #d0d7de;'>"
        "<thead><tr>"
        "<th style='border:1px solid #d0d7de;padding:8px;background:#f6f8fa;text-align:left;'>DNI</th>"
        "<th style='border:1px solid #d0d7de;padding:8px;background:#f6f8fa;text-align:left;'>Sede</th>"
        "<th style='border:1px solid #d0d7de;padding:8px;background:#f6f8fa;text-align:left;'>Fecha objetivo</th>"
        "<th style='border:1px solid #d0d7de;padding:8px;background:#f6f8fa;text-align:left;'>Hora objetivo</th>"
        "<th style='border:1px solid #d0d7de;padding:8px;background:#f6f8fa;text-align:left;'>Evidencia</th>"
        f"</tr></thead><tbody>{row}</tbody></table>"
        f"{evidence_line}"
    )


def build_multirun_html_body(events: list[dict]) -> str:
    now = datetime.now()
    today = now.strftime("%d/%m/%Y")
    now_hhmmss = now.strftime("%H:%M:%S")
    highlight_style = "background:#fff3b0;padding:2px 6px;border-radius:4px;"

    rows = []
    for event in events:
        registro = event["registro"]
        sede = str(registro.get("sede", "") or "").strip()
        fecha_objetivo = _format_fecha_larga(str(registro.get("fecha", "") or "").strip())
        hora = _hora_rango(str(event.get("hora_objetivo", "") or ""), registro)
        evidencia = "Adjunta" if event.get("has_evidence") else "No disponible"
        rows.append(
            "<tr>"
            f"<td style='border:1px solid #d0d7de;padding:8px;'>{case_label(registro)}</td>"
            f"<td style='border:1px solid #d0d7de;padding:8px;'>{sede}</td>"
            f"<td style='border:1px solid #d0d7de;padding:8px;'>{fecha_objetivo}</td>"
            f"<td style='border:1px solid #d0d7de;padding:8px;'>{hora}</td>"
            f"<td style='border:1px solid #d0d7de;padding:8px;'>{evidencia}</td>"
            "</tr>"
        )

    intro_suffix = _intro_suffix(events)
    evidence_line = (
        "<p>Se adjuntan las capturas finales de confirmacion disponibles por caso.</p>"
        if any(event.get("has_evidence") for event in events)
        else "<p>No se generaron evidencias adjuntas para los casos confirmados.</p>"
    )
    label = "Caso confirmado:" if len(events) == 1 else "Casos confirmados:"
    return (
        "<p>Buen dia &#129302;</p>"
        f"<p><span style='font-weight:700;'>Vacantes reservadas</span> el dia "
        f"<span style='{highlight_style}'>{today}</span> a las "
        f"<span style='{highlight_style}'>{now_hhmmss} hros</span>{intro_suffix}.</p>"
        f"<p>{label}</p>"
        "<table style='border-collapse:collapse;border:1px solid #d0d7de;'>"
        "<thead><tr>"
        "<th style='border:1px solid #d0d7de;padding:8px;background:#f6f8fa;text-align:left;'>DNI</th>"
        "<th style='border:1px solid #d0d7de;padding:8px;background:#f6f8fa;text-align:left;'>Sede</th>"
        "<th style='border:1px solid #d0d7de;padding:8px;background:#f6f8fa;text-align:left;'>Fecha objetivo</th>"
        "<th style='border:1px solid #d0d7de;padding:8px;background:#f6f8fa;text-align:left;'>Hora objetivo</th>"
        "<th style='border:1px solid #d0d7de;padding:8px;background:#f6f8fa;text-align:left;'>Evidencia</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
        f"{evidence_line}"
    )


def select_confirmation_attachments(events: list[dict]) -> list[Path]:
    attachments: list[Path] = []
    seen = set()
    for event in events:
        candidate = str(event.get("attachment", "") or "").strip()
        if not candidate:
            continue
        path = Path(candidate)
        key = str(path).lower()
        if not path.exists() or key in seen:
            continue
        seen.add(key)
        attachments.append(path)
    return attachments
