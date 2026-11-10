"""题库、测验和正式提交接口。"""

from datetime import UTC, datetime

from flask import g, request
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from app.api.auth import COOKIE
from app.api.http import success
from app.api.materials import REQUEST_KEY, _json, _positive, _query, material_id
from app.services.materials import READ_MATERIALS
from app.services.teaching import TEACHING_ANSWER, TEACHING_WRITE, invalid

TEACHING_POLICIES = {
    (endpoint, method): permission
    for endpoint, methods, permission in (
        ("list_questions", ("GET", "HEAD"), TEACHING_WRITE),
        ("read_question", ("GET", "HEAD"), TEACHING_WRITE),
        ("create_question", ("POST",), TEACHING_WRITE),
        ("edit_question", ("PATCH",), TEACHING_WRITE),
        ("review_question", ("POST",), TEACHING_WRITE),
        ("list_quizzes", ("GET", "HEAD"), READ_MATERIALS),
        ("read_quiz", ("GET", "HEAD"), READ_MATERIALS),
        ("create_quiz", ("POST",), TEACHING_WRITE),
        ("publish_quiz", ("POST",), TEACHING_WRITE),
        ("read_quiz_draft", ("GET", "HEAD"), TEACHING_ANSWER),
        ("save_quiz_draft", ("PUT",), TEACHING_ANSWER),
        ("submit_quiz", ("POST",), TEACHING_ANSWER),
        ("read_my_submission", ("GET", "HEAD"), TEACHING_ANSWER),
        ("list_submission_results", ("GET", "HEAD"), TEACHING_WRITE),
    )
    for method in methods
}


def body(limit=16384):
    try:
        return _json(limit)
    except (BadRequest, RequestEntityTooLarge):
        raise invalid() from None


def exact(value, required, optional=()):
    if required - value.keys() or value.keys() - (required | set(optional)):
        raise invalid()


def revision(value, *, zero=False):
    if type(value) is not int or not (0 if zero else 1) <= value <= 2_000_000_000:
        raise invalid("修订号无效")
    return value


def question_fields(payload):
    required = {"kind", "stem", "options", "answer", "explanation"}
    exact(payload, required, {"source_material_id"})
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
    elif options != ["正确", "错误"] or answer not in {"true", "false"}:
        raise invalid("判断题须使用固定选项和答案")
    source = payload.get("source_material_id")
    if source is not None:
        if not isinstance(source, str):
            raise invalid()
        source = material_id(source)
    return {
        "kind": kind,
        "stem": stem,
        "options": options,
        "answer": answer,
        "explanation": explanation,
        "source_material_id": source,
    }


def timestamp(value):
    if not isinstance(value, str) or len(value) > 40:
        raise invalid("时间格式无效")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(UTC).replace(tzinfo=None)
    except ValueError:
        raise invalid("时间须包含时区") from None


def quiz_fields(payload):
    exact(payload, {"title", "chapter_id", "deadline_at", "answers_open_at", "items"})
    title = payload["title"]
    if (
        not isinstance(title, str)
        or not 1 <= len(title.strip()) <= 120
        or "\0" in title
    ):
        raise invalid("测验标题长度无效")
    chapter = payload["chapter_id"]
    if chapter is not None:
        if not isinstance(chapter, str):
            raise invalid()
        chapter = material_id(chapter)
    specs = payload["items"]
    if not isinstance(specs, list) or not 1 <= len(specs) <= 50:
        raise invalid("每份测验须有 1 至 50 题")
    items = []
    for spec in specs:
        if not isinstance(spec, dict):
            raise invalid()
        exact(spec, {"question_id", "points"})
        if (
            not isinstance(spec["question_id"], str)
            or type(spec["points"]) is not int
            or not 1 <= spec["points"] <= 100
        ):
            raise invalid()
        items.append(
            {"question_id": material_id(spec["question_id"]), "points": spec["points"]}
        )
    if len({item["question_id"] for item in items}) != len(items):
        raise invalid("测验不能重复引用同一题")
    return (
        title.strip(),
        chapter,
        timestamp(payload["deadline_at"]),
        timestamp(payload["answers_open_at"]),
        items,
    )


