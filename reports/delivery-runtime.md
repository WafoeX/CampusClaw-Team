# 第 10 课交付运行证据

## 本地候选构建与启动

2026-11-16，对源码 `a0c2a5afd5869ee19127392c294f32669d726e9c` 的 Dockerfile、应用、MCP 和锁文件运行 `uv run --locked python -m scripts.build_candidate "$(git rev-parse HEAD)"`，退出 0。使用本地 Docker Desktop 与 Buildx，Compose 从本次构建的标签加载，两个运行容器的镜像 ID 均和构建结果相同。

| 服务 | 镜像标签 | Buildx 输出摘要 |
| --- | --- | --- |
| 应用 | `campusclaw-skeleton:a0c2a5afd5869ee19127392c294f32669d726e9c` | `sha256:6f733c70d5add479eecb589e8f0af780d90dc3dd95e7cf46c6f9065d80abc0b5` |
| MCP | `campusclaw-mcp:a0c2a5afd5869ee19127392c294f32669d726e9c` | `sha256:1749150486fd70d8813b574e6b0b3a17a5898a2f2dae92eaa60ac88c4e40c8df` |

`/live` 和 `/health` 的 GET、HEAD 均为 200。`/health` 的 MySQL、Qdrant 均为 `ready`，运行版本为上述完整提交。独立 MCP 的容器健康探针通过。隔离容器和卷清理完成。

首次以宿主 Python 3.9 直接运行时，探针辅助模块所用的 `datetime.UTC` 无法导入，复跑改用仓库锁定的 Python 3.13。Buildx 首轮构建成功，但 Docker Desktop 的容器存储返回 OCI 索引摘要，缺少独立的镜像配置摘要字段。根据实际 Buildx 元数据和已加载镜像 ID 校验 OCI 摘要或配置摘要，复跑通过。摘要语义见 [Docker Buildx 元数据说明](https://docs.docker.com/reference/cli/docker/buildx/build/#metadata-file)。

## 首轮 CI 与依赖仓库限流

2026-11-16，推送候选 `13d6a3452301182128009459e0dbd166a7d00815` 的 `make check` 和 `make check-security` 均通过，随后构建和启动通过。应用镜像 `campusclaw-skeleton:13d6a3452301182128009459e0dbd166a7d00815` 的 OCI 摘要为 `sha256:4c2f975828faa9bb0613042715f55f426e22dbe2fa27984b717e2b4d94c0a30d`，MCP 镜像 `campusclaw-mcp:13d6a3452301182128009459e0dbd166a7d00815` 为 `sha256:5ac326732e36d568ee67f8c1c5567a37ae8b1d17cfd872f79ce8f9f02fe69944`。`/live` 和 `/health` 返回 200，运行版本与源码一致。[推送构建 43822312011](https://github.com/WafoeX/CampusClaw-Team/actions/runs/43822312011/job/133150295337)

同一分支的 PR 合并候选 `6f507db51dec20b124215cc0fad434fa7f5f9bf2` 两项门禁通过，应用与 MCP 构建成功，隔离启动拉取依赖时镜像仓库返回 `toomanyrequests: Rate exceeded`，构建作业退出 1。[首轮 PR 构建 43822443769](https://github.com/WafoeX/CampusClaw-Team/actions/runs/43822443769/job/133150766376)

修复后逐一预拉取 Compose 固定摘要的 MySQL、Qdrant 镜像。仅明确限流时在 10 秒及 30 秒后重试，重试耗尽或其他错误仍失败。启动使用本地已取得的镜像。限流后成功、持续限流、非限流错误 3 项断网回归通过。基于 `13d6a34` 的构建输入，按新脚本在本地实际构建、启动并复核版本，双探针为 200，临时容器和数据卷正常清理。

## 修复后推送取证（3.2）

2026-11-16，推送 `eb740998083c2c9186d3452404d6493a20aa92ec` 自动触发流水线 `43860255221`。`make check` 通过，12 项 OpenSpec、470 项单元/API、4 项启动和 8 项集成通过。`make check-security` 通过，两项完成后构建作业退出 0。[推送流水线](https://github.com/WafoeX/CampusClaw-Team/actions/runs/43860255221)

| 服务 | 镜像标签 | Buildx 输出摘要 |
| --- | --- | --- |
| 应用 | `campusclaw-skeleton:eb740998083c2c9186d3452404d6493a20aa92ec` | `sha256:7b82600984231ccd1edc1801ec7d5f48c41a6574538df6a9c0387a8dd1f47d25` |
| MCP | `campusclaw-mcp:eb740998083c2c9186d3452404d6493a20aa92ec` | `sha256:3a1c8511db6d53c3dff9304489d2f5c0f90729e73a8141a6f22389f0fe46c4a5` |

两个容器的镜像 ID 与构建结果一致。`/live` 和 `/health` 通过，`/health` 报告运行版本为 `eb740998083c2c9186d3452404d6493a20aa92ec`，MySQL 和 Qdrant 均为 `ready`。此次 CI 未出现限流重试，重试行为由断网用例验证。此组为流水线编排及成品验证，数据库结构与索引无改动，扩迁和物理回退不适用。[构建实测](https://github.com/WafoeX/CampusClaw-Team/actions/runs/43860255221/job/133277811400)

## 2026-11-17 运行镜像源码剥离（3.1 部分）

以 `bf854f9` 加运行镜像改动为构建输入，用随机测试标识 `d33db579107ef3b2b95a0c46b46dd62c38f04244` 构建隔离镜像。应用归档 5 层、MCP 归档 4 层，逐层扫描确认无项目 `.py` 和受检工具路径，两个字节码入口均存在。应用和 MCP 容器采用刚构建的镜像，`/live`、`/health` 的 GET 和 HEAD 均为 200，`/health` 版本和测试标识一致。正常运行后回收容器、网络和卷。

`uv run --locked python scripts/check_pytest.py -q --disable-socket tests/unit/test_build_candidate.py` 7 项通过，包含早期层写入源码、uv 或 ensurepip 后在后一层隐藏时仍失败的对照。扫描检查 Docker 导出归档而非容器合并视图。固定安全门禁另行检查同一候选资产中的凭据和依赖漏洞。
