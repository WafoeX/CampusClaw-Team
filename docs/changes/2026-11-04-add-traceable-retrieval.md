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

## 2026-11-05 第一组实施进展（开发候选）

基线为 `main` 的 `e76fb4e`，工作分支 `change/2026-11-05-traceable-retrieval-implementation`。按 `openspec-apply-change` 读取 proposal、design、五份增量规格和 tasks；按 `project-data-change` 核对旧版迁移、原文、归属、备份与回退；按 `project-add-tests` 以 CH-N01/B01/F01–F05 编写隔离 MySQL 测试。读取 AGENTS.md、README、安全/后端/测试/数据/运维/评审规范。未接触生产数据。

新增 0004 只增迁移：`chapters`、24 小时 `chapter_idempotency`、资料可空 `chapter_id` 及同班组合外键；同步唯一数据字典。既有资料迁移后为空章节，原文字节仍在 `material_bodies`。单步降级会丢失章节与归类，限 `campusclaw_test_` 合成库；旧应用回退期间应禁止章节写入，恢复本版本后重新归类。章节 API 已接入当前 Cookie 身份、默认拒绝策略及同源写入校验，提供目录、章节资料分页、创建/修改/删除、资料归类；删除及资料修订同事务。章节页面和完整并发测试尚未完成。

| 验证 | 实际结果 |
| --- | --- |
| 变更前 `make check-integration` | Docker Desktop 隔离 Compose，退出 0，1 个集成测试通过，作为上游可运行基线。 |
| 0004 初版 `make check-integration` | 隔离 Compose，退出 0，1 个集成测试通过；旧库→升级→重跑→单步回退→重升、A/B 同班外键拒绝、原文字节保真。随后新增了幂等表和章节 API，此结果不能代表当前候选。 |
| `.venv/bin/ruff format app tests/integration/chapter_api_runtime.py tests/integration/chapter_migration_runtime.py tests/integration/test_compose.py`、`.venv/bin/ruff check app tests/integration/chapter_api_runtime.py tests/integration/chapter_migration_runtime.py tests/integration/test_compose.py` | 退出 0；格式化 1 个文件，静态规则通过。 |
| `PYTHONPYCACHEPREFIX=/private/tmp/campusclaw-pycache python3 -m compileall -q app tests/integration/chapter_api_runtime.py tests/integration/chapter_migration_runtime.py`、`git diff --check` | 退出 0；仅检查语法与空白，不代表运行通过。首次不设缓存前缀的 compileall 因系统缓存目录权限退出 1，改写入临时目录后复测通过。 |
| 恢复 Docker 前的当前候选运行回归 | **当时未执行**。临时 Python 3.13/uv 路径消失，`.venv/bin/python` 指向不存在的解释器；Docker socket 当时不可用。后续复测见下节。 |
| 当前候选 `make check CHANGE=2026-11-04-add-traceable-retrieval` | 退出 2，停在 `openspec validate --all --strict`：当前环境找不到 `openspec` 可执行文件；后续检查未运行，不记为代码失败或通过。 |
| 当前候选 Ruff、语法及差异复测 | `.venv/bin/ruff format --check` 与 `.venv/bin/ruff check` 均退出 0，40 个文件已格式化；指定新代码 `compileall` 与 `git diff --check` 退出 0。`python3 scripts/check_layout.py` 用系统 Python 3.9 退出 1（缺少 `sys.stdlib_module_names`），不能当作布局门禁结论。 |

七类 Harness 自审：接口入口核对新增方法均在 `CHAPTER_POLICIES` 显式登记、参数边界及 401/403/404；业务逻辑核对修订号、重放、删除归未分类与原文不变；数据库核对组合外键、事务、迁移及回退，初版脚本通过但当前候选待复测；公共函数复用现有资料元数据和输入解析，单元回归待运行；错误处理核对统一 JSON/业务码和故障 503，注入用例待运行；安全核对当前数据库身份、跨班隐藏、同源及请求键，负向用例待运行；性能仅有索引与有界分页静态检查，固定数据压测未执行。人工教学意图和同伴代码评审待全部功能后安排。

本组 1.1 的课程首次索引触发方式仍待课程联络人取得正式依据，CA-04 主规格同步留到归档前。1.2 的学期日期与清理实名责任待登记；1.3 的浏览器走查与两名教师并发归类仍待验证。已恢复的隔离集成与页面接入见下节，三项仍保持未勾选。

### Docker Desktop 恢复后的复测

用户重新打开 Docker Desktop 后，`docker info --format '{{.ServerVersion}}'` 在授权访问 socket 下退出 0，服务端为 29.9.2。本机临时 uv、OpenSpec、Python 3.13 仍缺失，因此用 `/private/tmp/campusclaw-chapter-check.sh` 在随机命名的专用 Compose 项目中构建当前未提交源码，生成随机合成凭据和 `campusclaw_test_` 库，依次从容器标准输入执行四段仓库测试脚本。镜像标签使用基线提交 `e76fb4e` 满足启动格式约束，**镜像内容包含工作区未提交改动，不将该标签当作不可变提交证据**。

第一轮退出 1：既有 `auth_runtime.py` 的原文下载断言失败，实际 503/1500。经隔离复现定位为新 `materials` schema 克隆后隐式 `JOIN material_bodies` 无法确定左表，SQLAlchemy 抛 `InvalidRequestError`。改为显式以资料 ID 连接，不删原断言。再次使用全新随机项目运行，`auth_runtime`、`chapter_migration_runtime`、`chapter_api_runtime`、`rate_limit_runtime` 四段均显示 PASS，脚本退出 0。覆盖旧库升级/重跑/单步回退、跨班组合外键、原文字节、章节创建/归类重放、学生与匿名拒绝、外班同构、旧修订拒绝和删章故障回滚。`docker ps -a`、`docker volume ls`、`docker network ls` 按专用项目前缀复查均为空，临时资源已清理。此结果只代表这四段集成脚本；主机 `make check` 和完整 pytest 仍未执行成功，浏览器与两名教师并发归类专项未执行。

