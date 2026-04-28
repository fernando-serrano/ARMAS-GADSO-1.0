import os
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
import time

from ... import excel as excel_ops
from ... import utils as shared_utils
from ...exceptions import (
    CuposOcupadosPostValidacionError as DomainCuposOcupadosPostValidacionError,
    FechaNoDisponibleError as DomainFechaNoDisponibleError,
    SinCupoError as DomainSinCupoError,
    TurnoDuplicadoError as DomainTurnoDuplicadoError,
)
from ..captcha_flow import solve_captcha_manual, solve_captcha_ocr_base, solve_login_captcha
from .group_runner import agrupar_trabajos_por_grupo, procesar_grupo_ruc
from .workers import ejecutar_scheduled_multihilo_orquestador, multihilo_scheduled_habilitado
from .monitoring import activar_monitor_growl, detectar_turno_duplicado_en_growl
from .navigation import (
    esperar_hasta_servicio_disponible as esperar_hasta_servicio_disponible_nav,
    navegar_reservas_citas as navegar_reservas_citas_nav,
    seleccionar_en_selectonemenu as seleccionar_en_selectonemenu_nav,
    seleccionar_tipo_cita_poligono as seleccionar_tipo_cita_poligono_nav,
)
from .runtime import (
    asegurar_contexto_reserva_operativo,
    clasificar_error_terminal_registro,
    confirmaciones_requeridas_para_categoria,
    es_error_transitorio_para_relogin,
    load_runtime_options,
    observacion_error_no_mapeado,
    observacion_terminal_por_categoria,
    validar_credenciales_configuradas,
    validar_tiempo_maximo,
)
from ..cita_flow.step_1_reserva_cupos import (
    seleccionar_hora_con_cupo_y_avanzar as seleccionar_hora_con_cupo_y_avanzar_paso_1,
    seleccionar_sede_y_fecha_desde_registro as seleccionar_sede_y_fecha_desde_registro_paso_1,
)
from ..cita_flow.step_2_datos_tramite import (
    completar_paso_2_desde_registro as completar_paso_2_desde_registro_paso_2,
    completar_tabla_tipos_arma_y_avanzar as completar_tabla_tipos_arma_y_avanzar_paso_2,
)
from ..cita_flow.step_2_datos_tramite.selectors import SELECTORS as STEP_2_SELECTORS
from ..cita_flow.step_3_validacion_final import (
    completar_fase_3_resumen as completar_fase_3_resumen_paso_3,
    generar_cita_final_con_reintento_rapido as generar_cita_final_con_reintento_rapido_paso_3,
)
from ..cita_flow.step_3_validacion_final.selectors import SELECTORS as STEP_3_SELECTORS
from ..cita_flow.step_4_confirmacion import capturar_confirmacion_cita
from ..login_flow.auth import realizar_login_sel
from ..login_flow.browser import escribir_input_rapido
from ..login_flow.config import URL_LOGIN, resolver_credenciales_por_grupo_ruc
from ..login_flow.selectors import LOGIN_SELECTORS
from ..notifications import register_nro_solicitud_terminal

load_dotenv()

script_dir = os.path.dirname(os.path.abspath(__file__))
package_dir = os.path.dirname(os.path.dirname(script_dir))
project_root = os.path.dirname(package_dir)
excel_path_env = os.getenv("EXCEL_PATH", "").strip()
if excel_path_env:
    EXCEL_PATH = excel_path_env if os.path.isabs(excel_path_env) else os.path.join(project_root, excel_path_env)
else:
    EXCEL_PATH = os.path.join(project_root, "data", "programaciones-armas.xlsx")

