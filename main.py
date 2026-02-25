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

load_dotenv()

HOST = os.getenv("HOST")
PORT = os.getenv("PORT")
USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")
ADDRESS = os.getenv("ADDRESS")
QUEUE_NAME = os.getenv("QUEUE_NAME")
NUM_CONSUMERS = int(os.getenv("NUM_CONSUMERS"))

setup_logging()
logger = logging.getLogger(__name__)

_processing_job_ids: set[str] = set()
_processing_lock = threading.Lock()


def validate_jobid_exists_in_results(jobid: str) -> bool:
        """
        Validate if the jobid has already been processed or is currently in-flight.
        Checks result files (.ai_response, .applied, .closed) and the in-flight set.
        """
        try:
            with _processing_lock:
                if jobid in _processing_job_ids:
                    return True
            return any(
                os.path.exists(f"./job_results/{jobid}.{ext}")
                for ext in ("ai_response", "applied", "closed")
            )
        except Exception as e:
            logger.error(f"Error validating jobid: {jobid}, error: {e}")
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
            # Validate if the jobid exists in the job_results directory
            if validate_jobid_exists_in_results(job_id):
                logger.warning(f"Jobid: {job.url} does exist in the job_results directory, from email subject: {alert.subject}")
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

            if job_matcher_result.job_status == "applied":
                with open(f"./job_results/{job_id}.applied", "w") as f:
                    f.write(f"Job URL: {job.url}\n")
                    f.write(f"From email subject: {alert.subject}\n")
                    f.write(f"From email date: {alert.date}\n")
                    f.write(f"Job Title: {job.title}\n")
                    f.write("You have already applied to this job.")

            elif job_matcher_result.job_status == "closed":
                with open(f"./job_results/{job_id}.closed", "w") as f:
                    f.write(f"Job URL: {job.url}\n")
                    f.write(f"From email subject: {alert.subject}\n")
                    f.write(f"From email date: {alert.date}\n")
                    f.write(f"Job Title: {job.title}\n")
                    f.write("The job is closed.")

            elif job_matcher_result.job_status == "open":
                with open(f"./job_results/{job_id}.ai_response", "w") as f:
                    f.write(f"Job URL: {job.url}\n")
                    f.write(f"From email subject: {alert.subject}\n")
                    f.write(f"From email date: {alert.date}\n")
                    f.write(f"Job Title: {job.title}\n")
                    f.write(f"AI Response: {job_matcher_result.ai_response}\n")
                    f.write(f"\n\nJob description: {job_matcher_result.job_description}\n")

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
    queue_consumer = QueueConsumer(HOST, PORT, USERNAME, PASSWORD, ADDRESS, QUEUE_NAME, NUM_CONSUMERS, message_processor)
    queue_consumer.start()
 

if __name__ == "__main__":
    main()


