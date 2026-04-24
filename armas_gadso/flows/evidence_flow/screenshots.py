from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path


def _safe_filename_part(value: object, fallback: str = "sin_valor") -> str:
    text = str(value or "").strip()
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    text = text.strip("._-")
    return text[:80] or fallback


def _record_part(registro: dict, key: str, fallback: str) -> str:
    return _safe_filename_part(registro.get(key, ""), fallback)


def screenshot_root() -> Path:
    return Path(os.getenv("SCREENSHOT_DIR", "screenshots"))


def screenshot_scale() -> str:
    value = str(os.getenv("SCREENSHOT_SCALE", "css") or "css").strip().lower()
    return value if value in {"css", "device"} else "css"


def step_dir(step_name: str) -> Path:
    path = screenshot_root() / _safe_filename_part(step_name, "step")
    path.mkdir(parents=True, exist_ok=True)
    return path


def screenshot_name(registro: dict, reason: str, hora: str = "") -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    idx_raw = (
        registro.get("_excel_index")
        or registro.get("idx_excel")
        or registro.get("id_registro")
        or ""
    )
    idx = _safe_filename_part(idx_raw, "0")
    hora_part = _safe_filename_part(hora or registro.get("hora_rango", ""), "hora")
    reason_part = _safe_filename_part(reason, "evidencia")
    return f"{stamp}_{reason_part}_i{idx}_h{hora_part}.png"


def capture_locator(locator, destination: Path, timeout_ms: int = 5000) -> bool:
    locator.wait_for(state="visible", timeout=timeout_ms)
    locator.screenshot(path=str(destination), scale=screenshot_scale())
    return True


def capture_page(page, destination: Path, timeout_ms: int = 5000) -> bool:
    page.wait_for_timeout(max(0, timeout_ms))
    page.screenshot(path=str(destination), full_page=False, scale=screenshot_scale())
    return True


def capture_first_visible(page, selectors: list[str], destination: Path, timeout_ms: int = 5000) -> bool:
    last_error = None
    for selector in selectors:
        try:
            locator = page.locator(selector)
            if locator.count() == 0:
                continue
            capture_locator(locator.first, destination, timeout_ms=timeout_ms)
            return True
        except Exception as exc:
            last_error = exc
    if last_error:
        raise last_error
    raise Exception(f"No se encontraron selectores visibles para screenshot: {selectors}")


def capture_step_1_no_cupos(page, registro: dict, table_selector: str, hora_objetivo: str, reason: str) -> Path | None:
    try:
        destination = step_dir("step_1_reserva_cupos") / screenshot_name(
            registro,
            f"sin_cupo_{reason}",
            hora=hora_objetivo,
        )
        capture_locator(page.locator(table_selector), destination)
        print(f"   [INFO] Screenshot tabla sin cupo: {destination}")
        return destination
    except Exception as exc:
        print(f"   [WARNING] No se pudo capturar screenshot de tabla sin cupo: {exc}")
        return None


def capture_step_1_tabla(page, registro: dict, table_selector: str, hora_objetivo: str, reason: str) -> Path | None:
    try:
        destination = step_dir("step_1_reserva_cupos") / screenshot_name(
            registro,
            reason,
            hora=hora_objetivo,
        )
        capture_locator(page.locator(table_selector), destination)
        print(f"   [INFO] Screenshot tabla cupos: {destination}")
        return destination
    except Exception as exc:
        print(f"   [WARNING] No se pudo capturar screenshot de tabla cupos: {exc}")
        return None


def capture_step_4_confirmacion(page, registro: dict, panel_selectors: list[str]) -> Path | None:
    try:
        destination = step_dir("step_4_confirmacion") / screenshot_name(
            registro,
            "cita_generada",
            hora=registro.get("_hora_seleccionada_actual", registro.get("hora_rango", "")),
        )
        capture_first_visible(page, panel_selectors, destination)
        print(f"   [INFO] Screenshot confirmacion cita: {destination}")
        return destination
    except Exception as exc:
        print(f"   [WARNING] No se pudo capturar screenshot de confirmacion: {exc}")
        return None


def capture_step_3_validacion_error(page, registro: dict, panel_selectors: list[str], reason: str) -> Path | None:
    try:
        destination = step_dir("step_3_validacion_final") / screenshot_name(
            registro,
            reason,
            hora=registro.get("_hora_seleccionada_actual", registro.get("hora_rango", "")),
        )
        capture_first_visible(page, panel_selectors, destination)
        print(f"   [INFO] Screenshot validacion final: {destination}")
        return destination
    except Exception as exc:
        print(f"   [WARNING] No se pudo capturar screenshot de validacion final: {exc}")
        return None


def capture_step_2_tramite_error(
    page,
    registro: dict,
    panel_selectors: list[str],
    reason: str,
    overlay_selectors: list[str] | None = None,
) -> Path | None:
    try:
        destination = step_dir("step_2_datos_tramite") / screenshot_name(
            registro,
            reason,
            hora=registro.get("_hora_seleccionada_actual", registro.get("hora_rango", "")),
        )
        delay_ms = 1200
        try:
            delay_ms = max(0, int(str(os.getenv("STEP_2_SCREENSHOT_DELAY_MS", "1200")).strip()))
        except Exception:
            delay_ms = 1200

        page.wait_for_timeout(delay_ms)

        overlay_visible = False
        for selector in overlay_selectors or []:
            try:
                locator = page.locator(selector)
                if locator.count() > 0 and locator.first.is_visible():
                    overlay_visible = True
                    break
            except Exception:
                pass

        if overlay_visible:
            capture_page(page, destination, timeout_ms=0)
        else:
            capture_first_visible(page, panel_selectors, destination)
        print(f"   [INFO] Screenshot paso 2: {destination}")
        return destination
    except Exception as exc:
        print(f"   [WARNING] No se pudo capturar screenshot del paso 2: {exc}")
        return None