SEL = {
    **LOGIN_SELECTORS,
    # ── Menú PanelMenu PrimeFaces ─────────────────────────────────────────────
    # Header del acordeón CITAS  ->  el <h3> que contiene el <a>CITAS</a>
    # Hacemos clic en él para expandir/colapsar el panel
    "menu_citas_header": '#j_idt11\\:menuPrincipal .ui-panelmenu-header:has(a:text-is("CITAS"))',

    # Panel de contenido que se despliega al hacer clic en el header CITAS
    # id fijo según el HTML: j_idt11:menuPrincipal_7
    "menu_citas_panel": '#j_idt11\\:menuPrincipal_7',

    # Ítem "RESERVAS DE CITAS" — usa el onclick con menuid='7_1'
    # Selector más robusto: busca dentro del panel CITAS el span con ese texto
    "submenu_reservas": '#j_idt11\\:menuPrincipal_7 span.ui-menuitem-text:text-is("RESERVAS DE CITAS")',

    # ── SelectOneMenu: tipo de cita en Gestión de Citas ──────────────────────
    "tipo_cita_trigger": '#gestionCitasForm\\:j_idt32 .ui-selectonemenu-trigger',
    "tipo_cita_panel": '#gestionCitasForm\\:j_idt32_panel',
    "tipo_cita_label": '#gestionCitasForm\\:j_idt32_label',
    "tipo_cita_opcion_poligono": '#gestionCitasForm\\:j_idt32_panel li[data-label="EXAMEN PARA POLÍGONO DE TIRO"]',

    # ── Reserva de Cupos (tabGestion:creaCitaPolJurForm) ───────────────────
    "reserva_form": '#tabGestion\\:creaCitaPolJurForm',
    "sede_trigger": '#tabGestion\\:creaCitaPolJurForm\\:sedeId .ui-selectonemenu-trigger',
    "sede_panel": '#tabGestion\\:creaCitaPolJurForm\\:sedeId_panel',
    "sede_label": '#tabGestion\\:creaCitaPolJurForm\\:sedeId_label',
    "fecha_trigger": '#tabGestion\\:creaCitaPolJurForm\\:listaDiasId .ui-selectonemenu-trigger',
    "fecha_panel": '#tabGestion\\:creaCitaPolJurForm\\:listaDiasId_panel',
    "fecha_label": '#tabGestion\\:creaCitaPolJurForm\\:listaDiasId_label',

    # ── Tabla de programación de cupos ──────────────────────────────────────
    "tabla_programacion": '#tabGestion\\:creaCitaPolJurForm\\:dtProgramacion',
    "tabla_programacion_rows": '#tabGestion\\:creaCitaPolJurForm\\:dtProgramacion_data tr',
    "boton_siguiente": '#tabGestion\\:creaCitaPolJurForm button:has-text("Siguiente")',
    "boton_limpiar": '#tabGestion\\:creaCitaPolJurForm\\:botonLimpiar',

    **STEP_2_SELECTORS,

    # ── Paso 3 del Wizard (Resumen de Cita) ───────────────────────────────
    **STEP_3_SELECTORS,
}


SinCupoError = DomainSinCupoError
FechaNoDisponibleError = DomainFechaNoDisponibleError
TurnoDuplicadoError = DomainTurnoDuplicadoError
CuposOcupadosPostValidacionError = DomainCuposOcupadosPostValidacionError

normalizar_hora_rango = shared_utils.normalizar_hora_rango
normalizar_hora_fragmento = shared_utils.normalizar_hora_fragmento
_parsear_rango_hora_a_minutos = shared_utils.parsear_rango_hora_a_minutos
_rango_desplazado_15m = shared_utils.rango_desplazado_15m
convertir_a_entero = shared_utils.convertir_a_entero
normalizar_texto_comparable = shared_utils.normalizar_texto_comparable
extraer_token_solicitud = shared_utils.extraer_token_solicitud
normalizar_tipo_arma_excel = shared_utils.normalizar_tipo_arma_excel
clasificar_motivo_detencion = shared_utils.clasificar_motivo_detencion

obtener_trabajos_pendientes_excel = excel_ops.obtener_trabajos_pendientes_excel
cargar_primer_registro_pendiente_desde_excel = excel_ops.cargar_primer_registro_pendiente_desde_excel
registrar_sin_cupo_en_excel = excel_ops.registrar_sin_cupo_en_excel
registrar_cita_programada_en_excel = excel_ops.registrar_cita_programada_en_excel


