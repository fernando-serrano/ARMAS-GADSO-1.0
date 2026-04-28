from __future__ import annotations

import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

try:
    import pandas as pd
except ImportError:
    pd = None

from ...excel import (
    cargar_primer_registro_pendiente_desde_excel,
    obtener_trabajos_pendientes_excel,
)
from ..notifications import send_multirun_step_1_summary


def _safe_int_env(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, str(default)) or default).strip())
    except Exception:
        return default


def _as_bool_env(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "1" if default else "0") or ("1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "si", "sí", "on"}


def _detect_windows_screen_size(default_w: int = 1920, default_h: int = 1080):
    """Retorna resolucion efectiva (espacio logico) en Windows."""
    try:
        import ctypes

        user32 = ctypes.windll.user32
        w = int(user32.GetSystemMetrics(0))
        h = int(user32.GetSystemMetrics(1))
        if w >= 800 and h >= 600:
            return w, h
    except Exception:
        pass
    return default_w, default_h


def multihilo_scheduled_habilitado() -> bool:
    run_mode = os.getenv("RUN_MODE", "manual").strip().lower()
    if run_mode != "scheduled":
        return False
    if _as_bool_env("MULTIWORKER_CHILD", default=False):
        return False
    if _as_bool_env("PERSISTENT_SESSION", default=False):
        return False
    return _as_bool_env("SCHEDULED_MULTIWORKER", default=True)


def ejecutar_scheduled_multihilo_orquestador(excel_path: str, project_root: str) -> None:
    """
    Orquesta el modo scheduled multihilo ejecutando el flujo existente en procesos aislados.
    No altera la logica de negocio del flujo por registro: cada worker invoca run_pipeline.py.
    """
    if pd is None:
        raise Exception("pandas no esta disponible para preparar lotes multihilo")

    workers = max(1, min(4, _safe_int_env("SCHEDULED_WORKERS", 4)))
    max_units = _safe_int_env("SCHEDULED_MAX_UNITS", 0)
    worker_mode = str(os.getenv("SCHEDULED_WORKER_MODE", "sticky") or "sticky").strip().lower()
    if worker_mode not in {"dynamic", "sticky"}:
        worker_mode = "sticky"

    screen_w_eff, screen_h_eff = _detect_windows_screen_size()
    origen_excel = excel_path
    if not os.path.exists(origen_excel):
        raise Exception(f"Excel no encontrado para multihilo: {origen_excel}")

    print(f"[INFO] SCHEDULED_MULTIWORKER activado | workers={workers} | mode={worker_mode}")
    print(f"[INFO] Excel origen multihilo: {origen_excel}")

    trabajos = obtener_trabajos_pendientes_excel(origen_excel)
    if not trabajos:
        print("[INFO] No hay trabajos pendientes para multihilo.")
        return

    unidades = []
    vistos_primarios = set()
    for trabajo in trabajos:
        idx = int(trabajo["idx_excel"])
        if idx in vistos_primarios:
            continue
        reg = cargar_primer_registro_pendiente_desde_excel(origen_excel, indice_excel_objetivo=idx)
        rel = sorted(set(int(x) for x in (reg.get("_excel_indices_relacionados", []) or [idx])))
        unidades.append(
            {
                "idx_principal": idx,
                "indices_relacionados": rel,
            }
        )
        vistos_primarios.add(idx)

    if max_units > 0:
        unidades = unidades[:max_units]

    if not unidades:
        print("[INFO] No se construyeron unidades multihilo.")
        return

    print(f"[INFO] Unidades multihilo a procesar: {len(unidades)}")

    stamp = os.getenv("LOG_RUN_STAMP", "").strip() or datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_root = os.getenv("LOG_RUN_DIR", "").strip() or os.path.join(project_root, "logs", stamp)
    os.makedirs(temp_root, exist_ok=True)

    lock_results = threading.Lock()
    results = []
    manifest_paths: list[str] = []
    base_cmd = [sys.executable, os.path.join(project_root, "run_pipeline.py"), "--mode", "scheduled"]

    def make_worker_excel(worker_id: int, target_indices: set, tag: str) -> str:
        safe_tag = str(tag).replace(" ", "_")
        dst = os.path.join(temp_root, f"worker_{worker_id}_{safe_tag}.xlsx")
        shutil.copy2(origen_excel, dst)

        df = pd.read_excel(dst, dtype=str)
        df.columns = [str(c).strip() for c in df.columns]
        if "estado" not in df.columns:
            df["estado"] = ""
        for col in df.columns:
            df[col] = df[col].fillna("").astype(str)

        for i in df.index:
            if int(i) in target_indices:
                df.at[i, "estado"] = "PENDIENTE"
            else:
                df.at[i, "estado"] = "NO_EJECUTAR_TEST"

        df.to_excel(dst, index=False)
        return dst

    def build_worker_env(worker_id: int, excel_worker: str, mode: str = "sticky") -> dict:
        env = os.environ.copy()
        env["EXCEL_PATH"] = excel_worker
        env["RUN_MODE"] = "scheduled"
        env["HOLD_BROWSER_OPEN"] = "0"
        env["MULTIWORKER_CHILD"] = "1"

        env["LOG_DIR"] = os.path.join(temp_root, f"logs_w{worker_id}")
        env["LOG_DIR_IS_RUN_DIR"] = "1"
        env["LOG_RUN_STAMP"] = stamp
        screenshot_root = os.getenv("SCREENSHOT_RUN_DIR", "").strip() or os.path.join(project_root, "screenshots", stamp)
        env["SCREENSHOT_DIR"] = os.path.join(screenshot_root, f"screenshots_w{worker_id}")
        env["SCREENSHOT_DIR_IS_RUN_DIR"] = "1"
        env["GRAPH_STEP1_MANIFEST_PATH"] = os.path.join(temp_root, f"graph_step1_worker_{worker_id}.jsonl")
        env["BROWSER_TILE_ENABLE"] = "1" if _as_bool_env("BROWSER_TILE_ENABLE", default=True) else "0"
        env["BROWSER_TILE_TOTAL"] = str(workers)
        env["BROWSER_TILE_INDEX"] = str(worker_id - 1)
        env["BROWSER_TILE_COLS"] = str(_safe_int_env("BROWSER_TILE_COLS", 0))
        env["BROWSER_TILE_ROWS"] = str(_safe_int_env("BROWSER_TILE_ROWS", 0))
        env["BROWSER_TILE_SCREEN_W"] = str(_safe_int_env("BROWSER_TILE_SCREEN_W", screen_w_eff))
        env["BROWSER_TILE_SCREEN_H"] = str(_safe_int_env("BROWSER_TILE_SCREEN_H", screen_h_eff))
        env["BROWSER_TILE_TOP_OFFSET"] = str(_safe_int_env("BROWSER_TILE_TOP_OFFSET", 0))
        env["BROWSER_TILE_GAP"] = str(_safe_int_env("BROWSER_TILE_GAP", 6))
        env["BROWSER_TILE_FRAME_PAD"] = str(_safe_int_env("BROWSER_TILE_FRAME_PAD", 2))
        env["ADAPTIVE_HOUR_SELECTION"] = "1"
        env["ADAPTIVE_HOUR_NOON_FULL_BLOCK"] = "1"
        env["NRO_SOLICITUD_CONFIRM_ATTEMPTS"] = str(_safe_int_env("NRO_SOLICITUD_CONFIRM_ATTEMPTS", 2))

        if mode == "sticky":
            env["PERSISTENT_SESSION"] = "1"
        return env

    def run_unit(worker_id: int, idx_label: str, excel_worker: str, mode: str = "sticky") -> int:
        started = time.time()
        env = build_worker_env(worker_id, excel_worker, mode)
        proc = subprocess.run(
            base_cmd,
            cwd=project_root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        elapsed = time.time() - started
        with lock_results:
            results.append(
                {
                    "worker": worker_id,
                    "idx_principal": idx_label,
                    "exit_code": int(proc.returncode),
                    "elapsed_sec": round(elapsed, 2),
                    "stdout_tail": (proc.stdout or "")[-1200:],
                    "stderr_tail": (proc.stderr or "")[-1200:],
                }
            )

        if proc.returncode == 0:
            print(f"[INFO][W{worker_id}] {idx_label} finalizo OK en {elapsed:.2f}s")
        else:
            print(f"[ERROR][W{worker_id}] {idx_label} finalizo con codigo={proc.returncode} en {elapsed:.2f}s")
        return int(proc.returncode)

    worker_queues = {}

    def worker_loop(worker_id: int) -> int:
        q = worker_queues[worker_id]
        local_done = 0
        seq = 0
        while True:
            try:
                unit = q.get_nowait()
            except queue.Empty:
                break

            seq += 1
            idx = int(unit["idx_principal"])
            try:
                excel_worker = make_worker_excel(
                    worker_id,
                    set(int(x) for x in unit["indices_relacionados"]),
                    f"unit_{seq}_idx_{idx}",
                )
                print(f"[INFO][W{worker_id}] Iniciando unidad idx={idx} rel={unit['indices_relacionados']}")
                run_unit(worker_id, f"Unidad idx={idx}", excel_worker, worker_mode)
            except Exception as e:
                with lock_results:
                    results.append(
                        {
                            "worker": worker_id,
                            "idx_principal": idx,
                            "exit_code": -1,
                            "elapsed_sec": 0,
                            "stdout_tail": "",
                            "stderr_tail": f"EXCEPCION_WORKER: {e}\n{traceback.format_exc()}",
                        }
                    )
                print(f"[ERROR][W{worker_id}] Excepcion en unidad idx={idx}: {e}")
            finally:
                q.task_done()
                local_done += 1
        return local_done

    def worker_sticky(worker_id: int, assigned_units: list) -> int:
        if not assigned_units:
            return 0

        assigned_idx = [int(u["idx_principal"]) for u in assigned_units]
        target_indices = set()
        for u in assigned_units:
            target_indices.update(int(x) for x in u["indices_relacionados"])

        print(f"[INFO][W{worker_id}] Lote asignado idx={assigned_idx}")
        try:
            excel_worker = make_worker_excel(
                worker_id,
                target_indices,
                f"batch_{len(assigned_units)}_idxs_{'_'.join(str(x) for x in assigned_idx)}",
            )
            manifest_paths.append(os.path.join(temp_root, f"graph_step1_worker_{worker_id}.jsonl"))
            run_unit(worker_id, f"Lote idx={assigned_idx}", excel_worker, worker_mode)
        except Exception as e:
            with lock_results:
                results.append(
                    {
                        "worker": worker_id,
                        "idx_principal": f"batch:{assigned_idx}",
                        "exit_code": -1,
                        "elapsed_sec": 0,
                        "stdout_tail": "",
                        "stderr_tail": f"EXCEPCION_WORKER_STICKY: {e}\n{traceback.format_exc()}",
                    }
                )
            print(f"[ERROR][W{worker_id}] Excepcion en lote idx={assigned_idx}: {e}")

        return len(assigned_units)

    test_started = time.time()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        if worker_mode == "sticky":
            assigned_by_worker = {wid: [] for wid in range(1, workers + 1)}
            for pos, unit in enumerate(unidades):
                wid = (pos % workers) + 1
                assigned_by_worker[wid].append(unit)
            futures = [
                executor.submit(worker_sticky, wid, assigned_by_worker[wid])
                for wid in range(1, workers + 1)
            ]
            counts = [f.result() for f in futures]
        else:
            global_queue = queue.Queue()
            for unit in unidades:
                global_queue.put(unit)
            worker_queues = {wid: global_queue for wid in range(1, workers + 1)}
            futures = [executor.submit(worker_loop, wid) for wid in range(1, workers + 1)]
            counts = [f.result() for f in futures]

    total_elapsed = time.time() - test_started
    total_unidades_procesadas = sum(int(x) for x in counts)
    print(f"[INFO] Conteo por worker: {counts}")
    print(f"[INFO] Unidades procesadas: {total_unidades_procesadas}/{len(unidades)}")
    print(f"[INFO] Tiempo total multihilo: {total_elapsed:.2f}s")

    failed = [r for r in results if int(r.get("exit_code", 1)) != 0]
    if failed:
        print(f"[ERROR] Unidades con fallo: {len(failed)}")
        for r in failed:
            print(
                f"[ERROR][W{r['worker']}] idx={r['idx_principal']} "
                f"exit={r['exit_code']} stderr_tail={r['stderr_tail']}"
            )
        raise Exception(f"Flujo multihilo finalizo con {len(failed)} fallos")

    send_multirun_step_1_summary(manifest_paths)
    print("[OK] Flujo multihilo scheduled finalizado sin fallos de proceso")
