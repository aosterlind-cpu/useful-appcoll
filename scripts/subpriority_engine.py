# scripts/subpriority_engine.py
"""
Subpriority assignment and date adjustment logic.

Given a docket entry that already has:
  - entry["_priority_letter"] : str  (e.g. "A", "B")
  - entry["_effective_deadline"] : date
  - entry["_tasks"] : list[dict]  (from task_generator)

Mutates each task in-place to add:
  subpriority  : str        e.g. "A.1", "A.2"
  target_date  : date       when the task should be completed
  is_overdue   : bool
  display_name : str        ALL CAPS if overdue
  original_target_date : date   raw computed date (before overdue adjustment)
"""

import logging
from datetime import date, timedelta

log = logging.getLogger(__name__)


def assign_subpriorities(entry: dict, today: date) -> None:
    """
    Assign subpriority labels and target dates to each task in entry["_tasks"].
    Mutates tasks in-place. Tasks must already be sorted by offset_days
    descending (generate_tasks_for_entry guarantees this).
    """
    tasks: list[dict] = entry.get("_tasks", [])
    if not tasks:
        return

    letter: str = entry.get("_priority_letter", "?")
    deadline: date | None = entry.get("_effective_deadline")

    if deadline is None:
        # No deadline: assign today as target for all tasks
        for i, task in enumerate(tasks, start=1):
            task["subpriority"] = f"{letter}.{i}"
            task["target_date"] = today
            task["original_target_date"] = today
            task["is_overdue"] = False
            task["display_name"] = task["name"]
        return

    # --- Step 1: compute raw target dates and overdue status ---
    for task in tasks:
        raw = deadline - timedelta(days=task["offset_days"])
        task["original_target_date"] = raw
        if raw < today:
            task["is_overdue"] = True
            task["target_date"] = today
            task["display_name"] = task["name"].upper()
        else:
            task["is_overdue"] = False
            task["target_date"] = raw
            task["display_name"] = task["name"]

    # --- Step 2: enforce monotonic date ordering (subpriority .1 first) ---
    # Tasks are already sorted offset_days DESC, meaning .1 has the largest
    # offset (earliest warning, should have the earliest target date).
    # We ensure each successive task's date is on or after the previous.
    #
    # Edge case: overdue tasks are all capped at today. If multiple tasks are
    # overdue they all display as today in ALL CAPS — monotonic enforcement
    # does NOT push overdue tasks past today (spec §7).
    previous_date: date | None = None
    for task in tasks:
        if task["is_overdue"]:
            # Overdue tasks are always capped at today regardless of previous.
            task["target_date"] = today
            task["display_name"] = task["name"].upper()
            previous_date = today
        else:
            if previous_date is not None and task["target_date"] <= previous_date:
                adjusted = previous_date + timedelta(days=1)
                task["target_date"] = adjusted
                # Re-evaluate overdue status after adjustment
                if task["target_date"] < today:
                    task["is_overdue"] = True
                    task["display_name"] = task["name"].upper()
                    task["target_date"] = today
                else:
                    task["is_overdue"] = False
                    task["display_name"] = task["name"]
            previous_date = task["target_date"]

    # --- Step 3: assign subpriority labels ---
    for i, task in enumerate(tasks, start=1):
        task["subpriority"] = f"{letter}.{i}"
        # Initialise help_fields placeholder (populated by task_help_annotator)
        task.setdefault("help_fields", {})
