import stomp
from dotenv import load_dotenv
import os
import time
import sys
from logger import setup_logging
import logging

# Setup logging
setup_logging()
# Get the logger for the current module
logger = logging.getLogger(__name__)



# Load environment variables
load_dotenv()

HOST = os.getenv('HOST')
PORT = os.getenv('PORT')
USERNAME = os.getenv('USERNAME')
PASSWORD = os.getenv('PASSWORD')
DESTINATION = os.getenv('DESTINATION')
print(HOST, PORT, USERNAME, PASSWORD, DESTINATION)


class MyListener(stomp.ConnectionListener):
    def __init__(self, conn):
        self.conn = conn

    def on_message(self, frame):
        logger.info(f"Received message: {frame.body}")
        logger.info(f"All headers: {frame.headers}")
        try:
            self.conn.ack(frame.headers['message-id'], frame.headers['subscription'])
            logger.info(f"Ack'ed message: {frame.headers['message-id']} with subscription: {frame.headers['subscription']}")
        except Exception as e:
            logger.error(f"ACK failed for message: {frame.headers['message-id']} with subscription: {frame.headers['subscription']} with error: {e}")

    def on_error(self, frame):
        logger.error(f"MyListener on Error: {frame.body}")
        logger.error(f"MyListener on Error: All headers: {frame.headers}")
       

    def on_disconnected(self):
        logger.info("MyListener on Disconnect: Disconnected from ActiveMQ")


class QueueConsumer:
    def __init__(self, host, port, username, password, destination, client_id, prefetch_count=10):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.destination = destination,
        self.client_id = client_id
        self.prefetch_count = prefetch_count

    def connect(self):
        self.conn = stomp.Connection([(self.host, int(self.port))], heartbeats=(10000, 10000))
        self.conn.connect(self.username, self.password, wait=True, headers={'client-id': self.client_id})
        self.conn.set_listener('', MyListener(self.conn))
        logger.info(f"Connected to ActiveMQ: {self.host}:{self.port}")

    def subscribe(self):
        self.conn.subscribe(
            destination=self.destination, 
            id=1, 
            ack='client', 
            headers={
                'subscription-type': 'MULTICAST', 
                'durable-subscription-name': 'my-durable-subscription',
                'activemq.prefetchPolicy.all': str(self.prefetch_count) # Prefetch 10 messages at a time
            }
        )

    def disconnect(self):
        self.conn.disconnect()

def main():
    load_dotenv()
    # Get environment variables
    HOST = os.getenv('HOST')
    PORT = os.getenv('PORT')
    USERNAME = os.getenv('USERNAME')
    PASSWORD = os.getenv('PASSWORD')
    DESTINATION = os.getenv('DESTINATION')
    logger.info(f"HOST: {HOST}, PORT: {PORT}, USERNAME: {USERNAME}, PASSWORD: {PASSWORD}, DESTINATION: {DESTINATION}")

    try:
        if len(sys.argv) != 2:
            logger.error("Usage: python activemq_consumer.py <client_id>")
            sys.exit(1)

        client_id = sys.argv[1]
        logger.info(f"Client ID: {client_id}")

        consumer = QueueConsumer(HOST, PORT, USERNAME, PASSWORD, DESTINATION, client_id, prefetch_count=10)
        consumer.connect()
        consumer.subscribe()

        # heartbeats=(10000, 10000) means send heartbeat every 10 seconds and expect heartbeat every 10 seconds
        # conn = stomp.Connection([(HOST, PORT)], heartbeats=(10000, 10000))
        # # Set the client-id so the consumer can be identified
        # conn.connect(USERNAME, PASSWORD, wait=True, headers={'client-id': client_id})
        # conn.set_listener('', MyListener(conn))

        # # Set it to multicast so each subscriber gets a copy of the message
        # # Set it to durable so the messages are persisted to the queue even if the consumer is disconnected
        # # Set it to client-id so the consumer can be identified
        # conn.subscribe(
        #     destination=DESTINATION, 
        #     id=1, 
        #     ack='client', 
        #     headers={
        #         'subscription-type': 'MULTICAST', 
        #         'durable-subscription-name': 'my-durable-subscription'
        #     }
        # )
        # print("Connected to ActiveMQ")
        while True:
            time.sleep(1)

        conn.disconnect()
        print("Disconnected from ActiveMQ")
    
    except Exception as e:
        logger.error(f"Error: {e}")
        consumer.disconnect()
        print("Disconnected from ActiveMQ")

if __name__ == "__main__":
    main()