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
