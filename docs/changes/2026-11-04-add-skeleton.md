# 2026-11-04-add-skeleton 提案与验证记录

## 变更说明

2026-11-04，本会话助手完成可评审的 [OpenSpec 提案](../../openspec/changes/2026-11-04-add-skeleton/proposal.md)、[设计与 C7 矩阵](../../openspec/changes/2026-11-04-add-skeleton/design.md)、三项能力增量规约和[分组任务](../../openspec/changes/2026-11-04-add-skeleton/tasks.md)。新增约束为本课骨架验收和实施顺序，依据 REV-08 待人工复核。既有 [establish-project-standards 证据](establish-project-standards.md)、八规范、五技能与[课程历史入口](../lesson-07/README.md)保持原状。

设计选择为 `/live` 独立存活、MySQL 核心就绪、Qdrant 可降级、1 秒单依赖探测截止、受保护短分支内的 A/B 制品及隔离蓝绿演练。配置、授权和门禁取舍见设计。组长负责登记小组实名角色。

## 验证记录

| 检查 | 本次结果 |
| --- | --- |
| 规划与任务状态 | `openspec status --change 2026-11-04-add-skeleton` 显示 4/4 类规划齐全；`openspec instructions apply --change 2026-11-04-add-skeleton --json` 显示 ready、0/15 项实施任务完成 |
| 严格校验 | `openspec validate 2026-11-04-add-skeleton --strict` 退出 0 |
| 规划结构 | 临时 Python 检查退出 0；17 个本地文档链接有效，7 项 C7 矩阵行齐全。运行、授权、门禁分别为 12/9/7 个三段式场景，其中失败场景 5/6/5 个；编号全局唯一。此处数量为规约场景，测试尚未编写 |
| 范围 | `git diff --check` 及对既有受保护路径的 `git diff --exit-code` 均退出 0。新增规划文件的行尾空白单列检查通过；两份操作前已存在的未跟踪课程提示文档保留 |

| 四层验证 | 实际状态 |
| --- | --- |
| V1 载体 | 本次完成规划结构、入口链接和改动范围自检；八规范、五技能的历史载体验证见既有记录。完整课内 V1 复核列入任务 1.3 |
| V2 独立会话 | 未执行。本会话已有上下文；等授权后按规约收集真实会话证据 |
| V3 正向生成 | 未执行，待运行候选及经批准的隔离样本 |
| V4 故意违规 | 未执行，待隔离环境、正向基线及有效断言；授权移除与核心就绪误报分别留证 |

技能记录：

- `openspec-propose` 输入为仓库、变更名和本课骨架范围。读取技能、根入口、OpenSpec 配置、既有变更规划和课程证据，按 CLI 指令及路径创建规划并严格校验通过。
- `project-review` 输入为同一变更、规划文件及既有证据。读取技能、AGENTS.md、README、相关产品/后端/安全/测试/运维/数据/评审规范和新规划，按 BE-01/11、SEC-01/04/10/16、TEST-02/08/10、OPS-03/06/08、REV-07–09 对照契约、失败场景与证据状态。文档自检通过。

## 评审结论

提案可交人工评审。首要实施阻断为编码前真实主干保护与拒绝直推证据；成员协作和教师访问仍待外部角色核验。运行构建、应用 pytest、`make check`、冷启动、跨成员复现、回滚、归档和标签未执行。模型评测及业务数据迁移不适用于本轮提案。课程完成状态待实施和人工验收。

## 2026-11-04 编码前核验

实施从第 1 组开始。`openspec-apply-change` 读取 CLI 返回的全部六份规划文件及根入口，确认 `spec-driven`、`ready`、0/15 项完成。`project-review` 读取相关规范与既有证据，按 REV-03/07–09 和评审规范的 V1 协议复核载体、场景、远程状态和完成口径。

| 检查 | 实际结果 |
| --- | --- |
| 1.1 成员、教师和协作 | 成员真实身份、克隆与协作记录、教师实际访问及课程方对历史偏差的处理结论待组长确认。项目许可仍未选择。 |
| 1.2 主干保护 | 只读请求 GitHub `GET /repos/WafoeX/CampusClaw-Team/branches/main` 及 `GET /repos/WafoeX/CampusClaw-Team/rules/branches/main` 成功。远程 `main` 为 `3f5d0e025cbe536950dae82cfdd9a3afcc0add4f`，`protected=false`，分支保护 `enabled=false`，生效规则返回 `[]`。GitHub 连接的仓库权限返回 `admin=false`、`maintain=false`、`push=false`、`pull=true`。保护前置检查失败，真实直推拒绝验证未执行。 |
| 1.2 远程规划状态 | GitHub Compare 接口显示远程 `main` 比本地记录的基线 `6e48529` 前进两提交，文件差异只新增骨架规划及提案证据，未见新增保护、成员或教师核验证据。本地引用首次用单条 `git rev-parse --short origin/main HEAD` 查询退出 128；拆成两条命令复测成功，分别得到 `6e48529` 和 `44bd604`。 |
| 1.3 规约与 V1 载体 | 骨架与既有规范变更的 `openspec validate <变更名> --strict` 均退出 0。结构检查在 35 份跟踪 Markdown 中核对 145 个本地链接目标、八份规范及 97 条唯一规则编号、五个工程技能的元数据和停止条件，复核 28 个三段式场景及 16 个失败场景。核对产品、后端、安全、测试、运维五类最小集合。V1 文档复核通过，人工评审待完成。 |
| V2–V4 与运行检查 | 未执行。V2 须另行取得独立会话授权；V3、V4 和运行门禁须待骨架实现。 |

**阻断 P1。** 有权限的运维须按设计启用 `main` 保护。获授权的普通成员应在证明同一身份可写短分支后，执行真实快进探针，记录规则拒绝、非零退出和推送前后远端引用。评审核对该证据及第 1 组其余前置项后，才可开始应用代码。此次只追加核验证据，任务状态为 0/15，人工评审待完成。

## 2026-11-04 主干保护复测与协作流程调整

用户确认已按给定选项配置主干保护，并授权简化文档，以三人正常提交和项目交付为先。远程重新查询 `GET /repos/WafoeX/CampusClaw-Team/branches/main`，请求成功，`main` 提交仍为 `3f5d0e025cbe536950dae82cfdd9a3afcc0add4f`，`protected=true`、`protection.enabled=true`。当前无必需状态检查，`rules/branches/main` 返回 `[]`，本次以分支接口确认经典分支保护已启用。具体配置由用户确认，远程复测没有验证真实拒绝行为。

本次更新 README、AGENTS.md、评审规范及骨架 proposal/design/tasks。为减少开工前重复取证，短分支开发以已启用保护和严格校验为前置条件。真实直推拒绝、规约人工复核和必需 CI 检查仍须在首份代码合并前验证。组长用三人实际提交与 PR 汇总协作与角色，教师访问在课程交付前核验。影响限于协作证据的时点和形式，运行、授权与门禁规约沿用原有验收条件。课程入口保留既有记录并追加当前进展。

`openspec-update-change` 按 CLI 报告的现有文件路径同步三份规划，用户本轮已授权修改。`openspec validate 2026-11-04-add-skeleton --strict`、`openspec validate establish-project-standards --strict` 和 `git diff --check` 均退出 0，CLI 记录 2/15 项完成。约束文件调整待人工复核。应用代码及真实直推探针尚未执行。
