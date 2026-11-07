"""有限证据结构和可明确核对的数量/单位校验；不代替人工语义裁决。"""

import re
from decimal import Decimal, InvalidOperation

from app.services.access import AccessDenied

NO_EVIDENCE = "资料中未找到相关内容"
NUMBER = r"[-+]?(?:\d+(?:\.\d+)?|\.\d+)"
CHINESE = r"[负零〇一二两三四五六七八九十百千万亿点]+"
FIELDS = {
    "电压": "voltage",
    "电流": "current",
    "功率": "power",
    "频率": "frequency",
    "温度": "temperature",
    "比例": "ratio",
    "比率": "ratio",
    "占比": "ratio",
    "概率": "ratio",
    "率": "ratio",
    "人数": "people",
    "次数": "count:次",
    "数量": "quantity",
    "费用": "currency",
    "价格": "currency",
    "时长": "duration",
    "用时": "duration",
    "长度": "length",
    "距离": "length",
    "质量": "mass",
    "重量": "mass",
}
UNITS = {
    "伏": ("voltage", "1"),
    "伏特": ("voltage", "1"),
    "V": ("voltage", "1"),
    "毫伏": ("voltage", ".001"),
    "mV": ("voltage", ".001"),
    "安": ("current", "1"),
    "安培": ("current", "1"),
    "A": ("current", "1"),
    "毫安": ("current", ".001"),
    "mA": ("current", ".001"),
    "瓦": ("power", "1"),
    "W": ("power", "1"),
    "千瓦": ("power", "1000"),
    "kW": ("power", "1000"),
    "赫兹": ("frequency", "1"),
    "Hz": ("frequency", "1"),
    "千赫兹": ("frequency", "1000"),
    "kHz": ("frequency", "1000"),
    "摄氏度": ("temperature", "1"),
    "℃": ("temperature", "1"),
    "°C": ("temperature", "1"),
    "%": ("ratio", ".01"),
    "％": ("ratio", ".01"),
    "成": ("ratio", ".1"),
    "人": ("people", "1"),
    "元": ("currency", "1"),
    "秒": ("duration", "1"),
    "s": ("duration", "1"),
    "毫秒": ("duration", ".001"),
    "ms": ("duration", ".001"),
    "分钟": ("duration", "60"),
    "小时": ("duration", "3600"),
    "米": ("length", "1"),
    "m": ("length", "1"),
    "厘米": ("length", ".01"),
    "cm": ("length", ".01"),
    "千米": ("length", "1000"),
    "公里": ("length", "1000"),
    "km": ("length", "1000"),
    "克": ("mass", ".001"),
    "g": ("mass", ".001"),
    "千克": ("mass", "1"),
    "公斤": ("mass", "1"),
    "kg": ("mass", "1"),
    "个": ("count:个", "1"),
    "次": ("count:次", "1"),
    "份": ("count:份", "1"),
    "章": ("count:章", "1"),
    "年": ("date:年", "1"),
    "月": ("date:月", "1"),
    "日": ("date:日", "1"),
    "天": ("duration", "86400"),
}
UNIT_PATTERN = "|".join(
    re.escape(unit) for unit in sorted(UNITS, key=len, reverse=True)
)
TOKEN = re.compile(
    rf"(?P<value>{NUMBER}|{CHINESE}(?=\s*(?:{UNIT_PATTERN})))(?:\s*(?P<unit>{UNIT_PATTERN}))?"
)


def invalid_answer():
    return AccessDenied(502, 1501, "回答校验未通过，请调整问题后重试")


def chinese_number(value):
    negative = value.startswith("负")
    value = value.removeprefix("负")
    digits = dict(zip("零〇一二两三四五六七八九", "001223456789", strict=True))
    if "点" in value:
        left, right = value.split("点", 1)
        result = chinese_number(left) + Decimal(
            "0." + "".join(digits[c] for c in right)
        )
        return -result if negative else result
    if not any(c in value for c in "十百千万亿"):
        result = Decimal("".join(digits[c] for c in value))
    else:
        total = section = number = 0
        for char in value:
            if char in digits:
                number = int(digits[char])
            else:
                unit = {"十": 10, "百": 100, "千": 1000, "万": 10000, "亿": 100000000}[
                    char
                ]
                if unit < 10000:
                    section += (number or 1) * unit
                else:
                    total += (section + number) * unit
                    section = 0
                number = 0
        result = Decimal(total + section + number)
    return -result if negative else result


