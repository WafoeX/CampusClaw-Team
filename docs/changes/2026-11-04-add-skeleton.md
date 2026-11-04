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

## 第 2 组骨架实现与本机验证

协作文档提交 `c3995a25ea5efab8217703f627c3401810b3819b` 已推送，`git ls-remote` 与本地提交一致。随后按 `openspec-apply-change` 继续任务 2.1–2.4。`project-add-tests` 按 RT/AC 场景补齐配置、授权、探针、日志、停机和真实依赖用例；`check_layout.py` 检查分层及运行/授权场景映射，测试函数名保留对应编号。默认运行装配只有 `/health`、`/live`，授权夹具均位于测试目录。

| 检查 | 实际结果 |
| --- | --- |
| 应用接口与单元 | `uv run --locked pytest -q --disable-socket tests/unit tests/api` 通过 25 项，覆盖授权失败和副作用、配置错误、探针协议、超时和日志脱敏。乱序复验使用 pytest-randomly，测试独立运行。 |
| 启动与停机 | `uv run --locked pytest -q tests/test_startup.py` 通过 4 项。首次 Gunicorn 进程因根日志配置缺失而退出 1，补齐日志配置后通过。复测核对配置错误在监听前退出，以及已进入健康探测的请求在 SIGTERM 后收到响应并有结构化停机记录。 |
| 真实依赖与制品 | Docker Desktop 29.4.2、Compose v5.1.3，独立项目使用临时卷、合成凭据、随机应用端口和隔离网络。冷启动、真实 MySQL 停启、真实 Qdrant 停启和撤就绪通过，应用只发布回环端口。测试版标识使用随机 40 位测试值；可追溯的 A/B 源码和制品仍需另验。 |
| 门禁 | `make check` 初次因 Debian 运行镜像高危发现退出 2。改用固定 Alpine 运行镜像后，剩余 5 项来自运行层随包管理工具引入的 Python 组件；移除运行层的打包工具后，保持扫描配置并完整复测，`make check` 退出 0。Gitleaks 扫描本地可达历史及待版本化工作文件，未发现匹配项。Trivy 的依赖锁和应用制品扫描通过当前 High/Critical 阻断。 |
| 门禁负向 | 临时副本将核心故障响应改成 200，原断言使 `make check` 退出 2，原工作区同一断言通过。独立副本缺失授权用例文件时，场景检查退出 1。外部测试数据库目标覆盖被集成夹具拒绝，pytest 退出 1，未创建测试项目。 |

运行直接依赖为 Flask（HTTP）、Gunicorn（WSGI）、PyMySQL（只读连通探测），其 RSA 依赖用于连接 MySQL 默认认证。开发直接依赖为 pytest、pytest-randomly、pytest-socket 和 Ruff。锁定版本在 `uv.lock`，安装元数据核对发现 cffi 为 MIT-0，需评审逐项确认；MySQL/Qdrant 基础设施分发条款、其他依赖元数据和人工评审待补。运行镜像调整用于修复制品实际发现，复测采用相同 High/Critical 阻断配置。

当前完成任务 2.1–2.4。本机阶段性故障注入不计作独立会话或 V4 的完整证据。任务 2.5 的 A 制品留存、远程 PR 检查与必需状态验证，以及后续成员复现、课程回滚和人工评审仍待完成。原始脱敏检查记录位于忽略的 `reports/2026-11-04-add-skeleton/`。

### 基线 A 与远程候选

骨架提交 `abba2291d9d4e13be3e277fed726fb12e6979151` 已推送并用远程引用复核。以该提交构建并保留本机镜像 `campusclaw-skeleton:abba2291d9d4e13be3e277fed726fb12e6979151`，镜像 ID `sha256:fb396ae9b3f1d498b024184a235448e425f5560abf8b16667e798d67ed69bda5`。

从同一提交、空卷及合成配置执行 `docker compose up --build -d` 后 6.32 秒内确认 `/live` 为 200，`/health` 为 200、两项依赖就绪、版本等于源码提交，健康响应的请求标识可在该版本 JSON 日志中找到。测试项目、网络和两份临时卷已清理，保留应用镜像。课内回退可用相同 Compose 配置和独立环境，设置 `APP_BUILD_REVISION` 为上述提交，再用 `docker compose up --no-build -d` 启用已保留的镜像，启动前核对镜像 ID。B 制品及切换耗时仍待取得。

