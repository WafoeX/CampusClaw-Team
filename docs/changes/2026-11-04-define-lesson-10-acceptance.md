# 第 10 课交付与最终人工评测规约

## 变更说明

以用户提供的第 10 课清单为输入，起草[第 10 课验收变更](../../openspec/changes/2026-11-04-define-lesson-10-acceptance/proposal.md)。既有项目最终验收继续提供跨功能业务卡片。本变更新增工程交付前置、人工判据、同伴复现和证据归档要求。

- `openspec-propose` 读取 AGENTS、README、OpenSpec 配置、既有最终验收计划、上游第 8 和第 9 课规约、相关业务设计、Makefile、Dockerfile、Compose 和 CI。按 CLI 产物依赖生成提案、规约、设计和任务。
- `project-review` 对照工程及评审规范检查四份规划产物、验收边界、证据路径和实际状态。同步 README、评审规范、AGENTS 与 Cursor 七类核查。Cursor 规则使用常驻 MDC 入口。[Cursor 规则文档](https://cursor.com/docs/rules)
- 受保护文件补充规则的理由是落实课程的代码准入与最终人工评测。适用范围是本仓库代码自审及第 10 课交付。验证限于规约、规则字段、文档链接和工作区差异。规则变更待人工复核。

## 验证记录

| 检查 | 实际结果 |
| --- | --- |
| `openspec status --change 2026-11-04-define-lesson-10-acceptance` | 退出 0，四份规划产物齐备。 |
| `openspec validate 2026-11-04-define-lesson-10-acceptance --strict` | 退出 0。 |
| `openspec validate --all --strict` | 退出 0，11 项通过。CLI 提示两个既有上游增量需等待对应主规格后归档。 |
| 文档自检 | 8 条要求、17 个三段式场景、14 项待办及场景映射、七类规则和本次新增链接均通过核对。`git diff --check` 退出 0。 |
| 运行与人工评测 | 未执行。双门禁、候选构建、镜像检查、告警送达、压测、用户试用、独立复验与签署均待实际交付。 |

## 评审结论

规划文档通过自检，待小组人工复核。教师改分、作业提交 202 和登录方式的差异须取得课程确认或补齐业务能力，再按确认的判据验收。根目录 `report.md` 和固定报告路径待实际取证后填写。
