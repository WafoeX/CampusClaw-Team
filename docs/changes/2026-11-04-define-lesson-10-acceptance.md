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

## 2026-11-16 接入 CI 双门禁（2.1 部分，L10-03）

在已合入 PR #37 的 `51ab460` 上，用 `openspec-apply-change` 和 `project-review` 对照 L10-03、OPS-02、REV-05 和 REV-08。在现有工作流加入独立 `make check-security` 作业，复用固定版本的 uv、Python、扫描器和真实安全预检。预检用隔离合成数据并核对镜像修订。两项作业检出同一事件提交，安全命令显式校验 `GITHUB_SHA`。PR 事件用 GitHub 的合并候选，推送事件用被推送的提交。预检未通过时作业失败，产物仅保留在运行器内。

用 Ruby YAML 解析和 Bash 语法检查核对双门禁名称、分支触发和脚本语法。`make check-static CHANGE=2026-11-04-define-lesson-10-acceptance` 通过。`git check-ignore` 确认资产观察记录和镜像归档仍被忽略。此项变动限于 CI 编排和说明，复用现有接口、数据结构、扫描判据及退出策略。主干双检查准入和非零候选真实拦截仍待核验，2.1 保持未完成。受保护工作流变更待人工评审。

本地按 README 采集 `51ab460` 的隔离资产，安全预检 1 项通过、30.49 秒。首次 `make check-security` 中应用镜像扫描分项退出 2、工具退出 1，Make 退出 2，其他六项已给出结果。单独诊断同一镜像扫描时工具退出 0，首次工具错误未再出现。保持同一提交、资产目录和漏洞库，全量复跑退出 0，六个凭据扫描范围均零命中，锁定依赖 High 与 Critical 均为 0。原始资产留在 Git 忽略目录，命令输出存于本机临时目录。
