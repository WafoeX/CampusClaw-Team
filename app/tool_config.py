"""部署级工具目录。部署项只允许封闭枚举及有界数值传输。"""

import ipaddress
import json
import math
import re
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from urllib.parse import urlsplit

KEY = re.compile(r"[a-z][a-z0-9-]{0,62}")
NAME = re.compile(r"[a-z][a-z0-9_]{0,63}")
PATH = re.compile(r"/(?:[a-zA-Z0-9_-]+/)*[a-zA-Z0-9_-]+")
HOST = re.compile(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?")
ENUM_INPUT = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}")
DECIMAL_TEXT = re.compile(r"-?[0-9]{1,13}(?:\.[0-9]{1,12})?")
MODES = {"material_qa", "problem_guidance"}
UNITS = ["mm", "cm", "m", "km", "g", "kg"]


def required(condition):
    if not condition:
        raise ValueError("工具部署目录配置无效")


def shape(row, mandatory, optional=()):
    required(
        isinstance(row, dict)
        and set(mandatory) <= row.keys() <= set(mandatory) | set(optional)
    )


def matches(pattern, value):
    return isinstance(value, str) and bool(pattern.fullmatch(value))


def number(value):
    return type(value) in (int, float) and abs(value) <= 10**12 and math.isfinite(value)


def properties(fields, *, output=False):
    required(isinstance(fields, dict) and 1 <= len(fields) <= 8)
    schema = {}
    for key, row in fields.items():
        required(matches(NAME, key) and isinstance(row, dict))
        kind = row.get("type")
        if kind == "number":
            shape(row, ("type", "minimum", "maximum"), ("scale",))
            scale = row.get("scale", 6)
            required(
                number(row["minimum"])
                and number(row["maximum"])
                and row["minimum"] <= row["maximum"]
                and type(scale) is int
                and 0 <= scale <= 6
            )
            schema[key] = {
                "type": "number",
                "minimum": row["minimum"],
                "maximum": row["maximum"],
                "multipleOf": 10**-scale,
            }
        elif kind == "decimal_text" and output:
            shape(row, ("type",))
            schema[key] = {"type": "string", "pattern": DECIMAL_TEXT.pattern}
        else:
            shape(row, ("type", "enum"))
            items = row["enum"]
            required(
                kind == "string"
                and isinstance(items, list)
                and 1 <= len(items) <= 32
                and all(
                    isinstance(item, str)
                    and (1 <= len(item) <= 120 if output else matches(ENUM_INPUT, item))
                    and not any(char in item for char in "\r\n<>")
                    and "://" not in item
                    for item in items
                )
                and len(set(items)) == len(items)
            )
            schema[key] = row
    return schema


def valid_fields(data, schema):
    if not isinstance(data, dict) or data.keys() != schema.keys():
        return False
    for name, rules in schema.items():
        value = data[name]
        if rules["type"] == "number":
            if (
                not number(value)
                or not rules["minimum"] <= value <= rules["maximum"]
                or Decimal(str(value)) % Decimal(str(rules["multipleOf"])) != 0
            ):
                return False
        elif "enum" in rules:
            if not isinstance(value, str) or value not in rules["enum"]:
                return False
        elif not matches(DECIMAL_TEXT, value):
            return False
    return True


@dataclass(frozen=True, repr=False)
class ToolPolicy:
    definition: dict
    modes: frozenset
    result: dict
    path: str | None = None

    def accepts(self, data):
        return valid_fields(data, self.definition["inputSchema"]["properties"])

    def accepts_result(self, data):
        return valid_fields(data, self.result)


@dataclass(frozen=True, repr=False)
class Target:
    key: str
    label: str
    protocol: str
    scheme: str
    host: str
    port: int
    path: str
    network: ipaddress.IPv4Network | None
    token: str
    credential_required: bool
    tools: dict
    version: str

    def headers(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}


def policy(name, row, protocol):
    required(matches(NAME, name))
    mandatory = ["description", "modes", "parameters", "result"]
    if protocol == "http":
        mandatory.append("path")
    shape(row, mandatory)
    modes = row["modes"]
    required(
        isinstance(row["description"], str)
        and 1 <= len(row["description"]) <= 120
        and isinstance(modes, list)
        and 1 <= len(modes) <= 2
        and all(isinstance(mode, str) and mode in MODES for mode in modes)
        and (protocol != "http" or matches(PATH, row["path"]))
    )
    params = properties(row["parameters"])
    definition = {
        "name": name,
        "description": row["description"],
        "inputSchema": {
            "type": "object",
            "properties": params,
            "required": list(params),
            "additionalProperties": False,
        },
    }
    return ToolPolicy(
        definition,
        frozenset(modes),
        properties(row["result"], output=True),
        row.get("path"),
    )


