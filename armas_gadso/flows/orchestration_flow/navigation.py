from __future__ import annotations

import os
import time

from .sync import esperar_fin_ajax_primefaces


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, str(default)) or default).strip())
    except Exception:
        return default


def pagina_muestra_servicio_no_disponible(page, selectors: dict) -> bool:
    """Detecta paginas de caida de SUCAMEC: HTTP 503 / Service Unavailable y tambien
    'Error del servidor / Ha ocurrido un error interno en el sistema' (que pide volver a
    ingresar al sistema). Si algun elemento valido del portal esta visible, retorna False."""
    selectores_ok = [
        selectors["tab_tradicional"],
        selectors["numero_documento"],
        '[id$=":menuPrincipal"]',
        "form#gestionCitasForm",
        selectors["reserva_form"],
    ]
    for sel in selectores_ok:
        try:
            loc = page.locator(sel)
            if loc.count() > 0 and loc.first.is_visible():
                return False
        except Exception:
            pass

    _SEÑALES_CAIDA = [
        "SERVICE UNAVAILABLE",
        "HTTP STATUS 503",
        "503 - SERVICE UNAVAILABLE",
        # Error interno de SUCAMEC: "Error del servidor / Ha ocurrido un error interno en
        # el sistema. Por favor vuelva a ingresar al sistema." (link a login.xhtml)
        "ERROR DEL SERVIDOR",
        "HA OCURRIDO UN ERROR INTERNO EN EL SISTEMA",
        "POR FAVOR VUELVA A INGRESAR AL SISTEMA",
    ]

    try:
        titulo = (page.title() or "").strip().upper()
        if any(s in titulo for s in _SEÑALES_CAIDA):
            return True
    except Exception:
        pass

    try:
        html = (page.content() or "").upper()
        if any(s in html for s in _SEÑALES_CAIDA):
            return True
    except Exception:
        pass

    return False


