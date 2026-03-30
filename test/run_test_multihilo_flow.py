from __future__ import annotations

import os
import sys
import time
import queue
import shutil
import traceback
import subprocess
import threading
import importlib
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor



def _bootstrap_project_path() -> Path:
    """Ajusta sys.path para poder importar 'armas_gadso' desde carpeta test/."""
    this_file = Path(__file__).resolve()
    for root in this_file.parents:
        if (root / "armas_gadso").is_dir() and (root / "run_pipeline.py").is_file():
            root_str = str(root)
            if root_str not in sys.path:
                sys.path.insert(0, root_str)
            return root
    raise RuntimeError("No se encontro la raiz del proyecto (carpeta con armas_gadso y run_pipeline.py).")


ROOT_DIR = _bootstrap_project_path()



def _safe_int(env_name: str, default: int) -> int:
    try:
        return int(str(os.getenv(env_name, str(default)) or default).strip())
    except Exception:
        return default



def _as_bool(env_name: str, default: bool = False) -> bool:
    raw = str(os.getenv(env_name, "1" if default else "0") or ("1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "si", "si", "on"}


def _detect_windows_screen_size(default_w: int = 1920, default_h: int = 1080) -> tuple[int, int]:
    """Retorna resolución efectiva (espacio lógico) que Windows entrega a apps no DPI-aware."""
    try:
        import ctypes

        user32 = ctypes.windll.user32
        w = int(user32.GetSystemMetrics(0))  # SM_CXSCREEN
        h = int(user32.GetSystemMetrics(1))  # SM_CYSCREEN
        if w >= 800 and h >= 600:
            return w, h
    except Exception:
        pass
    return default_w, default_h



def run_multihilo_flow_test() -> int:
    """
    Runner E2E de prueba para multihilo sobre flujo real, sin modificar el flujo base.

    Estrategia:
    - Coordinador crea unidades de trabajo desde el Excel origen (1 unidad por idx pendiente deduplicado).
    - Workers (hilos) consumen cola compartida y ejecutan el flujo real en procesos aislados.
    - Cada proceso usa un Excel temporal con solo su unidad en estado PENDIENTE para evitar superposicion.

    Notas:
    - Se abren ventanas reales de navegador (una por proceso worker activo).
    - No escribe sobre el Excel original.
    """
    config_mod = importlib.import_module("armas_gadso.config")
    logging_mod = importlib.import_module("armas_gadso.logging_utils")
    legacy_flow = importlib.import_module("armas_gadso.legacy_flow")

    load_config = config_mod.load_config
    build_logger = logging_mod.build_logger
    redirect_prints = logging_mod.redirect_prints

    cfg = load_config()
    screen_w_eff, screen_h_eff = _detect_windows_screen_size()
    workers = max(1, min(4, _safe_int("TEST_WORKERS", 4)))
    max_units = _safe_int("TEST_MAX_UNITS", 0)  # 0 = todos
    keep_temp = _as_bool("TEST_KEEP_TEMP", default=True)
    worker_mode = str(os.getenv("TEST_WORKER_MODE", "sticky") or "sticky").strip().lower()
    if worker_mode not in {"dynamic", "sticky"}:
        worker_mode = "sticky"

    logger, log_path = build_logger(cfg.log_dir)
    logger.info("Iniciando prueba E2E multihilo (flujo real)")
    logger.info("Excel origen: %s", str(cfg.excel_path))
    logger.info("Workers: %s", workers)
    logger.info("TEST_WORKER_MODE: %s", worker_mode)
    logger.info("TEST_MAX_UNITS: %s", max_units)
    if worker_mode == "dynamic":
        logger.warning(
            "Modo dynamic activo: cada unidad corre en un proceso separado, por lo que habra nuevo login por unidad. "
            "Usa TEST_WORKER_MODE=sticky para mantener una sola sesion por worker y avanzar al siguiente registro."
        )

    try:
        with redirect_prints(logger):
            trabajos = legacy_flow.obtener_trabajos_pendientes_excel(str(cfg.excel_path))

        if not trabajos:
            logger.info("No hay trabajos pendientes en el Excel origen.")
            logger.info("Log disponible en: %s", log_path)
            return 0

        # Construye unidades de trabajo usando indices relacionados reales del flujo.
        unidades = []
        vistos_primarios = set()
        for t in trabajos:
            idx = int(t["idx_excel"])
            if idx in vistos_primarios:
                continue

            reg = legacy_flow.cargar_primer_registro_pendiente_desde_excel(str(cfg.excel_path), indice_excel_objetivo=idx)
            rel = sorted(set(int(x) for x in (reg.get("_excel_indices_relacionados", []) or [idx])))
            unidades.append(
                {
                    "idx_principal": idx,
                    "indices_relacionados": rel,
                    "ruc_grupo": str(t.get("ruc_grupo", "OTRO")),
                    "prioridad": str(t.get("prioridad", "Normal")),
                }
            )
            vistos_primarios.add(idx)

        if max_units > 0:
            unidades = unidades[:max_units]

        if not unidades:
            logger.info("No se pudieron construir unidades para prueba.")
            logger.info("Log disponible en: %s", log_path)
            return 1

        logger.info("Unidades a procesar: %s", len(unidades))

        # Prepara carpeta temporal de prueba.
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_root = ROOT_DIR / "test" / f".tmp_multihilo_flow_{stamp}"
        temp_root.mkdir(parents=True, exist_ok=True)

        lock_results = threading.Lock()
        results = []

        python_exe = sys.executable
        base_cmd = [python_exe, str(ROOT_DIR / "run_pipeline.py"), "--mode", "scheduled"]

        def _make_worker_excel(worker_id: int, target_indices: set[int], tag: str) -> Path:
            """Copia Excel origen y deja solo indices target como PENDIENTE."""
            import pandas as pd

            safe_tag = str(tag).replace(" ", "_")
            dst = temp_root / f"worker_{worker_id}_{safe_tag}.xlsx"
            shutil.copy2(cfg.excel_path, dst)

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
                    # Evita que el proceso tome registros fuera de su unidad.
                    df.at[i, "estado"] = "NO_EJECUTAR_TEST"

            df.to_excel(dst, index=False)
            return dst

        def _build_worker_env(worker_id: int, excel_worker: Path, worker_log_dir: Path, mode: str = "sticky") -> dict:
            env = os.environ.copy()
            env["EXCEL_PATH"] = str(excel_worker)
            env["RUN_MODE"] = "scheduled"
            env["HOLD_BROWSER_OPEN"] = "0"
            env["LOG_DIR"] = str(worker_log_dir)
            env["BROWSER_TILE_ENABLE"] = "1"
            env["BROWSER_TILE_TOTAL"] = str(workers)
            env["BROWSER_TILE_INDEX"] = str(worker_id - 1)

            # Forzar validaciones de rango/reesignación horaria en pruebas multihilo.
            env["ADAPTIVE_HOUR_SELECTION"] = "1"
            env["ADAPTIVE_HOUR_NOON_FULL_BLOCK"] = "1"
            env["NRO_SOLICITUD_CONFIRM_ATTEMPTS"] = str(
                _safe_int("NRO_SOLICITUD_CONFIRM_ATTEMPTS", 2)
            )
            
            # En sticky mode: activar PERSISTENT_SESSION para evitar cerrar navegador entre grupos
            if mode == "sticky":
                env["PERSISTENT_SESSION"] = "1"

            # Usar resolución efectiva de Windows (DPI/escala) para evitar solape entre ventanas.
            env["BROWSER_TILE_SCREEN_W"] = str(_safe_int("BROWSER_TILE_SCREEN_W", screen_w_eff))
            env["BROWSER_TILE_SCREEN_H"] = str(_safe_int("BROWSER_TILE_SCREEN_H", screen_h_eff))
            env["BROWSER_TILE_TOP_OFFSET"] = str(_safe_int("BROWSER_TILE_TOP_OFFSET", 0))
            env["BROWSER_TILE_GAP"] = str(_safe_int("BROWSER_TILE_GAP", 6))
            env["BROWSER_TILE_FRAME_PAD"] = str(_safe_int("BROWSER_TILE_FRAME_PAD", 2))
            return env

        def _run_unit(worker_id: int, idx_label: str, excel_worker: Path, mode: str = "sticky") -> int:
            started = time.time()
            worker_log_dir = temp_root / f"logs_w{worker_id}"
            worker_log_dir.mkdir(parents=True, exist_ok=True)
            env = _build_worker_env(worker_id, excel_worker, worker_log_dir, mode)

            proc = subprocess.run(
                base_cmd,
                cwd=str(ROOT_DIR),
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
                logger.info("[W%s] %s finalizo OK en %.2fs", worker_id, idx_label, elapsed)
            else:
                logger.error("[W%s] %s finalizo con codigo=%s en %.2fs", worker_id, idx_label, proc.returncode, elapsed)
            return int(proc.returncode)

        def worker_loop(worker_id: int) -> int:
            q: queue.Queue[dict] = worker_queues[worker_id]
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
                    excel_worker = _make_worker_excel(
                        worker_id,
                        set(int(x) for x in unit["indices_relacionados"]),
                        f"unit_{seq}_idx_{idx}",
                    )

                    logger.info(
                        "[W%s] Iniciando unidad idx=%s rel=%s",
                        worker_id,
                        idx,
                        unit["indices_relacionados"],
                    )
                    _run_unit(worker_id, f"Unidad idx={idx}", excel_worker, worker_mode)

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
                    logger.error("[W%s] Excepcion en unidad idx=%s: %s", worker_id, idx, e)
                finally:
                    q.task_done()
                    local_done += 1

            return local_done

        def worker_sticky(worker_id: int, assigned_units: list[dict]) -> int:
            if not assigned_units:
                return 0

            assigned_idx = [int(u["idx_principal"]) for u in assigned_units]
            target_indices = set()
            for u in assigned_units:
                target_indices.update(int(x) for x in u["indices_relacionados"])

            logger.info("[W%s] Lote asignado idx=%s", worker_id, assigned_idx)
            try:
                excel_worker = _make_worker_excel(
                    worker_id,
                    target_indices,
                    f"batch_{len(assigned_units)}_idxs_{'_'.join(str(x) for x in assigned_idx)}",
                )
                _run_unit(worker_id, f"Lote idx={assigned_idx}", excel_worker, worker_mode)
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
                logger.error("[W%s] Excepcion en lote idx=%s: %s", worker_id, assigned_idx, e)

            return len(assigned_units)

        test_started = time.time()
        with ThreadPoolExecutor(max_workers=workers) as ex:
            if worker_mode == "sticky":
                # Reparte de forma estable por round-robin, 1 proceso por worker.
                assigned_by_worker = {wid: [] for wid in range(1, workers + 1)}
                for pos, unit in enumerate(unidades):
                    wid = (pos % workers) + 1
                    assigned_by_worker[wid].append(unit)
                futures = [
                    ex.submit(worker_sticky, wid, assigned_by_worker[wid])
                    for wid in range(1, workers + 1)
                ]
                counts = [f.result() for f in futures]
            else:
                # Cola dinamica: el worker libre toma la siguiente unidad.
                worker_queues = {wid: queue.Queue() for wid in range(1, workers + 1)}
                for i, unit in enumerate(unidades):
                    worker_queues[(i % workers) + 1].put(unit)

                # Una cola global real para modo dinamico.
                global_queue: queue.Queue[dict] = queue.Queue()
                for unit in unidades:
                    global_queue.put(unit)
                worker_queues = {wid: global_queue for wid in range(1, workers + 1)}

                futures = [ex.submit(worker_loop, wid) for wid in range(1, workers + 1)]
                counts = [f.result() for f in futures]
        total_elapsed = time.time() - test_started
        total_unidades_procesadas = sum(int(x) for x in counts)

        logger.info("Conteo por worker: %s", counts)
        logger.info("Unidades procesadas: %s/%s", total_unidades_procesadas, len(unidades))
        logger.info("Tiempo total prueba E2E: %.2fs", total_elapsed)

        failed = [r for r in results if int(r.get("exit_code", 1)) != 0]
        if failed:
            logger.error("Unidades con fallo: %s", len(failed))
            for r in failed:
                logger.error(
                    "[W%s] idx=%s exit=%s stderr_tail=%s",
                    r["worker"],
                    r["idx_principal"],
                    r["exit_code"],
                    r["stderr_tail"],
                )
            logger.info("Log disponible en: %s", log_path)
            logger.info("Temp dir: %s", temp_root)
            return 1

        logger.info("[OK] Prueba E2E multihilo finalizada sin fallos de proceso.")
        logger.info("Log disponible en: %s", log_path)
        logger.info("Temp dir: %s", temp_root)

        if not keep_temp:
            shutil.rmtree(temp_root, ignore_errors=True)
            logger.info("TEST_KEEP_TEMP=0 -> temporales eliminados")

        return 0

    except Exception as exc:
        logger.error("Prueba E2E multihilo finalizada con error: %s", exc)
        logger.error(traceback.format_exc())
        logger.info("Log disponible en: %s", log_path)
        return 1


if __name__ == "__main__":
    raise SystemExit(run_multihilo_flow_test())
