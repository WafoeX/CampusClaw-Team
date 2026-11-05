# 第 8 课异步教学闭环规约自检

## 变更说明

交付[提案](../../openspec/changes/2026-11-04-add-async-teaching-workflows/proposal.md)、[设计](../../openspec/changes/2026-11-04-add-async-teaching-workflows/design.md)、五份新增规格、一份索引修改规格及[实施任务](../../openspec/changes/2026-11-04-add-async-teaching-workflows/tasks.md)。按选题 §3.2、§4.2–4.4、§6.1 设计教学闭环，以 RabbitMQ、事务性发件箱、独立 worker 承接评分和出题。核心闭环验收后才切换后台索引。

## 验证记录

| 检查 | 状态 | 实际记录 |
| --- | --- | --- |
| 课程与技术资料 | 已核对 | 网页入口未能直接访问课程站，复读同一工作区前轮从课程站下载的[实践与验收](https://devops.hello1023.com/课件/第8课-课件-异步任务与消息队列/pages/apply.html)、[安全自查任务清单](https://devops.hello1023.com/课程任务清单-第8课.html)和相关专题文本；读取[选题说明](<../../选题说明(1).pdf>)相关章节及 RabbitMQ 官方确认和死信文档。 |
| openspec-propose | 已执行 | 读取技能、AGENTS.md、README、OpenSpec 配置、第 3–7 课规约、索引完整 IX-01、现有应用与 Makefile。由 `openspec context --json` 定位规划根，按 CLI 工件依赖生成。 |
| 结构与任务 | 通过 / 有归档前置 | `openspec validate 2026-11-04-add-async-teaching-workflows --strict` 退出 0；`openspec status --change 2026-11-04-add-async-teaching-workflows` 显示 4/4 规划完成；只读 apply 指令显示 0/20。CLI 提示索引 MODIFIED 目前缺主规格，须先验收并归档第 4 课，再核对 IX-01 和重跑严格校验。 |
| project-review | 已执行 | 读取八规范及评审技能，核对事务、队列状态与重放、角色/答案隔离、数据留存、范围和证据；检查六份规格的三段式、失败路径、场景覆盖、任务和链接。确认 `/reports/` 当前忽略六个固定证据路径，实施任务已安排最小跟踪例外与脱敏审查。 |
| 应用与人工验证 | 未执行 / 待人工评审 | 运行测试、真实 Compose、性能、迁移、课程安全红绿、跨成员、标签和实际验收留待实施。 |

## 评审结论

课程等价验收待任课教师确认。拟用确定性评分和教师审题映射课件的模型批改、教师改分及相关技能；首版在答案开放且评分成功后才向学生显示总分。报告须分别记录真实执行尝试和消息重投，性能未达预设阈值时保留实测并单列补充实验。课程安全自查留待真实环境取证。
