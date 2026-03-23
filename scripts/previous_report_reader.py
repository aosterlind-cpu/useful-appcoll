# scripts/previous_report_reader.py
"""
Reads the most recently generated docket Markdown file and extracts
completed tasks (checked checkboxes) keyed by (matter, task_type).
"""
from __future__ import annotations

import logging
import os
import re
from datetime import date
from pathlib import Path

from config.globals import (
    OBSIDIAN_VAULT_PATH,
    OBSIDIAN_DOCKET_SUBFOLDER,
)

log = logging.getLogger(__name__)

# Match entry headings: ### [N] matter · task_type [· status_flag]
_HEADING_RE = re.compile(r'^### \[\d+\] (.+)$')
_STATUS_SUFFIX_RE = re.compile(r'\s+\u00b7\s+(?:Overdue|\d+ days? remaining)$')
_CHECKED_RE = re.compile(r'^- \[x\] \*\*(.+)\*\*', re.IGNORECASE)

_SEP = f" \u00b7 "


def load_completed_tasks(today: date) -> dict[tuple[str, str], set[str]]:
    """
    Return {(matter, task_type): {completed_display_name, ...}} from the
    most recent docket file whose date is before today.

    Returns an empty dict if no previous file is found.
    """
    vault_root = (
        Path(os.environ.get("OBSIDIAN_VAULT_PATH") or OBSIDIAN_VAULT_PATH)
        .expanduser()
        .resolve()
    )
    daily_dir = vault_root / OBSIDIAN_DOCKET_SUBFOLDER

    if not daily_dir.exists():
        log.info("Vault daily directory not found; skipping completed-task carry-forward.")
        return {}

    pattern = re.compile(r'^Docket_(\d{4}-\d{2}-\d{2})\.md$')
    candidates: list[tuple[date, Path]] = []
    for f in daily_dir.iterdir():
        m = pattern.match(f.name)
        if m:
            file_date = date.fromisoformat(m.group(1))
            if file_date < today:
                candidates.append((file_date, f))

    if not candidates:
        log.info("No previous docket file found; no completed tasks to carry forward.")
        return {}

    _, prev_file = max(candidates, key=lambda x: x[0])
    log.info("Reading completed tasks from previous report: %s", prev_file.name)

    return _parse_completed_tasks(prev_file.read_text(encoding="utf-8"))


def _parse_completed_tasks(text: str) -> dict[tuple[str, str], set[str]]:
    """Parse a docket Markdown file and return completed tasks by entry key."""
    completed: dict[tuple[str, str], set[str]] = {}
    current_key: tuple[str, str] | None = None

    for line in text.splitlines():
        heading_match = _HEADING_RE.match(line)
        if heading_match:
            raw = _STATUS_SUFFIX_RE.sub("", heading_match.group(1))
            idx = raw.find(_SEP)
            if idx != -1:
                matter = raw[:idx].strip()
                task_type = raw[idx + len(_SEP):].strip()
                current_key = (matter, task_type)
            else:
                current_key = None
            continue

        if current_key is None:
            continue

        checked_match = _CHECKED_RE.match(line)
        if checked_match:
            display_name = checked_match.group(1)
            completed.setdefault(current_key, set()).add(display_name)

    return completed
