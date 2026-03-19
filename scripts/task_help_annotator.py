# scripts/task_help_annotator.py
"""
Injects contextual help fields into each task based on task_help.yaml.

For each task in entry["_tasks"], looks up the task's help_key in
task_help.yaml and fetches the corresponding field values from the entry,
storing them as task["help_fields"] = {label: value}.

Fields with null/empty values are silently omitted.
"""

import logging
from pathlib import Path
from playwright.sync_api import sync_playwright

import yaml

log = logging.getLogger(__name__)

_TASK_HELP_PATH = Path(__file__).parent.parent / "config" / "task_help.yaml"

_URL_DIR = "../../data/session_data"
 



def get_internal_urls() -> dict[str, str]:
    # Adjust this path to where you want to save your session data
    user_data_dir = _URL_DIR

    internal_urls = {}
    
    with sync_playwright() as p:
        # Launch persistent context to reuse your logged-in session
        browser = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=True # Change to False the very first time to log in
        )
        
        page = browser.new_page()
        
        # 1. Navigate to the Hub
        log.info("Loading Ofinno Hub...")
        page.goto("https://ofinnotech.sharepoint.com/sites/OfinnoHub")
        
        # 2. Wait for the specific text to appear on the page
        target_text = "View & Schedule Weekly Prosecution Meeting →"
        link_locator = page.get_by_text(target_text)
        link_locator.wait_for(state="visible")
        
        # 3. Intercept the new tab that opens when clicked
        log.info("Clicking element and intercepting WPM URL...")
        with page.context.expect_page() as new_page_info:
            link_locator.click()
            
        # 4. Grab the URL from the intercepted tab
        new_page = new_page_info.value
        wpm_url = new_page.url
        
        log.info(f"Extracted WPM URL: {wpm_url}")

        target_text = "Schedule Final Claims Review Meeting →"
        link_locator = page.get_by_text(target_text)
        link_locator.wait_for(state="visible")

        log.info("Clicking element and intercepting FCR URL...")
        with page.context.expect_page() as new_page_info:
            link_locator.click()
        
        new_page = new_page_info.value
        fcr_url = new_page.url

        internal_urls["wpm_url"] = wpm_url
        internal_urls["fcr_url"] = fcr_url
        log.info(f"Extracted FCR URL: {fcr_url}")
        # Clean up
        new_page.close()
        browser.close()
        
        return internal_urls


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
        task["help_label"] = help_def.get("label", "")
        fields_def: list[dict] = help_def.get("fields", [])

        help_fields: dict[str, str] = {}
        for field_def in fields_def:
            py_field = field_def["field"]
            label = field_def["label"]
            value = entry.get(py_field)
            if value is None or str(value).strip() in ("", "nan", "None", "NaT"):
                continue
            help_fields[label] = str(value).strip()

        task["help_fields"] = help_fields
