import pika
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class MessageQueue:
    def __init__(self, config):
        self.config = config
        self.connection = None
        self.channel = None
        self.connect()

    def connect(self):
        """Establish connection to RabbitMQ"""
        try:
            parameters = pika.URLParameters(self.config.RABBITMQ_URL)
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()

            self.channel.exchange_declare(exchange='market_data', exchange_type='topic', durable=True)

            self.channel.queue_declare(queue='data_updates', durable=True)
            self.channel.queue_declare(queue='data_quality', durable=True)
            self.channel.queue_declare(queue='collection_status', durable=True)

            self.channel.queue_bind(exchange='market_data', queue='data_updates', routing_key='data.*')
            self.channel.queue_bind(exchange='market_data', queue='data_quality', routing_key='quality.*')
            self.channel.queue_bind(exchange='market_data', queue='collection_status', routing_key='status.*')

            logger.info("Connected to RabbitMQ")

        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            raise

    def publish(self, topic, message):
        """Publish message to a topic"""
        try:
            if not self.connection or self.connection.is_closed:
                self.connect()

            routing_key = f"data.{topic}"

            self.channel.basic_publish(
                exchange='market_data',
                routing_key=routing_key,
                body=json.dumps(message),
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    timestamp=int(datetime.now().timestamp())
                )
            )

            logger.debug(f"Published message to {routing_key}")

        except Exception as e:
            logger.error(f"Failed to publish message: {e}")
            self.connect()

    def consume(self, queue, callback):
        """Consume messages from a queue"""
        try:
            if not self.connection or self.connection.is_closed:
                self.connect()

            def wrapper(ch, method, properties, body):
                try:
                    message = json.loads(body)
                    callback(message)
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

            self.channel.basic_consume(queue=queue, on_message_callback=wrapper)
            logger.info(f"Starting to consume from {queue}")
            self.channel.start_consuming()

        except Exception as e:
            logger.error(f"Error in consume: {e}")
            raise

    def close(self):
        """Close connection"""
        if self.connection and not self.connection.is_closed:
            self.connection.close()
            logger.info("Closed RabbitMQ connection")