随后接入 `/chapters` 页面并同步 README 与产品页面清单。页面复用现有身份导航、样式令牌和同源写入，展示章节/未分类、资料分页及教师操作，提供加载、空、错误和重试状态；UI 的实际键盘与双宽度浏览器走查尚未执行。`node --check` 从脚本标准输入检查通过；首次直接以 `.html` 文件名检查时 Node 不识别扩展名，改用标准输入后退出 0。增加同一账号两客户端并发创建、同键同结果断言，以及页面师生/匿名入口断言。最后一次全新 Compose 项目运行四段脚本均 PASS，整体退出 0。新增页面的浏览器行为仍不能据此判为通过；1.1–1.3 保持未勾选。

用户要求安装真实 OpenSpec CLI。核对 CI 固定 `@fission-ai/openspec@1.13.0` 后，使用 pnpm 将该官方包安装到被忽略的 `node_modules/.openspec-cli/`，未改仓库技能或 shell 启动文件。首次普通沙箱访问 npm 注册表失败，获准网络重试安装退出 0；通过显式 PATH 执行 `openspec --version` 返回 `1.13.0`，`OPENSPEC_TELEMETRY=0 openspec validate --all --strict` 退出 0，12 个变更通过。CLI 仍提示检索 CA-04 与异步 IX-01 增量尚无主规格目标，归档前必须按上游顺序同步；严格验证通过不等于可归档。


## 2026-11-05 章节组功能交接补齐

### 变更说明

本轮用户要求继续推进任务，并明确以功能实现及实际运行为重点，学期起止、清理到期日和实名责任不再阻挡隔离功能开发。据此调整任务 1.2 的交付边界；上线前登记仍按数据字典办理，不填写虚构日期或姓名。基线为已同步的 `main` 提交 `b853e29917b76a6b9cadff2ec17f595c6220db8e`，本地分支 `change/2026-11-05-chapter-handoff`。本轮仅推进第 1 组，未实施切片、检索或模型问答。

- 修复切换章节后 `aria-pressed` 仍停在未分类的问题，同步按钮选中色和资料区的当前章节标题；补齐创建与编辑字段的必填、失焦校验及关联无效状态。
- 补充真实双教师竞争、同键重放、同序稳定、改名调序、跨班与缺失配对及原文字节验证；章节七个正式场景登记到 `tests/scenario-map.json` 的已实现映射。保留原有断言与门禁。
- 增加可重复运行的浏览器主路径：临时 HTTPS 代理、隔离合成库、独立 Chromium 配置，覆盖加载/正常/空/错误与重试、键盘创建与浏览、真实资料归类、学生查看原文、教师改名及删章归回未分类，宽度为 1440 和 390。
- 真实并发发现上游限流短事务的 MySQL `1213` 死锁，导致章节竞争偶发得到 `503/1500`。将该事务改为 `READ COMMITTED`，消除过期范围清理对新主体插入间隙的锁竞争，仍由联合唯一键与原子 upsert 保证配额；不增加业务重试，不变更配额与窗口，不变更数据库结构。同步数据字典并补新主体并发插入回归。

### 验证记录

环境：本机 macOS arm64、Python 3.13.15、Docker 29.4.2、OpenSpec 1.13.0，使用仓库锁定的 MySQL/Qdrant 镜像。测试只操作随机命名的 `campusclaw-check-*` 项目及 `campusclaw_test_*` 合成库。构建标签为集成夹具生成的临时标识，内容包含本轮未提交源码，不作为不可变提交制品。退出后夹具检查专用容器、卷和网络已回收。

编码前经 GitHub 的 `branches/main` 只读接口确认 `protected=true`、必需状态为 `make check`。本轮 OpenSpec apply 为 `spec-driven`、初始 0/12；全部上下文文件已读取。原有 CA-04 主规格同步及课程首次索引触发口径仍属 1.1 未决项，本轮尝试读取课程实践页失败，没有代填课程确认。

| 检查 | 实际结果 |
| --- | --- |
| `uv run --locked pytest -q --disable-socket tests/api/test_chapters.py` | 退出 0，20 项新增接口用例通过。未登录、学生与同源拒绝、非法输入均不进入章节服务。 |
| `make check-integration`（前期补强） | 退出 0，隔离启动、迁移与回退、真实双教师竞争、幂等及原文字节验证通过。 |
| 浏览器失败及修复 | 初期夹具未提供 Chromium Enter 的文本事件、资料上传夹具多传字段，已按实际输入契约修正；未改应用断言。随后真实复现章节切换选中状态错误，修复页面后主流程通过。临时代理出现过上游连接关闭诊断，最终主路径复测成功。 |
| 并发失败及定位 | 首轮完整门禁退出 2：CH-F05 竞争出现 `[(503,1500),(200,0)]`，没有勾选 1.3。单轮复测可通过，扩为 12 轮后续竞争并在多次全新环境中诊断，确认 `1213` 发生于 `request_limits`，保留日志。未删除断言或将 503 算成功。 |
| 并发修复与复测 | 限流短事务改为 `READ COMMITTED`。新回归初次因沿用旧时间记录，使清理确实需要等待另一事务，屏障超时；在本段隔离配额夹具先清除计数后复测通过。章节首次竞争及后续 12 轮各为一成功、一冲突；同主体最后一个额度竞争仍恰好一条允许，窗口边界与到期清理等原断言保持通过。 |
| 最终完整门禁 | `UV_CACHE_DIR=/private/tmp/campusclaw-progress-uv-cache OPENSPEC_TELEMETRY=0 make check CHANGE=2026-11-04-add-traceable-retrieval` 退出 0；12 项 OpenSpec、60 个 Python 文件格式、Ruff、分层与业务追溯通过；111 项断网单元/API、4 项启动、1 项真实 Compose 集成通过。集成耗时 19.97 秒。Gitleaks、锁依赖及应用镜像扫描通过。日志 `/private/tmp/campusclaw-chapter-handoff-final.log`。 |
| 最终浏览器回归 | 设置 `CAMPUSCLAW_CHROMIUM` 为本机 Chromium 可执行文件，以 `UV_CACHE_DIR=/private/tmp/campusclaw-progress-uv-cache uv run --locked pytest -q --tb=short tests/browser` 执行，退出 0，1 项通过，15.52 秒。日志 `/private/tmp/campusclaw-chapter-handoff-browser-final.log`。截图和结果在 `reports/2026-11-04-add-traceable-retrieval/browser/`；已检查 390 宽度截图，主操作在视口内且无横向溢出。 |
| 未执行 | 正式人工教学走查、同伴代码批准、固定 1000 条并发 10 的专项压测、课程首次索引口径确认、CA-04 主规格同步及生产发布未执行；不以本轮自动化替代。 |

