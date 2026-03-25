from __future__ import annotations

import io
import logging
import sys
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


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
                # Evita bucles recursivos cuando el propio logging falla.
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
    """Handler tolerante a codificación de consola (cp1252/TTY)."""

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
            # No propagar fallos del stream de consola.
            pass


def build_logger(log_dir: Path) -> tuple[logging.Logger, Path]:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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