提交附带 `Skeleton check` 工作流，调用仓库的 `make check`。[首个分支 CI 作业](https://github.com/WafoeX/CampusClaw-Team/actions/runs/41764433314)已完成，GitHub Jobs 接口显示 `Run the repository gate` 及整体作业均为 `success`。分支 CI 与首份代码 PR 上的必需检查状态分开判定，任务 2.5 保持开放。仓库管理员需添加必需检查 `make check`，评审在首次代码合并前核验缺失或失败确实阻断。

### 候选 B 门禁回归

在现有变更分支继续任务 3.1 的独立工作。复查 [PR #3](https://github.com/WafoeX/CampusClaw-Team/pull/3) 仍开放，GitHub 分支接口确认 `main` 已启用保护，`required_status_checks` 当时为 `off` 且无检查项。分支开发继续，任务 2.5 的远程设置及阻断实测仍开放。

`make check` 的三个测试阶段统一拒绝空收集、跳过、预期失败和只收集而未执行。工作目录环境的 `PYTEST_ADDOPTS` 不会缩小门禁选定的范围。依赖锁扫描纳入开发依赖，Compose 验证退出后按本次项目标签检查容器、卷和网络。`project-add-tests` 补七个退出语义用例，断网的单元及接口以种子 `1702` 乱序复跑通过 32 项。最新完整 `make check` 退出 0，共 32 项断网单元/接口、4 项进程和 1 项真实 Compose 集成测试通过，依赖锁扫描返回 0 项 High/Critical 发现。

真实扫描负向验证覆盖 CK-F03 与 CK-F05。无缓存的一次性 Trivy 容器断网，因无法取得漏洞数据库退出 1；Gitleaks 对临时目录中的合成秘密退出 1，输出未回显合成值。首次记录脚本对 Gitleaks 诊断文字的匹配失败，按实际 `leaks found: 1` 修正后重跑通过。CK-B01 另在独立项目用不兼容扫描器使 `make check-integration` 退出 2，实际核对项目标签下无容器、网络和卷残留。结合基线阶段的目标覆盖、缺用例及误报就绪演练，CK-N01、F01–F05、B01 均已有本机证据。合成秘密和故障配置只在临时环境使用。

### 候选 B 制品与课内回滚

候选 B 提交 `2934644270d694123c42fcf358c5fb676ec124a2` 已推送并核对远程引用。本机保留 `campusclaw-skeleton:2934644270d694123c42fcf358c5fb676ec124a2`，镜像 ID `sha256:9db3492b1990b9ea3df412b22d39a35c68683b68c8a01aa910ce7e24cbf78530`。实际启动使用本记录中的 A 镜像和由 B 提交新建的镜像，两个隔离 Compose 项目分别使用空卷和合成配置。

GitHub 当前提交的检查接口确认 B 的两次 `make check` 均为 `success`。[PR/分支检查一](https://github.com/WafoeX/CampusClaw-Team/actions/runs/41765977653/job/126364331849) · [PR/分支检查二](https://github.com/WafoeX/CampusClaw-Team/actions/runs/41765968710/job/126364299842)

本机回环代理固定一个入口。A 就绪后预热并切至 B，通过同一入口核对 B 版本和应用日志。停止 B 的 MySQL 后，入口 `/health` 返回 503、B 直连 `/live` 返回 200，入口暂停转发 `/live`。确认 A 就绪并切回，原入口恢复 200、两项依赖均就绪且报告 A 版本，响应请求标识与 A 的 JSON 日志一致。最后重启 B 的 MySQL 并验证 B 再次就绪，清理两组隔离资源并保留镜像。

| 检测 | 切换 | 恢复复核 | 发现故障至恢复 | 注入故障至恢复 |
| --- | --- | --- | --- | --- |
| 1.236 秒 | 0.008 秒 | 0.072 秒 | 0.080 秒 | 1.317 秒 |

演练退出 0。原始脱敏输出和临时代理脚本保留在本机忽略目录 `reports/2026-11-04-add-skeleton/`，跨成员复现、首份代码 PR 的保护与人工评审仍待完成。复现步骤见 [README](../../README.md#课内回滚复现)。
