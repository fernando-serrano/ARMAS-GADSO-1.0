from __future__ import annotations

import os
from datetime import date

try:
    import pandas as pd
except ImportError:
    pd = None

from .utils import (
    fecha_comparable,
    inferir_objetivo_arma_desde_excel,
    limpiar_valor_excel,
    normalizar_fecha_excel,
    normalizar_hora_rango,
    normalizar_ruc_operativo,
    normalizar_texto_comparable,
)


def obtener_indices_relacionados_registro(registro: dict) -> list:
    indices = []
    for idx in registro.get("_excel_indices_relacionados", []) or []:
        try:
            indices.append(int(idx))
        except Exception:
            continue

    idx_principal = registro.get("_excel_index", None)
    try:
        if idx_principal is not None:
            indices.append(int(idx_principal))
    except Exception:
        pass

    return sorted(set(indices))


def obtener_grupo_ruc(valor_ruc: str) -> str:
    base = normalizar_ruc_operativo(valor_ruc)
    if "SELVA" in base or "20493762789" in base:
        return "SELVA"
    if "J&V" in base or "J V" in base or "RESGUARDO" in base or "20100901481" in base:
        return "JV"
    return "OTRO"


def prioridad_orden(valor_prioridad: str) -> int:
    base = normalizar_texto_comparable(limpiar_valor_excel(valor_prioridad))
    return 0 if base == "ALTA" else 1


def _asegurar_pandas() -> None:
    if pd is None:
        raise Exception("Falta dependencia 'pandas'. Instala con: pip install pandas openpyxl")


def _leer_excel_normalizado(ruta_excel: str):
    _asegurar_pandas()
    if not os.path.exists(ruta_excel):
        raise Exception(f"No se encontro el Excel en: {ruta_excel}")

    df = pd.read_excel(ruta_excel, dtype=str)
    df.columns = [str(c).strip() for c in df.columns]
    for col in df.columns:
        df[col] = df[col].fillna("").astype(str).apply(limpiar_valor_excel)
    return df


def _col_norm(df, nombre_col: str):
    if nombre_col in df.columns:
        return df[nombre_col].fillna("").astype(str).str.strip()
    return pd.Series([""] * len(df), index=df.index)


def obtener_trabajos_pendientes_excel(ruta_excel: str) -> list:
    df = _leer_excel_normalizado(ruta_excel)
    if "estado" not in df.columns:
        raise Exception("El Excel no contiene la columna 'estado'")

    if "doc_vigilante" not in df.columns:
        df["doc_vigilante"] = ""
    if "dni" not in df.columns:
        df["dni"] = ""
    if "nro_solicitud" not in df.columns:
        df["nro_solicitud"] = ""
    if "ruc" not in df.columns:
        df["ruc"] = ""
    if "prioridad" not in df.columns:
        df["prioridad"] = "Normal"

    fecha_col_programacion = "fecha_programacion" if "fecha_programacion" in df.columns else "fecha"
    if fecha_col_programacion not in df.columns:
        raise Exception("El Excel no contiene columna de fecha (fecha_programacion/fecha)")

    pendientes = df[df["estado"].str.upper().str.contains("PENDIENTE", na=False)].copy()
    print(f"   -> Registros con estado 'PENDIENTE': {len(pendientes)}")
    if pendientes.empty:
        return []

    validar_hoy = os.getenv("VALIDAR_FECHA_PROGRAMACION_HOY", "1").strip().lower() in {"1", "true", "si", "sí", "yes"}
    if validar_hoy:
        hoy = date.today().strftime("%d/%m/%Y")
        print(f"   -> Validando fecha de hoy: {hoy}")
        pendientes_antes = len(pendientes)
        pendientes = pendientes[pendientes[fecha_col_programacion].apply(fecha_comparable) == hoy]
        print(f"   -> Registros despues de filtrar por fecha: {len(pendientes)} (filtrados: {pendientes_antes - len(pendientes)})")
        if pendientes.empty:
            return []

    pendientes["_idx_excel"] = pendientes.index
    pendientes["_doc_norm"] = pendientes.apply(
        lambda r: str(r.get("doc_vigilante", "") or r.get("dni", "")).strip(),
        axis=1,
    )
    pendientes["_nro_norm"] = pendientes["nro_solicitud"].apply(lambda v: str(v or "").strip())
    pendientes["_fecha_prog"] = pendientes[fecha_col_programacion].apply(fecha_comparable)
    pendientes["_ruc_raw"] = pendientes["ruc"].apply(lambda v: str(v or "").strip())
    pendientes["_ruc_grupo"] = pendientes["_ruc_raw"].apply(obtener_grupo_ruc)
    pendientes["_ruc_orden"] = pendientes["_ruc_grupo"].map({"SELVA": 0, "JV": 1, "OTRO": 2})
    pendientes["_prioridad_raw"] = pendientes["prioridad"].apply(lambda v: str(v or "").strip())
    pendientes["_prioridad_orden"] = pendientes["_prioridad_raw"].apply(prioridad_orden)

    pendientes = pendientes.sort_values(
        by=["_ruc_orden", "_prioridad_orden", "_idx_excel"],
        ascending=[True, True, True],
        kind="stable",
    )

    trabajos = []
    claves_vistas = set()
    for _, fila in pendientes.iterrows():
        clave = (
            fila.get("_doc_norm", ""),
            fila.get("_nro_norm", ""),
            fila.get("_fecha_prog", ""),
            fila.get("_ruc_grupo", "OTRO"),
        )
        if clave in claves_vistas:
            continue
        claves_vistas.add(clave)
        trabajos.append(
            {
                "idx_excel": int(fila.get("_idx_excel")),
                "ruc": fila.get("_ruc_raw", ""),
                "ruc_grupo": fila.get("_ruc_grupo", "OTRO"),
                "prioridad": fila.get("_prioridad_raw", "Normal"),
                "fecha_programacion": fila.get("_fecha_prog", ""),
            }
        )

    return trabajos


