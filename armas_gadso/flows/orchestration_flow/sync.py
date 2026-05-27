"""
Sincronizacion con SUCAMEC (JSF + PrimeFaces).

Regla operativa (critica para la ventana de las 00:00): NO ejecutar la siguiente
accion hasta confirmar que la anterior termino. Esto evita acciones simultaneas con
el navegador (ej. tocar la tabla de armas mientras el AJAX del Nro. Solicitud aun
re-renderiza, que a medianoche tardo hasta 20s y rompia el flujo).

Senal de sincronizacion confirmada en vivo (.claude/recorrido_instrumentacion.json):
  - PRIMARIA: PrimeFaces.ajax.Queue.isEmpty()  -> hay AJAX en vuelo?
  - RESPALDO: .ui-widget-overlay visible        -> overlay de "ocupado"
  - DESCARTADAS: jQuery.active y .ui-blockui (siempre 0 en SUCAMEC)

Los growls se leen del DOM (.ui-growl-item), NO del buffer JS (que demostro quedar
vacio aunque hubiera growls en pantalla).
"""
from __future__ import annotations

import os
import time


# --- 1) Esperar a que PrimeFaces termine su AJAX ---------------------------------

_JS_AJAX_OCUPADO = r"""
() => {
    try {
        const pf = window.PrimeFaces;
        const q = pf && pf.ajax && pf.ajax.Queue;
        const cola = (q && typeof q.isEmpty === 'function') ? !q.isEmpty() : false;
        const overlay = document.querySelectorAll('.ui-widget-overlay').length > 0;
        return !!(cola || overlay);
    } catch (e) { return false; }
}
"""


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, str(default)) or default).strip())
    except Exception:
        return default


def esperar_fin_ajax_primefaces(
    page,
    timeout_ms: int | None = None,
    estable_ms: int | None = None,
    poll_ms: int = 60,
) -> bool:
    """
    Espera a que la cola AJAX de PrimeFaces este vacia y sin overlay, de forma ESTABLE
    durante `estable_ms` (para no continuar en un hueco momentaneo entre dos AJAX).

    Devuelve True si el navegador quedo en reposo; False si se agoto el timeout.
    NO lanza: el llamador decide que hacer si retorna False (normalmente seguir igual,
    porque luego se valida la presencia del elemento esperado).

    IMPORTANTE: timeout_ms es el TECHO maximo, NO un tiempo fijo. La funcion CONTINUA en
    cuanto la cola queda vacia (normalmente <1s); el techo solo aplica si SUCAMEC se cuelga.

    Defaults tolerantes por la lentitud de SUCAMEC; configurables por env:
      - AJAX_SETTLE_TIMEOUT_MS (default 45000)  -> techo, no espera fija
      - AJAX_SETTLE_ESTABLE_MS (default 350)
    """
    if timeout_ms is None:
        timeout_ms = _env_int("AJAX_SETTLE_TIMEOUT_MS", 45000)
    if estable_ms is None:
        estable_ms = _env_int("AJAX_SETTLE_ESTABLE_MS", 350)

    deadline = time.time() + max(0, timeout_ms) / 1000.0
    estable_desde = None
    while time.time() < deadline:
        try:
            ocupado = bool(page.evaluate(_JS_AJAX_OCUPADO))
        except Exception:
            ocupado = False

        if not ocupado:
            if estable_desde is None:
                estable_desde = time.time()
            elif (time.time() - estable_desde) * 1000.0 >= estable_ms:
                return True
        else:
            estable_desde = None

        page.wait_for_timeout(poll_ms)
    return False


# --- 2) Lectura de growls desde el DOM (no el buffer) ----------------------------

_JS_GROWLS = r"""
() => Array.from(document.querySelectorAll('.ui-growl-item')).map(n => ({
    titulo: ((n.querySelector('.ui-growl-title')||{}).textContent||'').trim(),
    msg:    ((n.querySelector('.ui-growl-message')||{}).textContent||'').trim(),
    error:  /ui-growl-error|ui-state-error/.test(n.className||'')
}))
"""


def leer_growls(page) -> list:
    """Devuelve los growls actualmente en el DOM: [{titulo, msg, error}]."""
    try:
        data = page.evaluate(_JS_GROWLS)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def hay_growl_de_error_nuevo(page, baseline: list | None = None) -> str:
    """
    Si hay un growl de error que NO estaba en `baseline`, devuelve su texto; si no, "".
    Se considera error por clase (ui-growl-error / ui-state-error) o por titulo que
    empieza con "Error". Lee del DOM (el buffer JS no es fiable).
    """
    base = {(g.get("titulo", ""), g.get("msg", "")) for g in (baseline or [])}
    for g in leer_growls(page):
        titulo = g.get("titulo", "")
        es_error = bool(g.get("error")) or titulo.strip().lower().startswith("error")
        if es_error and (titulo, g.get("msg", "")) not in base:
            texto = (titulo + " " + g.get("msg", "")).strip()
            return texto or "Growl de error detectado"
    return ""
