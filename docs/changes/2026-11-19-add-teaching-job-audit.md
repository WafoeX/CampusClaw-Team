# 候选题任务审计变更证据

## 变更说明

本次建立 `2026-11-19-add-teaching-job-audit` 的 proposal、能力规约、设计和任务清单，供第 10 课 L10-N07 技术缺口的后续实现及人工评审使用。现有候选任务可返回 202、轮询状态，但没有与班级操作审计关联；规划保留正式交卷 201 契约，不虚构技能 ID，不预先判定课程作业链路等价。PR 门禁发现新规格缺少场景实现状态声明后，在 `tests/scenario-map.json` 登记为 `planned`；未修改应用代码、迁移、实际测试用例、主干或既有门禁。

按 `openspec-propose` 读取了 `AGENTS.md`、`README.md`、OpenSpec 配置、候选任务服务/仓储、worker、模型适配器、审计接口与 0013/0015 迁移，生成四类规划文件；按 `project-review` 读取规划文件与安全开发、AI 应用、数据、评审规范，核对授权范围、失败路径、数据兼容和评审状态。`project-data-change` 与 `project-add-tests` 留待实施相应任务时调用，本次没有假称迁移或测试已完成。

## 验证记录

| 项目 | 实际结果 | 状态 |
| --- | --- | --- |
| `openspec context --json`、`openspec status --change 2026-11-19-add-teaching-job-audit --json` | 定位仓库 OpenSpec 根目录；proposal、specs、design、tasks 均为 `done`，规划集合完整 | 通过 |
| `openspec validate 2026-11-19-add-teaching-job-audit --strict` | 退出码 0，变更有效 | 通过 |
| `openspec validate --all --strict` | 退出码 0，13 个变更通过、0 失败；其他旧变更有归档提示信息 | 通过 |
| `git diff --check` | 退出码 0；本次新增文件提交后再复核差异 | 通过 |
| PR #64 初始两次 CI `make check` | 作业 `135636288316` 与 `135639059983` 均在 `scripts/scenario_trace.py` 报“规格未声明实现状态”，退出码 2；此前 OpenSpec、格式、lint、分层检查通过 | 失败，已定位并修正声明 |
| PR #64 初始两次 CI `make check-security` | 两次通过；后续镜像构建因 `make check` 未通过而跳过 | 通过 / 依赖跳过 |
| `make check-static` 复测 | 初次本地执行因 uv 缓存目录无写入权限退出 2，未运行到场景追溯；获授权复跑退出码 0，含 OpenSpec 13/13、格式、lint、分层、场景追溯及接口清单 | 通过 |
| 复测 CI `make check`、应用 pytest、MySQL/Kafka、H5 浏览器、迁移和恢复演练 | 场景状态修正提交前未执行；应用行为留待 tasks 对应实现组 | 未执行 |

规约场景包含正常受理与重放、用量缺失、非法输入、跨班和学生拒绝、重复消息/旧租约、审计存储故障、撤权与来源失效、到期及恢复。每项实施任务均写明后续可观察验证方式；当前场景为验收约定，并非运行结果。

## 评审结论

规划文件齐备、严格校验通过，属于可提交评审的规划版本。对照 SEC-02–04、SEC-11、AI-07/10、DATA 留存与副本规则、REV-07–09：服务端班级过滤、跨班同构、去内容、原子性、90 天清理及迁移回退均已列为实施约束；未发现本次规划文件放宽门禁或修改现行授权。应用行为、性能和课程方等价性仍未验证；第 10 课 4.3 与最终验收 1.5 保持未完成。OpenSpec 属约束文件，依据 REV-08 待实际评审人复核；助手自检不构成人工批准，也不授权合并。

## 第 1 组：数据契约与迁移（2026-11-20）

### 变更说明

基于已合并的 PR #64 与 `main` `19f2066` 实施 tasks 1.1–1.2。`0016_teaching_job_audit_data` 只增加任务用量列及配对约束、扩展审计终态结果、增加班级内对象查询索引；旧任务/审计不回填。更新运行表定义和数据字典，增加一次性 Compose/MySQL 迁移回归，不改变 HTTP 或 worker 行为。`project-data-change` 以本变更的任务、0012/0013/0015 结构、数据字典及 DATA/BE/OPS/SEC 规则核对归属链、唯一约束、留存、副本和回退；`project-add-tests` 依 TEST-04/06/07/12 增加真实 MySQL 正向、失败及边界断言；`project-review` 核对本组任务及证据。

