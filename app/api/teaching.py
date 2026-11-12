"""题库、测验和正式提交接口。"""

from datetime import UTC, datetime

from flask import g, request
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from app.api.auth import COOKIE
from app.api.http import success
from app.api.materials import REQUEST_KEY, _json, _positive, _query, material_id
from app.services.materials import READ_MATERIALS, unavailable
from app.services.teaching import TEACHING_ANSWER, TEACHING_WRITE, invalid
from app.services.teaching_question_fields import question_fields

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
        ("read_my_mistakes", ("GET", "HEAD"), TEACHING_ANSWER),
        ("read_quiz_insights", ("GET", "HEAD"), TEACHING_WRITE),
        ("list_mistakes", ("GET", "HEAD"), TEACHING_ANSWER),
        ("list_learning_insights", ("GET", "HEAD"), TEACHING_WRITE),
        ("create_generation_job", ("POST",), TEACHING_WRITE),
        ("read_teaching_job", ("GET", "HEAD"), TEACHING_WRITE),
        ("replay_teaching_job", ("POST",), TEACHING_WRITE),
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


def install_teaching(app, service, candidate_jobs=None):
    @app.after_request
    def teaching_response(response):
        if request.path.startswith(
            (
                "/api/v1/questions",
                "/api/v1/quizzes",
                "/api/v1/teaching-jobs",
                "/api/v1/question-generation-jobs",
                "/api/v1/mistakes",
                "/api/v1/learning-insights",
            )
        ):
            response.headers["Cache-Control"] = "no-store"
        return response

    def generation():
        if candidate_jobs is None:
            raise unavailable()
        return candidate_jobs

    @app.post("/api/v1/question-generation-jobs")
    def create_generation_job():
        _query()
        data = body()
        exact(data, {"count"}, {"chapter_id", "material_id"})
        keys = data.keys() & {"chapter_id", "material_id"}
        if (
            len(keys) != 1
            or type(data["count"]) is not int
            or not 1 <= data["count"] <= 10
        ):
            raise invalid()
        scope = {"chapter_id": None, "material_id": None, "count": data["count"]}
        key = keys.pop()
        if not isinstance(data[key], str):
            raise invalid()
        scope[key] = material_id(data[key])
        job = generation().admit(g.identity, request.cookies.get(COOKIE), scope)
        return (
            success(job),
            202,
            {"Location": f"/api/v1/teaching-jobs/{job['task_id']}"},
        )

    @app.get("/api/v1/teaching-jobs/<value>")
    def read_teaching_job(value):
        _query()
        return success(generation().read(g.identity, material_id(value)))

    def summaries(*, teacher):
        _query(("page", "page_size", "chapter_id", "quiz_id"))
        filters = {
            key: material_id(request.args[key])
            for key in ("chapter_id", "quiz_id")
            if key in request.args
        }
        return success(
            service.summaries(
                g.identity,
                teacher=teacher,
                page=_positive("page", 1, 1_000_000),
                page_size=_positive("page_size", 20, 100),
                **filters,
            )
        )

    @app.get("/api/v1/mistakes")
    def list_mistakes():
        return summaries(teacher=False)

    @app.get("/api/v1/learning-insights")
    def list_learning_insights():
        return summaries(teacher=True)

    @app.post("/api/v1/teaching-jobs/<value>/replays")
    def replay_teaching_job(value):
        _query()
        exact(body(), set())
        job = generation().replay(
            g.identity, request.cookies.get(COOKIE), material_id(value)
        )
        return (
            success(job),
            202,
            {"Location": f"/api/v1/teaching-jobs/{job['task_id']}"},
        )

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

    @app.get("/api/v1/quizzes/<value>/my-mistakes")
    def read_my_mistakes(value):
        _query()
        return success(service.my_mistakes(g.identity, material_id(value)))

    @app.get("/api/v1/quizzes/<value>/insights")
    def read_quiz_insights(value):
        _query()
        return success(service.insights(g.identity, material_id(value)))
