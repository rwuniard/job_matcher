import os
from dotenv import load_dotenv

# Get langchain dependencies
from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI

from get_resume import get_resume

from linkedin_loader_private import get_linkedin_job

from logger import setup_logging
import logging

from datetime import date

from models import JobMatcherResult

load_dotenv()
setup_logging()
logger = logging.getLogger(__name__)

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")


class TransientAgentError(Exception):
    """Raised when the agent fails due to a transient condition (rate limit, network, etc.)
    that is safe to retry by requeuing the message."""

_PROMPT_FILE = os.path.join(os.path.dirname(__file__), "prompts", "system_prompt.txt")
with open(_PROMPT_FILE, encoding="utf-8") as _f:
    _SYSTEM_PROMPT = _f.read()




def match_job(job_url: str) -> JobMatcherResult:
    """
    Match a job and return the AI response.
    Args:
        job_url: The URL of the job to match.
    Returns:
        A JobMatcherResult object containing the job result and AI response.
    """
    logger.info(f"Matching job-url: {job_url}")

    model = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.5)

    agent = create_agent(
        model=model,
        tools=[],
        system_prompt=_SYSTEM_PROMPT,
    )

    resume = get_resume("resume.txt")

    # Get job description from linkedin using linkedin_loader.py. This is from linkedin public page.
    # job_details = get_linkedin_job_public("https://www.linkedin.com/jobs/view/4354044808/")
    # Get the job description from the job_details dictionary.
    # job_details_description = job_details["description"]

    # Get job description from linkedin using linkedin_loader_private.py. This is from linkedin private page.
    # This allows us to know whether the candidate has applied to
    job = get_linkedin_job(job_url)

 
    # Short-circuit for jobs that don't need analysis.
    if job.status in ("applied", "closed"):
        print("The candidate has applied to the job or the job is closed.")
        return JobMatcherResult(job_url=job_url, job_status=job.status, ai_response="")

    if not job.description:
        raise TransientAgentError(f"Job description is empty for {job_url} — LinkedIn may be slow. Will retry.")

    # get today's date, so the LLM knows the current date.
    today_date = date.today()

    user_message = f"""
    Today's date: {today_date}
    Conduct a rigorous gap analysis between the following resume and job description.:

    Resume: {resume}

    Job Title: {job.title}
    Job Location: {job.location}
    Job Description: {job.description}
    """

    try:
        results = agent.invoke({"messages": [{"role": "user", "content": user_message}]})
    except Exception as e:
        # HTTP 429 (rate limit) and 5xx (server errors) are transient — safe to retry.
        # Everything else (e.g. invalid model name, bad API key) is permanent.
        status = getattr(e, "status_code", None) or getattr(e, "code", None)
        if status in (429, 500, 502, 503, 504):
            raise TransientAgentError(str(e)) from e
        raise

    ai_response = results.get("messages")[-1].content
    logger.debug("Job Matcher Result: %s", ai_response)
    print(f"AI Response: {ai_response}")

    return JobMatcherResult(job_url=job_url, job_status=job.status, ai_response=ai_response, job_description=job.description)



def main():
    job_result = match_job("https://www.linkedin.com/jobs/view/4375302812/")
    logger.info(f"Job Matcher Result: {job_result}")

if __name__ == "__main__":
    main()


