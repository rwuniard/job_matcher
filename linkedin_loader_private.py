from dataclasses import dataclass
from playwright.sync_api import sync_playwright

SESSION_DIR = "./linkedin_session"


@dataclass
class LinkedInJob:
    title: str
    description: str
    status: str  # "open", "applied", "closed"


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
    """
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR,
            headless=not first_login
        )
        page = browser.pages[0] if browser.pages else browser.new_page()

        page.goto(url)

        if first_login:
            print("Please log in to LinkedIn in the browser window...")
            input("Press Enter after logging in and the job page has loaded...")

        # Wait for job description to load
        page.wait_for_selector(".jobs-description", timeout=30000)

        # Extract job title
        title_selectors = [
            ".job-details-jobs-unified-top-card__job-title h1",
            ".jobs-unified-top-card__job-title",
            "h1.t-24",
        ]
        title = ""
        for selector in title_selectors:
            title_elem = page.locator(selector)
            if title_elem.count() > 0:
                title = title_elem.first.inner_text().strip()
                break

        # Detect application status (check most specific conditions first)
        status = "open"

        # Wait a moment for dynamic content to load
        page.wait_for_timeout(1000)

        # Try to find status from specific UI elements first
        status_selectors = [
            ".jobs-apply-button--applied",
            "[data-job-id] .artdeco-inline-feedback",
            ".jobs-unified-top-card__applicant-count",
            ".jobs-save-button",
        ]

        for selector in status_selectors:
            elem = page.locator(selector)
            if elem.count() > 0:
                elem_text = elem.first.inner_text().lower()
                if "application submitted" in elem_text or "applied" in elem_text:
                    status = "applied"
                    break
                elif "no longer accepting" in elem_text:
                    status = "closed"
                    break

        # Fallback: check full page text if not found via selectors
        if status == "open":
            page_text = page.locator("body").inner_text().lower()
            if "no longer accepting applications" in page_text:
                status = "closed"
            elif "application submitted" in page_text:
                status = "applied"

        # Click "See more" button to expand full description
        see_more_button = page.locator(".jobs-description button[aria-label*='more']")
        if see_more_button.count() > 0:
            see_more_button.first.click()
            page.wait_for_timeout(500)  # Wait for expansion animation

        description = page.locator(".jobs-description").inner_text()

        browser.close()
        return LinkedInJob(title=title, description=description, status=status)


def main():
    #job_url = "https://www.linkedin.com/jobs/view/4328534952/" # job applied
    #job_url = "https://www.linkedin.com/jobs/view/4365010800/" # job no longer accepting applications
    job_url = "https://www.linkedin.com/jobs/view/4350687450/" # job open

    # First run: set first_login=True to log in manually
    # After that: set first_login=False (session is saved)
    job = get_linkedin_job(job_url, first_login=False)

    print(f"Title: {job.title}")
    print(f"Status: {job.status}")
    print(f"\nDescription:\n{job.description}")


if __name__ == "__main__":
    main()
