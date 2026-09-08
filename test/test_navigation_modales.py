from __future__ import annotations

import unittest

from armas_gadso.flows.orchestration_flow import navigation


MSG_INTERCEPTADO = (
    'Locator.click: Timeout 30000ms exceeded. Call log: '
    '<div class="ui-widget-overlay ui-dialog-mask" '
    'id="mainForm:dlgComunicadoInstitucional_modal"> intercepts pointer events'
)


class _FakeLocator:
    """Locator minimo: si hay una mascara modal activa, click() falla como Playwright."""

    def __init__(self, page, selector: str) -> None:
        self._page = page
        self._selector = selector

    @property
    def first(self):
        return self

    def _es_boton_cierre(self) -> bool:
        return "titlebar-close" in self._selector

    def _existe(self) -> bool:
        if self._es_boton_cierre():
            return any(d in self._selector for d in self._page.dialogos_abiertos)
        if "_modal" in self._selector:
            return any(d + "_modal" in self._selector for d in self._page.dialogos_abiertos)
        return True

    def count(self) -> int:
        return 1 if self._existe() else 0

    def is_visible(self) -> bool:
        return self._existe()

    def wait_for(self, **kwargs) -> None:
        if not self._existe():
            raise TimeoutError("no visible: " + self._selector)

    def click(self, **kwargs) -> None:
        if self._es_boton_cierre():
            if self._page.modal_indestructible:
                return
            dlg = next(d for d in self._page.dialogos_abiertos if d in self._selector)
            self._page.dialogos_abiertos.remove(dlg)
            return

        # SUCAMEC pinta el comunicado por AJAX DESPUES de que la URL ya cambio: el modal
        # aparece justo cuando se intenta el primer click, no antes.
        if self._page.dialogos_diferidos:
            self._page.dialogos_abiertos.extend(self._page.dialogos_diferidos)
            self._page.dialogos_diferidos = []

        if self._page.dialogos_abiertos:
            self._page.clicks_interceptados.append(self._selector)
            raise TimeoutError(MSG_INTERCEPTADO)

        self._page.clicks.append(self._selector)


class _FakePage:
    def __init__(
        self,
        dialogos_abiertos: list | None = None,
        dialogos_diferidos: list | None = None,
        evaluate_falla: bool = False,
        modal_indestructible: bool = False,
    ) -> None:
        self.modal_indestructible = modal_indestructible
        self.dialogos_abiertos = list(dialogos_abiertos or [])
        self.dialogos_diferidos = list(dialogos_diferidos or [])
        self.evaluate_falla = evaluate_falla
        self.clicks: list = []
        self.clicks_interceptados: list = []

    def locator(self, selector: str) -> _FakeLocator:
        return _FakeLocator(self, selector)

    def evaluate(self, script, *args):
        if "ui-dialog-mask" in script:
            if self.evaluate_falla:
                raise RuntimeError("Execution context was destroyed")
            return [d + "_modal" for d in self.dialogos_abiertos]
        return None

    def wait_for_timeout(self, ms: int) -> None:
        return None


SEL = {
    "menu_citas_header": ".menu-citas-header",
    "menu_citas_panel": ".menu-citas-panel",
    "submenu_reservas": ".submenu-reservas",
}

COMUNICADO = "mainForm:dlgComunicadoInstitucional"


class CerrarDialogosModalesTests(unittest.TestCase):
    def test_cierra_comunicado_institucional(self) -> None:
        page = _FakePage([COMUNICADO])
        self.assertEqual(navigation.cerrar_dialogos_modales(page), [COMUNICADO])
        self.assertEqual(page.dialogos_abiertos, [])

    def test_sin_dialogos_no_hace_nada(self) -> None:
        page = _FakePage()
        self.assertEqual(navigation.cerrar_dialogos_modales(page), [])


class ClickToleranteAModalesTests(unittest.TestCase):
    def test_reintenta_cuando_el_modal_aparece_en_el_click(self) -> None:
        """Caso real del log 20260908_100425: el modal NO existe al inicio de la
        navegacion y aparece justo cuando se intenta el click al menu CITAS."""
        page = _FakePage(dialogos_diferidos=[COMUNICADO])
        navigation.click_tolerante_a_modales(
            page, page.locator(SEL["menu_citas_header"]), "menu CITAS"
        )
        self.assertEqual(page.clicks, [SEL["menu_citas_header"]])
        self.assertEqual(page.dialogos_abiertos, [])

    def test_respeta_el_presupuesto_si_el_modal_no_se_cierra(self) -> None:
        """Peor caso: la mascara nunca desaparece. Debe rendirse dentro del presupuesto
        y propagar el error de interceptacion, sin quedarse en bucle."""
        import time as _t

        page = _FakePage([COMUNICADO], modal_indestructible=True)
        inicio = _t.monotonic()
        with self.assertRaises(TimeoutError) as ctx:
            navigation.click_tolerante_a_modales(
                page,
                page.locator(SEL["menu_citas_header"]),
                "menu CITAS",
                timeout_total_ms=300,
            )
        transcurrido = _t.monotonic() - inicio
        self.assertIn("intercepts pointer events", str(ctx.exception))
        self.assertLess(transcurrido, 5.0, "no debe exceder el presupuesto")

    def test_propaga_errores_que_no_son_de_modal(self) -> None:
        class _LocatorRoto:
            def click(self, **kwargs):
                raise TimeoutError("Locator.click: Timeout 30000ms exceeded. no such element")

        page = _FakePage()
        with self.assertRaises(TimeoutError):
            navigation.click_tolerante_a_modales(page, _LocatorRoto(), "algo")


class NavegarReservasCitasTests(unittest.TestCase):
    def test_modal_presente_desde_el_inicio(self) -> None:
        page = _FakePage([COMUNICADO])
        navigation.navegar_reservas_citas(page, SEL)
        self.assertEqual(page.dialogos_abiertos, [])
        self.assertIn(SEL["submenu_reservas"], page.clicks)

    def test_modal_que_aparece_tarde(self) -> None:
        """El fallo que seguia colgando: el modal llega despues del chequeo previo."""
        page = _FakePage(dialogos_diferidos=[COMUNICADO])
        navigation.navegar_reservas_citas(page, SEL)
        self.assertEqual(page.dialogos_abiertos, [])
        self.assertIn(SEL["submenu_reservas"], page.clicks)
        self.assertTrue(page.clicks_interceptados, "el test debe ejercitar la interceptacion")

    def test_evaluate_que_falla_no_rompe_la_navegacion(self) -> None:
        page = _FakePage(evaluate_falla=True)
        navigation.navegar_reservas_citas(page, SEL)
        self.assertIn(SEL["submenu_reservas"], page.clicks)


if __name__ == "__main__":
    unittest.main()
