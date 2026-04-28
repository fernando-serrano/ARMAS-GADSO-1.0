from __future__ import annotations

from pathlib import Path


def mail_context_summary(config: dict, attachment_paths: list[Path]) -> str:
    return (
        f"sender={config['sender']} | "
        f"to={', '.join(config['to'])} | "
        f"cc={', '.join(config['cc']) or '-'} | "
        f"attachments={', '.join(path.name for path in attachment_paths) or '-'}"
    )
