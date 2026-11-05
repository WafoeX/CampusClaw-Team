# 第 4 课可追溯检索：规划交付证据

## 变更说明

只新增 [OpenSpec 规划](../../openspec/changes/2026-11-04-add-traceable-retrieval/proposal.md)、[设计](../../openspec/changes/2026-11-04-add-traceable-retrieval/design.md)、五份增量规格、[实施任务](../../openspec/changes/2026-11-04-add-traceable-retrieval/tasks.md)和本记录。范围涵盖章节、切片与双库发布、三模式检索、单次问答、原文与索引联动删除及课程评测。工作区已有部分骨架；第 3 课认证和资料原文变更仍处于规划阶段。本次未改动源码、规范和已有用户文档。

## 验证记录

环境：当前 CampusClaw 工作区，OpenSpec CLI 1.13.0。输入：本课需求、AGENTS.md、README、docs/standards 的八份规范、骨架与第 3 课 OpenSpec、当前 Compose/健康实现/Makefile，以及本地选题说明 §3.1、§3.2、§6.2。

| 检查 | 实际结果 |
| --- | --- |
| `openspec context --json`、`openspec list --json`、`openspec list --specs --json` | 退出码 0，确认使用仓库内 spec-driven，无归档主规格，第 3 课是活动变更 |
| `openspec validate 2026-11-04-add-traceable-retrieval --strict` | 退出码 0。CLI 同时提示：CA-04 的 MODIFIED 目标规格当前不存在，现阶段归档会被拒；第 3 课先归档，再对照完整条款复验 |
| `openspec status --change 2026-11-04-add-traceable-retrieval` 及 JSON 状态 | 退出码 0，proposal/specs/design/tasks 为 4/4；`openspec show 2026-11-04-add-traceable-retrieval --type change --json` 确认 5 份增量 |
| Python 本地文档核对 | 退出码 0：新增文档本地链接可解析，38 个场景 ID 唯一且均为 GIVEN/WHEN/THEN，每个增量能力具备正常/边界和不少于 4 条失败场景，12 项实施任务均未勾选；CA-04 保留上游全部场景 |
| 第 4 课站点来源 | 任务清单、切分、回答和实践页未能读取；课程联络人核实首次触发方式及正式口径后留证。选题 §3.2 和 §6.2 已从本地 PDF 提取核对 |
| 应用验证 | 未执行：本轮只写规划。应用 pytest、make check、Compose、真实 MySQL/Qdrant/网关、浏览器、迁移回退和 30 题对照均待实施 |
| 发布与独立会话 | 发布本轮不适用；独立会话、正向代码生成和故意违规回归未执行。本记录不构成该类证据 |

## 评审结论

- [openspec-propose](../../.agents/skills/openspec-propose/SKILL.md)：读本变更输入、上游规约及 CLI 工件指引，按依赖生成四类规划工件。用 pdf:pdf 的只读提取流程核对本地选题条款；外部仓库的测试与模型结果未沿用。
- [project-review](../../.agents/skills/project-review/SKILL.md)：读全套工件与任务，对照 PROD-01–12（入口、术语、四态）、BE-01–12（分层、响应、事务和幂等）、SEC-01–04/09–15（当前身份、范围、出处与不可信输入）、TEST-01–13（场景和真实依赖）、OPS-02–12（内网、降级、预算和恢复）、AI-03–12（有限证据、拒答、评测）、DATA-01–09（版本、留存、补偿）和 REV-01–09（边界、门禁、留证）。未发现文档结构阻断；保留上游归档依赖和未确认的课程口径，不登记规则例外。
- 可提交人工评审。人工评审待小组指定成员；运行验证与效果目标未达成验收，80%/90%/90% 仍为待测目标。

## 2026-11-05 第一组实施进展（开发候选）

基线为 `main` 的 `e76fb4e`，工作分支 `change/2026-11-05-traceable-retrieval-implementation`。按 `openspec-apply-change` 读取 proposal、design、五份增量规格和 tasks；按 `project-data-change` 核对旧版迁移、原文、归属、备份与回退；按 `project-add-tests` 以 CH-N01/B01/F01–F05 编写隔离 MySQL 测试。读取 AGENTS.md、README、安全/后端/测试/数据/运维/评审规范。未接触生产数据。

新增 0004 只增迁移：`chapters`、24 小时 `chapter_idempotency`、资料可空 `chapter_id` 及同班组合外键；同步唯一数据字典。既有资料迁移后为空章节，原文字节仍在 `material_bodies`。单步降级会丢失章节与归类，限 `campusclaw_test_` 合成库；旧应用回退期间应禁止章节写入，恢复本版本后重新归类。章节 API 已接入当前 Cookie 身份、默认拒绝策略及同源写入校验，提供目录、章节资料分页、创建/修改/删除、资料归类；删除及资料修订同事务。章节页面和完整并发测试尚未完成。

