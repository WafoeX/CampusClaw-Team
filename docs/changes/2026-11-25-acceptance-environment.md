# 完整隔离预验收环境

## 变更说明

按已授权收尾计划补齐本机完整环境入口，基于安全预算 PR #74。复用原 Compose 服务，不改变业务功能；本克隆独立项目、合成库和回环端口，私有配置只在 runtime/acceptance。

## 验证记录

- OpenSpec 严格校验通过，纯主机工具 skip_specs，不改变业务规格。
- `make check-static check-test CHANGE=2026-11-25-acceptance-environment` 退出 0：561 项单元/API、4 项启动检查通过。
- 工具定向 14 项通过，覆盖跨克隆隔离、口令保留、模型配置刷新、非合成库/root 拒绝、私有文件 600、配置文本不执行、仅回环 8444 网关端口及依赖摘要保留。
- 实际完整服务启动与双探针尚待执行，不能用上述替身/纯函数检查代替。

## 评审结论

工具实现与文档规划阶段，实际启动及人工评审未完成。复用 openspec-propose / openspec-apply-change、project-add-tests 和 project-review；读取 AGENTS、README 及安全、运维、测试、数据与评审约束。不发布公网，不修改已有部署，不把模型配置存在视为真实模型效果通过。
