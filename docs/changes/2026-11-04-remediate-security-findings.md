# 第 9 课安全修复规约自检

## 变更说明

将用户提供的第 9 课任务清单整理为[独立 OpenSpec 变更](../../openspec/changes/2026-11-04-remediate-security-findings/proposal.md)，承接第 8 课原始基线。SEC-01–07 和三条注入回归为必做项。按用户补充，SEC-08 为选做，执行时才要求实验报告及第四步工具层判绿。

- `openspec-propose` 的输入为第 9 课任务清单与 SEC-08 选做决定。读取 AGENTS、README、OpenSpec 配置与四类产物指令、第 8 课安全自查规约、相关上游设计、授权及资料仓储实现、Makefile、扫描脚本和认证用例。按 CLI 依赖生成四份规划产物。
- `project-review` 的输入为四份规划产物和当前工作区证据。对照安全、后端、测试、运维、AI、数据与评审规范，核对授权副作用、审计投影、报告可追溯性、门禁退出判据及选做项的完成条件。

## 验证记录

| 检查 | 实际结果 |
| --- | --- |
| `openspec status --change 2026-11-04-remediate-security-findings` | 退出 0，四份规划产物齐备。 |
| `openspec validate 2026-11-04-remediate-security-findings --strict` | 退出 0。 |
| `openspec validate --all --strict` | 退出 0，10 项通过。CLI 同时提示两个上游增量仍需等待相应主规格建立后才能归档。 |
| 文档自检 | 四份文档、八项课程编号、19 条三段式场景、16 条待实施任务、本地链接和 SEC-08 的选做判据通过核对。 |
| 运行取证 | 第 8 课实际预检报告缺失。基线重放、运行门禁、修复、实验及人工复验均未执行。 |

## 评审结论

规划自检通过，待小组人工评审。第 9 课以实际预检报告和可运行候选为实施前提。Cookie 配置写入新增一次性 CSRF 令牌，应用时同步客户端和服务端。异步演示继续引用第 8 课的课程等价确认记录，未确认的差异保留为缺项。

## 第 8 课预检移交

安全修复 1.1 的输入见[预检报告](../../reports/security-precheck.md)、[扫描基线](../../reports/security-baseline.md)、[权限复核](../../reports/risk-authz.md)、[并发复核](../../reports/risk-concurrency.md)和[事务复核](../../reports/risk-transaction.md)。应用候选为 `4aa4953`，收尾检查代码为 `1110729`。

