# Job Matcher

A simple demonstration project showcasing how to create an agent with LangChain that matches a resume against a job description from LinkedIn using an LLM.

## Overview

This project:
- Scrapes job descriptions from LinkedIn using Playwright (with persistent login session)
- Reads a local resume file
- Uses a LangChain agent with Google Gemini to analyze and score how well the resume matches the job description
- Provides structured feedback on relevant and missing skills/experiences

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Google API key (for Gemini)

## Setup

```bash
# Initialize git repository
git init

# Initialize project with uv
uv init

# Install dependencies
uv add langchain
uv add langchain-openai
uv add langchain-community
uv add langchain-google-genai
uv add beautifulsoup4
uv add playwright
uv add python-dotenv

# Install Playwright browser
uv run playwright install chromium
```

## Configuration

Create a `.env` file with your API keys:

```
GOOGLE_API_KEY=your-google-api-key-here
```

## LinkedIn Login Setup

On first run, you need to authenticate with LinkedIn:

1. In `url_loader.py`, set `first_login=True`
2. Run the script - a browser window will open
3. Log in to LinkedIn manually
4. Press Enter in the terminal after logging in
5. Your session is saved to `./linkedin_session/`
6. For subsequent runs, set `first_login=False`

## Usage

1. Create a `resume.txt` file with your resume content
2. Update the LinkedIn job URL in `job_matcher_agent.py`
3. Run the matcher:

```bash
uv run python main.py
```

## Project Structure

- `main.py` - Entry point
- `job_matcher_agent.py` - LangChain agent that performs the matching
- `url_loader.py` - Playwright-based LinkedIn job scraper
- `get_resume.py` - Resume file reader
