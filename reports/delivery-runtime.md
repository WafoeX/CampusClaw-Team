# 第 10 课交付运行证据

## 本地候选构建与启动

2026-11-16，对源码 `a0c2a5afd5869ee19127392c294f32669d726e9c` 的 Dockerfile、应用、MCP 和锁文件运行 `uv run --locked python -m scripts.build_candidate "$(git rev-parse HEAD)"`，退出 0。使用本地 Docker Desktop 与 Buildx，Compose 从本次构建的标签加载，两个运行容器的镜像 ID 均和构建结果相同。

| 服务 | 镜像标签 | Buildx 输出摘要 |
| --- | --- | --- |
| 应用 | `campusclaw-skeleton:a0c2a5afd5869ee19127392c294f32669d726e9c` | `sha256:6f733c70d5add479eecb589e8f0af780d90dc3dd95e7cf46c6f9065d80abc0b5` |
| MCP | `campusclaw-mcp:a0c2a5afd5869ee19127392c294f32669d726e9c` | `sha256:1749150486fd70d8813b574e6b0b3a17a5898a2f2dae92eaa60ac88c4e40c8df` |

`/live` 和 `/health` 的 GET、HEAD 均为 200。`/health` 的 MySQL、Qdrant 均为 `ready`，运行版本为上述完整提交。独立 MCP 的容器健康探针通过。隔离容器和卷清理完成。

首次以宿主 Python 3.9 直接运行时，探针辅助模块所用的 `datetime.UTC` 无法导入，复跑改用仓库锁定的 Python 3.13。Buildx 首轮构建成功，但 Docker Desktop 的容器存储返回 OCI 索引摘要，缺少独立的镜像配置摘要字段。根据实际 Buildx 元数据和已加载镜像 ID 校验 OCI 摘要或配置摘要，复跑通过。摘要语义见 [Docker Buildx 元数据说明](https://docs.docker.com/reference/cli/docker/buildx/build/#metadata-file)。
