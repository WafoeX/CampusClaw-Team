# 2026-11-15 资产门禁红绿对照（4.3，SEC-06）

候选为 PR #34 的 GitHub 合并预览提交 `996ac8a3ee00c3a730ea848d371aedd8fe3e15fb`，对应评审分支提交 `4105e3f`。GitHub Actions 的真实隔离候选采集通过，应用和 MCP 镜像标签一致。预检 1 项通过，耗时 40.07 秒。两轮使用 Makefile 固定摘要的 Gitleaks、Trivy，同一份锁文件及 schema 2 漏洞库，库更新时间为 `2026-11-15T01:07:39.649898494Z`，两次均通过时效检查。[完整 CI 输出](https://github.com/WafoeX/CampusClaw-Team/actions/runs/43680135553/job/132708754412)

执行 `uv run --locked python scripts/check_security_control.py reports/security-control-source`，两轮调用同一 `make check-security`，作用于同一临时资产副本。红轮只在前端产物副本加入不可用的纯文本扫描标记。绿轮移除该标记再复跑。

| 扫描范围 | 红轮实际 | 绿轮实际 |
| --- | --- | --- |
| Git 历史（175 个可达提交） | 退出 0，命中 0 | 退出 0，命中 0 |
| 工作区 | 退出 0，命中 0 | 退出 0，命中 0 |
| 前端 | 退出 1，命中 1 | 退出 0，命中 0 |
| 日志 | 退出 0，命中 0 | 退出 0，命中 0 |
| 锁文件及开发依赖 | 退出 0，High 0、Critical 0 | 退出 0，High 0、Critical 0 |
| 应用镜像 | 退出 0，命中 0 | 退出 0，命中 0 |
| MCP 镜像 | 退出 0，命中 0 | 退出 0，命中 0 |
| Make 总退出码 | 2 | 0 |

红轮依赖审计照常完成。项目真实资产的历史扫描另见[扫描基线](security-baseline.md)。本次原始产物留在 CI 隔离工作区并随任务清理，原始文件与合成标记均不纳入 Git。人工评审待执行。

## 2026-11-16 第 10 课本地完整门禁演练（2.3 部分，L10-F03）

候选 `1c6e381`，使用本地工作树、回环启动测试和隔离 Docker。两轮执行 `make check CHANGE=2026-11-04-define-lesson-10-acceptance`。红轮只在本地临时把 `tests/test_startup.py` 的 `test_RT_B04_local_wsgi_process_reaches_probes_and_drains` 中 `/live` 预期状态改为 `201`。绿轮恢复至候选原有的 `200` 断言。

| 轮次 | 实测与退出 |
| --- | --- |
| 红轮 | `/live` 实际为 `200`，断言报告 `200 == 201` 失败。启动组 1 项失败、3 项通过，`check-test` 退出 1，`make check` 退出 2。后续扫描与集成子门禁未进入。 |
| 绿轮 | 核对测试文件与 Git 版本一致后复跑。12 项 OpenSpec、467 项单元/API、4 项启动检查通过。凭据零命中、锁定依赖 High/Critical 各为 0，8 项集成通过、用时 312.45 秒。`make check` 退出 0。 |

原始日志保存在本机临时目录。故障样本未提交，恢复是本地演练的一部分。代码分支的 PR 合并候选 `9663e3db` 已通过本轮[完整门禁](https://github.com/WafoeX/CampusClaw-Team/actions/runs/43815992640/job/133128056661)和[安全门禁](https://github.com/WafoeX/CampusClaw-Team/actions/runs/43815992640/job/133128056334)。临时远端红轮、构建和合入的实际拦截证据待补，2.3 仍未完成。

## 2026-11-17 第 10 课远端门禁阻断与恢复（2.3，L10-F03）

以 `467f206b92a35ea4aee87bda7910ef09fd57399f` 为基线。临时 PR #42 的 `e0bfdb4` 将 `tests/test_startup.py::test_RT_B04_local_wsgi_process_reaches_probes_and_drains` 的 `/live` 状态期望由 `200` 改为 `201`。随后 `67ca589` 恢复 `200`，文件树与基线完全一致。[演练提交](https://github.com/WafoeX/CampusClaw-Team/pull/42/commits)

| 轮次 | 本地 `make check CHANGE=2026-11-04-define-lesson-10-acceptance` | GitHub PR 事件 `make check` |
| --- | --- | --- |
| 红轮 | `/live` 实际返回 `200`。启动组 1 项失败、3 项通过，pytest 退出 1，Make 退出 2。 | 合并候选 `75d81a982f353db964d8ae34ac347d08164fdab8` 在同一断言处失败，Make 退出 2。独立安全门禁通过，候选镜像构建跳过。[红轮流水线](https://github.com/WafoeX/CampusClaw-Team/actions/runs/44030607570) |
| 绿轮 | 12 项 OpenSpec、474 项单元/API、4 项启动和 8 项真实依赖集成通过。凭据扫描零命中，锁定依赖 High/Critical 各为 0。集成耗时 399.91 秒。 | 合并候选 `6853d94e46109bf1f7b9562326bbd9e62bcf57eb` 的常规门禁、安全门禁和候选构建均通过。[绿轮流水线](https://github.com/WafoeX/CampusClaw-Team/actions/runs/44030820957) |

红轮时，GitHub 将失败的 `make check` 标记为 `Required`，显示 `Merging is blocked`，合入按钮禁用。该候选当时还缺一名同伴批准。GitHub 显示 `main` 受保护，必需检查只有 `make check`。安全门禁的主干必需检查由 2.1 单独跟踪。

绿轮完成后，仓库协作者评审并合入临时 PR，提交为 `db77d99aa7d318691d6fa48fd5e1f586d9598aa4`。红轮和恢复提交因此都进入主干历史。合入提交和演练基线的 Git 文件树均为 `223f15f8d031d8b6c2270d1865c88b82dddd4445`。本地日志保留在临时目录。[已合入的演练 PR](https://github.com/WafoeX/CampusClaw-Team/pull/42)
