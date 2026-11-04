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
