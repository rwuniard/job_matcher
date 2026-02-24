# Job Matcher

A pipeline that consumes LinkedIn Job Alert emails from an AMQP queue, scrapes each job posting using Playwright, and uses a LangChain agent with Google Gemini to score how well a resume matches the job description.

## Overview

This project:
- Listens to an AMQP queue (Apache ActiveMQ Artemis) for LinkedIn Job Alert messages
- Parses each alert and extracts individual job URLs
- Scrapes job descriptions from authenticated LinkedIn pages using Playwright
- Uses a LangChain agent with Google Gemini to score resume-to-job fit
- Skips jobs already applied to or closed
- Saves AI analysis results to `./job_results/`

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Google API key (for Gemini)
- Apache ActiveMQ Artemis (or any AMQP 1.0 compatible broker)
- Playwright Chromium browser

## Setup

```bash
# Install dependencies
uv sync

# Install with dev dependencies (recommended for testing)
uv sync --extra dev

# Install Playwright browser
uv run playwright install chromium
```

## Configuration

Create a `.env` file based on `.env.example`:

```env
GOOGLE_API_KEY=your-google-api-key-here

# AMQP broker
HOST=localhost
PORT=5672
USERNAME=artemis
PASSWORD=artemis
ADDRESS=your-address
QUEUE_NAME=your-queue-name
NUM_CONSUMERS=1

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=text      # json | text | dual
ENVIRONMENT=development
```

## LinkedIn Authentication (First Run Only)

The scraper uses a persistent Playwright browser session to access authenticated LinkedIn pages.

1. In `linkedin_loader_private.py`, set `first_login=True` and run once:
   ```bash
   uv run linkedin_loader_private.py
   ```
2. Log in to LinkedIn in the browser window that opens
3. Press Enter after the job page has fully loaded
4. Session is saved to `./linkedin_session/` — subsequent runs use it automatically
5. Set `first_login=False` for all future runs

## Usage

### Run the full pipeline (queue consumer + job matcher)

```bash
uv run main.py
```

This starts `NUM_CONSUMERS` worker threads, each listening to the AMQP queue. When a LinkedIn Job Alert message arrives, each job URL in the alert is processed through the matcher.

### Run the job matcher standalone

```bash
uv run job_matcher_agent.py
```

Update the job URL in `main()` at the bottom of `job_matcher_agent.py`.

### Run the LinkedIn scraper standalone

```bash
uv run linkedin_loader_private.py
```

## Output

Results are saved to `./job_results/` with the job ID as the filename:

| File | Meaning |
|---|---|
| `{job_id}.ai_response` | AI scoring and gap analysis for open jobs |
| `{job_id}.applied` | Job was already applied to — skipped |
| `{job_id}.closed` | Job is no longer accepting applications — skipped |

## Running Tests

```bash
# Install dev dependencies (first time only)
uv sync --extra dev

# Run all tests
uv run pytest -v
```

Current unit tests cover:
- `get_resume.py` file loading behavior
- `linkedin_loader.py` HTML parsing with mocked network responses
- `linkedin_loader_private.py` status parsing logic with mocked Playwright objects
- `job_matcher_agent.py` open/applied/closed flow behavior with mocked LLM and loader dependencies

## Project Structure

```
job_matcher/
├── main.py                      # Entry point — queue consumer + message processor
├── job_matcher_agent.py         # LangChain agent with scoring rubric
├── linkedin_loader_private.py   # Playwright-based LinkedIn scraper (authenticated)
├── linkedin_loader.py           # Public LinkedIn scraper (no auth, legacy)
├── get_resume.py                # Resume file reader
├── models/
│   └── linkedin.py              # Pydantic models (LinkedInJobAlert, Job)
├── queue_consumer/
│   ├── __init__.py
│   ├── consumer.py              # AMQP queue listener (QueueConsumer)
│   └── message_processor.py    # MessageProcessor Protocol definition
├── logger/
│   └── logger_config.py        # JSON + text dual logging setup
├── tests/                       # Unit tests
├── job_results/                 # AI analysis output (generated at runtime)
└── resume.txt                   # Your resume content
```

## Known Issues / TODO

- [ ] **Refactor message processor into a separate thread from the job matcher** — currently `match_job()` blocks the AMQP worker thread while scraping LinkedIn and calling the AI API. This causes the broker to disconnect with `local-idle-timeout expired` because heartbeats cannot be sent while the thread is blocked. The fix is to hand off processing to a thread pool so the AMQP worker stays free for heartbeats.

## Agent Scoring Rubric

The agent acts as a strict Technical Executive Recruiter enforcing domain and location matching.

### Scores

| Score | Meaning |
|---|---|
| 1–3 | Hard fail: domain mismatch or location mismatch |
| 4–6 | Adjacent domain, stale experience (>5 years), or partial location match |
| 7–10 | Strong domain alignment + location/remote match + recent leadership |

### Domain Categories

- Product/AppDev
- Infrastructure/Platform
- Data Engineering
- ML/AI
- Security

### Hard Fail Rules

- Domain mismatch (e.g. Data leader applying for Infrastructure role)
- Location mismatch for on-site/hybrid roles
- No management experience in the domain within the last 10 years

### Penalties

- Experience older than 5 years in the domain → max score 5
- Leadership older than 10 years → not counted
