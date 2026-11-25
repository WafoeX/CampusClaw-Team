# 完整隔离预验收环境

## 变更说明

按已授权收尾计划补齐本机完整环境入口，基于安全预算 PR #74。复用原 Compose 服务，不改变业务功能；本克隆独立项目、合成库和回环端口，私有配置只在 runtime/acceptance。

## 验证记录

- OpenSpec 严格校验通过，纯主机工具 skip_specs，不改变业务规格。
- `make check-static check-test CHANGE=2026-11-25-acceptance-environment` 退出 0：561 项单元/API、4 项启动检查通过。
- 工具定向 14 项通过，覆盖跨克隆隔离、口令保留、模型配置刷新、非合成库/root 拒绝、私有文件 600、配置文本不执行、仅回环 8444 网关端口及依赖摘要保留。
- 在干净提交 `294e1fd280a11dfc86cf282c128250701e078252` 上实际启动八项服务：app、gateway、Kafka、MCP、MySQL、Qdrant 健康，relay、worker 运行；`/live` 为 `alive`，`/health` 为 `ready`，MySQL/Qdrant 均为 `ready`，返回版本与提交一致。HTTPS 仅监听 `127.0.0.1:8444`，app 仅监听 `127.0.0.1:18000`；本机原有其他 Compose 项目未停止。
- 实际 HTTPS 合成烟测退出 0：三种身份共 16 个请求，覆盖资料写读、跨班与不存在同形 404、人工题目审核、发布测验、答案开放前隐藏、草稿、同键交卷重放及教师汇总；真实数据库只形成 1 次提交，平均分为 5。原始状态和请求清单保存在权限 600 的 `runtime/acceptance/status.json`、`smoke.json`，不入版本。
- 根目录不存在私有 `.env`，因此聊天与嵌入模型均标记未配置；真实模型评估未执行。真人、手机和跨机器验收未执行，确定性烟测不能替代这些结果。

## 评审结论

完整服务与确定性教学闭环已形成可复跑的预验收入口；这项结论限于本机合成环境，尚不构成候选冻结或项目最终验收。复用 openspec-propose / openspec-apply-change、project-add-tests 和 project-review；读取 AGENTS、README 及安全、运维、测试、数据与评审约束。不发布公网，不修改已有部署，不把模型配置存在视为真实模型效果通过。人工评审仍待 PR 审阅。
