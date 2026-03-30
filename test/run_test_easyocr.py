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

FORCED_CAPTCHA = os.getenv("TEST_FORCED_CAPTCHA", "ABCDE").strip() or "ABCDE"


def run_easyocr_test() -> int:
    """
    Runner aislado para probar OCR con EasyOCR en:
    - CAPTCHA de login
    - CAPTCHA de fase final (resumen / reintentos)

    No altera el flujo productivo de legacy_flow.py.
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

    # Opcional: mantener también la lógica de hora adaptativa durante la prueba.
    os.environ.setdefault("ADAPTIVE_HOUR_SELECTION", "1")
    os.environ.setdefault("ADAPTIVE_HOUR_NOON_FULL_BLOCK", "1")

    # Importar después de inyectar env para que legacy_flow tome rutas/modo correctos.
    legacy_flow = importlib.import_module("armas_gadso.legacy_flow")

    if not getattr(legacy_flow, "OCR_AVAILABLE", False) or getattr(legacy_flow, "OCR_BACKEND", "") != "easyocr":
        print("[ERROR] El flujo no cargó EasyOCR como backend OCR.")
        print(f"Estado actual: OCR_AVAILABLE={getattr(legacy_flow, 'OCR_AVAILABLE', None)} | OCR_BACKEND={getattr(legacy_flow, 'OCR_BACKEND', None)}")
        print("Instala dependencias con: pip install -r requirements.txt")
        return 1

    logger, log_path = build_logger(config.log_dir)
    logger.info("Iniciando prueba aislada EasyOCR")
    logger.info("Modo: %s", os.environ.get("RUN_MODE", "scheduled"))
    logger.info("Excel: %s", os.environ.get("EXCEL_PATH", str(config.excel_path)))
    logger.info("[TEST] OCR backend activo: %s", getattr(legacy_flow, "OCR_BACKEND", "desconocido"))
    logger.info("[TEST] CAPTCHA mitigado forzado SOLO Fase 3: %s", FORCED_CAPTCHA)

    original_escribir_input_rapido = legacy_flow.escribir_input_rapido

    def escribir_input_rapido_mitigado(page, selector: str, valor: str):
        if selector == legacy_flow.SEL["fase3_captcha_input"]:
            valor = FORCED_CAPTCHA
            print(f"   [TEST] CAPTCHA Fase 3 mitigado forzado por runner: {valor}")
        return original_escribir_input_rapido(page, selector, valor)

    legacy_flow.escribir_input_rapido = escribir_input_rapido_mitigado

    try:
        with redirect_prints(logger):
            legacy_flow.llenar_login_sel()
        logger.info("Prueba aislada EasyOCR finalizada")
        return 0
    except Exception as exc:
        logger.error("Prueba aislada EasyOCR finalizada con error: %s", exc)
        logger.error(traceback.format_exc())
        return 1
    finally:
        legacy_flow.escribir_input_rapido = original_escribir_input_rapido
        logger.info("Log disponible en: %s", log_path)


if __name__ == "__main__":
    raise SystemExit(run_easyocr_test())
