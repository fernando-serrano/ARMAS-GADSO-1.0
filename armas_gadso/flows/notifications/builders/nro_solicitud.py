from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .sin_cupo import case_label


def build_subject(config: dict, total_cases: int) -> str:
    pieces = [config["subject_prefix"], "No se encontro Nro. Solicitud"]
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


def build_html_body(events: list[dict]) -> str:
    now = datetime.now()
    today = now.strftime("%d/%m/%Y")
    now_hhmmss = now.strftime("%H:%M:%S")
    highlight_style = "background:#fff3b0;padding:2px 6px;border-radius:4px;"

    rows = []
    for event in events:
        registro = event["registro"]
        rows.append(
            "<tr>"
            f"<td style='border:1px solid #d0d7de;padding:8px;'>{case_label(registro)}</td>"
            f"<td style='border:1px solid #d0d7de;padding:8px;'>{str(registro.get('sede', '') or '').strip()}</td>"
            f"<td style='border:1px solid #d0d7de;padding:8px;'>{_format_fecha_larga(str(registro.get('fecha', '') or '').strip())}</td>"
            f"<td style='border:1px solid #d0d7de;padding:8px;'>{str(event.get('hora_objetivo', '') or registro.get('hora_rango', '') or '').strip()}</td>"
            f"<td style='border:1px solid #d0d7de;padding:8px;'>{str(registro.get('nro_solicitud', '') or '').strip()}</td>"
            f"<td style='border:1px solid #d0d7de;padding:8px;'>{'Adjunta' if event.get('has_evidence') else 'No disponible'}</td>"
            "</tr>"
        )

    evidence_line = (
        "<p>Se adjuntan las capturas disponibles del paso 2 por caso.</p>"
        if any(event.get("has_evidence") for event in events)
        else "<p>No se generaron evidencias adjuntas para estos casos.</p>"
    )
    label = "Caso detectado:" if len(events) == 1 else "Casos detectados:"
    return (
        "<p>Buen dia &#129302;</p>"
        f"<p><span style='font-weight:700;'>No se encontro Nro. Solicitud</span> en la ejecucion del "
        f"<span style='{highlight_style}'>{today}</span> a las "
        f"<span style='{highlight_style}'>{now_hhmmss} hrs</span>.</p>"
        f"<p>{label}</p>"
        "<table style='border-collapse:collapse;border:1px solid #d0d7de;'>"
        "<thead><tr>"
        "<th style='border:1px solid #d0d7de;padding:8px;background:#f6f8fa;text-align:left;'>DNI</th>"
        "<th style='border:1px solid #d0d7de;padding:8px;background:#f6f8fa;text-align:left;'>Sede</th>"
        "<th style='border:1px solid #d0d7de;padding:8px;background:#f6f8fa;text-align:left;'>Fecha objetivo</th>"
        "<th style='border:1px solid #d0d7de;padding:8px;background:#f6f8fa;text-align:left;'>Hora objetivo</th>"
        "<th style='border:1px solid #d0d7de;padding:8px;background:#f6f8fa;text-align:left;'>Nro. Solicitud</th>"
        "<th style='border:1px solid #d0d7de;padding:8px;background:#f6f8fa;text-align:left;'>Evidencia</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
        f"{evidence_line}"
    )


def select_attachments(events: list[dict]) -> list[Path]:
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
