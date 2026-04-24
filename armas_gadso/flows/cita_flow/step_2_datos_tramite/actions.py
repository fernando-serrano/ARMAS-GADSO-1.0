from __future__ import annotations

import re
import time

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from ..step_3_validacion_final.selectors import SELECTORS as STEP_3_SELECTORS
from .screenshots import capturar_error_paso_2
from .selectors import SELECTORS


def seleccionar_opcion_flexible_en_panel(page, panel_selector: str, texto_objetivo: str, nombre_campo: str, deps: dict):
    """Selecciona un li dentro de un panel PrimeFaces por coincidencia flexible de texto."""
    normalizar_texto_comparable = deps["normalizar_texto_comparable"]

    panel = page.locator(panel_selector)
    panel.wait_for(state="visible", timeout=7000)

    items = panel.locator("li.ui-selectonemenu-item")
    total = items.count()
    if total == 0:
        raise Exception(f"No hay opciones disponibles en {nombre_campo}")

    objetivo_norm = normalizar_texto_comparable(texto_objetivo)
    for i in range(total):
        item = items.nth(i)
        label = (item.get_attribute("data-label") or item.inner_text() or "").strip()
        label_norm = normalizar_texto_comparable(label)
        if objetivo_norm == label_norm or objetivo_norm in label_norm or label_norm in objetivo_norm:
            item.click()
            return label

    opciones = []
    for i in range(total):
        item = items.nth(i)
        opciones.append((item.get_attribute("data-label") or item.inner_text() or "").strip())
    raise Exception(
        f"No se encontro coincidencia para {nombre_campo}. "
        f"Objetivo: '{texto_objetivo}' | Opciones: {opciones}"
    )


