# scripts/vault_writer.py
"""
Writes the generated Markdown file to the Obsidian Vault.

Reads OBSIDIAN_VAULT_PATH from the environment variable first, then falls
back to config/globals.py. Creates the target subdirectory if needed.
"""

import logging
import os
from datetime import date
from pathlib import Path

from config.globals import (
    OBSIDIAN_VAULT_PATH,
    OBSIDIAN_DOCKET_SUBFOLDER,
    OBSIDIAN_FILENAME_PATTERN,
)

log = logging.getLogger(__name__)


def write_to_vault(content: str, today: date) -> Path:
    """
    Write the Markdown content to the Obsidian Vault.

    Returns the absolute path of the written file.
    """
    vault_root_raw = os.environ.get("OBSIDIAN_VAULT_PATH") or OBSIDIAN_VAULT_PATH
    vault_root = Path(vault_root_raw).expanduser().resolve()

    target_dir = vault_root / OBSIDIAN_DOCKET_SUBFOLDER
    target_dir.mkdir(parents=True, exist_ok=True)

    filename = today.strftime(OBSIDIAN_FILENAME_PATTERN)
    output_path = target_dir / filename

    try:
        output_path.write_text(content, encoding="utf-8")
        log.info("Docket report written to: %s", output_path)
    except OSError as exc:
        log.error("Failed to write docket report to %s: %s", output_path, exc)
        raise SystemExit(1) from exc

    return output_path
