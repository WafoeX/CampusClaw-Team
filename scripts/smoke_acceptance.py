"""在本克隆专用 HTTPS 环境走通确定性教学链路，不调用真实模型。"""

import json
import ssl
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from http.cookiejar import CookieJar
from uuid import uuid4


def smoke(state, values):
    if (
        not values["MYSQL_DATABASE"].startswith("campusclaw_test_acceptance_")
        or values["APP_PUBLIC_ORIGIN"] != "https://localhost:8444"
    ):
        raise ValueError("烟测只允许本机专用合成环境")
    context = ssl.create_default_context(cafile=str(state / "tls/localhost.crt"))
    origin = values["APP_PUBLIC_ORIGIN"]
    checks = []

    def session(name):
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(CookieJar()),
            urllib.request.HTTPSHandler(context=context),
        )
        send(
            opener,
            "POST",
            "/api/v1/auth/sessions",
            {"login_name": name, "password": values["CAMPUSCLAW_SEED_PASSWORD"]},
        )
        return opener

    def send(opener, method, path, payload=None, expected=200, key=None):
        request = urllib.request.Request(
            origin + path,
            method=method,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={
                "Content-Type": "application/json",
                "Origin": origin,
                "X-CampusClaw-Request": "same-origin",
                "Idempotency-Key": key or uuid4().hex,
            },
        )
        try:
            response = opener.open(request, timeout=15)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            body = json.load(response)
            if response.status != expected or (
                expected < 400 and body.get("code") != 0
            ):
                raise ValueError(f"烟测请求未满足契约：{method} {path}")
            checks.append(
                {
                    "method": method,
                    "path": path,
                    "http": response.status,
                    "code": body.get("code"),
                }
            )
            return body

    teacher, student, outsider = [
        session(name) for name in ("demo_a_teacher", "demo_a_student", "demo_b_student")
    ]
    material = send(
        teacher,
        "POST",
        "/api/v1/materials",
        {"title": "预验收合成讲义", "text": "用于确定性教学闭环验证的合成资料"},
        201,
    )["data"]
    send(student, "GET", f"/api/v1/materials/{material['id']}")
    foreign = send(outsider, "GET", f"/api/v1/materials/{material['id']}", expected=404)
    missing = send(outsider, "GET", f"/api/v1/materials/{uuid4()}", expected=404)
    if any(foreign[key] != missing[key] for key in ("code", "message", "data")):
        raise ValueError("跨班与不存在的公开结果不一致")
    question = send(
        teacher,
        "POST",
        "/api/v1/questions",
        {
            "kind": "single_choice",
            "stem": "合成选择题",
            "options": ["甲", "乙"],
            "answer": "A",
            "explanation": "仅用于合成验收的解析",
        },
        201,
    )["data"]
    send(
        teacher,
        "POST",
        f"/api/v1/questions/{question['id']}/reviews",
        {"expected_version": 1},
    )
    now = datetime.now(UTC)
    quiz = send(
        teacher,
        "POST",
        "/api/v1/quizzes",
        {
            "title": "预验收合成测验",
            "chapter_id": None,
            "deadline_at": (now + timedelta(hours=1)).isoformat(),
            "answers_open_at": (now + timedelta(hours=2)).isoformat(),
            "items": [{"question_id": question["id"], "points": 5}],
        },
        201,
    )["data"]
    send(teacher, "POST", f"/api/v1/quizzes/{quiz['id']}/publications", {})
    view = send(student, "GET", f"/api/v1/quizzes/{quiz['id']}")["data"]
    if any("answer" in item or "explanation" in item for item in view["items"]):
        raise ValueError("答案开放前存在答案泄露")
    item_id = view["items"][0]["id"]
    draft = send(
        student,
        "PUT",
        f"/api/v1/quizzes/{quiz['id']}/draft",
        {"draft_revision": 0, "answers": {item_id: "A"}},
    )["data"]
    payload = {"draft_revision": draft["revision"], "answers": {item_id: "A"}}
    submit_key = uuid4().hex
    first = send(
        student,
        "POST",
        f"/api/v1/quizzes/{quiz['id']}/submissions",
        payload,
        202,
        submit_key,
    )["data"]
    repeated = send(
        student,
        "POST",
        f"/api/v1/quizzes/{quiz['id']}/submissions",
        payload,
        202,
        submit_key,
    )["data"]
    if first != repeated:
        raise ValueError("同键正式交卷没有保持幂等")
    for _ in range(120):
        task = send(student, "GET", f"/api/v1/submission-jobs/{first['task_id']}")[
            "data"
        ]
        if task["status"] == "succeeded":
            break
        if task["status"] == "failed":
            raise ValueError("正式交卷任务处理失败")
        time.sleep(0.25)
    else:
        raise ValueError("正式交卷任务未在时限内完成")
    insights = send(teacher, "GET", f"/api/v1/quizzes/{quiz['id']}/insights")["data"]
    if insights["submissions"] != 1 or insights["average_score"] != 5:
        raise ValueError("真实成绩或教师汇总与合成结果不一致")
    return {
        "revision": values["APP_BUILD_REVISION"],
        "origin": origin,
        "requests": len(checks),
        "checks": checks,
        "persisted_average_score": 5,
        "real_model_evaluation": "未执行",
        "human_acceptance": "未执行",
    }
