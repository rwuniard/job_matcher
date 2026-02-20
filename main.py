from job_matcher_agent import match_job
from queue_consumer import QueueConsumer
from models import LinkedInJobAlert
from dotenv import load_dotenv
import os
from logger import setup_logging
import logging
import threading
import time

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
    """Message processor function for processing messages from the AMQP broker.
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
            match_job(job.url)
        return True
    except Exception as e:
        print(f"Error processing message-id: {message_id}, body: {message_body}, error: {e}")
        return False

def main():
    logger.info("Hello from job-matcher!")
    queue_consumer = QueueConsumer(HOST, PORT, USERNAME, PASSWORD, ADDRESS, QUEUE_NAME, NUM_CONSUMERS, message_processor)
    for i in range(NUM_CONSUMERS):
        thread = threading.Thread(target=queue_consumer.worker, args=(i,), daemon=True, name=f"queue-consumer-worker-{i}")
        thread.start()
        logger.info(f"Started queue-consumer-worker-{i}")
    while True:
        time.sleep(1)
    #$match_job("https://www.linkedin.com/jobs/view/4333297231/")

if __name__ == "__main__":
    main()


