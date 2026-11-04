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

### 规范生效技术预演

基线为交付分支提交 `1a7787768a2225d31949159fb79f9ac8865a6a20`。从本地独立克隆创建临时分支 `test/lesson-07-v3-v4`，移除远程入口，合成样本快照为 `76b8566555545687dc4a1ab23e65614f81e84a12`。以临时 Compose 项目和回环浏览器验证一张资料页、一读一写接口。合成身份与数据只由临时装配加载，交付候选的应用工厂不注册样本路由。

| 核验 | 结果 |
| --- | --- |
| 正向接口 | 匿名写入 401，低权限写入 403，跨班读写 404，拒绝时存储无变化。合法写入 201，同键同内容重放 200 且仍为一条，同键改内容 409，空名称 400。统一响应的请求标识与头部一致。初次分层检查发现仓储反向导入业务类型，改为由业务层构造资源范围后复测通过。 |
| 正向页面 | 无头 Chromium 实际观察加载→错误→空→正常四状态，通过 Tab、Enter 完成重试和提交，检查可见焦点和正文对比度 17.74:1。首次浏览器驱动的 Enter 事件未触发默认按钮动作，补齐字符事件后复测通过。隔离正向样本的 `make check` 退出 0，35 项断网单元/接口、4 项进程和 1 项 Compose 集成通过。 |
| 自造样式 | 只改标题字号为自造值。原样式检查指出 PROD-07，退出 1。 |
| 业务层直连数据库 | 只加入直接调用 PyMySQL 的查询样本。分层检查指出业务层导入适配依赖，退出 1，查询未执行。对应 BE-01/05。 |
| 未登记入口 | 在隔离装配中额外注册入口，用有效合成身份访问。返回 403/1200，无数据，处理器及写入未执行。对应 SEC-01。 |
| 删除已有授权 | 只移除写入服务的资源归属检查。用另一班合成账号重放同一写入，原断言捕获错误的 201，pytest 退出 1。恢复后同一回归重新通过。对应 SEC-03/04。 |
| 核心故障误报 | 只将未就绪的 HTTP 503 改成 200。原健康断言失败，完整 `make check` 退出 2。对应 OPS-03/TEST-07。 |

每项单独恢复后均复跑完整 `make check`，五次退出 0。临时实验仓库和浏览器配置已清理，交付候选的路由表只含 `/health`、`/live` 的 GET/HEAD，跟踪文件中没有样本。清理后对原分支复跑 `make check` 退出 0，共 37 项测试，包含真实 Compose 冷启动。原始脱敏命令输出、浏览器驱动和最小样本差异保留在忽略目录 `reports/2026-11-04-add-skeleton/`。这些结果供后续 V3/V4 人工复核。独立会话 V2、正式 V3/V4 人工结论、三名成员各自冷启动及首次代码合并门禁尚未取得，任务 3.2、3.3 和 3.4 保持开放。


### 主干合并后复验与文档同步

#### 变更说明

2026-11-04，用户要求继续完善项目骨架。本轮按 `openspec-apply-change` 推进第 4 组任务中的 4.2，使用 `project-review` 做交付自检。读取根 AGENTS/README、OpenSpec status/apply 指向的 proposal/design/三项 specs/tasks、测试/安全/运维/评审规范及真实门禁、容器与测试文件。CLI 返回 spec-driven、ready、8/15；4/4 规划齐备与实施验收分别判定。

本轮从远程克隆于 `/Users/rice/Downloads/campusclaw-team`，基于 main `90817fb67b841ab2011319903e79079b88a1ce1e` 创建 `change/2026-11-04-skeleton-main-verification`。工作流增加 main 推送触发，继续调用原 `make check`，检查阶段与阈值不变；同步设计及 CK-N01 的执行入口说明。README 修正骨架仍在分支的过时表述、补充版本核对及存活/就绪区别，课程入口明确区分历史表和当前状态，新增[验收收尾](../lesson-07/acceptance.md)集中列明真实缺口及操作步骤。未引入业务路由、模型调用或数据迁移。

#### 验证记录

