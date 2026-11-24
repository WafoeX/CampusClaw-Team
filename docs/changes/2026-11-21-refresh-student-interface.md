# 中学生界面主题更新

## 变更说明

基于 `dc9aec1`，将登录、班级、教学及接口试调页面统一到靛蓝与薄荷绿主题。登录页复用共用令牌和控件，班级及教学页面突出当前导航与页面标题。导航在窄屏使用网格，正文走单列。现有路由、表单标识、状态文案与服务端授权沿用原契约。

使用 `openspec-propose` 与 `openspec-apply-change` 整理并实施提案、设计、六条场景和两项任务。使用 `project-add-tests` 扩充真实 Chromium 教学回归，使用 `project-review` 对照 AGENTS、README、产品设计、测试、安全、评审规范及差异完成自检。

## 验证记录

| 对象与命令 | 实际结果 |
| --- | --- |
| 编码前 `openspec validate 2026-11-21-refresh-student-interface --strict` | 退出 0。GitHub 分支 API 返回 `main protected: True`。 |
| `make check-static CHANGE=2026-11-21-refresh-student-interface` | 退出 0。OpenSpec 14 项、Ruff、分层、六条场景追溯及 13 个接口清单入口通过。新旧浏览器模块的 `node --check` 和 `git diff --check` 通过。 |
| `uv run --locked python scripts/check_pytest.py -q --tb=short tests/browser/test_teaching.py` | 退出 0，1 项通过，39.03 秒。隔离 HTTPS、真实 MySQL 和 Chromium。登录及学习页核对 1440／390 像素、焦点轮廓、正文对比度 4.5:1、当前导航、错误、空状态、503 重试和学生工作台 403。两项探针和既有教学浏览器契约通过。 |
| 设置 `CAMPUSCLAW_CHROMIUM` 后运行 `uv run --locked python scripts/check_pytest.py -q --tb=short tests/browser/test_chapters.py` | 退出 0，1 项通过，31.65 秒。覆盖章节、检索、问答、AI 应用、会话、反馈、工具及接口试调，复跑两档宽度、键盘和四状态。 |
| 本机 Chrome 预览 | 登录双栏及手机单列、桌面资料页和手机问答页的四份 PNG 已检查。使用真实模板与合成页面数据，预览位于被忽略的 `reports/student-theme-preview/`。 |
| `make check CHANGE=2026-11-21-refresh-student-interface` | 退出 0。静态检查、515 项单元/API、4 项启动、Gitleaks、锁定依赖扫描和 13 项集成及浏览器检查均通过。集成段用时 359.18 秒，锁定依赖高危和严重均为 0。 |
| `make check-security SECURITY_ASSETS=reports/theme-security-assets` | 临时本地快照 `e94d9f7` 先跑隔离 `security_precheck` 1 项通过，再执行现有门禁，退出 0。历史、工作区、前端、日志和两个镜像归档的凭据扫描均为 0，锁定依赖 High/Critical 均为 0。快照只用于满足候选镜像输入需提交的取证要求。 |
| 隔离焦点故障及恢复 | 在临时快照移除键盘焦点轮廓，教学浏览器回归在 `tabFromPage` 明确失败，退出 1。恢复原样式并确认快照差异为空后复跑，退出 0，1 项通过，24.44 秒。 |

场景 SIT-N01/B01、SIT-F01–F04 映射到教学浏览器 pytest 入口，具体浏览器断言位于 `tests/browser/student_theme.mjs`。颜色和宽度仅对实际测试的控件与页面取证。

## 评审结论

| Harness 类别 | 手段、判据和结果 |
| --- | --- |
| 接口入口 | 对照模板差异和页面清单，原入口、表单 ID、导航权限和双探针通过浏览器回归。 |
| 业务逻辑 | 复跑测验草稿、交卷与答案门控，主题下的禁用和隐藏行为按原断言通过。 |
| 数据库 | 未改数据、查询或迁移，专项不适用；真实 MySQL 已用于隔离浏览器回归。 |
| 公共函数 | 统一 Jinja 样式入口，登录和班级页面的主按钮、焦点和状态对比通过浏览器检查。 |
| 错误处理 | 错误口令与检索 503 仍显示文字和恢复操作，检索空状态不生成虚构结果。 |
| 安全 | 保留 CSP nonce、原生控件和角色判定；学生直访工作台返回 403，隔离安全门禁通过。 |
| 性能 | 模板差异核对无新增外部请求或运行依赖；性能专项压测不适用。 |

正式中学生试用、课程人工验收和同伴评审待执行。OpenSpec、页面视觉基线和场景清单待人工复核。
