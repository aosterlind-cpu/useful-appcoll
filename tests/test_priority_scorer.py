# tests/test_priority_scorer.py
"""
Unit tests for scripts/priority_scorer.py
"""

from datetime import date, timedelta
import pytest

from scripts.priority_scorer import compute_priority_score
from config.globals import (
    PRIORITY_SCORE_OVERDUE,
    PRIORITY_SCORE_NO_DEADLINE,
    PRIORITY_SCORE_OFFSETS,
)

TODAY = date(2024, 11, 1)


def _entry(respond_by=None, final_due=None):
    return {"respond_by": respond_by, "final_due": final_due}


class TestNullDeadlines:
    def test_no_deadline_fields(self):
        score, dl = compute_priority_score(_entry(), today=TODAY)
        assert score == PRIORITY_SCORE_NO_DEADLINE
        assert dl is None

    def test_both_null(self):
        score, dl = compute_priority_score(_entry(respond_by=None, final_due=None), today=TODAY)
        assert score == PRIORITY_SCORE_NO_DEADLINE

    def test_fallback_to_final_due(self):
        # respond_by is null; final_due is 20 days away → score 50
        entry = _entry(final_due=TODAY + timedelta(days=20))
        score, dl = compute_priority_score(entry, today=TODAY)
        assert score == 50
        assert dl == TODAY + timedelta(days=20)


class TestOverdueDeadlines:
    def test_deadline_today(self):
        score, dl = compute_priority_score(_entry(respond_by=TODAY), today=TODAY)
        assert score == PRIORITY_SCORE_OVERDUE

    def test_deadline_yesterday(self):
        score, dl = compute_priority_score(
            _entry(respond_by=TODAY - timedelta(days=1)), today=TODAY
        )
        assert score == PRIORITY_SCORE_OVERDUE

    def test_deadline_far_past(self):
        score, _ = compute_priority_score(
            _entry(respond_by=TODAY - timedelta(days=365)), today=TODAY
        )
        assert score == PRIORITY_SCORE_OVERDUE


class TestScoreBoundaries:
    """Test each boundary in PRIORITY_SCORE_OFFSETS.

    PRIORITY_SCORE_OFFSETS = [
        (10, 90), (20, 60), (30, 45), (40, 30), (50, 21),
        (60, 14), (70, 7), (80, 3), (90, 1)
    ]
    """

    # Actual scoring tiers (algorithm: score = highest tier where days_until <= offset):
    #   91+ days  → 0  (no tier matches: 91 > 90)
    #   61-90     → 10
    #   46-60     → 20
    #   31-45     → 30
    #   22-30     → 40
    #   15-21     → 50
    #   8-14      → 60
    #   4-7       → 70
    #   2-3       → 80
    #   1 day     → 90
    #   0 or past → 100 (OVERDUE)
    @pytest.mark.parametrize("days_until,expected_score", [
        (91, 0),    # > 90 days: no tier matches → score 0
        (90, 10),   # exactly 90 → score 10
        (61, 10),   # 61 days → score 10 (still in 61-90 tier)
        (60, 20),   # exactly 60 → score 20
        (46, 20),   # 46 days → score 20
        (45, 30),   # exactly 45 → score 30
        (31, 30),   # 31 days → score 30
        (30, 40),   # exactly 30 → score 40
        (25, 40),   # example from spec: 25 days → score 40
        (22, 40),   # 22 days → score 40
        (21, 50),   # exactly 21 → score 50
        (15, 50),   # 15 days → score 50
        (14, 60),   # exactly 14 → score 60
        (8, 60),    # 8 days → score 60
        (7, 70),    # exactly 7 → score 70
        (4, 70),    # 4 days → score 70
        (3, 80),    # exactly 3 → score 80
        (2, 80),    # 2 days → score 80
        (1, 90),    # exactly 1 → score 90
    ])
    def test_score_at_boundary(self, days_until, expected_score):
        deadline = TODAY + timedelta(days=days_until)
        score, dl = compute_priority_score(_entry(respond_by=deadline), today=TODAY)
        assert score == expected_score, (
            f"days_until={days_until}: expected score {expected_score}, got {score}"
        )

    def test_very_far_future(self):
        deadline = TODAY + timedelta(days=365)
        score, _ = compute_priority_score(_entry(respond_by=deadline), today=TODAY)
        # 365 days > 90 → only (10, 90) never satisfies days_until <= 90 → score stays 0?
        # Actually 365 > 90, so days_until <= 90 is False for first entry → break → score = 0
        assert score == 0


class TestReturnValues:
    def test_returns_effective_deadline(self):
        dl_date = TODAY + timedelta(days=25)
        score, dl = compute_priority_score(_entry(respond_by=dl_date), today=TODAY)
        assert dl == dl_date

    def test_respond_by_takes_precedence_over_final_due(self):
        respond = TODAY + timedelta(days=10)  # 10 days → score 60 (8-14 tier)
        final = TODAY + timedelta(days=50)    # 50 days → score 20 if used
        score, dl = compute_priority_score(_entry(respond_by=respond, final_due=final), today=TODAY)
        assert score == 60
        assert dl == respond
