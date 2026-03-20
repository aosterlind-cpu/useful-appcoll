# scripts/url_fetcher.py
"""
Headless browser automation to fetch dynamic URLs from the SharePoint hub.

Fetches two URLs used in task annotations:
  - wpm_url : Link to the Weekly Prosecution Meeting schedule (Dropbox)
  - fcr_url : Link to the Final Claims Review scheduling form (Forms.office.com)

Both URLs are embedded in the SharePoint page's spClientSidePageContext JavaScript
config block (not in the rendered DOM), so they are extracted by parsing page.content()
with regex after the page loads. No DOM interaction or popup interception is needed.

Requires:
  - playwright>=1.40.0  (pip install playwright && playwright install chromium)
  - Environment variables:
      SHAREPOINT_EMAIL    — Microsoft / SharePoint login email
      SHAREPOINT_PASSWORD — Microsoft / SharePoint login password

Browser context is persisted to data/sharepoint_context.json to skip the
login flow on subsequent runs.

On any failure, returns {"wpm_url": None, "fcr_url": None} so the pipeline
can continue without URL annotations.
"""

import logging
import os
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

log = logging.getLogger(__name__)

SHAREPOINT_URL = "https://ofinnotech.sharepoint.com/sites/OfinnoHub"
CONTEXT_FILE = Path("data/sharepoint_context.json")
SCREENSHOT_DIR = Path("debug")
TIMEOUT_MS = 30_000  # 30 seconds per action


def _screenshot(page, name: str) -> None:
    """Save a debug screenshot (best-effort; never raises)."""
    try:
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        path = SCREENSHOT_DIR / f"{name}.png"
        page.screenshot(path=str(path))
        log.info("Debug screenshot saved: %s", path)
    except Exception:  # noqa: BLE001
        log.warning("Could not save screenshot '%s'", name)


def _login(page) -> None:
    """
    Complete the Microsoft login flow.

    Page 1 — email prompt
    Page 2 — password prompt
    Page 3 — "Stay signed in?" prompt
    """
    # Page 1: enter email
    email_input = page.locator('input[type="email"][name="loginfmt"]').first
    email_input.wait_for(state="visible", timeout=TIMEOUT_MS)
    email_input.fill(os.environ["SHAREPOINT_EMAIL"])

    next_btn = page.locator('input[type="submit"][id="idSIButton9"]').first
    next_btn.wait_for(state="visible", timeout=TIMEOUT_MS)
    next_btn.click()

    # Page 2: enter password
    password_input = page.locator('input[type="password"][name="passwd"][id="i0118"]').first
    password_input.wait_for(state="visible", timeout=TIMEOUT_MS)
    password_input.fill(os.environ["SHAREPOINT_PASSWORD"])

    sign_in_btn = page.locator('input[type="submit"][id="idSIButton9"]').first
    sign_in_btn.wait_for(state="visible", timeout=TIMEOUT_MS)
    sign_in_btn.click()

    # Page 3: stay signed in
    try:
        yes_btn = page.locator('input[type="submit"][id="idSIButton9"][value="Yes"]').first
        yes_btn.wait_for(state="visible", timeout=10_000)
        yes_btn.click()
    except PlaywrightTimeoutError:
        # "Stay signed in" prompt may not appear in all flows
        log.debug("No 'Stay signed in' prompt detected; continuing.")

    page.wait_for_load_state("networkidle", timeout=TIMEOUT_MS)

    # If login redirected away from OfinnoHub, navigate back
    if "ofinnohub" not in page.url.lower():
        log.info("Redirected to %s after login; navigating back to hub.", page.url)
        page.goto(SHAREPOINT_URL, wait_until="networkidle")


