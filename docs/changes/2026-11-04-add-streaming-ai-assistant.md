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

## 2026-11-07–08 第 1 组：上游复核与存储基础（实施中）

### 变更说明

用户调用 `openspec-apply-change` 实施流式助手。本轮按逐组交付落实第 1 组，基线 `c17adde4babc07bc6805994806597667e06700d0`，分支 `change/2026-11-07-streaming-assistant-storage`。保留上一轮未提交的 `2026-11-07-sync-code-status.md`，不混入功能实现或假称该文档已提交。未执行推送、合并、发布或真人验收。

实际读取 CLI `contextFiles` 中 proposal、design、四份 specs 和 tasks，schema 为 spec-driven，初始 0/13、ready；没有额外 context/operationGuidance。CLI 规划工件 complete 不作为功能完成依据。读取 AGENTS、README、后端/安全/测试/数据/运维/AI/评审规范、现有数据字典及迁移、认证/检索 API 和真实依赖脚本。未使用另一仓库证据。

### 验证记录

- 编码前通过 GitHub 只读 `branches/main` 接口核对主干提交为 `c17adde`、`protected=true`，必需状态包含 `make check`，未修改保护。
- `OPENSPEC_TELEMETRY=0 openspec status --change 2026-11-04-add-streaming-ai-assistant --json`、`openspec instructions apply --change 2026-11-04-add-streaming-ai-assistant --json`、`openspec validate 2026-11-04-add-streaming-ai-assistant --strict`：退出 0。
- 基线 `UV_CACHE_DIR=/private/tmp/campusclaw-status-uv-cache uv run --locked python scripts/check_pytest.py -q --disable-socket tests/api/test_class_auth_material.py tests/api/test_access.py tests/api/test_answers.py tests/api/test_retrieval.py`：退出 0，52 项通过，0.24 秒。
- 修改前 `UV_CACHE_DIR=/private/tmp/campusclaw-status-uv-cache make check-integration`：在授权 Docker 环境退出 0，1 项真实 Compose 集成通过，132.48 秒，日志 `/private/tmp/campusclaw-streaming-baseline.log`。随机专用项目及 `campusclaw_test_` 合成库，完成双探针就绪、认证/同源防护/当前角色、资料字节与删除、章节与索引、三模式与无证据零对话调用、模型故障、依赖停启及排空，夹具回收专用容器/网络/卷和镜像。

核对结论：当前身份来自数据库会话联查，写入先校验同源与规定请求头，角色/班级不由客户端赋权；跨班/缺失同构。资料有原文版本及删除清单，检索先限定范围并返回版本化出处；原 `POST /api/v1/material-answers` 无持久会话副作用。CA-04 主规格同步仍是归档前置，课程 Bearer 等价及人工验收不作为本组技术开工前置。任务 1.1 的直接上游复核完成；持久功能接入时继续验证自身新增副作用与兼容。

### 评审结论（阶段）

实际使用 `openspec-apply-change` 读取工件并推进第 1 组；`project-data-change` 输入为新配置/私人记录/来源副本，先登记字典再编写只增迁移和隔离测试；`project-add-tests` 读取场景和既有套件、复验基线并补充约束与恢复断言；`project-review` 对照真实命令及任务状态，不代填人工批准。1.2 的结构、迁移及恢复验证在进行，尚未完成时不勾选；未启用新持久 API 或模型路径，未运行新提示词评测。

### 第 1 组实现结果（2026-11-08）

新增冻结结构 `assistant_schema_v8.py` 和追加迁移 `0008_assistant_storage`：15 张新表涵盖班级配置及不可变修订、同班材料/技能绑定、本人会话、逻辑操作、最多三次执行尝试、成功消息、历史出处、反馈和去内容审计。新增账号组合索引及私人归属组合外键；大小写敏感幂等键、同会话仅一条在途操作、一轮一个用户/助手消息与一个成功执行分别由唯一约束保护。成功执行去内容化为 revoked 后仍保留唯一成功占位。数据库不替代后续服务的权限、版本 CAS、JSON 白名单、条件提交和公开响应校验。

按 DATA-05 先登记字典再编码；本组新表未提供业务写入口，只在随机合成库放入夹具。`assistant_copies.py` 接入既有资料删除事务，按已登记出处清空私人输入、用户/助手消息正文、执行步骤结果、所有相关出处摘录及反馈说明，保持安全状态；删除章节会解除反馈的章节引用，不阻碍原有删章归未分类。原文删除清单重放复用同一事务原语，不新增另一套副本清理协议。章节、资料路由及原单次问答的公开契约未修改。

| 检查 | 实际结果 |
| --- | --- |
| 初次存储集成 | `make check-integration` 退出 2，12.81 秒；既有空库/全量降级回归发现 MySQL 1553：新增 `(class_id,id)` 索引替代原自动外键索引，降级时不能直接删除。修复 0008 降级，在删组合索引前补回 `accounts.class_id` 支撑索引；未改历史迁移或删断言。日志 `/private/tmp/campusclaw-streaming-storage-integration.log` |
| 第二次存储集成 | 退出 2，20.80 秒；外键负例同时命中已有 `(operation_id,role)` 唯一键，数据库先返回 1062 而非待验证的 1452。调整夹具顺序，在合法消息写入前单独验证偷换 owner，保留其后重复用户/助手消息断言，未允许错误码混用。日志 `/private/tmp/campusclaw-streaming-storage-integration-2.log` |
| 第三次存储集成 | 退出 0，1 项真实 Compose 集成通过，35.24 秒；新脚本和全部既有脚本共同执行，夹具 finally 回收专用容器/卷/网络/镜像。日志 `/private/tmp/campusclaw-streaming-storage-integration-3.log` |
| 独立测试回归 | `UV_CACHE_DIR=/private/tmp/campusclaw-status-uv-cache make check-test` 在授权回环环境退出 0，254 项断网单元/API 2.06 秒、4 项进程 2.25 秒。日志 `/private/tmp/campusclaw-streaming-storage-tests.log` |
| 完整门禁 | `UV_CACHE_DIR=/private/tmp/campusclaw-status-uv-cache OPENSPEC_TELEMETRY=0 make check CHANGE=2026-11-04-add-streaming-ai-assistant` 退出 0；12 项严格规约、106 文件格式/Ruff、分层与场景追溯、254 单元/API、4 进程及 1 项真实 Compose 集成（35.69 秒）通过；Gitleaks、锁依赖和集成应用镜像 HIGH/CRITICAL 扫描通过。日志 `/private/tmp/campusclaw-streaming-storage-make-check.log` |

`assistant_storage_runtime.py` 由 `verify_assistant_storage` 接入原 `make check-integration`，覆盖：

- 既有空库升级、已填充 0007 库升级；模拟 MySQL DDL 中途已提交但版本未前进，保留已建表后重跑并再次迁移；核对旧账号、资料和字节不变。
- 同班创建人、配置修订、材料/技能绑定、会话本人、操作与消息归属组合外键；重复修订/规范名；无租约、尝试第4次、错误作用域和不合法出处坐标等 CHECK 反例。
- 真实两连接同键竞争恰好一条受理；不同键同会话在途被拒；成功释放在途槽位且键大小写独立；重复用户消息、重复成功助手消息和第二个成功执行均被拒；失败执行不得存未校验 details，成功记录 revoked 后不能再写成功结果。
- 新表夹具的出处包含补充字符；通过真实受保护资料 API 删除，确认消息、操作输入、执行结果、快照与反馈说明共同去内容化。中途注入数据库故障验证全部回滚，原文字节及私人副本均保持原值。源码审查另发现多来源清理不能把既有 deleted 降为 revoked，使用保留 deleted 的条件表达式，并补两来源删除及重复重放不抬高修订断言后纳入完整门禁。
- 将保存的合成数据库行隔离还原，在接流量前重放独立删除凭证两次，确认原文与相关副本不复活；这不是生产物理备份恢复。单步降到 0007、旧字段和字节核对、重升为空扩展表均通过；先前全量降到 base 的回归保留。

场景追溯为 AP-B01、ST-F06、FB-B01、FB-F04 的**数据库前置断言**，不是这些场景的完整 API/SSE/历史读取实现；四项新能力仍在 `tests/scenario-map.json` 的 planned 区，待对应业务组完成后逐场景切换。没有借局部数据测试宣称能力已交付。

### Harness 七类自审

| 类别 | 手段、对象、判据与结果 |
| --- | --- |
| 接口入口 | 核对未注册新路由，使用原有同源认证及资料删除 API 验证清理副作用；既有匿名/学生/跨班断言通过。新应用接口不适用，尚未启用。 |
| 业务逻辑 | 核对逻辑轮次/尝试分离、三次上限、唯一成功及失效状态；真实竞争与重复键断言通过。完整流式状态机、反馈处理和教学意图保留后续组。 |
| 数据库 | 核对同班/本人组合外键、生成列唯一键、迁移顺序及索引回退；空库/旧库/DDL中断重跑/物理回退/字节保真通过。事务故障回滚及隔离旧行重放通过；生产备份演练未执行。 |
| 公共函数 | 清理原语位于适配器、复用既有 remove/replay_deletions 事务；Ruff/分层与254单元/API通过，无新增依赖或模型行为。 |
| 错误处理 | 新清理 SQL 故障仍由既有服务映射503，无成功删除或半笔数据；原依赖故障及启动回归通过。迁移失败非零，未吞错误。 |
| 安全 | 新表无公开读写路径，合成数据验证归属链；源码仅存去密钥元信息，副本失效清空内容；秘密/依赖/镜像门禁通过。独立攻击矩阵及故意移除授权测试归安全预检，本轮未执行。 |
| 性能 | 核对副本按来源索引定位、每次至多100条消息关联批处理，无外部I/O或模型占用事务。总删除事务耗时随关联数量增加，千条/并发10压测和SSE满额短请求预算未执行，不宣称性能验收通过。 |

### 第 1 组交接结论

1.1、1.2 的上游复核、数据字典/结构、归属与唯一约束、隔离迁移和回退、故障回滚及恢复重放已验证，整体 **2/13**。配置键沿用 `MYSQL_*`、`QDRANT_*`、`APP_PUBLIC_ORIGIN` 和构建标识；新表结构无新增运行开关或模型配置。集成镜像标签由随机夹具生成，内容包含未提交源码，不冒充不可变提交制品。

本轮先交付第1组，未进入第2组业务编排。下一组为最小 SSE、应用和技能；新增持久入口仍须实现当前身份、逐次授权、引用/输出验证及到期治理后启用。新存储路径的真人测试、课程口径和实名清理责任按最终验收/上线安排保留；本轮未新增 AI 提示或模型行为，`project-prompt-eval` 不适用。未修改产品页面，浏览器新页面回归不适用；已通过既有接口与真实依赖自动化回归。

