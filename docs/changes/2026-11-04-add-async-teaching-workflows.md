# 异步教学工作流

## 0010 人工教学阶段记录

依据[提案](../../openspec/changes/2026-11-04-add-async-teaching-workflows/proposal.md)、[设计](../../openspec/changes/2026-11-04-add-async-teaching-workflows/design.md)及[任务](../../openspec/changes/2026-11-04-add-async-teaching-workflows/tasks.md)，本 PR 交付人工单选/判断题的版本与审核、测验草稿与发布快照、冻结学生名单、学生草稿、一次正式提交、MySQL 事务内规则评分、答案开放门控及师生页面。0010 迁移新建 11 张表；对已有资料来源追加同班组合索引。资料删除会在同一事务去除教学来源指针。

本阶段没有接入 AI 候选题、Kafka、错题和看板，也没有把课程要求的异步作业提交 202 或教师改分声明为已实现。2.1–2.3 的人工确定性路径可供下游开发；涉及候选题、MCP、课堂等价或正式人工验收的情形仍按原任务推进。

## 技能与读取依据

本组调用 `openspec-apply-change`、`project-data-change`、`project-add-tests`、`project-review`，输入为当前变更的 proposal/design/specs/tasks、已合入骨架与认证基线、题目/测验数据设计和合成 A/B 班账号；读取 AGENTS.md、README、规范 01–05/07/08、数据字典、现有迁移与回归入口。动作是逐组实现、追加迁移/字典、补 API 与真实 MySQL 回归、核对场景和交付边界。结果与未覆盖项以本页实际记录为准；技能调用不代替人工批准。

## 验证记录

| 对象与手段 | 判据及实际结果 | 状态 |
| --- | --- | --- |
| OpenSpec | 项目所用 CLI 1.13.0 对 `2026-11-04-add-async-teaching-workflows --strict` 退出 0；提示现有 `material-indexing` 增量归档前需上游主规格，当前不归档 | 通过，归档前置未完成 |
| 代码格式、静态和映射 | 本机临时 Python 3.13 环境运行 `ruff format --check`、`ruff check`、`scripts/check_layout.py`、`scripts/scenario_trace.py`，均退出 0；160 个 Python 文件已符合格式 | 通过 |
| 单元、API、启动 | `make check` 中 `tests/unit tests/api` 430 passed、`tests/test_startup.py` 4 passed | 通过 |
| MySQL 人工闭环 | 一次性 `campusclaw_test_` MySQL 8.4 隔离库执行 `tests/integration/teaching_runtime.py`，输出 `TEACHING_RUNTIME_OK`；覆盖迁移、A/B 班角色与资源、版本审核、发布快照/名单、草稿重登读取、正式 201/同键重放及截止后重放、评分、截止、答案开放、名单锁并发、八学生集中提交、同人并发及故障回滚 | 通过 |
| 迁移回退 | 首次复测在降级时遇到 MySQL 1553：资料组合索引仍被上游外键使用。修正为降级只删除本组 11 表并保留索引；隔离库复测降级保留账号、重升两次成功 | 失败后修复并复测通过 |
| 浏览器 | `python3 tests/browser/run_teaching.py` 启动一次性 HTTPS 应用与真实 Chromium，执行 `tests/browser/teaching.mjs`；首轮草稿刷新恢复通过，退出登录后的自动跳转断言超时；改为显式登录页导航并确认会话 401 后复测输出 `TEACHING_BROWSER_OK` 和 `TEACHING_BROWSER_RUNTIME_OK`。再经 `scripts/check_pytest.py -q tests/browser/test_teaching.py` 得 1 passed | 失败后修复并复测通过 |
| 完整项目门禁 | 首轮工具容器缺 Git，补齐后规范/静态/434 项/秘密/依赖扫描通过，但 Compose 就绪检查因容器无法访问宿主回环端口而超时；改用本机临时 Python 3.13 环境原样执行 `make check`，最终退出 0。含 OpenSpec 12/12、静态、434 项、Gitleaks 无泄漏、Trivy 锁文件和应用镜像均 0 高危/严重漏洞、Compose 集成 1 passed | 环境失败后复测通过 |

以上数据库使用随机合成账号及密码；临时库和容器均在每轮结束时删除。应用镜像的构建修订在未提交代码测试时只是合成测试标识，不冒充 Git 提交。生产备份恢复、真实课堂试用、课程等价和同伴评审未执行。

## Harness 七类自审

