# scripts/csv_loader.py
"""
AppColl CSV ingestion and normalization.

Loads the most-recent (or named) CSV from APPCOLL_CSV_DIR and returns a
list of normalized dicts plus file metadata.

Column mapping strategy
-----------------------
AppColl exports contain two categories of columns:

1. Task-level columns  (e.g. TaskStatus, TaskType, RespondBy, FinalDueDate)
2. Matter-level columns prefixed with "Matter."
   (e.g. Matter.Title, Matter.CountryCode, Matter.SEP)

The COLUMN_MAP below maps the *normalized* CSV header (lowercase, stripped)
to the Python field name used throughout the rest of the system.

When the same logical field appears at both levels (e.g. FeesCap and
Matter.FeesCap) the matter-level value is preferred because it is more
authoritative; the task-level value is written first, then overwritten if
the matter-level value is non-empty.
"""

import logging

from datetime import date, datetime
from pathlib import Path

import pandas as pd

from config.globals import (
    APPCOLL_CSV_DIR,
    USE_LATEST_CSV,
    APPCOLL_CSV_FILENAME,
    DATE_PARSE_FORMATS,
)

from config.column_map import COLUMN_MAP

log = logging.getLogger(__name__)

# Fields parsed as dates
DATE_FIELDS: frozenset[str] = frozenset({
    "ref_date", "modified", "respond_by", "final_due", "closed_on",
    "open_date", "planned_filing_date", "filing_date", "first_office_action",
    "allowance_date", "abandoned_date", "issue_date", "expiration_date",
    "last_pair_updated", "submission_date", "revival_date",
    "earliest_benefit_date", "official_filing_date", "created_date",
    "publication_date", "priority_field", "next_external_deadline",
    "matter_modified", "next_internal_task_due", "last_patent_office_update_date",
})

# Fields parsed as numeric (float)
NUMERIC_FIELDS: frozenset[str] = frozenset({
    "budget_hours", "fees_cap", "actual_expense", "actual_cost",
    "number_of_claims", "independent_claims", "budget_expense", "budget_cost",
    "patent_term_adjustment",
})


def _normalize_key(raw: str) -> str:
    """Lowercase and strip whitespace from a column header."""
    return raw.strip().lower()


def _parse_date(raw: str) -> date | None:
    """Try each DATE_PARSE_FORMATS; return a date or None on failure."""
    if not raw or str(raw).strip().lower() in ("", "none", "na"):
        return None
    s = str(raw).strip()
    # dateutil can handle many formats; try explicit formats first
    for fmt in DATE_PARSE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except (ValueError, TypeError):
            continue
    # Fallback: try dateutil
    try:
        from dateutil import parser as du_parser
        return du_parser.parse(s, dayfirst=False).date()
    except Exception:
        return None


