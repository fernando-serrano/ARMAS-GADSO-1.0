from __future__ import annotations

import os
import unittest
from unittest import mock

from armas_gadso.flows.cita_flow.step_3_validacion_final import actions


class CaptchaForzadoParaPruebasTests(unittest.TestCase):
    def test_inactivo_por_defecto(self) -> None:
        """El flujo productivo no debe verse afectado si la variable no esta puesta."""
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TEST_FORCED_CAPTCHA", None)
            self.assertEqual(actions.captcha_forzado_para_pruebas(), "")

    def test_inactivo_si_esta_vacia(self) -> None:
        with mock.patch.dict(os.environ, {"TEST_FORCED_CAPTCHA": "   "}):
            self.assertEqual(actions.captcha_forzado_para_pruebas(), "")

    def test_devuelve_el_valor_en_mayusculas(self) -> None:
        with mock.patch.dict(os.environ, {"TEST_FORCED_CAPTCHA": " abcde "}):
            self.assertEqual(actions.captcha_forzado_para_pruebas(), "ABCDE")

    def test_rechaza_valores_que_no_tienen_5_caracteres(self) -> None:
        """SUCAMEC exige 5 caracteres; un valor invalido caeria al solver manual y
        dejaria el test colgado esperando intervencion humana."""
        for valor in ("ABC", "ABCDEFG"):
            with self.subTest(valor=valor):
                with mock.patch.dict(os.environ, {"TEST_FORCED_CAPTCHA": valor}):
                    self.assertEqual(actions.captcha_forzado_para_pruebas(), "")


if __name__ == "__main__":
    unittest.main()