数据归属链为任务 `class_id/creator_id` 到班级和账号、审计 `class_id/actor_id` 到当前身份；审计请求标识唯一，新增索引不代替查询授权。新增字段只在 MySQL 与其备份，未新增题干/答案副本、文件、向量或缓存。任务与审计分别按教学数据和 90 天去内容审计留存。应用回退保留 0016 扩展；物理降级测试仅在 `campusclaw_test_` 合成库运行。

### 验证记录

| 检查 | 实际结果 | 状态 |
| --- | --- | --- |
| `uv run --locked python scripts/check_pytest.py -q -s tests/integration/test_compose.py -k TJA_data_migration` | 首次因 Docker 未启动，在 fixture 建立前退出 1；启动 Docker 后复跑，发现测试脚本漏调用空库迁移，退出 1 | 失败并修复测试入口 |
| `uv run --locked python scripts/check_pytest.py -q --tb=short tests/integration/test_compose.py -k TJA_data_migration` | 首轮修复后 1 通过；增强无效用量断言时，MySQL 返回 3819 `OperationalError`，原断言只捕 `IntegrityError`，退出 1；修正为核对真实错误码后再次 1 通过 | 通过，保留失败与复测 |
| `uv run --locked python scripts/check_pytest.py -q --tb=short tests/integration/test_compose.py -k 'TJA_data_migration or JB_F05_mysql_job_transactions_without_broker'` | 一次性 Compose 启动，`/live` 与 `/health` 200；0016 空库升级、旧 0015 合成行保留、重复升级、用量约束拒绝、隔离降级与重升、既有候选任务事务回归；2 通过、8 未选，退出码 0 | 通过 |
| 审计恢复清理 | 合成过期审计行先由既有清理删 1 行，再重插同一备份行并清理删 1 行；这是行级恢复模拟，不是完整 MySQL 备份恢复演练 | 通过本组清理判据；完整恢复仍待最终演练 |
| `make check-static` | 首次因新增测试的导入顺序不符合 Ruff 而退出 2；调整导入后复跑退出码 0，OpenSpec 13/13、格式、lint、分层、场景追溯与接口清单均通过 | 通过，保留失败与复测 |
| `make check`、`make check-security`、课程人工等价性 | 本组提交前未执行；变更收尾及最终验收分别承担 | 未执行 |

PR #65 的首轮 CI：两套 `make check` 分别在作业 `136148847759`、`136149158688` 通过；后一套 `make check-security` 作业 `136149158331` 通过，镜像构建通过。前一套安全作业 `136148847501` 在拉取 MySQL 镜像时遇到 `toomanyrequests: Data limit exceeded`，测试未启动，不能记为代码通过。仅重跑失败作业后，`make check-security` 作业 `136154010558` 通过，镜像构建 `136154573902` 通过；PR 当前所需检查均通过。此次失败来自外部镜像拉取限额，没有修改测试、门禁或依赖版本来换取绿灯。课程人工评审仍未执行。

证据补充提交触发的 CI 中，一套 `make check` 作业 `136157980996` 通过，另一套 `136158001921` 在既有 `test_JB_QB_real_kafka_and_candidate_recovery` 中停止 Kafka 后立即检查容器退出状态时得到空值，退出码 2；同一提交的两套 `make check-security` 均通过。本机单独运行该 Kafka 恢复测试为 1 通过、退出码 0。仅重跑失败作业后，`make check` 作业 `136164621092` 通过，镜像构建 `136169086661` 通过。没有删除或修改该断言；此次时序失败仍保留为 CI 稳定性风险，后续若复现须单独定位。

### 评审结论

本组迁移、字典及受影响入口已有隔离真实依赖证据，tasks 1.1–1.2 标记完成。七类 Harness：接口入口与业务逻辑未改，按原候选事务回归；数据库由空/旧库、重跑、约束、降级核对；公共函数仅新增迁移内部 `_names` 并由重跑验证；错误处理核验 MySQL 3819 拒绝；安全核查班级键、无正文新副本及合成库限制；性能未做压测，新增索引的实际查询性能待第 3 组。README 无新增使用入口，保持现有阶段说明。OpenSpec 任务、数据字典和测试属于需人工复核文件；本次自检不是批准，PR 合并仍需真实门禁和同伴评审。课程 4.3 保持未完成。

