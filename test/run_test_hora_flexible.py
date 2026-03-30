from __future__ import annotations

import os
import sys
import traceback
import importlib
from pathlib import Path


def _bootstrap_project_path() -> None:
    """Ajusta sys.path para poder importar 'armas_gadso' desde carpeta test/."""
    this_file = Path(__file__).resolve()
    for root in this_file.parents:
        if (root / "armas_gadso").is_dir() and (root / "run_pipeline.py").is_file():
            root_str = str(root)
            if root_str not in sys.path:
                sys.path.insert(0, root_str)
            return
    raise RuntimeError("No se encontró la raíz del proyecto (carpeta con armas_gadso y run_pipeline.py).")


_bootstrap_project_path()


FORCED_CAPTCHA = "FERNA"


def run_hora_flexible_test() -> int:
    """
    Runner aislado para validar selección de hora flexible.

    Activa:
    - Selección adaptativa de hora.
    - Bloque completo 11:45-13:00 para elegir mayor cupo.
    - Replanificación cuando en paso final aparezca mensaje de cupos ocupados.
    """
    config_mod = importlib.import_module("armas_gadso.config")
    logging_mod = importlib.import_module("armas_gadso.logging_utils")
    load_config = config_mod.load_config
    build_logger = logging_mod.build_logger
    redirect_prints = logging_mod.redirect_prints

    config = load_config()
    os.environ["EXCEL_PATH"] = str(config.excel_path)
    os.environ["RUN_MODE"] = "scheduled"
    os.environ["HOLD_BROWSER_OPEN"] = "0"

    # Flags de prueba para la nueva lógica.
    os.environ["ADAPTIVE_HOUR_SELECTION"] = "1"
    os.environ["ADAPTIVE_HOUR_NOON_FULL_BLOCK"] = "1"
    os.environ["MAX_HOUR_FALLBACK_RETRIES"] = os.environ.get("MAX_HOUR_FALLBACK_RETRIES", "8")

    legacy_flow = importlib.import_module("armas_gadso.legacy_flow")

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