| 验证 | 实际结果 |
| --- | --- |
| 变更前 `make check-integration` | Docker Desktop 隔离 Compose，退出 0，1 个集成测试通过，作为上游可运行基线。 |
| 0004 初版 `make check-integration` | 隔离 Compose，退出 0，1 个集成测试通过；旧库→升级→重跑→单步回退→重升、A/B 同班外键拒绝、原文字节保真。随后新增了幂等表和章节 API，此结果不能代表当前候选。 |
| `.venv/bin/ruff format app tests/integration/chapter_api_runtime.py tests/integration/chapter_migration_runtime.py tests/integration/test_compose.py`、`.venv/bin/ruff check app tests/integration/chapter_api_runtime.py tests/integration/chapter_migration_runtime.py tests/integration/test_compose.py` | 退出 0；格式化 1 个文件，静态规则通过。 |
| `PYTHONPYCACHEPREFIX=/private/tmp/campusclaw-pycache python3 -m compileall -q app tests/integration/chapter_api_runtime.py tests/integration/chapter_migration_runtime.py`、`git diff --check` | 退出 0；仅检查语法与空白，不代表运行通过。首次不设缓存前缀的 compileall 因系统缓存目录权限退出 1，改写入临时目录后复测通过。 |
| 恢复 Docker 前的当前候选运行回归 | **当时未执行**。临时 Python 3.13/uv 路径消失，`.venv/bin/python` 指向不存在的解释器；Docker socket 当时不可用。后续复测见下节。 |
| 当前候选 `make check CHANGE=2026-11-04-add-traceable-retrieval` | 退出 2，停在 `openspec validate --all --strict`：当前环境找不到 `openspec` 可执行文件；后续检查未运行，不记为代码失败或通过。 |
| 当前候选 Ruff、语法及差异复测 | `.venv/bin/ruff format --check` 与 `.venv/bin/ruff check` 均退出 0，40 个文件已格式化；指定新代码 `compileall` 与 `git diff --check` 退出 0。`python3 scripts/check_layout.py` 用系统 Python 3.9 退出 1（缺少 `sys.stdlib_module_names`），不能当作布局门禁结论。 |

七类 Harness 自审：接口入口核对新增方法均在 `CHAPTER_POLICIES` 显式登记、参数边界及 401/403/404；业务逻辑核对修订号、重放、删除归未分类与原文不变；数据库核对组合外键、事务、迁移及回退，初版脚本通过但当前候选待复测；公共函数复用现有资料元数据和输入解析，单元回归待运行；错误处理核对统一 JSON/业务码和故障 503，注入用例待运行；安全核对当前数据库身份、跨班隐藏、同源及请求键，负向用例待运行；性能仅有索引与有界分页静态检查，固定数据压测未执行。人工教学意图和同伴代码评审待全部功能后安排。

本组 1.1 的课程首次索引触发方式仍待课程联络人取得正式依据，CA-04 主规格同步留到归档前。1.2 的学期日期与清理实名责任待登记；1.3 的浏览器走查与两名教师并发归类仍待验证。已恢复的隔离集成与页面接入见下节，三项仍保持未勾选。

### Docker Desktop 恢复后的复测

用户重新打开 Docker Desktop 后，`docker info --format '{{.ServerVersion}}'` 在授权访问 socket 下退出 0，服务端为 29.9.2。本机临时 uv、OpenSpec、Python 3.13 仍缺失，因此用 `/private/tmp/campusclaw-chapter-check.sh` 在随机命名的专用 Compose 项目中构建当前未提交源码，生成随机合成凭据和 `campusclaw_test_` 库，依次从容器标准输入执行四段仓库测试脚本。镜像标签使用基线提交 `e76fb4e` 满足启动格式约束，**镜像内容包含工作区未提交改动，不将该标签当作不可变提交证据**。

第一轮退出 1：既有 `auth_runtime.py` 的原文下载断言失败，实际 503/1500。经隔离复现定位为新 `materials` schema 克隆后隐式 `JOIN material_bodies` 无法确定左表，SQLAlchemy 抛 `InvalidRequestError`。改为显式以资料 ID 连接，不删原断言。再次使用全新随机项目运行，`auth_runtime`、`chapter_migration_runtime`、`chapter_api_runtime`、`rate_limit_runtime` 四段均显示 PASS，脚本退出 0。覆盖旧库升级/重跑/单步回退、跨班组合外键、原文字节、章节创建/归类重放、学生与匿名拒绝、外班同构、旧修订拒绝和删章故障回滚。`docker ps -a`、`docker volume ls`、`docker network ls` 按专用项目前缀复查均为空，临时资源已清理。此结果只代表这四段集成脚本；主机 `make check` 和完整 pytest 仍未执行成功，浏览器与两名教师并发归类专项未执行。

随后接入 `/chapters` 页面并同步 README 与产品页面清单。页面复用现有身份导航、样式令牌和同源写入，展示章节/未分类、资料分页及教师操作，提供加载、空、错误和重试状态；UI 的实际键盘与双宽度浏览器走查尚未执行。`node --check` 从脚本标准输入检查通过；首次直接以 `.html` 文件名检查时 Node 不识别扩展名，改用标准输入后退出 0。增加同一账号两客户端并发创建、同键同结果断言，以及页面师生/匿名入口断言。最后一次全新 Compose 项目运行四段脚本均 PASS，整体退出 0。新增页面的浏览器行为仍不能据此判为通过；1.1–1.3 保持未勾选。

用户要求安装真实 OpenSpec CLI。核对 CI 固定 `@fission-ai/openspec@1.13.0` 后，使用 pnpm 将该官方包安装到被忽略的 `node_modules/.openspec-cli/`，未改仓库技能或 shell 启动文件。首次普通沙箱访问 npm 注册表失败，获准网络重试安装退出 0；通过显式 PATH 执行 `openspec --version` 返回 `1.13.0`，`OPENSPEC_TELEMETRY=0 openspec validate --all --strict` 退出 0，12 个变更通过。CLI 仍提示检索 CA-04 与异步 IX-01 增量尚无主规格目标，归档前必须按上游顺序同步；严格验证通过不等于可归档。
