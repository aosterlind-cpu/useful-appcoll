# scripts/appcoll_downloader.py
"""
Headless browser automation to log into AppColl and download the Tasks CSV export.

Requires:
  - playwright>=1.40.0  (pip install playwright && playwright install chromium)
  - Environment variables:
      APPCOLL_EMAIL     — AppColl login email address
      APPCOLL_PASSWORD  — AppColl login password

Downloads the CSV to:
  data/appcoll_exports/appcoll_export_YYYY-MM-DD.csv

On any failure, saves debug screenshots to debug_screenshots/.
"""

import logging
import os
import sys
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

log = logging.getLogger(__name__)

LOGIN_URL = "https://login.appcoll.com/"
TASKS_URL = "https://login.appcoll.com/Tasks.aspx?islogin=1"
DOWNLOAD_DIR = Path("data/appcoll_exports")
SCREENSHOT_DIR = Path("debug")
TIMEOUT_MS = 30_000  # 30 seconds per action

# Selector lists — tried in order; first match wins.
EMAIL_SELECTORS = [
    'input[type="text"]',
    'input[name="LoginBox$UserName"]',
    'input[id="LoginBox_UserName"]',
    'input[placeholder*="Username" i]',
    'input[autocomplete="email"]',
]

PASSWORD_SELECTORS = [
    'input[type="password"]',
    'input[name="LoginBox$Password"]',
    'input[id="LoginBox_Password"]',
    'input[placeholder*="Password" i]',
]

LOGIN_BUTTON_SELECTORS = [
    'button[type="submit"]',
    'input[type="submit"]',
    'input[name="LoginBox$LoginButton"]',
    'input[id="LoginBox_LoginButton"]',
    'input[value="Login"]',
    'button:has-text("Log in")',
    'button:has-text("Login")',
    'button:has-text("Sign in")',
    'a:has-text("Log in")',
]

EXPORT_BUTTON_SELECTORS = [
    # Telerik RadGrid / standard grid export buttons
    'input[title*="Export information to CSV file" i]',
    'input[title*="Export" i]',
    'a[title*="CSV" i]',
    'a[title*="Export" i]',
    'button[title*="CSV" i]',
    'button[title*="Export" i]',
    # Image-based toolbar buttons (common in older ASP.NET apps)
    'img[title*="Export information to CSV file" i]',
    'img[name="ctl00$ExportButton"]',
    'img[id="ctl00_ExportButton"]',
    'img[title*="Export" i]',
    'img[alt*="CSV" i]',
    'img[alt*="Export" i]',
    # Text-based fallbacks
    'a:has-text("CSV")',
    'button:has-text("Export")',
    'a:has-text("Export")',
]


def _screenshot(page, name: str) -> None:
    """Save a debug screenshot (best-effort; never raises)."""
    try:
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        path = SCREENSHOT_DIR / f"{name}.png"
        page.screenshot(path=str(path))
        log.info("Debug screenshot saved: %s", path)
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not save screenshot '%s': %s", name, exc)


def _click_first_matching(page, selectors: list[str], description: str):
    """
    Try each selector in order and click the first visible match.
    Raises RuntimeError if nothing matched.
    """
    for sel in selectors:
        try:
            locator = page.locator(sel).first
            locator.wait_for(state="visible", timeout=3_000)
            locator.click()
            log.info("Clicked %s using selector: %s", description, sel)
            return sel
        except Exception:  # noqa: BLE001
            continue
    raise RuntimeError(
        f"Could not find {description}. Tried selectors: {selectors}"
    )


def _fill_first_matching(page, selectors: list[str], value: str, description: str):
    """Fill the first visible input that matches any selector."""
    for sel in selectors:
        try:
            locator = page.locator(sel).first
            locator.wait_for(state="visible", timeout=3_000)
            locator.fill(value)
            log.info("Filled %s using selector: %s", description, sel)
            return sel
        except Exception:  # noqa: BLE001
            continue
    raise RuntimeError(
        f"Could not find {description}. Tried selectors: {selectors}"
    )


