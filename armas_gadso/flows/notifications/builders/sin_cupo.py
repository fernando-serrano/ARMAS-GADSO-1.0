from __future__ import annotations

from datetime import datetime
from pathlib import Path


def build_subject(config: dict, registro: dict, hora_objetivo: str) -> str:
    idx_excel = registro.get("idx_excel")
    if idx_excel is None or idx_excel == "":
        idx_excel = registro.get("_excel_index", "")
    fecha = str(registro.get("fecha", "") or "").strip()
    sede = str(registro.get("sede", "") or "").strip()
    hora = str(hora_objetivo or registro.get("hora_rango", "") or "").strip()
    pieces = [config["subject_prefix"], "No se reservaron vacantes"]
    if idx_excel != "":
        pieces.append(f"idx={idx_excel}")
    if fecha:
        pieces.append(fecha)
    if sede:
        pieces.append(sede)
    if hora:
        pieces.append(hora)
    return " | ".join(pieces)


def build_multirun_subject(config: dict, total_cases: int) -> str:
    base = [config["subject_prefix"], "No se reservaron vacantes"]
    if total_cases > 1:
        base.append(f"{total_cases} casos")
    return " | ".join(base)


def format_fecha_corta(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%d/%m")
        except Exception:
            pass
    return raw


def hora_inicio(hora_objetivo: str, registro: dict) -> str:
    raw = str(hora_objetivo or registro.get("hora_rango", "") or "").strip()
    if not raw:
        return ""
    return raw.split("-", 1)[0].strip()


def hora_rango_completo(hora_objetivo: str, registro: dict) -> str:
    return str(hora_objetivo or registro.get("hora_rango", "") or "").strip()


def case_label(registro: dict) -> str:
    for key in ["doc_vigilante", "numero_documento", "nro_documento"]:
        value = str(registro.get(key, "") or "").strip()
        if value:
            return value

    idx_excel = registro.get("idx_excel")
    if idx_excel is None or idx_excel == "":
        idx_excel = registro.get("_excel_index", "")
    idx_excel = str(idx_excel).strip()
    return f"idx={idx_excel}" if idx_excel else "caso"


def build_html_body(registro: dict, hora_objetivo: str) -> str:
    fecha_objetivo = format_fecha_corta(str(registro.get("fecha", "") or "").strip())
    sede = str(registro.get("sede", "") or "").strip()
    hora = hora_inicio(hora_objetivo, registro)
    idx_excel = str(registro.get("idx_excel", registro.get("_excel_index", "")) or "").strip()
    momento = datetime.now().strftime("%d/%m/%Y")

    details = []
    if idx_excel:
        details.append(f"<li><b>Indice:</b> {idx_excel}</li>")
    if sede:
        details.append(f"<li><b>Sede:</b> {sede}</li>")
    if fecha_objetivo:
        details.append(f"<li><b>Fecha objetivo:</b> {fecha_objetivo}</li>")
    if hora:
        details.append(f"<li><b>Hora objetivo:</b> {hora}</li>")

    detail_block = f"<ul>{''.join(details)}</ul>" if details else ""
    return (
        f"<p>Buen dia 🤖 No se reservaron vacantes el dia {momento}"
        f"{f' a las {hora}' if hora else ''}"
        f"{f' para el {fecha_objetivo}' if fecha_objetivo else ''}.</p>"
        f"{detail_block}"
        "<p>Se adjuntan las capturas de disponibilidad y validacion del caso sin cupo.</p>"
    )


def build_multirun_html_body(events: list[dict]) -> str:
    now = datetime.now()
    today = now.strftime("%d/%m/%Y")
    now_hhmmss = now.strftime("%H:%M:%S")
    highlight_style = "background:#fff3b0;padding:2px 6px;border-radius:4px;"
    alert_style = "font-weight:700;"
    if len(events) == 1:
        event = events[0]
        registro = event["registro"]
        sede = str(registro.get("sede", "") or "").strip()
        fecha_objetivo = format_fecha_corta(str(registro.get("fecha", "") or "").strip())
        hora = hora_rango_completo(str(event.get("hora_objetivo", "") or ""), registro)
        evidencia = "Adjunta" if event.get("has_evidence") else "No disponible"
        row = (
            "<tr>"
            f"<td style='border:1px solid #d0d7de;padding:8px;'>{case_label(registro)}</td>"
            f"<td style='border:1px solid #d0d7de;padding:8px;'>{sede}</td>"
            f"<td style='border:1px solid #d0d7de;padding:8px;'>{fecha_objetivo}</td>"
            f"<td style='border:1px solid #d0d7de;padding:8px;'>{hora}</td>"
            f"<td style='border:1px solid #d0d7de;padding:8px;'>{evidencia}</td>"
            "</tr>"
        )
        return (
            "<p>Buen día 🤖</p>"
            f"<p><span style='{alert_style}'>No se encontraron vacantes</span> en la ejecución del "
            f"<span style='{highlight_style}'>{today}</span> a las "
            f"<span style='{highlight_style}'>{now_hhmmss} hrs</span>.</p>"
            "<p>Caso detectado:</p>"
            "<table style='border-collapse:collapse;border:1px solid #d0d7de;'>"
            "<thead><tr>"
            "<th style='border:1px solid #d0d7de;padding:8px;background:#f6f8fa;text-align:left;'>DNI</th>"
            "<th style='border:1px solid #d0d7de;padding:8px;background:#f6f8fa;text-align:left;'>Sede</th>"
            "<th style='border:1px solid #d0d7de;padding:8px;background:#f6f8fa;text-align:left;'>Fecha objetivo</th>"
            "<th style='border:1px solid #d0d7de;padding:8px;background:#f6f8fa;text-align:left;'>Hora objetivo</th>"
            "<th style='border:1px solid #d0d7de;padding:8px;background:#f6f8fa;text-align:left;'>Evidencia</th>"
            "</tr></thead>"
            f"<tbody>{row}</tbody></table>"
            "<p>Se adjunta la evidencia final disponible del caso.</p>"
        )

    rows = []
    for event in events:
        registro = event["registro"]
        sede = str(registro.get("sede", "") or "").strip()
        fecha_objetivo = format_fecha_corta(str(registro.get("fecha", "") or "").strip())
        hora = hora_rango_completo(str(event.get("hora_objetivo", "") or ""), registro)
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

    return (
        "<p>Buen día 🤖</p>"
        f"<p><span style='font-weight:700;'>No se encontraron vacantes</span> en la ejecución del "
        f"<span style='{highlight_style}'>{today}</span> a las "
        f"<span style='{highlight_style}'>{now_hhmmss} hrs</span>.</p>"
        "<p>Casos detectados:</p>"
        "<table style='border-collapse:collapse;border:1px solid #d0d7de;'>"
        "<thead><tr>"
        "<th style='border:1px solid #d0d7de;padding:8px;background:#f6f8fa;text-align:left;'>DNI</th>"
        "<th style='border:1px solid #d0d7de;padding:8px;background:#f6f8fa;text-align:left;'>Sede</th>"
        "<th style='border:1px solid #d0d7de;padding:8px;background:#f6f8fa;text-align:left;'>Fecha objetivo</th>"
        "<th style='border:1px solid #d0d7de;padding:8px;background:#f6f8fa;text-align:left;'>Hora objetivo</th>"
        "<th style='border:1px solid #d0d7de;padding:8px;background:#f6f8fa;text-align:left;'>Evidencia</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        "<p>Se adjuntan las evidencias finales disponibles por caso.</p>"
    )


def select_representative_attachments(events: list[dict]) -> list[Path]:
    attachments: list[Path] = []
    seen = set()
    for event in events:
        candidates = [event.get("sin_cupo_attachment"), event.get("tabla_inicial_attachment")]
        for candidate in candidates:
            if not candidate:
                continue
            path = Path(str(candidate))
            key = str(path).lower()
            if not path.exists() or key in seen:
                continue
            seen.add(key)
            attachments.append(path)
            break
    return attachments
