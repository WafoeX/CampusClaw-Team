"""本机 Docker 演示的真实 HTTPS/课程网关最小验证；凭据仅从环境读取。"""

import http.cookiejar
import json
import os
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4


def main():
    origin = os.environ["APP_PUBLIC_ORIGIN"]
    if urlsplit(origin).hostname not in (
        "localhost",
        "127.0.0.1",
    ) or not origin.startswith("https://"):
        raise SystemExit("真实烟测仅允许本机HTTPS演示入口")
    if not os.environ.get("MYSQL_DATABASE", "").startswith("campusclaw_test_"):
        raise SystemExit("真实烟测仅允许合成演示库")
    password = os.environ["CAMPUSCLAW_SEED_PASSWORD"]
    context = ssl.create_default_context(cafile="runtime/tls/localhost.crt")
    headers = {
        "Origin": origin,
        "X-CampusClaw-Request": "same-origin",
        "Content-Type": "application/json",
    }

    def client(name):
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=context),
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
        )
        _, body, _ = request(
            opener,
            "POST",
            "/api/v1/auth/sessions",
            {"login_name": name, "password": password},
        )
        assert body["code"] == 0
        return opener

    def request(opener, method, path, payload=None, expected=200):
        data = (
            None
            if payload is None
            else json.dumps(payload, ensure_ascii=False).encode()
        )
        request_headers = dict(headers)
        if method in ("POST", "PUT"):
            request_headers["Idempotency-Key"] = str(uuid4())
        started = time.monotonic()
        req = urllib.request.Request(
            origin + path, data=data, headers=request_headers, method=method
        )
        try:
            response = opener.open(req, timeout=40)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            body = json.load(response)
            elapsed = (time.monotonic() - started) * 1000
            assert response.status == expected, (
                "烟测HTTP失败",
                response.status,
                body.get("code"),
            )
            return response.status, body, elapsed

    teacher = client("demo_a_teacher")
    student = client("demo_a_student")
    outsider = client("demo_b_teacher")
    _, chapter, _ = request(
        teacher,
        "POST",
        "/api/v1/chapters",
        {"name": "真实网关烟测" + str(uuid4())[:8], "sort_order": 0},
        201,
    )
    scope = chapter["data"]["id"]
    source_ids = []
    for actor, title, text in [
        (teacher, "演示：合成电源", "合成电源的额定电压为24伏。"),
        (outsider, "演示：外班隔离", "紫铜螺旋仪编号为887766。"),
    ]:
        _, created, _ = request(
            actor, "POST", "/api/v1/materials", {"title": title, "text": text}, 201
        )
        target = created["data"]["id"]
        _, built, _ = request(
            actor, "POST", "/api/v1/materials/" + target + "/index-builds", {}, 201
        )
        assert built["data"]["status"] == "published"
        if actor is teacher:
            request(
                actor,
                "PUT",
                "/api/v1/materials/" + target + "/chapter-assignments/current",
                {"chapter_id": scope, "revision": created["data"]["revision"]},
            )
        source_ids.append(target)
    request(student, "GET", "/api/v1/materials/" + source_ids[1], expected=404)
    retrieval = {}
    for mode in ("keyword", "vector", "hybrid"):
        _, found, elapsed = request(
            student,
            "POST",
            "/api/v1/searches",
            {"query": "合成电源", "mode": mode, "chapter_scope": scope},
        )
        assert found["data"]["items"] and all(
            item["material_id"] == source_ids[0] for item in found["data"]["items"]
        )
        retrieval[mode] = {"passed": True, "duration_ms": elapsed}
    _, answered, elapsed = request(
        student,
        "POST",
        "/api/v1/material-answers",
        {
            "question": "合成电源的额定电压是多少？",
            "mode": "hybrid",
            "chapter_scope": scope,
        },
    )
    answer = answered["data"]
    assert answer["citations"] and all(
        item["material_id"] == source_ids[0] for item in answer["citations"]
    )
    assert "24" in answer["answer"] or "二十四" in answer["answer"]
    item = answer["citations"][0]
    path = (
        "/api/v1/materials/"
        + item["material_id"]
        + "/citations/"
        + item["chunk_id"]
        + "?source_version="
        + str(item["source_version"])
        + "&index_version="
        + str(item["index_version"])
    )
    _, opened, _ = request(student, "GET", path)
    assert opened["data"]["source_text"][item["start"] : item["end"]] == item["text"]
    _, empty, _ = request(
        student,
        "POST",
        "/api/v1/material-answers",
        {"question": "紫铜螺旋仪", "mode": "keyword", "chapter_scope": scope},
    )
    assert empty["data"] == {"answer": "资料中未找到相关内容", "citations": []}
    result = {
        "runtime": "本机Docker四服务，HTTPS验证本机CA，真实课程嵌入/对话网关",
        "retrieval": retrieval,
        "qa": {
            "passed": True,
            "duration_ms": elapsed,
            "citations": len(answer["citations"]),
            "request_id": answered["request_id"],
        },
        "cross_class_404": True,
        "no_evidence_refusal": True,
        "no_evidence_request_id": empty["request_id"],
        "samples_per_mode": 1,
        "performance_acceptance": False,
    }
    output = Path("reports/2026-11-06-index-builds/real-gateway-smoke.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
