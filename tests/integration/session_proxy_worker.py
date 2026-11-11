"""仅隔离测试装配：生产会话/检索/ChatClient，HTTP模型替身与合成SQL种子。"""

from datetime import timedelta
from uuid import uuid4

from flask import g, request
from sqlalchemy import insert, select, update

from app.adapters.assistant_schema_v8 import (
    assistant_materials,
    assistant_revisions,
    assistant_skills,
    assistants,
    skill_revisions,
    skills,
)
from app.adapters.auth_schema_v1 import accounts
from app.adapters.chat_client import ChatClient
from app.adapters.index_clients import JsonEndpoint
from app.adapters.index_schema_v5 import builds as index_builds
from app.adapters.index_schema_v5 import chunks, materials
from app.adapters.material_schema_v2 import bodies
from app.api.http import success
from app.config import ChatSettings
from app.services.auth import utc_now


def install(
    app, engine, class_id, creator_id, material_id, *, text="电压为24伏，频率为50赫兹。"
):
    now = utc_now()
    assistant_id = str(uuid4())
    skill_id = str(uuid4())
    with engine.begin() as connection:
        connection.execute(
            update(materials)
            .where(materials.c.id == material_id)
            .values(character_count=len(text), byte_size=len(text.encode()))
        )
        connection.execute(
            update(bodies)
            .where(bodies.c.material_id == material_id)
            .values(content=text.encode())
        )
        connection.execute(
            update(materials)
            .where(materials.c.id == material_id)
            .values(active_index_version=1, desired_index_version=1)
        )
        connection.execute(
            insert(index_builds).values(
                id=str(uuid4()),
                class_id=class_id,
                material_id=material_id,
                creator_id=creator_id,
                source_version=1,
                index_version=1,
                index_config_version="proxy-v1",
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
                class_id=class_id,
                material_id=material_id,
                source_version=1,
                index_version=1,
                index_config_version="proxy-v1",
                ordinal=0,
                start_offset=0,
                end_offset=len(text),
                content=text,
            )
        )
        connection.execute(
            insert(assistants).values(
                id=assistant_id,
                class_id=class_id,
                creator_id=creator_id,
                name="真实代理合成助手",
                revision=1,
                enabled=True,
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            insert(assistant_revisions).values(
                class_id=class_id,
                assistant_id=assistant_id,
                revision=1,
                creator_id=creator_id,
                prompt="",
                created_at=now,
            )
        )
        connection.execute(
            insert(assistant_materials).values(
                class_id=class_id,
                assistant_id=assistant_id,
                revision=1,
                material_id=material_id,
            )
        )
        connection.execute(
            insert(skills).values(
                id=skill_id,
                class_id=class_id,
                creator_id=creator_id,
                name="流中停用技能",
                name_key=b"proxy-skill",
                revision=1,
                enabled=True,
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            insert(skill_revisions).values(
                class_id=class_id,
                skill_id=skill_id,
                revision=1,
                creator_id=creator_id,
                definition={
                    "name": "流中停用技能",
                    "conditions": ["不命中的条件"],
                    "enabled": True,
                    "tools": [],
                    "steps": [{"type": "model", "instruction": "遵循资料依据"}],
                },
                created_at=now,
            )
        )
        connection.execute(
            insert(assistant_skills).values(
                class_id=class_id,
                assistant_id=assistant_id,
                revision=1,
                skill_id=skill_id,
            )
        )
    service = app.extensions["private_sessions"].ai
    service.expires_at = now + timedelta(days=1)
    service.chat = ChatClient(
        ChatSettings(
            "https://ai-gateway.devops.hello1023.com/v1", "synthetic", "course-chat"
        ),
        endpoint=JsonEndpoint("http://127.0.0.1:9090", {}),
    )

    @app.get("/__session_fixture")
    def session_fixture():
        return success({"assistant_id": assistant_id})

    @app.post("/__session_fixture")
    def change_fixture():
        # 控制入口只在复制进/tmp的隔离worker中存在，沿用当前Cookie和同源防护。
        action = request.json["action"]
        with engine.begin() as connection:
            if action == "skill":
                connection.execute(
                    update(skills).where(skills.c.id == skill_id).values(enabled=False)
                )
            elif action == "revoke":
                connection.execute(
                    update(accounts)
                    .where(accounts.c.id == g.identity.subject_id)
                    .values(enabled=False)
                )
            elif action == "source":
                connection.execute(
                    update(materials)
                    .where(materials.c.id == material_id)
                    .values(active_index_version=2)
                )
            elif action == "restore_source":
                connection.execute(
                    update(materials)
                    .where(materials.c.id == material_id)
                    .values(active_index_version=1)
                )
            elif action == "configuration":
                revision = (
                    connection.scalar(
                        select(assistants.c.revision).where(
                            assistants.c.id == assistant_id
                        )
                    )
                    + 1
                )
                connection.execute(
                    insert(assistant_revisions).values(
                        class_id=class_id,
                        assistant_id=assistant_id,
                        revision=revision,
                        creator_id=creator_id,
                        prompt="新配置",
                        created_at=utc_now(),
                    )
                )
                connection.execute(
                    insert(assistant_materials).values(
                        class_id=class_id,
                        assistant_id=assistant_id,
                        revision=revision,
                        material_id=material_id,
                    )
                )
                connection.execute(
                    insert(assistant_skills).values(
                        class_id=class_id,
                        assistant_id=assistant_id,
                        revision=revision,
                        skill_id=skill_id,
                    )
                )
                connection.execute(
                    update(assistants)
                    .where(assistants.c.id == assistant_id)
                    .values(revision=revision)
                )
        return success({})

    return assistant_id, skill_id
