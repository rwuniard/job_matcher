from job_matcher_agent import match_job, TransientAgentError
from queue_consumer import QueueConsumer
from queue_consumer.message_processor import ProcessingResult
from models import LinkedInJobAlert
from dotenv import load_dotenv
import os
import re
import threading
from logger import setup_logging
import logging

from models import JobMatcherResult
from redis_cache.job_cache import JobCache

load_dotenv()


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None:
        raise RuntimeError(f"Required environment variable '{name}' is not set.")
    return value


HOST = _require_env("HOST")
PORT = _require_env("PORT")
USERNAME = _require_env("USERNAME")
PASSWORD = _require_env("PASSWORD")
ADDRESS = _require_env("ADDRESS")
QUEUE_NAME = _require_env("QUEUE_NAME")
NUM_CONSUMERS = int(_require_env("NUM_CONSUMERS"))

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or None

setup_logging()
logger = logging.getLogger(__name__)

_processing_job_ids: set[str] = set()
_processing_lock = threading.Lock()

_REPORT_HEADER = "# Job Match Report\n\n"
_SCORE_RE = re.compile(r'Overall Match Score\D*(\d{1,2}(?:\.\d+)?)/10', re.IGNORECASE)
_MAX_TRANSIENT_RETRIES = 3


def _extract_score(ai_response: str) -> str:
    """Return the rounded integer score from the AI response, or 'na' if not found."""
    m = _SCORE_RE.search(ai_response)
    return str(round(float(m.group(1)))) if m else "na"


def _try_claim_job(job_id: str) -> bool:
    """
    Atomically checks whether a job is already in-flight or cached, and if not,
    marks it as in-flight. Returns True if the caller has claimed the job and
    should process it, False if it should be skipped.

    The in-flight check and the Redis check are both performed while holding
    _processing_lock to eliminate the TOCTOU race between the two checks.
    Fails open on Redis errors — if the cache is unavailable, the job is claimed
    and processed rather than silently skipped.
    """
    with _processing_lock:
        if job_id in _processing_job_ids:
            return False
        try:
            if JobCache.get_job(job_id) is not None:
                return False
        except Exception as e:
            logger.warning("Redis unavailable when checking job_id: %s, processing anyway. Error type: %s", job_id, type(e).__name__)
        _processing_job_ids.add(job_id)
        return True

def _write_job_result(job, job_id: str, result: JobMatcherResult, alert_subject: str, alert_date: str) -> None:
    """Write the job match result to a file."""
    header = (
        f"{_REPORT_HEADER}"
        f"**Job Title:** {job.title}  \n"
        f"**Job URL:** {job.url}  \n"
        f"**Email Subject:** {alert_subject}  \n"
        f"**Email Date:** {alert_date}\n\n"
    )

    if result.job_status == "applied":
        with open(f"./job_results/{job_id}.applied.md", "w") as f:
            f.write(header)
            f.write("## Status: Applied\n\nYou have already applied to this job.\n")

    elif result.job_status == "closed":
        with open(f"./job_results/{job_id}.closed.md", "w") as f:
            f.write(header)
            f.write("## Status: Closed\n\nThis job is no longer accepting applications.\n")

    elif result.job_status == "open":
        score = _extract_score(result.ai_response)
        with open(f"./job_results/{job_id}.{score}.ai_response.md", "w") as f:
            f.write(header)
            f.write(f"## AI Analysis\n\n{result.ai_response}\n\n")
            f.write(f"## Job Description\n\n{result.job_description}\n")

    else:
        logger.error(f"Invalid job status: {result.job_status} for {job.url}")


def _process_single_job(job, alert_subject: str, alert_date: str) -> None:
    """Process one job. Raises TransientAgentError or other exceptions on failure."""
    logger.info(f"Processing job-url: {job.url}")
    job_id = job.url.rstrip("/").split("/")[-1]

    if not _try_claim_job(job_id):
        logger.warning(f"Skipping duplicate job_id: {job_id}, from email subject: {alert_subject}")
        return

    try:
        job_matcher_result = match_job(job.url)
    finally:
        with _processing_lock:
            _processing_job_ids.discard(job_id)

    logger.info(f"Job Matcher Result: {job_matcher_result}")

    try:
        JobCache.set_job(job_id, {"job_id": job_id, "job_description": job_matcher_result.job_description})
    except Exception as e:
        logger.warning(f"Failed to cache job_id: {job_id}. Error: {e}")

    _write_job_result(job, job_id, job_matcher_result, alert_subject, alert_date)


def message_processor(message_id: str, message_body: str, delivery_count: int) -> ProcessingResult:
    """
    Message processor function for processing messages from the AMQP broker.
    This function is called by the QueueConsumer when a new message is received.
    It processes the message and writes the AI response to a file.
    Args:
        message_id: The ID of the message
        message_body: The body of the message
        delivery_count: Number of prior delivery attempts (0 = first attempt).
    Returns:
        ProcessingResult.ACCEPTED  — all jobs processed, remove from queue.
        ProcessingResult.RELEASED  — transient failure, requeue for retry.
        ProcessingResult.REJECTED  — malformed message or retry limit exceeded, send to DLQ.
    """
    try:
        alert = LinkedInJobAlert.model_validate_json(message_body)
    except Exception as e:
        logger.error(f"Error parsing message-id: {message_id}, error: {e}")
        return ProcessingResult.REJECTED

    os.makedirs("./job_results", exist_ok=True)

    has_transient_failure = False
    has_permanent_failure = False

    for job in alert.jobs:
        try:
            _process_single_job(job, alert.subject, alert.date)
        except TransientAgentError as e:
            if delivery_count >= _MAX_TRANSIENT_RETRIES:
                logger.error(f"Transient error exceeded max retries ({_MAX_TRANSIENT_RETRIES}) for job-url: {job.url}, sending to DLQ. Error: {e}")
                has_permanent_failure = True
            else:
                logger.warning(f"Transient error (attempt {delivery_count + 1}/{_MAX_TRANSIENT_RETRIES + 1}) for job-url: {job.url}, requeueing. Error: {e}")
                has_transient_failure = True
        except Exception as e:
            logger.error(f"Permanent error processing job-url: {job.url}, error: {e}")
            has_permanent_failure = True

    if has_permanent_failure:
        return ProcessingResult.REJECTED
    if has_transient_failure:
        return ProcessingResult.RELEASED
    return ProcessingResult.ACCEPTED

   

def main():
    logger.info("Hello from job-matcher!")
    JobCache.connect(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD)
    queue_consumer = QueueConsumer(HOST, PORT, USERNAME, PASSWORD, ADDRESS, QUEUE_NAME, NUM_CONSUMERS, message_processor)
    queue_consumer.start()
 

if __name__ == "__main__":
    main()


