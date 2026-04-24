from __future__ import annotations

from ...evidence_flow.screenshots import capture_step_3_validacion_error
from .selectors import SELECTORS


def capturar_error_validacion_final(page, registro: dict, motivo: str):
    """Captura el panel del paso 3 cuando falla el codigo/captcha de validacion."""
    return capture_step_3_validacion_error(
        page,
        registro,
        SELECTORS["panel_candidates"],
        motivo,
    )