## 第 2 组：受理、重放与结算审计（2026-11-20）

### 变更说明

基于已合并的 PR #65 与 `main` `f634f10` 实施 tasks 2.1–2.3。HTTP 受理及重放沿用本次请求标识，在任务和 outbox 所在事务内追加去内容审计；worker 将实际模型用量和执行耗时传入结算，在同一事务内提交终态、草稿/结果及审计。终态请求标识由任务 ID、代次和结果稳定生成；重复消息、旧租约和未终结重试不追加终态。重放重置本代用量，先前失败审计保留。模型已调用但未提供有效 token 时写 `unavailable` 和空数值；未调用时写 `not_applicable`。HTTP 响应未新增用量字段。

真实 Kafka 回归首次在已有 `teaching_runtime.py` 物理降到 0014 时失败：本组新增的 `failed` 审计不符合 0015 的旧结果约束。为避免 0016 降级在已改动索引/约束后才遇到不兼容行，在 0016 的**降级入口**追加预检；升级逻辑和已部署结构不变。此处修改已执行迁移的降级函数，仅用于隔离库回退安全，需按 REV-08 人工复核。迁移测试确认不兼容行使降级在改结构前拒绝；既有综合夹具仅在 `campusclaw_test_` 合成库断言这些行为任务审计后清理，再继续 0015/0014 回归。生产回退仍保留扩展结构，不执行物理降级。

`openspec-apply-change` 以本变更 proposal、design、spec、tasks 和当前代码落实第 2 组；`project-add-tests` 以 TJA-N01/N02、B01、F01–F04 为输入，补充单元及真实 MySQL/Kafka 正常、失败、边界断言；`project-data-change` 以 0016 降级和合成审计行为输入，核对旧约束、预检与隔离回退；`project-review` 对照 AGENTS、README、BE/SEC/TEST/AI/DATA/REV 规范、本组差异及下列实际结果自检。提示词、模型版本和检索参数未改变，`project-prompt-eval` 不适用；本组未引入新的数据副本或留存策略。

### 验证记录

| 场景 / 检查 | 实际结果 | 状态 |
| --- | --- | --- |
| TJA-N01/N02、F01/F03：真实 MySQL 接口与事务 | 受理 202 对应同班操作者、HTTP 请求标识和空技能 ID；非法来源、outbox 或审计写入失败不留任务/审计；重放失败回滚代次和 outbox；终态审计写失败回滚草稿、结果和状态，恢复后结算成功 | 通过 |
| TJA-B01/F04：模型用量与取消 | 单元检查无效/缺失用量、有效 17 token、跨尝试累计及模型协议失败保留已获用量；真实 Kafka 检查依赖失败为 `unavailable`/空数值，撤权或来源失效仅记录取消而不发布草稿 | 通过 |
| TJA-F02：真实 Kafka 重复与旧租约 | 旧租约结算前后不生成终态；新租约仅一条成功事件；重复投递后仍一条。死信原代次一条，获准重放新代次一条成功事件，重放前用量清空 | 通过 |
| `UV_CACHE_DIR=/private/tmp/campusclaw-uv-cache uv run --locked python scripts/check_pytest.py -q --disable-socket tests/unit/test_chat_client.py` | 12 通过，退出码 0 | 通过 |
| `UV_CACHE_DIR=/private/tmp/campusclaw-uv-cache uv run --locked python scripts/check_pytest.py -q --tb=short tests/integration/test_compose.py -k 'TJA_data_migration or JB_F05_mysql_job_transactions_without_broker'` | Compose 隔离启动，`/live`、`/health` 200；迁移预检与旧版回退、事务及故障回滚，2 通过、8 未选，退出码 0 | 通过 |
| `UV_CACHE_DIR=/private/tmp/campusclaw-uv-cache uv run --locked python scripts/check_pytest.py -q --tb=short tests/integration/test_compose.py -k JB_QB_real_kafka_and_candidate_recovery` | 真实 MySQL/Kafka，1 通过、9 未选，退出码 0，约 92 秒 | 通过 |
| `UV_CACHE_DIR=/private/tmp/campusclaw-uv-cache make check-static` | OpenSpec 13/13、格式、lint、分层、场景映射及接口清单通过，退出码 0 | 通过 |
| 首轮及环境失败 | 静态检查首轮报导入顺序，修正后通过；真实 Kafka 首轮在旧约束降级失败，加入预检及隔离夹具清理后通过。本轮在受限进程中另有 uv 缓存写入和 Docker socket 权限错误，改用临时缓存并获准访问 Docker 后复测；这些失败均未记作代码通过 | 失败已修复并复测 |
| `make check`、`make check-security`、人工课程等价性 | 本组本地未执行；PR 首轮双门禁见下方，变更收尾与最终验收分别负责其余范围 | 本地未执行 / PR CI 通过 / 人工待后续 |

