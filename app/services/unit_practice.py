"""服务端签发的本轮普通单位练习。"""

import base64
import binascii
import hmac
import json
import re
import secrets

from app.services.ai_contracts import bad

TOKEN = re.compile(r"[A-Za-z0-9_-]{1,480}\.[a-f0-9]{64}")
TTL_SECONDS = 300
UNITS = (("mm", "cm", "m", "km"), ("g", "kg"))


class UnitPractice:
    def __init__(self, secret, clock):
        self.secret = secret
        self.clock = clock

    @staticmethod
    def question(arguments):
        return f"单位练习：把 {arguments['value']} {arguments['from_unit']} 换算为 {arguments['to_unit']}。"

    def _signature(self, identity, session_id, key, encoded):
        binding = ":".join(
            (identity.class_id, identity.subject_id, session_id, key.decode(), encoded)
        )
        return hmac.digest(self.secret, binding.encode(), "sha256").hex()

    def issue(self, identity, session_id, key):
        group = secrets.choice(UNITS)
        first = secrets.choice(group)
        second = secrets.choice([unit for unit in group if unit != first])
        arguments = {
            "value": secrets.randbelow(80) + 11,
            "from_unit": first,
            "to_unit": second,
        }
        payload = {
            "arguments": arguments,
            "expires_at": int(self.clock()) + TTL_SECONDS,
        }
        encoded = (
            base64.urlsafe_b64encode(
                json.dumps(payload, separators=(",", ":")).encode()
            )
            .decode()
            .rstrip("=")
        )
        signature = self._signature(identity, session_id, key, encoded)
        return {
            "question": self.question(arguments),
            "practice_context": encoded + "." + signature,
        }

    def verify(self, identity, session_id, key, question, token):
        if not isinstance(token, str) or not TOKEN.fullmatch(token):
            raise bad("练习上下文无效，请重新领取单位练习")
        encoded, signature = token.split(".")
        if not hmac.compare_digest(
            self._signature(identity, session_id, key, encoded), signature
        ):
            raise bad("练习上下文无效，请重新领取单位练习")
        try:
            value = json.loads(
                base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
            )
            if (
                self.question(value["arguments"]) != question
                or type(value["expires_at"]) is not int
            ):
                raise ValueError
            return value
        except (ValueError, KeyError, TypeError, binascii.Error):
            raise bad("练习题面已变化，请重新领取单位练习") from None

    def check_expiry(self, context):
        if context["expires_at"] <= self.clock():
            raise bad("练习上下文已过期，请重新领取单位练习")
