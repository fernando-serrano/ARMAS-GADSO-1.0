from __future__ import annotations

from ...evidence_flow.screenshots import capture_step_4_confirmacion
from .selectors import SELECTORS


def capturar_panel_confirmacion(page, registro: dict):
    """Captura el panel final cuando SEL confirma la cita generada."""
    return capture_step_4_confirmacion(
        page,
        registro,
        SELECTORS["panel_candidates"],
    )
