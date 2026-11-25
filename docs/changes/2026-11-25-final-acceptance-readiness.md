# 最终验收准备与状态校准

## 变更说明

2026-11-25 基于 `d4fd479`，按用户确认的计划建立由 lezhonglezhong 统筹的收尾清单，引用既有最终验收 21 项任务；同步首页、矩阵、候选与第 10 课设计。候选题任务审计已实现，课程方对作业/技能语义的认可仍未发生；旧候选制品保持历史边界。评审规范和 AGENTS 仅澄清历史状态及远程协议，不放宽权限、门禁、真人或实际评审要求。

## 验证记录

- `openspec validate 2026-11-25-final-acceptance-readiness --strict`：退出 0，纯文档使用 skip_specs，无业务规格变化。
- `uv sync --locked`：退出 0，Python 3.13.9，安装仓库锁定依赖；不表示应用已启动。
- `gh api repos/WafoeX/CampusClaw-Team/branches/main`：protected 为 true。分支保护详情接口返回 404，分支规则接口为空；本账号未取得双门禁具体配置的新核验证据，沿用历史证据，不把 protected 布尔值当完整配置证明。
- 读取第 9、10 课正式任务：网页工具不可访问，HTTPS 下载成功，指纹与差异判定见剩余事项表。
- `make check-static CHANGE=2026-11-25-final-acceptance-readiness`：退出 0，全仓严格校验、232 个 Python 文件格式、lint、分层、场景及接口清单通过。
- 本次修改 Markdown 的 174 个本地链接目标存在；不包含外部可用性和锚点校验。首版临时检查器将文件名括号误作链接结束符，修正解析后通过，不是仓库链接缺失。
- `make check-test`：退出 0，520 项单元/API、4 项启动检查通过；未跑完整 Compose 与安全资产扫描，纯文档 PR 由 CI 继续验证。
- `git diff --check`：退出 0。

## 评审结论

本次使用 openspec-propose 建立文档规划，按用户已明确要求实施该计划继续使用 openspec-apply-change；project-review 核对状态和证据边界。实际输入为当前仓库、既有最终验收任务和用户确认的单人统筹计划，读取 AGENTS、README、评审规范及相关任务/报告。无业务 API、数据、模型或运行配置变化，无需补业务测试；应用启动、真人测试和独立复验均未由本次文档检查证明。约束文件澄清提交人工复核，自检不等于批准。

PR 已提交，任务 2.2 完成文档交付自检；实际人工评审与最终验收仍待执行。