def completar_paso_2_desde_registro(page, registro: dict, deps: dict):
    """
    Paso 2: tipo operacion, doc. vigilante, solicitud y numero de solicitud.
    """
    normalizar_texto_comparable = deps["normalizar_texto_comparable"]
    extraer_token_solicitud = deps["extraer_token_solicitud"]

    tipo_operacion = registro.get("tipo_operacion", "").strip()
    doc_vigilante = registro.get("doc_vigilante", "").strip()
    nro_solicitud_excel = registro.get("nro_solicitud", "").strip()
    token_solicitud = extraer_token_solicitud(nro_solicitud_excel)

    print("\n Completando Paso 2 con datos del Excel...")

    def capturar_si_falla(motivo: str):
        return capturar_error_paso_2(page, registro, motivo)

    page.locator(SELECTORS["tipo_operacion_trigger"]).wait_for(state="visible", timeout=12000)
    page.locator(SELECTORS["tipo_operacion_trigger"]).click()
    page.locator(SELECTORS["tipo_operacion_panel"]).wait_for(state="visible", timeout=7000)

    opcion_tipo = None
    items_tipo = page.locator(SELECTORS["tipo_operacion_items"])
    total_tipo = items_tipo.count()
    objetivo_tipo = normalizar_texto_comparable(tipo_operacion)
    for i in range(total_tipo):
        item = items_tipo.nth(i)
        label = (item.get_attribute("data-label") or item.inner_text() or "").strip()
        label_norm = normalizar_texto_comparable(label)
        if objetivo_tipo == label_norm or objetivo_tipo in label_norm or label_norm in objetivo_tipo:
            item.click()
            opcion_tipo = label
            break
    if not opcion_tipo:
        raise Exception(f"No se encontro Tipo Operacion '{tipo_operacion}' en el combo")

    page.wait_for_timeout(250)
    label_tipo = page.locator(SELECTORS["tipo_operacion_label"]).inner_text().strip()
    if not label_tipo or label_tipo == "---":
        raise Exception("No se confirmo la seleccion de Tipo Operacion")
    print(f"   [INFO] Tipo Operacion seleccionado: {opcion_tipo}")

    es_inicial = (
        "INICIAL" in normalizar_texto_comparable(label_tipo)
        or "INICIAL" in normalizar_texto_comparable(tipo_operacion)
    )

    def seleccionar_doc_vigilante_autocomplete():
        doc_input = page.locator(SELECTORS["doc_vig_input"])
        doc_input.wait_for(state="visible", timeout=12000)
        doc_input.click()
        doc_input.fill("")
        doc_input.type(doc_vigilante, delay=20)

        panel_doc = page.locator(SELECTORS["doc_vig_panel"])
        items_doc = page.locator(SELECTORS["doc_vig_items"])

        elegido = False
        try:
            panel_doc.wait_for(state="visible", timeout=2500)
        except PlaywrightTimeoutError:
            doc_input.press("ArrowDown")
            page.wait_for_timeout(350)

        if panel_doc.is_visible():
            try:
                items_doc.first.wait_for(state="visible", timeout=2500)
            except PlaywrightTimeoutError:
                page.wait_for_timeout(700)

            total_doc = items_doc.count()
            for i in range(total_doc):
                item = items_doc.nth(i)
                data_label = (item.get_attribute("data-item-label") or "").strip()
                data_value = (item.get_attribute("data-item-value") or "").strip()
                texto_item = item.inner_text().strip()
                if doc_vigilante in data_label or doc_vigilante in data_value or doc_vigilante in texto_item:
                    item.click()
                    elegido = True
                    break

            if not elegido and total_doc > 0:
                items_doc.first.click()
                elegido = True

        if not elegido:
            doc_input.evaluate(
                'el => { el.dispatchEvent(new Event("input", {bubbles:true})); el.dispatchEvent(new Event("change", {bubbles:true})); el.blur(); }'
            )

        page.wait_for_timeout(300)
        valor_doc = doc_input.input_value().strip()
        if doc_vigilante not in valor_doc:
            capturar_si_falla("doc_vigilante")
            raise Exception(f"No se confirmo el documento vigilante. Esperado contiene '{doc_vigilante}' | Actual '{valor_doc}'")
        print(f"   [INFO] Documento vigilante seleccionado: {valor_doc}")

    if es_inicial:
        print("    Flujo INICIAL detectado: primero Tipo de Licencia, luego Documento Vigilante")

        trigger_tramite = page.locator(SELECTORS["tipo_tramite_trigger"])
        label_tramite = page.locator(SELECTORS["tipo_tramite_label"])

        habilitado = False
        for _ in range(8):
            try:
                trigger_tramite.wait_for(state="visible", timeout=2000)
                label_tramite.wait_for(state="visible", timeout=2000)
                habilitado = True
                break
            except Exception:
                page.wait_for_timeout(400)

        if not habilitado:
            raise Exception("No aparecio el desplegable 'Tipo de Licencia' para flujo INICIAL")

        trigger_tramite.click()
        page.locator(SELECTORS["tipo_tramite_panel"]).wait_for(state="visible", timeout=7000)

        opcion_tramite = page.locator(SELECTORS["tipo_tramite_seg_priv"])
        try:
            opcion_tramite.wait_for(state="visible", timeout=2500)
            opcion_tramite.first.click()
        except PlaywrightTimeoutError:
            seleccionar_opcion_flexible_en_panel(
                page,
                panel_selector=SELECTORS["tipo_tramite_panel"],
                texto_objetivo="SEGURIDAD PRIVADA",
                nombre_campo="Tipo de Licencia",
                deps=deps,
            )

        page.wait_for_timeout(350)
        texto_tramite = page.locator(SELECTORS["tipo_tramite_label"]).inner_text().strip()
        if normalizar_texto_comparable(texto_tramite) != "SEGURIDAD PRIVADA":
            raise Exception(f"No se confirmo Tipo de Licencia = SEGURIDAD PRIVADA. Actual: '{texto_tramite}'")
        print("   [INFO] Tipo de Licencia: SEGURIDAD PRIVADA")

        seleccionar_doc_vigilante_autocomplete()
    else:
        seleccionar_doc_vigilante_autocomplete()

    page.locator(SELECTORS["seleccione_solicitud_trigger"]).wait_for(state="visible", timeout=12000)
    page.locator(SELECTORS["seleccione_solicitud_trigger"]).click()
    page.locator(SELECTORS["seleccione_solicitud_panel"]).wait_for(state="visible", timeout=7000)
    page.locator(SELECTORS["seleccione_solicitud_si"]).first.click()
    page.wait_for_timeout(350)
    label_si = page.locator(SELECTORS["seleccione_solicitud_label"]).inner_text().strip().upper()
    if label_si.replace(" ", "") != "SI":
        raise Exception(f"No se confirmo Seleccione Solicitud = SI. Actual: '{label_si}'")
    print("   [INFO] Seleccione Solicitud: SI")

    if es_inicial:
        print("    Flujo INICIAL: tambien se seleccionara Nro Solicitud")

    if not token_solicitud:
        raise Exception(f"No se pudo extraer token numerico de nro_solicitud: '{nro_solicitud_excel}'")

    page.locator(SELECTORS["nro_solicitud_trigger"]).wait_for(state="visible", timeout=12000)
    page.locator(SELECTORS["nro_solicitud_trigger"]).click()

    panel_nro = page.locator(SELECTORS["nro_solicitud_panel"])
    panel_nro.wait_for(state="visible", timeout=7000)
    items_nro = page.locator(SELECTORS["nro_solicitud_items"])
    total_nro = items_nro.count()
    if total_nro == 0:
        capturar_si_falla("nro_solicitud_vacio")
        raise Exception("No hay opciones en el combo de Nro Solicitud")

    seleccionado_label = None
    for i in range(total_nro):
        item = items_nro.nth(i)
        label = (item.get_attribute("data-label") or item.inner_text() or "").strip()
        bloques = re.findall(r"\d+", label)
        bloques_norm = [b.lstrip("0") or "0" for b in bloques]
        if token_solicitud in bloques_norm:
            item.click()
            seleccionado_label = label
            break

    if not seleccionado_label:
        disponibles = []
        for i in range(total_nro):
            item = items_nro.nth(i)
            disponibles.append((item.get_attribute("data-label") or item.inner_text() or "").strip())
        capturar_si_falla("nro_solicitud")
        raise Exception(
            f"No se encontro Nro Solicitud con token '{token_solicitud}'. Opciones: {disponibles}"
        )

    page.wait_for_timeout(300)
    label_nro = page.locator(SELECTORS["nro_solicitud_label"]).inner_text().strip()
    bloques_final = [b.lstrip("0") or "0" for b in re.findall(r"\d+", label_nro)]
    if token_solicitud not in bloques_final:
        capturar_si_falla("nro_solicitud_no_confirma")
        raise Exception(
            f"No se confirmo Nro Solicitud. Esperado token '{token_solicitud}' | Actual '{label_nro}'"
        )
    print(f"   [INFO] Nro Solicitud seleccionado: {label_nro}")


