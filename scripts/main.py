# scripts/main.py
"""
Entry point. Orchestrates the full pipeline:
  1. Load and validate CSV
  2. Filter open entries
  3. Score entries
  4. Sort by descending score (tie-break by document_number)
  5. Assign priority letters (A, B, C, ...)
  6. Generate tasks for threshold-meeting entries
  7. Assign subpriorities and adjust dates
  8. Annotate tasks with help fields
  9. Build Markdown
  10. Write to Obsidian Vault
"""

import logging
import string
import sys
from datetime import date

from config.globals import TASK_GENERATION_THRESHOLD, OPEN_ENTRIES_ONLY
from scripts.csv_loader import load_appcoll_csv
from scripts.priority_scorer import compute_priority_score
from scripts.task_generator import generate_tasks_for_entry
from scripts.subpriority_engine import assign_subpriorities
from scripts.task_help_annotator import annotate_task_help
from scripts.output_formatter import build_markdown
from scripts.vault_writer import write_to_vault

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)


def main() -> None:
    today = date.today()
    warnings: list[str] = []
    log.info("Starting docket report generation for %s", today)

    # 1. Load CSV
    try:
        entries, csv_meta = load_appcoll_csv(warnings=warnings)
    except (FileNotFoundError, RuntimeError) as exc:
        log.error("CSV load failed: %s", exc)
        sys.exit(1)
    log.info("Loaded %d entries from %s", len(entries), csv_meta["filename"])

    # 2. Filter to open entries only
    if OPEN_ENTRIES_ONLY:
        entries = [e for e in entries if not e.get("closed_on")]
        log.info("%d open entries after filtering", len(entries))

    # 3. Score entries
    for entry in entries:
        score, deadline = compute_priority_score(entry, today)
        entry["_priority_score"] = score
        entry["_effective_deadline"] = deadline

    # 4. Sort: descending score, then document_number for tie-breaking
    entries.sort(key=lambda e: (-e["_priority_score"], e.get("document_number") or ""))

    # 5. Assign priority letters (A-Z, then Z1, Z2, ... for overflow)
    letter_pool = list(string.ascii_uppercase)
    for i, entry in enumerate(entries):
        if i < 26:
            entry["_priority_letter"] = letter_pool[i]
        else:
            entry["_priority_letter"] = f"Z{i - 25}"

    # 6. Generate tasks for entries meeting the threshold
    for entry in entries:
        if entry["_priority_score"] >= TASK_GENERATION_THRESHOLD:
            entry["_tasks"] = generate_tasks_for_entry(entry)
        else:
            entry["_tasks"] = []

    # 7. Assign subpriorities and compute/adjust task dates
    for entry in entries:
        if entry["_tasks"]:
            assign_subpriorities(entry, today)

    # 8. Annotate tasks with contextual help fields
    for entry in entries:
        if entry["_tasks"]:
            annotate_task_help(entry)

    # 9. Build Markdown
    markdown_content = build_markdown(entries, today, csv_meta, warnings=warnings)

    # 10. Write to Obsidian Vault
    output_path = write_to_vault(markdown_content, today)
    log.info("Report written to: %s", output_path)


if __name__ == "__main__":
    main()
