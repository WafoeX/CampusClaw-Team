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
