# 第 9 课安全修复索引

以 `bc591b4` 的固定复跑为修复前基线。每行链接对应已提交的修复或验证记录。日期、运行命令及后续复测见[修复证据](../docs/changes/2026-11-04-remediate-security-findings.md)和[第 8 课预检记录](security-precheck.md)。

| 课程项 | 修复前实际 | 修复后实际与判定 | 提交 |
| --- | --- | --- | --- |
| SEC-01 匿名访问 | 五个合法对照均为 200，匿名请求均为 401/1100，`data` 为 null。 | 原策略通过基线复核，沿用已有认证策略。 | [`5892d7e`](https://github.com/WafoeX/CampusClaw-Team/commit/5892d7e) |
| SEC-02 班级隔离 | 跨班和缺失讲义均为 404/1300。部分更新 SQL 在事务锁内仅用讲义标识定位。 | 写 SQL 按班级与修订或源版本过滤。真实 MySQL 与 Qdrant 对照中，本班关键词、向量、混合查询均各命中 1 条，其他班级各返回空列表。2.2 通过。 | [`ae110f3`](https://github.com/WafoeX/CampusClaw-Team/commit/ae110f3) |
| SEC-03 配置写入 | 教师三类写入 200，学生三类写入 403/1200，配置与修订快照相同。 | 启用一次性请求令牌后，原样及带有效令牌的学生对照仍均为 403/1200。配置与修订保持一致，相关拒绝有审计。2.1、3.2 的对照通过。 | [`5892d7e`](https://github.com/WafoeX/CampusClaw-Team/commit/5892d7e)、[`ae2655e`](https://github.com/WafoeX/CampusClaw-Team/commit/ae2655e) |
| SEC-04 直接批改 | 向现有只读成绩入口发 PATCH 为 405，四表快照一致。 | 受控工具在发送前停用连接时拒绝且零发包，按执行标识核实单条拒绝审计。审计存储故障也无发包。独立评分写入口的课程等价待最终验收确认，2.3 未完成。 | [`b592e03`](https://github.com/WafoeX/CampusClaw-Team/commit/b592e03)、[本轮工具回归](../tests/integration/tool_dialogue_runtime.py) |
| SEC-05 凭据与资产 | 历史、工作区、前端、日志及两个镜像均零命中。关联 worktree 上另发现历史扫描因 Git 元数据路径异常漏扫。 | 候选各资产范围零命中。修复 worktree 扫描后，镜像副本与本地可达 Git 提交数一致，历史和工作区扫描零命中。4.1 通过。 | [`abdb0a8`](https://github.com/WafoeX/CampusClaw-Team/commit/abdb0a8)、[`2b8e438`](https://github.com/WafoeX/CampusClaw-Team/commit/2b8e438) |
| SEC-06 锁定依赖及门禁 | 本地 Trivy 更新漏洞库失败，未取得计数。 | 同字节 `uv.lock` 在 CI 扫描为 High 0、Critical 0。隔离资产红绿对照 Make 退出 2、0，详见[对照记录](gate-red-green.md)。4.2、4.3 通过。 | [`c30a4c3`](https://github.com/WafoeX/CampusClaw-Team/commit/c30a4c3)、[`e204d71`](https://github.com/WafoeX/CampusClaw-Team/commit/e204d71) |
| SEC-07 操作审计 | 固定模型返回 30 tokens，日志未关联请求标识，技能执行记录无用量。 | SSE、日志及执行记录的用量与请求对齐。教师获本班脱敏记录，学生和跨班访问被拒绝或隐藏。审计写失败时配置无写入。5.1 通过。 | [`384baa0`](https://github.com/WafoeX/CampusClaw-Team/commit/384baa0)、[`f2be908`](https://github.com/WafoeX/CampusClaw-Team/commit/f2be908) |
| SEC-08 四步实验 | 第 8 课无运行记录。 | 四步实测及固定报告待补，1.2、5.2 保持未完成。 | 待实测 |

## 注入回归记录

3.2 的用例在 [`tests/integration/security_precheck_runtime.py`](../tests/integration/security_precheck_runtime.py)，令牌签发接口另有 [`apitest` 用例](../apitest/cases/api/v1/auth/csrf-tokens/POST.json)。合法同源首次写入成功。跨来源表单、缺失或过期令牌、动作或会话不匹配为 403/1200。两个请求并发消费同一枚令牌时，一个 200、一个 403，配置只增加一条修订。再次提交为 403，数据库快照相同。

[`tests/integration/retrieval_runtime.py`](../tests/integration/retrieval_runtime.py) 已在真实 MySQL 上确认普通含撇号的检索值与班级值均独立绑定，额外排序字段返回 400/1000 且未执行全文检索 SQL。完整 SQL 注入、XSS 及三件套的门禁阻断证据仍待补，3.1、3.3 保持未完成。人工冷启动、跨机器独立复验和评审待执行。

[`tests/browser/teaching.mjs`](../tests/browser/teaching.mjs) 已在 Chromium 核对普通含尖括号的讲义标题。两页原始 HTML 不带标题标记，JSON 返回原值，学生列表和详情按纯文本显示且标题容器无子元素。临时移除详情标题赋值时，同一命令退出 1，恢复后退出 0。
