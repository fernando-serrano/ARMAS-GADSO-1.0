from __future__ import annotations


def escribir_input_jsf(page, selector: str, valor: str):
    for intento in range(4):
        campo = page.locator(selector)
        campo.wait_for(state="visible", timeout=12000)

        campo.click()
        campo.press("Control+A")
        campo.press("Backspace")
        campo.type(valor, delay=65)
        campo.evaluate('el => { el.dispatchEvent(new Event("input", {bubbles:true})); el.dispatchEvent(new Event("change", {bubbles:true})); }')
        page.wait_for_timeout(140)

        actual = campo.input_value().strip()
        if actual != valor:
            campo.evaluate(
                '''(el, val) => {
                    el.focus();
                    el.value = val;
                    el.setAttribute("value", val);
                    el.dispatchEvent(new Event("input", { bubbles: true }));
                    el.dispatchEvent(new Event("change", { bubbles: true }));
                }''',
                valor
            )
            page.wait_for_timeout(120)
            actual = campo.input_value().strip()

        if actual == valor:
            campo.evaluate('el => el.blur()')
            page.wait_for_timeout(220)
            try:
                confirmado = page.locator(selector).input_value().strip()
            except Exception:
                confirmado = ""
            if confirmado == valor:
                return
            actual = confirmado

        print(f"   [WARNING] Campo {selector}: esperado '{valor}', tiene '{actual}' -> reintentando ({intento+1}/4)")
        page.wait_for_timeout(260)

    raise Exception(f"No se pudo fijar correctamente el valor del campo {selector}")


def escribir_input_rapido(page, selector: str, valor: str):
    campo = page.locator(selector)
    campo.wait_for(state="visible", timeout=10000)
    campo.click()
    campo.fill(valor)
    campo.evaluate('el => { el.dispatchEvent(new Event("input", {bubbles:true})); el.dispatchEvent(new Event("change", {bubbles:true})); }')
    campo.blur()
    if campo.input_value() != valor:
        campo.click()
        campo.press("Control+A")
        campo.press("Backspace")
        campo.type(valor, delay=10)
        campo.evaluate('el => { el.dispatchEvent(new Event("input", {bubbles:true})); el.dispatchEvent(new Event("change", {bubbles:true})); }')
        campo.blur()
