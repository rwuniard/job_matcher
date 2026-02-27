from job_matcher_agent import match_job
from queue_consumer import QueueConsumer
from queue_consumer.message_processor import ProcessingResult
from models import LinkedInJobAlert
from dotenv import load_dotenv
import os
import threading
from logger import setup_logging
import logging

from models import JobMatcherResult
from redis_cache.job_cache import JobCache

load_dotenv()

HOST = os.getenv("HOST")
PORT = os.getenv("PORT")
USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")
ADDRESS = os.getenv("ADDRESS")
QUEUE_NAME = os.getenv("QUEUE_NAME")
NUM_CONSUMERS = int(os.getenv("NUM_CONSUMERS"))

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or None

setup_logging()
logger = logging.getLogger(__name__)

_processing_job_ids: set[str] = set()
_processing_lock = threading.Lock()

_REPORT_HEADER = "# Job Match Report\n\n"


def is_job_already_processed(job_id: str) -> bool:
    """
    Returns True if the job was already processed (in-flight or cached in Redis).
    Fails open on Redis errors — if the cache is unavailable, we process the job
    rather than skip it, to avoid missing legitimate new jobs.
    """
    with _processing_lock:
        if job_id in _processing_job_ids:
            return True
    try:
        return JobCache.get_job(job_id) is not None
    except Exception as e:
        logger.warning(f"Redis unavailable when checking job_id: {job_id}, processing anyway. Error: {e}")
        return False

def message_processor(message_id: str, message_body: str) -> ProcessingResult:
    """
    Message processor function for processing messages from the AMQP broker.
    This function is called by the QueueConsumer when a new message is received.
    It processes the message and writes the AI response to a file.
    Args:
        message_id: The ID of the message
        message_body: The body of the message
    Returns:
        ProcessingResult.ACCEPTED  — all jobs processed, remove from queue.
        ProcessingResult.RELEASED  — transient failure, requeue for retry.
        ProcessingResult.REJECTED  — malformed message, send to Dead Letter Queue.
    """
    # Parse the envelope once — if this fails the message is genuinely malformed.
    try:
        alert = LinkedInJobAlert.model_validate_json(message_body)
    except Exception as e:
        logger.error(f"Error parsing message-id: {message_id}, error: {e}")
        return ProcessingResult.REJECTED

    os.makedirs("./job_results", exist_ok=True)

    for job in alert.jobs:
        # Each job is independent — one failure must not affect the others.
        try:
            logger.info(f"Processing job-url: {job.url}")

            job_id = job.url.rstrip("/").split("/")[-1]
            if is_job_already_processed(job_id):
                logger.warning(f"Skipping duplicate job_id: {job_id}, from email subject: {alert.subject}")
                continue

            # Mark in-flight before the slow LLM/Playwright call so concurrent
            # workers processing the same job_id see it and skip.
            with _processing_lock:
                _processing_job_ids.add(job_id)

            try:
                job_matcher_result = match_job(job.url)
            finally:
                with _processing_lock:
                    _processing_job_ids.discard(job_id)
            logger.info(f"Job Matcher Result: {job_matcher_result}")

            try:
                JobCache.set_job(job_id, {
                    "job_id": job_id,
                    "job_description": job_matcher_result.job_description,
                })
            except Exception as e:
                logger.warning(f"Failed to cache job_id: {job_id}. Error: {e}")

            if job_matcher_result.job_status == "applied":
                with open(f"./job_results/{job_id}.applied.md", "w") as f:
                    f.write(_REPORT_HEADER)
                    f.write(f"**Job Title:** {job.title}  \n")
                    f.write(f"**Job URL:** {job.url}  \n")
                    f.write(f"**Email Subject:** {alert.subject}  \n")
                    f.write(f"**Email Date:** {alert.date}\n\n")
                    f.write("## Status: Applied\n\n")
                    f.write("You have already applied to this job.\n")

            elif job_matcher_result.job_status == "closed":
                with open(f"./job_results/{job_id}.closed.md", "w") as f:
                    f.write(_REPORT_HEADER)
                    f.write(f"**Job Title:** {job.title}  \n")
                    f.write(f"**Job URL:** {job.url}  \n")
                    f.write(f"**Email Subject:** {alert.subject}  \n")
                    f.write(f"**Email Date:** {alert.date}\n\n")
                    f.write("## Status: Closed\n\n")
                    f.write("This job is no longer accepting applications.\n")

            elif job_matcher_result.job_status == "open":
                with open(f"./job_results/{job_id}.ai_response.md", "w") as f:
                    f.write(_REPORT_HEADER)
                    f.write(f"**Job Title:** {job.title}  \n")
                    f.write(f"**Job URL:** {job.url}  \n")
                    f.write(f"**Email Subject:** {alert.subject}  \n")
                    f.write(f"**Email Date:** {alert.date}\n\n")
                    f.write("## AI Analysis\n\n")
                    f.write(f"{job_matcher_result.ai_response}\n\n")
                    f.write("## Job Description\n\n")
                    f.write(f"{job_matcher_result.job_description}\n")

            else:
                # Bug 3 fix: log and continue; don't abandon remaining jobs in the loop.
                logger.error(f"Invalid job status: {job_matcher_result.job_status} for {job.url}")

        except Exception as e:
            # Log and continue to the next job — individual job failures do not
            # affect remaining jobs, and the message is still accepted to avoid
            # reprocessing already-completed jobs (idempotency protection).
            logger.error(f"Error processing job-url: {job.url}, error: {e}")

    return ProcessingResult.ACCEPTED

   

def main():
    logger.info("Hello from job-matcher!")
    JobCache.connect(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD)
    queue_consumer = QueueConsumer(HOST, PORT, USERNAME, PASSWORD, ADDRESS, QUEUE_NAME, NUM_CONSUMERS, message_processor)
    queue_consumer.start()
 

if __name__ == "__main__":
    main()


