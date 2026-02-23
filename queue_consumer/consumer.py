
import os
import time
import sys
from logger import setup_logging
import logging
import threading

from proton import Timeout
from proton.utils import BlockingConnection

from .message_processor import MessageProcessor

# Setup logging
setup_logging()
# Get the logger for the current module
logger = logging.getLogger(__name__)

class QueueConsumer:
    """QueueConsumer class for consuming messages from an AMQP broker."""
    _heartbeat = 120
    _timeout = 60


    """QueueConsumer class for consuming messages from an AMQP broker."""
    def __init__(self, host, port, username, password, address, queue_name, num_consumers, message_processor: MessageProcessor):
        """Initialize the QueueConsumer."""
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.address = address
        self.queue_name = queue_name
        self.num_consumers = num_consumers
        self.amqp_destination = f'{self.address}::{self.queue_name}'
        self.message_processor = message_processor

    def worker(self, worker_id: int):
        """Worker function for consuming messages from the AMQP broker.
        Args:
            worker_id: The ID of the worker
        """
        try:
            # Connect to the AMQP broker
            url = f'amqp://{self.username}:{self.password}@{self.host}:{self.port}'
            conn = BlockingConnection(url, heartbeat=QueueConsumer._heartbeat, timeout=QueueConsumer._timeout)
            receiver = conn.create_receiver(self.amqp_destination, credit=1)
            logger.info(f"Connected to the AMQP broker: {url}")

            while True:
                # Receive a message from the AMQP broker
                try:
                    msg = receiver.receive(timeout=QueueConsumer._timeout)
                    if msg:
                        logger.info(f"{worker_id} received message-id: {msg.id}")
                        # Process the message using the message processor
                        ok = self.message_processor(msg.id, msg.body)
                        if ok:
                            receiver.accept()
                        else:
                            logger.error(f"{worker_id} message-id: {msg.id} processing failed")
                            receiver.reject()
                    else:
                        logger.info(f"{worker_id} message is empty, message-id: {msg.id}, body: {msg.body}")
                except Timeout:
                    logger.debug(f"{worker_id} timed out after {QueueConsumer._timeout} seconds")
                    continue
                except Exception as e:
                    logger.error(f"{worker_id} message-id: {msg.id} error: {e}")
                    continue
        except Exception as e:
            logger.error(f"{worker_id} error: {e}")
        finally:
            conn.close()
            logger.info(f"{worker_id} disconnected from the AMQP broker")


def main():

    def message_processor(message_id: str, message_body: str) -> bool:
        """Message processor function for processing messages from the AMQP broker.
        Args:
            message_id: The ID of the message
            message_body: The body of the message
        Returns:
            True if the message was processed successfully, False otherwise
        """
        logger.info("################################################################################")
        logger.info(f"Processing message-id: {message_id}, body: {message_body}")
        logger.info("################################################################################")
        return True
    
    try:
        from dotenv import load_dotenv
        # Load environment variables
        load_dotenv()
        HOST = os.getenv('HOST')
        PORT = os.getenv('PORT')
        USERNAME = os.getenv('USERNAME')
        PASSWORD = os.getenv('PASSWORD')
        ADDRESS = os.getenv('ADDRESS')
        QUEUE_NAME = os.getenv('QUEUE_NAME')
        NUM_CONSUMERS = int(os.getenv('NUM_CONSUMERS'))
        logger.info(f"HOST: {HOST}, PORT: {PORT}, USERNAME: {USERNAME}, PASSWORD: {PASSWORD},"
                    f"ADDRESS: {ADDRESS}, QUEUE_NAME: {QUEUE_NAME}, NUM_CONSUMERS: {NUM_CONSUMERS}")

        consumer = QueueConsumer(HOST, PORT, USERNAME, PASSWORD, ADDRESS, QUEUE_NAME, NUM_CONSUMERS, message_processor)

        for i in range(NUM_CONSUMERS):
            thread = threading.Thread(target=consumer.worker, args=(i,), daemon=True, name=f"consumer-worker-{i}")
            thread.start()
            logger.info(f"Started consumer-worker-{i}")
        while True:
            time.sleep(1)
    # except KeyboardInterrupt:
    #     logger.info("Keyboard interrupt received, shutting down...")
    #     consumer.disconnect()
    #     sys.exit(0)
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()