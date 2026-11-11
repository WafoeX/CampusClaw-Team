# 第 6 课 MCP 与工具接入规约自检

## 变更说明

交付[提案](../../openspec/changes/2026-11-04-add-controlled-mcp-tools/proposal.md)、[设计](../../openspec/changes/2026-11-04-add-controlled-mcp-tools/design.md)、四份增量规格及[任务](../../openspec/changes/2026-11-04-add-controlled-mcp-tools/tasks.md)。第 6 课使用第 5 课助手、技能、SSE、执行记录契约，实施待上游业务验收。

## 验证记录

| 项目 | 状态 | 实际记录 |
| --- | --- | --- |
| 课程及协议 | 已核对 | 网页入口未能直接访问课程站，复读同一工作区前轮下载的[第 6 课任务清单](https://devops.hello1023.com/课程任务清单-第6课.html)和[实践页](https://devops.hello1023.com/课件/第6课-课件-MCP与工具接入/pages/apply.html)。直接读取官方 2025-06-18 的[传输](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)、[生命周期](https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle)及[工具](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)协议。 |
| openspec-propose | 已执行 | 读取 AGENTS.md、README、仓库规则、现有上游规约及技能；经 `openspec context --json` 定位仓库，按各 artifact 的 instructions 和依赖生成。 |
| 结构与任务 | 通过 | `openspec validate 2026-11-04-add-controlled-mcp-tools --strict` 退出 0，`openspec status --change 2026-11-04-add-controlled-mcp-tools` 显示 4/4；只读 apply 指令显示 0/12 实施任务完成。 |
| project-review | 已执行 | 核对八规范及 SEC-01–06、SEC-10、SEC-13–15、AI-02、AI-08–12、DATA-02–08、REV-07–09 的规划覆盖；检查四份规格三段式、失败路径、任务映射、链接和改动范围。 |
| 运行和人工验证 | 未执行 / 待人工评审 | 应用测试、Compose、MCP 客户端互操作、真实网关、Swagger、浏览器、人工与同伴验证待实施。 |

## 评审结论

在课程示例的基础上，拟从部署批准的目录登记地址，教师只读本班去内容运行元数据，连接软删后保留可归属的只增记录。三项差异按课程口径待确认。第 5 课规约提交作为本课分支的直接上游，代码实施按组推进。

## 实施记录（2026-11-11）

### 变更说明

从主干 `7d581d51705a38cb2936e98076e710ab524ec2ac` 建立本地变更分支。独立教学服务使用 Compose 的 `tools` profile，通过内网提供就绪探针及 MCP Streamable HTTP `2025-06-18`，由外置机器令牌认证。服务没有主应用数据或模型的访问配置。会话在单个服务进程内有界保存，满 512 个时拒绝新会话，30 分钟到期，进程重启后须重新握手。

### 验证记录

| 任务 | 实际操作及结果 |
| --- | --- |
| 1.1 | `openspec validate 2026-11-04-add-controlled-mcp-tools --strict` 退出 0。GitHub 分支接口返回 `main protected=true`，提交与本地基线一致。读取本变更全部规划、四份规格及第 5 课技能、私有会话、快照/反馈的上游契约，对照 `app/services/{skills,sessions,session_stream}.py`、`app/adapters/{chat_client,ai_repository}.py` 和实际集成断言。 |
| 1.1 | `uv run --locked python scripts/check_pytest.py -q --tb=short tests/integration/test_compose.py tests/browser/test_chapters.py` 首跑 1 通过、1 失败，真实 Compose 集成通过，覆盖认证、班级权限、检索、技能、本人记录、出处/无证据和代理 SSE；浏览器缺少 README 要求的 `CAMPUSCLAW_CHROMIUM`。指定本机 Google Chrome 后，`uv run --locked pytest -q --tb=short tests/browser/test_chapters.py` 退出 0，1 项通过，覆盖会话及技能页面和受控渲染。 |
| 2.1 | `.venv/bin/python -m pytest -q --disable-socket tests/api/test_mcp_teaching_service.py` 退出 0，4 项通过。MP-N01/MP-B01 核对目录 schema、请求 ID、202 通知、GET 405 与 DELETE；MP-F01 核对解析、无效报文、未知方法、非法参数及跨量纲错误；MP-F02/MP-F03 核对凭据、Origin、过期或缺失会话无执行，显式重连可用。 |
| 2.1 | `uv run --locked python scripts/check_pytest.py -q --tb=short tests/integration/test_compose.py -k MP_N01` 退出 0。隔离 Compose 内网调用两个工具，核对健康、未发布端口、无 MySQL/Qdrant/模型配置、MySQL 写语句计数不变及停机后主应用仍就绪。 |
| 2.1 | 从本机回环上的独立服务执行 `uv run --isolated --no-project --with 'mcp==1.13.1' --with 'pydantic==2.11.7' python tests/integration/mcp_sdk_check.py <回环端点>`。首跑仅固定 MCP 版本时，解析到的 Pydantic 已移除 SDK 所需内部接口，导入失败；加上兼容版本复测退出 0，官方客户端完成固定版本握手、发现、两项真实调用与跨量纲失败。依赖只装在独立验证环境。 |

`openspec-apply-change` 读取仓库规则、README、CLI 指定的规划和规格，严格校验并按验证勾选。2.1 使用 `project-add-tests`，按测试、安全和运维规范编写协议接口与隔离 Compose 用例。

### 评审结论

2.1 已取得独立运行证据。合并前人工评审和课程真人验收待执行。

### 迁移、宿主与会话交接

| 任务 | 实际验证 |
| --- | --- |
| 1.2 | `uv run --locked python scripts/check_pytest.py -q --tb=short tests/integration/test_compose.py -k tool_storage` 对应的 0011 用例通过。真实隔离 MySQL 核对同班外键、别名和提议唯一性、结果只增、重复升级、退到 0010 保留教学数据、恢复未完成凭据及到期后合成备份行重放。 |
| 2.2 | `tests/unit/test_tool_protocol.py` 核对只读 GET 固定路径、字段和媒体类型，登记地址检查、协议版本、请求 ID 及拒绝非批准解析。Compose 中实际 MCP JSON 与独立分包 POST SSE 夹具均通过，固定响应到达后即关闭读取。 |
| 3.1 | `test_CN_N01_CN_B01_CN_B02_CN_F01_CN_F02_CN_F03_CN_F04_connector_management` 通过，覆盖真实 MySQL 权限、跨班同构、重复发现、定义变化、迟到发现及凭据配置标记。Chrome 复验加载/空/正常/错误、键盘登记与审阅、390/1440 px。 |
| 3.2 | 根据用户确认扩展已有提案、设计、会话规格和 3.2 任务。练习票据使用服务端生成的题面与参数，绑定班级、本人、会话和消息幂等键，五分钟首次受理。隔离 Compose 和签名单位用例通过，覆盖旧客户端、候选交集、同键回放、票据篡改/移用/过期和提议参数改写。 |
| 3.3–3.4 | `test_TD_N01_TD_N02_TD_F07_AU_N01_controlled_tool_dialogue` 在隔离 Compose 验证真实发包、上限与重复提议、发送前断开、在途撤销、响应过滤、写前审计、教师最小字段、本人执行详情及同班/跨班隐私。 |
| 4.2–4.3 | 真实 TLS/NGINX/Gunicorn 观察成功、停机和断开三个分支的 `meta → delta → done`。容器内错误令牌返回 401、畸形 JSON 返回 400，主应用停机降级路径保持可用。四项自动化契约分别覆盖 CN-F03、CN-N01/AU-F05、TD-F02、AU-F02/AU-F03。真实课程网关与替身结果见[工程评测](../eval/2026-11-11-controlled-tools.md)。 |

首次连接管理测试夹具遗漏构造参数，补全后发现日志与末行标记同流输出，改为核对末行及秘密标记零命中后复测通过。浏览器故障注入首跑误拦截断开请求，缩小到列表读请求后通过。一次沙箱内进程探针因回环监听权限失败，获得隔离 Docker/回环执行权限后该组进程检查通过。首次完整门禁及接口套件触发历史认证夹具的精确表集合断言，追加 0011 五张表后保留原断言并复测。

`project-data-change` 对照数据库规范与冻结迁移，执行合成库兼容回退和恢复；`openspec-update-change` 按用户确认补齐练习用途设计，重新严格校验后交还实施流程；`project-prompt-eval` 对照 AI、测试和安全规范固定输入与提示，留前后对照和真实网关报告；`project-review` 对照评审规范核验实际范围、门禁、字典、页面及回退契约。

### Harness 七类自审

| 类别 | 对象、判据与实际结果 |
| --- | --- |
| 接口入口 | 对照 Flask 注册、同源 OpenAPI、教师工具和本人会话。脚本与 Chrome 核对状态码、写入来源、公开探针和页面四态。 |
| 业务逻辑 | 核对连接代次、审批指纹、票据范围、候选交集、许可与撤销。隔离真实依赖走通从发现到调用及停机后的安全降级。 |
| 数据库 | 核对组合外键、事务外网络、只增结果和只增迁移。真实 MySQL 验证并发断开、发包前写故障、唯一结果和到期恢复重放。 |
| 公共函数 | 复用应用授权、JSON 响应、幂等和 SSE 宿主，单元及 API 回归覆盖新旧调用。 |
| 错误处理 | 缺失与越权同构，畸形协议、无证据、上游超限与不可用只返回安全分类。协议与会话夹具均含错误断言。 |
| 安全 | 核对凭据、地址解析、返回字段、未开放测验边界与私人记录。只读投影、固定输入、撤销和依赖/制品门禁有实际用例。独立专项攻防矩阵归课末安全预检。 |
| 性能 | 真实代理三条成功样本首段中位 65.28 ms、P95 93.57 ms，总时中位 76.04 ms、P95 105.16 ms；工具中位 10 ms、P95 12 ms。此为合成模型的隔离测试，真人体验待最终验收。 |

### 2026-11-11 收尾复验

- `make check CHANGE=2026-11-04-add-controlled-mcp-tools` 退出 0。12 项严格 OpenSpec、格式、分层与场景映射、442 项单元/API、4 项进程和 5 项真实隔离集成通过。Gitleaks 报告零命中，锁文件与主应用/工具镜像扫描通过当前门禁。原始日志为本地 `make-check-final.log`。
- `uv run --locked python apitest/run_all.py` 退出 0，77 项通过。共享用例按路径和方法覆盖工具登记、连接、发现、审阅、断开、技能、练习、私有会话与审计。本地报告为本变更报告目录的 `apitest.html`。
- 设置 `CAMPUSCLAW_CHROMIUM` 后运行 `uv run --locked pytest -q --tb=short tests/browser/test_chapters.py` 退出 0，1 项浏览器套件通过。新增教师工具页主路径及同源 Swagger 登记、连接、发现、审阅、保存工具技能和断开，保留原有本人会话 SSE 试调。
- 收尾代理报告记录 3 次成功样本，握手发现 14.68 ms，工具中位和 P95 均为 12 ms，首段中位 74.53 ms、P95 89.23 ms，总时中位 86.43 ms、P95 102.99 ms。同一入口验证服务停机后出错、断开后被拒及资料问答继续。此结果使用合成模型，与真实课程网关单条烟测分开。

实现与自动化交接完成。人工代码评审、课程等价及同伴真人复验待执行。当前改动在本地变更分支。
