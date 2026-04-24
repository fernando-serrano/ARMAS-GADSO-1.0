from __future__ import annotations

from ...evidence_flow.screenshots import capture_step_2_tramite_error
from .selectors import SELECTORS


def capturar_error_paso_2(page, registro: dict, motivo: str):
    """Captura el panel del paso 2 cuando falla doc vigilante o nro solicitud."""
    return capture_step_2_tramite_error(
        page,
        registro,
        SELECTORS["panel_candidates"],
        motivo,
        overlay_selectors=SELECTORS["overlay_candidates"],
    )
