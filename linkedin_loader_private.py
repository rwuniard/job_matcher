import logging
import re
import threading
from dataclasses import dataclass, field
from playwright.sync_api import sync_playwright, BrowserContext, Page

logger = logging.getLogger(__name__)

SESSION_DIR = "./linkedin_session"

# Chromium locks its user-data-dir; only one browser instance can hold it at a time.
# This lock serializes all get_linkedin_job calls so concurrent threads don't
# race on the shared session directory.
_playwright_lock = threading.Lock()

# Authwall indicators — LinkedIn redirects here when the session has expired
_AUTHWALL_PATHS = ("/authwall", "/login", "/signup", "/uas/login")


@dataclass
class LinkedInJob:
    title: str
    description: str
    status: str  # "open", "applied", "closed"
    location: str = field(default="")  # e.g. "Atlanta, GA (On-site)"


class LinkedInSessionExpiredError(RuntimeError):
    """Raised when the LinkedIn session cookie is missing or the page redirects to the auth wall."""


def _check_session(browser: BrowserContext, page: Page) -> None:
    """Raise LinkedInSessionExpiredError if the session appears to have expired."""
    cookies = browser.cookies()
    has_auth_cookie = any(c["name"] == "li_at" for c in cookies)
    on_authwall = any(page.url.startswith(f"https://www.linkedin.com{path}") for path in _AUTHWALL_PATHS)

    if not has_auth_cookie or on_authwall:
        logger.error(
            "LinkedIn session has expired (li_at cookie present: %s, redirected to auth wall: %s). "
            "Re-run with first_login=True to refresh the session.",
            has_auth_cookie,
            on_authwall,
        )
        raise LinkedInSessionExpiredError(
            "LinkedIn session has expired. Re-run with first_login=True to log in again."
        )


def _location_from_json_ld(page: Page) -> tuple[str, str]:
    """
    Extract job location from JSON-LD structured data embedded in the page.

    LinkedIn includes schema.org JobPosting markup for Google Jobs integration.
    This is far more stable than CSS class names, which change with every UI redesign.

    Returns:
        (place, workplace_type) — e.g. ("Arlington, VA", "Remote") or ("", "")
        workplace_type is "Remote" when jobLocationType is TELECOMMUTE; otherwise ""
        because On-site / Hybrid are not reliably encoded in the schema.
    """
    try:
        ld_data = page.evaluate("""
            () => {
                for (const el of document.querySelectorAll('script[type="application/ld+json"]')) {
                    try {
                        const d = JSON.parse(el.textContent);
                        if (d['@type'] === 'JobPosting') return d;
                    } catch (e) {}
                }
                return null;
            }
        """)
    except Exception:
        return "", ""

    if not isinstance(ld_data, dict):
        return "", ""

    job_loc = ld_data.get("jobLocation")
    if isinstance(job_loc, list):
        job_loc = job_loc[0] if job_loc else {}
    addr = job_loc.get("address", {}) if isinstance(job_loc, dict) else {}
    city = addr.get("addressLocality", "").strip()
    region = addr.get("addressRegion", "").strip()
    place = f"{city}, {region}" if city and region else city or region

    is_remote = ld_data.get("jobLocationType", "").upper() == "TELECOMMUTE"
    return place, ("Remote" if is_remote else "")