def obtener_indices_pendientes_excel(ruta_excel: str) -> list:
    trabajos = obtener_trabajos_pendientes_excel(ruta_excel)
    return [t["idx_excel"] for t in trabajos]


def cargar_primer_registro_pendiente_desde_excel(ruta_excel: str, indice_excel_objetivo: int = None) -> dict:
    df = _leer_excel_normalizado(ruta_excel)

    columnas_requeridas = {"sede", "fecha", "hora_rango", "tipo_operacion", "nro_solicitud", "tipo_arma", "arma", "estado"}
    faltantes = [c for c in columnas_requeridas if c not in df.columns]
    if faltantes:
        raise Exception(f"Faltan columnas requeridas en Excel: {faltantes}")

    pendientes = df[df["estado"].str.upper().str.contains("PENDIENTE", na=False)]
    if pendientes.empty:
        raise Exception("No hay registros con estado 'Pendiente' en el Excel")

    indice_primer_pendiente = pendientes.index[0] if indice_excel_objetivo is None else indice_excel_objetivo
    if indice_primer_pendiente not in pendientes.index:
        raise Exception(f"El indice objetivo {indice_primer_pendiente} no esta en estado Pendiente")

    registro = pendientes.loc[indice_primer_pendiente].to_dict()
    registro["_excel_index"] = int(indice_primer_pendiente)
    registro["_excel_path"] = ruta_excel

    fecha_col_programacion = "fecha_programacion" if "fecha_programacion" in df.columns else "fecha"
    fecha_programacion_valor = fecha_comparable(registro.get(fecha_col_programacion, registro.get("fecha", "")))

    sede = registro.get("sede", "").strip()
    fecha = normalizar_fecha_excel(registro.get("fecha", ""))
    hora_rango = normalizar_hora_rango(registro.get("hora_rango", ""))
    tipo_operacion = registro.get("tipo_operacion", "").strip()
    nro_solicitud = registro.get("nro_solicitud", "").strip()
    doc_vigilante = registro.get("doc_vigilante", registro.get("dni", "")).strip()
    tipo_arma_base = inferir_objetivo_arma_desde_excel(registro.get("tipo_arma", ""))
    arma_base = inferir_objetivo_arma_desde_excel(registro.get("arma", ""))

    if not sede or not fecha or not hora_rango:
        raise Exception("El registro pendiente no tiene 'sede', 'fecha' o 'hora_rango' con valor")
    if not tipo_operacion or not nro_solicitud or not doc_vigilante:
        raise Exception("El registro pendiente no tiene 'tipo_operacion', 'doc_vigilante/dni' o 'nro_solicitud'")
    if not tipo_arma_base:
        raise Exception("El registro pendiente no tiene 'tipo_arma'")
    if not arma_base:
        raise Exception("El registro pendiente no tiene 'arma'")

    fecha_base = fecha_comparable(registro.get(fecha_col_programacion, registro.get("fecha", "")))
    doc_base = doc_vigilante
    nro_base = nro_solicitud
    pendientes_aux = pendientes.copy()
    pendientes_aux["fecha_norm"] = pendientes_aux[fecha_col_programacion].apply(fecha_comparable)
    pendientes_aux["doc_norm"] = pendientes_aux.apply(
        lambda r: str(r.get("doc_vigilante", "") or r.get("dni", "")).strip(),
        axis=1,
    )
    pendientes_aux["nro_norm"] = pendientes_aux["nro_solicitud"].apply(lambda v: str(v or "").strip())
    relacionados = pendientes_aux[
        (pendientes_aux["fecha_norm"] == fecha_base)
        & (pendientes_aux["doc_norm"] == doc_base)
        & (pendientes_aux["nro_norm"] == nro_base)
    ]
    indices_relacionados = [int(i) for i in relacionados.index.tolist()]
    if int(indice_primer_pendiente) not in indices_relacionados:
        indices_relacionados.append(int(indice_primer_pendiente))
    indices_relacionados = sorted(set(indices_relacionados))

    siguiente_mismo_doc_y_fecha = False
    siguiente_idx = indice_primer_pendiente + 1
    if siguiente_idx in df.index:
        fila_sig = df.loc[siguiente_idx]
        estado_sig = str(fila_sig.get("estado", "")).strip().upper()
        doc_sig = str(fila_sig.get("doc_vigilante", "") or fila_sig.get("dni", "")).strip()
        nro_sig = str(fila_sig.get("nro_solicitud", "")).strip()
        fecha_sig = fecha_comparable(fila_sig.get(fecha_col_programacion, fila_sig.get("fecha", "")))
        if estado_sig == "PENDIENTE" and doc_sig == doc_base and nro_sig == nro_base and fecha_sig == fecha_base:
            siguiente_mismo_doc_y_fecha = True

    tipos_arma_excel = []
    armas_excel = []
    objetivos_arma = []
    armas_especificas = {"PISTOLA", "REVOLVER", "CARABINA", "ESCOPETA"}

    for _, fila in relacionados.iterrows():
        tipo_raw = str(fila.get("tipo_arma", "")).strip()
        arma_raw = str(fila.get("arma", "")).strip()
        tipo_inferido = inferir_objetivo_arma_desde_excel(tipo_raw)
        arma_inferida = inferir_objetivo_arma_desde_excel(arma_raw)

        if not arma_inferida:
            arma_inferida = inferir_objetivo_arma_desde_excel(tipo_raw)

        tipo_norm_texto = normalizar_texto_comparable(tipo_raw)
        if arma_inferida in {"PISTOLA", "REVOLVER"}:
            tipo_fila = "CORTA"
        elif arma_inferida in {"CARABINA", "ESCOPETA"}:
            tipo_fila = "LARGA"
        elif "CORT" in tipo_norm_texto or tipo_inferido == "CORTA":
            tipo_fila = "CORTA"
        elif "LARG" in tipo_norm_texto or tipo_inferido == "LARGA":
            tipo_fila = "LARGA"
        else:
            continue

        arma_objetivo = arma_inferida if arma_inferida in armas_especificas else ("PISTOLA" if tipo_fila == "CORTA" else "CARABINA")

        if tipo_fila not in tipos_arma_excel:
            tipos_arma_excel.append(tipo_fila)
        if arma_objetivo not in armas_excel:
            armas_excel.append(arma_objetivo)

        par_objetivo = (tipo_fila, arma_objetivo)
        if par_objetivo not in objetivos_arma:
            objetivos_arma.append(par_objetivo)

    if not objetivos_arma:
        if arma_base in {"PISTOLA", "REVOLVER"}:
            tipo_base = "CORTA"
            arma_objetivo = arma_base
        elif arma_base in {"CARABINA", "ESCOPETA"}:
            tipo_base = "LARGA"
            arma_objetivo = arma_base
        elif tipo_arma_base == "LARGA":
            tipo_base = "LARGA"
            arma_objetivo = "CARABINA"
        else:
            tipo_base = "CORTA"
            arma_objetivo = "PISTOLA"

        objetivos_arma = [(tipo_base, arma_objetivo)]
        tipos_arma_excel = [tipo_base]
        armas_excel = [arma_objetivo]

    tipos_arma_objetivo = [t for t, _ in objetivos_arma]

    registro["fecha"] = fecha
    registro["hora_rango"] = hora_rango
    registro["doc_vigilante"] = doc_vigilante
    registro["fecha_programacion"] = fecha_programacion_valor
    registro["ruc"] = registro.get("ruc", "")
    registro["prioridad"] = registro.get("prioridad", "")
    registro["objetivos_arma"] = objetivos_arma
    registro["tipos_arma_objetivo"] = tipos_arma_objetivo
    registro["armas_objetivo"] = armas_excel
    registro["_excel_indices_relacionados"] = indices_relacionados

    print(" Registro tomado desde Excel:")
    print(f"   - id_registro: {registro.get('id_registro', '')}")
    print(f"   - sede: {sede}")
    print(f"   - fecha: {fecha}")
    print(f"   - hora_rango: {hora_rango}")
    print(f"   - tipo_operacion: {tipo_operacion}")
    print(f"   - doc_vigilante: {doc_vigilante}")
    print(f"   - nro_solicitud: {nro_solicitud}")
    print(f"   - fecha_programacion: {fecha_programacion_valor}")
    print(f"   - ruc: {registro.get('ruc', '')}")
    print(f"   - prioridad: {registro.get('prioridad', '')}")
    print(f"   - siguiente_mismo_doc_y_fecha: {siguiente_mismo_doc_y_fecha}")
    print(f"   - indices_relacionados_excel: {indices_relacionados}")
    print(f"   - tipo_arma (excel): {tipos_arma_excel}")
    print(f"   - arma (excel): {armas_excel}")
    print(f"   - objetivos_arma: {objetivos_arma}")
    print(f"   - tipos_arma_objetivo: {tipos_arma_objetivo}")
    return registro


