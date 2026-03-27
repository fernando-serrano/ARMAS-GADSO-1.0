from __future__ import annotations

import os
import traceback

from armas_gadso.config import load_config
from armas_gadso.logging_utils import build_logger, redirect_prints


FORCED_CAPTCHA = "FERNA"


def run_hora_flexible_test() -> int:
    """
    Runner aislado para validar selección de hora flexible.

    Activa:
    - Selección adaptativa de hora.
    - Bloque completo 11:45-13:00 para elegir mayor cupo.
    - Replanificación cuando en paso final aparezca mensaje de cupos ocupados.
    """
    config = load_config()
    os.environ["EXCEL_PATH"] = str(config.excel_path)
    os.environ["RUN_MODE"] = "scheduled"
    os.environ["HOLD_BROWSER_OPEN"] = "0"

    # Flags de prueba para la nueva lógica.
    os.environ["ADAPTIVE_HOUR_SELECTION"] = "1"
    os.environ["ADAPTIVE_HOUR_NOON_FULL_BLOCK"] = "1"
    os.environ["MAX_HOUR_FALLBACK_RETRIES"] = os.environ.get("MAX_HOUR_FALLBACK_RETRIES", "8")

    from armas_gadso import legacy_flow

    logger, log_path = build_logger(config.log_dir)
    logger.info("Iniciando prueba aislada de hora flexible")
    logger.info("Modo: %s", os.environ.get("RUN_MODE", "scheduled"))
    logger.info("Excel: %s", os.environ.get("EXCEL_PATH", str(config.excel_path)))
    logger.info("[TEST] ADAPTIVE_HOUR_SELECTION=%s", os.environ.get("ADAPTIVE_HOUR_SELECTION", "0"))
    logger.info("[TEST] ADAPTIVE_HOUR_NOON_FULL_BLOCK=%s", os.environ.get("ADAPTIVE_HOUR_NOON_FULL_BLOCK", "0"))
    logger.info("[TEST] MAX_HOUR_FALLBACK_RETRIES=%s", os.environ.get("MAX_HOUR_FALLBACK_RETRIES", "8"))
    logger.info("[TEST] CAPTCHA forzado Fase 3: %s", FORCED_CAPTCHA)

    original_escribir_input_rapido = legacy_flow.escribir_input_rapido

    def escribir_input_rapido_test(page, selector: str, valor: str):
        if selector == legacy_flow.SEL["fase3_captcha_input"]:
            valor = FORCED_CAPTCHA
            print(f"   [TEST] CAPTCHA Fase 3 forzado por runner: {valor}")
        return original_escribir_input_rapido(page, selector, valor)

    legacy_flow.escribir_input_rapido = escribir_input_rapido_test

    try:
        with redirect_prints(logger):
            legacy_flow.llenar_login_sel()
        logger.info("Prueba aislada de hora flexible finalizada")
        return 0
    except Exception as exc:
        logger.error("Prueba aislada de hora flexible finalizada con error: %s", exc)
        logger.error(traceback.format_exc())
        return 1
    finally:
        legacy_flow.escribir_input_rapido = original_escribir_input_rapido
        logger.info("Log disponible en: %s", log_path)


if __name__ == "__main__":
    raise SystemExit(run_hora_flexible_test())
