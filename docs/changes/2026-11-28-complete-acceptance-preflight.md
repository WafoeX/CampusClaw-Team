# 2026-11-28 验收冻结前技术收口

## 变更说明

本变更以已合并 PR #78 的主干 `e2ada0d` 为起点，完成第 10 课任务 4.3 的剩余技术缺口。正式交卷受理、重试和终态现在写入去内容操作审计，教师可按任务 ID 查询候选题或正式交卷任务；跨班与不存在任务均返回空集合。确定性评分的 `skill_id`、`total_tokens` 如实为空，审计不保存作答、答案、幂等键或租约。

调用技能：`openspec-apply-change`、`project-add-tests`、`project-review`。输入为变更 `2026-11-04-define-lesson-10-acceptance`、任务 4.3 和本分支文件清单；读取 AGENTS.md、README、变更 proposal/design/spec/tasks、安全规范、测试规范、评审规范及既有验收报告。动作包括实现审计事务、补接口/单元/真实浏览器回归、校准验收状态并执行交付自检。

## 场景与七类核查

| 类别 | 手段、对象与判据 | 结果 |
| --- | --- | --- |
| 接口入口 | 核对正式交卷携带服务端请求 ID，审计 `job_id` 同时支持候选题与正式交卷；浏览器验证本班查询 | 通过 |
| 业务逻辑 | 核对受理、失败重试、成功/失败终态；终态审计与状态转换处于同一事务 | 通过 |
| 数据库 | 使用既有审计表，不新增迁移；隔离 MySQL 验证任务 ID 关联和跨班空结果 | 通过 |
| 公共函数 | 复用 `append_audit`、`projection` 与操作审计仓储，不复制七列投影 | 通过 |
| 错误处理 | 资源变化写失败终态；丢失租约不伪造成功审计 | 通过 |
| 安全 | 审计仅含元数据；检查无作答、答案和幂等键，跨班与不存在同为空；同提交安全资产门禁复测 | 通过；真人及独立复核未执行 |
| 性能 | 受理增加同事务单行审计，使用既有班级/资源索引；本变更不改变已完成的压测口径 | 不适用专项压测，理由为无查询形态或索引变更 |

场景映射：L10-N07 覆盖 390px HTTPS 登录、正式交卷 `202`、`pending → running → succeeded`、同任务受理/终态七列审计；L10-F07 覆盖未登记来源拒绝、跨班资源 404 及跨班审计空结果；L10-F08 只完成反馈字段结构，三名真实用户仍归最终验收 4.5。

## 验证记录

| 命令 | 实际结果 |
| --- | --- |
| `uv run --locked pytest -q tests/unit/test_submission_jobs.py tests/api/test_teaching.py tests/api/test_operation_audit.py` | 退出 0，48 项通过，2.84 秒 |
| `uv run --locked ruff check app tests`、`uv run --locked ruff format --check app tests` | 均退出 0 |
| `uv run --locked pytest -q tests/browser/test_teaching.py` | 退出 0，1 项通过，148.93 秒；真实 Chromium、HTTPS 和隔离 MySQL |
| 默认来源生成安全资产 | 未进入安全断言，连续三次拉取锁定 MySQL 镜像时 `public.ecr.aws` TLS 握手超时，退出非零 |
| `CAMPUSCLAW_TEST_DOCKER_MIRROR=docker.m.daocloud.io CAMPUSCLAW_SECURITY_ASSETS=reports/security-assets-20261128-58cb77c-retry uv run --locked python scripts/check_pytest.py -q tests/integration/test_compose.py -k security_precheck` | 退出 0，1 项通过、13 项未选择，39.13 秒；镜像摘要不变 |
| 首次 `make check-security ... SECURITY_CANDIDATE=58cb77c4f528b6f6aed7c3208c7a643075693915` | 退出 2；秘密和镜像分项通过，漏洞库已于 2026-11-26 过期，依赖扫描工具未完成，按失败保留 |
| 更新漏洞库后重跑同一 `make check-security` | 退出 0；历史、工作区、前端、日志、应用镜像和 MCP 镜像秘密均为 0，锁依赖 High/Critical 为 0；数据库更新时间 `2026-11-28T01:04:49.651015735Z` |
| 首次完整 `make check CHANGE=2026-11-04-define-lesson-10-acceptance` | 静态、602 项单元/API、4 项启动、秘密与依赖扫描通过；真实集成 16 通过、1 失败，806.14 秒。拒绝预算用例的观察器把新增的合法正式交卷终态审计误计为拒绝审计写入尝试；数据库拒绝审计行数、合法评分和其余断言均已通过 |

针对上述失败，观察器改为只统计编译参数中 `outcome=denied` 的 INSERT，继续保留拒绝写入尝试必须精确等于 3 的断言，未降低预算、并发或教学副作用判据。定向复测退出 0，1 项通过、13 项未选择，26.26 秒。最终提交 `04ab504` 完整重跑 `make check CHANGE=2026-11-04-define-lesson-10-acceptance` 退出 0：静态与规约检查通过，602 项单元/API、4 项启动、17 项真实集成/浏览器通过，集成阶段 809.99 秒；秘密扫描无发现，锁依赖和候选镜像 High/Critical 为 0。

原始安全资产位于被忽略的 `reports/security-assets-20261128-58cb77c-retry/`，只保留本页脱敏摘要。完整 `make check` 与远端双门禁在分支收尾执行，未执行前不写通过。

## 评审结论

任务 4.3 的自动化技术条件满足，OpenSpec 进度为 9/14。任务 4.1 仍缺正式阈值确认、负责人和真实收件通道，因而 5.1 候选冻结尚未完成。真实模型、三名使用者、另一成员独立复核、课程差异结论与人工批准均未执行。本记录是助手自检，不代表人工评审或合并批准。
