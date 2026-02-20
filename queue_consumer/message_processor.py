from typing import Protocol

class MessageProcessor(Protocol):
    """
    MessageProcessor class for processing messages from the AMQP broker.
    This is a protocol that defines the interface for processing messages from the AMQP broker.
    """

    def __call__(self, message_id: str, message_body: str) -> bool:
        """
        Process a message from the AMQP broker.
        Args:
            message_id: The ID of the message
            message_body: The body of the message
        Returns:
            True if the message was processed successfully.
            False otherwise
        """
        ...