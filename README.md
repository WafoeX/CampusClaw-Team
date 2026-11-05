# CampusClaw 班级智能助学系统

基于可追溯知识库与 AI 应用平台的班级智能助学系统，面向 Freebird 三人小组学期项目。

**当前阶段：开发骨架已合入 `main`。** Cookie 登录、班级资料和教师工作台已在认证与资料开发候选接入，代码交付及合并状态以对应变更为准。课程验收进度见[验收收尾](docs/lesson-07/acceptance.md)。选题说明中的“已完成”“可复用”均指另一个仓库；其 226 项测试、浏览器验收、部署和模型调用证据不代表本仓库成果。

## 开发者快速开始

从 `main` 拉取代码后，用 Docker Compose 启动开发环境。在仓库根目录将 [`.env.example`](.env.example) 复制为 `.env`（已有则沿用），填写 MySQL 库名、应用账号及口令、管理口令和 Qdrant 密钥。默认从本机 `8000` 端口访问；若该端口被占用，在 `.env` 设置 `APP_HOST_PORT`，并同步替换下面的端口。

```bash
export APP_BUILD_REVISION="$(git rev-parse HEAD)"
docker compose up --build -d
curl -fsS http://127.0.0.1:8000/health
```

初始化期间先等 MySQL 和 Qdrant 就绪，再查看 `/health`，两项依赖均为 `ready` 后即可使用完整开发环境。部署入口按就绪撤流；业务请求各自处理实际依赖故障，应用进入排空后拒绝新的已登记业务请求。启动失败可用 `docker compose ps` 和 `docker compose logs app mysql qdrant` 定位；`/live` 可单独查看应用进程是否还在响应。

日常修改代码后，只重建应用，继续使用正在运行的 MySQL 和 Qdrant：

```bash
export APP_BUILD_REVISION="$(printf 'campusclaw-local-dev:%s\n' "$PWD" | git hash-object --stdin)"
docker compose up --build -d --no-deps app
docker compose logs --tail=50 app
```