| 类别 | 手段、对象与判据 | 结果及证据 |
| --- | --- | --- |
| 接口入口 | 路由/输入与师生投影核对，API 测 400/401/403/404/201 | API 430 项及 `tests/api/test_teaching.py` |
| 业务逻辑 | 题目编辑失审、发布冻结、草稿修订、正式一次提交及开放时点 | 真实 MySQL 脚本通过；课程教学意图待人工确认 |
| 数据库 | 0010 组合外键、唯一约束、事务回滚、参与行锁和隔离降级重升 | 初次降级失败后修复，复测 `TEACHING_RUNTIME_OK` |
| 公共函数 | 复用认证、资料错误和响应契约；静态及单元回归 | 434 项通过 |
| 错误处理 | 不存在/跨班同构、非法参数、发布及评分故障注入 | API 与 MySQL 脚本通过 |
| 安全 | 服务端身份重验、学生答案门控、来源删除去内容化自审；脚本覆盖基础越权与泄露投影 | 已执行基础断言；独立攻击矩阵与全资产扫描归课末安全预检 |
| 性能 | 锁定某学生参与行时另一学生可在 2 秒内提交；八学生集中提交均得到 201 且各一份评分；单次隔离时延不是容量结论 | 脚本断言通过；正式负载测量和真实体验待 5.2/最终验收 |

## 评审结论

当前结果支持人工确定性教学闭环作为开发基线，2.1 和 2.3 已完成自动化判据。`1.1/1.2` 任务还包括候选、Kafka、索引等后续数据准备，不能因本阶段迁移通过而整项勾选；`2.2` 的普通会话及 MCP 等未来泄露旁路依赖后续服务，故不勾选整项。人工代码评审、课程等价与最终验收由相应任务和 PR 评审人完成，助手未自填批准。

## 2026-11-12 异步候选与错题看板

基线是 `origin/main` 的 `2c916db`，沿用已合入的认证、章节资料、检索、反馈和 MCP。使用合成 A/B 班和锁定的 Python 依赖。本轮新增 0012 出处快照、任务、发件与结果，接通错题和看板、候选题 202、本人状态及授权重放。第 6 组选做已跳过，索引构建继续同步。