PR #66 首轮 CI（候选提交 `b474739`）两套 `make check` 作业 `136245539440`、`136249442626` 均通过，两套 `make check-security` 作业 `136245539802`、`136249442266` 均通过；镜像构建作业 `136249542784`、`136253553380` 均通过。上述是 PR 自动检查，非本机执行；本次证据补充提交会重新触发检查，其结果另行核对。人工代码评审仍未发生。

用例映射：TJA-N01/F01/F03 对应 `teaching_jobs_runtime.py` 的 `task()`、错误受理和 `storage` 分支；TJA-N02/F02/F04 对应同文件的 Kafka 重放、重复消息、旧租约和撤权/失效分支；TJA-B01/F04 对应 `test_chat_client.py` 的 TJA 用量单元测试及 Kafka 依赖失败；0016 降级预检对应 `teaching_job_audit_migration.py`。TJA-N03/F05/F06/B02 属第 3/4 组，场景清单保持 `planned`，不冒充全部能力已验证。

### 评审结论

第 2 组 2.1–2.3 的受影响入口、隔离启动与实际自动化回归满足本组可运行交接；任务标记完成。七类 Harness：接口入口核对受理/重放状态码和请求标识；业务逻辑核对代次、终态及旧租约副作用；数据库核对同事务回滚、0016 回退预检与合成库清理；公共函数核对 `UsageCapture` 累计和适配器上下文；错误处理核对模型缺失/非法用量与审计写故障；安全核对当前服务端班级/操作者、空技能 ID 和无正文审计；性能仅记录实测耗时，未做吞吐压测，第 3 组查询索引再核对性能。README 无新增操作入口；数据字典与第 1 组契约一致。物理降级守卫、OpenSpec 任务及代码仍待真实同伴评审；助手自检不等于人工批准，未合并前不宣称变更完成。第 10 课 4.3 状态不变。

## 第 3 组：教师按任务查询与 H5 可追查路径（2026-11-20）

### 变更说明

基于已合并的 PR #66 与 `main` `918f3e0` 实施 tasks 3.1–3.2。`GET /api/v1/operation-audits` 新增可选 `job_id` 过滤参数，转换为 `resource_type=teaching_job` 与 `resource_id=任务 ID` 条件，始终与当前数据库身份的班级和 90 天有效期条件同时生效；非法 UUID 由接口层以 `identifier()` 拒绝为 400/1000，不触达服务层。新增教师页 `/console/audits`（页面清单登记），提供任务 ID 过滤、时间窗口、分页与去内容详情面板；候选题异步生成状态旁增加“按任务 ID 查看操作审计”入口，指向同一任务 ID 的审计查询。H5 仅用 `textContent` 渲染，不内嵌题目、答案、证据正文或凭据。

### 验证记录