def registrar_sin_cupo_en_excel(ruta_excel: str, registro: dict, observacion: str):
    if pd is None or not ruta_excel or not os.path.exists(ruta_excel):
        return

    try:
        df = pd.read_excel(ruta_excel, dtype=str)
        df.columns = [str(c).strip() for c in df.columns]

        col_obs = "observaciones" if "observaciones" in df.columns else ("observacion" if "observacion" in df.columns else "observaciones")
        if col_obs not in df.columns:
            df[col_obs] = ""

        idx = registro.get("_excel_index", None)
        indices_rel = obtener_indices_relacionados_registro(registro)
        actualizado = False
        total_actualizados = 0

        indices_validos = [i for i in indices_rel if i in df.index]
        if indices_validos:
            df.loc[indices_validos, col_obs] = observacion
            actualizado = True
            total_actualizados = len(indices_validos)
        else:
            sede = str(registro.get("sede", "")).strip()
            fecha = str(registro.get("fecha", "")).strip()
            hora = str(registro.get("hora_rango", "")).strip()
            nro = str(registro.get("nro_solicitud", "")).strip()

            mask = (
                (_col_norm(df, "sede") == sede)
                & (_col_norm(df, "fecha") == fecha)
                & (_col_norm(df, "hora_rango") == hora)
                & (_col_norm(df, "nro_solicitud") == nro)
            )
            idx_candidatos = df[mask].index.tolist()
            if idx_candidatos:
                df.loc[idx_candidatos, col_obs] = observacion
                actualizado = True
                total_actualizados = len(idx_candidatos)

        if actualizado:
            df.to_excel(ruta_excel, index=False)
            print(f"   [INFO] Excel actualizado: {col_obs}='{observacion}' en {total_actualizados} fila(s)")
        else:
            print(
                "   [WARNING] No se pudo ubicar el registro en Excel para actualizar observacion. "
                f"_excel_index={idx}, indices_rel={indices_rel}"
            )
    except Exception as e:
        print(f"   [WARNING] No se pudo actualizar Excel con observacion de sin cupo: {e}")


