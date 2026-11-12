"""Kafka transport for reference-only teaching events."""

import json

from kafka import KafkaConsumer, KafkaProducer
from kafka.structs import OffsetAndMetadata, TopicPartition

from app.teaching_job_contract import CONSUMER_GROUP, TASK_TOPIC


def producer(bootstrap):
    return KafkaProducer(
        bootstrap_servers=bootstrap,
        acks="all",
        enable_idempotence=True,
        max_in_flight_requests_per_connection=5,
        request_timeout_ms=5000,
        delivery_timeout_ms=12000,
        max_block_ms=5000,
    )


def consumer(bootstrap):
    return KafkaConsumer(
        TASK_TOPIC,
        bootstrap_servers=bootstrap,
        group_id=CONSUMER_GROUP,
        enable_auto_commit=False,
        allow_auto_create_topics=False,
        auto_offset_reset="earliest",
        max_poll_records=1,
        max_poll_interval_ms=120000,
        request_timeout_ms=15000,
        session_timeout_ms=10000,
    )


def publish(transport, row):
    receipt = transport.send(
        row["topic"],
        key=row["message_key"].encode(),
        value=json.dumps(row["payload"], separators=(",", ":")).encode(),
    ).get(timeout=13)
    return receipt.topic == row["topic"]


def commit(transport, record):
    partition = TopicPartition(record.topic, record.partition)
    if partition in transport.assignment():
        transport.commit({partition: OffsetAndMetadata(record.offset + 1, "", -1)})
