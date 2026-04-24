from __future__ import annotations

from .selectors import SELECTORS
from ...evidence_flow.screenshots import capture_step_1_no_cupos, capture_step_1_tabla


def capturar_tabla_cupos(page, registro: dict, hora_objetivo: str, motivo: str = "tabla_cupos"):
    """Evidencia base del Paso 1: tabla de cupos aunque existan horarios disponibles."""
    return capture_step_1_tabla(
        page,
        registro,
        table_selector=SELECTORS["tabla_programacion"],
        hora_objetivo=hora_objetivo,
        reason=motivo,
    )


def capturar_tabla_sin_cupo(page, registro: dict, hora_objetivo: str, motivo: str):
    """Evidencia del Paso 1: tabla de programacion cuando los cupos evaluados son 0."""
    return capture_step_1_no_cupos(
        page,
        registro,
        table_selector=SELECTORS["tabla_programacion"],
        hora_objetivo=hora_objetivo,
        reason=motivo,
    )
