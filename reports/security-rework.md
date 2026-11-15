# 第 9 课安全修复返工记录

## 配置写入客户端复验（3.2）

已归档的 3.2 完整集成首轮出现真实返工。配置写入接口已要求一次性令牌，受控工具代理的测试收尾仍用旧客户端恢复助手配置，收到 403。排查沿配置写入调用链检查测试收尾，再对照 OpenAPI 的 `operationId` 和签发接口，定位到漏取令牌的调用。修正时让恢复路径与其他集成客户端共用配置写入辅助方法。

修正后，`uv run --locked python scripts/check_pytest.py -q --tb=short tests/integration/test_compose.py` 退出 0，8 项通过，复跑用时 282.15 秒。定位和实际改动分别耗时未记录，现有证据不足以比较所有返工的成本。见[修复前后记录](../docs/changes/2026-11-04-remediate-security-findings.md#2026-11-15-配置写入-csrf-防护32sr-f04-与-sr-f09)和[修复提交](https://github.com/WafoeX/CampusClaw-Team/commit/ae2655e)。

可执行改法是配置写入契约变更时，按 OpenAPI 的 `operationId` 对照测试中所有调用，包含收尾恢复路径。先跑受影响入口，再跑包含收尾的完整 Compose 集成。

## Git worktree 凭据扫描（6.1）

另一次已验证返工发生在关联工作树。容器找不到工作树引用的 Git 路径，内部 Git 退出 128，Gitleaks 报告扫描 0 条提交。脚本改为扫描可在容器内独立读取的历史镜像，检查镜像和本地 Git 提交计数相同。再次运行 `make check-secrets` 退出 0，Gitleaks 报告扫描 130 条提交，历史与工作区凭据命中均为零。浅克隆复跑在进入扫描器前退出 1。定位、改动耗时未记录。见[实测记录](../docs/changes/2026-11-04-remediate-security-findings.md#2026-11-15-修复-git-worktree-凭据扫描61-部分)和[修复提交](https://github.com/WafoeX/CampusClaw-Team/commit/2b8e438)。

## 完整门禁本地重跑（6.1）

在 `8920297` 加四步走查改动的工作区重跑 `make check CHANGE=2026-11-04-remediate-security-findings`，Trivy 在更新阶段约 8 分 28 秒后返回 `unexpected EOF`。Make 退出 2，未进入集成子门禁。此耗时为镜像源下载等待，当前候选的锁定依赖结论由同提交 CI 复核。独立 Compose 定向回归 2 项通过，不能替代完整门禁。见[门禁记录](../docs/changes/2026-11-04-remediate-security-findings.md#2026-11-15-修复索引与返工取证6263-部分)。