Kafka 使用 Apache 4.1.2 KRaft 镜像索引摘要 `sha256:5cc2a2fd93fa2687b44015eee04fb2c3edd9e526bd64bf8bec5ff1e268772e0e`，客户端 `kafka-python==3.0.13`。隔离课堂配置为单节点持久卷，候选和死信各三分区、单副本，容器上限 1 GiB、堆 512 MiB。镜像来源见[Apache 镜像清单](https://hub.docker.com/layers/apache/kafka/4.1.2/images/sha256-4a07b91bf81b35fcc2aaabf3ab6e72aba68d3bb782bce95baba826270c3648da)。

| 对象 | 证据 |
| --- | --- |
| 规范、静态、门禁 | 全仓严格 OpenSpec 12/12。按授权整理骨架 RT-02、安全预检 PSC-03 超长正文，原判据保留。静态检查、463 项单元/API、4 项启动、7 项 Compose 集成通过。依赖锁文件扫描 0 项高危或严重发现。 |
| Gitleaks | 工作树的 Git 指针在扫描容器不可解析，文件扫描零命中。另将原仓库只读挂载运行同一固定镜像 `git --log-opts=--all --redact`，扫描 99 个提交、零命中。 |
| 人工教学和真实 MySQL | `cold_start_and_recovery` 复测通过，覆盖冻结名单、评分写失败、分母、草稿、两班过滤和删除出处，Qdrant 停机时仍可交卷。八人并发样本 8/8 成功，P95 236.83 ms。 |
| 浏览器 | 首次 Chromium 测试通过。最新复跑在容器内安装 Chromium 时超时，改用可缓存测试镜像后通过，覆盖草稿刷新、重新登录、错题和看板。 |
| 未开放答案 | `controlled_tool_dialogue` 在真实 MySQL 和真实 MCP 服务通过，合成答案标记未进入学生结果、普通会话模型输入、SSE 或 MCP 工具参数。 |
| 任务与真实 Kafka | 首轮镜像拉取超时 420 秒。官方镜像下载后复测通过。验证目标 topic 不可用、回执丢失、重投、过期租约、坏消息隔离、四次退避、死信恢复及授权重放。投递器和 worker 进程在 broker 重启后排空待办并正常退出。 |
| 候选题三项工程判据 | 22 次 202 受理，P95 10.18 ms。两个成功完成样本为 5589.45、40.71 ms，P95 5312.01 ms，含故障注入和正常执行。进程在 DB 提交后、offset 提交前退出，重启读到两条同事件记录，业务只生效一批。 |
| 数据和提示 | 空库、已有库、重复升级及合成降级已验证。真实 MySQL 另验证结果写入失败整批回滚。固定提示回归见[评测](../eval/2026-11-12-teaching-candidates-v1.md)，迁移和回退见[数据字典](../data-dictionary.md#异步教学出处和实时指标0012)。 |
| 尚未执行 | 缺少课程真实网关私有配置，真实模型候选 4.1、完整 5.3 及交付 7.4 待完成。课程等价、人工代码评审、课末安全预检及最终验收分别由相应任务负责。 |

复测入口为 `make check CHANGE=2026-11-04-add-async-teaching-workflows`，浏览器另用 `uv run --locked python scripts/check_pytest.py -q tests/browser/test_teaching.py`。脱敏事务与并发原始记录在本地 `reports/risk-transaction.md`、`reports/risk-concurrency.md`。真实网关命令及私有配置方式见 [README](../../README.md#异步教学)。

课程差异交最终验收 1.5 确认。当前异步 202 对象是 AI 候选题，正式交卷同步返回 201，教师审核题目，课程中的异步作业评分和教师改分仍待课程口径确认。

## 2026-11-12 交付自检续做

使用 `openspec-apply-change` 和 `project-review` 核对当前工作树的规划、任务、场景、README、规范及验证记录。使用 `project-add-tests` 核对真实模型用例与替身用例的边界。发现真实模型夹具原先把课程密钥写入 pytest 可能保留的 Compose 环境文件。调整后仅将已验证的三项配置传给 Compose 子进程，测试临时文件只含合成服务配置。真实模型成功路径追加候选草稿、审核状态、原始出处区间和脱敏模型元数据断言。

| 类别 | 已查对象和证据 | 状态 |
| --- | --- | --- |
| 接口入口 | 核对题库、任务状态、授权重放、错题和看板的路由及 Swagger。候选创建返回 202 和 `Location`，正式交卷仍为 201。 | 已有 API 和 Compose 回归通过 |
| 业务逻辑 | 检查冻结名单、答案开放、缺交不计分和候选待审。核对 Chromium 草稿恢复及师生视图证据。 | 确定性路径通过，候选真实模型待测 |
| 数据库 | 核对 0012、字典、回退顺序及 outbox 与业务写入事务。重放两次消费记录，仅一批生效。 | 隔离 MySQL/Kafka 回归通过 |
| 公共函数 | 核对复用的题目结构、证据和数值校验。真实烟测配置经 `ChatSettings` 验证固定网关和模型。用合成配置替换子进程，确认环境变量和私有文件两条路径均传入 Compose 环境，临时文件和命令参数均无网关密钥。 | 固定回归与两条配置传递路径通过 |
| 错误处理 | 核对无证据、坏消息、回执丢失、死信及重新投递。本轮真实模式预检缺配置，退出 1，未发模型请求。 | 预检拒绝符合预期，真实模型未执行 |
| 安全 | 核对两班资源权限、资料撤销与答案开放。重跑原仓库只读 Gitleaks 历史扫描，100 个提交零命中。 | 基础回归通过，专项安全预检及人工评审待执行 |
| 性能 | 核对 202 受理和任务完成时延分开统计，正式交卷并发另计。保留 5.2 两份本地脱敏报告。 | 工程样本已记录，真实模型时延未测 |

本轮重跑 `uv run --locked python scripts/check_pytest.py -q --tb=short tests/integration/test_compose.py -k real_kafka`，真实 MySQL/Kafka 与替身模型用例 1 项通过，耗时 61.02 秒。加入 `CAMPUSCLAW_REAL_CANDIDATES=1` 后，预检确认缺少课程网关配置，未发送真实模型请求。

本轮 `make check CHANGE=2026-11-04-add-async-teaching-workflows` 的 12 项严格 OpenSpec、静态检查、463 项单元/API 和 4 项启动检查通过。随后 GHCR 漏洞库下载以 `unexpected EOF` 中断，整条命令退出 2，未进入全部 Compose 集成。使用同一锁定的 Trivy 镜像和[官方 ECR 源](https://trivy.dev/docs/dev/configuration/db/)预取数据库也在三分钟时限内超时，退出 1。本轮完整门禁待复跑，前一轮通过记录保留。

4.1、5.3 和 7.4 仍未完成。按用户最新指令先拆分提交并开草稿 PR 供评审。真实课程模型验证和完整门禁复跑完成后，再更新证据并收尾。人工评审、课末专项安全预检及课程等价各按原任务执行。
