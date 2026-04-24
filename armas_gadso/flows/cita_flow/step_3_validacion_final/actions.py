from __future__ import annotations

import os
import re
import time

from .screenshots import capturar_error_validacion_final
from .selectors import SELECTORS


def completar_fase_3_resumen(page, deps: dict):
    """Paso 3: resolver captcha del resumen y aceptar terminos y condiciones."""
    solve_captcha_ocr_base = deps["solve_captcha_ocr_base"]
    escribir_input_rapido = deps["escribir_input_rapido"]
    solve_captcha_manual = deps["solve_captcha_manual"]
    validar_turno_duplicado_o_lanzar = deps["validar_turno_duplicado_o_lanzar"]
    turno_duplicado_error = deps["turno_duplicado_error"]

    print("\n Completando Fase 3 (Resumen de cita)...")

    try:
        page.locator(SELECTORS["fase3_panel"]).wait_for(state="visible", timeout=12000)
    except Exception as e:
        try:
            validar_turno_duplicado_o_lanzar(page, max_wait_ms=4500)
        except turno_duplicado_error as e_dup:
            raise turno_duplicado_error(str(e_dup)) from e
        raise

    captcha_text = solve_captcha_ocr_base(
        page,
        captcha_img_selector=SELECTORS["fase3_captcha_img"],
        boton_refresh_selector=None,
        contexto="CAPTCHA Fase 3",
        evitar_ambiguos=False,
        min_fuzzy_hits=0,
        max_intentos=None,
    )

    if captcha_text and len(captcha_text) == 5:
        escribir_input_rapido(page, SELECTORS["fase3_captcha_input"], captcha_text)
        print(f"   [INFO] CAPTCHA Fase 3 escrito: {captcha_text}")
    else:
        print("   [WARNING] OCR no resolvio CAPTCHA Fase 3; usa ingreso manual en el navegador")
        solve_captcha_manual(page)

    checkbox_input = page.locator(SELECTORS["fase3_terminos_input"])
    checkbox_box = page.locator(SELECTORS["fase3_terminos_box"])
    checkbox_box.wait_for(state="visible", timeout=7000)

    marcado = False
    try:
        marcado = checkbox_input.is_checked()
    except Exception:
        marcado = False

    if not marcado:
        checkbox_box.click()
        page.wait_for_timeout(180)

    try:
        marcado = checkbox_input.is_checked()
    except Exception:
        marcado = False

    if not marcado:
        clase_box = checkbox_box.get_attribute("class") or ""
        if "ui-state-active" in clase_box:
            marcado = True

    if not marcado:
        raise Exception("No se pudo marcar 'Acepto los terminos y condiciones de Sucamec'")

    print("   [INFO] Terminos y condiciones marcados")


