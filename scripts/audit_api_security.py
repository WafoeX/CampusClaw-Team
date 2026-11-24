"""从本地 Flask 装配和既有断网测试生成逐接口安全审查报告。"""

import argparse
import json
import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from http.cookies import CookieError, SimpleCookie
from importlib import import_module
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from flask import g, request, request_finished

import app as campus
from app.api.auth import COOKIE
from app.api.operation_audit import CONFIGURATION_ENDPOINTS
from app.config import Settings
from app.services.ai_contracts import AI_CONFIGURE
from scripts.check_pytest import RequiredCases

ROOT = Path(__file__).resolve().parents[1]
LOGIN = ("POST", "/api/v1/auth/sessions")
CONFIG_RESOURCES = {"assistants", "prompt-templates", "skills"}
TEACHER_RESOURCES = {
    "operation-audits",
    "tool-connectors",
    "tool-connector-options",
    "tool-call-audit",
}


@dataclass
class Operation:
    method: str
    path: str
    endpoint: str
    statuses: set[int] = field(default_factory=set)
    findings: set[str] = field(default_factory=set)
    failed_tests: set[str] = field(default_factory=set)

    def row(self):
        if any(200 <= status < 300 for status in self.statuses):
            coverage = "已观察成功响应"
        elif self.statuses:
            coverage = "仅观察到非成功响应"
        else:
            coverage = "未观察"
        return {
            "method": self.method,
            "path": self.path,
            "coverage": coverage,
            "statuses": sorted(self.statuses),
            "findings": sorted(self.findings),
            "failed_tests": sorted(self.failed_tests),
        }


def inventory(app, policies, public_routes):
    operations = {}
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith("/api/v1/"):
            continue
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            key = method, rule.rule
            item = Operation(method, rule.rule, rule.endpoint)
            public = (rule.endpoint, rule.rule, method) in public_routes
            permission = policies.get((rule.endpoint, method))
            if public and key != LOGIN:
                item.findings.add("授权登记允许匿名访问受保护接口")
            elif key == LOGIN and not public:
                item.findings.add("登录入口缺少公开例外，核对匿名登录的可用性")
            elif not public and not permission:
                item.findings.add("缺少授权登记，默认拒绝；核对合法用户的可用性")
            parts = rule.rule.removeprefix("/api/v1/").split("/")
            if parts[0] in TEACHER_RESOURCES and permission != AI_CONFIGURE:
                item.findings.add("审计或连接器管理入口缺少教师配置权限登记")
            if (
                parts[0] in CONFIG_RESOURCES
                and len(parts) <= 2
                and method in {"POST", "PATCH", "PUT", "DELETE"}
            ):
                if permission != AI_CONFIGURE:
                    item.findings.add("配置写缺少教师配置权限登记")
                if rule.endpoint not in CONFIGURATION_ENDPOINTS:
                    item.findings.add("配置写缺少一次性 CSRF 令牌动作登记")
            operations[key] = item
    return operations


def local_inventory():
    settings = Settings(
        mysql_host="mysql.invalid",
        mysql_port=3306,
        mysql_database="campusclaw_test_inventory",
        mysql_user="fixture",
        mysql_password="",
        qdrant_url="http://qdrant.invalid",
        qdrant_api_key="",
        version="local-audit",
        public_origin="https://campusclaw.test",
    )
    # 截取工厂实际传入的许可表，保留原注册行为；不复制生产许可表。
    with patch.object(campus, "install_http", wraps=campus.install_http) as install:
        app = campus.create_app(
            settings,
            health=Mock(),
            auth=Mock(),
            materials=Mock(),
            chapters=Mock(),
            limiter=Mock(),
            indexing=Mock(),
            retrieval=Mock(),
            answers=Mock(),
            ai_apps=Mock(),
            teaching=Mock(),
            candidate_jobs=Mock(),
            tool_connectors=Mock(),
        )
    registration = install.call_args.kwargs
    operations = inventory(app, registration["policies"], registration["public_routes"])
    with (
        patch.object(sys, "path", [str(ROOT / "mcp-server"), *sys.path]),
        patch.dict(os.environ, MCP_SERVICE_TOKEN="local-test-fixture"),
    ):
        mcp_app = import_module("teaching_server").create_app()
    for rule in mcp_app.url_map.iter_rules():
        if rule.rule == "/mcp":
            for method in rule.methods - {"HEAD", "OPTIONS"}:
                operations[method, rule.rule] = Operation(
                    method, rule.rule, rule.endpoint
                )
    return operations


