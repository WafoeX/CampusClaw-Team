"""Independent teaching outbox relay and Kafka consumer entry points."""

import argparse
import os
import signal
import threading
import time
from pathlib import Path

from kafka.errors import KafkaError

from app.adapters.chat_client import ChatClient, ChatProtocolError
from app.adapters.database import DatabaseError, mysql_engine
from app.adapters.index_clients import IndexDependencyError
from app.adapters.retrieval_repository import RetrievalRepository
from app.adapters.teaching_jobs import TeachingJobs
from app.adapters.teaching_kafka import commit, consumer, producer, publish
from app.config import Settings
from app.observability import log_event
from app.services.teaching_candidates import CandidateJobs
from app.teaching_job_contract import Event, JobFailure, JobNotSettled


def relay_once(repository, transport, event_log):
    row = repository.claim_outbox()
    if row is None:
        return False
    try:
        delivered = publish(transport, row)
    except KafkaError:
        delivered = False
    repository.delivery_receipt(row, delivered=delivered)
    event_log(
        "teaching_delivery",
        task_id=row["job_id"],
        event_id=row["id"],
        delivered=delivered,
    )
    return delivered


def process_record(repository, service, record, event_log):
    try:
        event = Event.parse(record.key, record.value)
    except (ValueError, RecursionError):
        repository.isolate(record.topic, record.partition, record.offset)
        event_log("teaching_isolated", partition=record.partition, offset=record.offset)
        return
    started = time.monotonic()
    claim = repository.claim_job(event)
    if claim is None:
        event_log("teaching_duplicate", task_id=event.task_id, event_id=event.event_id)
        return
    try:
        drafts = service.generate(claim)
    except JobFailure as error:
        settled = service.complete(claim, failure=error)
    else:
        settled = service.complete(claim, drafts=drafts)
    if not settled:
        raise JobNotSettled()
    event_log(
        "teaching_processed",
        task_id=event.task_id,
        event_id=event.event_id,
        trace_id=event.trace_id,
        duration_ms=round((time.monotonic() - started) * 1000, 2),
    )


def run_relay(repository, bootstrap, stopping, event_log):
    transport = producer(bootstrap)
    next_metrics = 0
    try:
        while not stopping.is_set():
            now = time.monotonic()
            if now >= next_metrics:
                recovered = repository.recover()
                event_log(
                    "teaching_backlog", recovered=recovered, **repository.metrics()
                )
                next_metrics = now + 15
            if not relay_once(repository, transport, event_log):
                stopping.wait(0.5)
    finally:
        transport.close(timeout=3)


def run_consumer(repository, service, bootstrap, stopping, event_log):
    transport = consumer(bootstrap)
    next_metrics = 0
    try:
        while not stopping.is_set():
            batches = transport.poll(timeout_ms=500, max_records=1)
            for records in batches.values():
                for record in records:
                    process_record(repository, service, record, event_log)
                    commit(transport, record)
            now = time.monotonic()
            if now >= next_metrics:
                # This is observed end offset minus the next offset to be read by this worker.
                lag = sum(
                    max(0, high - position)
                    for partition in transport.assignment()
                    if (high := transport.highwater(partition)) is not None
                    and (position := transport.position(partition)) is not None
                )
                event_log("teaching_lag", lag=lag)
                next_metrics = now + 15
    finally:
        transport.close(autocommit=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("role", choices=("relay", "consumer"))
    args = parser.parse_args()
    settings = Settings.load(os.environ, Path(__file__).with_name("BUILD_VERSION"))
    bootstrap = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
    engine = mysql_engine(
        host=settings.mysql_host,
        port=settings.mysql_port,
        database=settings.mysql_database,
        user=settings.mysql_user,
        password=settings.mysql_password,
    )
    repository = TeachingJobs(engine)

    def event_log(name, **fields):
        log_event(name, settings.version, **fields)

    def model_log(**fields):
        event_log("model", **fields)

    service = CandidateJobs(
        repository,
        DatabaseError,
        RetrievalRepository(engine),
        settings.chat.version if settings.chat else None,
        chat=ChatClient(settings.chat, on_result=model_log) if settings.chat else None,
        protocol_error=ChatProtocolError,
        dependency_error=IndexDependencyError,
    )
    stopping = threading.Event()

    def stop(*_):
        stopping.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, stop)
    delay = 1
    try:
        while not stopping.is_set():
            try:
                if args.role == "relay":
                    run_relay(repository, bootstrap, stopping, event_log)
                else:
                    run_consumer(repository, service, bootstrap, stopping, event_log)
            except (DatabaseError, KafkaError, JobNotSettled) as error:
                event_log(
                    "teaching_dependency", role=args.role, reason=type(error).__name__
                )
                stopping.wait(delay)
                delay = min(delay * 2, 15)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
