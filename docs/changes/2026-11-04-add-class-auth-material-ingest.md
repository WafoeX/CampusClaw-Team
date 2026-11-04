# 班级认证与资料入库证据

## 变更说明

2026-11-04，使用 `openspec-apply-change` 核对任务 1.1 的实施前置项。输入为用户指定的变更短名和前端示例，按 CLI 匹配到完整变更名 `2026-11-04-add-class-auth-material-ingest`。读取 AGENTS、README、本变更的提案、设计、增量规格和任务，以及相关产品、后端、安全、测试、运维、数据与评审规范。核对工作区骨架授权实现、上游 AC-01/AC-N03 及[第 7 课运行和门禁记录](2026-11-04-add-skeleton.md)。本轮交付为实施前核对记录。

## 验证记录

| 项目 | 实际结果 |
| --- | --- |
| OpenSpec | `openspec validate 2026-11-04-add-class-auth-material-ingest --strict` 退出 0。Apply 指令返回 `spec-driven`、`ready`、0/10。 |
| 主干保护 | 只读查询 GitHub 分支接口。远程 `main` 为 `e05e8e0a645a5b963c5cdcd02f53baac1e23b0e8`，`protected=true`，`make check` 为必需检查，`enforcement_level=everyone`。 |
| 骨架启动与门禁 | 核对既有证据中的隔离主干冷启动、MySQL/Qdrant 同时就绪、`make check` 通过及保护拒绝记录。本轮未重跑 Compose 或完整门禁。 |
| AC-01 和 AC-N03 | 现有骨架允许按端点、精确路径和方法声明公开例外。首次通过 uv 启动测试因默认缓存权限失败。随后用 `.venv/bin/python -m pytest --disable-socket -q tests/api/test_access.py` 复测，退出 0，13 项通过，包含公开样本的别名与方法隔离。 |
| 示例与课件 | Web 未能打开[前端示例](https://devops.hello1023.com/demo-src/dist/index.html)、[认证设计](https://devops.hello1023.com/课件/第3课-课件-认证授权与知识库入库/pages/auth.html)及[实践与验收](https://devops.hello1023.com/课件/第3课-课件-认证授权与知识库入库/pages/apply.html)。浏览器打开前端示例超时，本机请求未能解析域名。 |

### 待课程评审核对的方案

| Cookie 示例语义 | 可撤销 Bearer 的拟议映射 |
| --- | --- |
| 登录换发 | 原子替换当前会话，旧令牌失效。 |
| 注销 | 撤销数据库当前会话，后续请求重新鉴权。 |
| 当前数据库身份 | 每次受保护请求联查当前账号和班级，从数据库确定角色和班级。 |
| 防账号枚举 | 错误口令、停用账号和未知账号返回同构结果，均进行口令哈希验证。 |

浏览器通过同源 Fetch 显式携带 Authorization。令牌只保存在当前页面内存，刷新后重新登录。课件三项拟验收结果按当前提案整理，均待实际验证与课程确认。

1. 匿名访问资料接口返回 401，响应无资料内容。
2. 跨班详情和下载与不存在返回相同业务结果，均无附件头。
3. 学生上传返回 403，两张资料表和文件目录保持原样。

登录业务入口尚未实现。内嵌启动资源、登录例外的实际路由、页面直访或刷新跳转、到期后重新登录、合法同源返回、非法目标拒绝和业务 API 401 待实现后验证。

## 评审结论

任务 1.1 的技术前置核对已进行，任务仍保持未勾选。当前缺少课程评审人、日期、Bearer 方案的实际接受结论及出处。设计要求在编码前完成此项确认。若课程评审要求原样使用 Cookie，应先修订方案、规格和任务并重新严格校验。当前 0/10，尚未开始应用编码。

## 2026-11-04 项目改用 Cookie 会话

用户明确项目采用 Cookie 登录验证，并提供两张界面截图。使用 `openspec-update-change` 读取 CLI 定位的四份规划文件和各制品规则，修订提案、设计、增量规格和任务。旧记录中的 Bearer 等价方案停止采用。截图用于双栏登录、班级顶栏、侧栏及卡片样式。截图中一键选择预置账号和模拟数据属于演示内容，正式登录要求验证口令。

同源写入校验覆盖登录和受保护写入，拒绝来源缺失或不匹配的浏览器请求。会话凭据限 HTTPS、主机范围及 HttpOnly Cookie，服务器仅存摘要并继续按当前身份授权。SEC-09 的内存访问令牌约束适用于 JavaScript 持有的访问令牌，本项目浏览器会话凭据边界变更仍需人工安全复核。评审责任为小组安全评审人，姓名和结论待登记。评审前不得将方案视为批准或上线。变更认证传输方式或增加跨源客户端时重新评估。第 5 课流式及第 6 课宿主接口文档仍有 Bearer 假设，按其变更边界在实施前协调，独立 MCP 服务的机器凭据另属其自身契约。

OpenSpec 严格校验退出 0，使用本次已核对的 AC-N03 回归、骨架启动和主干保护证据完成任务 1.1。业务登录和浏览器走查继续由任务 1.3 验收，课件三项结果在授权、上传与下载可运行后留证。用户选定 Cookie 是本项目设计决定，课程评审仍待发生。

## 认证表迁移与合成种子

使用 `project-data-change`，在隔离开发环境读数据、后端、安全、运维规范及现有 MySQL/Compose 装配，新增集中数据字典，登记账号及会话归属、去内容审计、留存和备份恢复。新增 Alembic 版本迁移、认证适配器与种子命令。数据库降级及种子命令限明确登记的合成测试库。分层检查仅在适配器的迁移目录准许 Alembic，其他限制保留。

- `uv lock --python .venv/bin/python` 退出 0，锁定 SQLAlchemy 2.0.57、Alembic 1.20.1 及其传递依赖。此前读取 PyPI 项目 JSON 的请求超时，随后由 uv 解析成功。 `uv sync --locked` 退出 0。
- `.venv/bin/python -m pytest -q --tb=short tests/integration/test_compose.py` 退出 0，1 项通过，用时 16.68 秒。在新建隔离 Compose 项目内确认真实 MySQL/Qdrant 就绪，核对无业务表的骨架库、升级和重跑、会话外键和主键、A/B 两班四账号、修改角色后重跑不覆盖角色及口令哈希、两次降级和重新升级，夹具清理通过。
- `.venv/bin/python -m pytest --disable-socket -q tests/unit tests/api` 退出 0，52 项通过。Ruff 格式及检查、分层检查、OpenSpec 严格校验和差异检查通过。本轮尚未跑带扫描的完整门禁。
- SQLAlchemy 和 Alembic 用于事务仓储及版本迁移，直接依赖均为 MIT。传递依赖和制品扫描、人工安全复核，以及部署前的学期和实名责任登记仍待完成。

## Cookie 登录候选与交付自检

使用 `project-review` 对照本变更四份规划、任务、AGENTS、评审规范及认证相关规则，核对浏览器、数据库和门禁结果。当前候选提供账号口令登录、当前会话、并发换发、注销及停用/改密撤销的数据操作。采用截图的深红品牌区和浅色表单，窄屏切换为单列。HTTPS 源由 `APP_PUBLIC_ORIGIN` 显式配置；留空只启用骨架装配，便于保留骨架启动契约。README 和页面清单已同步。

| 检查 | 实际结果 |
| --- | --- |
| 隔离 Compose 与事务 | `.venv/bin/python -m pytest -q --tb=short tests/integration/test_compose.py` 退出 0。随后在完整门禁复测，覆盖并发登录只保留最后会话、迟到旧 Cookie 注销失败、跨源写拒绝、合法注销、改密与停用撤销、换发事务插入失败后原会话保留、到期前一微秒成功及恰好到期拒绝。 |
| 本机 WSGI 回归 | 默认沙箱执行进程测试时，回环套接字绑定失败，3 项通过、1 项环境错误。获准在完整门禁环境复测后，4 项通过。 |
| 完整门禁 | `make check CHANGE=2026-11-04-add-class-auth-material-ingest` 退出 0。8 个 OpenSpec 变更通过严格校验，本变更单独校验通过。Ruff、分层、机密和依赖/镜像漏洞扫描通过。断网单元/API 52 项、进程测试 4 项、真实 Compose 集成 1 项通过。下游两个尚未归档的目标规格仍有归档顺序提示。 |
| 真实浏览器 | 本机临时 HTTPS、独立 MySQL 8.4 和独立无头 Chrome 配置下，使用合成账号验证登录、刷新保留会话、退出后 API 401、非法外链返回目标拒绝、Cookie 三项安全属性及不可从 JavaScript 读取。核对 1440×900 双栏和 390×844 单列，截图在本机忽略目录 `reports/2026-11-04-add-class-auth-material-ingest/`。 |
| 依赖许可 | SQLAlchemy、Alembic、Mako 为 MIT。传递依赖 typing-extensions 为 PSF-2.0；greenlet 为 MIT AND PSF-2.0，并按锁文件的环境标记安装。两项含 PSF-2.0 的依赖需由小组按 SEC-16 逐项审阅，尚未批准。[typing-extensions 发布元数据](https://pypi.org/project/typing-extensions/4.16.0/) · [greenlet 发布元数据](https://pypi.org/project/greenlet/3.5.6/) |

按 REV-01/03/05/08，任务 1.1 和 1.2 已勾选，任务 1.3 仍开放。当前浏览器可在登录页核对会话身份。资料页和工作台接入后还须复验受保护页面直访、会话到期后重登录返回，以及课件三项业务验收。会话清理的定时执行、课程确认、依赖许可、认证安全与约束文件变更均待人工复核。真实 MySQL 测试只在隔离环境执行，未触及共享数据库。项目无 AI 行为改动，本轮模型评测不适用。
