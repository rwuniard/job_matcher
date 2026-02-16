# Job Matcher

A demonstration project showcasing how to create an agent with LangChain that matches a resume against a job description from LinkedIn using an LLM.

## Overview

This project:
- Fetches job descriptions from LinkedIn public pages (no authentication required)
- Reads a local resume file
- Uses a LangChain agent with Google Gemini to analyze and score how well the resume matches the job description
- Applies strict domain matching and recency rules for technical leadership roles
- Provides structured feedback on domain alignment, relevant assets, and gaps

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Google API key (for Gemini)

## Setup

```bash
# Install dependencies
uv sync

# Install with dev dependencies (recommended for testing)
uv sync --extra dev
```

## Configuration

Create a `.env` file with your API key:

```
GOOGLE_API_KEY=your-google-api-key-here
```

## Usage

1. Create a `resume.txt` file with your resume content
2. Update the LinkedIn job URL in `job_matcher_agent.py`
3. Run the matcher:

```bash
uv run python main.py
```

## Running Tests

This project uses `pytest` for unit testing.

```bash
# Run tests with dev dependencies enabled
uv run --extra dev pytest -q
```

Current unit tests cover:
- `get_resume.py` file loading behavior
- `linkedin_loader.py` HTML parsing with mocked network responses
- `linkedin_loader_private.py` status parsing logic with mocked Playwright objects
- `job_matcher_agent.py` open/applied/closed flow behavior with mocked LLM and loader dependencies

## Project Structure

```
job_matcher/
├── main.py                 # Entry point
├── job_matcher_agent.py    # LangChain agent with evaluation criteria
├── linkedin_loader.py      # Public LinkedIn job scraper (no auth)
├── linkedin_loader_private.py  # Playwright-based loader for authenticated pages
├── get_resume.py           # Resume file reader
├── tests/                  # Unit tests
│   ├── test_get_resume.py
│   ├── test_job_matcher_agent.py
│   ├── test_linkedin_loader.py
│   └── test_linkedin_loader_private.py
└── resume.txt              # Your resume content
```

### LinkedIn Loaders

**`linkedin_loader.py`** (Recommended)
- Uses `urllib` + `BeautifulSoup` to fetch public job pages
- No authentication required
- Fast and lightweight

```python
from linkedin_loader import get_linkedin_job_public

job = get_linkedin_job_public("https://www.linkedin.com/jobs/view/123456/")
print(job["title"])
print(job["description"])
```

**`linkedin_loader_private.py`** (Authenticated/Private pages)
- Uses Playwright with persistent browser session
- Required for authenticated LinkedIn pages or jobs not publicly visible
- Requires one-time manual login

To use authenticated scraping:
1. Install Playwright browser: `uv run playwright install chromium`
2. In `linkedin_loader_private.py`, set `first_login=True` and run once
3. Log in to LinkedIn in the browser window
4. Press Enter after login completes
5. Session is saved to `./linkedin_session/`
6. Set `first_login=False` for subsequent runs

## Agent Prompt Structure

The agent uses a two-part prompt design:

- **System Prompt**: Defines the recruiter persona, domain taxonomy, and scoring rubric
- **User Message**: Contains the task, output format, resume, and job description

### Scoring Criteria

| Score | Meaning |
|-------|---------|
| 1-3 | Domain mismatch (e.g., Data leader applying for Infra/Platform role) |
| 4-6 | Adjacent domain or stale experience (>5 years) |
| 7-10 | Strong domain alignment with recent leadership |

### Domain Categories

- Product/AppDev
- Infrastructure/Platform
- Data Engineering
- ML/AI
- Security
