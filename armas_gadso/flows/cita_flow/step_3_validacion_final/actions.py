from __future__ import annotations

import os
import re
import time

from .screenshots import capturar_error_validacion_final
from .selectors import SELECTORS


def captcha_forzado_para_pruebas() -> str:
    """CAPTCHA fijo a inyectar en Fase 3 durante pruebas de extremo a extremo.

    Reemplaza al runner `test/run_test_easyocr.py` (eliminado en el refactor d9c38b8), que
    hacia lo mismo por monkeypatch sobre `legacy_flow.escribir_input_rapido`.

    Con un CAPTCHA deliberadamente incorrecto se recorre TODO el flujo hasta el paso final
    sin generar una cita real. Devuelve "" (inactivo, flujo productivo intacto) salvo que
    TEST_FORCED_CAPTCHA traiga exactamente 5 caracteres, que es lo que exige SUCAMEC: con
    cualquier otra longitud el flujo caeria al solver manual y se quedaria esperando a una
    persona, que es justo lo contrario de lo que se busca en una prueba desatendida.
    """
    valor = str(os.getenv("TEST_FORCED_CAPTCHA", "") or "").strip().upper()
    if len(valor) != 5:
        if valor:
            print(
                "   [WARNING] TEST_FORCED_CAPTCHA='" + valor + "' ignorado: debe tener"
                " exactamente 5 caracteres"
            )
        return ""
    return valor


def completar_fase_3_resumen(page, deps: dict):
    """Paso 3: resolver captcha del resumen y aceptar terminos y condiciones."""
    solve_captcha_ocr_base = deps["solve_captcha_ocr_base"]
    escribir_input_rapido = deps["escribir_input_rapido"]
    solve_captcha_manual = deps["solve_captcha_manual"]
    validar_turno_duplicado_o_lanzar = deps["validar_turno_duplicado_o_lanzar"]
    turno_duplicado_error = deps["turno_duplicado_error"]
    esperar_fin_ajax = deps.get("esperar_fin_ajax")

    print("\n Completando Fase 3 (Resumen de cita)...")

    # Confirmar que el AJAX que renderiza el resumen termino antes de buscar el captcha
    # (no actuar sobre una vista a medio cargar).
    if esperar_fin_ajax:
        esperar_fin_ajax(page)

    # El servidor SUCAMEC renderiza el resumen tras un AJAX que en la ventana de
    # medianoche puede tardar muchisimo: en logs reales del 00:00, 60s no bastaron para
    # que apareciera la imagen del captcha. Subimos el default a 120s (2 min) como TECHO
    # tolerante; el wait_for continua APENAS aparezca el elemento (no es espera fija).
    # Configurable via env FASE3_PANEL_TIMEOUT_MS.
    try:
        fase3_timeout_ms = int(str(os.getenv("FASE3_PANEL_TIMEOUT_MS", "120000") or "120000").strip())
    except Exception:
        fase3_timeout_ms = 120000
    if fase3_timeout_ms < 12000:
        fase3_timeout_ms = 12000

    # Esperamos el ELEMENTO que realmente necesitamos (la imagen del captcha), no solo el
    # panelPaso4: a medianoche el resumen puede renderizarse como panelPaso3_content, y
    # antes esto causaba timeout aunque la Fase 3 ya estuviera lista.
    try:
        page.locator(SELECTORS["fase3_captcha_img"]).wait_for(state="visible", timeout=fase3_timeout_ms)
    except Exception as e:
        try:
            validar_turno_duplicado_o_lanzar(page, max_wait_ms=4500)
        except turno_duplicado_error as e_dup:
            raise turno_duplicado_error(str(e_dup)) from e
        raise

    forzado = captcha_forzado_para_pruebas()
    if forzado:
        # Se omite el OCR a proposito: no aporta nada a la prueba y evita el bucle de
        # reintentos sobre una imagen que igualmente se va a ignorar.
        captcha_text = forzado
        print(
            "   [TEST] CAPTCHA Fase 3 FORZADO a '" + forzado + "' por TEST_FORCED_CAPTCHA:"
            " la cita NO se generara"
        )
    else:
        captcha_text = solve_captcha_ocr_base(
            page,
            captcha_img_selector=SELECTORS["fase3_captcha_img"],
            # Pasamos el boton de refresh y un limite finito: sin esto, si el OCR no
            # lee el captcha, el bucle 'while True' giraba para siempre sobre la MISMA
            # imagen (cuelgue infinito de un worker en produccion). Ahora pide captcha
            # nuevo en cada intento y se rinde tras un maximo.
            boton_refresh_selector=SELECTORS["fase3_boton_refresh"],
            contexto="CAPTCHA Fase 3",
            evitar_ambiguos=False,
            min_fuzzy_hits=0,
            max_intentos=10,
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
        if esperar_fin_ajax:
            esperar_fin_ajax(page)  # techo 45s; continua al instante (el check es client-side)
        else:
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
        confirm_window_s = float(str(os.getenv("GENERAR_CITA_CONFIRM_WINDOW_S", "20.0") or "20.0").strip())
    except Exception:
        confirm_window_s = 20.0
    if confirm_window_s < 1.5:
        confirm_window_s = 1.5

    try:
        confirm_grace_s = float(str(os.getenv("GENERAR_CITA_CONFIRM_GRACE_S", "5.0") or "5.0").strip())
    except Exception:
        confirm_grace_s = 5.0
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

    def detectar_error_certificado_salud(mensajes: list) -> str:
        # Rechazo terminal de SUCAMEC: la persona no tiene certificado de salud vigente
        # para la fecha de la cita. Conservamos la frase con ambas fechas como motivo.
        for msg in mensajes:
            m = normalizar_texto_comparable(msg)
            if "CERTIFICADO DE SALUD" in m and ("VIGENTE" in m or "VENCIMIENTO" in m):
                idx = msg.lower().find("la persona no cuenta")
                if idx < 0:
                    idx = 0
                return re.sub(r"\s+", " ", msg[idx:idx + 300]).strip()
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

    estado_cert_salud = {"msg": ""}

    def observar_post_click_hasta(deadline_ts: float, error_captcha_msg: str, error_cupos_msg: str, ultimo_error: str):
        while time.time() < deadline_ts:
            mensajes = recolectar_mensajes_ui()
            if mensajes:
                for msg in mensajes:
                    if not ultimo_error:
                        ultimo_error = msg
                # El rechazo por certificado de salud vencido es terminal y debe primar
                # sobre cualquier deteccion de exito (el growl puede desaparecer en segundos).
                candidato_cert = detectar_error_certificado_salud(mensajes)
                if candidato_cert:
                    estado_cert_salud["msg"] = candidato_cert
                    break
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
        estado_cert_salud["msg"] = ""
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

        if estado_cert_salud["msg"]:
            mensaje_cert = estado_cert_salud["msg"]
            print(f"   [WARNING] Certificado de salud vencido detectado: {mensaje_cert}")
            if registro is not None:
                registro["_terminal_reason_label"] = mensaje_cert
                registro["_cert_salud_msg"] = mensaje_cert
                ruta_cert = capturar_error_codigo_validacion("certificado_salud_vencido")
                if ruta_cert:
                    registro["_step2_error_screenshot_path"] = str(ruta_cert)
            raise Exception(mensaje_cert)

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

        forzado_reintento = captcha_forzado_para_pruebas()
        if forzado_reintento:
            nuevo_captcha = forzado_reintento
            print(
                "   [TEST] CAPTCHA de reintento FORZADO a '" + forzado_reintento + "'"
                " por TEST_FORCED_CAPTCHA"
            )
        else:
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
