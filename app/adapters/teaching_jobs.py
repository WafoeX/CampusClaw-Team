"""MySQL owns job state, leases and publication receipts."""

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, insert, or_, select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert

from app.adapters.auth_schema_v1 import accounts, classes
from app.adapters.teaching_repository import TeachingRepository
from app.adapters.teaching_schema_v12 import (
    generated_questions,
    job_results,
    jobs,
    outbox,
    quarantine,
)
from app.teaching_job_contract import (
    ACTIVE,
    DEAD_TOPIC,
    JOB_LEASE_SECONDS,
    OUTBOX_LEASE_SECONDS,
    RECOVERY_SECONDS,
    RETRY_SECONDS,
    TASK_TOPIC,
    Event,
    JobNotSettled,
)


class TeachingJobs(TeachingRepository):
    def add_candidate(self, connection, job, fields, snapshot, now):
        question_id = str(uuid4())
        question = {
            "id": question_id,
            "class_id": job["class_id"],
            "creator_id": job["creator_id"],
            "current_version": 1,
            "reviewed_version": None,
            "created_at": now,
            "updated_at": now,
        }
        version = {
            **fields,
            "question_id": question_id,
            "class_id": job["class_id"],
            "version": 1,
            "created_at": now,
        }
        self.add_question(connection, question, version, job["creator_id"], now)
        self.save_source(connection, version, snapshot)
        connection.execute(
            insert(generated_questions).values(
                question_id=question_id, job_id=job["id"]
            )
        )
        return question_id

    def lock_capacity(self, connection, class_id, kind):
        connection.scalar(
            select(classes.c.id).where(classes.c.id == class_id).with_for_update()
        )
        return len(
            connection.scalars(
                select(jobs.c.id)
                .where(
                    jobs.c.class_id == class_id,
                    jobs.c.kind == kind,
                    jobs.c.state.in_(ACTIVE),
                )
                .with_for_update()
            ).all()
        )

    def owner_is_teacher(self, connection, job):
        return (
            connection.scalar(
                select(accounts.c.id)
                .where(
                    accounts.c.id == job["creator_id"],
                    accounts.c.class_id == job["class_id"],
                    accounts.c.enabled.is_(True),
                    accounts.c.role == "teacher",
                )
                .with_for_update()
            )
            is not None
        )

    def job(self, connection, job_id, *, lock=False):
        statement = select(jobs).where(jobs.c.id == job_id)
        if lock:
            statement = statement.with_for_update()
        return connection.execute(statement).mappings().one_or_none()

    def job_result(self, connection, job_id):
        return connection.scalar(
            select(job_results.c.result).where(job_results.c.job_id == job_id)
        )

    def _enqueue(self, connection, job, now, topic=TASK_TOPIC):
        event = Event(
            job["event_id"] if topic == TASK_TOPIC else str(uuid4()),
            job["id"],
            job["generation"],
            job["trace_id"],
        )
        self._message(
            connection,
            event.event_id,
            job["id"],
            topic,
            job["id"],
            event.payload(),
            now,
        )

    def _message(self, connection, event_id, job_id, topic, key, payload, now):
        connection.execute(
            insert(outbox).values(
                id=event_id,
                job_id=job_id,
                topic=topic,
                message_key=key,
                payload=payload,
                available_at=now,
            )
        )

    def add_job(self, connection, job, now):
        connection.execute(insert(jobs).values(job))
        self._enqueue(connection, job, now)

    def update_job(self, connection, job, **values):
        connection.execute(update(jobs).where(jobs.c.id == job["id"]).values(values))
        return {**job, **values}

    def replay(self, connection, job, now):
        replay = self.update_job(
            connection,
            job,
            state="pending",
            generation=job["generation"] + 1,
            attempt=0,
            event_id=str(uuid4()),
            error_code=None,
            error_reason=None,
            available_at=now,
            updated_at=now,
        )
        self._enqueue(connection, replay, now)
        return replay

    def claim_job(self, event):
        with self.transaction() as connection:
            job = self.job(connection, event.task_id, lock=True)
            now = self.now(connection)
            if (
                job is None
                or event.generation != job["generation"]
                or event.event_id != job["event_id"]
                or event.trace_id != job["trace_id"]
            ):
                return None
            if job["state"] == "running" or (
                job["state"] == "retry_wait" and job["available_at"] > now
            ):
                raise JobNotSettled()
            if job["state"] not in ("pending", "retry_wait"):
                return None
            return self.update_job(
                connection,
                job,
                state="running",
                lease_id=str(uuid4()),
                lease_until=now + timedelta(seconds=JOB_LEASE_SECONDS),
                updated_at=now,
            )

    def current_lease(self, connection, claim):
        job = self.job(connection, claim["id"], lock=True)
        now = self.now(connection)
        if (
            job is None
            or job["state"] != "running"
            or job["generation"] != claim["generation"]
            or job["lease_id"] != claim["lease_id"]
            or job["lease_until"] <= now
        ):
            return None, now
        return job, now

    def finish(self, connection, job, result, now):
        connection.execute(insert(job_results).values(job_id=job["id"], result=result))
        self._transition(connection, job, now, "succeeded", None)

    def _transition(self, connection, job, now, state, code, *, reason=None, **changes):
        return self.update_job(
            connection,
            job,
            state=state,
            error_code=code,
            error_reason=reason,
            lease_id=None,
            lease_until=None,
            updated_at=now,
            **changes,
        )

    def fail(self, connection, job, failure, now):
        reason = failure.reason
        if failure.cancelled:
            self._transition(
                connection, job, now, "cancelled", failure.code, reason=reason
            )
        elif not failure.transient:
            self._transition(
                connection, job, now, "failed", failure.code, reason=reason
            )
        elif job["attempt"] >= len(RETRY_SECONDS):
            terminal = self._transition(
                connection, job, now, "dead_letter", failure.code, reason=reason
            )
            self._enqueue(connection, terminal, now, DEAD_TOPIC)
        else:
            due = now + timedelta(seconds=RETRY_SECONDS[job["attempt"]])
            retry = self._transition(
                connection,
                job,
                now,
                "retry_wait",
                failure.code,
                reason=reason,
                attempt=job["attempt"] + 1,
                event_id=str(uuid4()),
                available_at=due,
            )
            self._enqueue(connection, retry, due)

    def recover(self):
        """Recover expired execution and events no longer reachable in Kafka."""
        with self.transaction() as connection:
            now = self.now(connection)
            stale = now - timedelta(seconds=RECOVERY_SECONDS)
            rows = (
                connection.execute(
                    select(jobs)
                    .join(outbox, outbox.c.id == jobs.c.event_id)
                    .where(
                        or_(
                            (jobs.c.state == "running") & (jobs.c.lease_until <= now),
                            jobs.c.state.in_(("pending", "retry_wait"))
                            & (outbox.c.sent_at <= stale),
                        )
                    )
                    .order_by(jobs.c.available_at, jobs.c.id)
                    .limit(20)
                    .with_for_update(skip_locked=True)
                )
                .mappings()
                .all()
            )
            for job in rows:
                self._transition(
                    connection, job, now, "pending", job["error_code"], available_at=now
                )
                connection.execute(
                    update(outbox)
                    .where(outbox.c.id == job["event_id"])
                    .values(
                        sent_at=None,
                        lease_id=None,
                        lease_until=None,
                        available_at=now,
                    )
                )
            return len(rows)

    def claim_outbox(self):
        with self.transaction() as connection:
            now = self.now(connection)
            row = (
                connection.execute(
                    select(outbox)
                    .where(
                        outbox.c.sent_at.is_(None),
                        outbox.c.available_at <= now,
                        or_(
                            outbox.c.lease_until.is_(None), outbox.c.lease_until <= now
                        ),
                    )
                    .order_by(outbox.c.available_at, outbox.c.id)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            lease = str(uuid4())
            connection.execute(
                update(outbox)
                .where(outbox.c.id == row["id"])
                .values(
                    lease_id=lease,
                    lease_until=now + timedelta(seconds=OUTBOX_LEASE_SECONDS),
                )
            )
            return {**row, "lease_id": lease}

    def delivery_receipt(self, claim, *, delivered):
        with self.transaction() as connection:
            now = self.now(connection)
            connection.execute(
                update(outbox)
                .where(
                    outbox.c.id == claim["id"], outbox.c.lease_id == claim["lease_id"]
                )
                .values(
                    sent_at=now if delivered else None,
                    available_at=claim["available_at"]
                    if delivered
                    else now + timedelta(seconds=5),
                    lease_id=None,
                    lease_until=None,
                )
            )

    def isolate(self, topic, partition, offset):
        with self.transaction() as connection:
            now = self.now(connection)
            location = {"topic": topic, "partition": partition, "offset": offset}
            existing = connection.execute(
                select(quarantine).filter_by(**location).with_for_update()
            ).first()
            if existing is not None:
                return
            connection.execute(
                mysql_insert(quarantine).values(**location, recorded_at=now)
            )
            event_id = str(uuid4())
            key = f"{topic}:{partition}:{offset}"
            self._message(
                connection,
                event_id,
                None,
                DEAD_TOPIC,
                key,
                {"version": 1, **location},
                now,
            )

    def metrics(self):
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(
                    jobs.c.state, func.count(), func.min(jobs.c.created_at)
                ).group_by(jobs.c.state)
            ).all()
            now = self.now(connection)
            ages = [
                (now - created).total_seconds()
                for state, _, created in rows
                if state in ACTIVE
            ]
            return {
                "states": {state: count for state, count, _ in rows},
                "oldest_pending_seconds": max(ages, default=0),
            }
