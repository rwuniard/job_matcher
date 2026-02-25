from enum import Enum
from typing import Protocol


class ProcessingResult(Enum):
    ACCEPTED = "accepted"    # Success — remove from queue
    RELEASED = "released"    # Transient failure — requeue for retry
    REJECTED = "rejected"    # Permanent failure — send to Dead Letter Queue


class MessageProcessor(Protocol):
    """
    MessageProcessor class for processing messages from the AMQP broker.
    This is a protocol that defines the interface for processing messages from the AMQP broker.
    """

    def __call__(self, message_id: str, message_body: str) -> ProcessingResult:
        """
        Process a message from the AMQP broker.
        Args:
            message_id: The ID of the message
            message_body: The body of the message
        Returns:
            ProcessingResult.ACCEPTED  — success, remove from queue.
            ProcessingResult.RELEASED  — transient failure, requeue for retry.
            ProcessingResult.REJECTED  — permanent failure, send to Dead Letter Queue.
        """
        ...
