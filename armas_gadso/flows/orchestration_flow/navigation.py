from __future__ import annotations

import os

from .sync import esperar_fin_ajax_primefaces


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


def navegar_reservas_citas(page, selectors: dict):
    """Abre el menu CITAS y hace click en RESERVAS DE CITAS."""
    print("\n Navegando a RESERVAS DE CITAS...")

    menu_citas_header = page.locator(selectors["menu_citas_header"]).first
    menu_citas_header.wait_for(state="visible", timeout=12000)

    panel = page.locator(selectors["menu_citas_panel"]).first
    panel_visible = False
    try:
        panel_visible = panel.is_visible()
    except Exception:
        panel_visible = False

    if not panel_visible:
        menu_citas_header.click()
        panel.wait_for(state="visible", timeout=7000)
        print("   [INFO] Menu CITAS expandido")
    else:
        print("   [INFO] Menu CITAS ya estaba expandido")

    submenu = page.locator(selectors["submenu_reservas"]).first
    submenu.wait_for(state="visible", timeout=7000)
    submenu.click()
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
