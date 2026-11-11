"""教学工具的输入契约及纯计算实现。"""

import json
from decimal import Decimal, InvalidOperation

HINTS = {
    "linear_equation": (
        "先找出含未知数的项，考虑如何在等式两边做同一种运算。",
        "把你的结果代回原等式，分别计算左右两边并比较。",
    ),
    "fraction_comparison": (
        "观察两个分母，考虑把两个分数改写成相同分母的形式。",
        "确认改写前后的分数相等，再比较相同分母下的分子。",
    ),
    "triangle_area": (
        "从图中找出一条底边和与它垂直的高。",
        "确认所选的底与高互相垂直，并检查面积单位。",
    ),
}
UNITS = {
    "mm": ("length", Decimal("0.001")),
    "cm": ("length", Decimal("0.01")),
    "m": ("length", Decimal("1")),
    "km": ("length", Decimal("1000")),
    "g": ("mass", Decimal("0.001")),
    "kg": ("mass", Decimal("1")),
}
STAGES = ("start", "check")


def object_schema(properties):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def enum_schema(values):
    return {"type": "string", "enum": list(values)}


TOOLS = {
    "formula_hint": {
        "name": "formula_hint",
        "description": "提供指定数学主题的起步或检查提示。",
        "inputSchema": object_schema(
            {"topic": enum_schema(HINTS), "stage": enum_schema(STAGES)}
        ),
    },
    "unit_convert": {
        "name": "unit_convert",
        "description": "在普通练习中换算同量纲的长度或质量单位。",
        "inputSchema": object_schema(
            {
                "value": {
                    "type": "number",
                    "minimum": -1000000,
                    "maximum": 1000000,
                    "multipleOf": 0.000001,
                },
                "from_unit": enum_schema(UNITS),
                "to_unit": enum_schema(UNITS),
            }
        ),
    },
}


def call_tool(name, arguments):
    if type(name) is not str or name not in TOOLS or not isinstance(arguments, dict):
        raise ValueError
    properties = TOOLS[name]["inputSchema"]["properties"]
    if arguments.keys() != properties.keys():
        raise ValueError
    for key, schema in properties.items():
        if "enum" in schema and arguments[key] not in schema["enum"]:
            raise ValueError
    if name == "formula_hint":
        topic, stage = arguments["topic"], arguments["stage"]
        data = {
            "hint_id": f"{topic}:{stage}",
            "hint": HINTS[topic][STAGES.index(stage)],
        }
    else:
        value = arguments["value"]
        if type(value) not in (int, Decimal):
            raise ValueError
        try:
            value = Decimal(value)
            if (
                not value.is_finite()
                or abs(value) > 1000000
                or value != round(value, 6)
            ):
                raise ValueError
        except InvalidOperation:
            raise ValueError from None
        from_dimension, from_factor = UNITS[arguments["from_unit"]]
        to_dimension, to_factor = UNITS[arguments["to_unit"]]
        if from_dimension != to_dimension:
            return {
                "content": [{"type": "text", "text": "只支持同量纲单位换算。"}],
                "isError": True,
            }
        factor = from_factor / to_factor
        data = {
            "value": format((value * factor).normalize(), "f"),
            "unit": arguments["to_unit"],
            "factor": format(factor.normalize(), "f"),
        }
    return {
        "content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
        "isError": False,
    }
