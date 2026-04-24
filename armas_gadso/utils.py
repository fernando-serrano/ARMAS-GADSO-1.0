from __future__ import annotations

import re
import unicodedata
from datetime import datetime


def normalizar_fecha_excel(valor_fecha: str) -> str:
    """Convierte fechas de Excel al formato dd/mm/yyyy esperado por SEL."""
    texto = str(valor_fecha or "").strip()
    if not texto:
        return ""

    texto_base = texto.split(" ")[0].strip()

    if "/" in texto_base:
        for fmt in ("%d/%m/%Y", "%d/%m/%y"):
            try:
                return datetime.strptime(texto_base, fmt).strftime("%d/%m/%Y")
            except ValueError:
                continue

    try:
        return datetime.fromisoformat(texto_base).strftime("%d/%m/%Y")
    except ValueError:
        pass

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(texto_base, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue

    return texto_base


def normalizar_hora_fragmento(valor_hora: str) -> str:
    """Normaliza una hora a HH:MM (ej: 8:5 -> 08:05)."""
    texto = str(valor_hora or "").strip().replace(".", ":")
    if ":" not in texto:
        return texto
    partes = texto.split(":")
    if len(partes) != 2:
        return texto
    try:
        hh = int(partes[0])
        mm = int(partes[1])
    except ValueError:
        return texto
    return f"{hh:02d}:{mm:02d}"


def normalizar_hora_rango(valor_rango: str) -> str:
    """Normaliza rango de hora a HH:MM-HH:MM."""
    texto = str(valor_rango or "").strip()
    if not texto:
        return ""
    texto = texto.replace("–", "-").replace("—", "-").replace(" a ", "-").replace(" ", "")
    partes = texto.split("-")
    if len(partes) != 2:
        return texto
    inicio = normalizar_hora_fragmento(partes[0])
    fin = normalizar_hora_fragmento(partes[1])
    return f"{inicio}-{fin}"


def parsear_rango_hora_a_minutos(valor_rango: str):
    """Convierte HH:MM-HH:MM a minutos (inicio, fin). Devuelve None si no parsea."""
    texto = normalizar_hora_rango(valor_rango)
    match = re.match(r"^(\d{2}):(\d{2})-(\d{2}):(\d{2})$", texto)
    if not match:
        return None
    ini = int(match.group(1)) * 60 + int(match.group(2))
    fin = int(match.group(3)) * 60 + int(match.group(4))
    return ini, fin


def _formatear_minutos_hhmm(total_min: int) -> str:
    hh = (int(total_min) // 60) % 24
    mm = int(total_min) % 60
    return f"{hh:02d}:{mm:02d}"


def rango_desplazado_15m(valor_rango: str, delta_slots: int) -> str:
    parsed = parsear_rango_hora_a_minutos(valor_rango)
    if not parsed:
        return ""
    ini, fin = parsed
    delta = int(delta_slots) * 15
    return f"{_formatear_minutos_hhmm(ini + delta)}-{_formatear_minutos_hhmm(fin + delta)}"


def convertir_a_entero(texto: str) -> int:
    numeros = re.findall(r"\d+", str(texto or ""))
    return int(numeros[0]) if numeros else 0


def normalizar_texto_comparable(texto: str) -> str:
    base = str(texto or "").strip().upper()
    base = unicodedata.normalize("NFKD", base)
    base = "".join(c for c in base if not unicodedata.combining(c))
    base = re.sub(r"\s+", " ", base)
    return base


def limpiar_valor_excel(valor: str) -> str:
    """Limpia artefactos comunes de celdas Excel exportadas a texto."""
    texto = str(valor or "")
    texto = re.sub(r"_x[0-9A-Fa-f]{4}_", "", texto)
    texto = texto.replace("\r", " ").replace("\n", " ")
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def extraer_token_solicitud(valor: str) -> str:
    """Obtiene el numero principal de solicitud para comparar dentro del label del combo."""
    texto = str(valor or "")
    grupos = re.findall(r"\d+", texto)
    if not grupos:
        return ""
    token = grupos[0].lstrip("0")
    return token if token else "0"


def normalizar_tipo_arma_excel(valor: str) -> str:
    """Normaliza valor de tipo_arma del Excel para comparaciones."""
    base = normalizar_texto_comparable(valor)
    equivalencias = {
        "LARG": "LARGA",
        "LARGA": "LARGA",
        "CORTA": "CORTA",
        "PISTOLA": "PISTOLA",
        "REVOLVER": "REVOLVER",
        "CARABINA": "CARABINA",
        "ESCOPETA": "ESCOPETA",
    }
    return equivalencias.get(base, base)


def inferir_objetivo_arma_desde_excel(valor: str) -> str:
    """Interpreta texto libre de tipo_arma y devuelve una clave usable."""
    base = normalizar_texto_comparable(valor)
    if not base:
        return ""
    if "ESCOPETA" in base:
        return "ESCOPETA"
    if "CARABINA" in base:
        return "CARABINA"
    if "REVOLVER" in base:
        return "REVOLVER"
    if "PISTOLA" in base:
        return "PISTOLA"
    if "LARG" in base:
        return "LARGA"
    if "CORT" in base:
        return "CORTA"
    return normalizar_tipo_arma_excel(base)


def fecha_comparable(valor_fecha: str) -> str:
    """Convierte fecha de Excel a una cadena comparable dd/mm/yyyy."""
    return normalizar_fecha_excel(valor_fecha)


def normalizar_ruc_operativo(valor_ruc: str) -> str:
    """Normaliza texto de RUC/razon social para clasificacion operativa."""
    return normalizar_texto_comparable(limpiar_valor_excel(valor_ruc))


def clasificar_motivo_detencion(error: BaseException) -> str:
    """Clasifica cierres/interrupciones para logs operativos mas claros."""
    if isinstance(error, KeyboardInterrupt):
        return "INTERRUPCION_MANUAL"

    texto = str(error or "").lower()
    senales_cierre = [
        "target page, context or browser has been closed",
        "browser has been closed",
        "context closed",
        "page closed",
        "connection closed",
    ]
    if any(s in texto for s in senales_cierre):
        return "VENTANA_CERRADA"

    return ""
