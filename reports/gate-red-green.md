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
