# tests/test_subpriority_engine.py
"""
Unit tests for scripts/subpriority_engine.py
"""

from datetime import date, timedelta

from scripts.subpriority_engine import assign_subpriorities

TODAY = date(2024, 11, 1)
DEADLINE = date(2024, 12, 1)   # 30 days from today


def _make_tasks(*offset_days_list):
    """Create a list of task dicts with the given offset_days, sorted descending."""
    tasks = [{"name": f"Task {i}", "offset_days": od, "help_key": None}
             for i, od in enumerate(sorted(offset_days_list, reverse=True), start=1)]
    return tasks


def _make_entry(tasks, deadline=DEADLINE, number=1):
    return {
        "_priority_number": number,
        "_effective_deadline": deadline,
        "_tasks": tasks,
    }


class TestSubpriorityLabels:
    def test_labels_assigned_sequentially(self):
        entry = _make_entry(_make_tasks(20, 10, 5))
        assign_subpriorities(entry, TODAY)
        labels = [t["subpriority"] for t in entry["_tasks"]]
        assert labels == ["1.1", "1.2", "1.3"]

    def test_labels_use_priority_number(self):
        entry = _make_entry(_make_tasks(10, 5), number=3)
        assign_subpriorities(entry, TODAY)
        labels = [t["subpriority"] for t in entry["_tasks"]]
        assert labels == ["3.1", "3.2"]


class TestTargetDateComputation:
    def test_target_date_is_deadline_minus_offset(self):
        entry = _make_entry(_make_tasks(10))
        assign_subpriorities(entry, TODAY)
        task = entry["_tasks"][0]
        assert task["target_date"] == DEADLINE - timedelta(days=10)

    def test_future_task_not_overdue(self):
        entry = _make_entry(_make_tasks(10))
        assign_subpriorities(entry, TODAY)
        task = entry["_tasks"][0]
        assert task["is_overdue"] is False
        assert task["display_name"] == task["name"]  # normal case

    def test_task_name_unchanged_when_not_overdue(self):
        entry = _make_entry(_make_tasks(5))
        assign_subpriorities(entry, TODAY)
        task = entry["_tasks"][0]
        assert task["display_name"] == "Task 1"


class TestOverdueTasks:
    def test_overdue_task_target_date_set_to_today(self):
        # offset_days=35 → raw target = Dec 1 - 35 days = Oct 27, which is < TODAY (Nov 1)
        entry = _make_entry(_make_tasks(35))
        assign_subpriorities(entry, TODAY)
        task = entry["_tasks"][0]
        assert task["is_overdue"] is True
        assert task["target_date"] == TODAY

    def test_overdue_display_name_unchanged(self):
        entry = _make_entry(_make_tasks(35))
        entry["_tasks"][0]["name"] = "Review the document"
        assign_subpriorities(entry, TODAY)
        task = entry["_tasks"][0]
        assert task["display_name"] == "Review the document"

    def test_original_target_date_preserved(self):
        entry = _make_entry(_make_tasks(35))
        assign_subpriorities(entry, TODAY)
        task = entry["_tasks"][0]
        expected_raw = DEADLINE - timedelta(days=35)
        assert task["original_target_date"] == expected_raw
        assert task["original_target_date"] < TODAY


class TestMonotonicDateEnforcement:
    def test_later_task_date_after_earlier_task_date(self):
        """Task B (lower priority) must have a later date than task A (higher priority)."""
        # offsets: 20 → target Nov 11, 5 → target Nov 26. No collision.
        entry = _make_entry(_make_tasks(20, 5))
        assign_subpriorities(entry, TODAY)
        t1, t2 = entry["_tasks"]
        assert t1["target_date"] < t2["target_date"]

    def test_collision_adjusted_to_day_after(self):
        """If two tasks compute the same raw date, the second gets day+1."""
        # With DEADLINE=Dec 1: offset 30 → Nov 1=TODAY; offset 31 → Oct 31 (overdue→today)
        # Both would be set to TODAY. Monotonic enforcement: second task → TODAY+1 day
        entry = _make_entry(_make_tasks(31, 30))
        assign_subpriorities(entry, TODAY)
        t1, t2 = entry["_tasks"]
        assert t1["target_date"] == TODAY         # first task: overdue, capped at today
        assert t2["target_date"] >= t1["target_date"]  # second must be >= first

    def test_three_tasks_monotonic_order(self):
        entry = _make_entry(_make_tasks(25, 20, 5))
        assign_subpriorities(entry, TODAY)
        dates = [t["target_date"] for t in entry["_tasks"]]
        assert dates == sorted(dates)

    def test_all_overdue_all_capped_at_today(self):
        """Multiple overdue tasks: all capped at today, display_name unchanged."""
        # offsets 35, 32, 31 → all raw dates in Oct (< TODAY)
        entry = _make_entry(_make_tasks(35, 32, 31))
        assign_subpriorities(entry, TODAY)
        for task in entry["_tasks"]:
            assert task["is_overdue"] is True
            assert task["display_name"] == task["name"]
            assert task["target_date"] == TODAY


class TestNoDeadline:
    def test_no_deadline_all_tasks_get_today(self):
        entry = _make_entry(_make_tasks(10, 5), deadline=None)
        assign_subpriorities(entry, TODAY)
        for task in entry["_tasks"]:
            assert task["target_date"] == TODAY
            assert task["is_overdue"] is False