def _hora_adaptativa_habilitada() -> bool:
    """Activa seleccion flexible de horario con fallback por vecinos/bloques."""
    return str(os.getenv("ADAPTIVE_HOUR_SELECTION", "0") or "0").strip().lower() in {"1", "true", "yes", "si", "s?"}


def _hora_adaptativa_bloque_mediodia_completo() -> bool:
    """Si esta activo, en bloque 11:45-13:00 evalua todos los slots del bloque."""
    return str(os.getenv("ADAPTIVE_HOUR_NOON_FULL_BLOCK", "1") or "1").strip().lower() in {"1", "true", "yes", "si", "s?"}


def validar_turno_duplicado_o_lanzar(page, max_wait_ms: int = 0):
    """Lanza TurnoDuplicadoError si detecta mensaje en growl/DOM."""
    msg = detectar_turno_duplicado_en_growl(page, max_wait_ms=max_wait_ms)
    if msg:
        raise TurnoDuplicadoError(msg)

def solve_captcha_ocr(page):
    """Mantiene compatibilidad del login usando el modulo captcha_flow."""
    return solve_login_captcha(page, SEL)


def _deps_paso_3_validacion_final() -> dict:
    return {
        "solve_captcha_ocr_base": solve_captcha_ocr_base,
        "escribir_input_rapido": escribir_input_rapido,
        "solve_captcha_manual": solve_captcha_manual,
        "validar_turno_duplicado_o_lanzar": validar_turno_duplicado_o_lanzar,
        "turno_duplicado_error": TurnoDuplicadoError,
        "normalizar_texto_comparable": normalizar_texto_comparable,
        "cupos_ocupados_error": CuposOcupadosPostValidacionError,
    }


def completar_fase_3_resumen(page):
    return completar_fase_3_resumen_paso_3(
        page,
        deps=_deps_paso_3_validacion_final(),
    )


def generar_cita_final_con_reintento_rapido(page, registro: dict | None = None, max_intentos: int = 3):
    return generar_cita_final_con_reintento_rapido_paso_3(
        page,
        deps=_deps_paso_3_validacion_final(),
        registro=registro,
        max_intentos=max_intentos,
    )


def esperar_hasta_servicio_disponible(page, url_objetivo: str, espera_segundos: int = 8):
    return esperar_hasta_servicio_disponible_nav(page, url_objetivo, SEL, espera_segundos=espera_segundos)


def seleccionar_en_selectonemenu(page, trigger_selector: str, panel_selector: str, label_selector: str, valor: str, nombre_campo: str):
    return seleccionar_en_selectonemenu_nav(
        page,
        trigger_selector,
        panel_selector,
        label_selector,
        valor,
        nombre_campo,
        FechaNoDisponibleError,
    )


def navegar_reservas_citas(page):
    return navegar_reservas_citas_nav(page, SEL)


def seleccionar_tipo_cita_poligono(page):
    return seleccionar_tipo_cita_poligono_nav(page, SEL)


def seleccionar_sede_y_fecha_desde_registro(page, registro: dict):
    return seleccionar_sede_y_fecha_desde_registro_paso_1(
        page,
        registro,
        seleccionar_en_selectonemenu=seleccionar_en_selectonemenu,
    )


def _deps_paso_1_reserva_cupos() -> dict:
    return {
        "normalizar_hora_rango": normalizar_hora_rango,
        "normalizar_hora_fragmento": normalizar_hora_fragmento,
        "convertir_a_entero": convertir_a_entero,
        "parsear_rango": _parsear_rango_hora_a_minutos,
        "rango_desplazado": _rango_desplazado_15m,
        "hora_adaptativa_habilitada": _hora_adaptativa_habilitada,
        "hora_adaptativa_bloque_mediodia_completo": _hora_adaptativa_bloque_mediodia_completo,
        "sin_cupo_error": SinCupoError,
    }


