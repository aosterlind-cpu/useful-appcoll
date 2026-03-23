# scripts/output_formatter.py
"""
Builds the final Markdown output string from scored, task-enriched entries.
"""

import logging
from datetime import date, datetime, timedelta

from config.globals import TASK_GENERATION_THRESHOLD

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_date(d) -> str:
    if d is None:
        return "N/A"
    if isinstance(d, date):
        return f"{d.month}/{d.day}/{d.year}"
    return str(d)

def _short_date(d, today) -> str:
    if d is None:
        return ""
    return f" {d.month}/{d.day} " if isinstance(d, date) else str(d)


def _days_remaining_str(deadline: date | None, today: date) -> str:
    if deadline is None:
        return ""
    delta = (deadline - today).days
    if delta < 0:
        return f"Overdue by {abs(delta)} days"
    if delta == 0:
        return "**Due today**"
    return f"*{delta} day{'s' if delta != 1 else ''} remaining*"


def _entry_header_flag(entry: dict, today: date) -> str:
    deadline = entry.get("_effective_deadline")
    if deadline is None:
        return ""
    if deadline <= today:
        return " \u00b7 Overdue"
    days = (deadline - today).days
    return f" \u00b7 {days} day{'s' if days != 1 else ''} remaining"

def _is_matter_overdue(entry: dict, today: date) -> bool:
    respond_by = entry.get("respond_by")
    finale_due = entry.get("final_due")

    if (respond_by and respond_by < today) or (finale_due and finale_due < today):
        return True
    return False


def _build_file_header(today: date, csv_meta: dict) -> str:
    iso_date = today.strftime("%Y-%m-%d")
    display_date = _fmt_date(today)
    csv_name = csv_meta.get("filename", "unknown")
    csv_mod = csv_meta.get("modified")
    if isinstance(csv_mod, datetime):
        csv_mod_str = csv_mod.strftime("%Y-%m-%d %H:%M UTC")
    else:
        csv_mod_str = str(csv_mod) if csv_mod else "unknown"

    return (
        f"---\n"
        f"date: {iso_date}\n"
        f"tags: [docket, patent, daily-review]\n"
        f"aliases: [Daily Docket {iso_date}]\n"
        f"---\n\n"
        f"# Docket Report \u2014 {display_date}\n\n"
        f"> AppColl CSV `{csv_name}`, exported on `{csv_mod_str}`\n\n"
        f"---\n"
    )


def _build_todays_todo(entries: list[dict], today: date) -> str:
    date_str = _fmt_date(today)
    lines: list[str] = [
        f"\n## Docket Report \u2014 {date_str}\n",
    ]

    # Filing deadlines due today
    deadline_rows = []
    for entry in entries:
        dl = entry.get("_effective_deadline")
        if dl == today:
            deadline_rows.append(entry)
        elif _is_matter_overdue(entry, today):
            deadline_rows.append(entry)

    lines.append("\n### Priority Docket Entries\n")
    if deadline_rows:
        lines.append("| Due | Matter No. | Docket Entry | Pub No. | SEP |")
        lines.append("|---|---|---|---|---|")
        for e in deadline_rows:
            

            link = f"[[#^[{e.get('_priority_number', 0)}] {e.get('matter', 'N/A')}"
            link += f" \u00b7 {e.get('task_type', 'N/A')}"
            link += f"\\|{e.get('task_type', 'N/A')}]]"

            if e.get("publication_number") and e.get("publication_number") is not None:
                pub_link = f"[{e.get('publication_number', 'N/A')}]"
                pub_link += f"(https://patents.google.com/patent/{e.get('country', '')}{str(e.get('publication_number', '')).replace('/', '')})"
            else:
                pub_link = "*none*"

            lines.append(
                f"| {_short_date(e.get('respond_by'), today)} "
                f"| {e.get('matter', '*none*')} "
                f"| {link} "
                f"| {pub_link} "
                f"| {e.get('sep_status', '*none*') or '*none*'} "
            )
    else:
        lines.append("_No filing deadlines due today._")

    # Tasks due today
    task_rows = []
    for entry in entries:
        for task in entry.get("_tasks", []):
            if task.get("target_date") <= today + timedelta(days=1) and not task.get("_completed"):
                task_rows.append((entry, task))

    lines.append("\n### Docket Entry Priority Tasks\n")
    if task_rows:
        lines.append("| Due | # | Task | Matter No. | Docket Entry |")
        lines.append("|---|---|---|---|---|")
        for e, t in task_rows:
            name_link = f"[[#^{str(t['subpriority']).replace('.', '-')}\\|{t['display_name']}]]"
            sp_link = f"[[#^{str(t['subpriority']).replace('.', '-')}\\|{t['subpriority']}]]"
            lines.append(
                f"| {_short_date(t['target_date'], today)} "
                f"| {sp_link} "
                f"| {name_link} "
                f"| {e.get('matter', 'N/A')} "
                f"| {e.get('task_type', 'N/A')} |"    
            )
    else:
        lines.append("_No tasks due today._")

    lines.append("\n---")
    return "\n".join(lines)