这里生成的标识只用于当前克隆的本地迭代，避免覆盖以提交号命名的镜像。正式取证使用[干净源码启动流程](#骨架冷启动)。开发结束执行 `docker compose down`，下次启动可以继续使用原来的数据卷。

### 业务代码从哪里接入

| 要做的事 | 现有入口 |
| --- | --- |
| 注册路由、装配依赖 | 在 [`app/api/`](app/api/) 放 HTTP 处理器，由 [Flask 应用工厂](app/__init__.py) 注册并注入依赖。 |
| 编写业务逻辑 | 在 [`app/services/`](app/services/) 组织业务规则；[通用授权模块](app/services/access.py) 提供身份、功能权限及资源归属检查。新增受保护入口时，在应用工厂传入按端点和 HTTP 方法登记的策略及服务端身份解析器；确需匿名的业务入口通过 `public_routes` 登记 `(endpoint, route_rule, method)`。骨架默认只开放探针。 |
| 连接 MySQL、Qdrant 等依赖 | 在 [`app/adapters/`](app/adapters/) 放外部访问代码，由装配层传给服务；骨架已有连通探测，分层检查仅允许适配器导入 SQLAlchemy；锁定依赖、业务仓储和迁移随认证与资料变更加入。 |
| 新增检查 | [`tests/unit/`](tests/unit/) 放单元检查，[`tests/api/`](tests/api/) 放接口检查，[`tests/integration/`](tests/integration/) 放真实依赖集成。GitHub Actions 继续运行 `make check`；本地完整重跑按改动需要安排。 |

后续业务入口见[班级认证与资料入库任务](openspec/changes/2026-11-04-add-class-auth-material-ingest/tasks.md)。骨架的交付项见[开发骨架任务](openspec/changes/2026-11-04-add-skeleton/tasks.md)。

### 本地验证班级登录

以下命令适用于包含认证与资料候选代码的开发分支。认证候选使用同源 HTTPS。将 `APP_PUBLIC_ORIGIN` 设置为浏览器实际访问的 HTTPS 源，省略路径、尾随斜杠及默认端口。Compose 应用仍绑定本机回环，由本地 HTTPS 入口代理到应用端口。留空时可继续运行骨架探针。MySQL 就绪后使用应用镜像执行 `docker compose exec app python -m app.auth_admin upgrade`，再访问 HTTPS 入口的 `/login`。

只有专用 `campusclaw_test_` 前缀的合成库可种入测试账号。通过私有环境设置 `CAMPUSCLAW_SEED_PASSWORD`，运行 `docker compose exec -e CAMPUSCLAW_ISOLATED_DATABASE=1 -e CAMPUSCLAW_SEED_PASSWORD app python -m app.auth_admin seed`。账号为 `demo_a_teacher`、`demo_a_student`、`demo_b_teacher`、`demo_b_student`，重跑保留既有角色和口令哈希。登录后进入本班资料列表，可浏览、预览和下载。教师可从工作台上传文字或 UTF-8 文件、修改标题和排序、删除资料。见[数据字典](docs/data-dictionary.md)及[真实验证记录](docs/changes/2026-11-04-add-class-auth-material-ingest.md)。

使用 `make check CHANGE=2026-11-04-add-class-auth-material-ingest` 运行认证与资料的自动化门禁。命令启动并清理独立的 Compose 测试项目，使用合成 A/B 班数据。场景与断言的对应关系见[任务 4.3 复核记录](docs/changes/2026-11-04-add-class-auth-material-ingest.md#任务-43-自动化回归与评审交接)。

## 项目价值与用户场景

| 价值问题 | 本项目的回答 |
| --- | --- |
| 服务谁 | 一个账号属于一个班级的教师和学生 |
| 解决什么问题 | 资料分散、回答缺少依据、练习准备和教学反馈脱节 |
| 比现有做法好在哪 | 以本班材料和可核对出处约束回答，把教师审核、练习和反馈串成闭环，减少反复翻资料和无依据回答 |
| 如何验收 | 用两个班的师生走通资料→检索问答→教师审题与发布→学生提交→错题和统计，核对出处、权限、评分与真实测试证据 |

| 用户 | 场景 | 规划页面入口 |
| --- | --- | --- |
| 教师 | 组织章节与资料、重建索引、配置模板/技能/工具 | 教师工作台 |
| 学生 | 按章节浏览资料，检索与提问，核对出处 | 资料、检索、资料问答 |
| 教师与学生 | 使用 AI 应用，查看本人执行记录和会话 | AI 应用、个人记录 |
| 学生 | 反馈未解决问题、作答、查看开放后的答案与错题 | 会话、测验、错题 |
| 教师 | 处理教学反馈、审核题目、发布测验、查看本班学习情况 | 问题反馈、题库、测验、学习看板 |

具体路由、入口、术语及实现状态以[产品设计规范](docs/standards/01-产品设计规范.md)为唯一基线。

## 建设范围与进度

| 层次 | 范围 | 本仓库状态 |
| --- | --- | --- |
| 基础平台 | 教师/学生认证、服务端角色检查、班级数据隔离 | Cookie 认证、资料角色权限与班级隔离已接入 |
| 资料与知识库 | 文字、UTF-8 TXT/Markdown 上传，原文预览/下载/删除，自动/自定义/标题切片、索引重建 | 原文入库、组织、预览、下载和删除已接入，切片与索引由后续变更交付 |
| 检索与问答 | 关键词/向量/RRF 混合检索，有限证据、编号出处和引用/数值校验 | 待从零实现 |
| AI 平台 | 写作润色、学习规划、练习生成、资料问答，班级模板与变量预览 | 待从零实现 |
| 技能与工具 | 内置技能、JSON 技能校验及顺序模型步骤、受控 HTTP/MCP 接入与结果回填 | 待从零实现；上传脚本不执行 |
| 私有记录 | 模型参数与响应、技能步骤及工具结果，仅执行者可读 | 待从零实现 |
| 教学业务 | 章节组织、持久问答与来源快照、反馈及教师未解决问题处理 | 待从零实现 |
| 教学业务 | 单选/判断题库、人工编辑、AI 候选题与教师审核、测验发布及不可变快照 | 待从零实现 |
| 教学业务 | 作答草稿、一次正式提交、客观评分、截止后答案开放、错题与学习看板 | 待从零实现 |
| 可选提高 | 文本 PDF 导入、后台索引、检索效果实验页面 | 核心验收后择项，均未实现 |
| 效果评价 | 不少于 30 题的检索对照、依据充分率、无答案处理和耗时 | 待开展；实验页面可选，评价工作仍需完成 |

首版不引入跨班选课、多角色切换、主观题自动评分、自适应组卷或监考。功能详细设计和骨架分别通过后续 OpenSpec 变更推进。

选题原计划直接复用另一仓库的认证、资料与 AI 平台。上表将这些能力列为本仓库需重建的基础；选题新增的教学交付是章节组织、答疑与反馈、结构化题库与审核、测验与错题、学习看板。后台索引在核心教学闭环验收后实施。首版计划支持 1 MiB 原文保存与下载，每份最多 32,000 个 Unicode 码点参与检索，超出时上传界面提示按章节拆分。

## 技术方向

拟采用 Python/Flask、HTML 模板/CSS/原生 JavaScript、SQLAlchemy/MySQL 8、Qdrant、pytest、Docker Compose。浏览器只通过服务端访问数据及外部模型/工具。SQLite 仅用于适合的本地测试，不能代替真实 MySQL/Qdrant 集成验收。

主干已提供 Python 3.13 依赖锁、Flask 工厂及 Docker Compose。课程 Go/React 案例仅供规范写法参考。

## 文档与操作技能

每次会话从 [AGENTS.md](AGENTS.md) 开始。下列规则文件须按改动范围实际读取，普通 Markdown 不会自动按源码路径触发。

| 类型 | 规范 |
| --- | --- |
| 五类必修 | [产品设计](docs/standards/01-产品设计规范.md)、[后端开发](docs/standards/02-后端开发规范.md)、[安全开发](docs/standards/03-安全开发规范.md)、[测试](docs/standards/04-测试规范.md)、[部署运维](docs/standards/05-部署运维规范.md) |
| 三类补充 | [AI 应用](docs/standards/06-AI应用规范.md)、[数据](docs/standards/07-数据规范.md)、[评审与完成定义](docs/standards/08-评审与完成定义规范.md) |

| 按需流程 | 技能入口 |
| --- | --- |
| 实现任务或修复缺陷后 | [按规范补测试](.agents/skills/project-add-tests/SKILL.md) |
| 发布准备 | [按规范发版本](.agents/skills/project-release/SKILL.md) |
| 改提示词、模型或检索参数 | [改提示词并评测](.agents/skills/project-prompt-eval/SKILL.md) |
| 数据结构或生命周期变化 | [按规范做数据变更](.agents/skills/project-data-change/SKILL.md) |
| 交付自检和评审 | [按规范评审变更](.agents/skills/project-review/SKILL.md) |

原始依据：[规范资料](规范.md)、[选题说明](选题说明(1).pdf)及[课程网站](https://devops.hello1023.com/课件/第7课-课件-小组项目启动/index.html)。本次[提案](openspec/changes/establish-project-standards/proposal.md)、[组织方案](openspec/changes/establish-project-standards/design.md)、[任务](openspec/changes/establish-project-standards/tasks.md)及[验证记录](docs/changes/establish-project-standards.md)可互相追溯。

## 第 7 课任务与当前缺项

本节“课程任课教师”指评阅本项目的课程教师；系统内“教师角色”是产品业务身份。仓库查看方式的调整不改变系统教师的登录、班级归属、题库/测验操作或数据权限要求。

第 7 课要求**在本课内完成建仓库 → 定规约 → 立规范 → 落骨架**，取得不含业务功能、可以复现的启动基线。下文“后续变更”指实施顺序，不表示这些必交项可以延到下一课。当前 `establish-project-standards` 只交付规范载体；其任务全部勾选或 OpenSpec 严格校验通过，都不等于本课完成。

| 编号 | 本课要完成的任务与判据 | 当前状态与责任角色 |
| --- | --- | --- |
| C7-01 建仓与协作 | 小写短名、成员全加入、首次提交最小集合、忽略规则/许可状态、课程任课教师可查看仓库内容；编码前主干保护 | Git 与文档已建立；命名和首次提交范围有历史偏差；主干保护已启用；仓库公开，课程任课教师无需加入或另行访问确认；成员协作待课程核验，规则阻断已有历史记录；组长与运维责任人 |
| C7-02 骨架规约 | 独立变更具备 proposal、design、specs、tasks；能力→场景对应，每能力至少四条真实失败路径，严格校验通过 | 骨架四类规划齐备并严格校验通过，PR #3 已批准合并；课程逐项人工验收待完成；实施与评审责任人 |
| C7-03 五类规范生效 | 五类最小条目、规则入口与按需技能齐备；用页面、一读一写接口及违规样本验证规则能发现问题 | 八规范、五技能载体已建立；正向页面/接口及移除授权等隔离技术预演已有记录，V2 与正式 V3/V4 人工结论待完成；实施与评审责任人 |
| C7-04 最小运行骨架 | 分层与通用授权机制、空值 `.env.example`、外置配置且缺失失败、匿名 `/health` 返回版本/时间/依赖状态、单行 JSON 请求标识日志、Dockerfile/Compose 一键启动 | 已交付，主干干净源码可启动并达到就绪 |
| C7-05 真实测试与门禁 | 健康能力正常/失败/边界用例，独立数据，一键门禁（本项目选 `make check`）；失败非零、改坏逻辑能变红 | 代码检查、断网测试和真实依赖集成已有结果，完整门禁与故障注入验收见[骨架证据](docs/changes/2026-11-04-add-skeleton.md) |
| C7-06 独立会话与跨成员复现 | 无历史会话只给仓库/变更名能执行，另一次相同改动遵守同一规范；每名成员在自己机器按 README 冷启动 | 未执行；当前审查不充当独立会话或跨机器证据；全组与评审责任人 |
| C7-07 回滚、归档与标签 | 本课完成当前/前一可运行版本的回滚演练，记录步骤/耗时；验收及人工评审后归档骨架变更，建立真实版本标签，证据汇总 `docs/lesson-07/` | A/B 制品与本机回滚已验证，归档及版本标签待人工验收；运维与评审责任人 |

来源：[四步与课内完成要求](https://devops.hello1023.com/课件/第7课-课件-小组项目启动/pages/project.html)、[仓库与主干保护](https://devops.hello1023.com/课件/第7课-课件-小组项目启动/pages/repo.html)、[规约验收](https://devops.hello1023.com/课件/第7课-课件-小组项目启动/pages/spec.html)、[骨架五维核查](https://devops.hello1023.com/课件/第7课-课件-小组项目启动/pages/skeleton.html)、[本课回滚演练](https://devops.hello1023.com/课件/第7课-课件-小组项目启动/pages/std-ops.html)。深入核对的 33 页来源、正式任务清单、逐项缺口和关闭条件见[第 7 课证据入口](docs/lesson-07/README.md)，文档检查见[验证记录](docs/changes/establish-project-standards.md)。

五类规范是课程下限；AI、数据、评审是课程补充类别，本项目已经选用，其适用规则仍须执行。完整登录、资料问答、题库、测验等属于学期业务增量；骨架仍须明确通用授权检查位置与默认拒绝、显式公开健康入口，不能省略安全机制；30 题检索实验属于选题效果评价，也不是第 7 课骨架验收项。指标接入可按课件后移，日志字段本课必须确定。

2026-10-28 的审查修正只落实第 6 组文档核验，依用户“修正文档推送到main，不要提出pr”的单次授权直接推送 `main`，不创建 PR；该操作不等于课程通过或人工批准全部规范，例外见评审规范；本课独立骨架变更已建规约，后续按任务组实施。

### 四步启动状态

| 步骤 | 已交付载体 | 待验证现象 |
| --- | --- | --- |
| 建仓库 | 本地 Git、已配置的 GitHub origin、README、AGENTS.md、忽略规则及协作约定 | 推送结果见初始化记录和远端分支；主干保护已启用，成员独立复现待课程核验，规则阻断已有历史记录 |
| 定规约 | 本次纯文档变更的规划与校验 | 骨架四类规划和三段式场景已建立，教学业务规约随课次补齐 |
| 立规范 | 八份规则、五个技能、必读映射 | 独立会话待验证；代码正向与违规技术预演已执行，人工结论待完成 |
| 落骨架 | 已合入 main 的 Flask 服务、Dockerfile、Compose 和 Makefile | 本机和远程 CI 门禁已通过，A/B 制品和隔离回滚已验证；PR #3 已批准合并，课程剩余验收及标签待完成 |

本次载体交付不代表整课四步完成。文档自检、人工批准和运行验证分别记录，人工评审状态见验证记录。

仓库地址：[CampusClaw-Team](https://github.com/WafoeX/CampusClaw-Team)。获取仓库可运行 `git clone git@github.com:WafoeX/CampusClaw-Team.git` 后进入 `CampusClaw-Team`。以下启动说明适用于主干及包含骨架源码的变更分支。PR 批准/合并事实与课程验收分别记录，最新状态见[验收收尾](docs/lesson-07/acceptance.md)。Git 初始化及首次推送的核验见[仓库初始化记录](docs/changes/2026-10-27-initialize-repository.md)。

## 命令与配置状态

在仓库根目录执行。规约检查需要 OpenSpec CLI，构建和集成测试需要 Docker 与 Compose，本机运行测试和静态检查需要 uv 及 Python 3.13。

| 命令 | 用途、前提 | 状态 | 退出码与证据 |
| --- | --- | --- | --- |
| `openspec status --change establish-project-standards` | 查看规划状态 | 可用 | 0 成功；不代表应用已实现 |
| `openspec instructions apply --change establish-project-standards --json` | 查看实际任务进度 | 可用 | 0 成功；以任务完成数判进度 |
| `openspec validate establish-project-standards --strict` | 校验本次规划 | 可用 | 0 通过，非 0 失败；证据见本次验证记录 |
| `make check` | 顺序执行规约、分层、格式、pytest、秘密和漏洞扫描、独立 Compose 验证 | 主干可执行，课程完整验收待完成 | 任一子项失败即非零退出 |
| `docker compose up --build -d` | 用固定镜像和外置配置启动骨架 | 已有隔离项目验证记录 | 以匿名 `/health` 返回 200 及对应版本确认就绪 |
| `uv run --locked pytest --disable-socket tests/unit tests/api` | 断网执行单元和 Flask 接口测试 | 主干可执行 | 真实依赖集成单列 |

### 合并检查与主干复验

`Skeleton check` 对目标为 `main` 的 PR、`change/**` 推送及 `main` 推送均运行 `make check`。[骨架复验 PR #5](https://github.com/WafoeX/CampusClaw-Team/pull/5) 已合入，[合并前检查](https://github.com/WafoeX/CampusClaw-Team/actions/runs/41778385185) 已通过。主干 CI 已通过。既有规则阻断记录和其他课程事项见[验收收尾](docs/lesson-07/acceptance.md)。

### 骨架冷启动

1. 从干净克隆检出全组约定的同一源码提交，记录 `git rev-parse HEAD`；不要将未提交的源码改动与该提交号混用。在含骨架代码的提交上将 `.env.example` 复制为 `.env`，填写本机私有的 MySQL 库名、应用账号、应用口令、管理口令和 Qdrant 密钥。应用账号使用普通账号，管理口令只供 MySQL 容器使用。应用宿主端口默认 `8000`，如被占用可填写 `APP_HOST_PORT`。Compose 注入容器内地址 `mysql:3306` 和 `http://qdrant:6333`。
2. 确认工作区对应要验证的源码提交，执行 `export APP_BUILD_REVISION=$(git rev-parse HEAD)`，再运行 `docker compose up --build -d`。镜像写入该版本；应用缺少必需配置时在监听前退出。
3. 执行 `curl -fsS http://127.0.0.1:8000/health`，使用自定义端口时替换端口。确认返回版本和 MySQL 状态。仅 Qdrant 不可用时为 200 且 `status=degraded`，MySQL 不可用时为 503。独立的 `/live` 用于确认进程仍可响应。
   `docker compose up` 返回成功或容器显示 healthy 只说明进程启动/存活。依赖初始化期间允许 `/health` 暂为 503，应等待并确认版本匹配且 `status=ready`、两项依赖均为 `ready`；`degraded` 表示向量依赖不可用，不能作为两项依赖均正常的冷启动验收。
4. 执行 `docker compose logs app` 查看单行 JSON 请求标识日志，使用 `docker compose down` 停止当前项目并保留本机卷。

### 成员冷启动记录

任务 3.4 的三名成员须各自在自己的干净克隆上启动全组约定的同一提交。服务就绪后执行以下命令；端口应与本人 `APP_HOST_PORT` 一致，输出文件名可换为成员标识：

```bash
uv run --locked python scripts/verify_runtime.py --port 8000 --output reports/cold-start-member-a.json
```

命令核对干净工作区、运行版本与当前提交一致、MySQL/Qdrant 均就绪、双探针的 GET/HEAD 及请求标识，记录系统与 Docker/Compose 版本。失败非零退出，不生成通过记录或覆盖旧报告；仅请求本机回环探针，不读取环境文件、口令、主机名或完整容器配置。`degraded` 可用于运行降级，但不满足完整冷启动验收。

将生成的脱敏记录连同成员姓名、实际启动命令、遇阻/复测说明和另一成员的实名交叉评审汇总到课程证据。该命令只提供机器检查结果；每人的独立运行、V2 会话和人工评审仍须实际发生。

### 课内回滚复现

1. 从[骨架验证记录](docs/changes/2026-11-04-add-skeleton.md)取得 A/B 的提交和镜像 ID。用 `docker image inspect --format '{{.Id}}' campusclaw-skeleton:<提交>` 核对本机保留的制品。需要重建时，在各自对应的源码提交上设置 `APP_BUILD_REVISION` 并执行 `docker compose build app`，另行登记新制品 ID。
2. 准备 `.env.drill-a` 和 `.env.drill-b`，按冷启动填写合成配置，分别设定 A/B 的 `APP_BUILD_REVISION` 及不同的 `APP_HOST_PORT`，例如 18081 和 18082。在没有同名项目的情况下，分别用 `docker compose -p campusclaw-drill-a --env-file .env.drill-a up --no-build -d` 和 B 对应命令启动，两侧均等待 `/health` 返回 200 且版本匹配。
3. 用只绑定回环地址的代理建立一个固定入口，转发当前侧的 `/health`，仅在该侧就绪时转发 `/live`。先指向 A 并确认版本，再指向已就绪的 B 并确认版本。执行 `docker compose -p campusclaw-drill-b --env-file .env.drill-b stop mysql`，检查固定入口返回 503，直连 B 的 `/live` 仍为 200。确认 A 就绪后将代理指回 A，从同一入口验证 200、A 版本和请求标识，并用 A 的应用日志匹配。记录故障检测、切换、复核及总耗时。
4. 启动 B 的 MySQL，验证 B 可重新就绪。关闭临时代理，使用上面两个项目及各自配置运行 `down --volumes` 回收演练专用容器和卷，保留 A/B 镜像。

## 第 10 课交付与最终人工评测

先完成纳入交付范围的必做功能、场景追溯、双门禁、干净目录启动、CI 制品追溯、观测与通知、对照压测及至少三名真实使用者试用。齐备后冻结候选提交、镜像和配置，由验收人按四项技能、手机四步及跨功能业务场景执行评测，同伴从干净目录独立复现。第 9 课 SEC-08 继续按选做状态登记。查看[第 10 课验收规约](openspec/changes/2026-11-04-define-lesson-10-acceptance/specs/lesson-10-acceptance/spec.md)和[项目业务走查](openspec/changes/2026-11-04-project-final-acceptance/design.md)。

当前处于规约阶段。`make check` 是现有入口，独立 `make check-security` 由课末安全预检建立，第 10 课接入同名 CI 双门禁并对候选交付取证。课程要求的教师改分、作业提交 `202` 和实际登录方式需与批准的上游契约逐项核对。差异未经课程方确认时按缺项记录。实际验收将结论与证据指针写入根目录 `report.md`，报告明细使用 `reports/` 固定路径。查看[证据清单和任务](openspec/changes/2026-11-04-define-lesson-10-acceptance/design.md)。

## 小组协作与增量流程

每组实现以[可运行交接](docs/standards/08-评审与完成定义规范.md#分阶段完成定义)为退出条件。实现人在隔离环境验证启动、就绪和本组关键路径，通过后可继续依赖该能力的开发。完整自动化回归、适用专项验证与代码评审在对应变更的收尾组完成。课程专项复验在各自任务执行，整体验收由第 10 课第 5 组统一调度。

### 规约依赖与验收交接

下表的「实施输入」指实际可启动、契约已明确且对应自动化回归通过的基线，可以是记录了版本的开发候选。合并到受保护主干仍须通过必需门禁并获同伴代码评审。涉及 OpenSpec `MODIFIED` 增量时，归档前还须把上游完整条款同步到主规格并复验，不能用独立开发候选代替归档前置。

| 变更 | 实施输入或验收前置 | 验证与评审归属 |
| --- | --- | --- |
| [工程规范](openspec/changes/establish-project-standards/tasks.md)与[开发骨架](openspec/changes/2026-11-04-add-skeleton/tasks.md) | 工程规则提供约束，骨架提供应用工厂、默认拒绝、就绪与门禁 | 骨架 3.2、4 组及[第 7 课收尾](docs/lesson-07/acceptance.md)承担相应复验、回滚和课程交付 |
| [认证与资料](openspec/changes/2026-11-04-add-class-auth-material-ingest/tasks.md) | 骨架运行基线 | 4.3 完整回归及代码评审。下游复用 Cookie 会话、同源写入防护、当前班级身份、资料版本和撤销 |
| [检索与问答](openspec/changes/2026-11-04-add-traceable-retrieval/tasks.md) | 可运行的认证与资料，重点是原文读取、撤销和班级隔离 | 第 5 组承担冻结题集评测、真实依赖回归及代码评审。归档前要求主规格有 CA-04 |
| [流式助手](openspec/changes/2026-11-04-add-streaming-ai-assistant/tasks.md) | 认证、资料和检索的可运行契约，含有限证据、出处与 QA-01 | 第 5 组完成门禁、AI 评测和四项同伴复验。反馈契约交异步教学看板 |
| [受控 MCP](openspec/changes/2026-11-04-add-controlled-mcp-tools/tasks.md) | 独立服务可先实现，宿主接入依赖助手的技能、SSE 和私有记录 | 第 4 组完成真实 Compose 互操作及同伴复验。人工教学闭环、AI 候选题与安全预检可独立于 MCP |
| [异步教学](openspec/changes/2026-11-04-add-async-teaching-workflows/tasks.md) | 人工建题、测验、规则评分依赖骨架与认证。候选题另需 Kafka、检索证据与固定提示配置。看板未解决数接流式助手反馈。后台索引选做，要求核心闭环自动化验证通过及已同步的 IX-01 | 第 5 组验证闭环和异步三判据，7.4 完成实现交付。课末专项复验由安全预检执行 |
| [课末安全预检](openspec/changes/2026-11-04-add-post-async-security-precheck/tasks.md) | 异步教学 7.4 的可运行候选、5.2 并发与事务证据，以及认证、检索、配置和技能调用 | 本变更执行课程 SEC-01–07 及独立复验，建立 `make check-security`。异步 7.1–7.3 引用同一证据 |
| [安全修复](openspec/changes/2026-11-04-remediate-security-findings/tasks.md) | 安全预检的版本、报告和实际复现结果 | 修复并复测实际发现，复用预检安全入口。选做 SEC-08 单列 |
| [第 10 课交付](openspec/changes/2026-11-04-define-lesson-10-acceptance/tasks.md)与[项目最终验收](openspec/changes/2026-11-04-project-final-acceptance/tasks.md) | 第 10 课 1–4 组完成交付验证，且纳入交付的必做能力和证据齐备后，由 5.1 冻结候选 | 项目最终验收用同一候选执行跨功能卡，结果回到第 10 课 5.2–5.4。正式人工走查只安排一轮，换候选后复验受影响场景 |

课程等价由对应任务记录。第 5 课 Bearer Swagger、第 8 课作业提交 `202` 与评分写入路径、第 10 课教师改分等差异在确认前保留为验收缺项。只暂停依赖未决契约的任务，已明确契约的独立组可以继续。

- 使用 `main` 为主干、`change/<变更名>` 为后续短分支。首次建仓按用户明确指令初始化和推送 `main`；常规后续变更禁止直接推送主干，先自检和评审再合并。历史文档直推按当时的[单次例外](docs/standards/08-评审与完成定义规范.md)执行，不推广到后续变更。GitHub 已确认远程 `main` 启用保护，复测见[骨架证据](docs/changes/2026-11-04-add-skeleton.md)。
- 每次先明确边界，建立 proposal、design、specs、tasks；场景采用“前置条件→操作→可观测结果”。本次纯文档的 `skip_specs: true` 不适用于业务行为变更。
- 在同一仓库提变更→校验→实施→自检→人工评审→归档→按需打标签，不在每课另建一套实现。骨架建成后主干必须持续可启动。
- 后续新变更采用课程约定 `YYYY-MM-DD-短横小写英文名`，例如 `2026-10-28-add-skeleton`；当前 `establish-project-standards` 是已指定且已执行的首个变更，保留原名便于追溯，不追溯重命名。
- 提交说明写清行为与对应规约，不能只有 `update` 或 `fix`。归档时将已验收业务增量合入主规格，下一轮先读既有约定。涉及 `MODIFIED` 的资料与索引条款按「认证与资料 → 检索与索引 → 异步索引」顺序归档，每次以上游已发布条款复验完整增量；纯文档跳过业务规格的原因仍须可查。
- 三名成员分别使用有写权限的账号在短分支提交并发起 PR。每个 PR 由另一名成员评审，提交和 PR 直接用作协作证据，运维动作记录实际执行者。评审一个工作日内响应，超期交组内协调。
- 业务实现按任务清单逐组交付。跨变更整理规约时说明涉及范围；规约、测试、README、页面清单及必要数据字典随改动同步。变更证据见 `docs/changes/<变更名>.md`，本课交付汇总到 [docs/lesson-07/](docs/lesson-07/README.md)；批准和发布是独立事实。
- 编码前确认主干保护已启用。首份代码合并前复核真实直推拒绝并将 CI 的 `make check` 设为必需。课程任课教师直接查看公开仓库内容，无需邀请或单独访问确认；三名成员按 README 独立冷启动的记录在课程交付前补齐。

## 许可状态

**未选择项目开源许可，未创建 LICENSE。** 原因：小组尚未决定公开复用范围和第三方素材授权边界。由组长在首次公开发布前组织确认并同步 README/许可证文件；依赖许可准入不能替代本项目许可选择。

完成判定与受保护文件范围以[评审规范](docs/standards/08-评审与完成定义规范.md)为准；不得删断言、弱化门禁或跳过已有钩子换取通过。

## 机密泄露处置

运维责任人执行轮换，实施人定位影响，评审人核对闭环。发现后立即停止继续传播，并：

1. 撤销泄露凭据和相关会话；记录受影响系统与时间，不复制秘密原值到证据。
2. 在提供方生成新凭据，通过私有环境注入；同时检查所有环境和受控工具配置。
3. 用新凭据重新部署受影响服务，验证旧凭据失效、新凭据可用且日志/响应无泄露。
4. 在已有仓库历史、镜像层、报告与备份中排查副本，按权限协调清理；删除文件不替代撤销和轮换。
5. 将脱敏后的原因、处置人、验证和防再发措施归档到变更记录，提交人工复核。

目前运行记录来自本机及 CI 隔离验证，发布环境按实际授权建立。
