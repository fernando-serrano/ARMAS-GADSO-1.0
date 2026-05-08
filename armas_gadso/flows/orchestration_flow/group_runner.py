from __future__ import annotations

import time
from collections import deque
from pathlib import Path


def agrupar_trabajos_por_grupo(trabajos_pendientes: list, grupos_ordenados: list[str]) -> dict:
    trabajos_por_grupo = {g: [] for g in grupos_ordenados}
    for trabajo in trabajos_pendientes:
        grupo = trabajo.get("ruc_grupo", "OTRO")
        if grupo not in trabajos_por_grupo:
            grupo = "OTRO"
        trabajos_por_grupo[grupo].append(trabajo)
    return trabajos_por_grupo


def _limpiar_confirmaciones_idx(confirmaciones_terminales: dict, idx_excel: int) -> None:
    for categoria in [
        "SIN_CUPO",
        "NRO_SOLICITUD",
        "DOC_VIGILANTE",
        "HORA_NO_DISPONIBLE",
        "FECHA_NO_DISPONIBLE",
        "TURNO_DUPLICADO",
        "RESTRICCION_48H_EXAMEN",
    ]:
        confirmaciones_terminales.pop((idx_excel, categoria), None)


def procesar_grupo_ruc(
    grupo_ruc: str,
    trabajos_grupo: list,
    state: dict,
    deps: dict,
) -> dict:
    validar_tiempo_maximo = deps["validar_tiempo_maximo"]
    resolver_credenciales_por_grupo_ruc = deps["resolver_credenciales_por_grupo_ruc"]
    validar_credenciales_configuradas = deps["validar_credenciales_configuradas"]
    realizar_login_sel = deps["realizar_login_sel"]
    solve_captcha_ocr = deps["solve_captcha_ocr"]
    solve_captcha_manual = deps["solve_captcha_manual"]
    navegar_reservas_citas = deps["navegar_reservas_citas"]
    seleccionar_tipo_cita_poligono = deps["seleccionar_tipo_cita_poligono"]
    esperar_hasta_servicio_disponible = deps["esperar_hasta_servicio_disponible"]
    asegurar_contexto_reserva_operativo = deps["asegurar_contexto_reserva_operativo"]
    cargar_primer_registro_pendiente_desde_excel = deps["cargar_primer_registro_pendiente_desde_excel"]
    seleccionar_sede_y_fecha_desde_registro = deps["seleccionar_sede_y_fecha_desde_registro"]
    seleccionar_hora_con_cupo_y_avanzar = deps["seleccionar_hora_con_cupo_y_avanzar"]
    completar_paso_2_desde_registro = deps["completar_paso_2_desde_registro"]
    detectar_cita_ya_registrada_visible = deps["detectar_cita_ya_registrada_visible"]
    detectar_restriccion_48h_examen_visible = deps["detectar_restriccion_48h_examen_visible"]
    validar_turno_duplicado_o_lanzar = deps["validar_turno_duplicado_o_lanzar"]
    completar_tabla_tipos_arma_y_avanzar = deps["completar_tabla_tipos_arma_y_avanzar"]
    completar_fase_3_resumen = deps["completar_fase_3_resumen"]
    generar_cita_final_con_reintento_rapido = deps["generar_cita_final_con_reintento_rapido"]
    capturar_confirmacion_cita = deps["capturar_confirmacion_cita"]
    registrar_cita_programada_en_excel = deps["registrar_cita_programada_en_excel"]
    limpiar_para_siguiente_registro = deps["limpiar_para_siguiente_registro"]
    clasificar_motivo_detencion = deps["clasificar_motivo_detencion"]
    es_error_transitorio_para_relogin = deps["es_error_transitorio_para_relogin"]
    cupos_ocupados_error = deps["cupos_ocupados_error"]
    normalizar_hora_rango = deps["normalizar_hora_rango"]
    registrar_sin_cupo_en_excel = deps["registrar_sin_cupo_en_excel"]
    turno_duplicado_error = deps["turno_duplicado_error"]
    cita_ya_registrada_error = deps["cita_ya_registrada_error"]
    clasificar_error_terminal_registro = deps["clasificar_error_terminal_registro"]
    confirmaciones_requeridas_para_categoria = deps["confirmaciones_requeridas_para_categoria"]
    observacion_terminal_por_categoria = deps["observacion_terminal_por_categoria"]
    observacion_error_no_mapeado = deps["observacion_error_no_mapeado"]
    register_nro_solicitud_terminal = deps["register_nro_solicitud_terminal"]
    selectors = deps["selectors"]
    url_login = deps["url_login"]
    excel_path = deps["excel_path"]
    inicio_total_flujo = deps["inicio_total_flujo"]
    max_run_minutes = deps["max_run_minutes"]
    max_login_retries_per_group = deps["max_login_retries_per_group"]
    login_validation_timeout_ms = deps["login_validation_timeout_ms"]
    terminal_confirmaciones_requeridas = deps["terminal_confirmaciones_requeridas"]
    nro_solicitud_confirmaciones_requeridas = deps["nro_solicitud_confirmaciones_requeridas"]
    sin_cupo_confirmaciones_requeridas = deps["sin_cupo_confirmaciones_requeridas"]
    max_unmapped_retries_per_record = deps["max_unmapped_retries_per_record"]
    max_hora_fallback_retries = deps["max_hora_fallback_retries"]
    persistent_session = deps["persistent_session"]
    browser_start_maximized = deps["browser_start_maximized"]
    browser_window_w = deps["browser_window_w"]
    browser_window_h = deps["browser_window_h"]
    tile_enabled = deps["tile_enabled"]
    tile_x = deps["tile_x"]
    tile_y = deps["tile_y"]
    tile_w = deps["tile_w"]
    tile_h = deps["tile_h"]
    tile_screen_w = deps["tile_screen_w"]
    tile_screen_h = deps["tile_screen_h"]

    validar_tiempo_maximo(inicio_total_flujo, max_run_minutes)
    credenciales_grupo = resolver_credenciales_por_grupo_ruc(grupo_ruc)
    validar_credenciales_configuradas(credenciales_grupo, grupo_ruc)

    print(f"\n Procesando grupo RUC {grupo_ruc} - Registros: {len(trabajos_grupo)}")
    grupo_procesado = False
    intento_global = 0

    while True:
        validar_tiempo_maximo(inicio_total_flujo, max_run_minutes)
        intento_global += 1
        print(
            f"\n[INFO] Intento login {intento_global}/{max_login_retries_per_group} "
            f"para grupo {grupo_ruc}"
        )

        if max_login_retries_per_group > 0 and intento_global > max_login_retries_per_group:
            raise Exception(
                f"MAX_LOGIN_RETRIES_PER_GROUP alcanzado para grupo {grupo_ruc}: {max_login_retries_per_group}"
            )

        browser = state["browser"]
        context = state["context"]
        playwright = state["playwright"]

        debe_cerrar_navegador = True
        if persistent_session and intento_global == 1 and browser is not None:
            debe_cerrar_navegador = False
            print("[DEBUG] PERSISTENT_SESSION: reutilizando navegador del grupo anterior")

        if debe_cerrar_navegador and browser is not None:
            try:
                browser.close()
            except Exception:
                pass

        launch_args = ["--disable-infobars"]
        if tile_enabled:
            launch_args.extend([
                f"--window-size={tile_w},{tile_h}",
                f"--window-position={tile_x},{tile_y}",
            ])
            print(f"[TILE] Args launch: --window-size={tile_w},{tile_h} --window-position={tile_x},{tile_y}")
        else:
            if browser_start_maximized:
                launch_args.append("--start-maximized")
            launch_args.extend([
                f"--window-size={browser_window_w},{browser_window_h}",
                "--window-position=0,0",
            ])

        if persistent_session and intento_global == 1 and browser is not None:
            print("[DEBUG] PERSISTENT_SESSION: creando nuevo context/page en navegador existente")
            context = browser.new_context(no_viewport=True, ignore_https_errors=True)
            page = context.new_page()
        else:
            print(f"[TILE] Lanzando Chromium con args: {launch_args}")
            browser = playwright.chromium.launch(
                headless=False,
                slow_mo=0,
                args=launch_args,
            )
            context = browser.new_context(no_viewport=True, ignore_https_errors=True)
            page = context.new_page()
            page.wait_for_timeout(300)

        state["browser"] = browser
        state["context"] = context

        if tile_enabled:
            actual_dims = page.evaluate(
                """
                () => {
                    return {
                        screenW: window.screen.availWidth || window.screen.width,
                        screenH: window.screen.availHeight || window.screen.height,
                        outerW: window.outerWidth,
                        outerH: window.outerHeight,
                        innerW: window.innerWidth,
                        innerH: window.innerHeight,
                    };
                }
                """
            )
            print(
                "[TILE] Geometría aplicada -> "
                f"xy=({tile_x},{tile_y}) "
                f"wh=({tile_w},{tile_h}) "
                f"screen_cfg={tile_screen_w}x{tile_screen_h} "
                f"screen_js={actual_dims.get('screenW')}x{actual_dims.get('screenH')} "
                f"outer_js={actual_dims.get('outerW')}x{actual_dims.get('outerH')}"
            )
        else:
            if browser_start_maximized:
                page.evaluate("() => { window.moveTo(0, 0); window.resizeTo(screen.width, screen.height); }")
        deps["activar_monitor_growl"](page)

        try:
            page.goto(url_login, wait_until="domcontentloaded", timeout=45000)
            esperar_hasta_servicio_disponible(page, url_login, espera_segundos=8)
            print("[INFO] Pagina de login cargada")

            state["login_exitoso"] = realizar_login_sel(
                page,
                credenciales_grupo=credenciales_grupo,
                grupo_ruc=grupo_ruc,
                captcha_solver=solve_captcha_ocr,
                manual_solver=solve_captcha_manual,
                login_validation_timeout_ms=login_validation_timeout_ms,
                selectors=selectors,
            )

            navegar_reservas_citas(page)
            seleccionar_tipo_cita_poligono(page)

            cola_trabajos = deque(trabajos_grupo)
            intentos_por_idx = {}
            intentos_no_mapeados_por_idx = {}
            intentos_replan_hora_por_idx = {}
            confirmaciones_terminales = {}
            iteracion = 0

            while cola_trabajos:
                validar_tiempo_maximo(inicio_total_flujo, max_run_minutes)
                iteracion += 1
                trabajo = cola_trabajos.popleft()
                idx_excel = trabajo["idx_excel"]
                intentos_por_idx[idx_excel] = intentos_por_idx.get(idx_excel, 0) + 1
                print(
                    f"\n-------- {grupo_ruc} Registro iterativo {iteracion} "
                    f"(idx={idx_excel}, prioridad={trabajo.get('prioridad', 'Normal')}, "
                    f"intento={intentos_por_idx[idx_excel]}, en_cola={len(cola_trabajos)}) --------"
                )

                esperar_hasta_servicio_disponible(page, page.url, espera_segundos=8)
                asegurar_contexto_reserva_operativo(page, selectors, seleccionar_tipo_cita_poligono)

                try:
                    registro_excel = cargar_primer_registro_pendiente_desde_excel(
                        excel_path,
                        indice_excel_objetivo=idx_excel,
                    )
                    registro_excel["_horas_descartadas"] = list(trabajo.get("_horas_descartadas", []) or [])
                except Exception as e:
                    txt_carga = str(e or "")
                    if "no est en estado Pendiente" in txt_carga or "No hay registros con estado 'Pendiente'" in txt_carga:
                        print(f"[INFO] Registro idx={idx_excel} ya no est pendiente. Se omite.")
                        intentos_no_mapeados_por_idx.pop(idx_excel, None)
                        intentos_replan_hora_por_idx.pop(idx_excel, None)
                        _limpiar_confirmaciones_idx(confirmaciones_terminales, idx_excel)
                        continue
                    raise

                try:
                    try:
                        page.locator(selectors["reserva_form"]).wait_for(state="visible", timeout=2500)
                    except Exception:
                        seleccionar_tipo_cita_poligono(page)

                    seleccionar_sede_y_fecha_desde_registro(page, registro_excel)
                    seleccionar_hora_con_cupo_y_avanzar(page, registro_excel)
                    completar_paso_2_desde_registro(page, registro_excel)
                    validar_turno_duplicado_o_lanzar(page, max_wait_ms=900)
                    completar_tabla_tipos_arma_y_avanzar(page, registro_excel)
                    validar_turno_duplicado_o_lanzar(page, max_wait_ms=900)
                    completar_fase_3_resumen(page)
                    validar_turno_duplicado_o_lanzar(page, max_wait_ms=900)
                    generar_cita_final_con_reintento_rapido(page, registro_excel, max_intentos=5)
                    capturar_confirmacion_cita(page, registro_excel)
                    registrar_cita_programada_en_excel(excel_path, registro_excel)

                    limpiar_para_siguiente_registro(page, motivo="fin de flujo")
                    state["total_ok"] += 1
                    intentos_no_mapeados_por_idx.pop(idx_excel, None)
                    intentos_replan_hora_por_idx.pop(idx_excel, None)
                    _limpiar_confirmaciones_idx(confirmaciones_terminales, idx_excel)

                except Exception as e:
                    motivo_detencion = clasificar_motivo_detencion(e)
                    if motivo_detencion == "VENTANA_CERRADA":
                        print(
                            f"Registro idx={idx_excel} no procesado: "
                            "la ventana/contexto del navegador fue cerrada."
                        )
                        raise KeyboardInterrupt("Ventana del navegador cerrada durante procesamiento") from e

                    if es_error_transitorio_para_relogin(e):
                        print(
                            f"[WARNING] Estado transitorio UI en idx={idx_excel}: {e}. "
                            "Se reiniciara sesion para recuperar flujo."
                        )
                        raise Exception("RELOGIN_UI_DESYNC") from e

                    cita_visible = isinstance(e, cita_ya_registrada_error)
                    if not cita_visible:
                        try:
                            cita_visible = detectar_cita_ya_registrada_visible(page, registro_excel)
                        except Exception:
                            cita_visible = False

                    if cita_visible:
                        print(
                            f"[INFO] Registro idx={idx_excel} tratado como cita programada "
                            f"por validacion intermedia: {e}"
                        )
                        registrar_cita_programada_en_excel(excel_path, registro_excel)
                        state["total_ok"] += 1
                        intentos_no_mapeados_por_idx.pop(idx_excel, None)
                        intentos_replan_hora_por_idx.pop(idx_excel, None)
                        _limpiar_confirmaciones_idx(confirmaciones_terminales, idx_excel)
                        try:
                            limpiar_para_siguiente_registro(page, motivo="cita ya registrada")
                        except Exception:
                            pass
                        time.sleep(1)
                        continue

                    restriccion_48h_visible = False
                    try:
                        restriccion_48h_visible = detectar_restriccion_48h_examen_visible(page, registro_excel)
                    except Exception:
                        restriccion_48h_visible = False

                    if restriccion_48h_visible:
                        e = Exception(
                            "No esta permitido reservar una cita con fecha anterior a las 48 horas "
                            "de rendido el examen"
                        )

                    if isinstance(e, cupos_ocupados_error):
                        hora_actual = normalizar_hora_rango(registro_excel.get("_hora_seleccionada_actual", ""))
                        descartadas = list(trabajo.get("_horas_descartadas", []) or [])
                        if hora_actual and hora_actual not in descartadas:
                            descartadas.append(hora_actual)
                        trabajo["_horas_descartadas"] = descartadas

                        hits_hora = intentos_replan_hora_por_idx.get(idx_excel, 0) + 1
                        intentos_replan_hora_por_idx[idx_excel] = hits_hora

                        if hits_hora >= max_hora_fallback_retries:
                            obs = (
                                "Cupos ocupados al confirmar cita tras "
                                f"{hits_hora} reintentos de horario. "
                                f"Ultima hora evaluada: {hora_actual or registro_excel.get('hora_rango', '')}"
                            )
                            registrar_sin_cupo_en_excel(excel_path, registro_excel, obs)
                            state["total_sin_cupo"] += 1
                            print(
                                f"[INFO] Registro idx={idx_excel} marcado como SIN_CUPO por "
                                f"cupos ocupados post-validacion ({hits_hora}/{max_hora_fallback_retries})."
                            )
                        else:
                            intentos_no_mapeados_por_idx.pop(idx_excel, None)
                            print(
                                f"[INFO] Registro idx={idx_excel} con cupos ocupados post-validacion. "
                                f"Reintentando con otro horario ({hits_hora}/{max_hora_fallback_retries})..."
                            )
                            cola_trabajos.append(trabajo)

                        try:
                            limpiar_para_siguiente_registro(page, motivo="replanificacion por cupos ocupados")
                        except Exception:
                            pass
                        time.sleep(1)
                        continue

                    if not isinstance(e, turno_duplicado_error):
                        try:
                            validar_turno_duplicado_o_lanzar(page, max_wait_ms=900)
                        except turno_duplicado_error as e_dup:
                            e = e_dup

                    categoria_terminal = clasificar_error_terminal_registro(e)
                    print(f"[WARNING] Error en registro idx={idx_excel}: {e}")

                    if categoria_terminal:
                        intentos_no_mapeados_por_idx.pop(idx_excel, None)
                        intentos_replan_hora_por_idx.pop(idx_excel, None)
                        clave_conf = (idx_excel, categoria_terminal)
                        confirmaciones_terminales[clave_conf] = confirmaciones_terminales.get(clave_conf, 0) + 1
                        hits = confirmaciones_terminales[clave_conf]
                        requeridas = confirmaciones_requeridas_para_categoria(categoria_terminal)

                        if hits >= requeridas:
                            obs = observacion_terminal_por_categoria(categoria_terminal, registro_excel, e)
                            registrar_sin_cupo_en_excel(excel_path, registro_excel, obs)
                            if categoria_terminal in {"NRO_SOLICITUD", "RESTRICCION_48H_EXAMEN"}:
                                if categoria_terminal == "RESTRICCION_48H_EXAMEN":
                                    registro_excel["_terminal_reason_label"] = "Restriccion 48h por examen"
                                screenshot_raw = str(registro_excel.get("_step2_error_screenshot_path", "") or "").strip()
                                screenshot_path = Path(screenshot_raw) if screenshot_raw else None
                                register_nro_solicitud_terminal(
                                    registro_excel,
                                    screenshot_path if screenshot_path and screenshot_path.exists() else None,
                                    str(registro_excel.get("_hora_seleccionada_actual", registro_excel.get("hora_rango", "")) or "").strip(),
                                )
                            if categoria_terminal == "SIN_CUPO":
                                state["total_sin_cupo"] += 1
                            else:
                                state["total_error"] += 1
                            print(
                                f"[INFO] Registro idx={idx_excel} marcado como terminal '{categoria_terminal}' "
                                f"tras {hits} confirmaciones"
                            )
                        else:
                            print(
                                f"[INFO] Registro idx={idx_excel} con causal terminal '{categoria_terminal}' "
                                f"pendiente de confirmacion ({hits}/{requeridas}). Reencolando..."
                            )
                            cola_trabajos.append(trabajo)
                    else:
                        hits_no_mapeados = intentos_no_mapeados_por_idx.get(idx_excel, 0) + 1
                        intentos_no_mapeados_por_idx[idx_excel] = hits_no_mapeados
                        if (
                            max_unmapped_retries_per_record > 0
                            and hits_no_mapeados >= max_unmapped_retries_per_record
                        ):
                            obs = observacion_error_no_mapeado(registro_excel, e, hits_no_mapeados)
                            registrar_sin_cupo_en_excel(excel_path, registro_excel, obs)
                            state["total_error"] += 1
                            print(
                                f"[INFO] Registro idx={idx_excel} marcado con error no mapeado "
                                f"tras {hits_no_mapeados} intentos"
                            )
                        else:
                            print(
                                f"[INFO] Error transitorio/no clasificado en idx={idx_excel}. "
                                f"Reencolando ({hits_no_mapeados}/"
                                f"{max_unmapped_retries_per_record if max_unmapped_retries_per_record > 0 else 'sin limite'})..."
                            )
                            cola_trabajos.append(trabajo)

                    try:
                        limpiar_para_siguiente_registro(page, motivo="recuperacion por error")
                    except Exception:
                        pass
                    time.sleep(1)
                    continue

            grupo_procesado = True
            if persistent_session:
                try:
                    print("[DEBUG] PERSISTENT_SESSION: cerrando contexto anterior para siguiente grupo")
                    context.close()
                except Exception as e_ctx:
                    print(f"[DEBUG] Error cerrando contexto: {e_ctx}")
            break

        except Exception as e:
            motivo_detencion = clasificar_motivo_detencion(e)
            if motivo_detencion == "VENTANA_CERRADA":
                print(
                    "Proceso detenido: se cerro la ventana/contexto del navegador "
                    f"durante el login del grupo {grupo_ruc}."
                )
                raise KeyboardInterrupt("Ventana del navegador cerrada") from e

            if "CAPTCHA_MANUAL_REQUERIDO_EN_SCHEDULED" in str(e or ""):
                print(
                    "[ERROR] En modo scheduled no se permite input manual de captcha. "
                    "Finalizando corrida para evitar bloqueo."
                )
                raise

            if es_error_transitorio_para_relogin(e):
                print(
                    f"[WARNING] Intento login {intento_global} para grupo {grupo_ruc}: "
                    "se detecto desincronizacion de UI. Reintentando login..."
                )
                time.sleep(1)
                continue

            print(f"[ERROR] Intento login {intento_global} para grupo {grupo_ruc} fallo: {e}")
            if intento_global >= max_login_retries_per_group:
                raise

            print("   Reintentando login...")
            espera_backoff = min(8, 1 + intento_global)
            time.sleep(espera_backoff)

    if not grupo_procesado:
        state["total_error"] += len(trabajos_grupo)
        print(
            f"[WARNING] No se pudo procesar el grupo {grupo_ruc}. "
            f"Se contabilizan {len(trabajos_grupo)} registros con error."
        )

    return state
