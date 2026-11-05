# 第 5 课流式 AI 助手规约自检

## 变更说明

本次交付[提案](../../openspec/changes/2026-11-04-add-streaming-ai-assistant/proposal.md)、[设计](../../openspec/changes/2026-11-04-add-streaming-ai-assistant/design.md)、四份增量能力规格和[实施任务](../../openspec/changes/2026-11-04-add-streaming-ai-assistant/tasks.md)。规约以第 7 课规范与已合入的开发骨架为工程基线。第 3、4 课业务仍在规划，主规格为空。第 5 课显式新增持久会话，继续按上游 QA-01 保持单次问答的无历史副作用。

## 验证记录

| 检查 | 状态 | 实际记录 |
| --- | --- | --- |
| 课件和选题 | 通过 | 网页检索入口未能打开课件，复读同一工作区前轮从课程站实际下载的[正式任务清单](https://devops.hello1023.com/课程任务清单-第5课.html)、[实践页](https://devops.hello1023.com/课件/第5课-课件-提示词AI技能与流式会话/pages/apply.html)和[SSE 专题页](https://devops.hello1023.com/课件/第5课-课件-提示词AI技能与流式会话/pages/stream.html)文本。读取[选题说明](<../../选题说明(1).pdf>)第 3 节相关功能。 |
| openspec-propose | 已执行 | 读取技能、AGENTS.md、README、OpenSpec 配置、第 4 课 QA-01、检索与设计，核对骨架授权及现有门禁。由 `openspec context --json` 定位仓库，经 `openspec new change` 和各工件 `instructions` 按依赖生成。 |
| OpenSpec 严格校验及状态 | 通过 | `openspec validate 2026-11-04-add-streaming-ai-assistant --strict` 退出 0；`openspec status --change 2026-11-04-add-streaming-ai-assistant` 显示 4/4 规划工件完成；只读 apply 指令报告 0/12 实施任务完成。 |
| 场景及范围自检 | 通过 | 检查每份增量规格的三段式、场景唯一、至少四条失败、任务引用全覆盖和本地链接；与开工前工作区清单比较，新增范围仅本变更规划和此记录。 |
| project-review | 已执行 | 读取八规范及评审技能，核对 SEC-01–06、SEC-09、SEC-14，AI-05–12，DATA-02、DATA-04、DATA-07–08 及 REV-01、REV-07–09 的规划覆盖。检查教师最小反馈、同班他人访问、单次问答兼容、分段预校验、事务提交后 done、留存与删除重放。 |
| 行为与人工验证 | 未执行 / 待人工评审 | 本轮为规约生成。应用测试、`make check`、Swagger 试调、实际模型、迁移、浏览器、独立会话及课件四项同伴验证待实施并留真实证据。 |

## 评审结论

规划结构通过，待小组人工复核。主要设计取舍为上传 JSON 对应课件文本技能、解题助手用受控通用提示处理无证据、SSE 只推送通过分段校验的正文。实施前先关闭上游验收依赖，核对 JSON 映射和分段流验收口径。
