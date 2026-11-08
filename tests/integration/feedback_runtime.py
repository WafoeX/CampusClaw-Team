"""FB-N01/B01/B02/F01–04，嵌入AI真实依赖夹具，共用其合成身份与当前服务。"""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import event, insert, select, update
from sqlalchemy.exc import OperationalError

from app.adapters.assistant_schema_v8 import (
    citations,
    feedback,
    messages,
    operations,
    runs,
)
from app.adapters.database import DatabaseError
from app.adapters.index_cleanup_repository import IndexCleanupRepository
from app.adapters.index_clients import IndexDependencyError, QdrantIndexClient
from app.adapters.index_schema_v5 import chunks
from app.adapters.index_schema_v5 import materials as indexed_materials
from app.adapters.index_schema_v7 import builds as fb_builds
from app.adapters.index_schema_v7 import cleanups
from app.adapters.material_schema_v2 import bodies
from app.config import EmbeddingSettings
from app.services.index_cleanup import IndexCleanupService
from app.services.index_scope import IndexScope


def verify_feedback(
    *,
    request,
    settings,
    class_ids,
    actor_ids,
    engine,
    now,
    frames,
    count,
    repo,
    service,
):
    fb_material = request(
        "a_teacher",
        "POST",
        "/api/v1/materials",
        {"title": "历史出处合成原文", "text": "合成原文"},
        "feedback-source",
    ).json["data"]["id"]
    fb_chunk = str(uuid4())
    fb_config = EmbeddingSettings(
        "https://ai-gateway.devops.hello1023.com/v1", "synthetic", "course-embedding", 2
    )
    fb_vectors = QdrantIndexClient(
        settings.qdrant_url, settings.qdrant_api_key, fb_config
    )
    fb_vectors.ensure_collection(time.monotonic() + 35)
    fb_scope = IndexScope(class_ids["a"], fb_material, 1, 1, fb_config.version)
    fb_vectors.write(
        fb_scope, [SimpleNamespace(id=fb_chunk)], [[1.0, 0.0]], time.monotonic() + 35
    )
    with engine.begin() as connection:
        connection.execute(
            insert(fb_builds).values(
                id=str(uuid4()),
                class_id=class_ids["a"],
                material_id=fb_material,
                creator_id=actor_ids["a_teacher"],
                source_version=1,
                index_version=1,
                index_config_version=fb_config.version,
                vector_collection=fb_config.collection,
                mode="auto",
                window_size=100,
                overlap=0,
                status="keyword_only",
                stage="complete",
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            insert(chunks).values(
                id=fb_chunk,
                class_id=class_ids["a"],
                material_id=fb_material,
                source_version=1,
                index_version=1,
                index_config_version=fb_config.version,
                ordinal=0,
                start_offset=0,
                end_offset=4,
                content="合成原文",
            )
        )
        connection.execute(
            update(indexed_materials)
            .where(indexed_materials.c.id == fb_material)
            .values(active_index_version=1, desired_index_version=1)
        )
    fb_assistant = request(
        "a_teacher",
        "POST",
        "/api/v1/assistants",
        {
            "name": "反馈助手",
            "prompt": "",
            "enabled": True,
            "material_ids": [fb_material],
            "skill_ids": [],
        },
        "feedback-assistant",
    )
    assert fb_assistant.status_code == 201, fb_assistant.json
    fb_created = request(
        "session",
        "POST",
        "/api/v1/sessions",
        {"assistant_id": fb_assistant.json["data"]["id"], "mode": "material_qa"},
        "feedback-session",
    )
    fb_path = "/api/v1/sessions/" + fb_created.json["data"]["id"]
    fb_chapter = request(
        "a_teacher",
        "POST",
        "/api/v1/chapters",
        {"name": "反馈章节", "sort_order": 0},
        "feedback-chapter",
    ).json["data"]["id"]
    assert (
        request(
            "a_teacher",
            "PUT",
            "/api/v1/materials/" + fb_material + "/chapter-assignments/current",
            {"chapter_id": fb_chapter, "revision": 1},
            "feedback-assignment",
        ).status_code
        == 200
    )
    fb_question = {"question": "合成原文", "chapter_scope": fb_chapter}
    fb_key = "feedback-message"
    fb_frames = frames(
        request("session", "POST", fb_path + "/messages", fb_question, fb_key)
    )
    assert fb_frames[-1][0] == "done", fb_frames
    fb_message = fb_frames[-1][1]["data"]["message_id"]
    fb_run = fb_frames[-1][1]["data"]["run_id"]
    fb_message_path = fb_path + "/messages/" + fb_message
    fb_citation = fb_message_path + "/citations/1"
    fb_feedback = fb_message_path + "/feedback"
    assert request("session", "GET", fb_citation).json["data"]["excerpt"] == "合成原文"
    # 私有资源：同班同学、教师、外班和缺失同构，反馈没有旁路。
    for who in ("student", "other", "a_teacher", "b_teacher", "session_b_student"):
        assert request(who, "GET", fb_citation).status_code == 404
        assert (
            request(who, "GET", fb_citation.replace(fb_message, str(uuid4()))).json[
                "code"
            ]
            == 1300
        )
        denied = request(
            who,
            "PUT",
            fb_feedback,
            {"rating": "unresolved", "note": "私有卡点", "expected_revision": 0},
        )
        assert denied.status_code == (
            403 if who in ("a_teacher", "b_teacher") else 404
        ), denied.json
    for invalid in (
        {"rating": "unknown", "expected_revision": 0},
        {"rating": "unresolved", "note": " ", "expected_revision": 0},
        {"rating": "unresolved", "note": "字" * 501, "expected_revision": 0},
        {"rating": "helpful", "class_id": "b", "expected_revision": 0},
    ):
        assert request("session", "PUT", fb_feedback, invalid).status_code == 400
    fb_user = request("session", "GET", fb_path).json["data"]["messages"][0]["id"]
    assert (
        request(
            "session",
            "PUT",
            fb_path + "/messages/" + fb_user + "/feedback",
            {"rating": "helpful", "expected_revision": 0},
        ).status_code
        == 409
    )
    fb_failed_session = request(
        "session",
        "POST",
        "/api/v1/sessions",
        {"assistant_id": fb_assistant.json["data"]["id"], "mode": "material_qa"},
        "feedback-failed-session",
    ).json["data"]["id"]
    service.chat.failure = "invalid"
    try:
        fb_failed_frames = frames(
            request(
                "session",
                "POST",
                "/api/v1/sessions/" + fb_failed_session + "/messages",
                {"question": "合成原文"},
                "feedback-failed-message",
            )
        )
        assert fb_failed_frames[-1][0] == "error"
    finally:
        service.chat.failure = None
    # 先等待模型生产者退出再交接，避免并发租约混淆反馈状态断言。
    until = time.monotonic() + 3
    while service.capacity.active and time.monotonic() < until:
        time.sleep(0.01)
    fb_failed_user = request(
        "session", "GET", "/api/v1/sessions/" + fb_failed_session
    ).json["data"]["messages"][0]["id"]
    assert (
        request(
            "session",
            "PUT",
            "/api/v1/sessions/"
            + fb_failed_session
            + "/messages/"
            + fb_failed_user
            + "/feedback",
            {"rating": "helpful", "expected_revision": 0},
        ).status_code
        == 409
    )
    fb_note = {
        "rating": "unresolved",
        "note": "  不理解引用步骤  ",
        "expected_revision": 0,
    }
    fb_saved = request("session", "PUT", fb_feedback, fb_note)
    assert fb_saved.status_code == 200, fb_saved.json
    fb_id = fb_saved.json["data"]["id"]
    fb_total = count(feedback)
    assert request("session", "PUT", fb_feedback, fb_note).json["data"]["revision"] == 1
    assert count(feedback) == fb_total
    fb_queue = request("a_teacher", "GET", "/api/v1/teaching-feedback").json["data"]
    fb_item = next(row for row in fb_queue["items"] if row["id"] == fb_id)
    assert set(fb_item) == {
        "id",
        "rating",
        "note",
        "status",
        "revision",
        "chapter",
        "updated_at",
    }
    assert fb_item["note"] == "不理解引用步骤"
    assert fb_item["chapter"] == "反馈章节"
    assert (
        request("session", "GET", fb_path).json["data"]["messages"][-1][
            "feedback_chapter"
        ]
        == "反馈章节"
    )
    assert (
        request("b_teacher", "GET", "/api/v1/teaching-feedback").json["data"]["total"]
        == 0
    )
    assert request("student", "GET", "/api/v1/teaching-feedback").status_code == 403
    fb_handle = "/api/v1/teaching-feedback/" + fb_id
    assert (
        request(
            "student", "PATCH", fb_handle, {"status": "handled", "expected_revision": 1}
        ).status_code
        == 403
    )
    assert (
        request(
            "b_teacher",
            "PATCH",
            fb_handle,
            {"status": "handled", "expected_revision": 1},
        ).status_code
        == 404
    )
    assert (
        request(
            "b_teacher",
            "PATCH",
            fb_handle.replace(fb_id, str(uuid4())),
            {"status": "handled", "expected_revision": 1},
        ).json["code"]
        == 1300
    )
    fb_handled = request(
        "a_teacher", "PATCH", fb_handle, {"status": "handled", "expected_revision": 1}
    )
    assert fb_handled.json["data"]["revision"] == 2, fb_handled.json
    assert (
        request(
            "a_teacher",
            "PATCH",
            fb_handle,
            {"status": "handled", "expected_revision": 1},
        ).json["data"]["revision"]
        == 2
    )
    assert (
        request("session", "PUT", fb_feedback, fb_note).json["data"]["status"]
        == "handled"
    )
    assert (
        request("a_teacher", "GET", "/api/v1/teaching-feedback").json["data"]["total"]
        == fb_queue["total"] - 1
    )
    assert (
        request(
            "session",
            "PUT",
            fb_feedback,
            {"rating": "unresolved", "note": "新的学习卡点", "expected_revision": 1},
        ).status_code
        == 409
    )
    assert (
        request(
            "session",
            "PUT",
            fb_feedback,
            {"rating": "unresolved", "note": "新的学习卡点", "expected_revision": 2},
        ).json["data"]["revision"]
        == 3
    )
    assert (
        request("a_teacher", "GET", "/api/v1/teaching-feedback").json["data"]["total"]
        == fb_queue["total"]
    )
    assert (
        request(
            "session", "PUT", fb_feedback, {"rating": "helpful", "expected_revision": 3}
        ).json["data"]["revision"]
        == 4
    )
    assert (
        request("a_teacher", "GET", "/api/v1/teaching-feedback").json["data"]["total"]
        == fb_queue["total"] - 1
    )
    # FB-F04实际更新失败，证明未写入且不丢原状态。
    fb_fault = {"count": 0}

    def fb_fail(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.startswith("UPDATE teaching_feedback"):
            fb_fault["count"] += 1
            raise OperationalError("synthetic-feedback-failure", {}, None)

    event.listen(engine, "before_cursor_execute", fb_fail)
    try:
        failed = request(
            "session",
            "PUT",
            fb_feedback,
            {"rating": "unresolved", "note": "故障不可提交", "expected_revision": 4},
        )
        assert failed.status_code == 503 and failed.json["code"] == 1500
        assert fb_fault["count"] == 1
    finally:
        event.remove(engine, "before_cursor_execute", fb_fail)
    assert (
        request("session", "GET", fb_path).json["data"]["messages"][-1]["feedback"][
            "revision"
        ]
        == 4
    )
    # 同一旧修订的并发改评仅一笔成功；另一个必须显式冲突。
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                request,
                "session",
                "PUT",
                fb_feedback,
                {"rating": "unresolved", "note": note, "expected_revision": 4},
            )
            for note in ("并发卡点甲", "并发卡点乙")
        ]
        outcomes = [future.result().status_code for future in futures]
    assert sorted(outcomes) == [200, 409], outcomes
    assert count(feedback) == fb_total
    # 重建后只读旧快照，不把版本指向新切片。
    with engine.begin() as connection:
        connection.execute(
            insert(fb_builds).values(
                id=str(uuid4()),
                class_id=class_ids["a"],
                material_id=fb_material,
                creator_id=actor_ids["a_teacher"],
                source_version=1,
                index_version=2,
                index_config_version=fb_config.version,
                vector_collection=fb_config.collection,
                mode="auto",
                window_size=100,
                overlap=0,
                status="keyword_only",
                stage="complete",
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            insert(chunks).values(
                id=str(uuid4()),
                class_id=class_ids["a"],
                material_id=fb_material,
                source_version=1,
                index_version=2,
                index_config_version=fb_config.version,
                ordinal=0,
                start_offset=0,
                end_offset=4,
                content="新建切片",
            )
        )
        connection.execute(
            update(indexed_materials)
            .where(indexed_materials.c.id == fb_material)
            .values(active_index_version=2, desired_index_version=2)
        )
    historical = request("session", "GET", fb_citation).json["data"]
    assert (
        historical["status"] == "historical"
        and historical["excerpt"] == "合成原文"
        and historical["location"]["index_version"] == 1
    )
    assert "新建切片" not in json.dumps(historical, ensure_ascii=False)
    # 仅恢复这个会话的行级备份；保留独立删除清单，清理中断仍禁止读副本。
    fb_backup = {}
    with engine.connect() as connection:
        fb_original = dict(
            connection.execute(
                select(indexed_materials).where(indexed_materials.c.id == fb_material)
            )
            .mappings()
            .one()
        )
        fb_body = dict(
            connection.execute(
                select(bodies).where(bodies.c.material_id == fb_material)
            )
            .mappings()
            .one()
        )
        for table in (operations, messages, runs, citations, feedback):
            if table is runs:
                query = (
                    select(table)
                    .join(operations, operations.c.id == runs.c.operation_id)
                    .where(operations.c.session_id == fb_created.json["data"]["id"])
                )
            else:
                query = select(table).where(
                    table.c.session_id == fb_created.json["data"]["id"]
                )
            fb_backup[table] = [
                dict(row) for row in connection.execute(query).mappings()
            ]
    assert (
        request("a_teacher", "DELETE", "/api/v1/materials/" + fb_material).status_code
        == 200
    )
    assert request("session", "GET", fb_citation).json["data"]["status"] == "deleted"
    assert (
        request("session", "GET", fb_path).json["data"]["messages"][-1]["content"]
        is None
    )
    assert (
        request("session", "GET", "/api/v1/runs/" + fb_run).json["data"]["result"]
        is None
    )
    assert (
        request(
            "session", "POST", fb_path + "/messages", fb_question, fb_key
        ).status_code
        == 409
    )
    assert (
        request("a_teacher", "GET", "/api/v1/teaching-feedback?status=handled").json[
            "data"
        ]["total"]
        == 0
    )
    assert fb_vectors.count(fb_scope, time.monotonic() + 35) == 1

    class TargetCleanups(IndexCleanupRepository):
        def candidates(self):
            return [
                row for row in super().candidates() if row["material_id"] == fb_material
            ]

    class BrokenVectors:
        def delete(self, *args):
            raise IndexDependencyError("synthetic-cleanup")

    fb_cleanup_repo = TargetCleanups(engine)
    assert (
        IndexCleanupService(
            fb_cleanup_repo,
            lambda collection: BrokenVectors(),
            DatabaseError,
            IndexDependencyError,
        ).run()["failed"]
        >= 1
    )
    assert request("session", "GET", fb_citation).json["data"]["excerpt"] is None
    with engine.begin() as connection:
        connection.execute(insert(indexed_materials).values(fb_original))
        connection.execute(insert(bodies).values(fb_body))
        for table, saved_rows in fb_backup.items():
            primary = [column.name for column in table.primary_key.columns]
            for row in saved_rows:
                connection.execute(
                    update(table)
                    .where(*(table.c[key] == row[key] for key in primary))
                    .values(
                        {
                            key: value
                            for key, value in row.items()
                            if key not in primary and not table.c[key].computed
                        }
                    )
                )
    # 恢复后删除凭证先于副本重放也足以屏蔽私人正文与教师队列。
    assert request("session", "GET", fb_citation).json["data"]["excerpt"] is None
    assert (
        request("session", "GET", fb_path).json["data"]["messages"][-1]["content"]
        is None
    )
    assert (
        request("session", "GET", "/api/v1/runs/" + fb_run).json["data"]["result"]
        is None
    )
    assert all(
        row["content"] is None
        for row in request("session", "GET", fb_path).json["data"]["messages"]
    )
    manifest = [
        (row["material_id"], row["deleted_at"])
        for row in repo.deletion_manifest()
        if row["material_id"] == fb_material
    ]
    repo.replay_deletions(manifest)
    repo.replay_deletions(manifest)
    with engine.begin() as connection:
        connection.execute(
            update(cleanups)
            .where(cleanups.c.material_id == fb_material)
            .values(next_attempt_at=now)
        )
    fb_cleaner = IndexCleanupService(
        fb_cleanup_repo,
        lambda collection: fb_vectors,
        DatabaseError,
        IndexDependencyError,
    )
    assert fb_cleaner.run()["failed"] == 0
    assert fb_vectors.count(fb_scope, time.monotonic() + 35) == 0
    assert fb_cleaner.run()["failed"] == 0
    assert (
        request("session", "GET", "/api/v1/materials/" + fb_material).status_code == 404
    )
    assert request("session", "GET", fb_citation).json["data"] == {
        "number": 1,
        "status": "deleted",
        "title": None,
        "excerpt": None,
        "location": None,
    }
    print(
        "FB：真实MySQL/Qdrant历史快照、本人出处、反馈重放/处理/最小投影、清理故障和恢复删除重放通过"
    )