按已有逐组安排，本轮为可运行存储交接；人工代码评审、约束文件复核、提交/合并及上线均未发生。应用制品回退保留扩展表，并暂停涉及本课副本协议的资料删除、章节删除和新增私人写入，恢复新制品后先重放独立删除清单及到期清理再开放新路径。具体学期日期/实名责任仍是生产启用前置，本轮不伪填。

## 2026-11-08 Task 2.0：最小 SSE 与容量验证

### 变更说明

用户要求继续推进。本轮继续使用 `openspec-apply-change`，读取磁盘AGENTS、README、proposal/design/四份specs/tasks，CLI为spec-driven、2/13、ready，无额外context或operationGuidance；本轮范围为第2组的最小通路2.0，保留上一组未提交改动，未改动0008结构或既有迁移。基线提交仍为`c17adde`，工作区包含已验证但未提交的第1组，不能将当前源码或测试镜像冒充该提交的不可变制品。编码前GitHub只读接口复核main受保护，必需状态仍有make check。

新增 `app/services/streaming.py`、`app/api/streaming.py`，应用工厂装配单实例长请求容量，未注册新业务路由。容量4、现有单worker/8线程，预留至少4个WSGI线程供普通请求。首次生产者启动前及每次出流前重验，原始结构只在服务端1项有界队列交接，调用方校验后的段落才进delta；组合校验和commit回调成功才发done。取消、排空和35秒期限触发安全终态并尽力中断上游，生产者未退出前继续占槽。0.25秒无内容心跳支持及时发现连接断开。后续同步AI应用必须复用此容量，不能自行新建实例绕开限制。

