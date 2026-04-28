from __future__ import annotations

import unittest

from armas_gadso import utils


class UtilsTests(unittest.TestCase):
    def test_normalizar_fecha_excel_acepta_iso(self) -> None:
        self.assertEqual(utils.normalizar_fecha_excel("2026-05-19"), "19/05/2026")

    def test_normalizar_hora_rango_estandariza_formato(self) -> None:
        self.assertEqual(utils.normalizar_hora_rango("8:0 - 8:15"), "08:00-08:15")

    def test_parsear_rango_hora_a_minutos(self) -> None:
        self.assertEqual(utils.parsear_rango_hora_a_minutos("12:00-12:15"), (720, 735))

    def test_rango_desplazado_15m(self) -> None:
        self.assertEqual(utils.rango_desplazado_15m("12:00-12:15", 1), "12:15-12:30")

    def test_extraer_token_solicitud_remueve_ceros_izquierda(self) -> None:
        self.assertEqual(utils.extraer_token_solicitud("000123-ABC"), "123")

    def test_normalizar_texto_comparable_quita_tildes(self) -> None:
        self.assertEqual(utils.normalizar_texto_comparable("Seguridad Priváda"), "SEGURIDAD PRIVADA")

    def test_clasificar_motivo_detencion_ventana_cerrada(self) -> None:
        error = Exception("Target page, context or browser has been closed")
        self.assertEqual(utils.clasificar_motivo_detencion(error), "VENTANA_CERRADA")


if __name__ == "__main__":
    unittest.main()
