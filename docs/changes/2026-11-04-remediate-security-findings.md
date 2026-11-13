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
