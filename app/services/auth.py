import re
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe

from app.services.access import AccessDenied

COOKIE_VALUE = re.compile(r"[A-Za-z0-9_-]{43}")
SESSION_DURATION = timedelta(minutes=30)


def utc_now():
    return datetime.now(UTC).replace(tzinfo=None)


def invalid_session():
    return AccessDenied(401, 1100, "登录状态无效，请重新登录")


def invalid_credentials():
    return AccessDenied(401, 1101, "账号或口令不正确")


def digest_cookie(value):
    if value is not None and COOKIE_VALUE.fullmatch(value):
        return sha256(value.encode("ascii")).digest()
    return None


class AuthService:
    def __init__(
        self, repository, verify_password, dummy_hash, database_error, clock=utc_now
    ):
        self.repository = repository
        self.verify_password = verify_password
        self.dummy_hash = dummy_hash
        self.database_error = database_error
        self.clock = clock

    def login(self, login_name, password):
        try:
            account = self.repository.find_account(login_name)
            stored_hash = self.dummy_hash if account is None else account.password_hash
            verified = self.verify_password(stored_hash, password)
            if not verified or account is None or not account.enabled:
                raise invalid_credentials()
            now = self.clock()
            expires = now + SESSION_DURATION
            cookie = token_urlsafe(32)
            if not self.repository.replace_session(
                account.id, stored_hash, digest_cookie(cookie), now, expires
            ):
                raise invalid_credentials()
            return cookie, expires
        except self.database_error:
            raise AccessDenied(503, 1500, "依赖服务暂不可用，请稍后重试") from None

    def current(self, cookie):
        digest = digest_cookie(cookie)
        if digest is None:
            return None
        return self.repository.find_session(digest, self.clock())

    def logout(self, account_id, cookie):
        digest = digest_cookie(cookie)
        try:
            revoked = self.repository.revoke_session(account_id, digest, self.clock())
        except self.database_error:
            raise AccessDenied(503, 1500, "依赖服务暂不可用，请稍后重试") from None
        if not revoked:
            raise invalid_session()
