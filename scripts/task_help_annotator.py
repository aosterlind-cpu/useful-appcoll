# scripts/task_help_annotator.py
"""
Injects contextual help fields into each task based on task_help.yaml.

For each task in entry["_tasks"], looks up the task's help_key in
task_help.yaml and fetches the corresponding field values from the entry,
storing them as task["help_fields"] = {label: value}.

Fields with null/empty values are silently omitted.
"""

import logging
import re
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

_TASK_HELP_PATH = Path(__file__).parent.parent / "config" / "task_help.yaml"


def _load_task_help() -> dict:
    try:
        with open(_TASK_HELP_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("task_help", {})
    except yaml.YAMLError as exc:
        log.error("Invalid YAML in task_help.yaml: %s", exc)
        raise SystemExit(1) from exc


_TASK_HELP: dict = _load_task_help()


def annotate_task_help(entry: dict) -> None:
    """
    Populate task["help_fields"] for every task in entry["_tasks"].
    Mutates tasks in-place.
    """
    for task in entry.get("_tasks", []):
        help_key = task.get("help_key")
        if not help_key or help_key not in _TASK_HELP:
            task["help_fields"] = {}
            task["help_label"] = ""
            continue

        help_def = _TASK_HELP[help_key]
        task["help_label"] = help_def.get("label", "") or ""
        fields_def: list[dict] = help_def.get("fields", [])

        help_fields: dict[str, str] = {}
        for field_def in fields_def:
            py_field = field_def["field"]
            label = field_def["label"]
            value = entry.get(py_field)
            if value is None or str(value).strip().lower() in ("", "nan", "None", "na"):
                continue
            raw = str(value).strip()
            link_type = field_def.get("link_type")
            if link_type == "url":
                link_text = field_def.get("link_text", raw)
                formatted = f"[{link_text}]({raw})"
            elif link_type == "email":
                formatted = f"[{raw}](mailto:{raw})"
            elif py_field == "connections":
                matches = re.findall(r'\d{2}-\d{4}[A-Za-z]+', raw)
                formatted = "; ".join(matches) if matches else raw
            else:
                formatted = raw
            help_fields[label] = formatted

        task["help_fields"] = help_fields
