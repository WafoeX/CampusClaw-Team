## Purpose

为班级助手提供可以独立部署和验证的教学 MCP 工具服务，以固定协议契约实现发现和只读调用，并隔离工具凭据及主应用的教学数据。

## ADDED Requirements

### Requirement: MP-01 受认证的教学工具服务

系统 SHALL 在同一 Compose 工程内运行独立的 MCP 服务，提供最小就绪检查与 JSON-RPC 2.0 的 Streamable HTTP 2025-06-18 端点。支持 initialize、initialized 通知、tools/list 和 tools/call；工具目录 SHALL 公布 formula_hint 和 unit_convert 的用途与输入 schema。工具不修改业务数据，服务端令牌只通过部署环境注入。

#### Scenario: MP-N01 独立客户端互操作
- **GIVEN** Compose 服务就绪，使用固定版本的独立 MCP 客户端和有效的私有令牌
- **WHEN** 访问 /health，按版本握手、发送 initialized 通知、列出工具并分别调用
- **THEN** 健康检查成功，通知返回 202 空响应，能发现两个工具及其 schema，分别得到步骤提示及合法换算结果；主应用业务数据无写入

#### Scenario: MP-B01 POST JSON 与 GET 限制
- **GIVEN** 自建服务已完成握手且会话有效
- **WHEN** 客户端以支持 JSON 和 SSE 的 Accept 发 POST，再以 SSE Accept 对同一端点发 GET
- **THEN** POST 返回与请求 ID 对应的 JSON 结果；独立 GET 流返回 405，宿主无需该 GET 流即可调用

#### Scenario: MP-F01 非法协议或参数
- **GIVEN** 已认证客户端
- **WHEN** 依次发畸形 JSON、非法 JSON-RPC 结构、未知方法及含额外字段或跨量纲的工具参数
- **THEN** 返回可读且无原文回显的协议错误或跨量纲业务错误，无有效执行结果

#### Scenario: MP-F02 令牌和 Origin 拒绝
- **GIVEN** 服务就绪
- **WHEN** 缺少令牌、使用错误令牌，或携带正确令牌但 Origin 未获允许
- **THEN** 无工具清单、会话标识或结果，错误不含凭据；可观测计数显示无工具执行

#### Scenario: MP-F03 会话过期或不存在
- **GIVEN** 客户端曾成功握手，旧会话已到期
- **WHEN** 分别用旧会话标识和随机不存在标识尝试列出工具及调用
- **THEN** 返回 404，无工具执行；显式重新握手后可恢复访问

#### Scenario: MP-F04 自建服务不可达
- **GIVEN** 主应用已有可用资料问答且已连接工具服务
- **WHEN** 停止工具服务后调用工具，并从隔离客户端核对健康探测
- **THEN** 工具被明确标记不可用且没有伪造结果，主应用的健康及普通检索问答仍可用

#### Scenario: MP-F05 版本协商失败
- **GIVEN** 对端不支持宿主配置的协议版本或未声明 tools 能力
- **WHEN** 发起连接
- **THEN** 宿主不发布已连接状态，不继续发现或执行工具
