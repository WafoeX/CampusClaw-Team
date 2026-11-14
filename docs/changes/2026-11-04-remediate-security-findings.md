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
