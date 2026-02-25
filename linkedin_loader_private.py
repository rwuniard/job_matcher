import logging
import threading
from dataclasses import dataclass
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

            # Detect application status — full page text is the most reliable fallback
            # because LinkedIn frequently renames CSS classes and SDUI components.
            page_text = page.locator("body").inner_text().lower()

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
            return LinkedInJob(title=title, description=description, status=status)


def main():
    job_url = "https://www.linkedin.com/jobs/view/4375302812/" # job applied
    #job_url = "https://www.linkedin.com/jobs/view/4365010800/" # job no longer accepting applications
    #job_url = "https://www.linkedin.com/jobs/view/4374040129/" # job open

    # First run: set first_login=True to log in manually
    # After that: set first_login=False (session is saved)
    job = get_linkedin_job(job_url, first_login=False)

    print(f"Title: {job.title}")
    print(f"Status: {job.status}")
    print(f"\nDescription:\n{job.description}")


if __name__ == "__main__":
    main()