def _parse_numeric(raw) -> float | None:
    """Parse a numeric value, handling commas and empty strings."""
    if raw is None or str(raw).strip().lower() in ("", "nan", "none", "na"):
        return None
    try:
        return float(str(raw).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _clean_str(raw) -> str | None:
    """Return stripped string or None if empty/NaN."""
    if raw is None:
        return None
    s = str(raw).strip().lower()
    return s if s not in ("", "nan", "none", "na") else None


def _find_csv(warnings: list[str]) -> Path:
    """Locate the CSV file to load."""
    csv_dir = Path(APPCOLL_CSV_DIR).expanduser()
    if not csv_dir.exists():
        raise FileNotFoundError(
            f"CSV directory not found: {csv_dir}. "
            f"Place an AppColl CSV export in that directory."
        )
    if USE_LATEST_CSV:
        csvs = sorted(csv_dir.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not csvs:
            raise FileNotFoundError(
                f"No CSV files found in {csv_dir}. "
                f"Export a CSV from AppColl and place it there."
            )
        return csvs[0]
    else:
        p = csv_dir / APPCOLL_CSV_FILENAME
        if not p.exists():
            raise FileNotFoundError(
                f"Expected CSV not found: {p}. "
                f"Export a CSV from AppColl and save it with that name."
            )
        return p


def _build_column_rename_map(df_columns: list[str]) -> dict[str, str]:
    """
    Build a rename dict mapping actual DataFrame column names to Python field names.
    Uses COLUMN_MAP (exact normalized match), then falls back to stripping
    the 'matter.' prefix for any remaining unknown columns.
    """
    rename: dict[str, str] = {}
    unmapped: list[str] = []

    if COLUMN_MAP is None or not isinstance(COLUMN_MAP, dict) or COLUMN_MAP == {}:
        log.error("COLUMN_MAP is not defined or empty. Please define it in config/column_map.py.")
        raise ValueError("Invalid COLUMN_MAP configuration.")

    for col in df_columns:
        norm = _normalize_key(col)
        if norm in COLUMN_MAP:
            rename[col] = COLUMN_MAP[norm]
        else:
            log.debug("Unknown CSV column (will be kept as-is): %r", col)
            unmapped.append(col)

    if unmapped:
        log.debug("%d columns not in COLUMN_MAP: %s", len(unmapped), unmapped)

    # Detect collisions: multiple source columns mapping to the same target
    from collections import defaultdict
    target_to_sources: dict[str, list[str]] = defaultdict(list)
    for src, tgt in rename.items():
        target_to_sources[tgt].append(src)
    for tgt, sources in target_to_sources.items():
        if len(sources) > 1:
            log.warning(
                "Duplicate target column %r: source columns %s will collide after rename",
                tgt, sources,
            )

    return rename


def load_appcoll_csv(warnings: list[str] | None = None) -> tuple[list[dict], dict]:
    """
    Load and normalize the AppColl CSV export.

    Returns
    -------
    (entries, meta)
        entries : list[dict]  — one dict per row, keys are Python field names
        meta    : dict        — {filename, modified, row_count}
    """
    if warnings is None:
        warnings = []

    csv_path = _find_csv(warnings)
    log.info("Loading CSV: %s", csv_path)

    try:
        df = pd.read_csv(
            csv_path,
            dtype=str,
            keep_default_na=False,
            low_memory=False,
            encoding="cp1252",
        )
    except UnicodeDecodeError:
        # cp1252 covers Windows-exported CSVs; latin-1 accepts every byte value
        df = pd.read_csv(
            csv_path,
            dtype=str,
            keep_default_na=False,
            low_memory=False,
            encoding="latin-1",
        )
    except Exception as exc:
        raise RuntimeError(f"Failed to read CSV {csv_path}: {exc}") from exc

    meta = {
        "filename": csv_path.name,
        "modified": datetime.fromtimestamp(csv_path.stat().st_mtime),
        "row_count": len(df),
    }
    log.info("CSV loaded: %d rows, %d columns", len(df), len(df.columns))

    # Build rename map and apply it
    rename_map = _build_column_rename_map(list(df.columns))
    df = df.rename(columns=rename_map)

    # Convert to list of dicts, then post-process each row
    raw_entries = df.to_dict(orient="records")
    entries: list[dict] = []

    for row in raw_entries:
        entry: dict = {}
        date_warn_fields: list[str] = []

        for key, raw_val in row.items():
            py_field = key  # already renamed (or kept as-is if unmapped)

            if py_field in DATE_FIELDS:
                parsed = _parse_date(raw_val)
                if raw_val and str(raw_val).strip().lower() not in ("", "nan", "none", "na") and parsed is None:
                    date_warn_fields.append(py_field)
                    warnings.append(
                        f"Could not parse date value {raw_val!r} for field {py_field!r}"
                    )
                    log.warning("Unparseable date: field=%r value=%r", py_field, raw_val)
                entry[py_field] = parsed
            elif py_field in NUMERIC_FIELDS:
                entry[py_field] = _parse_numeric(raw_val)
            else:
                entry[py_field] = _clean_str(raw_val)

        # Ensure document_number falls back to matter when empty
        if not entry.get("document_number"):
            entry["document_number"] = entry.get("matter")

        # Ensure client falls back to matter_client when empty
        if not entry.get("client"):
            entry["client"] = entry.get("matter_client")

        # Derive inventor email from responsible_inventor
        ri = entry.get("responsible_inventor")
        if ri and str(ri).strip().lower() not in ("", "nan", "none", "na"):
            ri = str(ri).strip()
            first = ri[0].lower()
            last = ri.split()[-1].lower()
            entry["email"] = f"{first}{last}@ofinno.com"
        else:
            entry["email"] = None

        entries.append(entry)

    log.info("Normalized %d entries", len(entries))
    return entries, meta
