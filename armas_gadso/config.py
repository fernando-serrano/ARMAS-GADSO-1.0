
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "si", "sí"}


@dataclass(frozen=True)
class AppConfig:
    root_dir: Path
    excel_path: Path
    log_dir: Path
    screenshot_dir: Path
    run_mode: str
    hold_browser_open: bool
    python_executable: str

    @property
    def is_scheduled(self) -> bool:
        return self.run_mode == "scheduled"



def load_config() -> AppConfig:
    excel_raw = os.getenv("EXCEL_PATH", str(ROOT_DIR / "data" / "programaciones-armas.xlsx"))
    excel_path = Path(excel_raw)
    if not excel_path.is_absolute():
        excel_path = ROOT_DIR / excel_path

    log_dir = ROOT_DIR / os.getenv("LOG_DIR", "logs")
    screenshot_dir = ROOT_DIR / os.getenv("SCREENSHOT_DIR", "screenshots")
    log_dir.mkdir(parents=True, exist_ok=True)
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    run_mode = os.getenv("RUN_MODE", "manual").strip().lower()
    if run_mode not in {"manual", "scheduled"}:
        run_mode = "manual"

    return AppConfig(
        root_dir=ROOT_DIR,
        excel_path=excel_path,
        log_dir=log_dir,
        screenshot_dir=screenshot_dir,
        run_mode=run_mode,
        hold_browser_open=_as_bool(os.getenv("HOLD_BROWSER_OPEN"), default=False),
        python_executable=os.getenv("PYTHON_EXE", "python"),
    )
