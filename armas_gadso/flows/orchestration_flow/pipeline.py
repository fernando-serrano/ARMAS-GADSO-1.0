from __future__ import annotations


def ejecutar_flujo_principal() -> None:
    """Run the current ARMAS-GADSO pipeline entrypoint."""
    from . import legacy_pipeline

    legacy_pipeline.llenar_login_sel()
