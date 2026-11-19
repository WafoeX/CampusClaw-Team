# 第 9 课安全修复返工记录

## 配置写入客户端复验（3.2）

已归档的 3.2 完整集成首轮出现真实返工。配置写入接口已要求一次性令牌，受控工具代理的测试收尾仍用旧客户端恢复助手配置，收到 403。排查沿配置写入调用链检查测试收尾，再对照 OpenAPI 的 `operationId` 和签发接口，定位到漏取令牌的调用。修正时让恢复路径与其他集成客户端共用配置写入辅助方法。

修正后，`uv run --locked python scripts/check_pytest.py -q --tb=short tests/integration/test_compose.py` 退出 0，8 项通过，复跑用时 282.15 秒。定位和实际改动分别耗时未记录，现有证据不足以比较所有返工的成本。见[修复前后记录](../docs/changes/2026-11-04-remediate-security-findings.md#2026-11-15-配置写入-csrf-防护32sr-f04-与-sr-f09)和[修复提交](https://github.com/WafoeX/CampusClaw-Team/commit/ae2655e)。

可执行改法是配置写入契约变更时，按 OpenAPI 的 `operationId` 对照测试中所有调用，包含收尾恢复路径。先跑受影响入口，再跑包含收尾的完整 Compose 集成。

## Git worktree 凭据扫描（6.1）

另一次已验证返工发生在关联工作树。容器找不到工作树引用的 Git 路径，内部 Git 退出 128，Gitleaks 报告扫描 0 条提交。脚本改为扫描可在容器内独立读取的历史镜像，检查镜像和本地 Git 提交计数相同。再次运行 `make check-secrets` 退出 0，Gitleaks 报告扫描 130 条提交，历史与工作区凭据命中均为零。浅克隆复跑在进入扫描器前退出 1。定位、改动耗时未记录。见[实测记录](../docs/changes/2026-11-04-remediate-security-findings.md#2026-11-15-修复-git-worktree-凭据扫描61-部分)和[修复提交](https://github.com/WafoeX/CampusClaw-Team/commit/2b8e438)。

## 完整门禁本地重跑（6.1）

在 `8920297` 加四步走查改动的工作区重跑 `make check CHANGE=2026-11-04-remediate-security-findings`，Trivy 在更新阶段约 8 分 28 秒后返回 `unexpected EOF`。Make 退出 2，未进入集成子门禁。此耗时为镜像源下载等待，当前候选的锁定依赖结论由同提交 CI 复核。独立 Compose 定向回归 2 项通过，不能替代完整门禁。见[门禁记录](../docs/changes/2026-11-04-remediate-security-findings.md#2026-11-15-修复索引与返工取证6263-部分)。

## 浏览器失败输出复核（SEC-05）

实际脚本输出复核发现，详情标题断言变红时，浏览器运行器的异常堆栈带有一次性测试口令。以同一标题故障和同一运行命令验证，改用子进程环境传递口令后，命令仍退出 1 并保留断言差异，合成口令模式命中 0。恢复标题后同一命令通过。诊断和修复耗时未单独记录。与上文 Git worktree 凭据扫描是两次实际发现与处置，均为技术复核，跨机器独立同伴复验仍待最终验收。见[实测记录](../docs/changes/2026-11-04-remediate-security-findings.md#2026-11-16-浏览器测试口令脱敏sec-0563-取证)。

## SEC-08 第四步候选解析（5.2）

SEC-08 实验首轮把工具登记、连接与批准放在第一个应用实例，为注册夹具路由再新建应用后直接流式提问，第五轮隔离门禁在最后不变量断言处变红：第四步 meta 显示所选工具在规划前就被 `rejected/unavailable`，规划器从未执行。定位沿 `sessions.py` 的候选构造、`tool_connectors.candidates` 与 `resolve` 逐一核对，根因是候选解析依赖当前进程内已建立的 MCP 连接会话，新建应用实例的连接注册表为空，证据非空也拿不到候选。修复为在新应用实例上重新建立一次 MCP 连接。复跑 `-k sec08` 退出 0，1 项通过、29.80 秒；真实网关轮 47.61 秒。此前各轮机械故障与本次定位的累计耗时未单独记录。见[实验报告](sec08-experiment.md)与[修复提交](https://github.com/WafoeX/CampusClaw-Team/commit/19203d0)。

可执行改法是：运行器跨应用实例复用连接时，先确认工具候选解析所依赖的连接会话属于当前实例，再开始流式提问；证据行先于断言输出，失败轮仍可取证。

## 场景映射门禁失效（6.1）

5.2 勾选后，`tests/scenario-map.json` 中 PSC-B02 仍以“待验证”绑定已完成任务，完整 `make check` 在静态阶段退出 2，错误指向待验证场景必须绑定未完成任务。定位后将该场景改绑四步实验测试并提交，复跑完整 `make check` 退出 0；首次失败日志 14:04，复跑完成 14:15，集成 12 项、462.19 秒。见[回归记录](../docs/changes/2026-11-04-remediate-security-findings.md#2026-11-19-同一候选完整回归61sr-n03sr-f14)与[修复提交](https://github.com/WafoeX/CampusClaw-Team/commit/4743507)。

可执行改法是：勾选任务前先运行 `uv run --locked python scripts/scenario_trace.py` 核对引用该任务的待验证场景绑定。
