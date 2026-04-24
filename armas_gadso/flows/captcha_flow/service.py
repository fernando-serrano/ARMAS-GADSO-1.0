from __future__ import annotations

import itertools
import os


OCR_AVAILABLE = False
OCR_BACKEND = "manual"
EASYOCR_READER = None
EASYOCR_ALLOWLIST = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
EASYOCR_LANGS = ["en"]
np = None
Image = None
ImageFilter = None
ImageEnhance = None
ImageOps = None
BytesIO = None

try:
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
    from io import BytesIO
    import numpy as np
    import easyocr

    langs_env = str(os.getenv("EASYOCR_LANGS", "en") or "en")
    EASYOCR_LANGS = [x.strip() for x in langs_env.split(",") if x.strip()] or ["en"]
    EASYOCR_ALLOWLIST = str(os.getenv("EASYOCR_ALLOWLIST", EASYOCR_ALLOWLIST) or EASYOCR_ALLOWLIST).strip() or EASYOCR_ALLOWLIST
    easyocr_use_gpu = str(os.getenv("EASYOCR_USE_GPU", "0") or "0").strip().lower() in {"1", "true", "yes", "si", "sí"}

    EASYOCR_READER = easyocr.Reader(EASYOCR_LANGS, gpu=easyocr_use_gpu, verbose=False)
    OCR_AVAILABLE = True
    OCR_BACKEND = "easyocr"
    print(f"[INFO] OCR (easyocr) cargado correctamente | langs={EASYOCR_LANGS} | gpu={easyocr_use_gpu}")
except ImportError as e:
    print(f"[WARNING] easyocr no esta instalado ({e}) -> se usara modo MANUAL (captcha a mano)")
except Exception as e:
    print(f"[WARNING] Error al cargar easyocr: {e} -> modo MANUAL")


def _is_scheduled_mode() -> bool:
    return os.getenv("RUN_MODE", "manual").strip().lower() == "scheduled"


def corregir_captcha_ocr(texto_raw: str) -> str:
    if not texto_raw:
        return ""
    texto = texto_raw.strip().upper().replace(" ", "").replace("\n", "").replace("\r", "")
    texto = "".join(c for c in texto if c.isalnum())
    return texto


def validar_captcha_texto(texto: str) -> bool:
    if not texto or len(texto) != 5:
        return False
    return texto.isalnum()


def captcha_fuzzy_normalize(texto: str) -> str:
    mapa = {
        "O": "0", "Q": "0", "D": "0",
        "I": "1", "L": "1",
        "Z": "2",
        "S": "5",
        "T": "7",
        "B": "8",
        "G": "6",
    }
    base = "".join(c for c in str(texto or "").upper() if c.isalnum())
    return "".join(mapa.get(c, c) for c in base)


def generar_candidatos_len5(texto: str) -> set:
    limpio = "".join(c for c in str(texto or "").upper() if c.isalnum())
    candidatos = set()

    if len(limpio) == 5:
        candidatos.add(limpio)

    if 6 <= len(limpio) <= 8:
        quitar = len(limpio) - 5
        for idxs in itertools.combinations(range(len(limpio)), quitar):
            rec = "".join(ch for i, ch in enumerate(limpio) if i not in idxs)
            if len(rec) == 5 and rec.isalnum():
                candidatos.add(rec)

    expandidos = set(candidatos)
    swaps = {
        "0": ["O", "Q", "D"],
        "1": ["I", "L"],
        "2": ["Z"],
        "3": ["E"],
        "6": ["G"],
        "7": ["T"],
        "8": ["B", "S"],
        "5": ["S"],
        "E": ["3"],
        "B": ["8"],
    }
    for candidato in list(candidatos):
        for i, ch in enumerate(candidato):
            for alt in swaps.get(ch, []):
                expandidos.add(candidato[:i] + alt + candidato[i + 1 :])

    return expandidos


def seleccionar_mejor_captcha_por_consenso(observaciones: list) -> str:
    if not observaciones:
        return ""

    sets_obs = []
    for obs in observaciones:
        candidatos = generar_candidatos_len5(obs)
        if candidatos:
            sets_obs.append(candidatos)

    if not sets_obs:
        return ""

    universo = set().union(*sets_obs)
    mejor = ""
    mejor_score = -1
    mejor_exact = -1

    for cand in universo:
        cand_fuzzy = captcha_fuzzy_normalize(cand)
        score = 0
        exact = 0
        for cands_obs in sets_obs:
            fuzzy_obs = {captcha_fuzzy_normalize(x) for x in cands_obs}
            if cand_fuzzy in fuzzy_obs:
                score += 1
            if cand in cands_obs:
                exact += 1

        if (score > mejor_score) or (score == mejor_score and exact > mejor_exact):
            mejor = cand
            mejor_score = score
            mejor_exact = exact

    return mejor if validar_captcha_texto(mejor) else ""