def quantities(text, *, strict=True):
    text = re.sub(r"百分之(" + NUMBER + "|" + CHINESE + ")", r"\1%", text)
    values = []
    for match in TOKEN.finditer(text):
        raw = match["value"]
        if len(raw) > 40:
            raise invalid_answer()
        try:
            value = Decimal(raw) if re.fullmatch(NUMBER, raw) else chinese_number(raw)
        except (InvalidOperation, KeyError, ValueError):
            raise invalid_answer() from None
        prefix = re.split(
            r"[。；;\n，,]", text[max(0, match.start() - 32) : match.start()]
        )[-1]
        found = [
            (prefix.rfind(key) + len(key), len(key), category)
            for key, category in FIELDS.items()
            if key in prefix
        ]
        field = max(found)[2] if found else None
        unit = match["unit"]
        if unit:
            suffix = re.match(r"[A-Za-z]+", text[match.start("unit") :])
            if suffix is not None and suffix[0] != unit:
                if strict:
                    raise invalid_answer()
                values.append((value, "unknown:" + suffix[0], None))
                continue
            category, factor = UNITS[unit]
            if field and field != "quantity" and field != category:
                if strict:
                    raise invalid_answer()
                field = category
            value *= Decimal(factor)
        else:
            tail = text[match.end() : match.end() + 1]
            # 未登记的紧邻量词不能被默认为已支持的单位。
            if (
                tail
                and re.match(r"[A-Za-z\u4e00-\u9fff]", tail)
                and tail not in "的为是在与和或及并"
            ):
                category = "unknown:" + tail
            else:
                category = field
        values.append((value, category, field))
    return values


def validate_numbers(text, evidence):
    if re.search(r"\d[eE][-+]?\d", text):
        raise invalid_answer()
    source = "\n".join(evidence)
    if re.search(r"\d\s*[+*/=]\s*\d", text) and text not in source:
        raise invalid_answer()
    available = quantities(source, strict=False)
    for value, unit, field in quantities(text):
        if not any(
            abs(value - other) <= Decimal("1e-9") * max(abs(value), Decimal(1))
            and unit == other_unit
            and (field is None or other_field is None or field == other_field)
            for other, other_unit, other_field in available
        ):
            raise invalid_answer()


def assemble_evidence(items):
    evidence = []
    total = 0
    for item in items[:8]:
        size = len(item["text"])
        if total + size > 12000:
            break
        evidence.append(item)
        total += size
    return evidence


def validate_claims(payload, evidence):
    if (
        not isinstance(payload, dict)
        or payload.keys() != {"insufficient", "claims"}
        or type(payload["insufficient"]) is not bool
        or not isinstance(payload["claims"], list)
    ):
        raise invalid_answer()
    claims = payload["claims"]
    if payload["insufficient"]:
        if claims:
            raise invalid_answer()
        return None, []
    if not 1 <= len(claims) <= 16:
        raise invalid_answer()
    output = []
    cited = set()
    for claim in claims:
        if not isinstance(claim, dict) or claim.keys() != {"text", "evidence"}:
            raise invalid_answer()
        text, ids = claim["text"], claim["evidence"]
        if (
            not isinstance(text, str)
            or not 1 <= len(text.strip()) <= 2000
            or not isinstance(ids, list)
            or not ids
            or len(ids) > 8
            or any(
                type(number) is not int or not 1 <= number <= len(evidence)
                for number in ids
            )
            or len(set(ids)) != len(ids)
        ):
            raise invalid_answer()
        try:
            text.encode("utf-8")
        except UnicodeError:
            raise invalid_answer() from None
        if "\0" in text:
            raise invalid_answer()
        validate_numbers(text, [evidence[number - 1]["text"] for number in ids])
        output.append(text.strip())
        cited.update(ids)
    answer = "\n".join(output)
    if len(answer) > 12000:
        raise invalid_answer()
    return answer, sorted(cited)
