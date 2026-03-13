# scripts/task_generator.py
"""
Rule-based task generation engine.

Loads config/rules.yaml at module import. For each docket entry, evaluates
all rules and collects tasks from every rule whose conditions all pass.
Tasks are then deduplicated by name (case-insensitive), keeping the highest
offset_days value.
"""

import logging
import re
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

_RULES_PATH = Path(__file__).parent.parent / "config" / "rules.yaml"


def _load_rules() -> list[dict]:
    try:
        with open(_RULES_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        rules = data.get("rules", [])
        log.info("Loaded %d rules from %s", len(rules), _RULES_PATH)
        return rules
    except yaml.YAMLError as exc:
        log.error("Invalid YAML in rules.yaml: %s", exc)
        raise SystemExit(1) from exc


_RULES: list[dict] = _load_rules()


# ---------------------------------------------------------------------------
# Condition evaluation
# ---------------------------------------------------------------------------

def _evaluate_condition(entry: dict, condition: dict) -> bool:
    """Return True if entry satisfies the condition."""
    field = condition["field"]
    op = condition["op"]
    value = condition.get("value")
    entry_value = entry.get(field)

    # Null checks
    if op == "is_null":
        return entry_value is None or str(entry_value).strip() == ""
    if op == "is_not_null":
        return entry_value is not None and str(entry_value).strip() != ""

    if entry_value is None:
        log.debug("Condition skipped (field %r is None): op=%r value=%r", field, op, value)
        return False

    ev_str = str(entry_value).strip()

    if op == "eq":
        return ev_str.lower() == str(value).lower()
    if op == "ne":
        return ev_str.lower() != str(value).lower()
    if op == "contains":
        return str(value).lower() in ev_str.lower()
    if op == "matches":
        return bool(re.search(str(value), ev_str, re.IGNORECASE))
    if op == "in":
        return ev_str.lower() in [str(v).lower() for v in value]
    if op == "not_in":
        return ev_str.lower() not in [str(v).lower() for v in value]
    if op in ("gt", "lt", "gte", "lte"):
        # Try numeric comparison first, then date
        try:
            ev_num = float(ev_str)
            val_num = float(value)
            return {
                "gt": ev_num > val_num,
                "lt": ev_num < val_num,
                "gte": ev_num >= val_num,
                "lte": ev_num <= val_num,
            }[op]
        except (ValueError, TypeError):
            from datetime import date as _date
            if isinstance(entry_value, _date) and isinstance(value, _date):
                return {
                    "gt": entry_value > value,
                    "lt": entry_value < value,
                    "gte": entry_value >= value,
                    "lte": entry_value <= value,
                }[op]

    log.warning("Unknown operator %r in rule condition; treating as False", op)
    return False


def _evaluate_rule(entry: dict, rule: dict) -> bool:
    """Return True if all conditions in the rule pass for the entry."""
    for condition in rule.get("conditions", []):
        if not _evaluate_condition(entry, condition):
            log.debug(
                "Rule %r did not match: failed condition field=%r op=%r value=%r (entry value=%r)",
                rule.get("id"),
                condition.get("field"),
                condition.get("op"),
                condition.get("value"),
                entry.get(condition.get("field")),
            )
            return False
    return True


# ---------------------------------------------------------------------------
# Task generation
# ---------------------------------------------------------------------------

def generate_tasks_for_entry(entry: dict) -> list[dict]:
    """
    Evaluate all rules against the entry and return the merged, deduplicated
    list of task dicts.

    Each returned task dict has:
        name         : str
        offset_days  : int
        help_key     : str | None
    """
    accumulated: dict[str, dict] = {}  # lowercase task name -> task dict

    for rule in _RULES:
        rule_id = rule.get("id", "<unknown>")
        if _evaluate_rule(entry, rule):
            log.debug("Rule %r matched entry %r", rule_id, entry.get("matter", entry.get("document_number")))
            for task_def in rule.get("tasks", []):
                task = {
                    "name": task_def["name"],
                    "offset_days": int(task_def.get("offset_days", 0)),
                    "help_key": task_def.get("help_key"),
                }
                key = task["name"].lower()
                # Dedup: keep the entry with the largest offset_days
                if key not in accumulated or task["offset_days"] > accumulated[key]["offset_days"]:
                    accumulated[key] = task
        else:
            log.debug("Rule %r did not match entry %r", rule_id, entry.get("matter"))

    tasks = list(accumulated.values())
    # Sort by offset_days descending (highest = earliest warning = first in list)
    tasks.sort(key=lambda t: -t["offset_days"])
    return tasks