def registrar_cita_programada_en_excel(ruta_excel: str, registro: dict):
    if pd is None or not ruta_excel or not os.path.exists(ruta_excel):
        return

    try:
        df = pd.read_excel(ruta_excel, dtype=str)
        df.columns = [str(c).strip() for c in df.columns]

        if "estado" not in df.columns:
            print("   [WARNING] Columna 'estado' no encontrada en Excel")
            return

        idx = registro.get("_excel_index", None)
        indices_rel = obtener_indices_relacionados_registro(registro)
        actualizado = False
        total_actualizados = 0

        indices_validos = [i for i in indices_rel if i in df.index]
        if indices_validos:
            df.loc[indices_validos, "estado"] = "Cita Programada"
            actualizado = True
            total_actualizados = len(indices_validos)
        else:
            sede = str(registro.get("sede", "")).strip()
            fecha = str(registro.get("fecha", "")).strip()
            hora = str(registro.get("hora_rango", "")).strip()
            nro = str(registro.get("nro_solicitud", "")).strip()

            mask = (
                (_col_norm(df, "sede") == sede)
                & (_col_norm(df, "fecha") == fecha)
                & (_col_norm(df, "hora_rango") == hora)
                & (_col_norm(df, "nro_solicitud") == nro)
            )
            idx_candidatos = df[mask].index.tolist()
            if idx_candidatos:
                df.loc[idx_candidatos, "estado"] = "Cita Programada"
                actualizado = True
                total_actualizados = len(idx_candidatos)

        if actualizado:
            df.to_excel(ruta_excel, index=False)
            print(f"   [INFO] Excel actualizado: estado='Cita Programada' en {total_actualizados} fila(s)")
        else:
            print(
                "   [WARNING] No se pudo ubicar el registro en Excel para actualizar estado. "
                f"_excel_index={idx}, indices_rel={indices_rel}"
            )
    except Exception as e:
        print(f"   [WARNING] No se pudo actualizar Excel con estado 'Cita Programada': {e}")