def _extract_urls_from_html(html: str) -> dict[str, str | None]:
    """
    Parse the SharePoint page HTML and extract wpm_url and fcr_url from the
    spClientSidePageContext JavaScript config block.

    The URLs are stored as content[N].link key-value pairs in an escaped JSON
    blob injected into the page's <script> tag by SharePoint:
      - content[1].link = wpm_url  (Dropbox WPM schedule)
      - content[2].link = fcr_url  (Forms.office.com FCR form)

    Handles both escaped-quote (\\") and plain-quote (") variants.
    """
    result: dict[str, str | None] = {"wpm_url": None, "fcr_url": None}
    for key, n in (("wpm_url", 1), ("fcr_url", 2)):
        for pat in (
            rf'content\[{n}\]\.link\\\\":\\\\"(https://[^\\\\"]+)',  # double-escaped (\\" each)
            rf'content\[{n}\]\.link\\":\\"(https://[^\\"]+)',         # single-escaped (\" each)
            rf'content\[{n}\]\.link":"(https://[^"]+)',               # plain quotes
        ):
            m = re.search(pat, html)
            if m:
                result[key] = m.group(1)
                log.info("Extracted %s: %s", key, result[key])
                break
        if not result[key]:
            log.warning("Could not find content[%d].link in page HTML", n)
    return result


def fetch_urls() -> dict[str, str | None]:
    """
    Fetch wpm_url and fcr_url from the SharePoint hub.

    Returns a dict with keys "wpm_url" and "fcr_url".
    Values are None if the URL could not be retrieved.
    On any unrecoverable error, returns both as None so the pipeline continues.
    """
    email = os.environ.get("SHAREPOINT_EMAIL")
    password = os.environ.get("SHAREPOINT_PASSWORD")
    if not email or not password:
        log.warning(
            "SHAREPOINT_EMAIL and SHAREPOINT_PASSWORD are not set; "
            "skipping URL fetch — wpm_url and fcr_url will be absent from annotations."
        )
        return {"wpm_url": None, "fcr_url": None}

    result: dict[str, str | None] = {"wpm_url": None, "fcr_url": None}

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)

            # Load saved context if available to skip login
            CONTEXT_FILE.parent.mkdir(parents=True, exist_ok=True)
            if CONTEXT_FILE.exists():
                log.info("Loading saved browser context from %s", CONTEXT_FILE)
                context = browser.new_context(storage_state=str(CONTEXT_FILE))
            else:
                context = browser.new_context()

            page = context.new_page()
            page.set_default_timeout(TIMEOUT_MS)

            # Intercept the raw HTTP response body before JavaScript can
            # remove the <script> tag containing the SPFx config data.
            _raw_html: list[str] = []

            def _on_response(response) -> None:
                if (not _raw_html
                        and "OfinnoHub" in response.url
                        and response.request.resource_type == "document"):
                    try:
                        _raw_html.append(
                            response.body().decode("utf-8", errors="replace")
                        )
                    except Exception:  # noqa: BLE001
                        pass

            page.on("response", _on_response)

            try:
                log.info("Navigating to SharePoint hub: %s", SHAREPOINT_URL)
                page.goto(SHAREPOINT_URL, wait_until="networkidle")

                # Login if redirected to Microsoft login page
                if "login.microsoftonline.com" in page.url or "login.microsoft.com" in page.url:
                    log.info("Login required; completing Microsoft login flow.")
                    _login(page)
                    # Re-navigate so response interception fires on the
                    # authenticated OfinnoHub response
                    _raw_html.clear()
                    page.goto(SHAREPOINT_URL, wait_until="networkidle")

                # Save context after successful authentication
                context.storage_state(path=str(CONTEXT_FILE))
                log.info("Browser context saved to %s", CONTEXT_FILE)

                # Use intercepted raw response (pre-JS) or fall back to DOM
                html = _raw_html[0] if _raw_html else page.content()
                html_source = "response interception" if _raw_html else "page.content()"

                # --- Diagnostics ---
                log.info("page.url after load: %s", page.url)
                log.info("HTML source: %s (%d chars)", html_source, len(html))
                log.info(
                    "'content[1].link' substring present: %s",
                    "content[1].link" in html,
                )
                # Dump raw HTML for inspection
                SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
                debug_html_path = SCREENSHOT_DIR / "url_fetcher_response.html"
                debug_html_path.write_text(html, encoding="utf-8", errors="replace")
                log.info("Raw HTML saved to %s", debug_html_path)
                # --- End diagnostics ---

                result.update(_extract_urls_from_html(html))

            except Exception:
                _screenshot(page, "url_fetcher_unhandled_error")
                raise
            finally:
                context.close()
                browser.close()

    except Exception as exc:  # noqa: BLE001
        log.error(
            "URL fetch failed (%s); wpm_url and fcr_url will be absent from annotations.", exc
        )

    log.info("fetch_urls result: %s", result)
    return result


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )
    print(fetch_urls())
