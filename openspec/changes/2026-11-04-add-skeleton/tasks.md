## 1. 搭建可扩展的应用基础

- [x] 1.1 提供 Flask 应用工厂、HTTP/服务/适配器分层、统一响应及后续身份和资源策略的接入点。
- [x] 1.2 提供外置配置、空值样例、存活与就绪探针，以及可按请求标识定位的日志。

## 2. 搭建可运行的开发环境

- [x] 2.1 提供锁定依赖、Dockerfile 和 Compose，干净源码可启动 Flask、MySQL、Qdrant 并达到就绪。
- [x] 2.2 建立单元、接口和真实依赖集成测试，执行骨架的适用测试及 `make check`，留存 CI 和运行记录。
- [x] 2.3 在 README 提供首次启动、日常只重建应用和新增业务模块的接入说明。

上述开发交付以现有主干实现、[已记录的主干 CI 与冷启动](../../../docs/changes/2026-11-04-add-skeleton.md#2026-11-04-逐项审计与主干保护实测)及[开发指南](../../../README.md#开发者快速开始)核对。仓库保护演练、成员复现、正式课程评审和归档状态见[课程验收页](../../../docs/lesson-07/acceptance.md)。原任务编号及 8/15 进度见[历史任务清单](https://github.com/WafoeX/CampusClaw-Team/blob/e0039aa381029d2200c041b45b500993572cbd65/openspec/changes/2026-11-04-add-skeleton/tasks.md)。

各实现变更保留自己的测试与门禁证据。核心功能齐备后，按[独立的最终验收任务](../2026-11-04-project-final-acceptance/tasks.md)验证跨功能流程。
