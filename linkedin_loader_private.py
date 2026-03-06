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

            # Extract job title from the page <title> tag: "Job Title | Company | LinkedIn"
            # This is far more stable than any DOM class or SDUI component name.
            raw_title = page.title()
            title = raw_title.split(" | ")[0].strip() if " | " in raw_title else raw_title.strip()

            # Extract location + work type from the top-card header.
            # LinkedIn renders this as: "Company · City, State (On-site)" in a subtitle line.
            # We try specific selectors first, then fall back to regex on raw page text.
            location = ""
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
                        location = _text
                        break

            # Detect application status — full page text is the most reliable fallback
            # because LinkedIn frequently renames CSS classes and SDUI components.
            page_text_raw = page.locator("body").inner_text()
            page_text = page_text_raw.lower()

            # Regex fallback: find the workplace type, then extract whatever location
            # text appears on the same line immediately before it.
            # This handles any city/region/country format (US, international, metro areas).
            # IMPORTANT: Scope to the job top-card area only to avoid picking up location
            # text from recommended/similar jobs rendered elsewhere on the page.
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
                # Fall back to full page text only if no scoped element was found
                if not _search_text:
                    _search_text = page_text_raw

                _wt_match = re.search(r'\b(On-site|Hybrid|Remote)\b', _search_text, re.IGNORECASE)
                if _wt_match:
                    workplace_type = _wt_match.group(1)
                    line_start = _search_text.rfind('\n', 0, _wt_match.start()) + 1
                    preceding = _search_text[line_start:_wt_match.start()].strip()
                    # Strip trailing separators (·, •, -, parens) from the location text
                    preceding = re.sub(r'[\s\u00b7\u2022\-\(]+$', '', preceding).strip()
                    location = f"{preceding} ({workplace_type})" if preceding else workplace_type

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
