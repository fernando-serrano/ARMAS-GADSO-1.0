from __future__ import annotations

import re

from .screenshots import capturar_tabla_cupos, capturar_tabla_sin_cupo
from .selectors import SELECTORS


def seleccionar_sede_y_fecha_desde_registro(page, registro: dict, seleccionar_en_selectonemenu):
    """Selecciona Sede y Fecha segun el registro del Excel."""
    sede = registro["sede"].strip()
    fecha = registro["fecha"].strip()

    print("\n Completando Reserva de Cupos con datos del Excel...")
    page.locator(SELECTORS["reserva_form"]).wait_for(state="visible", timeout=15000)

    seleccionar_en_selectonemenu(
        page,
        trigger_selector=SELECTORS["sede_trigger"],
        panel_selector=SELECTORS["sede_panel"],
        label_selector=SELECTORS["sede_label"],
        valor=sede,
        nombre_campo="Sede"
    )

    page.wait_for_timeout(700)

    seleccionar_en_selectonemenu(
        page,
        trigger_selector=SELECTORS["fecha_trigger"],
        panel_selector=SELECTORS["fecha_panel"],
        label_selector=SELECTORS["fecha_label"],
        valor=fecha,
        nombre_campo="Fecha"
    )


def seleccionar_hora_con_cupo_y_avanzar(page, registro: dict, deps: dict):
    """
    Busca la hora del Excel en la tabla de cupos, valida cupos > 0,
    selecciona el radiobutton de la fila y presiona 'Siguiente'.
    """
    normalizar_hora_rango = deps["normalizar_hora_rango"]
    normalizar_hora_fragmento = deps["normalizar_hora_fragmento"]
    convertir_a_entero = deps["convertir_a_entero"]
    parsear_rango = deps["parsear_rango"]
    rango_desplazado = deps["rango_desplazado"]
    hora_adaptativa_habilitada = deps["hora_adaptativa_habilitada"]
    hora_adaptativa_bloque_mediodia_completo = deps["hora_adaptativa_bloque_mediodia_completo"]
    sin_cupo_error = deps["sin_cupo_error"]

    hora_objetivo = normalizar_hora_rango(registro.get("hora_rango", ""))
    if not hora_objetivo:
        raise Exception("El registro no tiene 'hora_rango' valido")

    print(f"\n Buscando hora en tabla: {hora_objetivo}")

    tabla = page.locator(SELECTORS["tabla_programacion"])
    tabla.wait_for(state="visible", timeout=15000)
    capturar_tabla_cupos(page, registro, hora_objetivo, motivo="tabla_inicial")

    filas = page.locator(SELECTORS["tabla_programacion_rows"])
    total_filas = filas.count()
    if total_filas == 0:
        filas = page.locator(f"{SELECTORS['tabla_programacion']} tbody tr")
        total_filas = filas.count()
    if total_filas == 0:
        raise Exception("La tabla de programacion no tiene filas para la fecha/sede seleccionadas")

    fila_objetivo = None
    cupos_objetivo = 0
    resumen = []
    horas_descartadas = {
        normalizar_hora_rango(x)
        for x in (registro.get("_horas_descartadas", []) or [])
        if normalizar_hora_rango(x)
    }
    usar_hora_adaptativa = hora_adaptativa_habilitada()

    def extraer_hora_rango_desde_texto(texto: str) -> str:
        t = str(texto or "").replace(".", ":")
        m = re.search(r"(\d{1,2}:\d{2})\s*[-\u2013\u2014]\s*(\d{1,2}:\d{2})", t)
        if m:
            ini = normalizar_hora_fragmento(m.group(1))
            fin = normalizar_hora_fragmento(m.group(2))
            return f"{ini}-{fin}"
        return normalizar_hora_rango(t)

    def extraer_cupos_desde_celdas(textos_celdas: list) -> int:
        for txt in reversed(textos_celdas):
            t = str(txt or "").strip()
            if not t or ":" in t:
                continue
            if re.search(r"\d+", t):
                return convertir_a_entero(t)
        return 0

    def click_boton_limpiar_obligatorio():
        try:
            boton_limpiar = page.locator(SELECTORS["boton_limpiar"])
            boton_limpiar.wait_for(state="visible", timeout=7000)
            boton_limpiar.first.click(timeout=7000)
            page.wait_for_timeout(350)
            print("   [INFO] Click en boton 'Limpiar' por falta de cupos")
        except Exception as e:
            raise sin_cupo_error(f"No se pudo accionar el boton 'Limpiar' tras detectar cupo 0: {e}")

    slots = []
    for i in range(total_filas):
        fila = filas.nth(i)
        celdas = fila.locator("td")
        total_celdas = celdas.count()
        if total_celdas == 0:
            continue

        textos_celdas = []
        for j in range(total_celdas):
            try:
                textos_celdas.append((celdas.nth(j).inner_text() or "").strip())
            except Exception:
                textos_celdas.append("")

        hora_tabla = ""
        for txt in textos_celdas:
            cand = extraer_hora_rango_desde_texto(txt)
            if cand and "-" in cand and re.search(r"\d{2}:\d{2}-\d{2}:\d{2}", cand):
                hora_tabla = cand
                break

        cupos = extraer_cupos_desde_celdas(textos_celdas)
        if hora_tabla:
            resumen.append(f"{hora_tabla} ({cupos})")
            slots.append({
                "hora": hora_tabla,
                "cupos": cupos,
                "fila": fila,
                "orden": i,
                "rango": parsear_rango(hora_tabla),
            })

    for slot in slots:
        if slot["hora"] == hora_objetivo:
            fila_objetivo = slot["fila"]
            cupos_objetivo = slot["cupos"]
            break

    if fila_objetivo is None:
        raise Exception(
            "No se encontro la hora objetivo en la tabla. "
            f"Objetivo: '{hora_objetivo}' | Disponibles: {', '.join(resumen)}"
        )

    if cupos_objetivo > 0:
        print("   [INFO] Estrategia horario: prioridad a hora exacta del Excel")
    elif usar_hora_adaptativa and slots:
        slots_ordenados = sorted(
            slots,
            key=lambda s: (
                s["rango"][0] if s["rango"] else 9999,
                s["orden"],
            ),
        )
        slot_objetivo = next((s for s in slots_ordenados if s["hora"] == hora_objetivo), None)

        candidatos = []
        bloque_mediodia = [
            "11:45-12:00",
            "12:00-12:15",
            "12:15-12:30",
            "12:30-12:45",
            "12:45-13:00",
        ]

        if hora_objetivo in bloque_mediodia and hora_adaptativa_bloque_mediodia_completo():
            candidatos = [s for s in slots_ordenados if s["hora"] in bloque_mediodia]
            print("   [INFO] Estrategia horario: bloque completo de mediodia (11:45-13:00)")
        else:
            idx_obj = next((i for i, s in enumerate(slots_ordenados) if s["hora"] == hora_objetivo), -1)
            if idx_obj >= 0:
                inferior = slots_ordenados[idx_obj - 1] if idx_obj - 1 >= 0 else None
                superior = slots_ordenados[idx_obj + 1] if idx_obj + 1 < len(slots_ordenados) else None
                if inferior and superior:
                    candidatos = [inferior, superior]
                elif inferior and slot_objetivo:
                    candidatos = [inferior, slot_objetivo]
                elif superior and slot_objetivo:
                    candidatos = [slot_objetivo, superior]
                elif slot_objetivo:
                    candidatos = [slot_objetivo]

            if not candidatos and slot_objetivo:
                prev_hora = rango_desplazado(hora_objetivo, -1)
                next_hora = rango_desplazado(hora_objetivo, 1)
                candidatos = [
                    s for s in slots_ordenados
                    if s["hora"] in {prev_hora, next_hora, hora_objetivo}
                ]
            print("   [INFO] Estrategia horario: vecinos inmediatos (inferior/superior)")

        if not candidatos and slot_objetivo:
            candidatos = [slot_objetivo]

        if horas_descartadas:
            candidatos_filtrados = [s for s in candidatos if s["hora"] not in horas_descartadas]
            if candidatos_filtrados:
                candidatos = candidatos_filtrados

        candidatos_disponibles = [s for s in candidatos if s["cupos"] > 0]

        if candidatos_disponibles:
            seleccionado = max(
                candidatos_disponibles,
                key=lambda s: (
                    s["cupos"],
                    s["rango"][0] if s["rango"] else s["orden"],
                ),
            )
            fila_objetivo = seleccionado["fila"]
            cupos_objetivo = seleccionado["cupos"]
            if seleccionado["hora"] != hora_objetivo:
                print(
                    f"   [INFO] Reasignacion adaptativa de hora: "
                    f"{hora_objetivo} -> {seleccionado['hora']} (Cupos={cupos_objetivo})"
                )
                registro["hora_rango"] = seleccionado["hora"]
            hora_objetivo = seleccionado["hora"]
        else:
            opciones_dbg = ", ".join([f"{s['hora']}({s['cupos']})" for s in candidatos])
            capturar_tabla_sin_cupo(page, registro, hora_objetivo, "candidatos_0")
            click_boton_limpiar_obligatorio()
            raise sin_cupo_error(
                "No hay cupos en horarios candidatos. "
                f"Objetivo: {hora_objetivo} | Candidatos: {opciones_dbg}"
            )

    if cupos_objetivo <= 0:
        capturar_tabla_sin_cupo(page, registro, hora_objetivo, "hora_0")
        click_boton_limpiar_obligatorio()
        raise sin_cupo_error(f"La hora '{hora_objetivo}' no tiene cupos disponibles (Cupos Libres={cupos_objetivo})")

    radio_box = fila_objetivo.locator("td.ui-selection-column div.ui-radiobutton-box")
    if radio_box.count() == 0:
        raise Exception("No se encontro radiobutton en la fila de la hora objetivo")

    radio_box.first.click()
    page.wait_for_timeout(250)

    clase_radio = (radio_box.first.get_attribute("class") or "")
    aria_fila = (fila_objetivo.get_attribute("aria-selected") or "").lower()
    if "ui-state-active" not in clase_radio and aria_fila != "true":
        raise Exception("No se confirmo la seleccion del radiobutton de la hora")

    registro["_hora_seleccionada_actual"] = hora_objetivo
    print(f"   [INFO] Hora seleccionada: {hora_objetivo} (Cupos Libres={cupos_objetivo})")

    boton_siguiente = page.locator(SELECTORS["boton_siguiente"])
    boton_siguiente.wait_for(state="visible", timeout=7000)
    boton_siguiente.click()
    print("   [INFO] Click en boton 'Siguiente'")
