from __future__ import annotations

import json
import os
from pathlib import Path


def manifest_path() -> Path | None:
    raw = str(os.getenv("GRAPH_STEP1_MANIFEST_PATH", "") or "").strip()
    return Path(raw) if raw else None


def write_manifest_event(event: dict) -> None:
    target = manifest_path()
    if target is None:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def load_manifest_events(manifest_paths: list[str]) -> dict[str, dict]:
    events_by_key: dict[str, dict] = {}
    for manifest_str in manifest_paths:
        target = Path(str(manifest_str or "").strip())
        if not target.exists():
            continue
        for raw_line in target.read_text(encoding="utf-8", errors="replace").splitlines():
            if not raw_line.strip():
                continue
            event = json.loads(raw_line)
            key = str(event.get("key", "") or "").strip()
            if key:
                events_by_key[key] = event
    return events_by_key
