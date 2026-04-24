from __future__ import annotations

import os
import time
from dataclasses import dataclass


def _env_bool(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "1" if default else "0") or ("1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "si", "sí", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, str(default)) or default).strip())
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(str(os.getenv(name, str(default)) or default).strip())
    except Exception:
        return default


def detect_windows_screen_size(default_w: int = 1920, default_h: int = 1080):
    """Retorna resolucion efectiva (espacio logico) en Windows."""
    try:
        import ctypes

        user32 = ctypes.windll.user32
        w = int(user32.GetSystemMetrics(0))
        h = int(user32.GetSystemMetrics(1))
        if w >= 800 and h >= 600:
            return w, h
    except Exception:
        pass
    return default_w, default_h


@dataclass(frozen=True)
class RuntimeOptions:
    run_mode: str
    is_scheduled: bool
    hold_browser_open: bool
    browser_start_maximized: bool
    browser_window_w: int
    browser_window_h: int
    tile_enabled: bool
    tile_total: int
    tile_index: int
    tile_cols: int
    tile_rows: int
    tile_screen_w: int
    tile_screen_h: int
    tile_top_offset: int
    tile_gap: int
    tile_frame_pad: int
    tile_x: int
    tile_y: int
    tile_w: int
    tile_h: int
    max_run_minutes: float
    max_login_retries_per_group: int
    login_validation_timeout_ms: int
    terminal_confirmaciones_requeridas: int
    nro_solicitud_confirmaciones_requeridas: int
    sin_cupo_confirmaciones_requeridas: int
    max_unmapped_retries_per_record: int
    max_hora_fallback_retries: int
    persistent_session: bool


def load_runtime_options() -> RuntimeOptions:
    run_mode = os.getenv("RUN_MODE", "manual").strip().lower()
    is_scheduled = run_mode == "scheduled"
    hold_browser_open = _env_bool("HOLD_BROWSER_OPEN", default=False)
    browser_start_maximized = _env_bool("BROWSER_START_MAXIMIZED", default=False)
    browser_window_w = max(800, _env_int("BROWSER_WINDOW_W", 1366))
    browser_window_h = max(600, _env_int("BROWSER_WINDOW_H", 900))

    tile_enabled = _env_bool("BROWSER_TILE_ENABLE", default=False)
    tile_total = max(1, _env_int("BROWSER_TILE_TOTAL", 1))
    tile_index = _env_int("BROWSER_TILE_INDEX", 0)
    if tile_index < 0:
        tile_index = 0
    if tile_index >= tile_total:
        tile_index = tile_total - 1

    tile_cols = max(0, _env_int("BROWSER_TILE_COLS", 0))
    tile_rows = max(0, _env_int("BROWSER_TILE_ROWS", 0))
    tile_screen_w = _env_int("BROWSER_TILE_SCREEN_W", 1920)
    tile_screen_h = _env_int("BROWSER_TILE_SCREEN_H", 1080)
    tile_top_offset = _env_int("BROWSER_TILE_TOP_OFFSET", 0)
    tile_gap = max(0, _env_int("BROWSER_TILE_GAP", 8))
    tile_frame_pad = max(0, _env_int("BROWSER_TILE_FRAME_PAD", 24))

    tile_x = 0
    tile_y = 0
    tile_w = 1920
    tile_h = 1080
    if tile_enabled:
        cols = tile_cols or (2 if tile_total == 2 else (1 if tile_total == 1 else 2))
        rows = tile_rows or ((tile_total + cols - 1) // cols)
        cols = max(1, cols)
        rows = max(1, rows)
        usable_h = max(480, tile_screen_h - max(0, tile_top_offset))
        cell_w = max(360, tile_screen_w // cols)
        cell_h = max(320, usable_h // rows)

        tile_w = max(320, cell_w - (tile_gap * 2) - tile_frame_pad)
        tile_h = max(260, cell_h - (tile_gap * 2))
        col = tile_index % cols
        row = tile_index // cols
        tile_x = col * cell_w + tile_gap + (tile_frame_pad if col > 0 else 0)
        tile_y = max(0, tile_top_offset) + row * cell_h + tile_gap

    max_run_minutes = max(0.0, _env_float("MAX_RUN_MINUTES", 0.0))
    max_login_retries_per_group = max(1, _env_int("MAX_LOGIN_RETRIES_PER_GROUP", 12))
    login_validation_timeout_ms = max(1000, _env_int("LOGIN_VALIDATION_TIMEOUT_MS", 6000))
    terminal_confirmaciones_requeridas = max(1, _env_int("TERMINAL_CONFIRM_ATTEMPTS", 2))
    nro_solicitud_confirmaciones_requeridas = max(
        1,
        _env_int("NRO_SOLICITUD_CONFIRM_ATTEMPTS", terminal_confirmaciones_requeridas),
    )
    sin_cupo_confirmaciones_requeridas = max(1, _env_int("SIN_CUPO_CONFIRM_ATTEMPTS", 1))
    max_unmapped_retries_per_record = max(0, _env_int("MAX_UNMAPPED_RETRIES_PER_RECORD", 4))
    max_hora_fallback_retries = max(1, _env_int("MAX_HOUR_FALLBACK_RETRIES", 8))
    persistent_session = str(os.getenv("PERSISTENT_SESSION", "0")).strip().lower() in ("1", "true", "yes")

    return RuntimeOptions(
        run_mode=run_mode,
        is_scheduled=is_scheduled,
        hold_browser_open=hold_browser_open,
        browser_start_maximized=browser_start_maximized,
        browser_window_w=browser_window_w,
        browser_window_h=browser_window_h,
        tile_enabled=tile_enabled,
        tile_total=tile_total,
        tile_index=tile_index,
        tile_cols=tile_cols,
        tile_rows=tile_rows,
        tile_screen_w=tile_screen_w,
        tile_screen_h=tile_screen_h,
        tile_top_offset=tile_top_offset,
        tile_gap=tile_gap,
        tile_frame_pad=tile_frame_pad,
        tile_x=tile_x,
        tile_y=tile_y,
        tile_w=tile_w,
        tile_h=tile_h,
        max_run_minutes=max_run_minutes,
        max_login_retries_per_group=max_login_retries_per_group,
        login_validation_timeout_ms=login_validation_timeout_ms,
        terminal_confirmaciones_requeridas=terminal_confirmaciones_requeridas,
        nro_solicitud_confirmaciones_requeridas=nro_solicitud_confirmaciones_requeridas,
        sin_cupo_confirmaciones_requeridas=sin_cupo_confirmaciones_requeridas,
        max_unmapped_retries_per_record=max_unmapped_retries_per_record,
        max_hora_fallback_retries=max_hora_fallback_retries,
        persistent_session=persistent_session,
    )


def es_error_transitorio_para_relogin(error: BaseException) -> bool:
    """Detecta estados UI inconsistentes donde conviene reloguear."""
    txt = str(error or "").lower()
    pistas = [
        "relogin_ui_desync",
        "tipo de trmite es obligatorio",
        "no se confirm la vista de 'reservas de citas'",
        "no se encontr el header 'citas'",
        "no se confirm la seleccin en el combo",
        "reserva_form no visible",
    ]
    return any(p in txt for p in pistas)


def asegurar_contexto_reserva_operativo(page, selectors: dict, seleccionar_tipo_cita_poligono) -> None:
    """
    Valida que la UI este lista antes de procesar cada registro.
    Si detecta estado intermedio (ej. combo en ---), intenta recomponer una vez.
    """
    try:
        page.locator("form#gestionCitasForm").wait_for(state="visible", timeout=6000)
    except Exception as e:
        raise Exception("RELOGIN_UI_DESYNC: gestionCitasForm no visible") from e

    label_cita = ""
    try:
        label_cita = (page.locator(selectors["tipo_cita_label"]).inner_text() or "").strip().upper()
    except Exception:
        label_cita = ""

    if not label_cita or label_cita == "---":
        seleccionar_tipo_cita_poligono(page)
        page.wait_for_timeout(350)
        try:
            label_cita = (page.locator(selectors["tipo_cita_label"]).inner_text() or "").strip().upper()
        except Exception:
            label_cita = ""

    if not label_cita or label_cita == "---":
        raise Exception("RELOGIN_UI_DESYNC: combo 'Cita para' permanece en '---'")

    try:
        page.locator(selectors["reserva_form"]).wait_for(state="visible", timeout=7000)
    except Exception as e:
        raise Exception("RELOGIN_UI_DESYNC: reserva_form no visible") from e


def validar_credenciales_configuradas(credenciales: dict, etiqueta: str) -> None:
    faltantes = []
    if not str(credenciales.get("numero_documento", "")).strip():
        faltantes.append("numero_documento")
    if not str(credenciales.get("usuario", "")).strip():
        faltantes.append("usuario")
    if not str(credenciales.get("contrasena", "")).strip():
        faltantes.append("contrasena")
    if faltantes:
        raise Exception(
            f"Faltan credenciales para grupo {etiqueta}: {faltantes}. "
            "Configúralas en .env"
        )


def validar_tiempo_maximo(inicio_total_flujo: float, max_run_minutes: float) -> None:
    if max_run_minutes <= 0:
        return
    transcurrido = time.time() - inicio_total_flujo
    if transcurrido >= max_run_minutes * 60:
        raise KeyboardInterrupt(f"MAX_RUN_MINUTES alcanzado ({max_run_minutes} min)")


def clasificar_error_terminal_registro(
    error: BaseException,
    sin_cupo_error,
    fecha_no_disponible_error,
    turno_duplicado_error,
) -> str:
    txt = str(error or "")
    txt_low = txt.lower()
    if isinstance(error, sin_cupo_error):
        return "SIN_CUPO"
    if isinstance(error, fecha_no_disponible_error):
        return "FECHA_NO_DISPONIBLE"
    if isinstance(error, turno_duplicado_error):
        return "TURNO_DUPLICADO"
    if "ya existe un turno registrado" in txt_low:
        return "TURNO_DUPLICADO"
    if "no se encontr" in txt_low and "nro solicitud" in txt_low:
        return "NRO_SOLICITUD"
    if "no hay opciones en el combo de nro solicitud" in txt_low:
        return "NRO_SOLICITUD"
    if "documento vigilante" in txt_low:
        return "DOC_VIGILANTE"
    if "no se encontró la hora objetivo en la tabla" in txt:
        return "HORA_NO_DISPONIBLE"
    return ""


def observacion_terminal_por_categoria(categoria: str, registro_excel: dict, error: BaseException) -> str:
    if categoria == "SIN_CUPO":
        return f"No alcanzo cupo para horario {registro_excel.get('hora_rango', '')}"
    if categoria == "NRO_SOLICITUD":
        return f"No se encontró Nro Solicitud/Código de pago para token de {registro_excel.get('nro_solicitud', '')}"
    if categoria == "DOC_VIGILANTE":
        return (
            "Documento vigilante no disponible para esta razón social/RUC. "
            f"DNI={registro_excel.get('doc_vigilante', '')} | RUC={registro_excel.get('ruc', '')}"
        )
    if categoria == "HORA_NO_DISPONIBLE":
        return "Horario no figura en la tabla de cupos: " f"{registro_excel.get('hora_rango', '')}"
    if categoria == "FECHA_NO_DISPONIBLE":
        return "Fecha no disponible en combo de Reserva de Cupos: " f"{registro_excel.get('fecha', '')}"
    if categoria == "TURNO_DUPLICADO":
        return (
            "Ya existe un turno registrado para la misma persona y Tipo de Licencia. "
            f"DNI={registro_excel.get('doc_vigilante', '')} | "
            f"TipoOperacion={registro_excel.get('tipo_operacion', '')}"
        )
    return f"Error en procesamiento: {error}"


def confirmaciones_requeridas_para_categoria(
    categoria: str,
    terminal_confirmaciones_requeridas: int,
    nro_solicitud_confirmaciones_requeridas: int,
    sin_cupo_confirmaciones_requeridas: int,
) -> int:
    if categoria == "SIN_CUPO":
        return sin_cupo_confirmaciones_requeridas
    if categoria == "TURNO_DUPLICADO":
        return 1
    if categoria == "NRO_SOLICITUD":
        return nro_solicitud_confirmaciones_requeridas
    return terminal_confirmaciones_requeridas


def observacion_error_no_mapeado(registro_excel: dict, error: BaseException, intentos: int) -> str:
    hora = registro_excel.get("hora_rango", "")
    token = registro_excel.get("nro_solicitud", "")
    return "Error no mapeado persistente tras " f"{intentos} intentos (hora={hora}, token={token}): {error}"
