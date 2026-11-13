# 第 8 课课末安全预检实测（SEC-01–07）

2026-11-13，本次 Codex 会话执行。候选源码与应用/MCP 镜像的修订标签均为 `4aa4953bd08cf0bb397ecce6416300a41c7c2ad5`。主干保护已核对。隔离项目使用 Docker Desktop 29.9.2、真实 MySQL 8.4/Qdrant、两班合成讲义和合成师生 Cookie 会话。模型只使用本地替身，原始日志与制品位于忽略目录。应用 `/live` 和 `/health` 均为 200，测试完成后清理隔离项目。

| 课程项 | 前置与操作 | 预期 | 实际与判定 |
| --- | --- | --- | --- |
| SEC-01 | A1 合法调用以下五个入口后，匿名按相同方法和载荷重放 | 五条均为 401，data 为空 | 五条均为 `401/1100`、data 为 null，正向均为 200。绿 |
| SEC-02 | A/B 两班均有可读讲义及关键词正向命中。A1 读取 B 班讲义与缺失 ID，B1 查 A 班关键词 | 讲义响应同构，跨班检索 0 条 | `404/1300`、公开文案和 data 均同构。A1、B1 本班各 1 条，B1 跨班 0 条。绿。见[权限复验](risk-authz.md) |
| SEC-03 | 教师在当前版本更新三类配置，再用学生当前会话和同源条件请求更新 | 拒绝且数据库无副作用 | 教师三次 200 且版本升至 2。学生三次均为 `403/1200`，技能、模板、助手配置及修订、审计快照前后一致。绿 |
| SEC-04 | A1 正常交卷后有一份成绩。核对真实路由，向只读成绩入口直接发 PATCH | 无额外评分、提交、任务或发件 | 405，前后全表快照一致，四表行数为 1、1、0、0。技术对照通过。候选没有独立评分写入口，课程等价待确认 |
| SEC-05 | 扫描 Git 历史、工作区、合成页面、日志及两个候选镜像 | 完整执行且零命中 | 六个范围均为零。绿。见[扫描基线](security-baseline.md) |
| SEC-06 | 对候选提交的 uv.lock 执行 High/Critical 审计 | 可用漏洞库及分项计数 | 见[扫描基线](security-baseline.md) |
| SEC-07 | 合成学生通过同源入口调用已启用技能。根据响应的请求标识查运行日志，再按执行 ID 查隔离库 | 同一技能调用能关联操作者、技能、状态、耗时、用量 | SSE 成功，数据库四项可查，模型日志用量无法关联到请求。红 |

SEC-01 的真实入口是 `GET /api/v1/auth/sessions/current`、`GET /api/v1/materials`、`GET /api/v1/materials/{id}`、`GET /api/v1/materials/{id}/download` 和 `POST /api/v1/searches`。SEC-03 实测三个 `PATCH /api/v1/{skills,prompt-templates,assistants}/{id}`。第一次提示模板正向请求因误带创建字段 `app_key` 返回 400，判为夹具参数无效，去除后才计入权限判定。

写入面来自本次 Flask 注册表，覆盖 40 条 POST/PUT/PATCH/DELETE 路由。教师面包括章节和资料管理、模板/技能/助手配置、反馈处理、工具登记和审阅、题目及审核、测验发布、候选受理和任务重放。本人面包括会话和消息、反馈、练习票据、草稿与正式提交。搜索和预览虽使用 POST，按各自业务契约处理。完整路由输出由复跑命令生成。课程 SEC-04 的已注册评分相关入口为正式提交 POST 与教师成绩 GET。

## SEC-07 红项

| 字段 | 实测 | 缺口或拟补层级 |
| --- | --- | --- |
| 操作者 | 隔离 `application_runs.owner_id` 与合成学生 A1 一致 | 可按执行 ID 复查 |
| 技能 | 运行配置关联合成技能与修订 2 | 可按执行 ID 复查 |
| 结果 | `succeeded`，SSE 返回 done | 可按执行 ID 复查 |
| 耗时 | 技能运行记录 78 ms | 可按执行 ID 复查 |
| 用量 | 模型替身返回 20 输入、10 输出、共 30 tokens。模型日志有计数但 `request_id=null`，执行记录无用量 | 在流式技能编排与模型观测衔接处传递关联标识，并在合规审计投影保留同次执行的脱敏用量 |

原判定保留在本报告。复跑 `CAMPUSCLAW_SECURITY_ASSETS=reports/security-rerun uv run --locked python scripts/check_pytest.py -q -s tests/integration/test_compose.py -k security_precheck`，比较 `observations.json` 与 `logs/precheck.log` 的模型及 HTTP 记录。后续由安全修复实施者在同一夹具保留修复前后输出和实际提交号。真实模型准确度和 token 计费不由替身用量推断。

## 技术交接与待复验

- [并发](risk-concurrency.md)和[事务](risk-transaction.md)已复跑。候选题 202 及 `pending → running → succeeded` 和正式交卷 201 分别记录，作业 202 与评分写入等价留给课程确认。
- 回归覆盖现有的两班权限、MCP 出站约束、答案门控和撤销、任务恢复。独立专项组合矩阵仍有缺项，详见[变更证据](../docs/changes/2026-11-04-add-post-async-security-precheck.md)。
- 合成问题草稿。有答案：“蓝鲸动力站的额定电压是多少？” 无答案：“蓝鲸动力站的建造年份是多少？” 跨班：以 B1 问“蓝鲸动力站的额定电压是多少？” 本轮未选 SEC-08 注入实验。
- [独立复验记录](review-01.md)待项目最终验收 4.1 实际填写。