def get_linkedin_job(url: str, first_login: bool = False) -> LinkedInJob:
    """
    Load a LinkedIn job posting using Playwright.
    This is for private LinkedIn pages, so we need to log in to LinkedIn.
    The session is saved to ./linkedin_session/ directory.

    Args:
        url: LinkedIn job URL
        first_login: Set True for first run to manually log in

    Returns:
        LinkedInJob with title, description, and application status

    Raises:
        LinkedInSessionExpiredError: If the session has expired and first_login is False.
    """
    with _playwright_lock:
        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=SESSION_DIR,
                headless=not first_login
            )
            page = browser.pages[0] if browser.pages else browser.new_page()

            page.goto(url, wait_until="domcontentloaded")

            if first_login:
                print("Please log in to LinkedIn in the browser window...")
                input("Press Enter after logging in and the job page has loaded...")
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)

            _check_session(browser, page)

            # Wait for the job content column — stable across LinkedIn redesigns
            page.wait_for_selector("[data-testid='lazy-column']", timeout=30000)
            page.wait_for_timeout(1000)

            # Wait for the description section to appear (LinkedIn can be slow loading it).
            # Tries each known selector; moves on if none appear within 15 s.
            _desc_wait_selectors = [
                "[data-sdui-component*='aboutTheJob']",
                "#job-details",
                ".jobs-description__content",
                ".jobs-description-content__text",
                "[data-testid='expandable-text-box']",
            ]
            for _sel in _desc_wait_selectors:
                try:
                    page.wait_for_selector(_sel, timeout=15000)
                    break
                except Exception:
                    continue

            # Extract job title from the page <title> tag: "Job Title | Company | LinkedIn"
            # This is far more stable than any DOM class or SDUI component name.
            raw_title = page.title()
            title = raw_title.split(" | ")[0].strip() if " | " in raw_title else raw_title.strip()

            # --- Location extraction (three-tier, most stable first) ---
            #
            # Tier 1: JSON-LD structured data  — LinkedIn maintains this for Google Jobs;
            #         city/state is reliable here regardless of UI redesigns.
            # Tier 2: CSS selectors             — works while the class names are stable.
            # Tier 3: Regex on top-card text    — last resort; brittle but broad.
            #
            # Rule: JSON-LD city always wins if present. Workplace type (On-site/Hybrid)
            # comes from CSS/regex because schema.org only encodes TELECOMMUTE (Remote).

            ld_place, ld_workplace = _location_from_json_ld(page)
            logger.debug("JSON-LD location: place=%r workplace_type=%r", ld_place, ld_workplace)

            location = ""

            # Tier 1 short-circuit: JSON-LD has both city and Remote → done.
            if ld_place and ld_workplace:
                location = f"{ld_place} ({ld_workplace})"

            # Tier 2: CSS selectors.
            # Even when JSON-LD gave us a city, run CSS to pick up On-site / Hybrid.
            if not location:
                _location_selectors = [
                    ".job-details-jobs-unified-top-card__primary-description-without-tagline",
                    ".job-details-jobs-unified-top-card__primary-description",
                    ".jobs-unified-top-card__primary-description",
                    ".jobs-unified-top-card__workplace-type",
                ]
                for _sel in _location_selectors:
                    _elem = page.locator(_sel).first
                    if _elem.count() > 0:
                        _text = _elem.inner_text().strip()
                        if _text:
                            if ld_place:
                                # Substitute the JSON-LD city for whatever city CSS found
                                # (CSS may return country-level, e.g. "United States (Remote)")
                                _wt = re.search(r'\b(On-site|Hybrid|Remote)\b', _text, re.IGNORECASE)
                                location = f"{ld_place} ({_wt.group(1)})" if _wt else ld_place
                            else:
                                location = _text
                            break

            # Tier 3: Regex on scoped top-card text.
            if not location:
                _top_card_selectors = [
                    "[data-testid='lazy-column']",
                    ".job-details-jobs-unified-top-card__container",
                    ".jobs-unified-top-card",
                ]
                _search_text = ""
                for _sel in _top_card_selectors:
                    _elem = page.locator(_sel).first
                    if _elem.count() > 0:
                        _search_text = _elem.inner_text().strip()
                        if _search_text:
                            break
                if not _search_text:
                    _search_text = page.locator("body").inner_text()

                _wt_match = re.search(r'\b(On-site|Hybrid|Remote)\b', _search_text, re.IGNORECASE)
                if _wt_match:
                    workplace_type = _wt_match.group(1)
                    if ld_place:
                        location = f"{ld_place} ({workplace_type})"
                    else:
                        _separator_only = re.compile(r'^[\s\u00b7\u2022\-\(]+$')
                        _city_state_re = re.compile(r'^[A-Z][^·\n]+,\s*[A-Z]')
                        _lines_before = _search_text[:_wt_match.start()].splitlines()
                        preceding = ""
                        first_non_sep = ""
                        for _line in reversed(_lines_before):
                            _candidate = re.sub(r'[\s\u00b7\u2022\-\(]+$', '', _line).strip()
                            if _candidate and not _separator_only.match(_line.strip()):
                                if not first_non_sep:
                                    first_non_sep = _candidate
                                if _city_state_re.match(_candidate):
                                    preceding = _candidate
                                    break
                        if not preceding:
                            preceding = first_non_sep
                        location = f"{preceding} ({workplace_type})" if preceding else workplace_type

            # Final safety net: JSON-LD had a city but no workplace type resolved anywhere
            if not location and ld_place:
                location = ld_place

            # Detect application status — full page text is the most reliable fallback
            # because LinkedIn frequently renames CSS classes and SDUI components.
            page_text_raw = page.locator("body").inner_text()
            page_text = page_text_raw.lower()

            if "no longer accepting applications" in page_text:
                status = "closed"
            elif "application submitted" in page_text or "practice an interview" in page_text:
                status = "applied"
            else:
                status = "open"

            # Expand the "About the job" description.
            # Try the SDUI component first; fall back to any "see more" button near the description.
            description = ""

            sdui_section = page.locator(
                "[data-sdui-component*='aboutTheJob']"
            )
            if sdui_section.count() > 0:
                see_more = sdui_section.locator("button").filter(has_text="more")
                if see_more.count() > 0:
                    see_more.first.evaluate("el => el.click()")
                    page.wait_for_timeout(500)
                description = sdui_section.inner_text().strip()

            if not description:
                # Fallback: look for any element whose id or class suggests it holds the description
                fallback_selectors = [
                    "#job-details",
                    ".jobs-description__content",
                    ".jobs-description-content__text",
                    "[data-testid='expandable-text-box']",
                ]
                for selector in fallback_selectors:
                    elem = page.locator(selector).first
                    if elem.count() > 0:
                        # Try to expand first
                        see_more = elem.locator("button").filter(has_text="more")
                        if see_more.count() > 0:
                            see_more.first.evaluate("el => el.click()")
                            page.wait_for_timeout(500)
                        description = elem.inner_text().strip()
                        if description:
                            break

            if not description:
                logger.warning("Could not extract job description for %s — page structure may have changed.", url)

            browser.close()
            return LinkedInJob(title=title, description=description, status=status, location=location)


def main():
    job_url = "https://www.linkedin.com/jobs/view/4375302812/" # job applied
    #job_url = "https://www.linkedin.com/jobs/view/4365010800/" # job no longer accepting applications
    #job_url = "https://www.linkedin.com/jobs/view/4374040129/" # job open

    # First run: set first_login=True to log in manually
    # After that: set first_login=False (session is saved)
    job = get_linkedin_job(job_url, first_login=False)

    print(f"Title: {job.title}")
    print(f"Location: {job.location}")
    print(f"Status: {job.status}")
    print(f"\nDescription:\n{job.description}")


if __name__ == "__main__":
    main()