def enum(values):
    return {"type": "string", "enum": values}


def teaching_service():
    topics = ["linear_equation", "fraction_comparison", "triangle_area"]
    stages = ["start", "check"]
    return {
        "key": "teaching",
        "label": "本地教学工具",
        "protocol": "mcp",
        "url": "http://mcp-server:8090/mcp",
        "credential": "MCP_SERVICE_TOKEN",
        "tools": {
            "formula_hint": {
                "description": "提供数学主题的起步或检查提示。",
                "modes": ["material_qa", "problem_guidance"],
                "parameters": {"topic": enum(topics), "stage": enum(stages)},
                "result": {
                    "hint_id": enum(
                        [f"{topic}:{stage}" for topic in topics for stage in stages]
                    ),
                    "hint": enum(
                        [
                            "先找出含未知数的项，考虑如何在等式两边做同一种运算。",
                            "把你的结果代回原等式，分别计算左右两边并比较。",
                            "观察两个分母，考虑把两个分数改写成相同分母的形式。",
                            "确认改写前后的分数相等，再比较相同分母下的分子。",
                            "从图中找出一条底边和与它垂直的高。",
                            "确认所选的底与高互相垂直，并检查面积单位。",
                        ]
                    ),
                },
            },
            "unit_convert": {
                "description": "用于普通练习的同量纲换算。",
                "modes": ["material_qa"],
                "parameters": {
                    "value": {
                        "type": "number",
                        "minimum": -1000000,
                        "maximum": 1000000,
                    },
                    "from_unit": enum(UNITS),
                    "to_unit": enum(UNITS),
                },
                "result": {
                    "value": {"type": "decimal_text"},
                    "factor": {"type": "decimal_text"},
                    "unit": enum(UNITS),
                },
            },
        },
    }


def target(row, env, network=None):
    shape(row, ("key", "label", "protocol", "url", "tools"), ("credential",))
    key, label, protocol = (row[field] for field in ("key", "label", "protocol"))
    required(
        matches(KEY, key)
        and isinstance(label, str)
        and 1 <= len(label) <= 64
        and protocol in ("mcp", "http")
        and isinstance(row["url"], str)
        and all(33 <= ord(char) < 127 for char in row["url"])
    )
    address = urlsplit(row["url"])
    host, port = address.hostname, address.port
    required(
        address.scheme == ("http" if network else "https")
        and matches(HOST, host)
        and (port is None or port > 0)
        and not (
            address.username or address.password or address.query or address.fragment
        )
        and matches(PATH, address.path)
    )
    port = port or 443
    required(address.netloc in {host, f"{host}:{port}"})
    key_name = row.get("credential", "")
    required(
        isinstance(key_name, str)
        and (
            not key_name
            or key_name == "MCP_SERVICE_TOKEN"
            or bool(re.fullmatch(r"TOOL_TOKEN_[A-Z0-9_]{1,48}", key_name))
        )
    )
    token = env.get(key_name, "")
    required(len(token) <= 512 and all(33 <= ord(char) <= 126 for char in token))
    tools = row["tools"]
    required(isinstance(tools, dict) and 1 <= len(tools) <= 32)
    version = sha256(
        json.dumps([row, str(network)], sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    return Target(
        key,
        label,
        protocol,
        address.scheme,
        host,
        port,
        address.path,
        network,
        token,
        bool(key_name),
        {
            name: policy(name, definition, protocol)
            for name, definition in tools.items()
        },
        version,
    )


def load_tool_directory(env):
    entries = json.loads(env.get("TOOL_CONNECTOR_DIRECTORY") or "[]")
    required(isinstance(entries, list) and len(entries) <= 16)
    directory = {}
    subnet = env.get("MCP_SERVICE_NETWORK")
    if subnet:
        network = ipaddress.IPv4Network(subnet)
        required(
            any(
                network.subnet_of(ipaddress.IPv4Network(private))
                for private in (
                    "10.0.0.0/8",
                    "172.16.0.0/12",
                    "192.168.0.0/16",
                )
            )
        )
        item = target(teaching_service(), env, network)
        directory[item.key] = item
    for entry in entries:
        item = target(entry, env)
        required(item.key != "teaching" and item.key not in directory)
        directory[item.key] = item
    return directory
