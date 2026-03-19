# tests/test_output_formatter.py
"""
Unit tests for scripts/output_formatter.py
"""

from datetime import date, timedelta
import pytest

from scripts.output_formatter import build_markdown

TODAY = date(2024, 11, 1)

CSV_META = {
    "filename": "appcoll_export_test.csv",
    "modified": "2024-11-01 06:00 UTC",
    "row_count": 2,
}


def _base_entry(**overrides):
    entry = {
        "matter": "22-TEST-US",
        "entry_type": "Respond to Non-Final Office Action - 3 Month Deadline",
        "application_number": "17/999,999",
        "country": "US",
        "country_full": "United States",
        "title": "Test Patent Title",
        "tier": None,
        "sep_status": None,
        "_priority_score": 100,
        "_priority_number": 1,
        "_effective_deadline": TODAY,
        "_tasks": [],
    }
    entry.update(overrides)
    return entry


def _make_task(name, sp, target_date, is_overdue=False, orig_date=None, help_fields=None):
    return {
        "name": name,
        "subpriority": sp,
        "target_date": target_date,
        "original_target_date": orig_date or target_date,
        "is_overdue": is_overdue,
        "display_name": name,
        "offset_days": 5,
        "help_key": None,
        "help_label": "",
        "help_fields": help_fields or {},
    }


class TestFileHeader:
    def test_header_contains_date(self):
        md = build_markdown([], TODAY, CSV_META)
        assert "2024-11-01" in md

    def test_header_contains_csv_filename(self):
        md = build_markdown([], TODAY, CSV_META)
        assert "appcoll_export_test.csv" in md

    def test_header_yaml_frontmatter(self):
        md = build_markdown([], TODAY, CSV_META)
        assert "date: 2024-11-01" in md
        assert "tags: [docket, patent, daily-review]" in md


class TestTodaysToDo:
    def test_filing_deadline_today_appears_in_table(self):
        entry = _base_entry(_effective_deadline=TODAY, _priority_score=100)
        md = build_markdown([entry], TODAY, CSV_META)
        assert "Filing Deadlines Due Today" in md
        assert "22-TEST-US" in md

    def test_no_deadlines_today_shows_placeholder(self):
        entry = _base_entry(_effective_deadline=TODAY + timedelta(days=5))
        md = build_markdown([entry], TODAY, CSV_META)
        assert "No filing deadlines due today" in md

    def test_task_due_today_appears_in_tasks_table(self):
        task = _make_task("File response with USPTO", "1.1", TODAY, is_overdue=True)
        entry = _base_entry(_tasks=[task])
        md = build_markdown([entry], TODAY, CSV_META)
        assert "Tasks Due Today" in md
        assert "File response with USPTO" in md

    def test_no_tasks_today_shows_placeholder(self):
        task = _make_task("Future task", "1.1", TODAY + timedelta(days=5))
        entry = _base_entry(_tasks=[task])
        md = build_markdown([entry], TODAY, CSV_META)
        assert "No tasks due today" in md


class TestPrioritySection:
    def test_priority_entry_appears(self):
        entry = _base_entry(_priority_score=100, _priority_number=1)
        md = build_markdown([entry], TODAY, CSV_META)
        assert "Priority Docket Entries" in md
        assert "[1]" in md
        assert "22-TEST-US" in md

    def test_score_not_in_output(self):
        entry = _base_entry(_priority_score=100)
        md = build_markdown([entry], TODAY, CSV_META)
        assert "Score" not in md

    def test_overdue_entry_shows_flag(self):
        entry = _base_entry(_priority_score=100, _effective_deadline=TODAY)
        md = build_markdown([entry], TODAY, CSV_META)
        assert "Overdue" in md

    def test_entry_shows_metadata(self):
        entry = _base_entry()
        md = build_markdown([entry], TODAY, CSV_META)
        assert "Test Patent Title" in md
        assert "17/999,999" in md

    def test_family_id_not_in_output(self):
        entry = _base_entry()
        entry["family_id"] = "FAM-TEST"
        md = build_markdown([entry], TODAY, CSV_META)
        assert "FAM-TEST" not in md

    def test_task_block_rendered(self):
        task = _make_task("Review Office Action", "1.1", TODAY + timedelta(days=10))
        entry = _base_entry(_tasks=[task])
        md = build_markdown([entry], TODAY, CSV_META)
        assert "1.1" in md
        assert "Review Office Action" in md
        assert "- [ ]" in md

    def test_overdue_task_block_shows_warning(self):
        task = _make_task(
            "Review Office Action", "1.1", TODAY,
            is_overdue=True, orig_date=date(2024, 10, 1)
        )
        entry = _base_entry(_tasks=[task])
        md = build_markdown([entry], TODAY, CSV_META)
        assert "Overdue" in md
        assert "10/1/2024" in md

    def test_help_fields_rendered(self):
        task = _make_task(
            "Consult Inventor", "1.2", TODAY + timedelta(days=5),
            help_fields={"Responsible Inventor": "Jane Smith", "Art Unit": "2617"},
        )
        task["help_label"] = "Office Action Context"
        entry = _base_entry(_tasks=[task])
        md = build_markdown([entry], TODAY, CSV_META)
        assert "Jane Smith" in md
        assert "2617" in md
        assert "Office Action Context" in md

    def test_below_threshold_entry_not_in_priority_section(self):
        low_entry = _base_entry(_priority_score=20, _priority_number=2, _tasks=[])
        md = build_markdown([low_entry], TODAY, CSV_META)
        priority_section = md.split("Priority Docket Entries")[1].split("Monitored")[0]
        assert "[2]" not in priority_section

    def test_sep_pstrat_avanci_on_same_line(self):
        entry = _base_entry(sep_status="5G", psa="Pursue", avanci_status="Listed")
        md = build_markdown([entry], TODAY, CSV_META)
        # All three should appear, and on the same line
        for line in md.splitlines():
            if "SEP Status" in line:
                assert "PStrat" in line
                assert "Avanci" in line
                break
        else:
            pytest.fail("SEP Status line not found in output")

    def test_due_date_label_and_final_due(self):
        entry = _base_entry(final_due=date(2024, 12, 15))
        md = build_markdown([entry], TODAY, CSV_META)
        assert "Due Date" in md
        assert "Final Due Date" in md
        assert "12/15/2024" in md

    def test_dates_formatted_m_d_yyyy(self):
        entry = _base_entry(_effective_deadline=date(2024, 3, 5))
        md = build_markdown([entry], TODAY, CSV_META)
        assert "3/5/2024" in md


class TestMonitoredSection:
    def test_low_score_entry_in_monitored_table(self):
        low_entry = _base_entry(
            _priority_score=20,
            _priority_number=2,
            _tasks=[],
            _effective_deadline=TODAY + timedelta(days=65),
        )
        md = build_markdown([low_entry], TODAY, CSV_META)
        assert "Monitored Entries" in md
        assert "22-TEST-US" in md.split("Monitored Entries")[1]

    def test_no_low_entries_shows_placeholder(self):
        high_entry = _base_entry(_priority_score=100)
        md = build_markdown([high_entry], TODAY, CSV_META)
        assert "No entries in the monitored range" in md


class TestWarningsSection:
    def test_warnings_appear_at_bottom(self):
        md = build_markdown([], TODAY, CSV_META, warnings=["Could not parse date 'baddate'"])
        assert "Report Warnings" in md
        assert "Could not parse date" in md

    def test_no_warnings_no_section(self):
        md = build_markdown([], TODAY, CSV_META, warnings=[])
        assert "Report Warnings" not in md
