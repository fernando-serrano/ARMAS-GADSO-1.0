from __future__ import annotations

import os
import re
import sys
import traceback
import importlib
from io import BytesIO
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

import numpy as np
from PIL import Image, ImageOps

MAX_INTENTOS_LOGIN = 6
EASYOCR_LANGS = ["en"]
ALLOWED_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def _limpiar_captcha(texto: str) -> str:
    base = re.sub(r"[^A-Za-z0-9]", "", str(texto or "").upper())
    if len(base) == 5:
        return base
    if len(base) > 5:
        for i in range(0, len(base) - 4):
            trozo = base[i : i + 5]
            if len(trozo) == 5:
                return trozo
    return ""


def _extraer_captcha_easyocr(reader, img_bytes: bytes) -> str:
    """Aplica varias transformaciones simples y elige el primer candidato len=5."""
    img = Image.open(BytesIO(img_bytes)).convert("L")

    variantes = []
    variantes.append(np.array(img))

    auto = ImageOps.autocontrast(img)
    variantes.append(np.array(auto))

    bw = auto.point(lambda x: 255 if x > 145 else 0, mode="1").convert("L")
    variantes.append(np.array(bw))

    inv = ImageOps.invert(auto)
    variantes.append(np.array(inv))

    for arr in variantes:
        try:
            resultados = reader.readtext(
                arr,
                detail=0,
                paragraph=False,
                allowlist=ALLOWED_CHARS,
            )
        except Exception:
            resultados = []

        for item in resultados:
            candidato = _limpiar_captcha(item)
            if candidato:
                return candidato

    return ""


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

    try:
        easyocr = importlib.import_module("easyocr")
    except Exception as exc:
        print("[ERROR] EasyOCR no está instalado.")
        print("Instala dependencias de prueba con: pip install easyocr numpy pillow")
        print(f"Detalle: {exc}")
        return 1

    # Importar después de inyectar env para que legacy_flow tome rutas/modo correctos.
    legacy_flow = importlib.import_module("armas_gadso.legacy_flow")

    logger, log_path = build_logger(config.log_dir)
    logger.info("Iniciando prueba aislada EasyOCR")
    logger.info("Modo: %s", os.environ.get("RUN_MODE", "scheduled"))
    logger.info("Excel: %s", os.environ.get("EXCEL_PATH", str(config.excel_path)))
    logger.info("[TEST] EasyOCR idiomas=%s", EASYOCR_LANGS)
    logger.info("[TEST] CAPTCHA mitigado forzado SOLO Fase 3: %s", FORCED_CAPTCHA)

    reader = easyocr.Reader(EASYOCR_LANGS, gpu=False)

    original_solve_login = legacy_flow.solve_captcha_ocr
    original_solve_base = legacy_flow.solve_captcha_ocr_base
    original_escribir_input_rapido = legacy_flow.escribir_input_rapido

    def solve_captcha_ocr_base_easyocr(
        page,
        captcha_img_selector: str,
        boton_refresh_selector: str = None,
        contexto: str = "CAPTCHA",
        evitar_ambiguos: bool = False,
        min_fuzzy_hits: int = 0,
        max_intentos=6,
    ):
        _ = (evitar_ambiguos, min_fuzzy_hits)
        intento = 0
        while True:
            intento += 1
            if max_intentos is not None and max_intentos > 0 and intento > max_intentos:
                print(f"   [WARNING] {contexto}: EasyOCR no resolvió captcha tras {max_intentos} intentos")
                return None

            print(f" {contexto}: intento EasyOCR {intento}/{max_intentos if max_intentos else '∞'}...")
            try:
                img_bytes = page.locator(captcha_img_selector).screenshot(type="png")
            except Exception as exc:
                print(f"   [WARNING] {contexto}: no se pudo capturar imagen ({exc})")
                if max_intentos is None:
                    page.wait_for_timeout(350)
                    continue
                return None

            captcha = _extraer_captcha_easyocr(reader, img_bytes)
            if captcha:
                print(f"   [INFO] {contexto}: EasyOCR -> {captcha}")
                return captcha

            print(f"   [WARNING] {contexto}: EasyOCR sin candidato válido")
            if boton_refresh_selector:
                try:
                    page.locator(boton_refresh_selector).click()
                    page.wait_for_timeout(250)
                except Exception:
                    pass
            else:
                page.wait_for_timeout(250)

    def solve_captcha_login_easyocr(page):
        return solve_captcha_ocr_base_easyocr(
            page,
            captcha_img_selector=legacy_flow.SEL["captcha_img"],
            boton_refresh_selector=legacy_flow.SEL["boton_refresh"],
            contexto="CAPTCHA Login",
            max_intentos=MAX_INTENTOS_LOGIN,
        )

    def escribir_input_rapido_mitigado(page, selector: str, valor: str):
        if selector == legacy_flow.SEL["fase3_captcha_input"]:
            valor = FORCED_CAPTCHA
            print(f"   [TEST] CAPTCHA Fase 3 mitigado forzado por runner: {valor}")
        return original_escribir_input_rapido(page, selector, valor)

    legacy_flow.solve_captcha_ocr_base = solve_captcha_ocr_base_easyocr
    legacy_flow.solve_captcha_ocr = solve_captcha_login_easyocr
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
        legacy_flow.solve_captcha_ocr = original_solve_login
        legacy_flow.solve_captcha_ocr_base = original_solve_base
        legacy_flow.escribir_input_rapido = original_escribir_input_rapido
        logger.info("Log disponible en: %s", log_path)


if __name__ == "__main__":
    raise SystemExit(run_easyocr_test())