### Harness 七类自审与评审结论

| 类别 | 手段、对象、判据及结果 |
| --- | --- |
| 接口入口 | 对照 CHAPTER_POLICIES 和新增接口测试，创建/修改/删除/归类均按已登记方法执行，正常响应与失败码分别断言；通过。 |
| 业务逻辑 | 实际双教师竞争、重复请求、改名调序、删章归回未分类和师生浏览器流程；仅一次修订成功、原文不变；通过。教学意图仍待人工确认。 |
| 数据库 | 复用已有 0004 迁移；空库/旧库升级、重跑、单步回退和组合外键验证通过。限流事务调整不改结构；新主体竞争与最后一个额度原子性均通过。 |
| 公共函数 | 复用既有页面视觉令牌、统一响应与 ChapterService，无新依赖；格式、Ruff、分层及既有单元/API 回归通过。 |
| 错误处理 | 页面故障后有请求标识及重试入口，删章中断全回滚，并发旧修订 409；修复新主体请求误报 503；通过。 |
| 安全 | 复用当前数据库身份和资源范围，保留匿名/学生/外班与同源检查及秘密扫描；通过。未引入新权限系统。 |
| 性能 | 有界分页与短事务检查、13 轮双教师竞争通过；浏览器两档宽度主流程通过。专项吞吐和正式使用者体验未执行，不能据此宣称性能验收完成。 |

实际使用技能：`openspec-apply-change` 输入为本变更的 proposal、design、五份规格与 tasks，读取 CLI 上下文后仅推进章节组；`project-add-tests` 输入为 CH-N01/B01/F01–F05 及真实缺陷，补接口、并发和浏览器回归并保留红灯；`project-data-change` 核对现有字典、0001–0004 迁移及后端/安全/数据/运维规范，执行隔离迁移回退并核对本轮无结构变化；`project-review` 读取 AGENTS、README、适用工程规范及变更工件，核对七类自审、真实门禁、页面清单与证据。

1.2、1.3 本轮可勾选，进度为 2/12；1.1 保留未勾选。README、页面清单、场景追溯及事务字典已同步。任务、页面状态清单及场景映射的改动均提交人工复核；本记录仅为助手自检，不代填批准。上述功能验证结束时尚未提交；本次提交整理见下节，人工批准与主干合入仍未完成。


### 分批提交与推送交接

用户随后明确要求细化提交并推送远程。本次用 `project-review` 核对全部差异、原始日志、规划制品、任务和评审规范，按依赖分为四组：

| 顺序 | 提交 | 范围 |
| --- | --- | --- |
| 1 | `b029a6c` · 消除新主体并发限流的间隙锁死锁 | 短事务修复、新主体并发插入回归、数据字典。 |
| 2 | `2c46f67` · 同步章节选中状态并补齐浏览器主流程 | 章节页面交互、字段校验及真实浏览器测试入口。 |
| 3 | `72d3345` · 补齐章节并发归类与场景追溯 | 新增 20 项接口回归、真实双教师并发与章节七场景映射。 |
| 4 | 本次文档提交 · 同步章节组任务状态与交接证据 | README、页面状态清单、任务勾选和本记录。 |

分组前 `git fetch origin --prune` 退出 0，主干基线仍为 `b853e29`；推送目标为 `origin` 的 `change/2026-11-05-chapter-handoff`。不将中间提交的快照当作独立完成验收。上节完整门禁和浏览器结果对应完整候选；本次另执行 `UV_CACHE_DIR=/private/tmp/campusclaw-progress-uv-cache OPENSPEC_TELEMETRY=0 make check-static`、`node --check tests/browser/chapters.mjs` 和逐组 `git diff --cached --check`，均退出 0。提交尾注使用真实变更、命令与证据文件。没有改写历史或跳过钩子，主干合入与人工代码复核仍待后续办理。


## 2026-11-05 Task 2.1：切片与索引存储基础

### 变更说明

用户继续授权推进任务。本轮从已合入 PR #19 的 `origin/main` 提交 `bc9aa217dbd983f3fff01d118f7c9597754c8912` 建立 `change/2026-11-05-indexing-foundation`，只实施第 2 组的 2.1，不夹带模型调用、构建发布或检索页面。编码前通过 GitHub `branches/main` 只读接口复核主干保护启用且 `make check` 为必需状态，并运行最新基线的隔离集成。1.1 的课程初次触发口径与 CA-04 主规格同步仍未完成，不将本次确定性基础验证替代这些确认。

