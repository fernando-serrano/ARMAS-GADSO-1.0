from __future__ import annotations

from .screenshots import capturar_panel_confirmacion


def capturar_confirmacion_cita(page, registro: dict):
    """Evidencia del Paso 4: panel final cuando SEL confirma la cita generada."""
    return capturar_panel_confirmacion(page, registro)
