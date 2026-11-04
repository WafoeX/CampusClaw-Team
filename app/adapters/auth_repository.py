from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.mysql import insert

from app.adapters.auth_schema_v1 import accounts, auth_audits, auth_sessions, classes

SEED_CLASSES = ("class-a", "class-b")


class AuthRepository:
    def __init__(self, engine):
        self.engine = engine

    def find_account(self, login_name):
        with self.engine.connect() as connection:
            return (
                connection.execute(
                    select(accounts).where(accounts.c.login_name == login_name)
                )
                .mappings()
                .one_or_none()
            )

    def find_session(self, digest, now):
        query = (
            select(
                accounts.c.id,
                accounts.c.login_name,
                accounts.c.class_id,
                accounts.c.role,
                classes.c.name.label("class_name"),
                auth_sessions.c.expires_at,
            )
            .select_from(auth_sessions.join(accounts).join(classes))
            .where(
                auth_sessions.c.token_digest == digest,
                auth_sessions.c.expires_at > now,
                auth_sessions.c.revoked_at.is_(None),
                accounts.c.enabled.is_(True),
            )
        )
        with self.engine.connect() as connection:
            return connection.execute(query).mappings().one_or_none()

    def replace_session(self, account_id, verified_hash, digest, now, expires):
        with self.engine.begin() as connection:
            current = self._lock_account(connection, account_id)
            if (
                current is None
                or not current.enabled
                or current.password_hash != verified_hash
            ):
                return False
            connection.execute(
                delete(auth_sessions).where(auth_sessions.c.account_id == account_id)
            )
            connection.execute(
                auth_sessions.insert().values(
                    account_id=account_id,
                    token_digest=digest,
                    issued_at=now,
                    expires_at=expires,
                )
            )
            self._audit(connection, account_id, "login", now)
            return True

    def revoke_session(self, account_id, digest, now):
        with self.engine.begin() as connection:
            self._lock_account(connection, account_id)
            result = connection.execute(
                update(auth_sessions)
                .where(
                    auth_sessions.c.account_id == account_id,
                    auth_sessions.c.token_digest == digest,
                    auth_sessions.c.expires_at > now,
                    auth_sessions.c.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
            if result.rowcount != 1:
                return False
            self._audit(connection, account_id, "logout", now)
            return True

    def change_account(self, account_id, now, *, password_hash=None):
        with self.engine.begin() as connection:
            current = self._lock_account(connection, account_id)
            if current is None:
                return False
            fields = (
                {"enabled": False}
                if password_hash is None
                else {"password_hash": password_hash}
            )
            connection.execute(
                update(accounts)
                .where(accounts.c.id == account_id)
                .values(updated_at=now, **fields)
            )
            connection.execute(
                update(auth_sessions)
                .where(
                    auth_sessions.c.account_id == account_id,
                    auth_sessions.c.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
            event = "disable" if password_hash is None else "reset_password"
            self._audit(connection, account_id, event, now)
            return True

    @staticmethod
    def _lock_account(connection, account_id):
        return connection.execute(
            select(accounts).where(accounts.c.id == account_id).with_for_update()
        ).one_or_none()

    @staticmethod
    def _audit(connection, account_id, event, now):
        connection.execute(
            auth_audits.insert().values(
                id=str(uuid4()), account_id=account_id, event=event, created_at=now
            )
        )

    def seed_demo_accounts(self, password_hash):
        now = datetime.now(UTC).replace(tzinfo=None)
        with self.engine.begin() as connection:
            for code in SEED_CLASSES:
                class_insert = insert(classes).values(
                    id=str(uuid4()),
                    code=code,
                    name=f"合成 {code[-1].upper()} 班",
                    created_at=now,
                )
                connection.execute(
                    class_insert.on_duplicate_key_update(id=classes.c.id)
                )
                class_id = connection.execute(
                    select(classes.c.id).where(classes.c.code == code)
                ).scalar_one()
                for role in ("teacher", "student"):
                    login_name = f"demo_{code[-1]}_{role}"
                    account_insert = insert(accounts).values(
                        id=str(uuid4()),
                        login_name=login_name,
                        password_hash=password_hash,
                        enabled=True,
                        class_id=class_id,
                        role=role,
                        created_at=now,
                        updated_at=now,
                    )
                    connection.execute(
                        account_insert.on_duplicate_key_update(id=accounts.c.id)
                    )
                    actual_class = connection.execute(
                        select(accounts.c.class_id).where(
                            accounts.c.login_name == login_name
                        )
                    ).scalar_one()
                    if actual_class != class_id:
                        raise ValueError("合成登录名已被其他班级占用")