| 检查 | 实际结果 |
| --- | --- |
| GitHub 合并与评审 | 只读查询 PR #3 及 reviews；`ricemin0216` 于 UTC 04:01:26 批准，UTC 04:01:38 合并到上述 main。批准事实不扩展为课程外部证明齐备。 |
| 主干保护 | 分支接口返回 protected=true；必需检查 enforcement_level=off、contexts=[]、checks=[]。确认任务 2.5/3.5 仍有缺口；本轮未修改远程保护，也未执行直推探针。首次代码已合并而证据尚缺的历史偏差保留，不能以后补验证回填为合并前完成。 |
| 环境 | 本机 macOS arm64；Python 3.13.15、uv 0.12.16、OpenSpec 1.13.0、Docker 29.9.2、Compose 5.6.1。uv/OpenSpec 与 Python 安装于临时目录，依赖按 uv.lock 安装；Docker 初始未启动，启动 Docker Desktop 后继续。 |
| 完整门禁 | `make check` 退出 0；Ruff 格式/静态、分层及场景追溯通过；断网单元/接口 32 项、进程 4 项、真实 Compose 集成 1 项，共 37 项通过。Gitleaks 未发现匹配项，依赖锁 High/Critical 扫描为 0；集成中候选镜像扫描通过，原阈值保持。原始输出保留于忽略目录 `reports/main-make-check.log`。 |
| 主干干净源码冷启动 | 从 git archive 导出 main 精确提交，在独立项目 `campusclaw-main-275786d53319` 使用临时合成配置、动态端口与空卷执行 `docker compose up --build -d`。启动、探针及协议核验合计 12.179 秒；匿名 /health 为 200/ready，两项依赖 ready，版本等于 main；/live 为 200，两个 HEAD 均无正文，根路径及静态入口 404、POST /health 为 405。 |
| 主干版本、路由及日志 | 实际镜像 `campusclaw-skeleton:90817fb67b841ab2011319903e79079b88a1ce1e`，ID `sha256:b70fe910276a3b02d28487562abbd147ad352cf1af7df26fb8bf5265d3bd5813`，保留本机镜像。容器内默认应用路由只含 /health 与 /live 的 GET/HEAD；健康请求标识与 JSON 日志匹配。报告为 `reports/main-verification.json`。 |
| 隔离清理 | 上述主干项目 down --volumes 后，按本次项目标签枚举容器/网络/卷均无残留；保留本机镜像。完整门禁的集成套件也执行其隔离清理断言。 |
| 工作流配置 | 用 YAML 解析器读取实际工作流，确认 PR(main)、push(change/**、main) 均保留且作业执行 make check。主干推送的远程触发需工作流合并后取得实际运行结果，本机解析不充当远程触发证明。 |

#### 评审结论与剩余项

助手自检：本轮差异限 4.2 的主干复验、CI 触发与文档同步；CI/OpenSpec 属约束文件，按 REV-08 待人工复核。本轮没有授权/AI/迁移行为变更，相关业务专项验收不适用；真实容器依赖检查已执行。文档收尾后另执行严格规约、链接与差异检查，结果以下方追加为准。

任务 4.2 已推进文档与主干冷启动部分，但仍保留未勾选。7 项未完成任务维持开放：缺必需检查及阻断实测、V2、正式 V3/V4 人工结论、三人跨机器复现、角色与教师访问等外部证明，以及最终归档/标签。当前分支的人工评审尚未发生，既有 PR #3 的批准不能代替本轮批准，也不能代替全课验收。

文档收尾复核：`make check-static check-secrets` 退出 0，最终差异的严格规约、格式、静态、分层/场景和机密扫描通过；`git diff --check` 退出 0，73 个本地 Markdown 链接目标有效。首次临时链接检查器误将带括号的原有 PDF 文件名截断，改用支持括号的解析规则后通过，未修改原文件名。最终运行/构建输入与 main 一致，应用、测试、Dockerfile、Compose 和依赖锁无差异。本轮工作区改动尚未提交或推送，远程工作流触发与本轮人工评审未执行；原始收尾输出保留于 `reports/main-final-review.log`。

### 评审候选准备（2026-11-04）

用户继续要求开展下一步工作，本轮沿用 `openspec-apply-change` 与 `project-review` 推进任务 4.2 的候选提交及评审准备。重新读取根规则、README、全部骨架规划与任务、评审规范；CLI 返回 spec-driven/ready、8/15 完成。远程 main 仍为 `90817fb67b841ab2011319903e79079b88a1ce1e`，当前没有开放 PR。GitHub 连接具有 push 权限，但 admin/maintain 均为 false；main 的必需检查仍关闭。提交仅包含前述八个 CI/规划/文档文件，运行源码和构建输入未变，沿用本机完整 37 项门禁及主干冷启动记录。

本轮准备在既有变更分支提交并创建评审 PR，让远程工作流对候选实际执行完整门禁；提交、PR 和 CI 的实际结果随后追加。必需检查设置、真实保护拒绝、跨成员复现与人工验收仍由对应角色完成，不自动合并或关闭任务。


### 全部任务核对、归档追溯修复与用户范围澄清

用户明确要求推进全部 15 项任务并在完成后推送，随后说明教师只需看到仓库内容，不需要加入或单独确认访问。本轮据此取消当前 README、骨架 proposal/design/tasks、评审规范及课程验收说明中的教师邀请/单独访问证明要求；只读 GitHub 仓库接口确认 private=false、visibility=public。历史证据保留旧核对记录并增加当前说明，不再将该项列为阻断。用户已表示会安排管理员设置必需检查，其实际生效结果尚待查询。

按 `project-add-tests` 检查 4.3 的归档准备时发现真实缺陷：现有脚本只匹配额外日期前缀，找不到归档工具为已带日期变更生成的标准目录 `archive/2026-11-04-add-skeleton`。新增 7 项 CK-N01/CK-F02 回归，涵盖活动/标准归档/历史归档、重复归档、缺失用例/规格及缺失变更；修复前 pytest 退出 1（4 失败、3 通过），修复后退出 0（7 通过）。脚本增加标准目录候选并继续要求归档唯一；没有放宽场景缺失或授权用例缺失的失败判据。

对完整应用、脚本、测试和规约的隔离副本实际移动到标准归档路径，分层/场景追溯退出 0；再删除授权用例文件，检查退出 1 并报告九项 AC 场景缺失。临时副本自动清理，真实活动变更未移动。本机完整 `make check` 退出 0，共 39 项断网单元/接口、4 项进程、1 项真实 Compose 集成，合计 44 项。机密、依赖及制品扫描通过原有阻断阈值。原始日志在 `reports/archive-trace-before.log` 与 `reports/archive-fix-make-check.log`，新设计说明与验收清单记录标准归档追溯及全部 15 项的真实状态。

提交与推送：首份本地提交为 `33e090f8dab636878bbb5984592b40db48ccfa9b`，独立变更分支，本机工作流及文档准备已保存。普通 HTTPS 推送先无响应后限时重试超时；HTTPS 连通检查至 github.com:443 超时。本机 SSH 连接因无已知主机键退出 128，进一步确认没有 .ssh 目录或 SSH agent 身份，未关闭主机验证或创建身份冒充。GitHub 连接器对包含八个文件的树创建返回 403 Resource not accessible by integration；再对仅脚本/测试、完全不含工作流文件的树创建仍为同一 403，说明不能仅归因于工作流权限。尽管用户权限接口 push=true，应用实际写入权限仍受限，远程分支未创建、PR/远程 CI 未执行；这些失败不作为主干保护拒绝证据。

当前不能将 15 项全部勾选。8 项既有完成状态保留，7 项仍有管理员、成员独立环境、正式人工评审及归档标签等条件；最新矩阵和管理员完整清单见[验收收尾](../lesson-07/acceptance.md)。本轮不替人员签署验收，不在缺证时归档或打完成标签。脚本、OpenSpec、评审规范等约束差异按 REV-08 待人工复核。


教师术语核验：用户进一步明确“教师”指课程任课教师，而非系统实现的教师角色。实际差异核对确认 app、产品设计规范和安全开发规范均无改动；教师/学生认证、教师工作台、班级隔离、教师仅可看授权反馈及本班测验提交等业务要求保留。将当前课程交付文档中的相关称呼明确为“课程任课教师（项目评阅人）”，并在 README 和验收入口写明两个身份边界；历史证据中的仓库访问教师同样指课程评阅人，不代表系统角色权限。


### SSH 推送恢复与远程门禁

用户完成 SSH 配置后，本轮实际运行 `ssh -o BatchMode=yes -o ConnectTimeout=10 -T git@github.com`，GitHub 返回已成功认证为 ricemin0216。该测试因 GitHub 不提供 shell 而退出 1，与认证成功提示并存，不判为认证失败。origin 已为仓库 SSH 地址；普通 `git push --set-upstream origin change/2026-11-04-skeleton-main-verification` 成功，远程引用核对对应 `c717188811a5a6f788a673a35851ebff774bb022`，包含之前的 `33e090f` 与归档追溯修复提交。

[远程 Skeleton check](https://github.com/WafoeX/CampusClaw-Team/actions/runs/41776337351) 针对此提交 completed/success，作业 `make check` 及 Run the repository gate 均成功。此为变更分支推送检查，不冒充 PR 或 main 合并后的检查。本轮仅补充推送和远程验证记录，不改运行/构建输入。

连接器创建草稿 PR 返回 403 Resource not accessible by integration；通过浏览器比较页继续时控制接口超时，未能提交表单，因此尚无本分支 PR。比较入口为 https://github.com/WafoeX/CampusClaw-Team/compare/main...change/2026-11-04-skeleton-main-verification?expand=1 。推送已成功，应用 PR 权限与 SSH 推送身份分开判断。main 仍为 `90817fb67b841ab2011319903e79079b88a1ce1e`，必需状态检查仍关闭，不能把远程绿灯写成失败合并阻断已设置。任务仍为 8/15，待人工/成员/管理员条件不变。