def observe(operations, sender, response):
    if request.url_rule is None:
        return
    key = request.method, request.url_rule.rule
    mcp = key[1] == "/mcp"
    if sender.import_name != ("teaching_server" if mcp else campus.__name__):
        return
    item = operations.get(key)
    if item is None or request.endpoint != item.endpoint:
        return
    item.statuses.add(response.status_code)
    if mcp:
        if "Mcp-Session-Id" in response.headers and not response.cache_control.no_store:
            item.findings.add("初始化响应含 MCP 会话标识，缺少 Cache-Control: no-store")
        if 200 <= response.status_code < 300 and (
            not request.headers.get("Authorization", "").startswith("Bearer ")
            or "Origin" in request.headers
        ):
            item.findings.add("MCP 接受了缺少 Bearer 头或携带浏览器 Origin 的请求")
        return key
    if 200 <= response.status_code < 300:
        if not response.cache_control.no_store:
            item.findings.add("成功响应缺少 Cache-Control: no-store")
        if key != LOGIN and g.get("identity") is None:
            item.findings.add("受保护接口在缺少服务端身份时返回成功")
    for header in response.headers.getlist("Set-Cookie"):
        if header.partition("=")[0].strip() != COOKIE:
            continue
        cookie = SimpleCookie()
        try:
            cookie.load(header)
        except CookieError:
            item.findings.add("会话 Cookie 格式无法解析")
            continue
        session = cookie.get(COOKIE)
        if not session or not (
            session["secure"]
            and session["httponly"]
            and session["samesite"].lower() == "strict"
            and session["path"] == "/"
            and not session["domain"]
        ):
            item.findings.add("会话 Cookie 缺少规定的安全属性或主机限制")
    return key


class TestEvidence:
    def __init__(self, operations):
        self.operations = operations
        self.touched = set()

    def pytest_runtest_logstart(self, nodeid, location):
        self.touched.clear()

    def capture(self, sender, response, **kwargs):
        key = observe(self.operations, sender, response)
        if key is not None:
            self.touched.add(key)

    def pytest_runtest_logreport(self, report):
        if report.failed:
            # 参数化用例的 ID 可能含用户输入，只留模块和函数名。
            name = report.nodeid.partition("[")[0]
            for key in self.touched:
                self.operations[key].failed_tests.add(name)


def build_report(operations, suite_exit):
    rows = [operations[key].row() for key in sorted(operations)]
    observed = sum(bool(row["statuses"]) for row in rows)
    flagged = sum(bool(row["findings"]) for row in rows)
    complete = suite_exit == 0 and observed > 0
    return {
        "scope": "本地主应用 /api/v1/ 与教学服务 /mcp，不含 HEAD、OPTIONS；响应来自 tests/api 断网套件",
        "total": len(rows),
        "observed": observed,
        "observed_success": sum(row["coverage"] == "已观察成功响应" for row in rows),
        "flagged": flagged,
        "pytest_exit": int(suite_exit),
        "exit_code": 2 if not complete else int(flagged > 0),
        "operations": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="向标准输出写入 JSON")
    parser.add_argument(
        "--all", action="store_true", help="文本中列出所有接口与观测状态"
    )
    args = parser.parse_args()
    try:
        operations = local_inventory()
    except Exception as error:
        print(
            f"本地应用装配失败（{type(error).__name__}），检查未完成。", file=sys.stderr
        )
        return 2
    evidence = TestEvidence(operations)

    with (
        request_finished.connected_to(evidence.capture),
        open(os.devnull, "w") as quiet,
        redirect_stdout(quiet),
        redirect_stderr(quiet),
        patch.dict(os.environ, PYTEST_ADDOPTS=""),
    ):
        suite_exit = pytest.main(
            ["-q", "--disable-socket", str(ROOT / "tests/api")],
            plugins=[RequiredCases(), evidence],
        )
    report = build_report(operations, suite_exit)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(report["scope"])
        print(
            f"登记 {report['total']}，有成功响应 {report['observed_success']}，"
            f"仅有非成功响应 {report['observed'] - report['observed_success']}，"
            f"未观察 {report['total'] - report['observed']}，规则告警 {report['flagged']}"
        )
        for row in report["operations"]:
            if not (args.all or row["findings"] or row["failed_tests"]):
                continue
            detail = "、".join(row["findings"]) or "本次规则无告警"
            statuses = "/".join(map(str, row["statuses"])) or "—"
            print(
                f"{row['method']:6} {row['path']}  {row['coverage']} ({statuses})  {detail}"
            )
            if row["failed_tests"]:
                print(
                    "  涉及该接口的失败用例（待定位）", "、".join(row["failed_tests"])
                )
    if report["exit_code"] == 2:
        print(
            f"检查未完成（pytest 退出 {suite_exit}）。请单独运行 tests/api 查看诊断。",
            file=sys.stderr,
        )
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
