# 第 6 课 MCP 与工具接入规约自检

## 变更说明

交付[提案](../../openspec/changes/2026-11-04-add-controlled-mcp-tools/proposal.md)、[设计](../../openspec/changes/2026-11-04-add-controlled-mcp-tools/design.md)、四份增量规格及[任务](../../openspec/changes/2026-11-04-add-controlled-mcp-tools/tasks.md)。第 6 课使用第 5 课助手、技能、SSE、执行记录契约，实施待上游业务验收。

## 验证记录

| 项目 | 状态 | 实际记录 |
| --- | --- | --- |
| 课程及协议 | 已核对 | 网页入口未能直接访问课程站，复读同一工作区前轮下载的[第 6 课任务清单](https://devops.hello1023.com/课程任务清单-第6课.html)和[实践页](https://devops.hello1023.com/课件/第6课-课件-MCP与工具接入/pages/apply.html)。直接读取官方 2025-06-18 的[传输](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)、[生命周期](https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle)及[工具](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)协议。 |
| openspec-propose | 已执行 | 读取 AGENTS.md、README、仓库规则、现有上游规约及技能；经 `openspec context --json` 定位仓库，按各 artifact 的 instructions 和依赖生成。 |
| 结构与任务 | 通过 | `openspec validate 2026-11-04-add-controlled-mcp-tools --strict` 退出 0，`openspec status --change 2026-11-04-add-controlled-mcp-tools` 显示 4/4；只读 apply 指令显示 0/12 实施任务完成。 |
| project-review | 已执行 | 核对八规范及 SEC-01–06、SEC-10、SEC-13–15、AI-02、AI-08–12、DATA-02–08、REV-07–09 的规划覆盖；检查四份规格三段式、失败路径、任务映射、链接和改动范围。 |
| 运行和人工验证 | 未执行 / 待人工评审 | 应用测试、Compose、MCP 客户端互操作、真实网关、Swagger、浏览器、人工与同伴验证待实施。 |

## 评审结论

在课程示例的基础上，拟从部署批准的目录登记地址，教师只读本班去内容运行元数据，连接软删后保留可归属的只增记录。三项差异按课程口径待确认。第 5 课规约提交作为本课分支的直接上游，代码实施按组推进。
