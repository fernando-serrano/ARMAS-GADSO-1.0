from __future__ import annotations

import os
import traceback

from armas_gadso.config import load_config
from armas_gadso.logging_utils import build_logger, redirect_prints


FORCED_CAPTCHA = "ABCDE"
MAX_INTENTOS_FINAL = 3


def run_captcha_test() -> int:
    """
    Runner aislado para prueba real del captcha final, sin alterar producción.

    Este script fuerza solo el CAPTCHA de Fase 3 a 'ABCDE' y limita
    la acción 'Generar Cita' a 3 intentos para validar la detección de fallo.
    """
    config = load_config()
    os.environ["EXCEL_PATH"] = str(config.excel_path)
    os.environ["RUN_MODE"] = "scheduled"
    os.environ["HOLD_BROWSER_OPEN"] = "0"
    os.environ["DEBUG_TURNO_DUPLICADO"] = "1"

    # Importar después de inyectar env para que legacy_flow tome rutas/modo correctos.
    from armas_gadso import legacy_flow

    logger, log_path = build_logger(config.log_dir)
    logger.info("Iniciando prueba aislada captcha final")
    logger.info("Modo: %s", os.environ.get("RUN_MODE", "scheduled"))
    logger.info("Excel: %s", os.environ.get("EXCEL_PATH", str(config.excel_path)))
    logger.info("[TEST] DEBUG_TURNO_DUPLICADO=%s", os.environ.get("DEBUG_TURNO_DUPLICADO", "0"))
    logger.info("[TEST] CAPTCHA forzado: %s | Intentos finales: %s", FORCED_CAPTCHA, MAX_INTENTOS_FINAL)

    original_escribir_input_rapido = legacy_flow.escribir_input_rapido
    original_generar_final = legacy_flow.generar_cita_final_con_reintento_rapido

    def escribir_input_rapido_test(page, selector: str, valor: str):
        if selector == legacy_flow.SEL["fase3_captcha_input"]:
            valor = FORCED_CAPTCHA
            print(f"   [TEST] CAPTCHA Fase 3 forzado por runner: {valor}")
        return original_escribir_input_rapido(page, selector, valor)

    def generar_cita_final_test(page, max_intentos: int = 3):
        return original_generar_final(page, max_intentos=MAX_INTENTOS_FINAL)

    legacy_flow.escribir_input_rapido = escribir_input_rapido_test
    legacy_flow.generar_cita_final_con_reintento_rapido = generar_cita_final_test

    try:
        with redirect_prints(logger):
            legacy_flow.llenar_login_sel()
        logger.info("Prueba aislada finalizada")
        return 0
    except Exception as exc:
        logger.error("Prueba aislada finalizada con error: %s", exc)
        logger.error(traceback.format_exc())
        return 1
    finally:
        legacy_flow.escribir_input_rapido = original_escribir_input_rapido
        legacy_flow.generar_cita_final_con_reintento_rapido = original_generar_final
        logger.info("Log disponible en: %s", log_path)


if __name__ == "__main__":
    raise SystemExit(run_captcha_test())