def answers_payload(payload):
    exact(payload, {"draft_revision", "answers"})
    rev = revision(payload["draft_revision"], zero=True)
    answers = payload["answers"]
    if (
        not isinstance(answers, dict)
        or len(answers) > 50
        or any(
            not isinstance(key, str) or not isinstance(value, str) or len(value) > 8
            for key, value in answers.items()
        )
    ):
        raise invalid("作答格式无效")
    return rev, answers


def submit_key():
    value = request.headers.get("Idempotency-Key", "")
    if not REQUEST_KEY.fullmatch(value):
        raise invalid("提交标识格式无效")
    return value.encode("ascii")


def install_teaching(app, service):
    @app.after_request
    def teaching_response(response):
        if request.path.startswith("/api/v1/questions") or request.path.startswith(
            "/api/v1/quizzes"
        ):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/v1/questions")
    def list_questions():
        _query(("page", "page_size"))
        return success(
            service.list_questions(
                g.identity,
                _positive("page", 1, 2**31 - 1),
                _positive("page_size", 20, 100),
            )
        )

    @app.get("/api/v1/questions/<value>")
    def read_question(value):
        _query()
        return success(service.read_question(g.identity, material_id(value)))

    @app.post("/api/v1/questions")
    def create_question():
        _query()
        return success(
            service.create_question(
                g.identity, request.cookies.get(COOKIE), question_fields(body())
            )
        ), 201

    @app.patch("/api/v1/questions/<value>")
    def edit_question(value):
        _query()
        payload = body()
        expected = revision(payload.pop("expected_version", None))
        return success(
            service.edit_question(
                g.identity,
                request.cookies.get(COOKIE),
                material_id(value),
                expected,
                question_fields(payload),
            )
        )

    @app.post("/api/v1/questions/<value>/reviews")
    def review_question(value):
        _query()
        payload = body()
        exact(payload, {"expected_version"})
        return success(
            service.review_question(
                g.identity,
                request.cookies.get(COOKIE),
                material_id(value),
                revision(payload["expected_version"]),
            )
        )

    @app.get("/api/v1/quizzes")
    def list_quizzes():
        _query(("page", "page_size"))
        return success(
            service.list_quizzes(
                g.identity,
                teacher=g.actor.role == "teacher",
                page=_positive("page", 1, 2**31 - 1),
                page_size=_positive("page_size", 20, 100),
            )
        )

    @app.get("/api/v1/quizzes/<value>")
    def read_quiz(value):
        _query()
        return success(
            service.read_quiz(
                g.identity, material_id(value), teacher=g.actor.role == "teacher"
            )
        )

    @app.post("/api/v1/quizzes")
    def create_quiz():
        _query()
        return success(
            service.create_quiz(
                g.identity, request.cookies.get(COOKIE), *quiz_fields(body())
            )
        ), 201

    @app.post("/api/v1/quizzes/<value>/publications")
    def publish_quiz(value):
        _query()
        exact(body(1024), set())
        return success(
            service.publish_quiz(
                g.identity, request.cookies.get(COOKIE), material_id(value)
            )
        )

    @app.get("/api/v1/quizzes/<value>/draft")
    def read_quiz_draft(value):
        _query()
        return success(service.read_draft(g.identity, material_id(value)))

    @app.put("/api/v1/quizzes/<value>/draft")
    def save_quiz_draft(value):
        _query()
        rev, answers = answers_payload(body())
        return success(
            service.save_draft(
                g.identity,
                request.cookies.get(COOKIE),
                material_id(value),
                rev,
                answers,
            )
        )

    @app.post("/api/v1/quizzes/<value>/submissions")
    def submit_quiz(value):
        _query()
        key = submit_key()
        rev, answers = answers_payload(body())
        return success(
            service.submit(
                g.identity,
                request.cookies.get(COOKIE),
                material_id(value),
                key,
                rev,
                answers,
            )
        ), 201

    @app.get("/api/v1/quizzes/<value>/my-submission")
    def read_my_submission(value):
        _query()
        return success(service.my_submission(g.identity, material_id(value)))

    @app.get("/api/v1/quizzes/<value>/submission-results")
    def list_submission_results(value):
        _query(("page", "page_size"))
        return success(
            service.submission_results(
                g.identity,
                material_id(value),
                _positive("page", 1, 100000),
                _positive("page_size", 20, 100),
            )
        )