NGINX显式`proxy_buffering off`、`proxy_cache off`、`proxy_ignore_client_abort off`，保留原连接/读写超时与不重试策略。行为依据为[NGINX官方代理说明](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_buffering)和[Flask官方流式说明](https://flask.palletsprojects.com/en/stable/patterns/streaming/)；流中不访问已结束的Flask request/g，所需身份和请求标识在响应前捕获。

### 验证记录

- 起步 `make check-static` 退出0，12项严格规约、106文件格式/Ruff、分层和场景追溯通过；受影响认证/权限/单次问答回归41项通过0.16秒。上一组完整真实依赖证据继续保留，本轮完整真实套件包含第1组回归。
- 新增19项断网单元测试，覆盖段先出/提交后done、错误数量/引用、空或非法UTF-8/NUL/超预算输出、最多8段、上游/提交故障安全错误、组合校验、开始前和段间撤权、未启动close、取消回调幂等、非协作生产者未退出时继续占槽、超时、排空、10线程竞争恰好4条受理及启动线程失败不漏槽；最后独立执行19项通过0.02秒。
- `UV_CACHE_DIR=/private/tmp/campusclaw-status-uv-cache uv run --locked python scripts/check_pytest.py -q --disable-socket tests/unit tests/api` 退出0，273项通过2.07秒。
- 首次 `make check-integration` 退出2，49.14秒，临时慢上游进程缺少模块搜索路径，9090拒绝连接。为夹具补`PYTHONPATH=/srv/campusclaw`，未改生产模块路径或断言。日志`/private/tmp/campusclaw-minimal-sse-integration.log`。
- 第二次退出2，37.81秒；增量、取消与错误第二段已通过，混合并发探针的负载得到非200。第三次保留原断言补安全诊断，退出2，38.39秒，定位`/health`在13.74毫秒返回503/not_ready。骨架现有每依赖两个探测槽，夹具同时压三个health请求混入了探测自身的容量边界；未把该503算通过。日志`...integration-2.log`与`...integration-3.log`。
- 修正负载夹具，将10并发用于普通资料读取，双探针在同一负载中逐次200和1000毫秒硬预算断言保持；未修改HealthService、既有门禁、槽位或阈值。第四次 `UV_CACHE_DIR=/private/tmp/campusclaw-status-uv-cache make check-integration` 退出0，1项真实Compose集成通过39.37秒，日志`/private/tmp/campusclaw-minimal-sse-integration-4.log`。

真实代理由 `verify_streaming_proxy` 接入原真实集成套件，沿用随机专用Compose项目、真实MySQL/Qdrant和固定NGINX镜像。临时TLS证书仅有效1天、客户端校验该CA，不关闭证书验证；网关非root/只读/cap_drop ALL，只有HTTPS随机回环端口。受控HTTP上游和测试Flask路由只在容器/tmp，`Dockerfile`仍只COPY app，不引入测试路由、控制口或测试开关到产品镜像。测试后停止额外进程、移除NGINX，原夹具继续回收容器/网络/卷并检查无残留。

| 真实代理断言 | 结果 |
| --- | --- |
| 同源/认证 | 匿名401、有效Cookie缺写头403，均无SSE或上游请求；五个独立合成学生持各自Cookie |
| 实际增量 | 3轮均先meta、合法第一段delta；断言慢上游仍active且未完成，再主动放行第二段，随后delta、唯一done；done的正文等于两段拼接，提交回调已发生 |
| 取消与错误 | 客户端断开后上游socket实际中止、active归零，已取消轮次无成功；第二段25伏不匹配24伏证据，error1501且无done，错误段不公开 |
| 满额 | 4条不同账号长流保持暂停，第5条429/1600且不访问上游；普通资料为1000条、10并发50样本，最大35.46ms、P95 23.96ms；同时探针`/live`、`/health`各5次，均200，最大20.63/29.05ms |
| 排空 | 标记排空后/live仍200、/health503，四长流分别error1500且无done，上游及槽位回收；清除仅测试使用的marker后容量恢复 |

原始脱敏报告`reports/2026-11-04-add-streaming-ai-assistant/minimal-sse.json`，本轮首次成功测试首段耗时3样本约28.39–32.06ms、总耗时238.01–245.11ms；总耗时包含测试控制命令开销。普通读取及探针合计60样本，P95 26.26ms。这是本机Docker及明确HTTP模型替身结果，非课程真实模型性能或正式全功能性能验收，完整门禁重跑会另记新数值。旧`/health`并发槽位边界仍保留，不据此声称可无界并发探测。

### Harness 七类自审与交接边界

| 类别 | 手段、对象、判据与结果 |
| --- | --- |
| 接口入口 | 组件未注册生产新路由；真实代理夹具复用当前Cookie/写头检查，匿名/缺头零上游请求；新持久API仍未实现 |
| 业务逻辑 | 核对meta/delta/单一终态、校验/重验/提交顺序、取消和租约外的传输期限；单元与真实暂停上游验证通过；持久幂等及完整来源授权仍交3组 |
| 数据库 | 本轮未改schema和持久服务；真实读取1000条合成资料通过，上一组迁移/清理回归继续执行；流工作线程中无长事务 |
| 公共函数 | 单实例容量、幂等release、有界队列、取消回调和未退出继续占槽；19项单元、分层和已有回归通过，未新增依赖 |
| 错误处理 | 无效数量/引用等不进delta，流内错误唯一error、无done，不传播上游错误正文；线程启动/提交故障、期限和排空有回归 |
| 安全 | 无测试路由进入产品镜像，不修改当前身份及默认拒绝；新组件要求调用方注入授权重验，不能当作本身已实现ST-F03；专项攻击矩阵由安全预检执行 |
| 性能 | 相同固定代理、TLS和1worker/8threads，长流4满额时普通读10并发50样本及探针响应均满足1000ms硬档；取消和排空实际回收；课程模型、技能多步骤和测验提交仍待对应功能接入及最终候选复验 |

实际使用 `openspec-apply-change` 输入当前变更2.0、读工件并按实际结果勾选；`project-add-tests` 输入ST-01传输前置和容量风险，新增单元与真实代理测试、保留失败及复测；`project-review` 读取安全/后端/测试/运维/AI/评审规范及源码和真实报告，核对七类自审和任务边界。未改变模型、提示词或技能选择，AI效果评测不适用；未改数据结构，数据变更技能不重复调用；无新页面，浏览器交互回归不适用。本轮不代填独立会话、真人评审或课程批准。

Task2.0完成，进度3/13；2.1应用/模板/助手绑定、2.2技能和后续持久会话仍待实施，不能把传输夹具的提交回调当作真实消息事务，四类能力仍保留planned场景。当前分支保留所有未提交增量，未提交、推送、合并、发布或归档。

收尾完整门禁：`UV_CACHE_DIR=/private/tmp/campusclaw-status-uv-cache OPENSPEC_TELEMETRY=0 make check CHANGE=2026-11-04-add-streaming-ai-assistant` 退出0，12项严格规约、111文件格式/Ruff、分层/场景追溯、Gitleaks、锁依赖及应用镜像扫描通过；273单元/API 2.03秒、4进程2.24秒、1真实Compose集成39.68秒，日志`/private/tmp/campusclaw-minimal-sse-make-check.log`。本轮最终重跑报告替换前次同口径样本：60次普通读及探针中位数21.155ms/P95 33.37ms，资料读取最大37.98ms；首段3样本28.53–31.72ms，总耗时210.09–243.36ms，仍全部满足本组断言。首轮成功值作为历史复测保留，不混合样本。应用与代理源码清单保存在忽略目录`source-manifest.json`，清单SHA-256为`319bd2b1c2c1045b823ee8589b39df505c484732f836d0a0cf971807983c5bc2`，只是工作区内容摘要，不是Git提交。所有新代码的技术交付证据可用于后续2.1，代码及约束文件仍待实际同伴复核。

## 2026-11-08 Task 2.1：应用目录、班级配置与同步执行

### 变更说明

用户继续授权推进。本轮仍使用 `openspec-apply-change`，读取磁盘AGENTS、README、proposal/design/四份specs/tasks，CLI为spec-driven、3/13、ready，无额外context/operationGuidance。保留此前存储及最小SSE未提交改动，在同一开发分支实施Task2.1，没有顺带实现2.2技能管理、持久会话或反馈。主干保护经只读GitHub接口复核为启用、必需`make check`；基线仍为`c17adde`加已留证的工作区增量，未提交源码不冒充该提交内容。

新增 `AIRepository`、`AIApplicationService`、`ai_contracts` 和API装配：四项目录、模板创建/修改/停用/逻辑删除、变量预览、助手修订与同班材料/技能绑定，三种同步执行和本人运行记录。页面复用原materials模板、视觉令牌、导航、CSP nonce及纯文本组件，增加 `/apps`、`/runs`、`/runs/{id}`、`/console/templates`，在工作台增加助手配置。列表具加载/正常/空/错误与重试、稳定分页；应用内模板按app_key筛选分页，教师执行页也只展示启用模板。记录页显示中文状态、原模板修订、模型参数、输入/预览及结果，不直接铺出内部JSON标识。

用 `project-data-change` 先登记数据字典和接口细化，再追加0009：模板deleted事实与24小时配置创建幂等，保留0008及旧迁移不变；助手/模板版本和绑定同事务更新，旧修订409不能覆盖。同步执行复用0008逻辑操作/尝试，SQL只短事务受理/最终提交；模型在事务外，共用长请求4、账号连接锁并发1、每实际调用6/min及35秒总预算。成功只存校验后的text/渲染模板，失败清空input/details，保留固定诊断；在途/异输入409，确认失败后同键至多3次。已提交结果先按当前授权回放，不依赖当前模型或已删除模板，不再调网关；普通重放200，新执行201。

`AI_DATA_EXPIRES_AT`由统一Settings读取显式UTC值，缺失/过期时不启用新的私人执行，配置/预览仍可用。不得猜测真实学期或实名清理责任。记录与重放按原到期过滤，`python -m app.ai_admin cleanup`按100个操作一批清理，恢复旧行也不延长期限。正式学期及责任登记仍是生产启用前置；测试只用随机隔离库与合成账号。本组没有新增Qdrant/文件/缓存正文副本。

### 实际验证记录

| 命令/入口 | 实际结果 |
| --- | --- |
| 修改前 `make check-static` 及受影响单元/API回归 | 退出0，12规约、111文件格式/Ruff/分层/场景映射通过；认证/权限/单次问答/最小流60项通过 |
| 新接口及确定性单元测试 | 初版37项通过0.13秒；补UTC配置反例后40项通过0.13秒。匿名/学生配置写入/跨源、未知字段/重复JSON键不进入服务；表达式/变量/渲染上限及模型畸形输出有独立断言 |
| `make check-integration` 初次 | 退出0，1项45.89秒；0009升级、接口/模型替身/本人隔离和已有全部真实依赖脚本通过。前置Ruff报告紧凑测试初稿多语句格式问题，随后format处理、Ruff复验通过，没有修改规则或删断言 |
| 补强后的 `make check-integration` | 退出0，1项43.60秒；补实际三次尝试上限、账号6/min、第7次零模型调用、提交SQL中断回滚与重试、缺期限零副作用和停模型时成功回放。日志 `/private/tmp/campusclaw-ai-apps-integration-final.log` |
| 完整 `make check CHANGE=2026-11-04-add-streaming-ai-assistant` | `UV_CACHE_DIR=/private/tmp/campusclaw-status-uv-cache OPENSPEC_TELEMETRY=0`，退出0；12项严格规约、123文件格式/Ruff、分层/场景映射、秘密扫描、锁依赖及应用镜像扫描通过；313项单元/API 2.29秒、4项进程2.33秒、1项真实Compose集成42.70秒。日志 `/private/tmp/campusclaw-ai-apps-make-check.log`。本轮配额测试按既有隔离方法固定数据库窗口，避免测试跨自然分钟而不改生产窗口规则 |
| 自动化浏览器 | 设置真实Chrome路径，运行 `uv run --locked python scripts/check_pytest.py -q --tb=short tests/browser`，模型为明确 `synthetic-browser-chat`；初版1项18.97秒、可读记录页复测18.57秒、模板分页复测19.11秒通过。末次启用模板过滤为只影响页面的收尾增量，另以同命令复测并保留最后日志；不把早期截图当作新界面已验证 |
| 固定工程与真实网关 | `python -m scripts.evaluate_ai_apps`及显式`--real`均经uv locked执行退出0。20个固定结构/拒绝样本通过，3个真实合成模型请求通过；模型版本、限制、耗时和非语义结论见[专项评测](../eval/2026-11-08-class-apps.md) |

`ai_apps_runtime.py` 由原Compose测试的 `verify_ai_apps` 执行，断言包括：

- 0009单步降到0008后，模拟deleted列已提交但版本未前进，再升级和重跑；新表存在且原数据兼容。既有空库升级、全量降级、迁移回退及原文字节回归继续通过，未改已执行迁移。
- 四类目录仅含本班摘要；同键创建不多写父表、修订或审计；外班/缺失模板与绑定同构404，学生直接修改403；非法模板和变量无配置/模型/执行副作用。原文绑定及受限技能夹具只验证同班引用，不当作技能管理功能已实现。
- 模板预览零模型调用、零操作/记录写入，运行实际user JSON中的rendered_prompt与预览一致；变量中的另一变量字样不二次展开，系统政策不含学生变量。
- 助手清空提示词后使用默认角色、修订递增；旧修订409且材料/技能绑定不被覆盖；历史修订保留。
- 三类同步执行的真实MySQL记录、当前模板修订和实际模型输入；同键重放无额外模型调用/写入，异输入冲突；同班另一学生、教师和外班账号列表不见本人行，详情与不存在404同构。
- 网关超时503、畸形输出502无成功正文；同键失败后复用操作并在第2次成功，第4次尝试被拒；实际MySQL模型锁和共享配额生效。暂停模型时并发同键409，更新模板后原在途执行409且无成功记录。
- 模板仓储故障零模型调用；成功提交SQL中断使事务回滚，失败确认后重试仅一条成功；逻辑删除保留旧修订且不能再读取/启用。已提交回放不依赖当前模型配置。
- 到期后列表/详情隐藏，批清理后隔离还原过期行仍不可读，再清理幂等；这是合成旧行恢复，不称为生产备份演练。

`class-ai-apps`的AP-N01、AP-B01、AP-F01–F04已逐项从planned切为真实pytest/Compose断言映射，场景校验器未修改。其他三项能力仍planned。浏览器保留原章节、索引、检索、问答用例，另走教师键盘建模板/助手→预览→真实同步API及MySQL持久化（仅模型替身）→本人记录、两档宽度、目录503后键盘重试。已目视检查390宽应用和1440宽记录截图；末次截图位于 `reports/2026-11-04-add-traceable-retrieval/browser/`，有单独`ai-app-result.json`。浏览器和真实网关证据分开，未将CDP夹具或替身称作真实模型结果。

### Harness 七类自审与技能记录

| 类别 | 手段、对象、判据与结果 |
| --- | --- |
| 接口入口 | 核对AI_POLICIES逐方法登记、同源Cookie与写头先行、字段白名单和分页；匿名/学生/跨源/外班配对及错误码/副作用通过；没有增加匿名业务例外 |
| 业务逻辑 | 核对不可变模板修订、助手绑定、预览零调用、三应用政策、幂等尝试/成功回放；接口、真实并发及SQL中断回归通过。技能执行和持久会话未实现，不混称完成 |
| 数据库 | 核对0009追加、同班外键、逻辑删除事实、创建键、操作/成功唯一约束、到期过滤与有界清理；真实空/旧库/重跑/回退、并发、回滚及到期旧行重放通过。上线实名责任与生产恢复演练未执行 |
| 公共函数 | 预览/运行共用单次变量替换，响应复用success，容量/配额/ModelGate复用已有实现；分层/Ruff及313单元/API通过，无新增包依赖 |
| 错误处理 | 未知字段/表达式400，权限403与资源隐藏404，旧版本/在途409，模型故障503与畸形502分开；失败正文不可回读，事务失败非成功；页面有请求标识、重试及清晰状态 |
| 安全 | 当前数据库身份、班级及本人SQL范围，配置写入再次锁身份；模板/变量为user数据，模型没有资料/答案/工具入口，浏览器用textContent，不写Web Storage或秘密日志；既有秘密/依赖/镜像门禁通过，专项攻击审计仍由安全变更执行 |
| 性能 | 同步生成35秒/单调用15秒/账号并发1/6次/分钟，容量4；重放与预览零模型，列表20/100分页、绑定最多各100，渲染12000上限。真实3个单样本时延均在35秒内，不能宣称P95或最终性能验收；SSE满额短请求既有回归保留通过 |

实际调用技能：`openspec-apply-change`输入本变更2.1、读取CLI工件并按证据推进；`project-add-tests`读取场景和测试/安全规范，新增单元/API/真实MySQL/浏览器断言与场景映射；`project-data-change`读取字典、0008/0009和数据/后端/安全/运维规则，先登记副本/期限，再验证迁移、删除事实及过期旧行恢复；`project-prompt-eval`读取AI规则、现有适配器及QA基线，为首次同步应用固化`class-apps-v1`、20个工程样本和3个真实烟测，不编造旧应用前测；`project-review`读取以上工件与七类自审、实际日志、页面/字典/README，区分替身、真实网关、人工未执行与合并批准。

任务2.1的实现及适用自动化可交付，末次页面回归通过后已勾选，整体进度4/13；2.2技能选择/执行、持久会话、快照和反馈继续待实施。本轮没有提交、推送、合并、归档、生产部署、独立会话或真人验收，约束文件及代码仍待实际同伴复核，不自填批准。


收尾复核：当前页面过滤增量的浏览器复测退出0，1项18.49秒，日志`/private/tmp/campusclaw-ai-apps-browser-delivery.log`；完整门禁之后只改了执行页隐藏停用模板的布尔过滤及交付文档，末次适用静态检查与秘密扫描再次退出0（日志`...ai-apps-final-static.log`、`...ai-apps-final-secrets.log`），`git diff --check`及本地文档链接核对通过。CLI apply复核4/13、ready。配置创建重放返回同一对象的当前修订，不追加审计或配置；独立运行成功重放返回保存的原成功记录。源码改动均未提交，保留早前失败/成功日志，不自填人工批准。

本组应用/代理/Compose源码清单保存在忽略目录`apps-source-manifest.json`，SHA-256为`358ef230830dae99fb198459cf548b7c1859289b76d60d6e92a2f1a61b425870`，用于识别未提交工作区内容，不当作Git提交或发布制品。

## 2026-11-08 续做2.2：技能管理与执行组件（尚未整项交付）

### 变更说明

基线 `c17adde4babc07bc6805994806597667e06700d0`，沿用 `change/2026-11-07-streaming-assistant-storage` 的已有未提交候选；本轮未提交、推送或合并。编码前通过GitHub连接读取远程main分支，确认 `protected: true`，必需检查含 `make check`。本机无 `gh`，改用连接器读取；未修改保护。

本轮只推进第2组的2.2：新增 `app/services/skills.py`、`app/adapters/skill_repository.py`、`app/api/skills.py` 及技能页面，复用现有0008表和统一Cookie/Origin/请求头防护。教师显式添加内置解题引导和学习计划拆解，上传技能支持创建、修改、启停、删除；审计与修订同事务。班级锁与唯一键防止重复定义，外班与缺失资源同为404/1300。模型槽位、选路和步骤执行组件尚未接入会话宿主，没有学生持久技能执行入口。

实现细节及课件字段映射见design末段。README、页面清单、字典和场景清单已同步，原因是登记新增管理入口与真实部分交付状态；没有修改规则判据、门禁或既有断言。上述约束文件修改待人工复核。

### 验证记录

全部数据为独立 `campusclaw_test_` 库中的合成A/B班，非生产数据。Compose测试使用独立项目并自动回收容器与卷，模型为显式替身。宿主uv缓存不可写，以下uv命令均设 `UV_CACHE_DIR=/private/tmp/campusclaw-uv-cache`，不改依赖锁。

| 实际命令 | 退出码与观察 |
| --- | --- |
| `openspec validate 2026-11-04-add-streaming-ai-assistant --strict` | 0，业务规约严格校验通过 |
| `uv run --locked pytest -q --disable-socket tests/unit tests/api` | 最终0，343项通过；其中新增技能30项 |
| `uv run --locked pytest -q --tb=short tests/integration/test_compose.py` | 0，1项46.06秒；真实MySQL的技能创建、修订、同名拒绝、内置启停/只读、删除、班级隔离通过；包含原有认证/检索/迁移回归 |
| `CAMPUSCLAW_CHROMIUM='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' uv run --locked pytest -q --tb=short tests/browser` | 0，1项19.52秒；真实后端页面键盘保存与停用技能、390/1440宽度无横向溢出；原有主路径保持通过 |
| `uv run --locked python -m scripts.evaluate_skills` | 0，10条合法槽位与10条非法槽位全部符合判据 |
| `uv run --locked python -m scripts.evaluate_ai_apps` | 0，上游同步应用固定工程20条通过 |
| `make check CHANGE=2026-11-04-add-streaming-ai-assistant` | 0，规约12/12，静态/分层/场景追溯，343项单元/API，4项启动，Gitleaks、Trivy依赖与候选镜像扫描，真实依赖集成1项43.52秒均通过；本次集成含新增绑定交集/停用断言 |
| `make check-static CHANGE=2026-11-04-add-streaming-ai-assistant` | 0，文档与场景清单同步后复核通过 |
| `node --check < app/templates/_skills_script.html`、`node --check tests/browser/chapters.mjs`、`git diff --check` | 0，脚本语法与差异空白检查通过 |

失败与修复：首次uv命令因默认缓存目录权限失败（退出2），改为独立临时缓存后运行；初次直接访问Docker socket被沙箱拒绝，获得工具提权后执行独立测试。首次ruff发现导入顺序/重复夹具名，已修复。夹具复用调整时发生343项中7项setup错误（336通过，退出1），原因是别名夹具被未使用导入修复移除；改为显式pytest插件复用后343项及完整门禁复测通过。保留这些失败说明，不把当时结果列为通过。

原始日志、固定评测和两档截图放 `reports/2026-11-04-add-streaming-ai-assistant/skills-*`；浏览器原始综合结果同时位于 `reports/2026-11-04-add-traceable-retrieval/browser/`。本轮未调用真实课程模型，未做教学效果人工判定；不能用槽位校验20条替代任务5.2或真实网关实验。

### 场景与副作用追溯

| 场景 | 已执行对象与判据 | 剩余 |
| --- | --- | --- |
| SK-N01 | 单元替身按顺序执行两步，第二步输入只含第一步校验后的提示，上传文字在user JSON数据位置；真实API保存定义修订 | 私人执行记录、教师不可读及完整会话路径待3.1/3.2 |
| SK-B01 | Unicode归一、条件去重得分、同分稳定ID、零分不选；真实SQL限定当前班级/助手修订/绑定/启用，停用立即排除 | 既有会话下一轮回读待接入 |
| SK-B02 | 无证据解题仅审核通用步骤及无依据标识、空出处；无证据资料问答固定文案且零模型调用 | 会话公开帧与回读待接入 |
| SK-F01 | 非法字段、类型、脚本/URL、工具、步数、条件、重复键和8 KiB边界单元/API；真实MySQL同名请求400无新增 | 已有组件检查通过 |
| SK-F02/F03 | 匿名401、学生所有管理入口403且零业务服务调用；真实外班与缺失404/1300，原AP绑定回归仍通过 | 管理场景通过 |
| SK-F04/F05 | 第二步失败后第三步零调用，无部分成功返回；拒绝自由答案/非法槽位/附加字段，不可信步骤不提升至系统指令 | 私人脱敏诊断、成功消息与原始SSE反例待宿主接入 |

### Harness七类自审与评审结论

| 类别 | 手段、对象与判据 | 结果和证据 |
| --- | --- | --- |
| 接口入口 | 核对skills路由和策略、白名单、同源及统一错误；pytest访问各管理方法 | 通过管理组件检查，API与Compose记录 |
| 业务逻辑 | 核对修订、只读内置、选路、步骤顺序与失败关闭；单元及真实API验证 | 通过组件检查，会话端到端未执行 |
| 数据库 | 核对归属过滤、班级锁、唯一名称、修订/审计原子性；真实MySQL写读及重复/旧修订反例 | 通过现有结构读写；无新增迁移，旧迁移兼容随既有集成执行 |
| 公共函数 | 核对归一、条件得分和槽位渲染共享契约；断网单元及20条工程评测 | 通过 |
| 错误处理 | 核对400/403/404/409及模型1501；拒绝路径不保留未验证输出 | 通过组件检查；持久失败诊断待3.1 |
| 安全 | 当前数据库教师身份、资源归属、纯文本DOM、无任意工具/代码执行；原门禁扫描与权限断言 | 管理组件通过；专项攻击审计仍归安全变更 |
| 性能 | 新增管理入口无长模型请求，现有长请求容量未修改；分页上限100、定义8 KiB、最多3步 | 有界检查通过，未声称技能端到端P95达标；会话耗时留3.2 |

技能调用记录：`openspec-apply-change` 输入为本变更，读取AGENTS/README/全部规划并执行状态、apply和严格校验；`project-add-tests` 输入为2.2组件，读取安全/测试/AI/实现代码后补单元、API、MySQL、浏览器断言；`project-prompt-eval` 输入为 `bounded-skills-v1` 槽位，读取AI规范与上游评测脚本后固定10正10负工程检查并重跑上游20条；`project-review` 输入为本轮文件和实际日志，按八规范和七类完成助手自检。均非人工批准。

**2.2仍未完成，整体仍4/13。** 缺口为持久会话宿主、本人步骤记录、失败脱敏诊断及流中配置变更验证；不因管理组件可运行而勾选完整场景。未新增学生会话入口，不跨入第3/4组实施。后续接入3.1/3.2时补齐上述证据后再判定2.2。合并前人工代码/约束文件评审待小组安排；本轮未做发布、归档或人工签署。

## 2026-11-08 续做：2.2与3.1交接，3.2仍待完整代理取证

### 变更说明

仍在 `change/2026-11-07-streaming-assistant-storage`，基线 `c17adde4babc07bc6805994806597667e06700d0`；保留原有工作区，未提交、推送、合并或归档。本轮用GitHub连接重新核验main保护及必需 `make check` 仍启用。范围已在实施前明确为第3组接入，同时闭合2.2所需的会话宿主证据；未实现反馈、Swagger、外部工具或发布。任务从4/13推进到6/13，仅勾选2.2、3.1，3.2保留未完成。

新增本人会话创建/列表/分页读取与 `POST /api/v1/sessions/{id}/messages`，统一同源Cookie、Origin和写入头，当前身份/班级及本人资源校验全部在服务端。创建也要求幂等键；消息指纹覆盖本轮规范化问题、章节、检索模式。采用0008原有表、组合外键、单在途和唯一成功约束，无新迁移。`SessionService` 管理受理、租约、配置重读和原子提交，`SessionStreamService` 负责已校验段落与步骤出流。来源与助手配置在事务提交前重新锁定，过期执行者不能续写。

检索增加服务端绑定材料的仓储视图，关键词SQL、向量版本与回表校验都在召回前求交，空绑定不扩大到全班。独立单次问答默认行为不变，新增真实副作用计数断言，证明正常/无证据/故障回归不增加私人会话、消息或执行记录。历史仅已成功轮次最近6条、每条500码点，证据最多4片且总量不超12000码点。

生成按声明步骤或最多3段顺序调用，等待前段校验确认后再继续；解题只渲染审核槽位，上传文字只在user数据中。首段后使用 `complete_once`，瞬态故障不隐式重试；整个检索与流式生成共用35秒预算。成功消息、出处快照、执行步骤和成功状态同事务完成后发done；终帧丢失可以按同键回放持久结果，失败只保留固定诊断。本人 `/runs` 现在包含会话运行，教师无法读其他人的记录。

新增 `/sessions` 与详情页面，复用现有布局/CSP/纯文本DOM，提供助手与模式选择、章节范围、流式预览、取消和回读。失败/异常帧/断流清除预览，界面只把done后的结果视为成功。前端只显示启用助手。完整真实代理抓帧及网络取消、UTF-8切包与容量验收仍未齐备，未把页面主路径当成3.2完成。

### 实际验证与失败复测

所有环境都是本机独立随机Compose项目、`campusclaw_test_` 合成A/B班，含同班另一学生、教师及B班学生/教师；数据库与Qdrant为真实服务，模型明确为替身，不调用课程网关。项目在退出时自动清理容器、网络、卷及候选镜像。uv命令均使用 `UV_CACHE_DIR=/private/tmp/campusclaw-uv-cache`。未操作生产数据。

| 实际命令 | 退出码、范围与结果 |
| --- | --- |
| `uv run --locked pytest -q --disable-socket tests/unit tests/api` | 0，最终367项通过，新增问题/键/权限/流前拒绝及首段后不重试断言 |
| `uv run --locked pytest -q --tb=short tests/integration/test_compose.py` | 多次受影响增量回归；最后边界复测0，1项43.29秒，覆盖当前宿主、10片材料截为4片、跨班章节同构与流前数据库故障零副作用 |
| `CAMPUSCLAW_CHROMIUM='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' uv run --locked pytest -q --tb=short tests/browser` | 修复后0，1项19.50秒；键盘新建会话、真实同源POST SSE无绑定固定回复、两条消息回读、预览完成清理与390/1440宽度，包含既有应用/技能/资料/章节路径 |
| `uv run --locked python -m scripts.evaluate_skills` | 0，固定10合法+10非法槽位；会话执行证据另列，不以纯函数评测代替 |
| `uv run --locked python -m scripts.evaluate_ai_apps` | 0，上游同步应用工程20条通过 |
| `make check CHANGE=2026-11-04-add-streaming-ai-assistant` | 最终0：规约12/12、135个Python文件格式、静态/分层/场景追溯、367项单元/API（2.45秒）、4项启动（2.30秒）、Gitleaks、Trivy依赖/候选镜像扫描、真实集成1项（45.97秒）通过；含隔离过期数据行级回灌后隐藏及重复清理 |
| `make check-static CHANGE=2026-11-04-add-streaming-ai-assistant` | 0，任务与场景清单同步后通过 |
| `node --check`（会话、应用内联脚本及浏览器脚本）、`git diff --check` | 0，语法和空白检查通过 |

失败保留：第一次真实集成发现扩展查询误把sessions整表加入SELECT，旧同步执行503；修正后通过，未改旧断言。丢回执测试最初在上一条畸形流生产者尚未关闭时立即重发，命中真实账号并发429；保持容量/租约约束，夹具改为等待生产者退出，并强制丢回执错误必须为1500，再验证持久成功回放零模型调用。会话页面首次误向现有不分页的章节列表传分页参数，导致400和浏览器等待失败；按真实章节契约改正后19.50秒复测通过。流前检索故障夹具最初没有命中：事件挂在配置仓储引擎，而检索使用独立引擎；迁到实际检索引擎并增加“确实注入1次”断言，原503、无SSE、零消息/记录判据复测通过。期间ruff导入/未使用变量问题均已修复，不留跳过或降低门禁。

原始失败与复测日志为 `reports/2026-11-04-add-streaming-ai-assistant/sessions-*.log`，最终完整门禁为 `sessions-final-make-check.log`；浏览器截图与 `session-result.json`、实现文件SHA-256清单同目录。父目录旧技能/同步评测原始结果保留。未调用真实课程模型、未做正式效果人工裁决，任务5.2仍未完成。

### 场景与副作用

| 场景 | 实际观察与证据 |
| --- | --- |
| SK-N01/B01 | 同时绑定可匹配内置与上传技能，最高分上传胜出，3步顺序进入本人记录；同分/零分Unicode规则单元回归，真实既有会话停用后下一轮不再选该技能；教师读步骤记录404 |
| SK-B02/F05 | 无证据解题固定通用提示、空出处、零模型调用；上传/内置/无命中三条有证据解题路径的自由答案输出均只有meta和1501错误，无delta或成功正文；越权指令只进user数据 |
| SK-F01/F02/F03 | 原管理白名单/重复键/名称/学生越权与跨班读取/绑定回归继续通过，无额外写入或工具调用 |
| SK-F04 | 三步技能第二步依赖失败，实际只调用2次，第三步零调用；meta/delta/error(1500)，没有done，私人失败记录正文/输入均空 |
| ST-N02 | 原单次问答各阶段执行前后私人sessions/messages/application_runs数量一致；原检索/Qdrant回归保留 |
| ST-B01/B02 | 真实10片召回仅取绑定范围4片；历史最近6条且最长500；外班章节与缺失均404。助手停用后记录enabled=false、空材料绑定、固定答复且零模型调用，新建拒绝 |
| ST-F01/F02/F03 | 2–500码点、未知字段/非法键与同键异输入拒绝；匿名401及错误来源/缺写入条件流前拒绝；同班学生、教师、B班学生/教师列表无本人资源，直读与发消息均404同构 |
| ST-F06核心 | 模型暂停时同键409；关闭流后重试attempt=2、仅一条原用户消息和一条成功助手消息。提交后故意丢回执，下一请求回放原成功且模型无新增调用。过期租约重试后旧令牌提交409 |
| ST-F04/F07部分 | 检索引擎注入实际DB错误，503且无SSE/新消息/新运行/模型调用；受理后助手修订变化拒绝成功。真实代理的首段后撤权、来源变化、故障/取消仍归3.2 |

### 数据治理与七类自审

复用现有副本清单，只在MySQL保存受理输入、成功消息/步骤、最小出处和去内容诊断，不新增文件、向量或缓存正文副本。统一清理额外处理每批100个过期会话及所有私人子对象。真实集成把会话父期限改为过去，证明清理前即不可读；清理后按原期限回灌该会话/操作/消息/执行/出处行，仍不可读，再重放清理为1、重复为0。这是隔离行级恢复验证，未宣称生产备份、RPO/RTO或正式恢复演练通过。原0008/0009空库/重跑/回退兼容检查继续随门禁执行。

| Harness类目 | 手段、对象、判据与结果 |
| --- | --- |
| 接口入口 | 核对会话路由、AI_USE策略、Cookie写防护与只读分页；API/真实HTTP检查401/403/404/409及无流前失败，通过 |
| 业务逻辑 | 核对受理/重试/完成状态、当前配置和受控步骤；真实暂停/取消/丢回执/旧租约证明唯一结果，通过3.1和2.2核心 |
| 数据库 | 核对班级/本人过滤、复合外键、单在途、唯一成功、短事务及来源锁；真实MySQL与回灌清理，通过；无新增迁移 |
| 公共函数 | 规范化问题/键、槽位、引用/数值、SSE基础及ChatClient单次入口回归通过；浏览器异常解帧矩阵待3.2 |
| 错误处理 | 校验/依赖/配置变化安全错误，不存原始模型或异常，流前故障零新增；故障夹具次数及复测均留证，通过当前范围 |
| 安全 | 当前身份、私有归属、来源交集、纯文本DOM、上传内容不提权；现有扫描与授权断言通过；专项审计仍归安全变更 |
| 性能 | 共享全局长请求4、单账号模型并发1和35秒总预算；未降低约束。当前会话真实代理满额、排空、普通请求预算与首段/总P95未执行，3.2保留缺口 |

技能使用：`openspec-apply-change` 读取本变更全部规划并按现状实施/校验；`project-add-tests` 按安全/测试/AI/后端规范补上述单元、API、真实MySQL与浏览器断言；`project-data-change` 核对0008/0009和字典、父子期限、副本清理及隔离恢复重放，无生产操作；`project-prompt-eval` 重跑既有技能与同步固定工程集，并区分新宿主合成集成和未执行真实网关；`project-review` 读取评审规范、八规范相关范围、实际差异及原始日志完成本会话七类自检。没有创建独立聊天或假冒同伴评审。

结论：**2.2、3.1实现交接完成，整体6/13；3.2、4.1、4.2、5.1–5.4共7项未完成。** 后续先补3.2代理、取消/竞态/解帧/容量与时延证据，再做历史出处详情及反馈；Swagger/一键接口用例、完整课程评测和收尾仍缺。README、页面清单、字典、任务与追溯变更原因均为登记实际接入和证据，不豁免规约。约束文件和业务代码仍待人工复核，真人测试归最终验收；本轮没有批准、发布或归档。

交接末次补充：会话输入改为前端按Unicode码点检查2–500字符，不使用HTML的UTF-16 maxlength来误拒emoji；启用助手选项做前端筛选，服务端拒绝停用助手的断言保留。`node --check < app/templates/_sessions_script.html` 与静态门禁退出0；末次浏览器主路径重跑退出0，1项19.62秒，日志为 `sessions-browser-handoff.log`。截图、源码摘要及 `sessions-handoff-static.log` 已更新。完整UTF-8分包/异常流矩阵仍不在此主路径结果中，留3.2执行。

## 2026-11-08 续做：3.2真实会话代理交接

### 变更说明

本轮限第3组3.2，沿用未提交工作区，基线仍为 `c17adde4babc07bc6805994806597667e06700d0`、分支 `change/2026-11-07-streaming-assistant-storage`。编码前读取AGENTS、README、本变更proposal/design/四份spec/tasks及八规范；GitHub公开分支接口实际返回 `main protected=true`。没有提交、推送、归档或修改主干保护。

修复会话取消链：`SessionStreamService` 将取消上下文传到 `ChatClient.complete_cancellable` 和 `JsonEndpoint`，在连接建立后登记socket关闭回调；断开/排空时shutdown正在等待的模型连接，模型线程退出后才释放容量。取消异常先检查上下文，不再按瞬态传输错误自动重试或重复扣模型配额。原同步应用、嵌入及单次问答未传取消上下文，沿用原接口。未改提示词、模型、检索参数、技能行为或数据库结构。

新增 `session_proxy_worker.py` 与 `session_proxy_check.py` 仅作隔离测试。worker经现有夹具复制到容器/tmp，不进入镜像或生产路由；控制入口只操作本轮新建的合成班级、账号及来源。真实会话/检索/事务/ChatClient、Cookie、Origin防护、NGINX配置和Gunicorn配置均使用生产代码，只有HTTP模型为可暂停的合成网关。每一段模型响应是完整校验单元，第二段等待显式控制放行；不是把全部响应预先缓冲后拆帧。

新增 `session_frames.mjs` 用Node执行实际会话页面脚本，注入fetch字节流和DOM观察点，覆盖241个单切点、逐字节中文/emoji、CRLF及8种异常清屏；pytest入口为 `test_session_frames.py`。此项是页面脚本契约测试，另执行真实Chromium主路径，不把DOM夹具称为真人操作。

### 验证记录

环境：本机Docker 29.4.2、独立随机Compose项目与 `campusclaw_test_` 数据库、真实MySQL/Qdrant、TLS NGINX固定镜像、单worker/8线程、共享长请求上限4。合成班级20个账号、1000条资料；真实模型适配器只访问隔离HTTP替身，未调用课程网关。退出清理项目容器、网络、卷及候选镜像；无生产数据操作。uv命令使用 `UV_CACHE_DIR=/private/tmp/campusclaw-uv-cache`。

| 实际命令 | 结果 |
| --- | --- |
| `openspec validate 2026-11-04-add-streaming-ai-assistant --strict` | 0，通过 |
| `uv run --locked pytest -q --disable-socket tests/unit tests/api` | 0，369项通过，2.89秒；含取消不重试及页面脚本矩阵 |
| `uv run --locked pytest -q --tb=short tests/integration/test_compose.py` | 最终0，1项51.50秒；原认证、迁移、检索、应用、技能、会话及新增真实代理全部断言通过 |
| `CAMPUSCLAW_CHROMIUM='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' uv run --locked pytest -q --tb=short tests/browser` | 0，1项21.73秒，真实键盘会话/应用/技能/资料主路径及390/1440宽度 |
| `node tests/browser/session_frames.mjs` | 0，241个切点及逐字节UTF-8/CRLF、8种错误均通过，未完成预览清空 |
| `make check-static CHANGE=2026-11-04-add-streaming-ai-assistant`、`ruff check app tests scripts`、`git diff --check` | 0，静态、追溯、语法与空白检查通过；收尾门禁另列 |

失败与复测保留：首次隔离worker误用迁移表导出名 `index_builds`，启动未就绪；改用实际 `builds` 别名。随后测试运行期间调整helper签名造成参数不匹配，后续冻结测试输入重跑。完整私有会话测试首次通过后，原最小传输检查发现模型替身503分支没有删除active标记；修复替身收尾后重跑。技能停用反例曾得到第二个delta，排查为测试控制入口更新助手修订时遗漏复制技能绑定，停用时该技能已不在当前绑定；补齐绑定复制后维持原“只能error、不得成功”断言，最终真实依赖51.50秒通过。未降低阈值、删断言或添加跳过。原始失败日志为 `streaming-proxy-integration.log`、`streaming-proxy-retest.log`、`streaming-proxy-complete.log`、`streaming-proxy-final.log`，通过记录为 `streaming-proxy-handoff.log`。

### 场景、容量及副作用

| 场景 | 实际判据与结果 |
| --- | --- |
| ST-N01 | 真实TLS响应先meta再delta；第二段仍在HTTP网关active且未completed时已收到第一段。随后放行第二段，唯一done对应已持久消息/出处/本人run，拼接文本与数据库相同 |
| AUTH-F05、ST-F02/F04 | 有效Cookie但缺来源/头、错误Origin、空写入头分别403，消息回读前后一致、上游零请求；已有匿名、撤销与流前真实DB故障继续通过 |
| ST-F04 | 第一段后HTTP网关503，唯一error(1500)、无done；消息只有用户输入。首段后故障零隐式重试；页面脚本错误/断流清空预览 |
| ST-F05 | 第二段错误数值、越界出处和合成未开放答案文本均error(1501)，无非法delta或成功正文。网关断言模型输入不含合成受保护答案或外班资料，注入问题只作用户数据；回读和抓帧均无该答案。既有解题自由文本拒绝路径继续通过；本课未新增真实测验题库 |
| ST-F06 | 首段暂停期间同键409；断开下游后HTTP网关在未放行时观察到socket断开、账号/全局容量回收。同键重试后仅一条用户及一条成功回复。已成功同键回放返回原message_id，上游状态不变；实际提交后丢回执、陈旧租约和唯一成功事务继续由3.1真实MySQL夹具验证 |
| ST-F07 | 第一段后分别改变助手修订、停用当前绑定技能、切换证据发布版本、停用数据库账号；后续只有1400/1100错误，无后段成功，未撤销用户回读仅原用户消息，撤销用户回读401 |
| OPS-11/排空 | 生产形态全局4个真实会话长流占满，第5个429/1600且不写消息；1000条资料、10并发50次读取均在1000ms内，双探针及登录正常；排空后/live200、/health503，四流error(1500)、网关取消、容量归零，取消尝试均无成功消息。测验提交按原任务留最终候选复验 |

首次独立通过的3条分段样本：首段中位33.23ms、P95 56.78ms；总耗时中位345.27ms、P95 370.90ms；满额下50次普通读取P95 29.02ms。P95为nearest-rank，3条取最大；模型为本地合成网关，总耗时包含测试控制放行开销，不能推断课程网关或真实用户效果。完整门禁将重跑并更新机器报告，以最终 `private-sse.json` 为准。报告包含原始分段帧、首段先于放行标记及每条时延；原最小传输证据 `minimal-sse.json` 另保留。机器报告、日志均在被忽略的 `reports/2026-11-04-add-streaming-ai-assistant/`。

### 七类自审与评审结论

| 类别 | 手段、对象、判据及结果 |
| --- | --- |
| 接口入口 | 对真实会话路由及同源Cookie、写入头、容量拒绝核对，HTTP/SSE及数据库副作用断言通过 |
| 业务逻辑 | 校验前出流禁止、段顺序、终态、取消/排空、同键成功回放；真实代理及既有事务回归通过 |
| 数据库 | 无新增迁移或副本，复用本人/班级过滤与唯一成功事务；真实MySQL一致性及上游迁移回归通过 |
| 公共函数 | JsonEndpoint不传context的调用保持原形，ChatClient取消不重试；单元、共享检索/模型和页面脚本回归通过 |
| 错误处理 | 1500/1501/1400/1100无不可信正文；失败只留既有去内容诊断，预览清屏，真实夹具断言通过 |
| 安全 | 当前身份/配置/来源每段重验，未开放答案/外班材料不入模型输入；原授权断言保留。专项攻击、破坏验证及人工审计仍归专门变更 |
| 性能 | 真实代理/现有WSGI、共享上限4、短请求50样本与探针/登录/排空通过，报告明确合成网关和样本量限制 |

技能使用：`openspec-apply-change` 输入本变更3.2，读取全部规划、状态/apply/严格校验并按证据勾选；`project-add-tests` 输入取消链及ST-N01/F04–07，读取测试/安全/AI等规范、生产代码和旧夹具，补单元/页面脚本/真实代理断言并实际运行；`project-review` 输入本轮差异及原始报告，按八规范与七类核对权限、兼容、错误、容量和文档。未改AI提示/配置或数据结构，不另调用提示评测/迁移技能；无发布授权，不调用发布技能。

3.2实现交接完成，整体 **7/13**；未完成为4.1、4.2、5.1–5.4。README、课程入口及场景映射同步的原因为登记已验证的真实代理能力，没有扩大业务或放宽规则。本轮只交付第3组，按REV-02保留后续组。人工代码及约束文件复核待小组安排，真人测试归最终验收；没有自填批准。

收尾实测：`make check CHANGE=2026-11-04-add-streaming-ai-assistant` 退出0，日志 `streaming-make-check.log`；规约、分层、格式、场景追溯、369项单元/API、4项启动、Gitleaks、Trivy锁文件/候选镜像及真实依赖集成全部通过，最终集成1项52.51秒。最终机器报告时延：first_median_ms=35.16ms、first_p95_ms=55.41ms、total_median_ms=348.06ms、total_p95_ms=379.31ms、short_p95_ms=25.70ms。`openspec instructions apply` 实际返回complete=7、total=13、remaining=6；`git diff --check` 退出0。完整门禁后仅补充本文实际结果，无代码调整。

## 2026-11-08 续做：第4组历史出处与教学反馈

### 变更说明

继续同一变更、同一未提交分支 `change/2026-11-07-streaming-assistant-storage`，基线仍为 `c17adde4babc07bc6805994806597667e06700d0`。本轮范围为4.1、4.2，未实施Swagger、接口作业入口、课程效果实验或外部工具。编码前重读AGENTS/README、状态与apply返回的全部规划，按产品/后端/安全/测试/数据/运维/评审规则核对现状；GitHub公开分支接口再次返回 `main protected=true`，本变更严格校验通过。

新增本人历史出处GET、学生PUT反馈、教师本班反馈GET/PATCH及 `/console/feedback` 页面。会话回读附本人反馈及可分享章节，学生先查看教师可见字段、再明确确认分享；无证据但成功的固定回复也可反馈。未解决的说明去首尾空白后1–500码点，helpful可空；修订冲突拒绝覆盖，相同内容不新增/重开，实质改评重新pending。教师只能处理本班未解决反馈，返回白名单 `id/rating/note/status/revision/chapter/updated_at`，无用户标识、私人链接、问题、答案或出处。

历史出处只从生成时快照返回标题、摘录及区间；重建后显示historical及原版本，不跳新切片。读取同时校验本人、期限、当前同班来源及独立删除凭证。恢复的旧成功操作在副本重放前，也不会通过本人回复、关联用户消息、运行记录或历史输入返回已删除来源。原有删除事务继续清空SQL副本、登记Qdrant清理凭证；未新增数据库结构、迁移或留存期限。本人当前身份仍从数据库重验，教师身份不取得私人访问权。

### 实际验证与失败复测

环境为本机独立随机Compose项目和 `campusclaw_test_` 合成A/B班数据，真实MySQL/Qdrant；既有TLS NGINX/Gunicorn会话测试继续执行，模型为替身。本组Qdrant向量为明确的二维合成数据，只验证删除补偿，不代表课程嵌入质量。uv使用 `UV_CACHE_DIR=/private/tmp/campusclaw-uv-cache`。容器、网络、卷及候选镜像退出清理；没有生产数据、推送、合并或发布操作。

| 实际命令 | 结果 |
| --- | --- |
| `openspec validate 2026-11-04-add-streaming-ai-assistant --strict` | 0，通过 |
| `uv run --locked pytest -q --disable-socket tests/unit tests/api` | 最终0，387项通过，2.85秒；新增反馈输入/修订/Unicode/匿名/角色/写入头反例 |
| `uv run --locked pytest -q --tb=short tests/integration/test_compose.py` | 4.1/4.2核心首次完整通过为53.64秒；补齐真实章节、失败轮次、并发改评后的最终交接0，1项54.03秒 |
| `CAMPUSCLAW_CHROMIUM='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' uv run --locked pytest -q --tb=short tests/browser` | 学生/教师闭环复测0，1项20.27秒；覆盖预览、必填、无证据回复评价、教师处理、四态和390/1440宽度，视觉复核后的末次结果另记 |
| `make check CHANGE=2026-11-04-add-streaming-ai-assistant` | 0，完整规约/格式/分层/追溯、387项单元/API、4项启动、Gitleaks、Trivy依赖与候选镜像、真实依赖集成通过；集成1项53.78秒，日志 `feedback-make-check.log` |
| `ruff check app tests scripts`、`python scripts/check_layout.py`、`python scripts/scenario_trace.py`、`node --check`（会话/反馈/浏览器脚本）、`git diff --check` | 0，通过实际执行的受影响静态检查 |

失败保留及修复：新增出处的删除凭证关联使SQLAlchemy无法推断JOIN左侧，会话回读503。最初简化章节提取未解决，之后离线编译复现 `InvalidRequestError`，为出处和反馈查询显式指定FROM后真实回归通过；保留HTTP状态断言。浏览器登录到新入口曾返回原默认资料页，补充同源登录返回路径白名单 `/sessions`、`/console/feedback` 后闭环通过。清理故障夹具首次没有命中失败，因为复用模型配额的冻结数据库时钟，导致清理凭证在该时钟下未到期；将本组与该冻结时钟隔离，并显式恢复合成凭证的到期时间后实际故障次数与收敛断言通过。补真实章节用例曾遗漏归类接口的幂等键，按已有契约补键后通过。未改旧断言、降阈值或增加跳过。

日志 `feedback-integration.log`、`feedback-integration-retest.log`、`feedback-diagnostic.log`、`feedback-query-retest.log`、`feedback-integration-final.log`、`feedback-handoff.log` 保留失败；通过为 `feedback-clock-retest.log`、`feedback-handoff-retest.log`。浏览器失败及复测分别为 `feedback-browser.log`、`feedback-browser-retest.log`；源码及报告位于 `reports/2026-11-04-add-streaming-ai-assistant/`。浏览器截图/JSON原件沿用 `reports/2026-11-04-add-traceable-retrieval/browser/`，含feedback与teaching-feedback文件名。

### 场景与副本结果

| 场景 | 真实断言与结果 |
| --- | --- |
| FB-N01 | 学生读生成时原文区间，提交未解决；教师白名单投影的说明与真实本班章节正确，处理后pending数量减1；浏览器先预览后确认，键盘完成闭环 |
| FB-B01 | 发布版本切换为2后仍返旧快照/旧区间及index_version=1，不包含新切片。删除后出处deleted、消息/运行正文为空、同键重放409；原文404，SQL副本均去内容 |
| FB-B02 | 同评价说明重放不增加行或修订、保留handled；实质变更重新pending，改helpful移出未解决；两个同旧修订并发不同说明得到200/409，始终同一行 |
| FB-F01 | 未知评价、空白未解决、超500码点、伪造班级、非法修订拒绝；成功轮次用户消息与只有用户消息的失败轮次均409，无反馈。单元另测500个emoji上限及畸形Unicode |
| FB-F02/F03 | 匿名401；学生读/处理教师队列403，教师本人之外出处404；同班他人/外班学生出处与评价404，外班教师处理反馈与缺失均404/1300。教师队列不含任何私人资源引用 |
| FB-F04 | 实际UPDATE teaching_feedback注入数据库错误，503/1500，注入计数1且原修订/内容未变。SQL来源已删而Qdrant还存1个向量，故障清理确实failed；此期间出处无摘录，恢复清理后向量为0，重复执行无失败 |
| 无证据反馈 | 浏览器用无绑定固定回复创建成功助手消息，未解决缺说明拒绝预览；主动填写说明可保存，教师仅见该说明，无原问题 |

副本清单：原文/正文在MySQL，向量在独立Qdrant集合；消息、操作输入、执行步骤、出处标题/摘录及反馈说明均在MySQL。没有新增文件或缓存正文。测试保存本会话SQL行级副本及原文行，删除后重新写回旧成功值，独立删除凭证立即阻断私人读取；接流量前重放删除凭证两次，SQL正文清空、原文不存在，再执行实际Qdrant补偿至0。原反馈到期/父对象到期规则不延长。既有空库、升级、重复迁移、隔离回退及过期行恢复测试随完整门禁通过。本次是合成行级恢复与补偿验证；生产加密备份、14天轮换、RPO/RTO和实名运维演练未执行，不能由此宣称通过。

### Harness七类自审与评审结论

| 类别 | 手段、对象、判据与结果 |
| --- | --- |
| 接口入口 | 对照FB路由、Cookie/Origin/写入头、角色策略、输入/分页和统一错误；单元/API/真实HTTP正反例通过 |
| 业务逻辑 | 核对成功轮次可评、内容重放不重开、实质改评与处理版本；真实MySQL并发200/409及队列数量通过，教学意图真人确认留最终验收 |
| 数据库 | 核对班级/本人归属、父子期限、唯一消息反馈、短事务、追加去内容审计；真实副作用/回滚/恢复删除重放通过，无新增迁移 |
| 公共函数 | 复用clean_text、统一分页、SessionService来源判断；387项断网单元/API与上游回归通过 |
| 错误处理 | 故障明确503、非法400、私有隐藏404、冲突409；实际故障次数、状态未改、页面重试和预览清屏通过 |
| 安全 | 教师七字段白名单、不自动复制私有正文/身份；来源删除凭证、当前身份、纯文本DOM和服务端归属检查通过，专项攻击/审计仍归安全变更 |
| 性能 | 列表默认20/上限100、说明500码点、出处1–4有界，无模型/外部网络进入事务；既有满额短请求代理回归保持通过。本组未新增独立反馈大规模压测结论 |

技能记录：`openspec-apply-change` 输入本变更第4组，读取实际规划/状态/apply并按通过结果勾选4.1/4.2；`project-data-change` 输入快照、反馈与删除副本，读取字典、0008/0009、数据/运维/后端/安全规范，核对无新schema、固定期限、备份删除清单及真实补偿；`project-add-tests` 输入FB全部场景，补输入/API/真实MySQL/Qdrant/浏览器断言并保留失败复测；`project-review` 核对本轮范围、八规范相关项、实际报告与七类。未改变提示词、模型或检索参数，不调用提示评测技能；没有发布授权，不调用发布技能。故意破坏与独立安全审计按仓库调度留安全变更，真人独立走查留最终验收。

4.1、4.2实现与自动化交接完成，整体 **9/13**；5.1–5.4仍未完成。README、页面清单、字典、设计细化、任务及场景映射同步用于登记实际接口/数据行为，没有放宽原规范。约束文件及业务代码仍待人工复核；未自行批准、提交、推送、归档或发布。

末次视觉及静态复核：实际查看学生预览窄屏和教师宽屏截图，修正反馈页误显示空资料列表及预览截图滚动位置，未改服务端契约。随后浏览器重跑退出0，1项20.53秒（`feedback-browser-final.log`），预览字段及无横向溢出断言通过；`make check-static CHANGE=2026-11-04-add-streaming-ai-assistant`、`git diff --check`退出0。完整门禁原运行387项单元/API为2.72秒、4项启动2.30秒、真实集成53.78秒；末次模板调整以受影响浏览器与静态回归验证，完整变更最终收尾仍属5.4。


## 2026-11-08 分批提交与远程交付准备

### 变更说明

用户明确要求“细化提交并推送到远程仓库”。范围为当前82个文件的已有开发候选，按依赖拆分10笔提交；不新增业务，不合并主干，不创建PR，不归档变更。当前分支 `change/2026-11-07-streaming-assistant-storage`，远程origin为 `git@github.com:WafoeX/CampusClaw-Team.git`。推送前 `git ls-remote --heads` 确认main仍为 `c17adde4babc07bc6805994806597667e06700d0`，远程尚无同名开发分支，采用普通新分支推送并建立upstream。

提交前使用 `project-review` 核对AGENTS/README、评审/安全规则、任务、全量文件及证据；确认没有生效的本地pre-commit/pre-push钩子，未删除或跳过钩子。报告、私有.env、运行数据与证书继续忽略，没有纳入提交。修正tasks中3.2已经勾选但仍称未完成的旧进度说明，保持9/13及5.1–5.4未完成，约束文件仍待人工复核。

### 验证记录

- `UV_CACHE_DIR=/private/tmp/campusclaw-uv-cache make check CHANGE=2026-11-04-add-streaming-ai-assistant` 退出0，含387项单元/API、4项启动、秘密/漏洞及候选镜像扫描，真实集成1项55.83秒；日志 `reports/2026-11-04-add-streaming-ai-assistant/commit-push-make-check.log`。
- `uv run --locked python -m scripts.evaluate_ai_apps` 与 `uv run --locked python -m scripts.evaluate_skills` 退出0，分别20条及10正10负工程回归；本轮未调用真实课程网关。相应日志为 `commit-push-apps-eval.log`、`commit-push-skills-eval.log`。
- 提交逐笔精确核对暂存文件集合，并执行 `git diff --cached --check`；提交尾注只登记真实Change/Verify/Evidence。测试结论针对最终组合候选，没有逐一对每个中间提交重跑完整门禁。

前9笔真实提交如下；第10笔为本记录、README/字典/页面清单/设计/tasks/追溯的同步提交，避免在提交内容中伪造自身哈希。

| 提交 | 内容 |
| --- | --- |
| `d37d03ae60ad` | docs: 归档主干同步与开发基线核对 |
| `14da1b760977` | feat(data): 建立助手存储迁移与来源副本清理 |
| `56e590bbb7bd` | feat(stream): 增加有界SSE与网关连接取消 |
| `0d3b23be8e3f` | feat(ai): 实现班级应用、受限技能和私有轮次服务 |
| `19e076da0362` | feat(web): 接通助手接口、教学反馈与页面交互 |
| `1c796de685f8` | test(ai): 覆盖配置、会话与反馈的授权边界 |
| `512efe3f7426` | test(integration): 验证双库事务、代理流式和恢复补偿 |
| `8f53ddb1bc9a` | test(browser): 覆盖会话反馈闭环与UTF-8解帧 |
| `b67f400fa83f` | test(eval): 固定应用与技能工程评测样本 |

### 评审结论

候选可提交到开发分支供后续工作与评审，整体仍9/13；提交/推送不等于5.4收尾、人工批准或课程验收。七类技术自审沿用上方本轮实际证据；本次仅组织提交与同步状态，无新增技术例外。远端推送结果将在提交后用 `git ls-remote` 与本地HEAD核对，并在交付答复中提供分支链接。

## 2026-11-08 第5组接口契约与评测续做

### 变更说明

基线 `256fd924765986a95923950b9b073e1dd10e1af7`，分支 `change/2026-11-07-streaming-assistant-storage`，开始时工作区干净。本轮未提交、推送或合并。编码前只读查询 GitHub 分支API，`main.protected=true`；本机无 `gh`、沙箱DNS失败后改用获准网络读取，未更改保护规则。

完成Task5.1：从已登记路由生成同源OpenAPI，提供登录后 `/swagger` 原生试调控制台（无第三方脚本），Cookie/Origin仍由浏览器处理，写入头及幂等键受原API检查；文档包含请求字段、路径/分页、错误响应及SSE终态。控制台复用共用样式，原始响应以textContent显示，失败/取消清空未完成显示。课件Bearer差异继续交最终验收1.5确认，不宣称课程等价已批准。

`apitest/cases/`按路径/方法组织登录、检索、模板/预览、技能、创建会话及发消息，运行器调用门禁共享pytest及真实集成入口；失败、跳过、零用例非零，本地HTML不复制错误正文/请求/日志。Makefile仅将新增apitest代码纳入原有格式及lint检查，未删断言或降低扫描要求。

完成Task5.3：沿用并补强真实MySQL回归，覆盖同班同学/教师及外班账号的列表与直读隔离；外班助手与缺失助手同构、停用后默认角色/空证据；客户端class_id明确拒绝且零消息/运行写入、绑定材料交集及外班章节隐藏；技能停用后下一轮skill为null且成功。合成身份为脚本中的session/other/a_teacher/session_b_student，不对应真人。具体断言见 `tests/integration/ai_apps_runtime.py`，由 `tests/integration/test_compose.py`运行。

Task5.2新增通用固定20条评测及pytest入口，未改生产提示词。用户明确模型版本不作前置；记录配置指纹及模型标识，不推断提供方版本。真实评测18/20失败，按技能要求暂停该项，不勾选5.2或5.4；详细样本、分层边界及失败见[评测记录](../eval/2026-11-08-assistant-regression.md)。

实际技能：`openspec-apply-change`（输入本变更，读取CLI status/apply及全部规划文件，实施第5组）；`project-add-tests`（输入5.1/5.3及评测入口，读取测试/安全/后端/产品/运维规范、现有代码与测试，新增文档鉴权/路由契约、报告脱敏/退出码、固定20条和真实数据库断言）；`project-prompt-eval`（输入5.2，读取AI规范、模型配置/适配器/生产流宿主，执行固定集替身/真实网关/替身后测）；`project-review`（输入本轮差异与报告，核对规则、门禁和文档，结论为部分交付、真实评测失败、待人工复核）。不涉及迁移或留存变更，未调用数据/发布技能。

### 验证记录

环境为本机Python3.13、Docker29.4.2、Chrome及Node24；依赖锁不变，MySQL/Qdrant均使用每次新建且最终回收的Compose合成隔离项目。uv默认缓存在沙箱外，首次命令因此未执行；后续设置 `UV_CACHE_DIR=/tmp/campusclaw-uv-cache`，未跳过依赖锁。

| 实际命令 | 退出码 | 受检范围/结果 |
| --- | --- | --- |
| `openspec validate 2026-11-04-add-streaming-ai-assistant --strict` | 0 | 开始前严格校验通过 |
| `uv run --locked python apitest/run_all.py` | 0 | 73项，共享API及真实MySQL/Qdrant、探针、SSE与副作用；本地HTML在reports对应apitest目录 |
| `uv run --locked pytest -q --disable-socket tests/unit tests/api` | 0 | 新增评测及报告测试后413项通过，未跳过 |
| `make check CHANGE=2026-11-04-add-streaming-ai-assistant`（首轮） | 0 | 格式/lint、全部严格校验、分层/追溯、391项单元/API、4项进程、秘密与依赖/镜像扫描、1项真实Compose通过 |
| `uv run --locked python -m scripts.evaluate_assistant`（前后） | 0 | 固定20条均通过，明确模型/存储替身 |
| `uv run --locked python -m scripts.evaluate_assistant --real` | 1 | 18/20，两条有据数值题error；保持原样本及判据 |
| `CAMPUSCLAW_CHROMIUM=… uv run --locked pytest -q tests/browser`（首轮） | 1 | 新增试调SSE已成功，但390px选择框溢出，原断言发现问题 |
| 同上（修复后复测） | 0 | 1项完整浏览器主路径通过；既有章节/应用/技能/会话/反馈及新增试调Cookie POST SSE、键盘、390/1440宽度均通过 |
| `make check CHANGE=2026-11-04-add-streaming-ai-assistant`（最终工作区） | 2 | 静态/严格校验、413项单元API、4项进程、秘密/依赖/镜像扫描通过；真实集成在 `session_proxy_check.py:290` 等待上游active清零超时，子命令退出1；最终门禁失败 |

首次文档测试1失败/3通过，原因是测试将同路径多个方法误视为单条路由；改为逐路由核对其operationId后相关26项通过。窄屏修复仅约束试调组合内控件宽度，未更改断言。浏览器截图在 `reports/2026-11-04-add-traceable-retrieval/browser/swagger-390.png` 和 `swagger-1440.png`，沿用既有浏览器报告目录；第5组报告和汇总归本变更目录。

### 七类自审与评审结论

| 类别 | 手段、对象及判据 | 结果/证据 |
| --- | --- | --- |
| 接口入口 | AI核对路由/白名单与BE-02/04；脚本检查文档鉴权、方法/字段、Cookie写入及SSE | 通过，共享API与真实数据库、浏览器；不新增匿名业务例外 |
| 业务逻辑 | AI核对试调不绕过服务、默认角色/配置重读；脚本断言终态与副作用 | 5.1/5.3通过；5.2真实18/20失败，未宣布全组成功 |
| 数据库 | AI核对新增入口不查库/不迁移；真实集成检查原有隔离与零副作用 | 通过，真实MySQL/Qdrant；本轮无新迁移，迁移专项不适用 |
| 公共函数 | AI核对原生控制台复用样式、运行器共享pytest；脚本测格式、报告和固定集 | 通过，413项单元/API及浏览器；未复制业务授权算法 |
| 错误处理 | AI核对HTTP/SSE错误、失败退出码及报告脱敏；脚本复现鉴权/恶意输出/报告失败 | 已检查；真实网关两条error原因未定位，保留失败记录 |
| 安全 | AI核对当前身份、同源、CSP、textContent及私人边界；原有秘密/依赖扫描和资源反例回归 | 通过已启用门禁；专项攻击矩阵与未启用check-security仍归安全预检，本轮未宣称执行 |
| 性能 | AI核对文档只读路由元数据、SSE沿用生产容量；现有代理/短请求容量由真实集成复验 | 已执行既有容量回归，评测逐条记耗时；本轮无新并发压测，不把替身耗时当课程效果 |

5.1、5.3可运行交接完成，整体11/13；5.2真实评测失败，5.4尚未满足完整收尾。模型版本按用户本轮要求记录通用性决策，不修改全仓规范。产品规范、OpenSpec勾选、Makefile和新增测试/脚本均待实际人工复核；未指定真人评审人，未填批准。真实语义裁决、Bearer课件差异和真人独立复验仍交最终验收。依据apply技能“Pause on errors, blockers, or unclear requirements - don't guess”，下一步需按原样本安全定位两条失败并复测，不得改标签或删断言。

最终门禁失败补记：前次完整门禁通过不能替代本次最终结果。取消回收时限保持不变，未改代理/流宿主或该用例断言，尚不能确定故障原因。该集成在执行应用组脚本之前失败，因此不能把最终这一轮当作5.3再次通过；5.3依据前次真实通过交接。原始命令日志与浏览器截图副本归本变更 `reports/` 目录。后续还须定位代理取消回收失败，再重跑完整门禁；本轮不宣称可合并。

## 2026-11-08 失败修复与收尾复测

### 变更说明

用户在上述失败交付后明确要求“请修复并推进”，继续同一变更第5组。实际沿用 `openspec-apply-change`、`project-add-tests`、`project-prompt-eval` 与 `project-review`；输入为两类失败、原20条评测与最终门禁日志，读取当前任务、代理/慢上游夹具、流宿主、HTTP模型适配器、评测包装器及相关测试。未更改业务规约、权限、输出校验、既有时限或门禁标准。

定位到慢上游测试夹具仅在正常返回或FIN分支回收活动标记，RST/异常退出没有统一清理。修复 `tests/integration/streaming_probe_worker.py` 的finally回收，成功和取消仍分开记录，原10秒等待与15秒上游预算不变。新增无需网络的FIN/RST用例，通过原处理器及metrics响应判断结果；临时恢复HEAD旧实现执行相同用例退出1（1失败/1通过），恢复修复后两条均通过。测试夹具不进入生产镜像，没有用增加等待时间或放行残留记录换绿灯。该缺口可确定复现，但因最初集成没有保存具体上游异常，不断言最初那次故障必然由RST触发。

模型侧保留最初18/20报告并增加脱敏诊断，原提示词/参数/样本全量复测20/20；最初P02/P09未复现，原因仍未确定。另修复评测包装器丢失生产取消/首段后禁止重试能力的问题，新增两段调用断言同一StreamContext及allow_retry为True/False。最终再次全量真实网关20/20，未修改生产提示词或以额外重试求通过。工程与真实模型分层、配置/样本/提示词指纹及初次失败限制见[完整评测](../eval/2026-11-08-assistant-regression.md)。

### 验证记录

沿用本机锁定Python依赖及每次新建的合成Compose项目，报告路径为 `reports/2026-11-04-add-streaming-ai-assistant/`，均设置 `UV_CACHE_DIR=/tmp/campusclaw-uv-cache`。没有访问其他成员或生产数据库。

| 实际命令 | 退出码 | 结果 |
| --- | --- | --- |
| `pytest -q --disable-socket tests/unit/test_proxy_fixture.py`，由uv锁定环境临时复原旧夹具 | 1 | 旧实现RST复现，保留 `proxy-fixture-before-fix.log`；finally恢复当前修复 |
| `uv run --locked pytest -q --disable-socket tests/unit/test_assistant_eval.py tests/unit/test_proxy_fixture.py` | 0 | 包装器回归加入后23项通过 |
| `uv run --locked pytest -q tests/integration/test_compose.py` | 0 | 1项真实MySQL/Qdrant/代理回归通过，54.21秒 |
| `uv run --locked python -m scripts.evaluate_assistant --real`（诊断与最终） | 0、0 | 均20/20，原16条真实网关、2条零调用、2条故障夹具；保留首轮失败及两次成功分层报告 |
| `uv run --locked python -m scripts.evaluate_assistant`（最终替身后测） | 0 | 原20条全部通过；不称为真实模型表现 |
| `make check CHANGE=2026-11-04-add-streaming-ai-assistant` | 0 | 全部严格校验、格式/lint/分层/追溯、单元/API、4项进程、秘密扫描、依赖/镜像扫描及真实Compose通过；集成54.36秒 |

完整门禁启动后补入一条评测包装器策略回归，因此又对最终测试集合执行 `make check-test`；未以单条通过替代完整套件。新增代码仅限夹具及评测工具，没有业务迁移，应用回退继续保留0008/0009扩展表；反向移除本轮工具/夹具改动不影响业务数据，不需要物理降级或新回滚演练。

### 七类自审与评审结论

接口与业务：未新增业务入口/策略，复验原同源Cookie、SSE终态及四项契约；数据库：无结构变化，真实双库与私人副作用回归通过；公共函数：新增FIN/RST与模型包装器策略回归，保留共享pytest入口；错误处理：异常路径finally清理、脱敏诊断及原失败报告齐全；安全：模型/资料仍是不可信数据，引用/数值/最终答案策略与已启用扫描不变，check-security尚未启用仍归专项变更；性能：原代理容量、短请求预算与取消时限保持不变并在真实集成通过，不声称新增负载实验或真人体验结果。

最初真实模型两条失败未能复现且无原始诊断，保留为稳定性限制，不宣称已找到或修复其生产根因。修复的是确定性夹具清理缺陷和评测器对生产调用策略的遗漏；当前固定集运行结果满足5.2，技术交付不能代替教学语义人工裁决或提供方模型稳定承诺。约束文件及代码仍待真实同伴评审，未提交、推送、合并或发布；人工验收及Bearer课程等价仍由最终验收登记。

最终补充结果：`make check-test`退出0，最终416项单元/API、4项进程均通过；`CAMPUSCLAW_CHROMIUM=… uv run --locked pytest -q tests/browser`退出0，1项完整浏览器主路径20.75秒，包含同源试调POST SSE、四状态、键盘与390/1440宽度。最终静态检查、严格规约校验及 `git diff --check`通过。原始日志以 `task5-*-repair.log` 等归本变更reports目录。5.2与5.4均按实际结果勾选，CLI状态为all_done、13/13；可交下游开发及人工评审，未自动归档。本轮修复无新功能和存储变化，回退契约沿用前组0008/0009保留扩展表及恢复前重放删除/到期清单。

## 2026-11-08 第5组分批提交与分支推送

用户明确要求“细化提交并推送到该分支change/2026-11-07-streaming-assistant-storage”。核对当前分支、origin与既有验证记录，`git diff --check`及本变更严格校验退出0；未配置额外hooksPath，默认hooks目录没有已启用的自定义钩子，未跳过钩子。

已按行为拆分的真实提交如下，README、任务勾选、课程汇总及本证据另以收尾文档提交保存：

| 提交 | 范围 |
| --- | --- |
| `e06e625` | 同源OpenAPI、Cookie试调页、共用样式、入口规范及文档API回归 |
| `4ec86d7` | 按路径/方法的一键共享接口套件、脱敏HTML、失败退出码回归及lint纳入 |
| `790fbf5` | 通用固定20条助手评测、生产取消/重试策略回归与评测证据 |
| `1618afc` | 慢上游连接重置/异常退出清理及FIN/RST回归 |
| `8a40db0` | 真实数据库四项契约、同源试调SSE及浏览器两档宽度回归 |

提交使用真实Change/Verify/Evidence尾注，代码与测试内容沿用上方实际通过的最终门禁及补跑结果。本次仅组织提交与状态同步，不重复消耗真实网关调用。目标仅为用户指定开发分支，不推main、不合并、不发布；推送后用远端引用与本地HEAD核对，实际结果在交付答复提供。提交与推送不等于人工批准或课程最终验收。
