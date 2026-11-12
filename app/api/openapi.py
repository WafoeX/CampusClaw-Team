"""从已登记路由生成同源 OpenAPI；不读取业务数据或私有配置。"""

import re
from secrets import token_urlsafe

from flask import jsonify, make_response, render_template

from app.services.ai_contracts import AI_USE

DOC_POLICIES = {
    (endpoint, method): AI_USE
    for endpoint in ("openapi_document", "swagger_page")
    for method in ("GET", "HEAD")
}


def obj(properties, required=None):
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": list(properties) if required is None else required,
    }


TEXT = {"type": "string"}
ID = {"type": "string", "format": "uuid"}
REV = {"type": "integer", "minimum": 1, "maximum": 2_000_000_000}
ENABLED = {"type": "boolean"}
IDS = {"type": "array", "items": ID, "maxItems": 100, "uniqueItems": True}
VARIABLES = obj(
    {
        "input": {"type": "string", "minLength": 1, "maxLength": 4000},
        "audience": {"type": "string", "maxLength": 120},
    },
    ["input"],
)
CONFIG = {
    "name": {"type": "string", "minLength": 1, "maxLength": 64},
    "prompt": {"type": "string", "maxLength": 2000},
    "enabled": ENABLED,
}
SCOPE = {"type": "string", "description": "本班章节 UUID 或 uncategorized"}
MODE = {"type": "string", "enum": ["keyword", "vector", "hybrid"]}
TOOL_REF = {"type": "string", "pattern": r"^[a-z][a-z0-9_]{0,63}@[a-z][a-z0-9-]{0,62}$"}
SKILL = {
    "name": CONFIG["name"],
    "conditions": {"type": "array", "items": TEXT, "minItems": 1, "maxItems": 16},
    "enabled": ENABLED,
    "tools": {
        "type": "array",
        "items": {"oneOf": [{"enum": ["knowledge_search"]}, TOOL_REF]},
        "maxItems": 17,
        "uniqueItems": True,
    },
    "steps": {
        "type": "array",
        "minItems": 1,
        "maxItems": 3,
        "items": obj({"type": {"enum": ["model"]}, "instruction": TEXT}),
    },
}
REQUESTS = {
    "create_question": obj(
        {
            "kind": {"enum": ["single_choice", "true_false"]},
            "stem": TEXT,
            "options": {"type": "array", "items": TEXT, "minItems": 2, "maxItems": 6},
            "answer": TEXT,
            "explanation": TEXT,
            "source_material_id": ID,
        },
        ["kind", "stem", "options", "answer", "explanation"],
    ),
    "edit_question": obj(
        {
            "expected_version": REV,
            "kind": {"enum": ["single_choice", "true_false"]},
            "stem": TEXT,
            "options": {"type": "array", "items": TEXT},
            "answer": TEXT,
            "explanation": TEXT,
            "source_material_id": ID,
        },
        ["expected_version", "kind", "stem", "options", "answer", "explanation"],
    ),
    "review_question": obj({"expected_version": REV}),
    "create_quiz": obj(
        {
            "title": TEXT,
            "chapter_id": {"oneOf": [ID, {"type": "null"}]},
            "deadline_at": {"type": "string", "format": "date-time"},
            "answers_open_at": {"type": "string", "format": "date-time"},
            "items": {
                "type": "array",
                "items": obj(
                    {
                        "question_id": ID,
                        "points": {"type": "integer", "minimum": 1, "maximum": 100},
                    }
                ),
                "minItems": 1,
                "maxItems": 50,
            },
        }
    ),
    "publish_quiz": obj({}),
    "save_quiz_draft": obj(
        {
            "draft_revision": {"type": "integer", "minimum": 0},
            "answers": {"type": "object", "additionalProperties": TEXT},
        }
    ),
    "submit_quiz": obj(
        {
            "draft_revision": {"type": "integer", "minimum": 0},
            "answers": {"type": "object", "additionalProperties": TEXT},
        }
    ),
    "login": obj(
        {"login_name": TEXT, "password": {"type": "string", "format": "password"}}
    ),
    "create_templates": obj(
        CONFIG
        | {"app_key": {"enum": ["polish", "learning_plan", "practice", "material_qa"]}}
    ),
    "update_templates": obj(CONFIG | {"revision": REV}),
    "create_assistants": obj(CONFIG | {"material_ids": IDS, "skill_ids": IDS}),
    "update_assistants": obj(
        CONFIG | {"material_ids": IDS, "skill_ids": IDS, "revision": REV}
    ),
    "delete_ai_template": obj({"revision": REV}),
    "preview_ai_template": obj({"revision": REV, "variables": VARIABLES}),
    "run_ai_app": obj({"template_id": ID, "revision": REV, "variables": VARIABLES}),
    "create_skill": {
        "oneOf": [
            obj(SKILL),
            obj(
                {
                    "builtin_key": {"enum": ["problem_guidance", "learning_plan"]},
                    "enabled": ENABLED,
                }
            ),
        ]
    },
    "update_skill": {
        "oneOf": [
            obj(SKILL | {"revision": REV}),
            obj({"enabled": ENABLED, "revision": REV}),
        ]
    },
    "delete_skill": obj({"revision": REV}),
    "create_private_session": obj(
        {"assistant_id": ID, "mode": {"enum": ["material_qa", "problem_guidance"]}}
    ),
    "register_tool_connector": obj({"alias": TEXT, "key": TEXT}),
    "connect_tool_connector": obj({}),
    "review_connector_tool": obj(
        {
            "fingerprint": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
            "enabled": ENABLED,
        }
    ),
    "issue_unit_practice": obj({}),
    "send_private_message": obj(
        {
            "question": {"type": "string", "minLength": 2, "maxLength": 500},
            "chapter_scope": SCOPE,
            "retrieval_mode": MODE,
            "selected_tools": {
                "type": "array",
                "items": TOOL_REF,
                "maxItems": 3,
                "uniqueItems": True,
            },
            "practice_context": {
                "type": "string",
                "description": "当前会话签发的短期单位练习票据",
            },
        },
        ["question"],
    ),
    "search_materials": obj(
        {"query": TEXT, "mode": MODE, "chapter_scope": SCOPE}, ["query"]
    ),
    "answer_materials": obj(
        {"question": TEXT, "mode": MODE, "chapter_scope": SCOPE}, ["question"]
    ),
    "put_message_feedback": obj(
        {
            "rating": {"enum": ["helpful", "unresolved"]},
            "note": {"type": "string", "maxLength": 500},
            "expected_revision": {
                "type": "integer",
                "minimum": 0,
                "maximum": 2_147_483_647,
            },
        },
        ["rating", "expected_revision"],
    ),
    "handle_teaching_feedback": obj(
        {"expected_revision": REV, "status": {"enum": ["handled"]}}
    ),
    "create_generation_job": {
        "oneOf": [
            obj({scope: ID, "count": {"type": "integer", "minimum": 1, "maximum": 10}})
            for scope in ("chapter_id", "material_id")
        ]
    },
    "replay_teaching_job": obj({}),
}
KEYED = {
    "submit_quiz",
    "create_templates",
    "create_assistants",
    "create_private_session",
    "send_private_message",
    "issue_unit_practice",
    "run_ai_app",
}
ENDPOINTS = set(REQUESTS) | {
    "list_questions",
    "read_question",
    "list_quizzes",
    "read_quiz",
    "read_quiz_draft",
    "read_my_submission",
    "list_submission_results",
    "read_my_mistakes",
    "read_quiz_insights",
    "list_mistakes",
    "list_learning_insights",
    "read_teaching_job",
    "current_session",
    "logout",
    "ai_catalogue",
    "list_templates",
    "read_templates",
    "list_assistants",
    "read_assistants",
    "list_skills",
    "read_skill",
    "list_ai_runs",
    "read_ai_run",
    "list_private_sessions",
    "read_private_session",
    "read_history_citation",
    "list_teaching_feedback",
    "tool_connector_options",
    "list_tool_connectors",
    "read_tool_connector",
    "delete_tool_connector",
    "disconnect_tool_connector",
    "list_connector_tools",
    "tool_call_audit",
}
ENVELOPE = obj(
    {"code": {"type": "integer"}, "message": TEXT, "data": {}, "request_id": TEXT}
)


