# scripts/priority_scorer.py
"""
Numerical priority scoring engine.

Assigns a priority score to each docket entry based on how many calendar
days remain until its effective deadline.
"""

import logging
from datetime import date

from config.globals import (
    PRIORITY_SCORE_OFFSETS,
    PRIORITY_SCORE_OVERDUE,
    PRIORITY_SCORE_NO_DEADLINE,
    PRIMARY_DEADLINE_FIELD,
    FALLBACK_DEADLINE_FIELD,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Startup validation
# ---------------------------------------------------------------------------

def _assert_offsets_sorted() -> None:
    """Assert PRIORITY_SCORE_OFFSETS is sorted by offset_days DESCENDING."""
    offsets = [o for _, o in PRIORITY_SCORE_OFFSETS]
    if offsets != sorted(offsets, reverse=True):
        raise ValueError(
            "PRIORITY_SCORE_OFFSETS must be sorted by offset_days DESCENDING. "
            f"Current order: {offsets}"
        )


_assert_offsets_sorted()


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def compute_priority_score(entry: dict, today: date | None = None) -> tuple[int, date | None]:
    """
    Compute the priority score for a single docket entry.

    Parameters
    ----------
    entry : dict
        Normalized docket entry (Python field names).
    today : date, optional
        Reference date. Defaults to date.today().

    Returns
    -------
    (priority_score, effective_deadline_date)
        effective_deadline_date is None when no deadline is available.
    """
    if today is None:
        today = date.today()

    deadline: date | None = entry.get(PRIMARY_DEADLINE_FIELD) or entry.get(FALLBACK_DEADLINE_FIELD)

    if deadline is None:
        return PRIORITY_SCORE_NO_DEADLINE, None

    days_until = (deadline - today).days

    if days_until <= 0:
        return PRIORITY_SCORE_OVERDUE, deadline

    # Walk through offsets (sorted descending). Keep updating score as long as
    # days_until <= offset. Stop at the first offset that days_until exceeds.
    score = 0
    for score_value, offset_days in PRIORITY_SCORE_OFFSETS:
        if days_until <= offset_days:
            score = score_value
        else:
            # List is sorted descending, so no later entry can match either.
            break

    return score, deadline
