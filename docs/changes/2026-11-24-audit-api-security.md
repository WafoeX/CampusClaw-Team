# API 安全审查与接口测试汇报

2026-11-24 在开发分支 `change/2026-11-21-refresh-student-interface` 检查应用源码 `248d279b5eb91ad3a92e4a808fdb726656aa0208`。本次工作区增量为审查脚本、工具测试和文档。修复前，自动规则在教学服务的 `POST /mcp` 发现 1 项缓存防护缺口，代码审查另发现一项拒绝审计的容量风险。随后已在本地工作区修复 MCP 响应头，复扫告警为 0。拒绝审计的容量风险仍待复核。

## 变更说明

维护者可在仓库根目录运行 `uv run --locked python -m scripts.audit_api_security --all`。每行显示方法、路由模板、实际 HTTP 状态和触发的规则。JSON 中的 `findings` 是具体发现，`failed_tests` 是触达该接口且失败的用例，后者仍需定位。输出仅保留路由模板与状态等元数据。[使用说明](../../README.md#按接口查看安全检查结果) · [脚本](../../scripts/audit_api_security.py)

## 安全审查问题

| 优先级和状态 | 接口及观察 | 影响和复核判据 |
| --- | --- | --- |
| P3，已修复并复测 | `POST /mcp` 初始化成功后，响应头携带新的 `Mcp-Session-Id`，缺少 `Cache-Control: no-store`。本地观察器实际收到该响应，工具报告只保留头是否存在。[初始化响应](../../mcp-server/teaching_server.py) · [协议测试](../../tests/api/test_mcp_teaching_service.py) | 该服务使用内网和 Bearer 机器凭据，实测没有发现未授权访问或缓存泄露。修复后成功握手同时返回会话标识和禁缓存指令，错误凭据仍被拒绝。 |
| P2，可用性风险，待处理 | 技能、提示词模板和助手的配置写入共 8 个方法。学生的同源写入在角色检查处被拒，403 处理器另开事务写拒绝审计。业务写配额在后续的请求钩子中检查，此路径没有独立的审计写入预算。审计表按服务端生成的请求标识去重，每个新请求有独立标识。[授权顺序](../../app/api/http.py) · [限流](../../app/api/auth.py) · [受影响动作](../../app/api/operation_audit.py) · [审计写入](../../app/services/operation_audit.py) | 配置数据保持受保护。持续拒绝请求可能增加数据库写入和 90 天留存量。当前未测得容量阈值或实际服务中断。复核时需同时证明拒绝事件可追踪、审计写入有资源上限、合法教学请求仍可用。 |
| 测试追溯缺口，已量化 | 85 个已登记方法中，OpenAPI 描述 67 个，`apitest/cases` 有 21 个路径与方法条目。现有 OpenAPI 回归与 `ENDPOINTS` 白名单比对，白名单外包含资料、章节、出处与索引等入口。[契约生成](../../app/api/openapi.py) · [对应测试](../../tests/api/test_openapi.py) | 仅依据 Swagger 或 JSON 清单会低估测试范围，也会漏掉缺少用例的接口。本次以 Flask 路由表为分母；单条清单可以引用整个共享测试模块。 |

## 验证记录

| 检查与口径 | 本次结果 |
| --- | --- |
| `.venv/bin/python -m pytest -q --disable-socket tests/api`，JUnit 汇总 | 退出 0，16 个模块、170 项通过。包含主应用、探针、测试专用授权路由和独立 MCP 协议。 |
| `python -m scripts.audit_api_security`，同一目录的断网测试 | 主应用 62 条路径、85 个方法，另计教学服务 `/mcp` 的 3 个方法，共 88 个。排除页面、探针及 HEAD/OPTIONS。49 个方法有匹配响应，其中 13 个有 2xx、36 个仅有非成功响应，另 39 个在这一层未观察。JSON-RPC 的 2xx 也可能承载协议错误。pytest 退出 0，扫描器因上述 1 项发现退出 1。默认、`--all` 和 `--json` 三种输出均复跑。 |
| `python apitest/run_all.py --validate-only`、`python scripts/scenario_trace.py` | 均退出 0。21 份清单选择 13 个去重 pytest 入口；已实现能力的场景与执行入口映射通过。 |
| `uv run --locked python apitest/run_all.py`，独立隔离 Compose 与浏览器 | 退出 0，83 项通过，362.85 秒。JUnit 中 72 项来自上述断网套件所用的 API 模块，另有 10 项 Compose 和 1 项 Chromium。两次运行有重复用例。使用合成 A/B 班、MySQL、Qdrant、Kafka 及模型替身。 |
| 候选资产安全门禁 | 以 `CAMPUSCLAW_SECURITY_ASSETS=reports/api-review-248d279-assets` 执行隔离 `security_precheck`，1 项通过；`make check-security SECURITY_ASSETS=reports/api-review-248d279-assets` 退出 0。325 个可达提交，历史、工作区、前端、日志与两个候选镜像的凭据扫描均为 0；锁定依赖 High/Critical 均为 0。该门禁检查资产，不检测 MCP 响应头。 |
| 工具定向回归与反向验证 | `.venv/bin/python scripts/check_pytest.py -q --disable-socket tests/unit/test_api_security_audit.py` 退出 0，5 项通过。覆盖 MCP 初始化响应和安全对照、公开例外、教师权限降级、令牌动作缺失、无身份成功、缓存与 Cookie 属性、输出脱敏、失败用例归属、无响应及执行失败。仅在测试进程替换观察函数为空操作，断言告警条数时退出 1；恢复观察函数后复测通过，最终版本共 5 项。[断言](../../tests/unit/test_api_security_audit.py) |

**工程门禁。** `make check CHANGE=2026-11-24-audit-api-security` 退出 0，包含 519 项单元/API、4 项启动和 13 项集成／浏览器检查，集成段用时 356.05 秒。在该次运行期间补充了独立 MCP 服务的响应头检查及其用例。最终工具版本重跑 `make check-static check-test check-secrets CHANGE=2026-11-24-audit-api-security`，退出 0，15 项 OpenSpec 检查、520 项单元/API、4 项启动及凭据扫描通过。完整门禁沿用仓库既有判据，新脚本单独以退出 1 报告本次 MCP 发现。

**授权、隐私与答案。** 隔离安全预检对五个受保护入口比较已登录与匿名响应，三类教师配置写入对照学生 403 和配置快照。跨班资料与缺失资源公开响应同构，本班检索有命中、跨班无命中；教师访问学生私有运行返回 404。未开放测验的学生视图隐藏答案和解析。缺失、过期、重放或动作不匹配的一次性令牌被拒，并发消费仅一次成功。[预检断言](../../tests/integration/security_precheck_runtime.py)

**工具与教学流程。** Compose 回归覆盖工具连接、停用与审计，Kafka 任务受理和恢复，以及无 broker 时的 MySQL 事务。浏览器覆盖登录、讲义标题按文本展示、测验交卷与角色边界。39 个断网未触达方法包括连接器审批、签发 CSRF 令牌、测验草稿与候选任务轮询，其中多条在隔离环境有验证。此次没有对 Compose 进程逐路由计数，故没有给出两个套件合并后的路由覆盖率。[Compose 用例](../../tests/integration/test_compose.py) · [浏览器入口](../../tests/browser/test_teaching.py)

## 评审结论

按 `project-review` 读取 AGENTS、README、后端、安全、测试、评审规范及安全修复规约，核对了入口授权、拒绝路径、审计事务和数据投影。按 `openspec-propose`、`openspec-apply-change` 建立并严格校验工程工具变更，按 `project-add-tests` 检查脚本的正常、失败与边界场景。业务接口、数据结构、模型和部署配置均无修改。GitHub 分支详情 API 首次核对因匿名配额返回 403；公开分支页的默认分支记录确认 main 已启用保护。工具侧性能仅以本次运行取证；拒绝审计的容量结论仍待独立验证。人工代码评审及跨机器复验待执行。[变更计划](../../openspec/changes/2026-11-24-audit-api-security/tasks.md) · [历史安全问题与处置](../../reports/security-fix-log.md)

## 2026-11-24 MCP 初始化禁缓存复测

修复基于 `248d279` 的工作区。成功的 `POST /mcp` initialize 响应在签发 `Mcp-Session-Id` 的同一处设置 `Cache-Control: no-store`。MP-N01、MP-B01 共用的握手测试现在直接断言实际响应的 `cache_control.no_store`，并继续使用该会话完成通知和工具发现。[修复位置](../../mcp-server/teaching_server.py) · [协议回归](../../tests/api/test_mcp_teaching_service.py)

| 验证 | 实际结果 |
| --- | --- |
| 修复前运行 `.venv/bin/python -m scripts.audit_api_security`；仅添加测试断言后运行 MP-N01/MP-B01 | 扫描器退出 1，唯一告警为 MCP 初始化响应缺少禁缓存指令。握手返回 200，新断言得到 False，定向 pytest 退出 1。 |
| 修复后运行 `.venv/bin/python scripts/check_pytest.py -q --disable-socket tests/api/test_mcp_teaching_service.py tests/unit/test_api_security_audit.py` | 退出 0，9 项通过，覆盖握手、后续会话操作、认证拒绝及审查器的告警和安全对照。 |
| 修复后以默认和 `--json` 两种模式运行 `.venv/bin/python -m scripts.audit_api_security` | 两次均退出 0。登记 88 个方法与路径组合，13 个有成功响应、36 个仅有非成功响应、39 个未观察，告警由 1 降为 0。机器报告在本机 `reports/api-security-audit.json`。 |
| 修复制品安全门禁 | 在临时本地克隆将服务端和回归测试两处改动固定为快照 `4b204b4`。隔离 `security_precheck` 1 项通过；对同一快照的资产运行 `make check-security` 退出 0。历史、快照工作区、前端、日志及两个镜像凭据扫描均为 0，锁定依赖 High/Critical 均为 0。 |
| 工作区工程门禁 | `make check CHANGE=2026-11-04-add-controlled-mcp-tools` 退出 0。15 项 OpenSpec 检查、520 项单元／接口、4 项启动及 13 项容器集成／浏览器回归通过；集成段耗时 365.48 秒。 |

本轮按 `project-add-tests` 和 `project-review` 对照 MCP 服务规格、协议实现、测试及审查脚本验证。变动限于握手响应头、回归断言和证据；数据库、模型、授权状态机及性能测试均不涉及本项修复。人工评审与上线另行记录。

## 2026-11-24 补齐 8 个业务读取接口的正常路径

上轮将断网测试与五个 Compose 场景合并后，88 个方法中有 79 个取得过 2xx、7 个仅有非成功响应、2 个未观察。本轮按 `project-add-tests` 对照章节、题库、交卷、学情、模板、助手、技能和连接器的读取场景，在既有隔离 MySQL 流程中增加以下断言。每个 GET 都同时要求 HTTP 200、业务码 0，并以测试中创建的资源或交卷记录验证归属。

| GET 接口（省略共同前缀 `/api/v1`） | 数据归属的判据 |
| --- | --- |
| `/assistants` | 两班各建一个同名助手并绑定各自的资料和技能。两个班的学生各看到一项，且 ID 分别与本班的创建回执一致。 |
| `/questions` | 两个班分别建题，其中一道题干相同。两位教师逐页读取题库，列表总数和全部题目 ID 必须与 MySQL 中本班原有题目加本次建题回执完全一致，重复、遗漏或混入外班题目均会失败。 |
| `/chapters/<value>` | 本班学生读到与教师创建回执一致的章节。外班教师读取同一 ID 得到 404、业务码 1300、空数据。 |
| `/prompt-templates/<resource_id>` | 两班各建同名同类型模板。两班学生分别按 ID 读回本班模板，返回的配置与各自创建回执一致。 |
| `/skills/<resource_id>` | 本班教师读回刚创建的技能，核对 ID 和技能定义等返回字段。外班教师读同一 ID 及不存在 ID 均得到 404、业务码 1300。 |
| `/tool-connectors/<resource_id>` | 本班教师按登记 ID 读回对应连接器，核对登记信息和状态。外班教师读取同一 ID 得到 404、业务码 1300、空数据。 |
| `/learning-insights` | 按本班已交卷测验筛选，唯一一行的测验 ID、提交数 1、平均分 15 与夹具一致。外班教师使用同一筛选得到 404、业务码 1300、空数据。 |
| `/quizzes/<value>/submission-results` | 本班教师读到一份成绩，学生 ID、交卷回执 ID 和得分 15 均吻合。外班教师读取同一测验得到 404、业务码 1300、空数据。 |

断言随现有集成场景执行。[章节](../../tests/integration/chapter_api_runtime.py) · [题库、学情和成绩](../../tests/integration/teaching_runtime.py) · [助手、模板和技能](../../tests/integration/ai_apps_runtime.py) · [连接器](../../tests/integration/tool_connectors_runtime.py)

首轮完整集成有 12 项通过、1 项失败。真实 Kafka 场景会先在本班生成题目，题库用例假设初始题库为空，在精确总数断言处失败。修订后先按两班身份从 MySQL 独立读取各班已有题目 ID，再加上各班新建 ID；逐页校验全部结果，保留精确数量和归属判据。

本轮 `python -m scripts.audit_api_security --json` 退出 0。单独执行断网套件观察到 13 个方法有成功响应、36 个方法仅有非成功响应、39 个方法未观察，规则告警 0。合并统计时，用临时 pytest 观察器在容器内 Flask 客户端的 `request_finished` 信号上调用同一份 `observe` 规则；只汇入通过场景，按方法和路由模板合并各次响应状态及告警。浏览器回归计入套件通过数；路由明细只计捕获到的 Flask 客户端请求。

工程门禁 `make check-static check-test check-secrets check-dependencies CHANGE=2026-11-24-audit-api-security` 退出 0。15 项 OpenSpec 校验、520 项单元/API 测试、4 项启动测试通过；仓库历史及工作区的凭据扫描为 0，锁定依赖的 High/Critical 均为 0。另对与当前应用、MCP 和构建输入一致的既有候选快照 `4b204b4` 重跑 `make check-security`，七项资产检查均退出 0，含前端、日志和两个镜像的凭据检查。此次新增回归在当前工作区执行。

修订后重跑全套 `tests/integration tests/browser/test_teaching.py`，13 项全部通过，耗时 361.11 秒。8 个新增 GET 均在通过的容器场景中取得 HTTP 200，并通过业务码与班级归属断言。集成使用隔离 Compose 和合成教学数据，模型使用项目测试替身。

| 断网与集成合并，按方法和路由模板去重 | 实测数量 |
| --- | ---: |
| 已登记且观察到响应 | 88/88 |
| 至少一次 HTTP 2xx | 87/88 |
| 仅有非成功响应 | 1 |
| 未观察 | 0 |
| 触发接口安全规则 | 0 |

85 个主应用业务方法全部观察到 2xx。教学服务的 `POST /mcp`、`DELETE /mcp` 也取得成功响应。唯一只返回 405 的 `GET /mcp` 已由协议用例验证，服务声明支持 POST 和 DELETE。接口安全规则覆盖登记和实际响应；既有的拒绝审计写库容量风险仍待专项验证。[MCP 协议断言](../../tests/api/test_mcp_teaching_service.py) · [88 个接口的逐项覆盖明细](2026-11-24-audit-api-security-coverage.json)

按 `project-review` 逐项核对入口、业务码、返回数据、数据库归属、跨班拒绝与实际安全告警。四处修改均在集成测试脚本；本轮未改变服务端、公共函数或数据结构，也未执行容量压测。人工评审待执行。