def medir_consenso_captcha(candidato: str, observaciones: list) -> tuple:
    if not candidato:
        return 0, 0, 0

    sets_obs = []
    for obs in observaciones:
        candidatos = generar_candidatos_len5(obs)
        if candidatos:
            sets_obs.append(candidatos)

    if not sets_obs:
        return 0, 0, 0

    cand_fuzzy = captcha_fuzzy_normalize(candidato)
    fuzzy_hits = 0
    exact_hits = 0
    for cands_obs in sets_obs:
        fuzzy_obs = {captcha_fuzzy_normalize(x) for x in cands_obs}
        if cand_fuzzy in fuzzy_obs:
            fuzzy_hits += 1
        if candidato in cands_obs:
            exact_hits += 1

    return fuzzy_hits, exact_hits, len(sets_obs)


def captcha_tiene_ambiguedad(texto: str) -> bool:
    t = "".join(c for c in str(texto or "").upper() if c.isalnum())
    if len(t) != 5:
        return True

    grupos_ambiguos = [
        set("A4"),
        set("1I"),
        set("I7"),
        set("S8"),
        set("S5"),
    ]

    for ch in t:
        for grupo in grupos_ambiguos:
            if ch in grupo:
                return True
    return False


def solve_captcha_manual(page):
    if _is_scheduled_mode():
        raise Exception(
            "CAPTCHA_MANUAL_REQUERIDO_EN_SCHEDULED: OCR no resolvio captcha y no hay entrada interactiva"
        )
    print("\n[MANUAL] MODO MANUAL ACTIVADO")
    print("Completa el codigo de verificacion en la ventana del navegador")
    input("[INFO] Cuando hayas escrito el captcha -> presiona ENTER para continuar...")


def preprocesar_imagen_captcha(img_bytes: bytes, variante: int = 0):
    img = Image.open(BytesIO(img_bytes))
    img = img.convert("L")
    if variante == 0:
        img = ImageEnhance.Contrast(img).enhance(3.5)
        w, h = img.size
        img = img.resize((w * 4, h * 4), Image.LANCZOS)
        img = img.filter(ImageFilter.MedianFilter(size=3))
        img = ImageOps.invert(img)
        img = img.point(lambda p: 255 if p > 130 else 0)
        img = ImageEnhance.Sharpness(img).enhance(3.0)
    elif variante == 1:
        img = ImageEnhance.Contrast(img).enhance(2.5)
        w, h = img.size
        img = img.resize((w * 3, h * 3), Image.LANCZOS)
        img = img.filter(ImageFilter.MedianFilter(size=5))
        img = img.point(lambda p: 255 if p > 160 else 0)
        img = ImageEnhance.Sharpness(img).enhance(2.0)
    else:
        img = ImageEnhance.Contrast(img).enhance(4.0)
        w, h = img.size
        img = img.resize((w * 5, h * 5), Image.LANCZOS)
        img = img.filter(ImageFilter.GaussianBlur(radius=0.5))
        img = ImageOps.invert(img)
        img = img.point(lambda p: 255 if p > 110 else 0)
        img = ImageEnhance.Sharpness(img).enhance(4.0)
    return img


def _leer_texto_easyocr_desde_imagen(img, decoder: str = "greedy") -> str:
    if EASYOCR_READER is None or np is None:
        return ""

    try:
        arr = np.array(img)
    except Exception:
        return ""

    try:
        resultados = EASYOCR_READER.readtext(
            arr,
            detail=0,
            paragraph=False,
            allowlist=EASYOCR_ALLOWLIST,
            decoder=decoder,
        )
    except TypeError:
        resultados = EASYOCR_READER.readtext(
            arr,
            detail=0,
            paragraph=False,
            allowlist=EASYOCR_ALLOWLIST,
        )
    except Exception:
        return ""

    if isinstance(resultados, (list, tuple)):
        return " ".join(str(x or "") for x in resultados).strip()
    return str(resultados or "").strip()


