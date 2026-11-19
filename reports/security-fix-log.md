# 第 9 课安全修复索引

以 `bc591b4` 的固定复跑为修复前基线。每行链接对应已提交的修复或验证记录。日期、运行命令及后续复测见[修复证据](../docs/changes/2026-11-04-remediate-security-findings.md)和[第 8 课预检记录](security-precheck.md)。

| 课程项 | 修复前实际 | 修复后实际与判定 | 提交 |
| --- | --- | --- | --- |
| SEC-01 匿名访问 | 五个合法对照均为 200，匿名请求均为 401/1100，`data` 为 null。 | 原策略通过基线复核，沿用已有认证策略。 | [`5892d7e`](https://github.com/WafoeX/CampusClaw-Team/commit/5892d7e) |
| SEC-02 班级隔离 | 跨班和缺失讲义均为 404/1300。部分更新 SQL 在事务锁内仅用讲义标识定位。 | 写 SQL 按班级与修订或源版本过滤。真实 MySQL 与 Qdrant 对照中，本班关键词、向量、混合查询均各命中 1 条，其他班级各返回空列表。2.2 通过。 | [`ae110f3`](https://github.com/WafoeX/CampusClaw-Team/commit/ae110f3) |
| SEC-03 配置写入 | 教师三类写入 200，学生三类写入 403/1200，配置与修订快照相同。 | 启用一次性请求令牌后，原样及带有效令牌的学生对照仍均为 403/1200。配置与修订保持一致，相关拒绝有审计。2.1、3.2 的对照通过。 | [`5892d7e`](https://github.com/WafoeX/CampusClaw-Team/commit/5892d7e)、[`ae2655e`](https://github.com/WafoeX/CampusClaw-Team/commit/ae2655e) |
| SEC-04 直接批改 | 向现有只读成绩入口发 PATCH 为 405，四表快照一致。 | 受控工具在发送前停用连接时拒绝且零发包，按执行标识核实单条拒绝审计。审计存储故障也无发包。SEC-08 第四步固定写提议在执行层拒绝、零发包、六表无变化并有拒绝审计。独立评分写入口的课程等价由最终验收 1.5 确认，缺项如实登记，2.3 完成。 | [`b592e03`](https://github.com/WafoeX/CampusClaw-Team/commit/b592e03)、[本轮工具回归](../tests/integration/tool_dialogue_runtime.py) |
| SEC-05 凭据与资产 | 历史、工作区、前端、日志及两个镜像均零命中。关联 worktree 上另发现历史扫描因 Git 元数据路径异常漏扫。 | 候选各资产范围零命中。修复 worktree 扫描后，镜像副本与本地可达 Git 提交数一致，历史和工作区扫描零命中。4.1 通过。 | [`abdb0a8`](https://github.com/WafoeX/CampusClaw-Team/commit/abdb0a8)、[`2b8e438`](https://github.com/WafoeX/CampusClaw-Team/commit/2b8e438) |
| SEC-06 锁定依赖及门禁 | 本地 Trivy 更新漏洞库失败，未取得计数。 | 同字节 `uv.lock` 在 CI 扫描为 High 0、Critical 0。隔离资产红绿对照 Make 退出 2、0，详见[对照记录](gate-red-green.md)。4.2、4.3 通过。 | [`c30a4c3`](https://github.com/WafoeX/CampusClaw-Team/commit/c30a4c3)、[`e204d71`](https://github.com/WafoeX/CampusClaw-Team/commit/e204d71) |
| SEC-07 操作审计 | 固定模型返回 30 tokens，日志未关联请求标识，技能执行记录无用量。 | SSE、日志及执行记录的用量与请求对齐。教师获本班脱敏记录，学生和跨班访问被拒绝或隐藏。审计写失败时配置无写入。5.1 通过。 | [`384baa0`](https://github.com/WafoeX/CampusClaw-Team/commit/384baa0)、[`f2be908`](https://github.com/WafoeX/CampusClaw-Team/commit/f2be908) |
| SEC-08 四步实验 | 第 8 课无运行记录。 | 四步实测完成：默认替身与真实网关各一轮，第三步真实模型在答案末尾引述恶意讲义指令原文但未执行；第四步固定写提议在执行层拒绝、零发包、有审计且六表无变化，按 SR-B01 判绿。真实观察见[固定报告](sec08-experiment.md)，1.2 基线补齐、5.2 完成，真人复验交最终验收 4.3。 | [`19203d0`](https://github.com/WafoeX/CampusClaw-Team/commit/19203d0) |

## 注入回归记录

3.2 的用例在 [`tests/integration/security_precheck_runtime.py`](../tests/integration/security_precheck_runtime.py)，令牌签发接口另有 [`apitest` 用例](../apitest/cases/api/v1/auth/csrf-tokens/POST.json)。合法同源首次写入成功。跨来源表单、缺失或过期令牌、动作或会话不匹配为 403/1200。两个请求并发消费同一枚令牌时，一个 200、一个 403，配置只增加一条修订。再次提交为 403，数据库快照相同。

[`tests/integration/retrieval_runtime.py`](../tests/integration/retrieval_runtime.py) 前序已在真实 MySQL 上确认普通含撇号的检索值与班级值均独立绑定，额外排序字段返回 400/1000 且未执行全文检索 SQL。2026-11-18 补齐课程原注入词及完整三件套，实测和门禁阻断见下表；人工冷启动、跨机器独立复验和评审待执行。

[`tests/browser/teaching.mjs`](../tests/browser/teaching.mjs) 已在 Chromium 核对普通含尖括号的讲义标题。两页原始 HTML 不带标题标记，JSON 返回原值，学生列表和详情按纯文本显示且标题容器无子元素。临时移除详情标题赋值时，同一命令退出 1，恢复后退出 0。

## 6.3 可重复复验索引

2026-11-18 增补：注入三件套可用 `make check-injection`，详见[本轮取证](#2026-11-18-三段式与阻断复验)。下表保留此前候选与执行记录。

以代码候选 `546a954` 运行，按 [README 的隔离环境](../README.md#课末安全预检)准备 Docker、uv 和 OpenSpec。工程门禁以该候选的 [GitHub Actions](https://github.com/WafoeX/CampusClaw-Team/actions/runs/43742209674/job/132897628672) 为证，`make check` 已通过。其他运行按其报告登记候选与环境。

| 核查 | 复跑办法及证据 |
| --- | --- |
| 认证、讲义、班级及 CSRF | `uv run --locked python scripts/check_pytest.py -q tests/integration/test_compose.py -k security_precheck`。基线和重放见[预检记录](security-precheck.md)及本报告前文。 |
| 异步三项与四步走查 | `uv run --locked python scripts/check_pytest.py -q -s tests/integration/test_compose.py -k 'real_kafka or transactions_without_broker'`。核对 `security_normal_delivery`、受理、重投递与单批生效，详见[风险证据](risk-concurrency.md)及[四步走查记录](../docs/changes/2026-11-04-remediate-security-findings.md#2026-11-15-四步安全走查61sr-n03)。 |
| 工具撤权与审计 | `uv run --locked python scripts/check_pytest.py -q tests/integration/test_compose.py -k controlled_tool_dialogue`。核对拒绝、发包计数与审计结果。 |
| 讲义浏览器回归 | `uv run --locked python -m tests.browser.run_teaching`。核对 `MATERIAL_TITLE_BROWSER_OK` 与 `TEACHING_BROWSER_RUNTIME_OK`。 |
| 固定候选资产与依赖 | 按 README 从同一 Git 提交采集资产并运行 `make check-security`。扫描器红绿及分项输出见[资产门禁对照](gate-red-green.md)与[依赖基线](security-baseline.md)。 |

技术自审各有一份实际发现、处置和复测记录，见[关联工作树历史扫描](security-self-review-git.md)和[浏览器回归失败输出](security-self-review-browser.md)。其他实际失败及复测见[返工记录](security-rework.md)。资产归档、日志及漏洞库缓存保留在 Git 忽略目录。[SEC-08 四步实测报告](sec08-experiment.md)已归档，四步记录与第四步工具层判据见该报告。

6.3 技术复验索引和两份自审已归档，注入三件套技术回归于 2026-11-18 补齐，SEC-08 四步实测于 2026-11-19 补齐。课程验收仍待直接评分入口等价确认，以及同伴在另一台机器冷启动后至少两条一致复验。正式署名和分歧复测由[最终验收 4.2–4.3](../openspec/changes/2026-11-04-project-final-acceptance/tasks.md)记录。

## 2026-11-18 三段式与阻断复验

基线 `cd695bd`。代码提交为 SQL `fa8aa12`、脚本标题 `663227a`、门禁及清单 `183bb51`。运行 `make check-injection`，从下列实际清单收集共享 pytest，第一次 23 项通过、200.73 秒，故意破坏并恢复后再次 23 项通过、200.86 秒。两次 Make 均退出 0。

| 场景与可执行清单 | 前置 → 操作 → 可观测结果 | 破坏与恢复 |
| --- | --- | --- |
| SR-F07：[检索 POST](../apitest/cases/api/v1/searches/POST.json) | A/B 班真实已索引数据及正向命中 → 提交 `' OR '1'='1`，再将其放入非法排序字段 → 检索 200/0 空结果，SQL 结构不变、原值及班级独立绑定；排序 400/1000 且无额外全文查询，正向查询仍命中。 | 临时移除额外字段拒绝，定向检索冷启动用例在排序状态断言失败，pytest 退出 1、65.06 秒；恢复后完整复测通过。 |
| SR-F08：[资料 POST](../apitest/cases/api/v1/materials/POST.json) | 教师创建含 `<script>alert(1)</script>` 的标题 → 学生读取 JSON、原始 HTML 并打开列表/详情 → 标题保留原文，HTML 不嵌入标题标记，DOM 只有文本且无 alert 副作用。 | 临时改为 innerHTML，详情出现两个子元素且文字变化，浏览器 pytest 退出 1、28.76 秒；恢复 textContent 后完整复测通过。 |
| SR-F09：[模板 PATCH](../apitest/cases/api/v1/prompt-templates/{resource_id}/PATCH.json) | 有效教师会话与真实库快照 → 跨来源表单、同源缺令牌、重放及合法首次写入 → 非法请求 403/1200 且无配置副作用；合法写入一次，并发仅一次成功，Cookie 属性保持 Strict/Secure/HttpOnly。 | 临时绕过令牌消费，缺令牌断言失败，预检 pytest 退出 1、22.87 秒；恢复后完整复测通过。 |

`make check` 的集成阶段保留全部现有集成，同时增加标题浏览器测试；SQL、CSRF 原集成入口继续运行。静态阶段执行清单校验，缺 SR-F07–09 任一项、空三段式或无测试文件即非零。临时清空 XSS 验收段时，`make check-static CHANGE=2026-11-04-remediate-security-findings` 退出 2；恢复后退出 0。定向 pytest 的非零及共享运行器的失败、跳过、空套件契约共同保持门禁阻断，不将三次定向失败写成执行了三轮完整 Make。

本项复用已有防护，未发现需修改业务实现的红项。3.1、3.3 技术完成；SEC-08、直接评分课程等价及综合收尾仍缺。真实基线、七类自审与原始日志位置见[本轮证据](../docs/changes/2026-11-04-remediate-security-findings.md#2026-11-18-注入三件套与必需门禁)。约束文件变更待人工评审。
