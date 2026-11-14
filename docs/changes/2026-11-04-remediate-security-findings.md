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
