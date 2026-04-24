from __future__ import annotations

import io
import logging
import os
import shutil
import sys
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


MAX_RUN_ARTIFACT_DIRS = 10


class StreamToLogger(io.TextIOBase):
    def __init__(self, logger: logging.Logger, level: int):
        self.logger = logger
        self.level = level
        self._buffer = ""
        self._lock = threading.RLock()
        self._in_write = False

    def write(self, message: str) -> int:
        if not message:
            return 0
        with self._lock:
            if self._in_write:
                try:
                    sys.__stderr__.write(message)
                    sys.__stderr__.flush()
                except Exception:
                    pass
                return len(message)

            self._in_write = True
            try:
                self._buffer += message
                while "\n" in self._buffer:
                    line, self._buffer = self._buffer.split("\n", 1)
                    line = line.rstrip()
                    if line:
                        self.logger.log(self.level, line)
            except Exception:
                try:
                    sys.__stderr__.write(message)
                    sys.__stderr__.flush()
                except Exception:
                    pass
            finally:
                self._in_write = False
        return len(message)

    def flush(self) -> None:
        with self._lock:
            if not self._buffer.strip():
                self._buffer = ""
                return
            try:
                self.logger.log(self.level, self._buffer.strip())
            except Exception:
                try:
                    sys.__stderr__.write(self._buffer.strip() + "\n")
                    sys.__stderr__.flush()
                except Exception:
                    pass
            finally:
                self._buffer = ""


class SafeStreamHandler(logging.StreamHandler):
    """Console handler tolerant to cp1252/TTY encoding issues."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            super().emit(record)
        except UnicodeEncodeError:
            try:
                msg = self.format(record)
                safe = msg.encode("ascii", errors="replace").decode("ascii")
                self.stream.write(safe + self.terminator)
                self.flush()
            except Exception:
                pass
        except Exception:
            pass


def _run_stamp() -> str:
    stamp = os.getenv("LOG_RUN_STAMP", "").strip()
    if stamp:
        return stamp
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _is_run_dir_name(path: Path) -> bool:
    name = path.name
    if len(name) != 15 or name[8] != "_":
        return False
    return name[:8].isdigit() and name[9:].isdigit()


def _cleanup_old_run_dirs(base_dir: Path, current_run_dir: Path) -> None:
    try:
        run_dirs = [
            p
            for p in base_dir.iterdir()
            if p.is_dir() and _is_run_dir_name(p)
        ]
        run_dirs.sort(key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
        protected = current_run_dir.resolve()
        removable = [p for p in run_dirs if p.resolve() != protected]
        keep_slots = max(0, MAX_RUN_ARTIFACT_DIRS - 1)
        for old_dir in removable[keep_slots:]:
            shutil.rmtree(old_dir, ignore_errors=True)
    except Exception:
        pass


def prepare_run_artifact_dir(base_dir: Path, run_dir_env: str, is_run_dir_env: str) -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    stamp = _run_stamp()
    if os.getenv(is_run_dir_env, "").strip() == "1":
        run_dir = base_dir
    else:
        run_dir = base_dir / stamp
        run_dir.mkdir(parents=True, exist_ok=True)
        os.environ[run_dir_env] = str(run_dir)
        _cleanup_old_run_dirs(base_dir, run_dir)

    run_dir.mkdir(parents=True, exist_ok=True)
    os.environ["LOG_RUN_STAMP"] = stamp
    return run_dir


def _prepare_log_path(log_dir: Path) -> Path:
    stamp = _run_stamp()
    run_dir = prepare_run_artifact_dir(log_dir, "LOG_RUN_DIR", "LOG_DIR_IS_RUN_DIR")
    return run_dir / f"run_{stamp}.log"


def build_logger(log_dir: Path) -> tuple[logging.Logger, Path]:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = _prepare_log_path(log_dir)
    logger = logging.getLogger(f"armas_gadso.{log_path.stem}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logging.raiseExceptions = False

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = SafeStreamHandler(sys.__stdout__)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    logger.propagate = False
    return logger, log_path


@contextmanager
def redirect_prints(logger: logging.Logger):
    old_stdout, old_stderr = sys.stdout, sys.stderr
    stdout_proxy = StreamToLogger(logger, logging.INFO)
    stderr_proxy = StreamToLogger(logger, logging.ERROR)
    sys.stdout = stdout_proxy
    sys.stderr = stderr_proxy
    try:
        yield
    finally:
        stdout_proxy.flush()
        stderr_proxy.flush()
        sys.stdout = old_stdout
        sys.stderr = old_stderr
