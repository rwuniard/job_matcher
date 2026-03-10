
import os
import sys
from logger import setup_logging
import logging
import threading

from proton import Delivery
from proton.handlers import MessagingHandler
from proton.reactor import Container

from .message_processor import MessageProcessor, ProcessingResult

# Setup logging
setup_logging()
# Get the logger for the current module
logger = logging.getLogger(__name__)


class ConsumerHandler(MessagingHandler):
    """Event-driven AMQP message handler.

    The Container runs the IO loop internally, so heartbeats are always sent
    regardless of how long message processing takes. Each message is processed
    in a background thread; when done, the delivery settlement is scheduled
    back onto the Container's IO thread (the only thread-safe way to call it).
    """

    def __init__(self, url: str, amqp_destination: str, credit: int, message_processor: MessageProcessor):
        super().__init__(prefetch=credit, auto_accept=False)
        self.url = url
        self.amqp_destination = amqp_destination
        self.message_processor = message_processor
        self._pending: dict[object, ProcessingResult | None] = {}  # delivery → result (None = in-progress)
        self._lock = threading.Lock()

    # ── Container lifecycle ────────────────────────────────────────────────

    def on_start(self, event):
        conn = event.container.connect(self.url)
        event.container.create_receiver(conn, self.amqp_destination)
        logger.info(f"Connected to the AMQP broker: {self.url}")

    def on_disconnected(self, event):
        logger.warning(f"Disconnected from the AMQP broker: {self.url}")

    def on_error(self, event):
        logger.error(f"AMQP error: {event}")

    # ── Message handling ───────────────────────────────────────────────────

    def on_message(self, event):
        msg = event.message
        delivery = event.delivery
        logger.info(f"Received message-id: {msg.id}")

        # Register delivery as in-progress before spawning the thread
        # Lock the _pending dictionary to prevent race conditions between the main thread and the worker thread.
        with self._lock:
            # Add the delivery to the pending dictionary with a None result.
            # None means the delivery is in progress.
            # The _pending dictionary is a way to communicate the result
            # from the worker thread to the main thread.
            # It needs to be locked to prevent race conditions between the main thread and the worker thread.
            # The main thread needs to know when the worker thread has finished processing the message.
            # The worker thread needs to know when the main thread has settled the delivery.
            # The _pending dictionary is a way to communicate the result
            # from the worker thread to the main thread.
            self._pending[delivery] = None

        def _process():
            try:
                result = self.message_processor(msg.id, msg.body, msg.delivery_count)
            except Exception as e:
                logger.error(f"message-id: {msg.id} processing raised exception: {e}")
                result = ProcessingResult.RELEASED

            with self._lock:
                self._pending[delivery] = result
            event.container.schedule(0, self)

        threading.Thread(target=_process, daemon=True).start()

    def on_timer_task(self, _event):
        """Called by Container.schedule() — runs on the IO thread, safe to settle deliveries."""
        with self._lock:
            # Create a new dictionary with delivery that the result is not None.
            settled = {d: r for d, r in self._pending.items() if r is not None}
            # remove the deliveries from the pending dictionary, since they are settled.
            for delivery in settled:
                del self._pending[delivery]

        for delivery, result in settled.items():
            if result == ProcessingResult.ACCEPTED:
                delivery.update(Delivery.ACCEPTED)
                logger.info(f"Accepted delivery: {delivery.tag}")
            elif result == ProcessingResult.RELEASED:
                delivery.update(Delivery.RELEASED)
                logger.warning(f"Released delivery for redelivery: {delivery.tag}")
            else:
                delivery.update(Delivery.REJECTED)
                logger.error(f"Rejected delivery to DLQ: {delivery.tag}")
            delivery.settle()


class QueueConsumer:
    """QueueConsumer — manages configuration and starts the Container."""

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
        self.url = f'amqp://{self.username}:{self.password}@{self.host}:{self.port}'

    def start(self):
        """Start the consumer. Blocks until the Container stops."""
        logger.info(f"Starting consumer with {self.num_consumers} concurrent messages")
        handler = ConsumerHandler(
            url=self.url,
            amqp_destination=self.amqp_destination,
            credit=self.num_consumers,
            message_processor=self.message_processor,
        )
        Container(handler).run()


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
        consumer.start()  # blocks — Container owns the IO loop

    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
