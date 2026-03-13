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
import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from config.globals import (
    APPCOLL_CSV_DIR,
    USE_LATEST_CSV,
    APPCOLL_CSV_FILENAME,
    DATE_PARSE_FORMATS,
    OPEN_ENTRIES_ONLY,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Column mapping: normalized_csv_header -> python_field_name
# Normalized means: stripped of surrounding whitespace, lowercased.
# Matter-level fields keep the "matter." prefix when normalized.
# ---------------------------------------------------------------------------
COLUMN_MAP: dict[str, str] = {
    # --- Task-level fields ---
    "taskstatus": "task_status",
    "taskid": "task_id",
    "refdate": "ref_date",
    "modified": "modified",
    "tasktype": "entry_type",
    "creator": "creator",
    "owner": "owner",
    "client": "client",
    "matter": "matter",
    "document": "document_number",
    "respondby": "respond_by",
    "finalduedate": "final_due",
    "deadlinetype": "deadline_type",
    "closedon": "closed_on",
    "closedby": "closed_by",
    "comments": "comments",
    "actualexpense": "actual_expense",
    "actualcost": "actual_cost",
    "billwhencomplete": "bill_when_complete",
    "openedon": "open_date",
    "genbytaskid": "generated_by",
    "complexity": "complexity",
    "billingitems": "billing_items",
    "taskcode": "code",
    "expensecode": "expense_code",
    "activitycode": "activity",
    "discussion": "discussion",
    "budgethours": "budget_hours",
    "budgetexpense": "budget_expense",
    "budgetcost": "budget_cost",
    "feescap": "fees_cap",          # task-level; overridden by Matter.FeesCap if present
    "expensescap": "expenses_cap",
    # --- Matter-level fields ---
    "matter.matterid": "matter_id",
    "matter.title": "title",
    "matter.type": "matter_type",
    "matter.status": "matter_status",
    "matter.attorneyref": "attorney_ref",
    "matter.clientref": "client_ref",
    "matter.foreignassociateref": "foreign_associate_ref",
    "matter.confirmationnum": "confirmation_number",
    "matter.applicationnum": "application_number",
    "matter.publicationnum": "publication_number",
    "matter.patentnum": "patent_number",
    "matter.examiner": "examiner",
    "matter.artunit": "art_unit",
    "matter.country": "country_full",       # full name e.g. "United States"
    "matter.classification": "classification",
    "matter.usgovagency": "us_gov_agency",
    "matter.usgovcontractnum": "contract",
    "matter.ptostatus": "pto_status",
    "matter.plantlatinname": "plant_latin_name",
    "matter.plantvarietyname": "variety",
    "matter.plantnewcultivated": "new_cultivated_variety",
    "matter.nonpublication": "non_publication",
    "matter.earlypublication": "early_publication",
    "matter.createddate": "created_date",
    "matter.prioritydate": "priority_field",
    "matter.foreignfile": "foreign_file",
    "matter.plannedfilingdate": "planned_filing_date",
    "matter.filingdate": "filing_date",
    "matter.publicationdate": "publication_date",
    "matter.expectedfirstofficeactiondate": "first_office_action",
    "matter.allowancedate": "allowance_date",
    "matter.abandoneddate": "abandoned_date",
    "matter.issuedate": "issue_date",
    "matter.expireddate": "expiration_date",
    "matter.actualcost": "matter_actual_cost",
    "matter.intlsearchauth": "intl_search_auth",
    "matter.pphcountry": "pph_qualified",
    "matter.attorney": "lead_attorney",
    "matter.paralegal": "paralegal",
    "matter.foreignassociate": "foreign_associate",
    "matter.client": "matter_client",       # kept separate; merged into client below
    "matter.clientcontact": "client_contact",
    "matter.lawfirm": "law_firm",
    "matter.firstinventor": "first_inventor",
    "matter.inventors": "inventors",
    "matter.leadinventor": "lead_inventor",
    "matter.requestcontinuedexamination": "rce",
    "matter.modified": "matter_modified",
    "matter.notes": "notes",
    "matter.reelframe": "reel_frame",
    "matter.lastpairupdate": "last_pair_updated",
    "matter.terminaldisclaimer": "terminal_disclaimer",
    "matter.state": "state",
    "matter.goodsandservices": "goods_and_services",
    "matter.partner": "partner",
    "matter.contributor": "contributor",
    "matter.patenttermandjustment": "patent_term_adjustment",
    "matter.assignee": "assignee",
    "matter.officialfilingdate": "official_filing_date",
    "matter.image": "image",
    "matter.entitystatus": "entity_status",
    "matter.fasttrack": "fast_track",
    "matter.products": "products",
    "matter.keywords": "keywords",
    "matter.technologies": "technologies",
    "matter.familyid": "family_id",
    "matter.filingbasis": "basis",
    "matter.prioritymatter": "priority_matter",
    "matter.countrycode": "country",        # SHORT code e.g. "US", "EP" — used in rules
    "matter.connections": "connections",
    "matter.applicants": "applicants",
    "matter.adverseparties": "adverse_judgment",
    "matter.licensees": "license",
    "matter.nextexternaltaskduedate": "next_external_deadline",
    "matter.nextexternaltask": "next_external_task",
    "matter.trademarkregister": "trademark_registration",
    "matter.wipodaccesscode": "wipo_das_access",
    "matter.lastpatentoffice updatestatus": "last_patent_office_update_status",
    "matter.lastpatentofficeupdatestatus": "last_patent_office_update_status",
    "matter.lastpatentofficeupdatesource": "last_patent_office_update_source",
    "matter.lastpatentofficeupdatedate": "last_patent_office_update_date",
    "matter.numberofclaims": "number_of_claims",
    "matter.numberofindependentclaims": "independent_claims",
    "matter.submissiondate": "submission_date",
    "matter.reviveddate": "revival_date",
    "matter.ratecategory": "rate_category",
    "matter.complexity": "matter_complexity",
    "matter.opentaskcountexternal": "open_task_count_external",
    "matter.opentaskcountinternal": "open_task_count_internal",
    "matter.nextinternaltask": "next_internal_task",
    "matter.nextinternaltaskduedate": "next_internal_task_due",
    "matter.registrationnumberid": "registration_number_id",
    "matter.discussion": "matter_discussion",
    "matter.unitaryeffect": "unitary_effect",
    "matter.earliestbenefitdate": "earliest_benefit_date",
    "matter.billafterfiling": "bill_after_filing",
    "matter.billingcontact": "billing_contact",
    "matter.budgetcost": "matter_budget_cost",
    "matter.feescap": "fees_cap",           # matter-level overrides task-level
    "matter.expensescap": "matter_expenses_cap",
    "matter.relevantstandardsdocs": "relevant_standards_doc",
    "matter.portfolio": "portfolio",
    "matter.responsibleinventor": "responsible_inventor",
    "matter.sep": "sep_status",
    "matter.toyotaselection": "toyota_selection",
    "matter.philipsselection": "philips_status",
    "matter.filingtier": "tier",
    "matter.avancistatus": "avanci_status",
    "matter.standardscontribution": "standards_contribution",
    "matter.shortdescription": "short_description",
    "matter.pstrat": "psa",
    "matter.nonprovselection": "non_provisional_ref",
    "matter.technologycategory": "technology_category",
    "matter.patentfamily": "patent_family",
    "matter.standardversions": "version",
    "matter.comcastselection": "comcast",
    "matter.comcastmeeting": "comcast_meeting",
    "matter.philipsmeeting": "philips_meeting",
    "matter.licprojdate": "license_project",
    "matter.toyotameeting": "toyota_meeting",
}

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
    if not raw or str(raw).strip() in ("", "nan", "NaT", "None"):
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
    if raw is None or str(raw).strip() in ("", "nan", "None"):
        return None
    try:
        return float(str(raw).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _clean_str(raw) -> str | None:
    """Return stripped string or None if empty/NaN."""
    if raw is None:
        return None
    s = str(raw).strip()
    return s if s not in ("", "nan", "None", "NaT") else None


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

    for col in df_columns:
        norm = _normalize_key(col)
        if norm in COLUMN_MAP:
            rename[col] = COLUMN_MAP[norm]
        else:
            log.debug("Unknown CSV column (will be kept as-is): %r", col)
            unmapped.append(col)

    if unmapped:
        log.debug("%d columns not in COLUMN_MAP: %s", len(unmapped), unmapped)

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
        df = pd.read_csv(csv_path, dtype=str, keep_default_na=False, low_memory=False)
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
                if raw_val and str(raw_val).strip() not in ("", "nan", "None", "NaT") and parsed is None:
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

        entries.append(entry)

    log.info("Normalized %d entries", len(entries))
    return entries, meta
