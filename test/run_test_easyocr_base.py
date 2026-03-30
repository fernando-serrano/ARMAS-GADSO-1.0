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


def run_easyocr_base_test() -> int:
    """
    Runner aislado de EasyOCR sin mitigación de captcha forzado.

    Usa OCR real en:
    - CAPTCHA de login
    - CAPTCHA de fase final (resumen / reintentos)

    Mantiene el flujo base de legacy_flow sin alterar entradas manualmente.
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

    # Opcional: mantener lógica de hora adaptativa durante la prueba.
    os.environ.setdefault("ADAPTIVE_HOUR_SELECTION", "1")
    os.environ.setdefault("ADAPTIVE_HOUR_NOON_FULL_BLOCK", "1")

    legacy_flow = importlib.import_module("armas_gadso.legacy_flow")

    if not getattr(legacy_flow, "OCR_AVAILABLE", False) or getattr(legacy_flow, "OCR_BACKEND", "") != "easyocr":
        print("[ERROR] El flujo no cargó EasyOCR como backend OCR.")
        print(f"Estado actual: OCR_AVAILABLE={getattr(legacy_flow, 'OCR_AVAILABLE', None)} | OCR_BACKEND={getattr(legacy_flow, 'OCR_BACKEND', None)}")
        print("Instala dependencias con: pip install -r requirements.txt")
        return 1

    logger, log_path = build_logger(config.log_dir)
    logger.info("Iniciando prueba aislada EasyOCR (flujo base)")
    logger.info("Modo: %s", os.environ.get("RUN_MODE", "scheduled"))
    logger.info("Excel: %s", os.environ.get("EXCEL_PATH", str(config.excel_path)))
    logger.info("[TEST] OCR backend activo: %s", getattr(legacy_flow, "OCR_BACKEND", "desconocido"))
    logger.info("[TEST] Sin captcha forzado: se usa OCR real del flujo base para login y fase final")

    try:
        with redirect_prints(logger):
            legacy_flow.llenar_login_sel()
        logger.info("Prueba aislada EasyOCR (flujo base) finalizada")
        return 0
    except Exception as exc:
        logger.error("Prueba aislada EasyOCR (flujo base) finalizada con error: %s", exc)
        logger.error(traceback.format_exc())
        return 1
    finally:
        logger.info("Log disponible en: %s", log_path)


if __name__ == "__main__":
    raise SystemExit(run_easyocr_base_test())