def seleccionar_hora_con_cupo_y_avanzar(page, registro: dict):
    seleccionar_hora_con_cupo_y_avanzar_paso_1(
        page,
        registro,
        deps=_deps_paso_1_reserva_cupos(),
    )


def limpiar_para_siguiente_registro(page, motivo: str = ""):
    """Restablece el wizard al estado inicial usando el boton Limpiar."""
    motivo_txt = f" ({motivo})" if motivo else ""
    ultimo_error = None

    candidatos = [
        SEL.get("boton_limpiar"),
        '#tabGestion\\:creaCitaPolJurForm button:has-text("Limpiar")',
        'button:has-text("Limpiar")',
    ]

    for selector in [s for s in candidatos if s]:
        try:
            boton = page.locator(selector).first
            boton.wait_for(state="visible", timeout=4000)
            boton.click(timeout=5000)
            page.wait_for_timeout(500)
            try:
                page.locator(SEL["reserva_form"]).wait_for(state="visible", timeout=10000)
            except Exception:
                pass
            print(f"[INFO] Wizard limpiado para siguiente registro{motivo_txt}")
            return
        except Exception as exc:
            ultimo_error = exc

    raise Exception(
        "No se pudo limpiar el formulario para el siguiente registro"
        f"{motivo_txt}: {ultimo_error}"
    )


def _deps_paso_2_datos_tramite() -> dict:
    return {
        "normalizar_texto_comparable": normalizar_texto_comparable,
        "extraer_token_solicitud": extraer_token_solicitud,
        "normalizar_tipo_arma_excel": normalizar_tipo_arma_excel,
        "validar_turno_duplicado_o_lanzar": validar_turno_duplicado_o_lanzar,
    }


def completar_paso_2_desde_registro(page, registro: dict):
    return completar_paso_2_desde_registro_paso_2(
        page,
        registro,
        deps=_deps_paso_2_datos_tramite(),
    )


def completar_tabla_tipos_arma_y_avanzar(page, registro: dict):
    return completar_tabla_tipos_arma_y_avanzar_paso_2(
        page,
        registro,
        deps=_deps_paso_2_datos_tramite(),
    )


# ============================================================
# FLUJO PRINCIPAL
# ============================================================

