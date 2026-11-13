# 跨班资料与检索实测（SEC-02）

2026-11-13，候选 `4aa4953`，实施及自动化执行为本次 Codex 会话。隔离 Compose 使用真实 MySQL 8.4 与 Qdrant，关键词索引由测试夹具写入合成记录，同源 Cookie 使用独立客户端。

| 手段 | 对象 | 判据 | 结果 |
| --- | --- | --- | --- |
| 同源 GET | A1 访问 B 班讲义、对照随机不存在 ID | 两者 HTTP、业务码、公开文案、data 同构 | 均为 `404/1300`，文案为“资源不存在或不可访问”，data 为 null。B1 访问 B 班讲义 200。绿 |
| 同源 POST | A1 与 B1 以同一关键词模式检索“蓝鲸” | A1 正向命中，B1 无片段或出处 | A1 1 条，B1 0 条。B1 查询本班“海豚”1 条。绿 |

复跑 `uv run --locked python scripts/check_pytest.py -q -s tests/integration/test_compose.py -k security_precheck`。接口、数据和其他 SEC 项见[预检记录](security-precheck.md)。