def generar_cita_final_con_reintento_rapido(page, deps: dict, registro: dict | None = None, max_intentos: int = 3):
    """
    Hace click en 'Generar Cita' y, si detecta error de captcha/validacion,
    reintenta rapido regenerando el captcha de Fase 3.
    """
    normalizar_texto_comparable = deps["normalizar_texto_comparable"]
    solve_captcha_ocr_base = deps["solve_captcha_ocr_base"]
    escribir_input_rapido = deps["escribir_input_rapido"]
    solve_captcha_manual = deps["solve_captcha_manual"]
    cupos_ocupados_error = deps["cupos_ocupados_error"]

    print("\n Paso final opcional: Generar Cita (reintento rapido)")

    try:
        confirm_window_s = float(str(os.getenv("GENERAR_CITA_CONFIRM_WINDOW_S", "2.5") or "2.5").strip())
    except Exception:
        confirm_window_s = 2.5
    if confirm_window_s < 1.5:
        confirm_window_s = 1.5

    try:
        confirm_grace_s = float(str(os.getenv("GENERAR_CITA_CONFIRM_GRACE_S", "2.0") or "2.0").strip())
    except Exception:
        confirm_grace_s = 2.0
    if confirm_grace_s < 0:
        confirm_grace_s = 0.0

    boton_generar = page.locator(SELECTORS["fase3_boton_generar_cita"])
    boton_generar.wait_for(state="visible", timeout=10000)

    def recolectar_mensajes_ui(max_por_selector: int = 4) -> list:
        textos = []
        selectores = [
            ".ui-growl-item .ui-growl-title",
            ".ui-growl-item .ui-growl-message",
            ".ui-growl-message-error",
            ".ui-messages-error",
            ".ui-message-error",
            ".mensajeError",
        ]
        for selector in selectores:
            try:
                loc = page.locator(selector)
                total = min(loc.count(), max_por_selector)
                for i in range(total):
                    txt = (loc.nth(i).inner_text() or "").strip()
                    if txt:
                        textos.append(txt)
            except Exception:
                pass
        try:
            buffer_msgs = page.evaluate(
                """
                () => (window.__armasGrowlBuffer || []).slice(-20).map(x => x && x.text ? String(x.text) : '')
                """
            )
            if isinstance(buffer_msgs, list):
                for txt in buffer_msgs:
                    t = str(txt or "").strip()
                    if t:
                        textos.append(t)
        except Exception:
            pass

        vistos = set()
        unicos = []
        for t in textos:
            if t not in vistos:
                vistos.add(t)
                unicos.append(t)
        return unicos

    def detectar_error_captcha(mensajes: list) -> str:
        for msg in mensajes:
            if re.search(r"captcha.*incorrect|error.*captcha|captcha", msg, flags=re.IGNORECASE):
                return msg
        return ""

    def capturar_error_codigo_validacion(motivo: str):
        if not registro:
            return None
        return capturar_error_validacion_final(page, registro, motivo)

    def detectar_error_cupos_ocupados(mensajes: list) -> str:
        patrones = [
            r"cupos?.*horario.*ocupad",
            r"cupos?.*ocupad",
            r"escoja\s+otro\s+horario",
            r"ya\s+han\s+sido\s+ocupados",
        ]
        for msg in mensajes:
            msg_norm = normalizar_texto_comparable(msg)
            if "CUPOS" in msg_norm and "HORARIO" in msg_norm and "OCUP" in msg_norm:
                return msg
            if any(re.search(p, msg, flags=re.IGNORECASE) for p in patrones):
                return msg
        return ""

    def detectar_exito_fuerte() -> bool:
        try:
            if boton_generar.count() == 0 or not boton_generar.first.is_visible():
                return True
        except Exception:
            return True

        try:
            url_actual = page.url or ""
            if "/faces/aplicacion/" in url_actual and "GestionCitas.xhtml" not in url_actual:
                if page.locator(SELECTORS["fase3_boton_generar_cita"]).count() == 0:
                    return True
        except Exception:
            pass
        return False

    def detectar_exito_fuerte_estable() -> bool:
        if not detectar_exito_fuerte():
            return False
        page.wait_for_timeout(150)
        return detectar_exito_fuerte()

    def observar_post_click_hasta(deadline_ts: float, error_captcha_msg: str, error_cupos_msg: str, ultimo_error: str):
        while time.time() < deadline_ts:
            mensajes = recolectar_mensajes_ui()
            if mensajes:
                for msg in mensajes:
                    if not ultimo_error:
                        ultimo_error = msg
                candidato_cupos = detectar_error_cupos_ocupados(mensajes)
                if candidato_cupos:
                    error_cupos_msg = candidato_cupos
                    break
                candidato = detectar_error_captcha(mensajes)
                if candidato:
                    error_captcha_msg = candidato
                    break

            if detectar_exito_fuerte_estable():
                return True, error_captcha_msg, error_cupos_msg, ultimo_error

            page.wait_for_timeout(120)

        return False, error_captcha_msg, error_cupos_msg, ultimo_error

    for intento in range(1, max_intentos + 1):
        inicio_validacion = time.time()
        print(f"    Intento generar cita {intento}/{max_intentos}")
        boton_generar.click(timeout=10000)

        error_captcha_msg = ""
        error_cupos_msg = ""
        ultimo_error = ""
        deadline = time.time() + confirm_window_s
        confirmado, error_captcha_msg, error_cupos_msg, ultimo_error = observar_post_click_hasta(
            deadline,
            error_captcha_msg,
            error_cupos_msg,
            ultimo_error,
        )

        if not confirmado and not error_captcha_msg and not error_cupos_msg and confirm_grace_s > 0:
            print(
                "   [INFO] Sin senal clara tras click en 'Generar Cita'. "
                f"Aplicando ventana extra de confirmacion ({confirm_grace_s:.2f}s)..."
            )
            deadline_grace = time.time() + confirm_grace_s
            confirmado, error_captcha_msg, error_cupos_msg, ultimo_error = observar_post_click_hasta(
                deadline_grace,
                error_captcha_msg,
                error_cupos_msg,
                ultimo_error,
            )

        if confirmado:
            tiempo = time.time() - inicio_validacion
            print(f"   [INFO] Generar Cita confirmado en {tiempo:.2f}s")
            print(f"   -> URL: {page.url}")
            return True

        tiempo = time.time() - inicio_validacion
        if error_cupos_msg:
            print(f"   [WARNING] Mensaje de cupos detectado: {error_cupos_msg}")
            raise cupos_ocupados_error(error_cupos_msg)
        if error_captcha_msg:
            capturar_error_codigo_validacion(f"codigo_invalido_i{intento}")
            print(f"   [WARNING] Mensaje captcha detectado: {error_captcha_msg}")
        elif ultimo_error:
            print(f"   [WARNING] Mensaje detectado: {ultimo_error}")
        print(f"    Validacion final: {tiempo:.2f}s")

        if not error_captcha_msg:
            raise Exception(
                "No se pudo confirmar la generacion de cita de forma robusta "
                "(sin senales claras de exito y sin captcha incorrecto explicito)"
            )

        nuevo_captcha = solve_captcha_ocr_base(
            page,
            captcha_img_selector=SELECTORS["fase3_captcha_img"],
            boton_refresh_selector=SELECTORS["fase3_boton_refresh"],
            contexto="CAPTCHA Fase 3 (reintento final)",
            evitar_ambiguos=False,
            min_fuzzy_hits=0,
            max_intentos=3,
        )

        if nuevo_captcha and len(nuevo_captcha) == 5:
            escribir_input_rapido(page, SELECTORS["fase3_captcha_input"], nuevo_captcha)
            print(f"   [INFO] CAPTCHA reintento escrito: {nuevo_captcha}")
        else:
            print("   [WARNING] OCR no resolvio captcha en reintento final; pasar a ingreso manual")
            solve_captcha_manual(page)

        try:
            if not page.locator(SELECTORS["fase3_terminos_input"]).is_checked():
                page.locator(SELECTORS["fase3_terminos_box"]).click()
                page.wait_for_timeout(150)
        except Exception:
            pass

    capturar_error_codigo_validacion("codigo_invalido_final")
    raise Exception("No se pudo generar cita tras reintentos rapidos")
