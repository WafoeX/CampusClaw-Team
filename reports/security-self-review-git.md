# 安全技术自审一：关联工作树历史扫描

| 项目 | 实际记录 |
| --- | --- |
| 手段 | 比较 `make check-secrets` 的内部 Git、扫描器退出状态与实际扫描提交数，另用临时浅克隆验证前置拒绝。 |
| 对象 | `ae2655e` 关联工作树的历史与工作区扫描，规则 SEC-10、TEST-08、REV-05。 |
| 判据 | 扫描器须读取本地可达历史。Git 读失败或扫描为空时，扫描器的零命中不能作为历史通过证据。 |
| 发现 | 容器内 Git 无法解析宿主主仓库路径，Git 退出 128，Gitleaks 报告扫描 0 条。 |
| 处置与复测 | 使用临时镜像并核对本地 Git 与镜像的可达提交数。复跑 `make check-secrets` 退出 0，Gitleaks 报告扫描 130 条提交，历史与工作区零命中。浅克隆在扫描前退出 1。 |

执行环境为本地关联工作树和隔离 Docker 扫描容器，结果取自变更中的原始复验记录。人工独立复验待项目最终验收。见[修复及结果](../docs/changes/2026-11-04-remediate-security-findings.md#2026-11-15-修复-git-worktree-凭据扫描61-部分)和[修复提交](https://github.com/WafoeX/CampusClaw-Team/commit/2b8e438)。