def llenar_login_sel():
    print("[INFO] INICIANDO SCRIPT SEL - Login Automtico")

    if multihilo_scheduled_habilitado():
        ejecutar_scheduled_multihilo_orquestador(
            excel_path=EXCEL_PATH,
            project_root=project_root,
        )
        return

    options = load_runtime_options()
    is_scheduled = options.is_scheduled
    hold_browser_open = options.hold_browser_open
    browser_start_maximized = options.browser_start_maximized
    browser_window_w = options.browser_window_w
    browser_window_h = options.browser_window_h
    tile_enabled = options.tile_enabled
    tile_total = options.tile_total
    tile_index = options.tile_index
    tile_screen_w = options.tile_screen_w
    tile_screen_h = options.tile_screen_h
    tile_top_offset = options.tile_top_offset
    tile_gap = options.tile_gap
    tile_frame_pad = options.tile_frame_pad
    tile_x = options.tile_x
    tile_y = options.tile_y
    tile_w = options.tile_w
    tile_h = options.tile_h
    max_run_minutes = options.max_run_minutes
    max_login_retries_per_group = options.max_login_retries_per_group
    login_validation_timeout_ms = options.login_validation_timeout_ms
    terminal_confirmaciones_requeridas = options.terminal_confirmaciones_requeridas
    nro_solicitud_confirmaciones_requeridas = options.nro_solicitud_confirmaciones_requeridas
    sin_cupo_confirmaciones_requeridas = options.sin_cupo_confirmaciones_requeridas
    max_unmapped_retries_per_record = options.max_unmapped_retries_per_record
    max_hora_fallback_retries = options.max_hora_fallback_retries
    persistent_session = options.persistent_session

    if persistent_session:
        print("[INFO] PERSISTENT_SESSION activado - navegador se reutilizara entre grupos sin cerrarse")

    inicio_total_flujo = time.time()
    duracion_total_flujo = None

    playwright = sync_playwright().start()
    browser = None
    context = None
    login_exitoso = False
    total_ok = 0
    total_sin_cupo = 0
    total_error = 0

    try:
        validar_tiempo_maximo(inicio_total_flujo, max_run_minutes)
        trabajos_pendientes = obtener_trabajos_pendientes_excel(EXCEL_PATH)
        if not trabajos_pendientes:
            print("\n No hay registros pendientes para procesar. Todos los registros han sido procesados o marcados.")
            return

        print(f"\n Registros pendientes a procesar: {len(trabajos_pendientes)}")

        grupos_ordenados = ["SELVA", "JV", "OTRO"]
        trabajos_por_grupo = agrupar_trabajos_por_grupo(trabajos_pendientes, grupos_ordenados)

        state = {
            "playwright": playwright,
            "browser": browser,
            "context": context,
            "login_exitoso": login_exitoso,
            "total_ok": total_ok,
            "total_sin_cupo": total_sin_cupo,
            "total_error": total_error,
        }
        group_deps = {
            "validar_tiempo_maximo": validar_tiempo_maximo,
            "resolver_credenciales_por_grupo_ruc": resolver_credenciales_por_grupo_ruc,
            "validar_credenciales_configuradas": validar_credenciales_configuradas,
            "realizar_login_sel": realizar_login_sel,
            "solve_captcha_ocr": solve_captcha_ocr,
            "solve_captcha_manual": solve_captcha_manual,
            "navegar_reservas_citas": navegar_reservas_citas,
            "seleccionar_tipo_cita_poligono": seleccionar_tipo_cita_poligono,
            "esperar_hasta_servicio_disponible": esperar_hasta_servicio_disponible,
            "asegurar_contexto_reserva_operativo": asegurar_contexto_reserva_operativo,
            "cargar_primer_registro_pendiente_desde_excel": cargar_primer_registro_pendiente_desde_excel,
            "seleccionar_sede_y_fecha_desde_registro": seleccionar_sede_y_fecha_desde_registro,
            "seleccionar_hora_con_cupo_y_avanzar": seleccionar_hora_con_cupo_y_avanzar,
            "completar_paso_2_desde_registro": completar_paso_2_desde_registro,
            "validar_turno_duplicado_o_lanzar": validar_turno_duplicado_o_lanzar,
            "completar_tabla_tipos_arma_y_avanzar": completar_tabla_tipos_arma_y_avanzar,
            "completar_fase_3_resumen": completar_fase_3_resumen,
            "generar_cita_final_con_reintento_rapido": generar_cita_final_con_reintento_rapido,
            "capturar_confirmacion_cita": capturar_confirmacion_cita,
            "registrar_cita_programada_en_excel": registrar_cita_programada_en_excel,
            "limpiar_para_siguiente_registro": limpiar_para_siguiente_registro,
            "clasificar_motivo_detencion": clasificar_motivo_detencion,
            "es_error_transitorio_para_relogin": es_error_transitorio_para_relogin,
            "cupos_ocupados_error": CuposOcupadosPostValidacionError,
            "normalizar_hora_rango": normalizar_hora_rango,
            "registrar_sin_cupo_en_excel": registrar_sin_cupo_en_excel,
            "turno_duplicado_error": TurnoDuplicadoError,
            "clasificar_error_terminal_registro": lambda e: clasificar_error_terminal_registro(
                e,
                SinCupoError,
                FechaNoDisponibleError,
                TurnoDuplicadoError,
            ),
            "confirmaciones_requeridas_para_categoria": lambda categoria: confirmaciones_requeridas_para_categoria(
                categoria,
                terminal_confirmaciones_requeridas,
                nro_solicitud_confirmaciones_requeridas,
                sin_cupo_confirmaciones_requeridas,
            ),
            "observacion_terminal_por_categoria": observacion_terminal_por_categoria,
            "observacion_error_no_mapeado": observacion_error_no_mapeado,
            "register_nro_solicitud_terminal": register_nro_solicitud_terminal,
            "activar_monitor_growl": activar_monitor_growl,
            "selectors": SEL,
            "url_login": URL_LOGIN,
            "excel_path": EXCEL_PATH,
            "inicio_total_flujo": inicio_total_flujo,
            "max_run_minutes": max_run_minutes,
            "max_login_retries_per_group": max_login_retries_per_group,
            "login_validation_timeout_ms": login_validation_timeout_ms,
            "terminal_confirmaciones_requeridas": terminal_confirmaciones_requeridas,
            "nro_solicitud_confirmaciones_requeridas": nro_solicitud_confirmaciones_requeridas,
            "sin_cupo_confirmaciones_requeridas": sin_cupo_confirmaciones_requeridas,
            "max_unmapped_retries_per_record": max_unmapped_retries_per_record,
            "max_hora_fallback_retries": max_hora_fallback_retries,
            "persistent_session": persistent_session,
            "browser_start_maximized": browser_start_maximized,
            "browser_window_w": browser_window_w,
            "browser_window_h": browser_window_h,
            "tile_enabled": tile_enabled,
            "tile_x": tile_x,
            "tile_y": tile_y,
            "tile_w": tile_w,
            "tile_h": tile_h,
            "tile_screen_w": tile_screen_w,
            "tile_screen_h": tile_screen_h,
        }

        for grupo_ruc in grupos_ordenados:
            trabajos_grupo = trabajos_por_grupo.get(grupo_ruc, [])
            if not trabajos_grupo:
                continue
            state = procesar_grupo_ruc(grupo_ruc, trabajos_grupo, state, group_deps)

        browser = state["browser"]
        context = state["context"]
        login_exitoso = state["login_exitoso"]
        total_ok = state["total_ok"]
        total_sin_cupo = state["total_sin_cupo"]
        total_error = state["total_error"]

        duracion_total_flujo = time.time() - inicio_total_flujo
        print(f"\n Tiempo total del flujo: {duracion_total_flujo:.2f} segundos")
        print(f" Resumen: OK={total_ok} | SIN_CUPO={total_sin_cupo} | ERROR={total_error}")

        if login_exitoso:
            print("\n[INFO] Flujo completado.")
            if duracion_total_flujo is not None:
                print(f"    Duracin final del flujo: {duracion_total_flujo:.2f} segundos")
            if hold_browser_open and not is_scheduled:
                print("   Navegador abierto para uso manual.")
                print("   Presiona Ctrl+C o cierra la ventana cuando termines.")
                try:
                    while True:
                        time.sleep(60)
                except KeyboardInterrupt:
                    print("\n Interrupcin manual. Cerrando navegador...")
        else:
            print("\n[ERROR] No se pudo completar el login despus de todos los intentos.")
            if not is_scheduled:
                input("   Presiona ENTER para cerrar el navegador...")

    except KeyboardInterrupt as e:
        if duracion_total_flujo is None:
            duracion_total_flujo = time.time() - inicio_total_flujo
        print("\n Ejecucin interrumpida.")
        print(f"   -> Motivo: {e}")
        print(f"    Tiempo transcurrido: {duracion_total_flujo:.2f} segundos")
        print(f"    Resumen parcial: OK={total_ok} | SIN_CUPO={total_sin_cupo} | ERROR={total_error}")

    finally:
        try:
            if context is not None:
                context.close()
        except Exception:
            pass
        try:
            if browser is not None:
                browser.close()
        except Exception:
            pass
        try:
            playwright.stop()
        except Exception:
            pass
        print("Navegador cerrado.")


if __name__ == "__main__":
    llenar_login_sel()
