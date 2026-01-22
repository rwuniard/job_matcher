import urllib.request
from bs4 import BeautifulSoup


def get_linkedin_job_public(url: str) -> dict:
    """
    Load a LinkedIn job description from public page (no authentication required).

    Args:
        url: LinkedIn job URL (e.g., https://www.linkedin.com/jobs/view/123456/)

    Returns:
        Dictionary with job details: title, company, location, description
    """
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req).read().decode("utf-8")
    soup = BeautifulSoup(html, "html.parser")

    job_data = {}

    # Job title
    title_el = soup.select_one(".top-card-layout__title")
    job_data["title"] = title_el.get_text(strip=True) if title_el else ""

    # Company name
    company_el = soup.select_one(".topcard__org-name-link")
    job_data["company"] = company_el.get_text(strip=True) if company_el else ""

    # Location
    location_el = soup.select_one(".topcard__flavor--bullet")
    job_data["location"] = location_el.get_text(strip=True) if location_el else ""

    # Job description (full content is in HTML, no need to click "Show more")
    desc_el = soup.select_one(".show-more-less-html__markup")
    job_data["description"] = desc_el.get_text(separator=" ", strip=True) if desc_el else ""

    return job_data


def main():
    job_url = "https://www.linkedin.com/jobs/view/4358994928/"

    print("Fetching job details...")
    job = get_linkedin_job_public(job_url)

    print(f"\nTitle: {job['title']}")
    print(f"Company: {job['company']}")
    print(f"Location: {job['location']}")
    print(f"\nDescription:\n{job['description']}")


if __name__ == "__main__":
    main()
