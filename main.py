from job_matcher_agent import match_job
from queue_consumer import QueueConsumer
from models import LinkedInJobAlert
from dotenv import load_dotenv
import os
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


def message_processor(message_id: str, message_body: str) -> bool:
    """
    Message processor function for processing messages from the AMQP broker.
    This function is called by the QueueConsumer when a new message is received.
    It processes the message and writes the AI response to a file.
    Args:
        message_id: The ID of the message
        message_body: The body of the message
    Returns:
        True if the message was processed successfully, False otherwise
    """
    try:
        alert = LinkedInJobAlert.model_validate_json(message_body)
        for job in alert.jobs:
            logger.info(f"Processing job-url: {job.url}")

            job_matcher_result = match_job(job.url)
            
            logger.info(f"Job Matcher Result: {job_matcher_result}")

            # Write the AI response to a file.
            # Get the job id from the job url.
            job_id = job.url.rstrip("/").split("/")[-1]
            # Create the job_results directory if it doesn't exist.
            os.makedirs("./job_results", exist_ok=True)

            if job_matcher_result.job_status == "applied":
                with open(f"./job_results/{job_id}.applied", "w") as f:
                    f.write(f"Job URL: {job.url}\n")
                    f.write(f"From email subject: {alert.subject}\n")
                    f.write(f"From email date: {alert.date}\n")
                    f.write(f"Job Title: {job.title}\n")
                    f.write(f"You have already applied to this job.")
                        
            elif job_matcher_result.job_status == "closed":
                with open(f"./job_results/{job_id}.closed", "w") as f:
                    f.write(f"Job URL: {job.url}\n")
                    f.write(f"From email subject: {alert.subject}\n")
                    f.write(f"From email date: {alert.date}\n")
                    f.write(f"Job Title: {job.title}\n")
                    f.write(f"The job is closed.")
            elif job_matcher_result.job_status == "open":
                with open(f"./job_results/{job_id}.ai_response", "w") as f:
                    f.write(f"Job URL: {job.url}\n")
                    f.write(f"From email subject: {alert.subject}\n")
                    f.write(f"From email date: {alert.date}\n")
                    f.write(f"Job Title: {job.title}\n")
                    f.write(f"AI Response: {job_matcher_result.ai_response}\n")
                    f.write(f"\n\nJob description: {job_matcher_result.job_description}\n")
            else:
                logger.error(f"Invalid job status: {job_matcher_result.job_status}")
                return False
        return True
    except Exception as e:
        logger.error(f"Error processing message-id: {message_id}, body: {message_body}, error: {e}")
        return False

def main():
    logger.info("Hello from job-matcher!")
    queue_consumer = QueueConsumer(HOST, PORT, USERNAME, PASSWORD, ADDRESS, QUEUE_NAME, NUM_CONSUMERS, message_processor)
    queue_consumer.start()
 

if __name__ == "__main__":
    main()


