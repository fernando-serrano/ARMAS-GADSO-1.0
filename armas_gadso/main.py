from __future__ import annotations

import argparse
import os
import traceback
from pathlib import Path

from .config import load_config
from .logging_utils import build_logger, prepare_run_artifact_dir, redirect_prints


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pipeline ARMAS-GADSO")
    parser.add_argument(
        "--mode",
        choices=["manual", "scheduled"],
        default=None,
        help="Modo de ejecución",
    )
    parser.add_argument(
        "--hold-browser-open",
        action="store_true",
        help="Mantener navegador abierto al terminar (solo manual)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.mode:
        os.environ["RUN_MODE"] = args.mode
    if args.hold_browser_open:
        os.environ["HOLD_BROWSER_OPEN"] = "1"

    config = load_config()
    os.environ["EXCEL_PATH"] = str(config.excel_path)
    os.environ["RUN_MODE"] = config.run_mode
    os.environ["HOLD_BROWSER_OPEN"] = "1" if config.hold_browser_open else "0"

    logger, log_path = build_logger(config.log_dir)
    screenshot_dir = prepare_run_artifact_dir(config.screenshot_dir, "SCREENSHOT_RUN_DIR", "SCREENSHOT_DIR_IS_RUN_DIR")
    os.environ["SCREENSHOT_DIR"] = str(screenshot_dir)
    logger.info("Iniciando pipeline ARMAS-GADSO")
    logger.info("Modo: %s", config.run_mode)
    logger.info("Excel: %s", config.excel_path)
    logger.info("Screenshots: %s", screenshot_dir)

    try:
        from . import legacy_flow

        with redirect_prints(logger):
            legacy_flow.llenar_login_sel()
        logger.info("Pipeline finalizado")
        return 0
    except Exception as exc:
        logger.error("Pipeline finalizado con error: %s", exc)
        logger.error(traceback.format_exc())
        return 1
    finally:
        logger.info("Log disponible en: %s", log_path)


if __name__ == "__main__":
    raise SystemExit(main())