先用[预检复跑命令](../../README.md#课末安全预检)确认原判定。已记录的 SEC-07 问题为技能用量日志缺少请求关联，修复前后的结果归安全修复 5.1。SEC-04 采用当前评分只读入口的对照，正式交卷为 201，候选题为 202。课程等价由最终验收 1.5 确认，独立真人复验由最终验收 4.1 执行。预检 1.3 尚缺授权及发布规则破坏演练证据，相关结论以[专项检查记录](../../reports/security-precheck.md#13-专项检查复核)为准。

## 2026-11-14 授权复核（2.1，SEC-01、SEC-03）

从已合入 PR #31 的主干 `bc591b4c00fe01614db912842f62ab333268911b` 重放。按 `openspec-apply-change` 和 `project-review` 对照 SR-F02、SR-F04、仓库 SEC-01/02、TEST-09 与 TEST-11。执行者为本次 Codex 会话。使用 Docker 29.9.2、Compose 5.6.1、锁定的 MySQL 8.4 与 Qdrant 1.15.3、A/B 合成班级和同源 HTTPS Cookie。应用存活与核心就绪检查为 200，镜像修订与候选提交一致。

| 前置与操作 | 预期 | 实际 |
| --- | --- | --- |
| A1 先合法调用会话详情、资料列表、资料详情、资料下载和关键词检索，再用独立无 Cookie 客户端逐一重放 | 匿名统一拒绝，无受保护响应数据 | 五个合法请求均为 200。匿名五次均为 401/1100，data 均为 null。 |
| A 班教师分别成功更新技能、提示词模板与助手；A1 维持现有有效会话、合法 Origin 和同源头，带当前修订重放三条写入 | 403/1200 且无业务写入 | 教师三次 200，修订升至 2。学生三次均为 403/1200，配置、修订和审计七表快照前后一致。 |

复跑使用 `CAMPUSCLAW_SECURITY_ASSETS=reports/security-remediation-bc591b4 uv run --locked python scripts/check_pytest.py -q -s tests/integration/test_compose.py -k security_precheck`。本轮授权用例通过并保存了对应 `observations.json`。首次运行时 Docker 未启动。启动后取得授权对照和资产；同次选择的其他用例中，Kafka worker 因资产模式使用的隔离镜像标签与扩展 Compose 预期不符而失败。随后按 README 分开运行两个异步用例，均通过。原始产物留在 Git 忽略目录。

单独运行 `uv run --locked python scripts/check_pytest.py -q -s tests/integration/test_compose.py -k security_precheck`，退出 0，1 项通过，耗时 14.93 秒。2.1 复核通过，当前策略未发现需要改动的授权缺口。3.2 引入一次性令牌后需要复跑适用令牌条件的角色对照。人工评审待执行。

## 2026-11-14 固定基线复跑（1.1、1.2）

本次 Codex 会话在首个修复前固定主干 `bc591b4c00fe01614db912842f62ab333268911b`。使用 Docker 29.9.2、Compose 5.6.1、arm64、10 个 Docker 虚拟 CPU、锁定 MySQL 8.4、Qdrant 1.15.3、Kafka 4.1.2 和合成 A/B 班。候选资产留在忽略目录 `reports/security-remediation-bc591b4`，应用与 MCP 镜像标签和对应 `revision` 文件均指向该提交。

| 基线对照 | 实际结果与缺项 |
| --- | --- |
| SEC-01、SEC-03 | 合法对照通过，五条匿名请求和三条学生配置写请求均按契约拒绝。数值及副作用见 2.1。 |
| SEC-02 | 跨班讲义与合法但不存在的讲义均为 404/1300，文案及 data 相同。本班关键词各命中 1 条，跨班为 0 条。 |
| SEC-04 | 现有只读成绩入口返回 405。测验提交、结果、任务和发件箱四表快照无变化，行数为 1、1、0、0。独立评分写入口的课程等价仍待确认。 |
| SEC-05、SEC-06 | 凭据六项通过。锁文件依赖审计失败于漏洞库下载，未获得 High/Critical 计数。分项退出码见 4.1。 |
| SEC-07 | 技能调用成功，数据库操作者与会话相符，隔离运行耗时 75 ms。固定模型返回 30 tokens，日志未关联请求标识，执行记录无用量。基线红，后续进展见 5.1。 |
| SEC-08 | 上一课无实验运行记录，本轮仍缺四步实测。 |

从干净独立克隆运行 `make check CHANGE=2026-11-04-remediate-security-findings`。12 项 OpenSpec、静态与分层追溯、467 项单元/API、4 项启动检查通过。Gitleaks 在该克隆扫描 118 个可达提交并检查工作区，均零命中。Trivy 拉取漏洞库时收到 `unexpected EOF`，Make 退出 2，未进入集成子门禁。首次运行时 Docker 未启动。启动后改用完整克隆解决工作树的 Git 元数据挂载问题。随后尝试 Trivy 官方 ECR 镜像，下载超过 3 分钟时限仍失败。现有缓存已过计划更新时间，未用于本次判定。

`uv run --locked python scripts/check_pytest.py -q -s tests/integration/test_compose.py -k 'real_kafka or transactions_without_broker'` 单独复跑退出 0，2 项通过，耗时 87.24 秒。固定模型替身下，22 次受理的 P95 为 11.76 ms，两次完成为 5621.98 ms 与 38.56 ms。停止消费者后恢复，崩溃后实际重投递 2 次，首个任务只生效写入 1 批。资产采集与 Kafka 合并运行时出现过隔离镜像标签不匹配，按 README 分开复跑通过。此处的延迟只对应隔离替身回归。

基线执行当天未取得依赖漏洞计数。后续同锁文件的复验见下文 4.2。完整基线门禁已留退出结果，1.2 继续等待 SEC-08 基线证据。

2026-11-15 再核对固定候选的 `revision` 与脱敏 `observations.json`，SEC-01–05 技术对照与上表一致，SEC-07 的日志关联缺口归操作审计。SEC-06 按 SR-F01 补同字节锁文件的后续真实扫描，High/Critical 各为 0，保留首次下载失败及复验日期。1.1 到此具备 SEC-01–07 可追溯记录及三项异步实测。采用先校验权限与数据归属，再验证输入防护的实施顺序。SEC-04 课程等价和 SEC-08 四步基线分别留在 2.3 和 1.2。

## 2026-11-14 凭据与落库检查（4.1，SEC-05）

使用 `make check-security SECURITY_ASSETS=reports/security-remediation-bc591b4 SECURITY_CANDIDATE=bc591b4c00fe01614db912842f62ab333268911b` 扫描基线。锁定 Gitleaks 对本地可获取提交历史（168 个可达提交）、工作区、前端产物、运行日志、应用镜像和 MCP 镜像六项扫描分别退出 0，均为零命中。两份镜像均核对构建修订标签。锁定依赖审计因 Trivy 漏洞库获取失败返回 2（工具退出 1），因此 Make 退出 2。依赖审计及门禁复验归 4.2、4.3。

核对 MySQL 迁移 0001–0012、SQLAlchemy 表定义以及认证、模型和工具连接配置。账号表保存 scrypt 口令哈希，会话表保存 32 字节 SHA-256 令牌摘要。工具连接表保存目录键及版本，凭据由目录指定的环境变量读取，发现及审批仅保存工具定义。MySQL、Qdrant、聊天与嵌入服务的凭据在运行时从环境读取。核查范围内未发现需要可逆加密的凭据持久字段。基线未出现真实命中，轮换、历史清理、复扫和重新克隆流程不适用。

`uv run --locked python scripts/check_pytest.py -q tests/integration/test_compose.py -k 'connector_management or tool_storage or isolated_compose_teaching_service or cold_start_and_recovery'` 在隔离环境退出 0，4 项通过，耗时 165.79 秒。覆盖真实 MySQL 上的认证迁移、口令验证和会话撤销，以及连接登记、工具存储和凭据不回显。首次在默认沙箱运行因 Docker 套接字权限无法启动，改在可访问 Docker 的进程中复测通过。使用 `openspec-apply-change` 与 `project-review` 核对 SR-F10、SEC-10 和实际扫描结果。人工评审待执行。

## 2026-11-14 讲义与检索班级隔离（2.2，SEC-02）

按 SR-F03 和后端、安全、测试规范复核讲义详情、下载、元数据更新、归章、删除及索引构建。改动前，写事务先锁定本班讲义，部分 SQL 写语句仅使用讲义 ID。元数据更新与归章现要求班级、讲义 ID 和当前修订一致，设置待构建索引版本要求班级、讲义 ID 和源版本一致。删除在事务内锁定本班资源并按归属删除主记录，副本清理和运维删除清单重放继续共用同一事务操作。

| 核查面 | 实际结果 |
| --- | --- |
| 接口及错误处理 | 本班读取成功。跨班与不存在详情均为 404/1300，公开文案一致、data 为 null。认证回归按同一判据覆盖下载、PATCH 和 DELETE，拒绝写入前后数据库快照一致。 |
| 业务及数据库 | 本班更新、归章、索引发布和删除通过。旧修订返回 409。副本清理失败后事务回滚，删除清单重放与恢复回归通过。无需迁移。 |
| 安全及查询条件 | 预检原关键词命中计数为 1、1、0。补充对照用两班合成资料和确定性向量，对班级专属词执行关键词、向量、混合查询，授权班级各命中 1 条，其他班级各为 200 空列表。实际 MySQL 全文语句在排序取限前绑定班级；发往真实 Qdrant 的查询在取限前包含班级及索引范围过滤。检索入口未发现取回所有班级再筛选的路径。 |
| 公共函数及性能 | 复用仓储组合条件和既有回表核验，检索每分支仍取最多 20 条。未改变查询阈值。压测未执行。 |

以 `project-add-tests` 补充 `tests/integration/retrieval_runtime.py` 的三种检索对照，保留既有写入和恢复断言。首轮 1 项失败，原因是测试把驱动参数的表示当成稳定接口。改用 SQLAlchemy 已编译的绑定参数后，`uv run --locked python scripts/check_pytest.py -q tests/integration/test_compose.py -k 'cold_start_and_recovery or security_precheck'` 退出 0，2 项通过，耗时 126.85 秒。`make check-static check-test CHANGE=2026-11-04-remediate-security-findings` 在允许绑定本地端口的环境退出 0，OpenSpec 12 项、分层及场景追溯、467 项单元/API、4 项启动检查均通过。按 `project-review` 核对并留存结果，人工评审待执行。

## 2026-11-14 流式模型日志关联（5.1 部分，SEC-07）

复用安全预检的真实 SSE 入口、合成学生、技能和固定模型返回。基线 `bc591b4` 与修复后的模型日志均记录 30 tokens。基线日志的请求标识为空，修复后与 HTTP 请求标识一致，技能及数据库操作者对照均通过。从现有流上下文把服务端生成的标识传到模型回调。字段不随请求发送给模型，日志保持结构化单行并继续限制用量字段，不记录正文或凭据。

`uv run --locked python scripts/check_pytest.py -q -s tests/integration/test_compose.py -k 'security_precheck or controlled_tool_dialogue'` 退出 0，2 项通过，耗时 37.81 秒。预检加入模型与 HTTP 日志的请求标识一致性断言。按 `project-add-tests` 和 `project-review` 核对入口、现有 SSE 及工具流程、日志字段和安全边界。`make check-static CHANGE=2026-11-04-remediate-security-findings` 与断网单元/API 检查通过，467 项。无数据库结构改动，未做压测。技能用量持久化、教师授权投影、学生拒绝审计及故障关闭仍待 5.1 实施和验证。

## 2026-11-15 持久操作审计（5.1，SEC-07）

在已合入 PR #32 的 `9440234` 上实施。该 PR 的 GitHub `make check` 已通过（运行 43599290307）。本次按 `openspec-apply-change`、`project-data-change`、`project-add-tests` 和 `project-review`，读取 SR-N02、SR-F12/13、数据字典、迁移 0012 与后端、测试、安全、数据、运维、AI 和评审规则。新增 0013，追加带请求标识的去内容单行 JSON，保留 90 天。配置和技能成功审计使用业务事务，拒绝记录用独立事务与唯一请求标识。恢复清理和回退约定见[审计字典](../data-dictionary.md#班级操作审计0013)。

| 核查 | 判据及实测 |
| --- | --- |
| 接口 | 受保护列表和详情已连入 OpenAPI。教师可按操作者、技能、时间查询，学生 403、匿名 401，超出 7 日窗口返回 400。 |
| 业务 | 同一 SSE 技能完成事件的用量为 30 tokens，耗时等于数据库执行耗时，请求标识与 HTTP 响应匹配。三次同源学生配置写均 403/1200，分别有且仅有一条关联的拒绝审计。 |
| 数据库 | 真实 MySQL 验证空库升级、重复升级、单步降至 0012 后再升，保留旧账号并保留教学表。通过时钟推进清理到期记录，重插清理前的合成审计行模拟恢复，再次清理至零。 |
| 公共函数 | 复用当前身份与分页约束，统一白名单投影和 JSON 编码。实际落库 JSON 单行，字段值与投影一致。 |
| 错误处理 | 模拟审计 INSERT 存储故障，教师配置写返回 503/1500，相关配置、修订与审计行快照一致；学生仍返回 403/1200。受控工具回归验证发包前审计故障不调用远端。 |
| 安全 | 跨班详情与缺失对象同构，跨班操作者筛选计数为零。技能投影只含定义标识，排除私人会话和执行 ID、输入输出正文。 |
| 性能 | 班级时间、操作者与技能查询具备组合索引，清理每批至多 100 条。未执行压测。 |

`uv run --locked python scripts/check_pytest.py -q -s tests/integration/test_compose.py -k 'security_precheck or controlled_tool_dialogue or cold_start_and_recovery'` 两轮退出 0。加入单行 JSON、0013 单步回退和恢复清理后，最终轮 3 项通过、耗时 90.13 秒。隔离 Compose 使用真实 MySQL 8.4 与 Qdrant，技能调用使用固定替身。`make check-static check-test CHANGE=2026-11-04-remediate-security-findings` 退出 0，12 项严格 OpenSpec、分层及追溯、467 项单元/API、4 项启动检查通过。新一轮本地 Trivy 官方源下载 7 分钟超时，依赖扫描单列到 4.2；完整候选门禁由后续 CI 复核。人工评审待执行。

## 2026-11-15 锁定依赖审计（4.2，SEC-06）

以 `openspec-apply-change` 和 `project-review` 对照 SEC-06、SEC-16、REV-05，读取 PR #33 的实际 CI 日志并核对三个 Git 锁文件对象。固定 Trivy 在 GitHub Actions 中首次下载漏洞库并执行含开发依赖的锁文件扫描，High 与 Critical 均为 0。锁文件与第 9 课基线和最新主干完全一致。结果、判定和 CI 链接已归档到[扫描基线](../../reports/security-baseline.md#2026-11-15-锁定依赖复验安全修复-42)。4.3 仍须用隔离资产复验完整门禁。人工评审待执行。

## 2026-11-15 资产门禁红绿对照（4.3，SEC-06）

按 `project-review` 对照 SR-F11、SEC-16、OPS-03、REV-05 与 REV-08。现有 `make check-security` 的扫描范围、阻断条件和分项退出规则保持原样。独立 CI 采集实际候选后执行同一命令两次，验证红轮前端命中 1 项且其他六个范围有完整结果，绿轮七项均通过，Make 分别退出 2、0。依赖用同一版本漏洞库，High/Critical 两轮均为 0。README 已同步复跑入口，Git 忽略规则只放行脱敏报告。见[实际输出与提交号](../../reports/gate-red-green.md)。数据库、业务接口、提示词与发布流程不涉及本项。人工评审待执行。

## 2026-11-15 配置写入 CSRF 防护（3.2，SR-F04 与 SR-F09）

以 `fe2dc24` 为候选基线，按 `openspec-apply-change`、`project-data-change`、`project-add-tests` 与 `project-review` 核对受保护路由、数据字典和评审准入。新增 0014 迁移、签发接口与一次消费约束。教师页面和同源试调自动取令牌，直接 API 客户端按 OpenAPI 获取。启用前先迁移数据库，再切换应用和 API 客户端。

| 核查项 | 隔离候选结果 |
| --- | --- |
| 接口与授权 | OpenAPI 登记八个配置写操作，签发 action 枚举与这些 operationId 一致。未知 action 为 400/1000。三个学生配置写同时保留原样与带有效令牌对照，全部为 403/1200，配置和修订未变，相关拒绝审计仍保留。 |
| 业务与错误 | 合法同源首次写成功。跨来源表单、同源缺令牌、过期令牌、动作或会话不匹配均为 403/1200。并发消费一枚令牌时为 200 和 403，各一次，仅增加一条修订；再次提交为 403 且数据快照相同。 |
| 数据库 | MySQL 实测 0014 升级、幂等重跑、合成库回退 0013 并重升。物理回退验证保留审计表和原账号。过期布置与有界清理实测删除一条过期摘要。 |
| 公共函数与安全 | 浏览器共用取令牌函数，OpenAPI 试调按 operationId 取值。签发响应带 `Cache-Control: no-store`，登录 Cookie 保持 `SameSite=Strict`、`Secure`、`HttpOnly`。响应头无令牌原值，表仅存摘要。 |
| 性能 | 每次配置写增加一次签发和一次按摘要主键删除。签发沿用用户限流并有独立计数。并发正确性已实测，专项负载测试未执行。 |

独立预检与 OpenAPI 断言通过，1 项通过、16.11 秒。放入测试容器的客户端初版改变了场景追溯要求的 Compose 入口参数，恢复既有入口并让测试容器加载辅助模块后，`make check-static CHANGE=2026-11-04-remediate-security-findings` 通过。首轮完整集成发现代理收尾时恢复助手配置未取令牌，返回 403；同步该客户端后，`uv run --locked python scripts/check_pytest.py -q --tb=short tests/integration/test_compose.py` 8 项通过、282.15 秒。`make check-test` 467 项单元/API 和 4 项启动检查通过。渲染后的教师配置、技能管理和 Swagger 脚本均经 `node --check` 验证。人工浏览器验收与评审留待对应环节。

## 2026-11-15 修复 Git worktree 凭据扫描（6.1 部分）

按 `project-review` 对照 SEC-10、TEST-08、REV-05。在本地关联 worktree 执行 `make check-secrets` 时，原脚本把工作目录挂给容器，容器无法解析指向宿主主仓库的 Git 路径。原日志为 Git 128、Gitleaks 扫描 0 条提交，即使扫描器退出 0，也不计为历史通过。脚本改为在临时目录镜像本地可达历史并比较 Git 计数，扫描器只读取镜像；工作区文件按原规则单独复制和扫描。

在 `ae2655e` 工作区复跑 `make check-secrets` 退出 0。Git 本地可达计数为 182，镜像计数相同，Gitleaks 报告扫描了 130 条提交，历史及工作区均零发现。另在深度 1 的临时克隆运行同一脚本，确认在启动扫描器前以明确错误退出 1。`ruff check scripts/check_secrets.py` 通过。此项只覆盖凭据门禁，6.1 的候选四步演示及完整回归仍单独验收。

## 2026-11-15 四步安全走查（6.1，SR-N03）

按 `openspec-apply-change`、`project-add-tests`、`project-review` 对照 SR-N03、SR-F14、SEC-11、TEST-09 和 REV-05。基于 `8920297` 加本项测试改动，用隔离 Compose、真实 MySQL 8.4 和 Kafka 4.1.2、合成 A/B 班与固定模型替身。Compose 为隔离实例使用随机构建标识，Git 基线见上文。

| 步骤 | 隔离环境实测 |
| --- | --- |
| 登录 | A 班教师通过实际登录入口取得会话，HTTP 200。B 班教师也使用独立登录会话，HTTP 200。 |
| 任务受理 | A 班提交同班讲义的候选题任务，HTTP 202，任务 `68586ba8-fecd-4dc2-8543-70bef0683c2a`，`Location` 与任务查询路径一致。 |
| 查询状态 | 原会话按顺序观测 `pending → running → succeeded`。MySQL 中该任务仅有一条发件和一条结果，Kafka 正常投递一次，无孤立任务。 |
| 换班查讲义 | B 班读取本班资料为 200，读取 A 班讲义和缺失讲义均为 404/1300，公开响应字段同构，请求标识按请求独立生成。 |

`uv run --locked python scripts/check_pytest.py -q -s --tb=short tests/integration/test_compose.py -k 'real_kafka or transactions_without_broker'` 退出 0，2 项通过，耗时 90.89 秒。该轮 Kafka 崩溃后重投递 2 次、首任务提交 1 批；22 次受理 P95 为 9.98 ms，两次完成分别为 5583.64 ms、42.75 ms。结果为替身模型下的异步工程回归数据。

同轮候选静态检查和 467 项单元/API 通过。在默认沙箱中，启动测试绑定回环端口被拒，`make` 退出 2。放开回环限制后，4 项启动检查与 Git 历史/工作区凭据扫描均通过。完整门禁与整套注入回归仍按 6.1 独立验收，6.1 保持未完成。业务路由、持久结构、公共函数和错误映射沿用现状，此项变动限于测试及证据。人工评审待执行。

## 2026-11-15 修复索引与返工取证（6.2、6.3 部分）

按 REV-05、REV-08 自检。本地 `make check CHANGE=2026-11-04-remediate-security-findings` 在四步走查工作区退出 2。Gitleaks 历史、工作区均零命中。Trivy 从 Google 镜像下载漏洞库约 8 分 28 秒后收到 `unexpected EOF`，本轮未取得锁文件漏洞计数，完整门禁未进入集成阶段。独立定向集成结果见四步走查记录。已合入的 PR #35 的 [CI](https://github.com/WafoeX/CampusClaw-Team/actions/runs/43683828817/job/132719974208) 通过，适用于原候选 `2b8e438`。

归档 [SEC-01–08 修复索引](../../reports/security-fix-log.md)及[返工记录](../../reports/security-rework.md)。用脚本核对本地报告链接、标题锚点和 Git 提交对象，`git check-ignore` 确认原始资产和漏洞库缓存仍被忽略。6.2 仍缺 SEC-08 和可比较的定位、修复耗时。6.3 的技术证据和最终人工复验按任务分别登记。当前候选待完整 CI 和人工评审。
