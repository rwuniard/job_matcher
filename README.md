# Job Matcher

An automated AI-powered pipeline that evaluates LinkedIn job postings against a candidate's resume and produces structured match reports — saving time by filtering out irrelevant roles before a human ever reads them.

## Overview

**Job Matcher** is one half of a two-project system:

```
[Gmail]
   │  LinkedIn Job Alert emails
   ▼
[gmail_linkedin_job_alert]   ← companion project (see below)
   │  Extracts job URLs, publishes messages to queue
   ▼
[ActiveMQ Artemis]           ← AMQP message broker
   │  Job alert messages (list of job URLs per email)
   ▼
[job_matcher]                ← this project
   │
   ├─ Scrapes each job URL → LinkedIn job description (Playwright)
   ├─ Loads candidate resume (static file)
   ├─ Evaluates match using LangChain agent + Google Gemini
   ├─ Writes a structured Markdown report to ./job_results/
   └─ Caches job ID + description in Redis (skips duplicates on future emails)
```

### How it works

1. **Consume** — Worker threads listen to an ActiveMQ Artemis queue. Each message represents one LinkedIn Job Alert email and contains a list of job URLs.

2. **Scrape** — For each job URL, Playwright loads the authenticated LinkedIn page and extracts the job title, full description, application status (open / applied / closed), and **location + work type** (e.g. `Atlanta, GA (On-site)`). Location is scraped from the top-card header using a selector cascade with a regex fallback, so it works for any city or country format.

3. **Evaluate** — A LangChain agent powered by Google Gemini acts as a strict Technical Recruiter, scoring the candidate's resume against the job description across domain fit, location, and recency of experience. The job's **location and work type** are provided explicitly to the agent so it can make an accurate location determination without having to infer it from the description text.

4. **Report** — A Markdown report is written to `./job_results/` for every processed job, capturing the AI score, gap analysis, and full job description for reference.

5. **Deduplicate** — After processing, the job ID and description are stored in Redis with a 30-day TTL. The same job posting frequently appears across multiple LinkedIn Job Alert emails. Without deduplication, each occurrence would trigger a full Playwright scrape and an LLM evaluation — burning time and API tokens on a job already reviewed. With Redis, the second occurrence is recognised instantly and skipped before any expensive work begins.

### Companion project

**[gmail_linkedin_job_alert](https://github.com/rwuniard/Gmail_LinkedIn_job_alerts)** is the upstream feeder for this pipeline. It monitors Gmail for LinkedIn Job Alert emails, extracts all job URLs from each email, and publishes them as messages to ActiveMQ Artemis for this service to consume.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Google API key (for Gemini)
- Apache ActiveMQ Artemis (or any AMQP 1.0 compatible broker)
- Playwright Chromium browser
- Redis 7+ (for job deduplication cache)

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

# Redis cache
REDIS_HOST=localhost
REDIS_PORT=6379
# REDIS_PASSWORD=        # optional: set if Redis requires authentication

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=text      # json | text | dual
ENVIRONMENT=development
# LOG_FILE=logs/job_matcher.log   # optional: write logs to a rotating file
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
| `{job_id}.ai_response.md` | AI scoring and gap analysis for open jobs |
| `{job_id}.applied.md` | Job was already applied to — skipped |
| `{job_id}.closed.md` | Job is no longer accepting applications — skipped |

All result files are written in Markdown format.

## Redis Cache (Job Deduplication)

Processed job IDs are cached in Redis to prevent re-evaluation when the same job appears in multiple emails or after report files are deleted.

On each job:
1. `job_id` is checked against Redis before running Playwright or the LLM
2. If found → job is skipped as a duplicate
3. If not found → job is processed, then stored in Redis with the job description

Cached entries expire after **30 days** by default. Each entry stores:

```json
{
  "job_id": "4375302812",
  "job_description": "Full scraped description text..."
}
```

If Redis is unavailable, the cache check fails open — the job is processed normally rather than silently skipped.

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
├── prompts/
│   └── system_prompt.txt        # AI recruiter system prompt (edit without touching Python)
├── models/
│   └── linkedin.py              # Pydantic models (LinkedInJobAlert, Job)
├── queue_consumer/
│   ├── __init__.py
│   ├── consumer.py              # AMQP queue listener (QueueConsumer)
│   └── message_processor.py    # MessageProcessor Protocol definition
├── redis_cache/
│   └── job_cache.py             # Redis-backed job deduplication cache (JobCache)
├── logger/
│   └── logger_config.py        # JSON + text dual logging setup
├── tests/                       # Unit tests
├── job_results/                 # AI analysis output (generated at runtime)
└── resume.txt                   # Your resume content
```

## Known Issues / TODO

- [ ] **Refactor message processor into a separate thread from the job matcher** — currently `match_job()` blocks the AMQP worker thread while scraping LinkedIn and calling the AI API. This causes the broker to disconnect with `local-idle-timeout expired` because heartbeats cannot be sent while the thread is blocked. The fix is to hand off processing to a thread pool so the AMQP worker stays free for heartbeats.

## Agent Scoring Rubric

The agent acts as a strict Technical Executive Recruiter enforcing domain and location matching. The full prompt lives in [`prompts/system_prompt.txt`](prompts/system_prompt.txt) — edit it there without touching Python code.

### Scores

| Score | Meaning |
|---|---|
| 1–3 | Hard fail: domain mismatch (cap applied regardless of location) |
| 4–6 | Domain matches but location is a mismatch, or experience is stale (>5 years) |
| 7–10 | Strong domain alignment + location/remote match + recent leadership |

Location mismatch (On-site/Hybrid role in a different state) subtracts 3 points from the otherwise-calculated score.

### Domain Categories

- Product/AppDev
- Infrastructure/Platform
- Data Engineering
- ML/AI
- Security

### Location / Work Mode Logic

The scraper extracts the work type directly from the LinkedIn top-card header and passes it to the agent as `Job Location` (e.g. `Atlanta, GA (On-site)`). The agent applies these rules:

| JD Work Mode | Candidate State | Result |
|---|---|---|
| Remote | Any | Match |
| On-site / Hybrid | Same state as JD | Match |
| On-site / Hybrid | Different state | Mismatch (−3 pts) |
| Not specified | Any | Treated as unspecified |

### Recency Constraints

- No domain management in the last 5 years → max score 5
- Leadership experience older than 10 years → not counted
- Only accomplishments from the last 5 years weighted