def download_appcoll_csv() -> Path:
    """
    Log into AppColl, navigate to Tasks.aspx, click the CSV export button,
    intercept the download, and save the file.

    Returns the Path of the saved CSV file.
    Raises RuntimeError on any failure (caller should treat as fatal).
    """
    email = os.environ.get("APPCOLL_EMAIL")
    password = os.environ.get("APPCOLL_PASSWORD")
    if not email or not password:
        raise RuntimeError(
            "APPCOLL_EMAIL and APPCOLL_PASSWORD environment variables must be set."
        )

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    today_str = date.today().strftime("%Y-%m-%d")
    dest_path = DOWNLOAD_DIR / f"appcoll_export_{today_str}.csv"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.set_default_timeout(TIMEOUT_MS)

        try:
            # Step 1 — Load login page
            log.info("Navigating to login page: %s", LOGIN_URL)
            page.goto(LOGIN_URL, wait_until="networkidle")

            # Step 2 — Fill credentials
            try:
                _fill_first_matching(page, EMAIL_SELECTORS, email, "email field")
                _fill_first_matching(page, PASSWORD_SELECTORS, password, "password field")
            except RuntimeError:
                _screenshot(page, "login_page_error")
                raise

            # Step 3 — Submit login
            try:
                _click_first_matching(page, LOGIN_BUTTON_SELECTORS, "login button")
            except RuntimeError:
                _screenshot(page, "login_button_error")
                raise

            # Wait for navigation after login
            try:
                page.wait_for_load_state("networkidle", timeout=TIMEOUT_MS)
            except PlaywrightTimeoutError:
                _screenshot(page, "post_login_timeout")
                raise RuntimeError("Timed out waiting for page after login submit.")

            # Verify we're no longer on the login page (basic auth check)
            current_url = page.url
            log.info("Post-login URL: %s", current_url)
            if "login.appcoll.com" in current_url and current_url.rstrip("/") == LOGIN_URL.rstrip("/"):
                _screenshot(page, "login_failed")
                raise RuntimeError(
                    "Login appears to have failed — still on login page after submit."
                )

            # Step 4 — Navigate to Tasks.aspx
            log.info("Navigating to Tasks page: %s", TASKS_URL)
            page.goto(TASKS_URL, wait_until="networkidle")

            # Step 5 — Click the export button to open the export popup
            log.info("Looking for CSV export button...")
            try:
                _click_first_matching(page, EXPORT_BUTTON_SELECTORS, "CSV export button")
            except RuntimeError:
                _screenshot(page, "export_button_error")
                raise

            # Step 5b — Confirm in the export popup and intercept the download.
            #
            # Clicking the export button opens a modal with:
            #   File Type:  "AppColl Tasks (CSV)"  (default — leave as-is)
            #   Export:     "Visible information only"  (default — leave as-is)
            #
            # The confirm button is:
            #   <input type="submit" id="ctl00_ExportOk"
            #          name="ctl00$ExportOk" onclick="onExportButtonClick(event);">
            log.info("Waiting for export popup confirm button...")
            try:
                with page.expect_download(timeout=TIMEOUT_MS) as dl_info:
                    popup_btn = page.locator('input[id="ctl00_ExportOk"]').first
                    popup_btn.wait_for(state="visible", timeout=TIMEOUT_MS)
                    popup_btn.click()
                download = dl_info.value
            except PlaywrightTimeoutError:
                _screenshot(page, "popup_export_timeout")
                raise RuntimeError(
                    "Timed out waiting for export popup or CSV download after clicking confirm."
                )

            # Step 6 — Save to destination
            download.save_as(str(dest_path))
            log.info("CSV saved to: %s", dest_path)

        except Exception:
            # Catch-all: screenshot and re-raise so caller gets a clean error
            _screenshot(page, "unhandled_error")
            raise
        finally:
            context.close()
            browser.close()

    return dest_path


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )
    try:
        saved = download_appcoll_csv()
        print(f"Downloaded: {saved}")
    except Exception as exc:
        log.error("Download failed: %s", exc)
        sys.exit(1)
