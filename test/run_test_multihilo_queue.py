from __future__ import annotations

import os
import sys
import time
import traceback
import importlib
from queue import Empty, Queue
from pathlib import Path
from threading import Lock
from concurrent.futures import ThreadPoolExecutor


def _bootstrap_project_path() -> None:
    """Ajusta sys.path para poder importar 'armas_gadso' desde carpeta test/."""
    this_file = Path(__file__).resolve()
    for root in this_file.parents:
        if (root / "armas_gadso").is_dir() and (root / "run_pipeline.py").is_file():
            root_str = str(root)
            if root_str not in sys.path:
                sys.path.insert(0, root_str)
            return
    raise RuntimeError("No se encontro la raiz del proyecto (carpeta con armas_gadso y run_pipeline.py).")


_bootstrap_project_path()


def run_multihilo_queue_test() -> int:
    """
    Prueba aislada de coordinacion multihilo sobre una sola fuente Excel.

    Objetivo:
    - Simular workers (2-3) tomando registros pendientes desde una cola compartida.
    - Validar que no haya superposicion de idx_excel entre workers.
    - Validar que un worker, al terminar un item, toma el siguiente en cola.

    Esta prueba NO lanza navegador ni escribe en Excel de produccion.
    """
    config_mod = importlib.import_module("armas_gadso.config")
    logging_mod = importlib.import_module("armas_gadso.logging_utils")
    legacy_flow = importlib.import_module("armas_gadso.legacy_flow")

    load_config = config_mod.load_config
    build_logger = logging_mod.build_logger
    redirect_prints = logging_mod.redirect_prints

    config = load_config()

    workers = int(str(os.getenv("TEST_WORKERS", "2") or "2").strip())
    workers = max(1, min(3, workers))

    simulated_work_ms = int(str(os.getenv("TEST_SIMULATED_WORK_MS", "180") or "180").strip())
    simulated_work_ms = max(0, simulated_work_ms)

    logger, log_path = build_logger(config.log_dir)
    logger.info("Iniciando prueba de cola multihilo")
    logger.info("Excel: %s", str(config.excel_path))
    logger.info("Workers: %s", workers)
    logger.info("Simulacion trabajo por item: %sms", simulated_work_ms)

    try:
        with redirect_prints(logger):
            trabajos = legacy_flow.obtener_trabajos_pendientes_excel(str(config.excel_path))

        if not trabajos:
            logger.info("No hay trabajos pendientes para probar coordinacion multihilo.")
            logger.info("Log disponible en: %s", log_path)
            return 0

        expected_idxs = [int(t["idx_excel"]) for t in trabajos]

        queue: Queue[dict] = Queue()
        for t in trabajos:
            queue.put(dict(t))

        assigned_once = set()
        assigned_lock = Lock()
        claimed_collisions: list[tuple[int, int]] = []
        processed_records: list[dict] = []
        processed_lock = Lock()

        def worker_loop(worker_id: int) -> int:
            local_count = 0
            while True:
                try:
                    task = queue.get_nowait()
                except Empty:
                    break

                idx = int(task["idx_excel"])
                with assigned_lock:
                    if idx in assigned_once:
                        claimed_collisions.append((worker_id, idx))
                    else:
                        assigned_once.add(idx)

                if simulated_work_ms > 0:
                    # Simula el tiempo que un worker dedica a un registro antes de pedir el siguiente.
                    time.sleep(simulated_work_ms / 1000.0)

                with processed_lock:
                    processed_records.append(
                        {
                            "worker": worker_id,
                            "idx_excel": idx,
                            "ruc_grupo": str(task.get("ruc_grupo", "")),
                            "prioridad": str(task.get("prioridad", "")),
                        }
                    )

                local_count += 1
                queue.task_done()

            return local_count

        started = time.time()
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(worker_loop, wid) for wid in range(1, workers + 1)]
            counts = [f.result() for f in futures]
        elapsed = time.time() - started

        from collections import Counter

        counter = Counter(int(r["idx_excel"]) for r in processed_records)
        duplicated_idxs = sorted(idx for idx, c in counter.items() if c > 1)
        missing_idxs = sorted(set(expected_idxs) - set(counter.keys()))

        logger.info("Resultado workers por hilo: %s", counts)
        logger.info("Total esperado: %s | Total procesado: %s", len(expected_idxs), len(processed_records))
        logger.info("Tiempo prueba cola: %.2fs", elapsed)

        if claimed_collisions:
            logger.error("Se detectaron colisiones de claim atomico: %s", claimed_collisions)
        if duplicated_idxs:
            logger.error("Se detectaron idx procesados mas de una vez: %s", duplicated_idxs)
        if missing_idxs:
            logger.error("Se detectaron idx no procesados: %s", missing_idxs)

        if not claimed_collisions and not duplicated_idxs and not missing_idxs:
            logger.info("[OK] Cola multihilo valida: sin superposicion y con consumo completo.")
            logger.info("Log disponible en: %s", log_path)
            return 0

        logger.error("[FAIL] La coordinacion multihilo requiere ajustes.")
        logger.info("Log disponible en: %s", log_path)
        return 1

    except Exception as exc:
        logger.error("Prueba multihilo finalizada con error: %s", exc)
        logger.error(traceback.format_exc())
        logger.info("Log disponible en: %s", log_path)
        return 1


if __name__ == "__main__":
    raise SystemExit(run_multihilo_queue_test())