| 检查 | 实际结果 | 状态 |
| --- | --- | --- |
| `tests/api/test_operation_audit.py` 新增 8 条（TJA-N03 投影仅元数据且 `job_id` 传入仓储、TJA-F05 学生 403、TJA-F06 四种非法 ID 400 且不触达服务、未知过滤 400、详情 404 同构、教师页面渲染） | 单文件 13 通过；`tests/api` 全量 169 通过，退出码 0 | 通过 |
| `UV_CACHE_DIR=/private/tmp/campusclaw-uv-cache uv run --locked python scripts/check_pytest.py -q --tb=short tests/integration/test_compose.py -k JB_QB_real_kafka_and_candidate_recovery` | 真实 MySQL/Kafka：`?job_id=` 列表动作集为受理/重放/结算、详情等于列表项、B 班为空、跨班与不存在详情 404/1300 同构、查询不推进任务状态且不调用模型，1 通过，约 90 秒 | 通过 |
| `UV_CACHE_DIR=/private/tmp/campusclaw-uv-cache uv run --locked python scripts/check_pytest.py -q --tb=short tests/browser/test_teaching.py` | 真实 Chromium：任务页审计入口链接含任务 ID、审计页显示受理与结算、详情仅元数据、无题干/答案/提示词正文，输出 `H5_AUDIT_BROWSER_OK`，1 通过，约 35 秒 | 通过 |
| `tests/scenario-map.json` 迁移 | teaching-job-audit 从 `planned` 转为 `implemented`，11 条 TJA 场景全部映射到 `test_operation_audit.py`、`test_chat_client.py`、`test_compose.py` 及两个真实依赖脚本的测试函数/唯一模块级断言；`scripts/scenario_trace.py` 退出码 0 | 通过 |
| `test_compose.py` 重构 | `test_JB_F05` 与 `test_TJA_data_migration` 的脚本执行抽为 `verify_job_storage`、`verify_audit_migration` 具名入口供追溯校验，行为不变；全量集成复跑通过 | 通过 |
| `make check CHANGE=2026-11-19-add-teaching-job-audit`（本机全量） | 静态：OpenSpec 13/13、Ruff 格式/lint、分层与运行/授权映射、场景追溯、接口清单 13 个去重入口均通过；单元/接口 515 通过、启动 4 通过；secrets 与依赖扫描 uv.lock 高危/严重 0；真实集成+浏览器 13 通过，退出码 0，集成段约 480 秒 | 通过 |
| `make check-security` | 首轮以默认旧候选制品运行：`frontend/logs/app.tar/mcp-server.tar` 因 `reports/security-assets` 的 revision 为旧提交 `4aa4953` 而退出 2（制品未就绪，非漏洞）；history/worktree 密钥 0、dependencies 高危/严重 0。按 CI 同款流程以 `CAMPUSCLAW_SECURITY_ASSETS` 重跑 `security_precheck` 捕获本候选制品（revision 与 HEAD `aee8182` 一致）后复测：history/worktree/frontend/logs/app.tar/mcp-server.tar 密钥均 0，dependencies 高危/严重 0，全部范围 exit 0，退出码 0 | 首轮制品未就绪；捕获制品后复测通过 |
| 数据恢复检查 | 全量集成含 `test_TJA_data_migration_empty_existing_repeat_and_downgrade`：空库升级、旧行兼容、重复升级、约束拒绝、隔离降级重升与审计到期清理复跑通过 | 通过 |

PR #67（第 3 组）CI：同提交两轮作业中，一轮 `make check` 与 `make check-security` 及镜像构建全部通过；另一轮 `make check-security` 在资产捕获步骤失败（细节见第 4 组）。人工代码评审仍未执行。
用例映射：TJA-N03 对应 `test_operation_audit.py::test_TJA_N03...` 与 `teaching_jobs_runtime.py` 的任务筛选断言；TJA-F05/F06 对应接口学生 403、非法 ID 400 及脚本中 B 班空列表/404 同构断言；TJA-B02 对应 `teaching_job_audit_migration.py` 的到期清理断言；TJA-N01/B01/F01–F04 沿用第 2 组映射。H5 流程对应 `candidates.mjs` 的审计链接、列表、详情断言与 `test_teaching.py` 的 `H5_AUDIT_BROWSER_OK` 核对。

### 评审结论

第 3 组 3.1–3.2 有接口、真实依赖与真实浏览器三层证据，tasks 标记完成。七类 Harness：接口入口核对 `job_id` 参数校验、权限与页面路由登记；业务逻辑核对过滤同时受班级和有效期约束、查询无状态推进副作用；数据库核对 0016 索引承载按对象过滤、迁移与到期清理回归；公共函数核对仓储/服务参数传递与 H5 共用 API 封装；错误处理核对非法 ID 受控 400、详情 404 同构与页面错误态含请求标识；安全核对学生 403、跨班空列表/同构 404、列表与详情去内容、仅 `textContent` 渲染；性能核对查询走 `ix_operation_audit_class_resource` 索引、页面分页每页 20 条，未做专项压测。README、页面清单与接口文档已同步。OpenSpec 任务与代码仍待真实同伴评审；助手自检不等于人工批准。第 10 课 4.3 状态不变。

## 第 4 组：跨入口追溯、门禁与收尾评审（2026-11-20）

### 变更说明