def _build_task_block(task: dict, today: date) -> str:
    """Build the Markdown block for a single task."""
    lines: list[str] = []
    sp = task["subpriority"]
    td = _fmt_date(task.get("target_date"))
    display = task["display_name"]

    # Checkbox first
    checkbox = "- [x]" if task.get("_completed") else "- [ ]"
    lines.append(f"{checkbox} **{display}**")

    # Due date + overdue info on next line
    due_line = f"  *Due: {td}"
    if task.get("is_overdue"):
        orig = _fmt_date(task.get("original_target_date"))
        due_line += f" \u2014 *Overdue ({orig})*"
    due_line += "*   "
    due_line += f"   \u005e{str(sp).replace('.', '-')}"
    lines.append(due_line)

    # Help fields
    help_label = task.get("help_label", "") or ""
    help_fields: dict = task.get("help_fields", {})
    if help_fields:
        lines.append("")
        if help_label and help_label.strip() != "":
            lines.append(f"> **{help_label}**  ")
        for label, value in help_fields.items():
            lines.append(f">     - **{label}**: {value}  ")

    lines.append("")

    return "\n".join(lines)


def _build_entry_block(entry: dict, today: date) -> str:
    """Build the full Markdown block for one docket entry."""
    number = entry.get("_priority_number", 0)
    matter = entry.get("matter", "N/A")
    deadline = entry.get("_effective_deadline")
    respond_by = entry.get("respond_by") or deadline
    days_str = _days_remaining_str(respond_by, today)
    header_flag = _entry_header_flag(entry, today)

    lines: list[str] = []

    header_parts = []
    if not matter or str(matter).strip() == "":
        matter = "*none*"
    header_parts.append(f"{matter}")
    entry_type = entry.get("task_type", "") or ""
    if not entry_type or str(entry_type).strip() == "":
        entry_type = "*none*"
    header_parts.append(f"{entry_type}")

    lines.append(f"\n### [{number}] \u00b7 {' \u00b7 '.join(header_parts)}")

    app_parts = []

    title = entry.get("title", "") or ""
    if title:
        lines.append(f"**Title**: {title}  ")

    app_num = entry.get("application_number", "") or ""
    if not app_num or str(app_num).strip() == "":
        app_num = "*none*"
    app_parts.append(f"**Appn #**: {app_num}")
    pub_number = entry.get("publication_number", "") or ""
    if not pub_number or str(pub_number).strip() == "":
        pub_number = "*none*"
    app_parts.append(f"**Pub #**: {pub_number}  ")

    lines.append("  \u00b7  ".join(app_parts) + "  ")

    # SEP Status, PStrat, Avanci on one line
    parts = []
    
    sep = entry.get("sep_status") or ""
    if sep and isinstance(sep, str) and sep.strip() != "":
        sep = sep.strip()
    else:
        sep = "_none_"
    parts.append(f"**SEP Status**: {sep}")
    
    psa = entry.get("psa") or ""
    if psa and isinstance(psa, str) and psa.strip() != "":
        psa = psa.strip()
    else:
        psa = "_none_"
    parts.append(f"**PStrat**: {psa}")

    avanci = entry.get("avanci_status") or ""
    if avanci and isinstance(avanci, str) and avanci.strip() != "":
        avanci = avanci.strip()
    else:
        avanci = "_none_"
    parts.append(f"**Avanci**: {avanci}")

    lines.append("  \u00b7  ".join(parts) + "  ")

    lines.append("  \u2014  ")

    due_parts = []
    if "overdue" in days_str.lower() or "today" in days_str.lower():
        due_parts.append("\u26A0 ")
    due_parts.append(f"**Due Date**: {_fmt_date(respond_by)} (next) ")
    final_due = entry.get("final_due") 
    if final_due:
        due_parts.append(f" {_fmt_date(final_due)} (final)  ")
    lines.append("  \u00b7  ".join(due_parts) + "  ")
    lines.append(f"{days_str}")

    next_external = entry.get("next_external_task", "") or ""
    next_external = next_external.replace("|", "/")
    next_external = next_external.replace("*", "")
    next_external = next_external.replace(" -", " ")

    next_internal = entry.get("next_internal_task", "") or ""
    next_internal = next_internal.replace("|", "/")
    next_internal = next_internal.replace("*", "")
    next_internal = next_internal.replace(" -", " ")

    if (next_external and str(next_external).strip() != "") or (next_internal and str(next_internal).strip() != ""):
        lines.append("  \u2014  ")
    
    if next_external and str(next_external).strip() != "":
        truncated = next_external.strip()[:100] + ("..." if len(next_external.strip()) > 100 else "")
        truncated = truncated.replace("|", "/")
        truncated = truncated.replace("*", "")
        truncated = truncated.replace(" -", " ")
        lines.append(f"**External Next**: {truncated}  ")

    if next_internal and str(next_internal).strip() != "":
        truncated = next_internal.strip()[:100] + ("..." if len(next_internal.strip()) > 100 else "")
        lines.append(f"**Internal Next**: {truncated}  ")

    notes = entry.get("notes", "") or ""
    comments = entry.get("comments", "") or ""

    if (notes and str(notes).strip() != "") or (comments and str(comments).strip() != ""):
        lines.append("  \u2014  ")

    if notes and str(notes).strip() != "":
        notes = notes.replace("|", "/")
        notes = notes.replace("*", "")
        notes = notes.replace(" -", " ")
        truncated = notes.strip()[:100] + ("..." if len(notes.strip()) > 100 else "")
        lines.append(f"**Notes**: {truncated}  ")

    if comments and str(comments).strip() != "":
        comments = comments.replace("|", "/")
        comments = comments.replace("*", "")
        comments = comments.replace(" -", " ")
        truncated = comments.strip()[:100] + ("..." if len(comments.strip()) > 100 else "")
        lines.append(f"**Comments**: {truncated}  ")

    tasks: list[dict] = entry.get("_tasks", [])
    if tasks:
        lines.append("#### Tasks \n")
        for task in tasks:
            lines.append(_build_task_block(task, today))

    return "\n".join(lines)