def esperar_hasta_servicio_disponible(page, url_objetivo: str, selectors: dict, espera_segundos: int = 8, max_intentos: int | None = None):
    """Reintenta mientras la pagina muestre señal de caida (503 o error interno de SUCAMEC).

    Recupera re-ingresando por la URL de login (que es lo que pide la propia pagina de error).
    Tiene TOPE de reintentos para no quedarse ejecutando infinitamente: al agotarse, lanza una
    excepcion marcada como RELOGIN_UI_DESYNC para que el orquestador reintente el login/grupo.
    """
    if max_intentos is None:
        try:
            max_intentos = int(str(os.getenv("SERVICIO_NO_DISPONIBLE_MAX_RETRIES", "20") or "20").strip())
        except Exception:
            max_intentos = 20

    intento = 0
    while pagina_muestra_servicio_no_disponible(page, selectors):
        intento += 1
        if max_intentos > 0 and intento > max_intentos:
            raise Exception(
                "RELOGIN_UI_DESYNC: SUCAMEC sigue caido (503 o error interno del sistema) "
                f"tras {max_intentos} reintentos de reingreso"
            )
        print(f"[WARNING] SUCAMEC no disponible (503/error interno). Reintento {intento}/{max_intentos} en {espera_segundos}s...")
        page.wait_for_timeout(max(1000, int(espera_segundos * 1000)))
        try:
            page.goto(url_objetivo, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            print(f"    Error al reintentar acceso: {e}")


def seleccionar_en_selectonemenu(page, trigger_selector: str, panel_selector: str, label_selector: str, valor: str, nombre_campo: str, fecha_no_disponible_error):
    """Selecciona una opcion PrimeFaces SelectOneMenu por data-label o texto visible."""
    trigger = page.locator(trigger_selector)
    trigger.wait_for(state="visible", timeout=12000)
    trigger.click()

    panel = page.locator(panel_selector)
    panel.wait_for(state="visible", timeout=7000)

    if str(nombre_campo or "").strip().lower() == "fecha":
        items = panel.locator("li.ui-selectonemenu-item")
        try:
            items.first.wait_for(state="visible", timeout=5000)
        except Exception as e:
            raise fecha_no_disponible_error(
                f"No hay opciones visibles en el combo de Fecha para '{valor}'."
            ) from e

        total = items.count()
        opciones_disponibles = []
        opcion_objetivo = None
        valor_norm = str(valor or "").strip().upper()
        for i in range(total):
            txt = (items.nth(i).inner_text() or "").strip()
            if not txt:
                continue
            opciones_disponibles.append(txt)
            if txt.upper() == valor_norm:
                opcion_objetivo = items.nth(i)

        if opcion_objetivo is None:
            raise fecha_no_disponible_error(
                f"Fecha '{valor}' no disponible en combo. Opciones actuales: {opciones_disponibles}"
            )

        opcion_objetivo.click()
        # No leer el label hasta que el AJAX de la seleccion termine (a medianoche
        # tarda); evita confirmar contra el valor viejo o tocar el combo a medio render.
        esperar_fin_ajax_primefaces(page)

        texto_label = page.locator(label_selector).inner_text().strip()
        if texto_label.upper() != valor_norm:
            raise Exception(
                f"No se confirmo la seleccion de {nombre_campo}. Esperado: '{valor}' | Actual: '{texto_label}'"
            )
        print(f"   [INFO] {nombre_campo} seleccionado: {texto_label}")
        return

    panel.locator(f"li[data-label='{valor}']").first.click()
    esperar_fin_ajax_primefaces(page)
    texto_label = page.locator(label_selector).inner_text().strip()
    if texto_label.upper() != valor.upper():
        raise Exception(
            f"No se confirmo la seleccion de {nombre_campo}. Esperado: '{valor}' | Actual: '{texto_label}'"
        )
    print(f"   [INFO] {nombre_campo} seleccionado: {texto_label}")


# --- Dialogos modales de bienvenida (comunicados de SUCAMEC) ---------------------
#
# SUCAMEC muestra dialogos PrimeFaces modales al entrar a inicio.xhtml (visto en vivo:
# "mainForm:dlgComunicadoInstitucional"). Su mascara .ui-widget-overlay.ui-dialog-mask
# cubre la pagina y ABSORBE los clicks: el click al menu CITAS reintenta hasta agotar el
# timeout de Playwright y el orquestador interpreta el login como fallido y reinicia.
#
# Se cierran por el boton estandar de la barra de titulo:
#   <a class="ui-dialog-titlebar-icon ui-dialog-titlebar-close ..." aria-label="Close">
#
# Es generico a proposito (cualquier mascara modal visible) para tolerar nuevos dialogos
# sin tocar codigo. Solo debe invocarse donde NINGUN dialogo es legitimo (justo tras
# autenticarse), nunca dentro de los pasos que si usan dialogos de confirmacion.

_JS_MASCARAS_MODALES_VISIBLES = r"""
() => Array.from(document.querySelectorAll('.ui-widget-overlay.ui-dialog-mask'))
    .filter(m => {
        const st = window.getComputedStyle(m);
        return st.display !== 'none' && st.visibility !== 'hidden';
    })
    .map(m => m.id || '')
    .filter(id => id)
"""

_JS_FORZAR_CIERRE_DIALOGO = r"""
(ids) => {
    const [idDialogo, idMascara] = ids;
    try {
        const w = window.PF ? window.PF(idDialogo) : null;
        if (w && typeof w.hide === 'function') { w.hide(); }
    } catch (e) { /* widget PrimeFaces no accesible */ }
    for (const id of [idDialogo, idMascara]) {
        const nodo = document.getElementById(id);
        if (nodo) { nodo.style.display = 'none'; }
    }
    return true;
}
"""


def _mascara_modal_visible(page, id_mascara: str) -> bool:
    try:
        loc = page.locator('[id="' + id_mascara + '"]')
        return loc.count() > 0 and loc.first.is_visible()
    except Exception:
        return False


def cerrar_dialogos_modales(
    page,
    timeout_click_ms: int | None = None,
    max_dialogos: int = 5,
    deadline: float | None = None,
) -> list:
    """Cierra los dialogos modales visibles y devuelve los ids que cerro.

    No lanza nunca: si un dialogo no se deja cerrar por su boton, se fuerza por JS; si aun
    asi persiste, se sigue adelante (el llamador ya valida el elemento que necesita).

    `deadline` (time.monotonic) permite al llamador acotar el trabajo a su presupuesto.
    """
    if timeout_click_ms is None:
        timeout_click_ms = _env_int("CIERRE_MODAL_CLICK_TIMEOUT_MS", 5000)

    cerrados = []
    for _ in range(max(1, max_dialogos)):
        if deadline is not None and (deadline - time.monotonic()) <= 0:
            break
        try:
            mascaras = page.evaluate(_JS_MASCARAS_MODALES_VISIBLES) or []
        except Exception as e:
            # No silenciar: un evaluate roto es indistinguible de "no hay modales" y deja
            # el log sin rastro (paso en la corrida 20260908_100425).
            print("   [WARNING] No se pudo inspeccionar dialogos modales: " + str(e))
            mascaras = []
        if not mascaras:
            break

        id_mascara = str(mascaras[0])
        sufijo = "_modal"
        id_dialogo = id_mascara[: -len(sufijo)] if id_mascara.endswith(sufijo) else id_mascara

        cerrado = False
        try:
            boton = page.locator('[id="' + id_dialogo + '"] a.ui-dialog-titlebar-close').first
            boton.click(timeout=timeout_click_ms)
            cerrado = True
        except Exception:
            try:
                page.evaluate(_JS_FORZAR_CIERRE_DIALOGO, [id_dialogo, id_mascara])
                cerrado = True
                print("   [WARNING] Dialogo '" + id_dialogo + "' cerrado por JS (boton no respondio)")
            except Exception as e:
                print("   [WARNING] No se pudo cerrar el dialogo '" + id_dialogo + "': " + str(e))

        if not cerrado:
            break

        # Confirmar que la mascara dejo de interceptar antes de seguir. El cierre es JS
        # local (sin viaje al servidor), asi que no depende de la carga de SUCAMEC.
        for _ in range(_env_int("CIERRE_MODAL_ESPERA_CICLOS", 30)):
            if not _mascara_modal_visible(page, id_mascara):
                break
            if deadline is not None and (deadline - time.monotonic()) <= 0:
                break
            page.wait_for_timeout(100)

        if _mascara_modal_visible(page, id_mascara):
            print("   [WARNING] La mascara '" + id_mascara + "' sigue visible tras cerrar el dialogo")
            break

        cerrados.append(id_dialogo)
        print("   [INFO] Dialogo modal cerrado: " + id_dialogo)

    return cerrados


# El comunicado NO esta presente cuando termina la validacion del login: SUCAMEC lo pinta
# por AJAX un instante despues. Cerrarlo una sola vez antes de navegar no alcanza (log
# 20260908_100425: cerrar_dialogos_modales no vio ninguna mascara y el click siguiente si
# fue interceptado). Por eso los clicks se hacen tolerantes: si Playwright reporta que un
# overlay intercepta el puntero, se cierra el dialogo y se reintenta.

_SENAL_CLICK_INTERCEPTADO = "intercepts pointer events"


def _click_interceptado_por_overlay(error) -> bool:
    return _SENAL_CLICK_INTERCEPTADO in str(error or "")


def click_tolerante_a_modales(
    page,
    locator,
    descripcion: str,
    timeout_total_ms: int | None = None,
    timeout_intento_ms: int | None = None,
):
    """Hace click reintentando si un dialogo modal intercepta el puntero.

    PRESUPUESTO, NO TIMEOUTS FIJOS: en hora pico SUCAMEC responde lento y un click puede
    tardar legitimamente. El presupuesto TOTAL es el mismo que tenia el click antes de
    este helper (30s por defecto, configurable con CLICK_MODAL_TIMEOUT_MS), asi que ningun
    click pierde tiempo de espera respecto al comportamiento previo. Lo unico que cambia
    es que ese tiempo deja de malgastarse: si el fallo es una interceptacion por modal, se
    cierra el dialogo y se reintenta con lo que quede del presupuesto, en vez de reintentar
    a ciegas contra la mascara hasta agotarlo.

    Solo trata el caso de interceptacion: cualquier otro error se propaga tal cual para no
    enmascarar fallos reales.
    """
    if timeout_total_ms is None:
        timeout_total_ms = _env_int("CLICK_MODAL_TIMEOUT_MS", 30000)
    if timeout_intento_ms is None:
        timeout_intento_ms = _env_int("CLICK_MODAL_INTENTO_TIMEOUT_MS", 10000)

    deadline = time.monotonic() + max(1, timeout_total_ms) / 1000.0
    ultimo_error = None
    intento = 0

    while True:
        intento += 1
        restante_ms = int((deadline - time.monotonic()) * 1000)
        if restante_ms <= 0:
            break
        # Nunca gastar mas de lo que queda: el ultimo intento consume el resto del
        # presupuesto en lugar de cortar antes de tiempo.
        timeout_este_intento = min(max(timeout_intento_ms, 1000), restante_ms)

        try:
            locator.click(timeout=timeout_este_intento)
            return
        except Exception as e:
            if not _click_interceptado_por_overlay(e):
                raise
            ultimo_error = e
            print(
                "   [WARNING] Click en " + descripcion + " interceptado por un dialogo"
                " modal (intento " + str(intento) + ")"
            )
            if not cerrar_dialogos_modales(page, deadline=deadline):
                # Mascara presente pero sin dialogo cerrable todavia (render a medias):
                # dar un respiro corto antes de reintentar, sin exceder el presupuesto.
                if (deadline - time.monotonic()) <= 0:
                    break
                page.wait_for_timeout(400)

    if ultimo_error is not None:
        raise ultimo_error
    raise Exception(
        "No se pudo hacer click en " + descripcion + ": presupuesto agotado sin intentos"
    )


def navegar_reservas_citas(page, selectors: dict):
    """Abre el menu CITAS y hace click en RESERVAS DE CITAS."""
    print("\n Navegando a RESERVAS DE CITAS...")

    # Cierre oportunista: si el comunicado ya esta pintado, se quita aqui. Si todavia no
    # llego (caso habitual, lo pinta un AJAX posterior), lo cubre click_tolerante_a_modales.
    cerrar_dialogos_modales(page)

    menu_citas_header = page.locator(selectors["menu_citas_header"]).first
    menu_citas_header.wait_for(state="visible", timeout=12000)

    panel = page.locator(selectors["menu_citas_panel"]).first
    panel_visible = False
    try:
        panel_visible = panel.is_visible()
    except Exception:
        panel_visible = False

    if not panel_visible:
        click_tolerante_a_modales(page, menu_citas_header, "menu CITAS")
        panel.wait_for(state="visible", timeout=7000)
        print("   [INFO] Menu CITAS expandido")
    else:
        print("   [INFO] Menu CITAS ya estaba expandido")

    submenu = page.locator(selectors["submenu_reservas"]).first
    submenu.wait_for(state="visible", timeout=7000)
    click_tolerante_a_modales(page, submenu, "RESERVAS DE CITAS")
    page.wait_for_timeout(900)
    print("   [INFO] Click en 'RESERVAS DE CITAS'")


def seleccionar_tipo_cita_poligono(page, selectors: dict):
    """Selecciona el tipo de cita 'EXAMEN PARA POLIGONO DE TIRO'."""
    print("\n Seleccionando tipo de cita: EXAMEN PARA POLIGONO DE TIRO")

    trigger = page.locator(selectors["tipo_cita_trigger"]).first
    trigger.wait_for(state="visible", timeout=12000)
    trigger.click()

    panel = page.locator(selectors["tipo_cita_panel"]).first
    panel.wait_for(state="visible", timeout=7000)

    opcion = page.locator(selectors["tipo_cita_opcion_poligono"]).first
    try:
        opcion.wait_for(state="visible", timeout=2500)
        opcion.click()
    except Exception:
        print("   [WARNING] Opcion por data-label no visible -> buscando por texto")
        items = panel.locator("li.ui-selectonemenu-item")
        total = items.count()
        encontrada = False
        for i in range(total):
            item = items.nth(i)
            label = (item.get_attribute("data-label") or item.inner_text() or "").strip().upper()
            if "POLIGONO DE TIRO" in label or "POLÍGONO DE TIRO" in label:
                item.click()
                encontrada = True
                break
        if not encontrada:
            raise Exception("No se encontro opcion 'EXAMEN PARA POLIGONO DE TIRO' en el combo")

    page.wait_for_timeout(350)
    label = page.locator(selectors["tipo_cita_label"]).first
    texto_label = label.inner_text().strip().upper()
    if "POLÍGONO DE TIRO" not in texto_label and "POLIGONO DE TIRO" not in texto_label:
        raise Exception(f"No se confirmo la seleccion en el combo. Label actual: '{texto_label}'")
    print(f"   [INFO] Tipo de cita seleccionado: {texto_label}")