基于已合并的 PR #67 前置提交与 `main` `918f3e0` 实施 tasks 4.1–4.2。`project-add-tests` 将 teaching-job-audit 从场景清单 `planned` 转为 `implemented`，11 条 TJA 场景逐条映射到接口/单元测试函数与真实 MySQL/Kafka、迁移脚本的模块级唯一断言；为满足追溯校验的具名入口要求，将 `test_JB_F05` 与 `test_TJA_data_migration` 的脚本执行抽为 `verify_job_storage`、`verify_audit_migration` 两个 runner，行为不变。随后在本机全量执行 `make check` 与按 CI 同款流程捕获候选制品后的 `make check-security`，并用 `project-review` 对照规约、任务、数据字典、README、页面清单与证据完成收尾自检。

### 验证记录

| 检查 | 实际结果 | 状态 |
| --- | --- | --- |
| `scripts/scenario_trace.py` | teaching-job-audit 11/11 场景映射有效，断言唯一性通过，退出码 0 | 通过 |
| `make check CHANGE=2026-11-19-add-teaching-job-audit`（本机全量） | 静态 OpenSpec 13/13、格式/lint/分层/追溯/接口清单通过；单元+接口 515 通过、启动 4 通过；secrets 与依赖扫描 0 高危/严重；真实集成+浏览器 13 通过（约 480 秒），退出码 0 | 通过 |
| `make check-security` 首轮 | `reports/security-assets` 的 revision 为旧提交 `4aa4953`，`frontend/logs/app.tar/mcp-server.tar` 因制品与候选不一致退出 2；history/worktree 密钥 0、dependencies 高危/严重 0 | 制品未就绪，非代码失败 |
| `CAMPUSCLAW_SECURITY_ASSETS=reports/security-assets-aee8182 ... -k security_precheck` | 捕获本候选（HEAD `aee8182`）的前端、日志、镜像制品并断言镜像 revision 一致，1 通过 | 通过 |
| `make check-security SECURITY_ASSETS=reports/security-assets-aee8182 SECURITY_CANDIDATE=<HEAD>` | history/worktree/frontend/logs/app.tar/mcp-server.tar 密钥均 0，dependencies 高危/严重 0，全部范围 exit 0，退出码 0 | 通过 |
| `openspec validate 2026-11-19-add-teaching-job-audit --strict` | 退出码 0 | 通过 |
| 任务与字典同步 | tasks 1.1–4.1 已勾选；数据字典登记 0016 用量字段/状态、终态枚举、索引、请求标识来源与 90 天留存；README 操作审计段含 `job_id` 过滤说明；产品设计规范页面清单含 `/console/audits` | 通过 |
| PR #67 首轮 CI | 一轮 `make check-security` 的“捕获隔离候选资产”步骤在 fixture 建立时失败：Docker Hub 匿名拉取限额 `toomanyrequests: Data limit exceeded`（mysql 镜像未拉取，Compose 未启动，测试 6.96 秒报错），安全门禁被跳过；同提交另一轮双门禁与镜像构建均通过。`gh run rerun --failed` 重跑后该作业 `make check`、`make check-security`、镜像构建三项全部成功，PR #67 检查全绿 | 外部镜像配额，非代码失败；重跑后通过 |
| PR #68 CI | 两轮作业的 `make check`、`make check-security` 与镜像构建均 SUCCESS，PR 检查全绿 | 通过 |
| 未执行项 | 真实人工代码评审、课程方等价性判断（第 10 课 4.3 与最终验收 1.5）、H5 真人走查、查询专项压测 | 未执行，如实登记 |

### 评审结论

tasks 1.1–4.1 的交付物与自动化证据逐项对应，4.2 的收尾核对完成；本变更实现与自动化验证部分满足可运行交接，人工批准与合并前置仍保留。七类 Harness 在前三组证据上补充：接口入口、业务逻辑、数据库、公共函数、错误处理、安全六类有接口/单元/真实依赖/浏览器证据；性能类仅记录实测耗时与索引使用，未做专项压测，记未执行。约束文件（OpenSpec、数据字典、产品设计规范页面清单、场景清单、测试）与实际代码均待真实同伴评审；助手自检不等于人工批准。第 10 课 4.3 保持未完成：技术侧 H5 四步与七列审计的自动化回归已通过，但课程方等价性判断尚无真实证据，最终验收 1.5 仍待执行。合并前需人工代码评审并按既有流程合入主干。
