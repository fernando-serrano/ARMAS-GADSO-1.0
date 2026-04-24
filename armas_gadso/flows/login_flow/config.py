from __future__ import annotations

import os

from dotenv import load_dotenv

"""Configuracion especifica del acceso SEL."""

load_dotenv()

URL_LOGIN = "https://www.sucamec.gob.pe/sel/faces/login.xhtml?faces-redirect=true"


def _credenciales_desde_env(prefix: str = "") -> dict:
    return {
        "tipo_documento_valor": os.getenv(f"{prefix}TIPO_DOC", "RUC"),
        "numero_documento": os.getenv(f"{prefix}NUMERO_DOCUMENTO", ""),
        "usuario": os.getenv(f"{prefix}USUARIO_SEL", ""),
        "contrasena": os.getenv(f"{prefix}CLAVE_SEL", ""),
    }


def credenciales_default() -> dict:
    return _credenciales_desde_env()


def credenciales_selva() -> dict:
    return _credenciales_desde_env("SELVA_")


def resolver_credenciales_por_grupo_ruc(grupo_ruc: str) -> dict:
    if grupo_ruc == "SELVA":
        return credenciales_selva()
    return credenciales_default()


__all__ = [
    "URL_LOGIN",
    "credenciales_default",
    "credenciales_selva",
    "resolver_credenciales_por_grupo_ruc",
]