def _build_priority_section(entries: list[dict], today: date) -> str:
    threshold = TASK_GENERATION_THRESHOLD
    priority_entries = [e for e in entries if e.get("_priority_score", 0) >= threshold]

    lines: list[str] = [
        "\n## Priority Docket Entries\n",
        "---",
    ]

    if not priority_entries:
        lines.append("_No entries meet the priority threshold today._")
    else:
        for entry in priority_entries:
            lines.append(_build_entry_block(entry, today))
            lines.append("\n\n---\n")


    return " ".join(lines)


def _build_monitored_section(entries: list[dict], today: date) -> str:
    threshold = TASK_GENERATION_THRESHOLD
    monitored = [e for e in entries if e.get("_priority_score", 0) < threshold
                 and e.get("_priority_score", 0) > 0]

    lines: list[str] = [
        "\n---\n",
        "## Monitored Entries (Below Task Threshold)\n",
        "> No tasks generated yet. Watch deadlines.\n",
    ]

    if monitored:
        lines.append("| Docket No. | Type | Application No. | Country | Due Date | Days Remaining |")
        lines.append("|---|---|---|---|---|---|")
        for e in monitored:
            deadline = e.get("_effective_deadline")
            days_r = (deadline - today).days if deadline else None
            days_display = str(days_r) if days_r is not None else "N/A"
            country = e.get("country") or e.get("country_full", "N/A")
            lines.append(
                f"| {e.get('matter', 'N/A')} "
                f"| {e.get('task_type', 'N/A')} "
                f"| {e.get('application_number', 'N/A')} "
                f"| {country} "
                f"| {_fmt_date(deadline)} "
                f"| {days_display} |"
            )
    else:
        lines.append("_No entries in the monitored range today._")

    lines.append("\n---")
    lines.append("_End of report._")
    return "\n".join(lines)


def _build_warnings_section(warnings: list[str]) -> str:
    if not warnings:
        return ""
    lines = ["\n---\n", "## Report Warnings\n"]
    for w in warnings:
        lines.append(f"- {w}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_markdown(
    entries: list[dict],
    today: date,
    csv_meta: dict,
    warnings: list[str] | None = None,
) -> str:
    """
    Build the complete Markdown report string.

    Parameters
    ----------
    entries  : list of scored, task-enriched entry dicts
    today    : reference date
    csv_meta : metadata dict from csv_loader
    warnings : list of warning strings accumulated during the run
    """
    if warnings is None:
        warnings = []

    parts = [
        _build_file_header(today, csv_meta),
        _build_todays_todo(entries, today),
        _build_priority_section(entries, today),
        _build_monitored_section(entries, today),
    ]
    if warnings:
        parts.append(_build_warnings_section(warnings))

    return "\n".join(parts) + "\n"