def document(app):
    paths = {}
    for rule in app.url_map.iter_rules():
        if rule.endpoint not in ENDPOINTS:
            continue
        path = re.sub(r"<([^>]+)>", r"{\1}", rule.rule)
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            endpoint = rule.endpoint
            parameters = [
                {"in": "path", "name": name, "required": True, "schema": TEXT}
                for name in sorted(rule.arguments)
            ]
            if method not in {"GET", "HEAD"}:
                parameters.append(
                    {
                        "in": "header",
                        "name": "X-CampusClaw-Request",
                        "required": True,
                        "schema": {"enum": ["same-origin"]},
                    }
                )
            if endpoint in KEYED:
                parameters.append(
                    {
                        "in": "header",
                        "name": "Idempotency-Key",
                        "required": True,
                        "schema": {
                            "type": "string",
                            "pattern": "^[A-Za-z0-9_-]{1,64}$",
                        },
                    }
                )
            if (
                endpoint.startswith("list_")
                and endpoint != "list_connector_tools"
                or endpoint in {"read_private_session", "tool_call_audit"}
            ):
                for name, default, maximum in (
                    ("page", 1, 1_000_000),
                    ("page_size", 20, 100),
                ):
                    parameters.append(
                        {
                            "in": "query",
                            "name": name,
                            "schema": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": maximum,
                                "default": default,
                            },
                        }
                    )
            if endpoint == "list_templates":
                parameters.append(
                    {
                        "in": "query",
                        "name": "app_key",
                        "schema": {
                            "enum": [
                                "polish",
                                "learning_plan",
                                "practice",
                                "material_qa",
                            ]
                        },
                    }
                )
            if endpoint == "list_teaching_feedback":
                parameters.append(
                    {
                        "in": "query",
                        "name": "status",
                        "schema": {
                            "enum": ["pending", "handled"],
                            "default": "pending",
                        },
                    }
                )
            if endpoint in {"list_mistakes", "list_learning_insights"}:
                parameters.extend(
                    {"in": "query", "name": name, "schema": ID}
                    for name in ("chapter_id", "quiz_id")
                )
            operation = {
                "operationId": endpoint,
                "summary": endpoint,
                "parameters": parameters,
                "responses": {
                    str(status): {
                        "description": description,
                        "content": {"application/json": {"schema": ENVELOPE}},
                    }
                    for status, description in (
                        (200, "成功或幂等回读，code=0"),
                        (400, "1000 参数非法"),
                        (401, "1100/1101 登录失效或失败"),
                        (403, "1200 权限或同源防护拒绝"),
                        (404, "1300 不存在或不可访问"),
                        (409, "1400 修订或幂等冲突"),
                        (429, "1600 限流"),
                        (502, "1501 模型输出无效"),
                        (503, "1500 依赖不可用"),
                    )
                },
            }
            if endpoint == "login":
                operation["security"] = []
            if endpoint in {"create_generation_job", "replay_teaching_job"}:
                operation["responses"]["202"] = {
                    "description": "任务与发件箱已提交，可按 Location 轮询。",
                    "headers": {"Location": {"schema": {"type": "string"}}},
                    "content": {"application/json": {"schema": ENVELOPE}},
                }
                del operation["responses"]["200"]
            elif endpoint.startswith("create_") or endpoint in {
                "run_ai_app",
                "submit_quiz",
            }:
                operation["responses"]["201"] = operation["responses"]["200"]
            if endpoint in REQUESTS:
                operation["requestBody"] = {
                    "required": True,
                    "content": {"application/json": {"schema": REQUESTS[endpoint]}},
                }
            if endpoint == "send_private_message":
                operation["responses"]["200"] = {
                    "description": "meta → delta* → 唯一 done 或 error；done 表示事务已提交。流前错误为 HTTP JSON；error/断流须丢弃未完成预览并回读。",
                    "content": {"text/event-stream": {"schema": TEXT}},
                }
            paths.setdefault(path, {})[method.lower()] = operation
    return {
        "openapi": "3.0.3",
        "info": {"title": "CampusClaw 同源接口", "version": "1"},
        "servers": [{"url": "/"}],
        "paths": paths,
        "security": [{"cookieSession": []}],
        "components": {
            "securitySchemes": {
                "cookieSession": {
                    "type": "apiKey",
                    "in": "cookie",
                    "name": "__Host-campusclaw_session",
                    "description": "通过同源登录设置 HttpOnly Cookie；浏览器自动携带，不能手填或读取。所有写请求由浏览器设置 Origin 并携带规定写入头。",
                }
            }
        },
    }


def install_openapi(app):
    @app.get("/api/v1/openapi.json")
    def openapi_document():
        response = jsonify(document(app))
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/swagger")
    def swagger_page():
        nonce = token_urlsafe(24)
        response = make_response(render_template("swagger.html", nonce=nonce))
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; "
            "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
        )
        return response
