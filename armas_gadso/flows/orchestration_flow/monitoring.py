from __future__ import annotations

import os
import time


def debug_turno_duplicado_activo() -> bool:
    return str(os.getenv("DEBUG_TURNO_DUPLICADO", "0") or "0").strip().lower() in {"1", "true", "yes", "si", "sí"}


def log_debug_turno_duplicado(msg: str) -> None:
    if debug_turno_duplicado_activo():
        print(f"[DEBUG][TURNO_DUPLICADO] {msg}")


def obtener_buffer_growl(page, limite: int = 8) -> list:
    """Devuelve ultimas entradas capturadas por el monitor growl."""
    try:
        data = page.evaluate(
            """
            (limit) => {
                const arr = window.__armasGrowlBuffer || [];
                return arr.slice(-Math.max(1, Number(limit) || 8)).map(x => x && x.text ? String(x.text) : '');
            }
            """,
            limite,
        )
        if isinstance(data, list):
            return [str(x or "").strip() for x in data if str(x or "").strip()]
    except Exception:
        pass
    return []


def script_monitor_growl_js() -> str:
    return """
    (() => {
        if (window.__armasGrowlInstalled) return;
        window.__armasGrowlInstalled = true;
        window.__armasGrowlBuffer = window.__armasGrowlBuffer || [];

        const pushMessage = (text) => {
            if (!text) return;
            const t = String(text).trim();
            if (!t) return;
            window.__armasGrowlBuffer.push({ text: t, ts: Date.now() });
            if (window.__armasGrowlBuffer.length > 160) {
                window.__armasGrowlBuffer = window.__armasGrowlBuffer.slice(-160);
            }
        };

        const extractFromNode = (node) => {
            if (!node) return;
            const selectors = '.ui-growl-title, .ui-growl-message, .ui-growl-message-error, #mensajesGrowl_container .ui-growl-title, #mensajesGrowl_container .ui-growl-message';

            if (typeof node.matches === 'function' && node.matches(selectors)) {
                pushMessage(node.textContent || '');
            }

            if (typeof node.querySelectorAll === 'function') {
                const nodes = Array.from(node.querySelectorAll(selectors));
                for (const n of nodes) {
                    pushMessage(n.textContent || '');
                }
            }
        };

        const observer = new MutationObserver((mutations) => {
            for (const m of mutations) {
                for (const n of m.addedNodes || []) {
                    extractFromNode(n);
                }
                if (m.type === 'characterData' && m.target) {
                    pushMessage(m.target.textContent || '');
                }
            }
        });

        if (document && document.body) {
            observer.observe(document.body, { childList: true, subtree: true, characterData: true });
            extractFromNode(document.body);
        }
    })();
    """


def activar_monitor_growl(page) -> None:
    """Instala un buffer JS para conservar mensajes growl aunque desaparezcan del DOM."""
    try:
        monitor_script = script_monitor_growl_js()
        page.add_init_script(script=monitor_script)
        page.evaluate(monitor_script)
        log_debug_turno_duplicado("monitor growl instalado")
    except Exception:
        pass


def detectar_turno_duplicado_en_growl(page, max_wait_ms: int = 0) -> str:
    """Busca mensaje de turno duplicado en growls con espera opcional."""
    deadline = time.time() + (max_wait_ms / 1000.0)
    while True:
        mensajes = []
        instalacion_activa = False
        try:
            instalacion_activa = bool(page.evaluate("() => Boolean(window.__armasGrowlInstalled)"))
        except Exception:
            instalacion_activa = False

        for selector in [
            ".ui-growl-item .ui-growl-title",
            ".ui-growl-item .ui-growl-message",
            ".ui-growl-message",
            ".ui-growl-message-error",
            "#mensajesGrowl_container .ui-growl-title",
            "#mensajesGrowl_container .ui-growl-message",
        ]:
            try:
                loc = page.locator(selector)
                total = min(loc.count(), 6)
                for i in range(total):
                    txt = (loc.nth(i).text_content() or "").strip()
                    if txt:
                        mensajes.append(txt)
            except Exception:
                pass

        try:
            buffer_msgs = page.evaluate(
                """
                () => (window.__armasGrowlBuffer || []).map(x => x && x.text ? String(x.text) : '')
                """
            )
            if isinstance(buffer_msgs, list):
                for txt in buffer_msgs:
                    t = str(txt or "").strip()
                    if t:
                        mensajes.append(t)
        except Exception:
            pass

        try:
            body_text = (page.locator("body").text_content(timeout=400) or "").strip()
            if body_text:
                mensajes.append(body_text)
        except Exception:
            pass

        try:
            html_doc = (page.content() or "").lower()
            if (
                "ya existe un turno registrado" in html_doc
                or ("misma persona" in html_doc and "tipo de licencia" in html_doc)
            ):
                log_debug_turno_duplicado("mensaje detectado por fallback HTML")
                return "Ya existe un turno registrado para la misma persona y Tipo de Licencia"
        except Exception:
            pass

        for msg in mensajes:
            msg_low = msg.lower()
            if (
                "ya existe un turno registrado" in msg_low
                or ("misma persona" in msg_low and "tipo de licencia" in msg_low)
            ):
                log_debug_turno_duplicado(f"mensaje detectado: {msg[:180]}")
                return msg

        if max_wait_ms <= 0 or time.time() >= deadline:
            if debug_turno_duplicado_activo():
                ultimos = obtener_buffer_growl(page, limite=8)
                log_debug_turno_duplicado(
                    f"sin match. monitor_instalado={instalacion_activa} | mensajes_buffer={len(ultimos)} | ultimos={ultimos}"
                )
            return ""
        page.wait_for_timeout(120)
