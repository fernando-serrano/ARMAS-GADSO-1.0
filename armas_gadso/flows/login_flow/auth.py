from __future__ import annotations

import time

from .browser import escribir_input_jsf, escribir_input_rapido
from .selectors import LOGIN_SELECTORS


def validar_resultado_login_por_ui(page, timeout_ms: int = 3000):
    """
    Determina resultado de login por señales de UI:
    - Exito: aparece menu principal/controles de sesion autenticada.
    - Falla: aparece mensaje de error de validacion/captcha.
    """
    inicio = time.time()

    selectores_exito = [
        "#j_idt11\\:menuPrincipal",
        "#j_idt11\\:j_idt18",
        "form#gestionCitasForm",
    ]
    selectores_error = [
        ".ui-messages-error",
        ".ui-message-error",
        ".ui-growl-message-error",
        ".mensajeError",
        "[class*='error']",
        "[class*='Error']",
    ]

    while (time.time() - inicio) * 1000 < timeout_ms:
        try:
            if "/faces/aplicacion/inicio.xhtml" in (page.url or ""):
                return True, None, (time.time() - inicio)
        except Exception:
            pass

        for selector in selectores_exito:
            try:
                loc = page.locator(selector)
                if loc.count() > 0 and loc.first.is_visible():
                    return True, None, (time.time() - inicio)
            except Exception:
                pass

        for selector in selectores_error:
            try:
                loc = page.locator(selector)
                total = min(loc.count(), 3)
                for i in range(total):
                    txt = (loc.nth(i).inner_text() or "").strip()
                    if txt:
                        return False, txt, (time.time() - inicio)
            except Exception:
                pass

        page.wait_for_timeout(120)

    try:
        if "/faces/aplicacion/inicio.xhtml" in (page.url or ""):
            return True, None, (time.time() - inicio)
    except Exception:
        pass

    for selector in selectores_exito:
        try:
            if page.locator(selector).count() > 0:
                return True, None, (time.time() - inicio)
        except Exception:
            pass

    mensaje_error = None
    for selector in selectores_error:
        try:
            loc = page.locator(selector)
            total = min(loc.count(), 3)
            for i in range(total):
                txt = (loc.nth(i).inner_text() or "").strip()
                if txt:
                    mensaje_error = txt
                    break
            if mensaje_error:
                break
        except Exception:
            pass

    return False, mensaje_error, (time.time() - inicio)


def activar_pestana_autenticacion_tradicional(page, selectors: dict | None = None):
    """Activa la pestaña tradicional sin depender de ids j_idt variables."""
    sel = selectors or LOGIN_SELECTORS
    try:
        campo_doc = page.locator(sel["numero_documento"])
        if campo_doc.count() > 0 and campo_doc.first.is_visible():
            print("[INFO] Pestaña tradicional ya activa")
            return
    except Exception:
        pass

    candidatos = [
        sel["tab_tradicional"],
        '#tabViewLogin a:has-text("Autenticación Tradicional")',
        '#tabViewLogin a:has-text("Autenticacion Tradicional")',
    ]

    ultimo_error = None
    for selector in candidatos:
        try:
            tab = page.locator(selector).first
            tab.wait_for(state="visible", timeout=6000)
            tab.click(timeout=6000)
            page.locator(sel["numero_documento"]).wait_for(state="visible", timeout=8000)
            print("[INFO] Pestaña 'Autenticación Tradicional' seleccionada")
            return
        except Exception as exc:
            ultimo_error = exc

    raise Exception(
        "No se pudo activar la pestaña 'Autenticación Tradicional'. "
        f"Detalle: {ultimo_error}"
    )


def realizar_login_sel(
    page,
    credenciales_grupo: dict,
    grupo_ruc: str,
    captcha_solver,
    manual_solver,
    login_validation_timeout_ms: int,
    selectors: dict | None = None,
):
    """Ejecuta el formulario de login tradicional y valida sesion autenticada."""
    sel = selectors or LOGIN_SELECTORS
    start_time = time.time()

    activar_pestana_autenticacion_tradicional(page, selectors=sel)

    page.locator(sel["numero_documento"]).wait_for(state="visible", timeout=8000)

    page.select_option(sel["tipo_doc_select"], value=credenciales_grupo["tipo_documento_valor"])
    page.wait_for_timeout(450)
    page.locator(sel["numero_documento"]).wait_for(state="visible", timeout=8000)
    escribir_input_jsf(page, sel["numero_documento"], credenciales_grupo["numero_documento"])
    escribir_input_rapido(page, sel["usuario"], credenciales_grupo["usuario"])
    escribir_input_rapido(page, sel["clave"], credenciales_grupo["contrasena"])
    print(f"[INFO] Credenciales llenadas para grupo {grupo_ruc}")

    captcha_text = captcha_solver(page)
    if captcha_text and len(captcha_text) == 5:
        escribir_input_rapido(page, sel["captcha_input"], captcha_text)
        print(f"[INFO] Captcha automatico: {captcha_text}")
    else:
        manual_solver(page)

    print("[INFO] Enviando login...")
    page.locator(sel["ingresar"]).click(timeout=10000)

    print("[INFO] Validando acceso...")
    url_ok, mensaje_error, tiempo_espera = validar_resultado_login_por_ui(
        page,
        timeout_ms=login_validation_timeout_ms,
    )

    if not url_ok:
        print("[ERROR] Login fallo - no se detecto sesion autenticada")
        print(f"   -> URL actual: {page.url}")
        if mensaje_error:
            print(f"   -> Error detectado: {mensaje_error}")
        print(f"[INFO] Tiempo validacion: {tiempo_espera:.2f} segundos")
        raise Exception("CAPTCHA incorrecto o credenciales invalidas")

    total_time = time.time() - start_time
    print("[INFO] Acceso exitoso")
    print(f"   -> URL: {page.url}")
    print(f"[INFO] Tiempo total login: {total_time:.2f} segundos")
    return True
