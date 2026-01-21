from playwright.sync_api import sync_playwright

SESSION_DIR = "./linkedin_session"


def get_linkedin_job(url: str, first_login: bool = False) -> str:
    """
    Load a LinkedIn job description using Playwright.

    Args:
        url: LinkedIn job URL
        first_login: Set True for first run to manually log in

    Returns:
        Job description text
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

        # Click "See more" button to expand full description
        see_more_button = page.locator(".jobs-description button[aria-label*='more']")
        if see_more_button.count() > 0:
            see_more_button.first.click()
            page.wait_for_timeout(500)  # Wait for expansion animation

        content = page.locator(".jobs-description").inner_text()

        browser.close()
        return content


def main():
    job_url = "https://www.linkedin.com/jobs/view/4358994928/"

    # First run: set first_login=True to log in manually
    # After that: set first_login=False (session is saved)
    # description = get_linkedin_job(job_url, first_login=True)
    description = get_linkedin_job(job_url, first_login=False)
    print(description)


if __name__ == "__main__":
    main()
