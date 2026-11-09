# 异步教学工作流：人工数据与规则评分阶段

## 变更说明

依据[提案](../../openspec/changes/2026-11-04-add-async-teaching-workflows/proposal.md)、[设计](../../openspec/changes/2026-11-04-add-async-teaching-workflows/design.md)及[任务](../../openspec/changes/2026-11-04-add-async-teaching-workflows/tasks.md)，本 PR 交付人工单选/判断题的版本与审核、测验草稿与发布快照、冻结学生名单、学生草稿、一次正式提交、MySQL 事务内规则评分、答案开放门控及师生页面。0010 迁移新建 11 张表；对已有资料来源追加同班组合索引。资料删除会在同一事务去除教学来源指针。

本阶段没有接入 AI 候选题、Kafka、错题和看板，也没有把课程要求的异步作业提交 202 或教师改分声明为已实现。2.1–2.3 的人工确定性路径可供下游开发；涉及候选题、MCP、课堂等价或正式人工验收的情形仍按原任务推进。

## 技能与读取依据

本组调用 `openspec-apply-change`、`project-data-change`、`project-add-tests`、`project-review`，输入为当前变更的 proposal/design/specs/tasks、已合入骨架与认证基线、题目/测验数据设计和合成 A/B 班账号；读取 AGENTS.md、README、规范 01–05/07/08、数据字典、现有迁移与回归入口。动作是逐组实现、追加迁移/字典、补 API 与真实 MySQL 回归、核对场景和交付边界。结果与未覆盖项以本页实际记录为准；技能调用不代替人工批准。

## 验证记录

| 对象与手段 | 判据及实际结果 | 状态 |
| --- | --- | --- |
| OpenSpec | 项目所用 CLI 1.13.0 对 `2026-11-04-add-async-teaching-workflows --strict` 退出 0；提示现有 `material-indexing` 增量归档前需上游主规格，当前不归档 | 通过，归档前置未完成 |
| 代码格式、静态和映射 | 本机临时 Python 3.13 环境运行 `ruff format --check`、`ruff check`、`scripts/check_layout.py`、`scripts/scenario_trace.py`，均退出 0；160 个 Python 文件已符合格式 | 通过 |
| 单元、API、启动 | `make check` 中 `tests/unit tests/api` 430 passed、`tests/test_startup.py` 4 passed | 通过 |
| MySQL 人工闭环 | 一次性 `campusclaw_test_` MySQL 8.4 隔离库执行 `tests/integration/teaching_runtime.py`，输出 `TEACHING_RUNTIME_OK`；覆盖迁移、A/B 班角色与资源、版本审核、发布快照/名单、草稿重登读取、正式 201/同键重放及截止后重放、评分、截止、答案开放、名单锁并发、八学生集中提交、同人并发及故障回滚 | 通过 |
| 迁移回退 | 首次复测在降级时遇到 MySQL 1553：资料组合索引仍被上游外键使用。修正为降级只删除本组 11 表并保留索引；隔离库复测降级保留账号、重升两次成功 | 失败后修复并复测通过 |
| 浏览器 | `python3 tests/browser/run_teaching.py` 启动一次性 HTTPS 应用与真实 Chromium，执行 `tests/browser/teaching.mjs`；首轮草稿刷新恢复通过，退出登录后的自动跳转断言超时；改为显式登录页导航并确认会话 401 后复测输出 `TEACHING_BROWSER_OK` 和 `TEACHING_BROWSER_RUNTIME_OK`。再经 `scripts/check_pytest.py -q tests/browser/test_teaching.py` 得 1 passed | 失败后修复并复测通过 |
| 完整项目门禁 | 首轮工具容器缺 Git，补齐后规范/静态/434 项/秘密/依赖扫描通过，但 Compose 就绪检查因容器无法访问宿主回环端口而超时；改用本机临时 Python 3.13 环境原样执行 `make check`，最终退出 0。含 OpenSpec 12/12、静态、434 项、Gitleaks 无泄漏、Trivy 锁文件和应用镜像均 0 高危/严重漏洞、Compose 集成 1 passed | 环境失败后复测通过 |

以上数据库使用随机合成账号及密码；临时库和容器均在每轮结束时删除。应用镜像的构建修订在未提交代码测试时只是合成测试标识，不冒充 Git 提交。生产备份恢复、真实课堂试用、课程等价和同伴评审未执行。

## Harness 七类自审

| 类别 | 手段、对象与判据 | 结果及证据 |
| --- | --- | --- |
| 接口入口 | 路由/输入与师生投影核对，API 测 400/401/403/404/201 | API 430 项及 `tests/api/test_teaching.py` |
| 业务逻辑 | 题目编辑失审、发布冻结、草稿修订、正式一次提交及开放时点 | 真实 MySQL 脚本通过；课程教学意图待人工确认 |
| 数据库 | 0010 组合外键、唯一约束、事务回滚、参与行锁和隔离降级重升 | 初次降级失败后修复，复测 `TEACHING_RUNTIME_OK` |
| 公共函数 | 复用认证、资料错误和响应契约；静态及单元回归 | 434 项通过 |
| 错误处理 | 不存在/跨班同构、非法参数、发布及评分故障注入 | API 与 MySQL 脚本通过 |
| 安全 | 服务端身份重验、学生答案门控、来源删除去内容化自审；脚本覆盖基础越权与泄露投影 | 已执行基础断言；独立攻击矩阵与全资产扫描归课末安全预检 |
| 性能 | 锁定某学生参与行时另一学生可在 2 秒内提交；八学生集中提交均得到 201 且各一份评分；单次隔离时延不是容量结论 | 脚本断言通过；正式负载测量和真实体验待 5.2/最终验收 |

## 评审结论

当前结果支持人工确定性教学闭环作为开发基线，2.1 和 2.3 已完成自动化判据。`1.1/1.2` 任务还包括候选、Kafka、索引等后续数据准备，不能因本阶段迁移通过而整项勾选；`2.2` 的普通会话及 MCP 等未来泄露旁路依赖后续服务，故不勾选整项。人工代码评审、课程等价与最终验收由相应任务和 PR 评审人完成，助手未自填批准。
