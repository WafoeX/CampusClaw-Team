"""Shared validation for manually entered and model generated questions."""

import re

from app.services.teaching import invalid

UUID_PATTERN = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")


def question_fields(payload):
    required = {"kind", "stem", "options", "answer", "explanation"}
    if not isinstance(payload, dict) or not required <= payload.keys() <= required | {
        "source_material_id"
    }:
        raise invalid()
    kind, stem, options, answer, explanation = (
        payload[key] for key in ("kind", "stem", "options", "answer", "explanation")
    )
    if (
        not isinstance(kind, str)
        or kind not in {"single_choice", "true_false"}
        or not isinstance(stem, str)
        or not isinstance(explanation, str)
    ):
        raise invalid()
    stem, explanation = stem.strip(), explanation.strip()
    if (
        not 1 <= len(stem) <= 2000
        or not 1 <= len(explanation) <= 2000
        or "\0" in stem + explanation
    ):
        raise invalid("题干或解析长度无效")
    if not isinstance(options, list) or any(
        not isinstance(option, str) for option in options
    ):
        raise invalid()
    options = [option.strip() for option in options]
    if kind == "single_choice":
        if (
            not 2 <= len(options) <= 6
            or any(
                not option or len(option) > 500 or "\0" in option for option in options
            )
            or len(set(options)) != len(options)
        ):
            raise invalid("单选题须有 2 至 6 个互异选项")
        if answer not in [chr(65 + index) for index in range(len(options))]:
            raise invalid("正确选项无效")
    elif options != ["正确", "错误"] or answer not in ("true", "false"):
        raise invalid("判断题须使用固定选项和答案")
    source = payload.get("source_material_id")
    if source is not None:
        if not isinstance(source, str):
            raise invalid()
        if not UUID_PATTERN.fullmatch(source):
            raise invalid("资料标识格式无效")
    return {
        "kind": kind,
        "stem": stem,
        "options": options,
        "answer": answer,
        "explanation": explanation,
        "source_material_id": source,
    }