def completar_tabla_tipos_arma_y_avanzar(page, registro: dict, deps: dict):
    """Completa la tabla dtTipoLic segun tipo_arma/arma del Excel y avanza a Fase 3."""
    normalizar_tipo_arma_excel = deps["normalizar_tipo_arma_excel"]
    normalizar_texto_comparable = deps["normalizar_texto_comparable"]
    validar_turno_duplicado_o_lanzar = deps["validar_turno_duplicado_o_lanzar"]

    print("\n Completando tabla de tipos de arma (Fase 2)...")

    objetivos_excel = registro.get("objetivos_arma", []) or []
    objetivos = []
    for item in objetivos_excel:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            tipo_fila = normalizar_tipo_arma_excel(item[0])
            arma_objetivo = normalizar_tipo_arma_excel(item[1])
            if tipo_fila and arma_objetivo and (tipo_fila, arma_objetivo) not in objetivos:
                objetivos.append((tipo_fila, arma_objetivo))

    if not objetivos:
        raise Exception("No se recibieron objetivos de arma validos desde Excel (tipo_arma + arma)")

    filas = page.locator(SELECTORS["dt_tipo_lic_rows"])
    try:
        filas.first.wait_for(state="visible", timeout=9000)
    except PlaywrightTimeoutError:
        filas = page.locator(SELECTORS["dt_tipo_lic_rows_fallback"])
        try:
            filas.first.wait_for(state="visible", timeout=4000)
        except PlaywrightTimeoutError:
            raise Exception("No se encontro la tabla de tipos de arma (dtTipoLic)")

    total_filas = filas.count()
    if total_filas == 0:
        raise Exception("La tabla dtTipoLic no tiene filas")

    aplicados = []
    for tipo_fila, arma_objetivo in objetivos:
        fila_match = None
        for i in range(total_filas):
            fila = filas.nth(i)
            celdas = fila.locator('td[role="gridcell"]')
            if celdas.count() == 0:
                celdas = fila.locator("td")

            textos = []
            for j in range(celdas.count()):
                texto_celda = normalizar_texto_comparable(celdas.nth(j).inner_text().strip())
                if texto_celda:
                    textos.append(texto_celda)

            tipo_texto = " ".join(textos)
            if tipo_fila in tipo_texto:
                fila_match = fila
                break

        if fila_match is None:
            raise Exception(f"No se encontro fila para tipo de arma '{tipo_fila}' en dtTipoLic")

        celdas_editables = fila_match.locator("td.ui-editable-column")
        if celdas_editables.count() > 0:
            celdas_editables.last.click()
            page.wait_for_timeout(180)

        combo = fila_match.locator("select")
        if combo.count() == 0:
            raise Exception(f"No se encontro combo de Arma para tipo '{tipo_fila}'")

        combo.first.wait_for(state="visible", timeout=3500)
        combo.first.select_option(label=arma_objetivo)
        page.wait_for_timeout(350)

        try:
            page.wait_for_load_state("networkidle", timeout=3500)
        except Exception:
            pass

        seleccionado = combo.first.evaluate(
            "el => el.options[el.selectedIndex] ? el.options[el.selectedIndex].text.trim() : ''"
        )
        if normalizar_texto_comparable(seleccionado) != normalizar_texto_comparable(arma_objetivo):
            raise Exception(
                f"No se confirmo Arma para '{tipo_fila}'. Esperado '{arma_objetivo}' | Actual '{seleccionado}'"
            )

        aplicados.append(f"{tipo_fila} -> {seleccionado}")
        print(f"   [INFO] {tipo_fila}: {seleccionado}")

    if not aplicados:
        raise Exception("No se aplico ninguna seleccion de arma en dtTipoLic")

    boton_siguiente_3 = page.locator(SELECTORS["boton_siguiente_3"])
    boton_siguiente_3.wait_for(state="visible", timeout=8000)
    boton_siguiente_3.click()
    print("   [INFO] Click en boton 'Siguiente' de Fase 2 (botonSiguiente3)")

    esperar_transicion_a_fase3_o_turno_duplicado(
        page,
        validar_turno_duplicado_o_lanzar=validar_turno_duplicado_o_lanzar,
        timeout_ms=12000,
    )


def esperar_transicion_a_fase3_o_turno_duplicado(page, validar_turno_duplicado_o_lanzar, timeout_ms: int = 12000):
    """
    Espera robusta de transicion tras 'Siguiente' en Paso 2:
    - Si aparece mensaje de turno duplicado, lanza TurnoDuplicadoError.
    - Si aparece panel de Fase 3, retorna OK.
    """
    deadline = time.time() + (max(1000, int(timeout_ms)) / 1000.0)
    while time.time() < deadline:
        validar_turno_duplicado_o_lanzar(page, max_wait_ms=0)

        try:
            if page.locator(STEP_3_SELECTORS["fase3_panel"]).is_visible(timeout=200):
                return
        except Exception:
            pass

        page.wait_for_timeout(180)

    validar_turno_duplicado_o_lanzar(page, max_wait_ms=1200)
    raise Exception("No se confirmo transicion a Fase 3 tras 'Siguiente' de Paso 2")
