# config/globals.py
"""
Global configuration for the AppColl Docket Automation system.

HOW TO EDIT:
- To change priority score values: edit PRIORITY_SCORE_OFFSETS.
- To add a new priority tier: add a new entry (score, offset_days) to PRIORITY_SCORE_OFFSETS.
  The list MUST remain sorted by offset_days DESCENDING (earliest warning first).
- To change the task-generation threshold: edit TASK_GENERATION_THRESHOLD.
- All offsets are calendar days BEFORE the filing deadline (respond_by date).
  Larger offset_days = earlier warning = higher urgency = higher score.
"""

from datetime import date  # noqa: F401  (imported for type annotation use by callers)

# ---------------------------------------------------------------------------
# PRIORITY SCORING
# ---------------------------------------------------------------------------

# Each tuple: (score_value, days_before_deadline)
# The entry with the LARGEST days_before_deadline that is still >= days_until_deadline
# determines the score for a given docket entry.
#
# MUST be sorted by offset_days DESCENDING.
PRIORITY_SCORE_OFFSETS: list[tuple[int, int]] = [
    (10, 90),   # Score 10: deadline is 90 or more days away
    (20, 60),   # Score 20: deadline is 60-89 days away
    (30, 45),   # Score 30: deadline is 45-59 days away
    (40, 30),   # Score 40: deadline is 30-44 days away
    (50, 21),   # Score 50: deadline is 21-29 days away
    (60, 14),   # Score 60: deadline is 14-20 days away
    (70, 7),    # Score 70: deadline is 7-13 days away
    (80, 3),    # Score 80: deadline is 3-6 days away
    (90, 1),    # Score 90: deadline is 1-2 days away
]

# Score offset increase when deadline is TODAY or has ALREADY PASSED
PRIORITY_SCORE_OVERDUE: int = 95

# Score assigned when no deadline date is available (respond_by is null)
PRIORITY_SCORE_NO_DEADLINE: int = 0

# Score offset decrease applied when deadline is not hard but is extendible 
PRIORITY_SCORE_EXTENDIBLE: int = -5

# Score offset decrease applied when deadline is FOA Response - 2 month deadline 
FOA_2_MO_OFFSET: int = -25

# Score offset increase applied when deadline is not extendible 
PRIORITY_SCORE_NON_EXTENDIBLE: int = 5

# Score Threshold for being included in docket output. Only entries with score >= this value will be included. 
PRIORITY_SCORE_THRESHOLD: int = 70

# ---------------------------------------------------------------------------
# TASK GENERATION THRESHOLD
# ---------------------------------------------------------------------------

# Docket entries with a priority score >= this value will have tasks generated.
# Set to 0 to generate tasks for ALL entries with any score.
TASK_GENERATION_THRESHOLD: int = 70

# ---------------------------------------------------------------------------
# OUTPUT
# ---------------------------------------------------------------------------

# Path to the Obsidian Vault root (override via environment variable
# OBSIDIAN_VAULT_PATH for CI/CD; this default is used for local runs)
OBSIDIAN_VAULT_PATH: str = "~/Documents/ObsidianVault"

# Sub-folder within the vault where daily docket notes are written
OBSIDIAN_DOCKET_SUBFOLDER: str = "Docket"

# Filename pattern for the daily note. Supports strftime codes.
OBSIDIAN_FILENAME_PATTERN: str = "Docket_%Y-%m-%d.md"

# ---------------------------------------------------------------------------
# CSV INGESTION
# ---------------------------------------------------------------------------

# Directory where AppColl CSV exports are placed (local or mounted path)
APPCOLL_CSV_DIR: str = "data/appcoll_exports"

# If True, always use the most recently modified CSV in APPCOLL_CSV_DIR.
# If False, expect a file named exactly APPCOLL_CSV_FILENAME.
USE_LATEST_CSV: bool = True
APPCOLL_CSV_FILENAME: str = "appcoll_export.csv"

# The primary deadline field used for scoring (must match a Python field name
# from the field reference table).
PRIMARY_DEADLINE_FIELD: str = "respond_by"

# Fallback deadline field used if PRIMARY_DEADLINE_FIELD is null/missing.
FALLBACK_DEADLINE_FIELD: str = "final_due"

# Open/closed filter: if True, only process entries where closed_on is null.
OPEN_ENTRIES_ONLY: bool = True

# ---------------------------------------------------------------------------
# DATE HANDLING
# ---------------------------------------------------------------------------

# Date formats to try when parsing date strings from the CSV.
DATE_PARSE_FORMATS: list[str] = [
    "%m/%d/%Y",
    "%Y-%m-%d",
    "%m/%d/%y",
    "%B %d, %Y",
    "%d-%b-%Y",
]