- `app/services/chunking.py` 实现自动、自定义窗口与 Markdown 标题切片，版本为 `slice-v1`/`headings-v1`。保留 Unicode 码点坐标、原始空白及 CRLF，忽略一个开头 BOM；配置指纹与固定 UUIDv5 标识可重放。覆盖 64 片、32,000 码点及自动模式回退，无超限截断发布。
- `app/services/index_scope.py` 定义精确版本作用域和无正文的 Qdrant payload，仅生成确定性元数据，不连接 Qdrant。模型、维度、集合及发布检查由 2.2 实施时登记。
- 追加 `0005_indexing` 与冻结结构 `index_schema_v5.py`，建立构建、切片、去内容清理表及资料可空发布指针；同班、原文/索引/配置版本组合外键及坐标检查生效。既有资料默认无索引，原文、章节及修订不变。
- MySQL Compose 固定 ngram 2、关闭停用词，新切片表采用 `utf8mb4_0900_ai_ci` 和 FULLTEXT ngram。迁移在结构变更前核对有效配置，按已提交 DDL 步骤恢复。依据已核对的 [MySQL ngram 文档](https://dev.mysql.com/doc/refman/8.4/en/fulltext-search-ngram.html)与[全文索引重建文档](https://dev.mysql.com/doc/refman/8.4/en/fulltext-fine-tuning.html)，README 登记已有卷升级顺序。
- 既有认证空库白名单准确增加三张表；章节迁移回归的回退目标从相对 `-1` 改为明确 `0003_request_limits`，继续验证真正的章节前旧库，新增 0005 的单步回退另由本轮脚本验证。没有删除原有断言或放宽门禁。

### 验证记录

环境：本机 Python 3.13 与锁定依赖、OpenSpec 1.13.0、本机 Docker 的独立 Compose 项目及仓库固定 MySQL/Qdrant 镜像。只使用随机 `campusclaw-check-*` 项目和 `campusclaw_test_*` 合成库；专用容器、卷和网络由原夹具回收并检查无残留。测试镜像含工作区源码，使用夹具临时版本，不冒充已提交制品。

| 检查 | 实际结果 |
| --- | --- |
| 开发前上游基线 | `UV_CACHE_DIR=/private/tmp/campusclaw-progress-uv-cache make check-integration` 退出 0，1 项真实集成通过，22.19 秒。日志 `/private/tmp/campusclaw-indexing-baseline.log`。 |
| 确定性切片专项 | `uv run --locked pytest -q --disable-socket tests/unit/test_chunking.py` 最终退出 0，21 项通过；涵盖三模式、BOM、CRLF、补充字符/组合字符、前言、围栏伪标题、无标题回退、稳定 ID/作用域、窗口与容量边界。首轮 1 项失败是测试误读 AccessDenied 的属性名，改用既有 `status` 契约后通过，没有改业务判据。 |
| 首轮完整存储专项 | 退出 1；预期非法坐标由 MySQL 以 3819 CHECK 错误拒绝，驱动归类为 OperationalError 而非 IntegrityError。回归改为对两种驱动错误明确核对预期 3819 或外键 1452，其他错误仍失败；原本合法写入与查询已通过。失败日志 `/private/tmp/campusclaw-indexing-foundation-integration.log`。 |
| 存储专项复测 | `uv run --locked pytest -q --tb=short tests/integration` 退出 0，1 项通过，20.58 秒。旧库升级、重复迁移、模拟 DDL 中断后继续、空库与旧库、单步回退/重升、旧原文/章节保真、中文全文命中/空命中/单字边界与稳定排序、跨班和错版本外键、第二笔切片写入失败整批回滚通过。清理凭证可在无对应资料行时持久化。日志 `/private/tmp/campusclaw-indexing-foundation-integration-2.log`。 |
| 反例敏感性 | `uv run --locked python /private/tmp/campusclaw-chunk-mutation.py` 退出 0；仅在自动清理的临时应用副本把上限改为 32,001，原始 IX-B02 用例因未拒绝而退出 1，证明断言能发现放宽边界。工作区未保留坏实现。 |
| 静态与断网回归 | 首轮 `make check-static check-test` 静态及 132 项断网单元/API 通过；启动测试因沙箱禁止绑定回环端口为 3 通过、1 环境错误。未记成完整通过，后续以实际授权环境完整重跑。 |
| 最终完整门禁 | `UV_CACHE_DIR=/private/tmp/campusclaw-progress-uv-cache OPENSPEC_TELEMETRY=0 make check CHANGE=2026-11-04-add-traceable-retrieval` 退出 0；12 项 OpenSpec、66 个 Python 文件格式、Ruff、分层与场景追溯、132 项断网单元/API、4 项启动、1 项真实 Compose 集成通过（20.82 秒）；Gitleaks、锁依赖与应用镜像扫描通过。日志 `/private/tmp/campusclaw-indexing-foundation-final.log`。 |
| 未执行/不适用 | 本轮没有模型/向量调用或发布 API，提示词前后评测及浏览器新增入口验证不适用；正式检索效果、网关、发布 CAS、恢复清理执行与专项吞吐仍待对应后续任务。未运行旧应用镜像回退，仅验证旧结构查询及既有应用在扩展库的行为。人工代码批准与发布未执行。 |

真实入口为现有 `python -m app.auth_admin upgrade` 迁移命令及既有认证/章节接口；本组没有临时开放未完成的构建/检索 API。隔离集成确认 `/live`、`/health` 就绪，既有业务回归和数据库故障/恢复、Qdrant 降级及优雅停止保持通过。

### Harness 七类自审与评审结论

| 类别 | 手段、对象、判据、结果 |
| --- | --- |
| 接口入口 | 本轮无新增 HTTP 路由；核对原认证/章节/资料入口及升级命令，既有接口和真实 Compose 回归通过。构建入口按 2.2 待实现。 |
| 业务逻辑 | 21 项切片及作用域回归、容量反例破坏验证；坐标逐字匹配、无截断、版本 ID 可重放、超限明确拒绝，通过。 |
| 数据库 | 数据字典先行、0005 只增迁移；真实空库/旧库/中断恢复/回退、原文与章节保真、全文和约束通过。无共享或生产库操作。 |
| 公共函数 | 确定性切片与精确作用域只依赖标准库，配置版本集中；分层、Ruff 与原单元/API 回归通过。未新增依赖。 |
| 错误处理 | 参数与容量使用统一 AccessDenied 400/1000，错误配置迁移明确失败，写入第二步中断验证整批回滚；通过。 |
| 安全 | 服务不执行 Markdown/资料指令，Qdrant payload 无正文/章节/令牌；真实同班外键与既有授权回归、秘密和制品扫描通过。 |
| 性能 | 单份 32,000 码点、64 片和最大 1200 窗口均有界，默认自动回退为 62 片；参数绑定全文查询和稳定排序在真实 MySQL 验证通过。专项压测未执行，不作吞吐达标结论。 |

技能执行：`openspec-apply-change` 读取 CLI 指定 proposal/design/五份 specs/tasks，初始 2/12，按 ready 指引实施 2.1；`project-data-change` 输入为新索引表/发布指针/派生副本，读取字典、既有迁移和后端/安全/数据/运维规范，登记副本与回退并在隔离库实测；`project-add-tests` 输入为 IX-N01/B01/B02/F01 的确定性部分，执行边界、真实存储和破坏反例；`project-review` 对照 AGENTS、README、后端、安全、测试、运维、AI、数据与评审规范完成上述七类自审及文档核对。读取 `project-prompt-eval` 以判断适用性，本次仅首次建立确定性切片与存储，无现存模型或检索参数调优，未调用模型评测流程。

Task 2.1 可勾选，整体进度 3/12。完整 IX-01 仍缺 2.2 的发布、权限和故障契约，追溯清单继续把该完整能力标记为规划状态并注明已有基础回归；不将部分测试当完整能力验收。任务、Compose、设计和追溯说明等约束文件改动待人工复核。上述功能验证结束时尚未提交；分批提交整理见下节，人工批准与主干合入仍未完成。


### Task 2.1 分批提交与远端交接

用户随后明确要求细化提交并推送远程。本次用 `project-review` 核对当前差异、任务与规划、README、评审规则及上节完整门禁日志，按依赖分为四组：

| 顺序 | 提交 | 范围 |
| --- | --- | --- |
| 1 | `3646e9a` · 三种确定性切片与版本作用域 | 三模式切片、精确版本元数据及 21 项单元回归。 |
| 2 | `017ccb2` · 索引存储迁移与中文全文配置 | 0005 固定结构及迁移、Compose 全文参数、数据字典和既有迁移回归调整。 |
| 3 | `8d0e7ff` · 索引全文查询与兼容迁移 | 新的真实 MySQL 脚本、Compose 入口及完整能力尚未验收的追溯说明。 |
| 4 | 本次文档提交 · 索引基础任务与验证交接 | README、设计落点、Task 2.1 勾选及本记录。 |

`git fetch origin --prune` 退出 0，基线仍为 `bc9aa21`。本次另执行 `UV_CACHE_DIR=/private/tmp/campusclaw-progress-uv-cache OPENSPEC_TELEMETRY=0 make check-static`，12 项 OpenSpec、66 个 Python 文件格式、Ruff、分层及场景追溯通过；`git diff --check` 和逐组 `git diff --cached --check` 均退出 0。完整运行结果沿用上节同一实现候选的真实记录，不把中间提交视为独立验收或声称本次重复运行完整门禁。

推送目标为 `origin` 的同名 `change/2026-11-05-indexing-foundation` 分支。提交保留真实 Change/Verify/Evidence 尾注；本次未创建 PR、合并主干或发布。人工复核和后续 2.2–2.3 仍按任务清单办理。

## 2026-11-06 Task 1.1：上游基线复验与下一组输入核对

### 变更说明

用户调用 `openspec-apply-change` 要求继续检索与问答。CLI 返回 spec-driven、ready、3/12；本轮先完成尚未勾选的 1.1。源码基线为已同步主干 `e18c1930bca42cf2dff51ea2871d9837bba75989`，本轮分支为 `change/2026-11-06-index-builds`。保留上一轮限流交接的两份未提交文档；此次只新增本变更任务勾选及证据，不修改应用代码、结构、配置或既有断言。

### 实际验证与契约核对

| 对象 | 命令、结果与边界 |
| --- | --- |
| 规划 | `openspec status --change 2026-11-04-add-traceable-retrieval --json`、`openspec instructions apply --change 2026-11-04-add-traceable-retrieval --json` 均退出 0，实际读取 proposal、design、五份规格和 tasks。`openspec validate 2026-11-04-add-traceable-retrieval --strict` 退出 0，上游主规格尚未同步的归档提示保留。 |
| 受影响回归 | `UV_CACHE_DIR=/private/tmp/campusclaw-uv-cache uv run --locked python scripts/check_pytest.py -q --disable-socket tests/api/test_class_auth_material.py tests/api/test_access.py tests/api/test_chapters.py tests/unit/test_chunking.py` 退出 0，73 项通过，0.26 秒。 |
| 真实依赖及运行交接 | 沙箱首次 `docker info` 访问本机 socket 被拒，随后在获准访问 Docker 的环境执行 `UV_CACHE_DIR=/private/tmp/campusclaw-uv-cache make check-integration`，退出 0，1 项通过，36.41 秒。使用独立随机 Compose 项目、合成 A/B 班及专用空卷；镜像扫描、双探针就绪、当前数据库身份、角色变更、注销/改密/停用撤销、两班资料读写隔离、原文版本及附件字节、上传/删除事务回退、删除凭证重放、章节和索引基础迁移回退、限流并发、MySQL/Qdrant 停启及排空均由现有真实依赖脚本断言执行。套件 finally 清理容器、网络、卷及专用镜像，并检查无项目残留；未执行生产或共享库操作。 |
| 直接输入 | 当前身份由会话联查账号获得，写事务通过 `lock_actor` 重验；资料正文版本为 `content_version`，元数据修订与正文版本分离；预览 UTF-8-sig 解码而下载保留原字节。章节移动只更新归类和元数据修订；切片和精确版本作用域可复用。现有删除撤销原文访问，但尚未接入索引删除补偿，该部分保留任务 2.3，不把原文回归当作新索引能力通过。 |

技能记录：`openspec-apply-change` 输入为本变更及 1.1，按 CLI 上下文读取工件、复验并勾选；`project-add-tests` 读取测试/安全规范与现有单元、API 和 Compose 入口，核对场景和副作用断言后运行已有回归，本轮无新行为故不增加镜像式测试；`project-review` 读取 AGENTS、README、评审规范及本变更工件/证据，区分本轮结果、历史结果、人工未执行和后续输入缺口。`project-data-change` 读取数据字典、0005 结构、数据/后端/安全/运维规范并核对副本与回退，执行既有隔离迁移回归，未新增迁移。已读取 `project-prompt-eval` 判断后续模型接入前提，本轮未调用模型或执行效果评测。

### 评审结论及继续实施所缺输入

1.1 的上游契约和自动化运行前置已验证，可勾选，整体进度为 4/12。CA-04 主规格同步仍仅为归档前置；人工验收与课程口径确认保留在全部功能完成后的项目最终验收，未用人工待办阻断本项。

2.2 的组输入要求“经确认的切片、限额和模型配置”。本轮仅核对配置键及是否设置，不输出秘密：仓库没有 `.env`，`.env.example` 没有网关/嵌入模型配置，当前进程未发现 OPENAI/EMBED/MODEL/GATEWAY 相关环境键；字典和设计也仍将集合、固定模型与维度留待 2.2 登记。已向用户请求可用网关地址、固定嵌入模型标识和维度，密钥须通过私有环境提供，不发到聊天或文档。缺少这些实际输入时不编造型号、维度、阈值、集合或真实模型验证结果，2.2 保持未勾选；后续构建、向量检索及问答尚未实现。当前等待配置答复，不代表需要提前开展人工验收。

文档更新后执行 `UV_CACHE_DIR=/private/tmp/campusclaw-uv-cache make check-static`，退出 0，12 项严格校验、格式、Ruff、分层和场景追溯通过；`git diff --check` 退出 0。CLI apply 复核为 4/12、ready（规划工件齐备），此状态不表示外部模型输入已具备。本轮未执行完整 `make check`、浏览器回归、模型调用或人工验收；本次仅整理上游回归和任务状态，约束文件改动仍待人工复核。

## 2026-11-06–07 Tasks 2.2–5.2：索引、检索、问答和 Docker 可运行交接

### 变更说明

用户随后给出课程网关、`course-embedding`/2048及`course-chat`，要求写入私有`.env`，MySQL/Qdrant使用Docker、最终展示通过Docker，并授权助手填写其余配置及继续任务。后续私有配置中的两项模型密钥已具备并实际调用成功；前节“等待配置”是当时状态，当前已解除。数据库、Qdrant、演示种子口令各自随机生成，`.env`权限600且被Git/构建上下文排除，未把值写入版本、聊天或报告。

仍在`change/2026-11-06-index-builds`，基线`e18c1930bca42cf2dff51ea2871d9837bba75989`；本节是未提交工作区候选，不是新提交/主干/发布。应用及部署配置74文件摘要为`279977c2bed8c291ba31643cdf7e898f1805a0a05f2467446d18cd78c732b394`，生成清单口径见忽略报告`environment.json`。运行机macOS 26.7 arm64，Docker29.4.2、Compose5.1.3。编码前通过GitHub公开REST复核main受保护且要求`make check`；连接器未能取得时使用只读REST，未改保护。没有创建独立聊天、PR、提交、推送、归档、公开发布或自填批准。

#### 实施内容与接口

- 构建：`IndexService`明确prepare/run/publish/cancel/recover；事务外计算切片与模型/Qdrant副作用，短事务校当前身份、班级租约、原文与索引配置版本。首次完整关键词版本可见，已有完整旧版重建保留旧版，向量点ID/payload/数量读回一致后才CAS发布。支持24小时同键重放、每班并发1、35秒租约、最多64片、每批32片及失效执行不可迟到发布。
- 存储：追加0006幂等受理及0007精确集合/无正文旧出处映射，没有改写已交付0005。退役正文片段被清除、旧出处去内容映射90天；删除同事务撤销原文、切片、发布事实并登记精确版本清理。CLI`python -m app.index_admin recover/cleanup`每批100，网络预算35秒，最多3次，失败1/5分钟退避后转人工，命令非零报告未收敛；完成凭证继续复核迟到写入，活动完整版本不被误删。恢复接流量前重放原文删除清单。
- 检索：当前班级与当前章节先求交，MySQL绑定参数自然语言MATCH、Qdrant精确class/scope_key预过滤后再回表验全payload。每路20、RRF k60、去重稳定排序、最多8条；空范围不执行无范围点查询，仍核对向量健康。关键词不依赖模型/Qdrant；向量或混合故障503且建议关键词，不冒充合法空结果。
- 出处：原文/索引版本和码点[start,end)绑定；合法旧版409，伪造/外班/已删404，绝不重指新片段。返回前重验身份、归属、范围和版本，浏览器用Array.from处理补充字符，纯文本及mark定位，不执行资料中的HTML/脚本。
- 问答：`grounded-qa-v1`固定system加当前问题/有限证据的user JSON，最多8片/12000码点完整前缀；空命中固定提示、对话调用0，无会话写入。JSON结构、证据编号、数值/单位/字段进行确定性校验，生成完成重验证据全集。畸形/伪引用/不匹配数值502，依赖503，在途来源失效409；不返回部分答案。主要结论语义支持仍需最终人工裁决。
- 模型：每次尝试均计共享每账号6/min；跨worker并发1使用数据库名+账号摘要的MySQL连接锁，自动提交、无行事务跨网络。单次调用15秒、瞬态最多重试1次/退避1秒、共享35秒预算，无工具调用、无历史注入。日志仅记服务器请求标识、配置摘要、模板版本、耗时与受限token计数，不记正文/回答/密钥。
- 页面：教师工作台切片方式/窗口/重叠、构建阶段与新键重试；`/search`、`/ask`共用范围和出处卡，加载/正常/错误/空态及键盘可用。问答默认hybrid，检索默认keyword。API字段、默认值、返回data与错误契约已同步design，数据副本同步字典，页面状态同步产品清单。

#### Docker 展示与依赖取舍

新增`scripts/start_demo.py`、`docker-compose.demo.yml`和`deploy/nginx.conf`，一条命令生成缺少的私有配置、本机证书、构建、迁移、合成种子并等待HTTPS就绪。`campusclaw-demo`是专用项目，四服务MySQL/Qdrant/app/gateway均运行在Docker，只有应用8000与HTTPS8443绑定回环，数据库和Qdrant无宿主映射。网关非root、只读根、cap_drop ALL、内存临时目录；固定官方NGINX1.30.6镜像digest`sha256:583b7f2fce1cdb8da5ad5c39ebd3c33b98b87d493190e548bdee1fa8c619c311`。本机自签证书30天，未修改操作系统信任库。演示环境留运行便于后续开发，不是公网发布。

曾尝试官方Caddy2.11.9，固定Trivy扫描发现go-jose/v3的HIGH `CVE-2026-116587`，该候选未通过，不加忽略项。改用上述NGINX后相同HIGH/CRITICAL扫描0项。参考[上游漏洞公告](https://github.com/go-jose/go-jose/security/advisories/GHSA-mgcc-cww5-fp2q)及[NGINX发布信息](https://nginx.org/)。NGINX只读启动先因chown和默认fastcgi临时目录失败，修正为宿主非root UID/GID及所有临时目录进入/tmp后启动成功；未通过增加特权或放宽根文件系统解决。

### 实际验证记录

除下表显式真实网关外，模型均为明确确定性替身；数据库和Qdrant为真实Docker依赖。原始报告在忽略目录`reports/2026-11-06-index-builds/`，截图另在`reports/2026-11-04-add-traceable-retrieval/browser/`，失败及复测日志保留。

| 命令/入口 | 实际结果与判据 |
| --- | --- |
| `UV_CACHE_DIR=/private/tmp/campusclaw-uv-cache OPENSPEC_TELEMETRY=0 make check CHANGE=2026-11-04-add-traceable-retrieval` | 退出0；12项OpenSpec严格校验、101文件格式/Ruff、分层、场景追溯、秘密扫描、锁文件HIGH/CRITICAL扫描通过；254项单元/API 2.05秒、4项真实进程启动2.20秒、1项Compose集成33.18秒。日志`completion-make-check.log`。集成包含下列全部脚本与固定34题。 |
| `index_build_runtime.py`由`verify_index_builds`执行 | 真实双库发布/重放/异键冲突/班级并发/租约过期/权限撤销/恢复/部分写/点错配；恰好64片暂停向量确认时首次关键词与完整旧版指针、状态及下载保真；真实入口32000码点自动回退62片发布、32001返回400且无构建/嵌入副作用。删除注入事务回退保留原文/切片/凭证；并发删除后迟到写入不能发布，补偿两次后零残留且外班点不变。将保存的旧数据库行隔离还原并双重放删除清单，不等同真实生产备份恢复演练。 |
| `retrieval_runtime.py`由`verify_retrieval`执行setup/down/delete | 真实中文MATCH及三模式、A/B范围、授权码点出处、真实旧出处409、移动期间输出409、关键词版本覆盖不全时向量503。真实停止Qdrant时关键词仍有命中，向量/混合及相应问答503且对话0调用；恢复后删除，三模式空且旧出处404。实际MySQL两个连接争抢命名锁429及释放重获通过。真实API问答24伏正确、伪编号/25伏502、超时503、生成期间重建409。 |
| `uv run --locked pytest -q --disable-socket tests/unit tests/api` | 最后独立执行254项通过2.10秒；两来源编号映射、8片/12000预算、无证据零调用、恶意材料作数据、10合法/10非法数值输出及MySQL/嵌入故障均有独立断言。完整门禁随后再次执行254项。 |
| `UV_CACHE_DIR=/private/tmp/campusclaw-uv-cache CAMPUSCLAW_CHROMIUM=… uv run --locked pytest -q --tb=short tests/browser` | 退出0，1项17.62秒，`completion-browser.log`。真实Chrome/临时HTTPS/专用双库；键盘登录→章节→构建→检索→出处，390/1440无横向溢出；码点定位前缀含emoji且高亮实际非0起点，四态503重试、新键重试。/ask当前问题/默认hybrid及无命中/缺网关错误；正向回答显示使用显式CDP HTTP夹具，出处请求仍是真实授权后端，不能写成真实浏览器模型正向调用。最终人工体验未执行。已目视核对移动回答和桌面检索截图。 |
| `evaluation_runtime.py` | 34题三模式各独立检索与问答，共204请求。keyword Hit@5/夹具支持率23/24，vector/hybrid24/24；三模式无答案10/10，HTTP失败0，跨片段组合覆盖100%。保留ngram2的单字漏召回，全部样本在分母。耗时仅为真实双库+模型替身/测试客户端，详见[工程评测](../eval/2026-11-07-retrieval-engineering.md)，不是正式教学或生产性能验收。 |
| 真实网关调参与适配器最小调用 | 用户配置的course-embedding2048与course-chat均实际成功。独立4资料+4正例+4负例批量嵌入得阈值0.449357，模型/集摘要及原始分离见[调参记录](../eval/2026-11-06-retrieval-calibration.md)。嵌入响应无model字段，修正为若提供则必须一致，维度/索引/有限非零校验不放宽。提供方不可变版本尚未提供，不能作为上线模型冻结通过。 |
| `uv run --locked python scripts/start_demo.py` | 退出0，升级/合成种子重跑、四容器就绪，受CA验证HTTPS `/health`为ready/mysql ready/qdrant ready。`demo-startup-current.log`。脚本不输出口令，实际本机入口`https://localhost:8443/login`。 |
| 私有环境注入后执行`scripts/demo_smoke.py` | 退出0，经Docker HTTPS+真实课程模型完成A/B合成资料构建、三模式、问答24伏及原文区间；外班详情404、外班唯一词无证据固定拒答。keyword13.36ms、vector414.30ms、hybrid503.59ms、问答2374.43ms，各仅1样本，不计算有效P95或宣称性能验收。请求`1d6b24f3037a4475b2369b6bf81786af`有embedding/chat/answered日志；`e78dd2cfec3c444a85582da0fc216a78`仅no_evidence+HTTP，无chat事件。见`real-gateway-smoke.json`。 |
| 网关镜像固定Trivy扫描 | 原Caddy失败日志`caddy-image-scan.log`保留；NGINX扫描退出0，HIGH/CRITICAL0，`nginx-image-scan.log`。没有删门禁、忽略CVE或将未扫描写为通过。 |

失败及修复保留：SQL初版literal_column内的`:query`未绑定导致真实检索503，改为SQLAlchemy MySQL `match(...against=query)`后通过；删除故障注入曾使用不同engine而未触发，改在实际MaterialService连接注入，仍保留503和回退断言；章节/索引复用账号耗尽60/min导致429，改为各专项独立账号与班级，未改阈值；限流迁移夹具曾在检索setup/down之间删除章节，调整隔离执行顺序；场景追溯不接受不唯一断言，按分支命名计数与合并收敛/外班保留判据，未修改追溯校验器。相关red日志`retrieval-integration*.log`、`sixty-four-delete*.log`、`cleanup-*.log`均留存，成功复测纳入最终完整门禁。

### Harness 七类自审及技能记录

| 类别 | 手段、对象、判据与结果 |
| --- | --- |
| 接口入口 | 对照design核API、method策略、严格字段与code/data；API回归及真实A/B接口断言通过。`tests/scenario-map.json`将四项能力由planned改为实际pytest/Compose脚本唯一断言，未弱化校验器。 |
| 业务逻辑 | 核受理/关键词/完整发布/失败/过期/删除状态与CAS；真实64片、超限、旧版保留、在途撤权与问答重建断言通过；教学意图与语义裁决待最终人工。 |
| 数据库 | 核同班组合过滤、短事务、幂等与追加迁移，真实空/旧库、重跑、隔离降级/重升、事务回退、连接锁及删除重放通过；生产恢复与实名留存责任未执行。0007降级会丢集合/旧出处映射，正式应用回退应保留扩展库。 |
| 公共函数 | 核码点切片、scope、RRF、预算、数值校验共享契约；单元及边界通过，没有引入HTML执行或通用上传脚本入口。 |
| 错误处理 | 核匿名/外班同构、503故障与200空区别、502输出拒绝、409来源失效；API/双库/浏览器复现通过，无异常正文/凭据进入响应。 |
| 安全 | 核当前数据库身份、每次资源归属、精确payload回表、原文纯文本、环境及镜像边界；现有秘密/依赖/镜像门禁与基本反例通过。独立攻击矩阵、破坏授权/发布检查、全资产专项审计交安全预检，不宣称已完成。 |
| 性能 | 核每批32/总64、召回20/输出8、限定范围1000、35秒与共享配额，无无限队列；固定夹具各模式34样本时延和真实单次时延分开记录。1000资料/并发10压测、真实模型全量P95与真人体验未执行，不能写性能验收通过。 |

本轮实际使用`openspec-apply-change`（输入本变更2.2–5.2，读取proposal/design/五规格/tasks并按组推进）；`project-add-tests`（读取测试/安全/后端规范及现有三类测试，新增上述单元/API/真实依赖/浏览器回归）；`project-data-change`（读取字典、0005–0007与数据/运维/后端规范，核副本、迁移、删除恢复及隔离回退）；`project-prompt-eval`（读取AI规范、模型/检索设计及调参/固定夹具，执行真实调参、20输出固定校验、34题三模式与真实烟测并分开报告）；`project-review`（读取AGENTS/README/适用八规范、全部本变更工件、差异与实际报告，执行七类自审、门禁和文档同步）。未调用发布技能，因为没有请求正式发布。

规范生效四层证据分别为：入库规则及工件已读；生成代码按授权/分层/事务/有限证据落实；脚本实际校验及保留red/复测；真人确认和交叉评审尚未执行。本会话AI自审不伪装成独立会话验证或人名批准。

### 交接结论

Tasks2.2–5.2功能及适用自动化已满足，可勾选，整体12/12实现交付。可从本机Docker演示及同分支源码继续下游开发；项目其他功能并未因此完成。人工操作、课程口径、模型不可变版本/实名责任、正式真实效果裁决及最终性能/体验仍按项目最终验收与上线要求执行。合并前代码评审、约束文件复核独立保留；未批准合并，未公开发布。上游CA-04主规格同步仍为归档前置，本轮不自动归档。


收尾复核：`make check-static CHANGE=2026-11-04-add-traceable-retrieval`在新增启动脚本和文档勾选后再次退出0（102文件，12项规约、格式/Ruff/分层/场景映射通过）；`make check-secrets`退出0，`git diff --check`退出0。CLI apply实际返回12/12、remaining0、all_done。烟测脚本按每次独立合成章节隔离，保留已有演示数据后重跑通过；上表为最后一次各模式1样本，事件已按请求标识断言有证据包含chat、无证据不含chat并保存`real-gateway-events.json`。最后四容器仍运行，app/mysql/qdrant健康，受本机CA校验的HTTPS health为ready。任务勾选不触发归档、合并或人工批准。


## 2026-11-07 分批提交与远端交接

用户明确要求“细化提交，并推送到远程仓库”。本次使用`project-review`核对磁盘AGENTS、README、安全/评审/运维规范、本变更proposal/design/specs/tasks、67个变动文件及已有证据。`git fetch origin --prune`退出0；开始时HEAD与origin/main均为`e18c1930bca42cf2dff51ea2871d9837bba75989`、左右差异0/0，远端尚无本变更分支。保留原有限流交接文档，单独提交，不混入模型配额实现。

本轮重新执行`UV_CACHE_DIR=/private/tmp/campusclaw-uv-cache OPENSPEC_TELEMETRY=0 make check CHANGE=2026-11-04-add-traceable-retrieval`，退出0：12项严格规约、102文件格式/Ruff/分层/场景映射、秘密/依赖及集成镜像扫描通过，254单元/API 2.10秒、4启动2.24秒、真实Compose集成1项33.74秒；日志`reports/2026-11-06-index-builds/push-make-check.log`。仅拆分提交，不修改业务逻辑或重复执行真实付费模型调用/浏览器；其结果沿用前节同一业务实现的实际证据。

| 顺序 | 提交 | 范围 |
| --- | --- | --- |
| 1 | `db4ef67` | docs: 完成限流与场景追溯的实现交接 |
| 2 | `e9e1fb5` | feat: 接入课程嵌入配置与共享模型配额 |
| 3 | `eae2ccd` | feat: 实现有界索引发布与精确删除补偿 |
| 4 | `887b70f` | feat: 实现班内三模式检索与版本化出处 |
| 5 | `d6a6f6f` | feat: 实现有限证据问答与引用数值校验 |
| 6 | `b1457eb` | feat: 接通索引工作台与检索问答页面 |
| 7 | `0ffc99c` | test: 补齐检索问答的双库浏览器与固定评测 |
| 8 | `408608c` | feat: 提供本机 Docker HTTPS 展示与真实网关烟测 |
| 9 | 本节文档提交 | README、数据字典、页面清单、课程交接、设计及12/12任务与本记录。 |

分组按模型基础→索引及清理→检索→问答→装配页面→三类回归/评测→Docker展示→文档的依赖推进，单独保留限流交接。完整门禁针对最终组合候选，不把中间快照宣称为独立功能验收。所有提交保留真实Change/Verify/Evidence尾注，逐组以精确路径暂存并执行`git diff --cached --check`，没有跳过钩子或修改Git身份。`.env`、证书私钥、运行数据和原始报告均受忽略且未暂存。

暂存新增文件时发现`docker-compose.demo.yml`末尾多余空行（原未跟踪文件不在普通git diff范围），差异检查非零阻止该组提交。仅清理文件尾空行，原有配置不变；复测`docker compose -p campusclaw-demo -f docker-compose.yml -f docker-compose.demo.yml config --quiet`、`make check-static CHANGE=2026-11-04-add-traceable-retrieval`均退出0，再完成该组提交。失败与修正如实保留，未跳过检查。

目标为`origin/change/2026-11-06-index-builds`，使用普通推送并建立跟踪，随后用远端引用核对最终提交。此授权用于提交和推送本变更分支，未请求创建PR、合并main、归档或正式发布；人工评审/最终真人验收仍按现有调度保留。约束文件的本轮改动仅同步实际实现状态及场景入口，待人工复核；助手自审不作为批准。最终推送命令与远端一致性保存在忽略报告及本次回复中，不预填尚未执行的远端成功。