def solve_captcha_ocr_base(
    page,
    captcha_img_selector: str,
    boton_refresh_selector: str = None,
    contexto: str = "CAPTCHA",
    evitar_ambiguos: bool = False,
    min_fuzzy_hits: int = 0,
    max_intentos=6,
):
    if not OCR_AVAILABLE:
        return None

    num_variantes = 3
    decoders = ["greedy", "beamsearch"]

    intento = 0
    while True:
        if max_intentos is not None and max_intentos > 0 and intento >= max_intentos:
            break
        intento += 1
        try:
            total_txt = str(max_intentos) if (max_intentos is not None and max_intentos > 0) else "inf"
            print(f" OCR {contexto}: intento interno {intento}/{total_txt}...")
            page.wait_for_timeout(200)
            img_bytes = page.locator(captcha_img_selector).screenshot(type="png")

            mejor_texto = None
            observaciones = []
            for variante in range(num_variantes):
                img = preprocesar_imagen_captcha(img_bytes, variante=variante)
                for decoder in decoders:
                    texto_raw = _leer_texto_easyocr_desde_imagen(img, decoder=decoder)
                    texto = corregir_captcha_ocr(texto_raw)
                    observaciones.append(texto)

                    if validar_captcha_texto(texto):
                        print(f"   -> Variante {variante}, Decoder {decoder}: '{texto_raw}' -> '{texto}' [INFO]")
                        mejor_texto = texto
                        break
                    print(f"   -> Variante {variante}, Decoder {decoder}: '{texto_raw}' -> '{texto}' (len={len(texto)}) [WARNING]")
                if mejor_texto:
                    break

            if not mejor_texto:
                mejor_texto = seleccionar_mejor_captcha_por_consenso(observaciones)
                if validar_captcha_texto(mejor_texto):
                    print(f"   [INFO] CAPTCHA por consenso -> Usando: {mejor_texto}")

            if mejor_texto:
                if evitar_ambiguos:
                    fuzzy_hits, exact_hits, total_hits = medir_consenso_captcha(mejor_texto, observaciones)
                    print(f"    Consenso OCR: fuzzy={fuzzy_hits}/{total_hits}, exacto={exact_hits}/{total_hits}")

                    es_ambiguo = captcha_tiene_ambiguedad(mejor_texto)
                    consenso_debil = total_hits > 0 and fuzzy_hits < min_fuzzy_hits

                    if es_ambiguo or consenso_debil:
                        motivo = "ambiguo" if es_ambiguo else "consenso debil"
                        print(f"   [WARNING] CAPTCHA {motivo} detectado ('{mejor_texto}') -> se solicitara uno nuevo")
                        if boton_refresh_selector:
                            page.locator(boton_refresh_selector).click(force=True)
                            page.wait_for_timeout(500)
                            continue

                print(f"   [INFO] CAPTCHA valido -> Usando: {mejor_texto}")
                return mejor_texto

            if boton_refresh_selector:
                print("   [WARNING] Ninguna combinacion dio resultado -> Refrescando CAPTCHA...")
                print("-------------------------------------------")
                page.locator(boton_refresh_selector).click(force=True)
                page.wait_for_timeout(500)
            else:
                print("   [WARNING] Ninguna combinacion dio resultado (sin boton refresh configurado)")

        except Exception as e:
            print(f"   Error en intento {intento}: {str(e)}")
            page.wait_for_timeout(300)

    if max_intentos is None or max_intentos <= 0:
        print(f"[ERROR] No se pudo resolver {contexto} automaticamente (modo sin limite agotado por salida externa) -> modo manual")
    else:
        print(f"[ERROR] No se pudo resolver {contexto} automaticamente despues de {max_intentos} intentos -> modo manual")
    return None


def solve_captcha_ocr_generico(
    page,
    captcha_img_selector: str,
    boton_refresh_selector: str = None,
    contexto: str = "CAPTCHA",
    evitar_ambiguos: bool = False,
):
    return solve_captcha_ocr_base(
        page,
        captcha_img_selector=captcha_img_selector,
        boton_refresh_selector=boton_refresh_selector,
        contexto=contexto,
        evitar_ambiguos=evitar_ambiguos,
        min_fuzzy_hits=6,
    )


def solve_login_captcha(page, selectors: dict):
    return solve_captcha_ocr_base(
        page,
        captcha_img_selector=selectors["captcha_img"],
        boton_refresh_selector=selectors["boton_refresh"],
        contexto="CAPTCHA",
        evitar_ambiguos=False,
        min_fuzzy_hits=0,
    )
