# 第 10 课验收矩阵

盘点基线为 `878a2a04cf1f2d9e9abfb5b83f02fc258244904b`，日期为 2026-11-17，时间均用 Asia/Shanghai。每项证据仅适用于记录中的提交和环境。第 10 课 5.1 尚未冻结正式候选，人工评测保持待启动。[第 10 课任务](../openspec/changes/2026-11-04-define-lesson-10-acceptance/tasks.md)

## 可复跑入口与最新可核对记录

同一组合下的定向入口可用 `tests/scenario-map.json` 中的 `test::function` 参数复跑。使用合成环境，Docker 启动与私有配置步骤见 README。表中“版本/时间”取相应命令的实测记录，前序候选的结果须在正式候选上按影响范围复验。

| 阶段 | 命令或入口 | 判据 | 版本、时间与实际结果 | 责任角色 |
| --- | --- | --- | --- | --- |
| 变更收尾 | `make check` | 所有子门禁退出 0 | 主干 `878a2a0`，2026-11-17 15:24 启动，CI 常规门禁成功。[主干 CI](https://github.com/WafoeX/CampusClaw-Team/actions/runs/44038526078) | 实施人 |
| 变更收尾 | `make check-specs`、`make check-static CHANGE=2026-11-04-define-lesson-10-acceptance` | 严格校验、格式、分层、映射通过 | 主干 `878a2a0` 的 `make check` 包含全仓严格校验与静态检查。目标变更的额外严格校验见本轮变更记录。 | 实施人 |
| 变更收尾 | `make check-test`、`make check-integration` | 单元/API、启动、真实依赖回归均通过 | 主干 `878a2a0` 的 `make check` 全部通过，2026-11-17。[常规门禁](https://github.com/WafoeX/CampusClaw-Team/actions/runs/44038526078/job/133887169329) | 实施人 |
| 变更收尾 | `make check-secrets`、`make check-dependencies` | 历史及工作区无凭据，锁定依赖 High/Critical 均为 0 | 主干 `878a2a0` 的 `make check` 全部通过，2026-11-17。[常规门禁](https://github.com/WafoeX/CampusClaw-Team/actions/runs/44038526078/job/133887169329) | 安全负责人 |
| 变更收尾 | `CAMPUSCLAW_SECURITY_ASSETS=reports/ci-security-assets uv run --locked python scripts/check_pytest.py -q tests/integration/test_compose.py -k security_precheck`，随后同提交运行 `make check-security SECURITY_ASSETS=reports/ci-security-assets` | 资产与提交一致，预检和七个资产/锁依赖分项成功 | 主干 `878a2a0`，2026-11-17 15:24 启动，CI 独立安全门禁成功。[安全门禁](https://github.com/WafoeX/CampusClaw-Team/actions/runs/44038526078/job/133887169037) | 安全负责人 |
| 实现组可运行 | `docker compose up --build -d`，核对 `/health` 和 `/live`。只构建并核对成品可用 `uv run --locked python -m scripts.build_candidate <完整提交>` | 依赖就绪，探针版本、镜像标签及实际成品一致 | 2026-11-17，`878a2a0` 的 CI 双镜像构建与运行通过；`8dcd9f0` 上的 HTTPS 网关变更完成停库撤流和恢复复验。[当前候选构建](https://github.com/WafoeX/CampusClaw-Team/actions/runs/44038526078/job/133890131945) · [隔离运行证据](delivery-runtime.md) | 运维负责人 |
| 实现组可运行 | `uv run --locked python scripts/check_pytest.py -q -s --tb=short tests/integration/test_compose.py -k 'real_kafka or transactions_without_broker'` | 见下节三项判据 | `878a2a0`，2026-11-17 15:29 结束，退出 0，2 项通过、107.19 秒。使用真实 MySQL/Kafka 与固定模型替身。[异步三判据](#异步三判据) | 异步教学实施人 |
| 实现组可运行 | `CAMPUSCLAW_REAL_CANDIDATES=1 uv run --locked python scripts/check_pytest.py -q -s tests/integration/test_compose.py -k real_kafka` | 真实网关生成待审草稿、保留授权原文区间 | 2026-11-12，基于 `6538600` 的异步收尾候选复跑退出 0，1 项通过。当前基线未重跑真实网关。[真实模型记录](../docs/changes/2026-11-04-add-async-teaching-workflows.md#2026-11-12-异步教学收尾复验) | 异步教学实施人 |
| 实现组可运行 | `uv run --locked pytest -q tests/browser/test_chapters.py`，先按 README 配置本地 Chromium | 章节、检索、出处及窄屏状态 | 2026-11-06 至 07 的检索交付候选通过，退出 0。当前基线未重跑该浏览器用例。[检索交付](../docs/changes/2026-11-04-add-traceable-retrieval.md) | 资料与检索实施人 |
| 实现组可运行 | `uv run --locked python scripts/check_pytest.py -q tests/browser/test_teaching.py` 或 `uv run --locked python -m tests.browser.run_teaching` | 390px Chromium 验证 HTTPS 会话、候选题三态、成功停询、刷新只读、交卷、来源及换班隔离 | 2026-11-18，基于 `20db163` 的增量在隔离 Chromium/MySQL 中通过。固定模型、文件闸门推进，Kafka 单列。[H5 异步实测](../docs/changes/2026-11-04-define-lesson-10-acceptance.md#2026-11-18-h5-候选题三态回归43-部分) | 教学实施人 |
| 实现组可运行 | `uv run --locked python scripts/start_demo.py`，核对本地 HTTPS 就绪；按私有配置运行 `scripts/demo_smoke.py` | 合成资料构建、三路检索、问答与出处可回查 | 2026-11-06 至 07，检索候选启动与真实烟测均退出 0。当前基线未重跑。[检索交付](../docs/changes/2026-11-04-add-traceable-retrieval.md) | 资料与检索实施人 |
| 实现组可运行 | `uv run --locked python apitest/run_all.py` | 按 HTTP 路径和方法收集，请求、响应与必要持久副作用正确 | 2026-11-11 的 MCP 交付候选退出 0，77 项通过。当前基线未重跑此独立入口。[MCP 交付](../docs/changes/2026-11-04-add-controlled-mcp-tools.md) | MCP 实施人 |
| 实现组可运行 | `uv run --locked python -m scripts.evaluate_ai_apps`，加 `--real` 可单独跑授权网关烟测 | 固定结构回归和三条合成网关输入 | 2026-11-08 的同步应用候选两轮退出 0，替身结构 20 项通过。当前基线未重跑。[应用评测](../docs/eval/2026-11-08-class-apps.md) | 流式助手实施人 |
| 实现组可运行 | `uv run --locked python -m scripts.evaluate_skills` | 10 条合法槽位渲染，10 条非法选择拒绝 | 2026-11-08 的有界技能候选退出 0。当前基线未重跑。[技能评测](../docs/eval/2026-11-08-bounded-skills.md) | 流式助手实施人 |
| 实现组可运行 | `uv run --locked python -m scripts.evaluate_assistant`，加 `--real` 可单独验证获准网关 | 固定 20 条证据与拒答集 | 2026-11-08 的流式助手候选替身 20/20。真实网关首轮退出 1，复跑退出 0、20/20，含故障替身和零调用样本。MCP 交付时前后替身回归再次通过。[助手回归](../docs/eval/2026-11-08-assistant-regression.md) · [MCP 对照](../docs/eval/2026-11-11-controlled-tools.md) | 流式助手实施人 |
| 实现组可运行 | `uv run --locked python -m scripts.evaluate_controlled_tools`，按证据说明启用私有课程模型配置 | 真实网关提议、本机 MCP 一次调用及审核提示 | 2026-11-11，基于 `7d581d5` 的 MCP 候选退出 0，单样本烟测。当前基线未重跑。[MCP 评测](../docs/eval/2026-11-11-controlled-tools.md) | MCP 实施人 |
| 课程专项 | `uv run --locked python scripts/calibrate_retrieval.py` 和 `uv run --locked python scripts/check_pytest.py -q tests/integration/test_compose.py -k cold_start_and_recovery` | 调参与固定 34 题工程用例分离，比较三模式与拒答 | 2026-11-06 调参退出 0。2026-11-07 基于 `e18c193` 的检索候选记录固定 34 题工程结果。冻结题集和人工裁决待最终验收 2.4。[调参](../docs/eval/2026-11-06-retrieval-calibration.md) · [工程评测](../docs/eval/2026-11-07-retrieval-engineering.md) | 资料与检索实施人 |
| 课程专项 | 临时分支执行 `make check CHANGE=2026-11-04-define-lesson-10-acceptance`，查对应 PR 两轮 CI | 反例时构建及合入阻断，恢复后二者转绿 | 2026-11-17，`e0bfdb4` 的 PR 合并候选退出 2，`67ca589` 的候选双门禁与构建成功。[红绿记录](gate-red-green.md) | 实施人 |
| 课程专项 | 按报告设置 `CAMPUSCLAW_BENCH_*`，运行 `uv run --locked python scripts/check_pytest.py -q -s tests/bench/test_teaching_bench.py` | 同口径对照提交、查询、检索、候选受理及完成，核对分页优化 | 2026-11-17，`96a7eee`、`7a2f6f9` 两轮各 1 项通过，达到预登记判据。[压测取证](bench.md) | 性能实施人 |
| 课程专项 | `uv run --locked python scripts/check_security_control.py reports/security-control-source` | 受检资产出现检测标记时非零，恢复后零退出 | 2026-11-15，合并候选 `996ac8a` 红轮退出 2、绿轮退出 0。[资产对照](gate-red-green.md) | 安全负责人 |
| 正式人工评测 | 干净检出、按 README 启动，再执行 `uv run --locked python scripts/verify_runtime.py --port 8000 --output reports/cold-start-member-a.json` | 三名成员独立核对版本、依赖与双探针 | 成员独立记录未执行。工具使用及过往证据见[骨架验收](../docs/lesson-07/acceptance.md)。 | 复验同伴 |
| 正式人工评测 | 依最终验收 2.1–2.10、4.1–4.5 操作固定候选 | 功能、人工意图、跨设备、真实用户和反馈均有记录 | 未执行，等 5.1 冻结。[最终验收清单](../openspec/changes/2026-11-04-project-final-acceptance/tasks.md) | 验收人、复验同伴 |

## 异步三判据

本轮使用隔离两班合成数据。样本仅用于确认正确性与恢复，容量对照见第 10 课 4.2。

| 判据 | 入口及断言 | 实际 |
| --- | --- | --- |
| 候选受理与完成分开 | `test_JB_QB_real_kafka_and_candidate_recovery` 核对 202、任务地址、三态与成功结果 | 22 次受理的 P95 为 12.10 ms。两次完成耗时 5534.00 ms（含故障恢复）与 38.95 ms。另行观察同一任务 `pending → running → succeeded`。 |
| 重投递仅一批生效 | 上述用例核对提交 DB 后中断、再次收到同事件、结果批次及持久行数 | 同一事件收到两次，首个任务只提交一批结果。正常对照为一条发件、一条结果、零孤儿任务。 |
| 停 Kafka 后教学核心仍可运行 | 上述用例停止 broker 并检查核心就绪和真实教学操作。另跑 `test_JB_F05_mysql_job_transactions_without_broker` | `/health` 仍就绪，八次并行正式交卷全部提交，P95 188.14 ms。无 broker 的数据库事务用例通过。 |

## 实现组场景与责任

[逐场景映射](../tests/scenario-map.json)用规格路径和场景 ID 定位用例。查每条规约的 THEN 得到判据，用映射中的 `test`、`function` 取得执行入口。真实依赖的二次脚本另列 `script`、`runner` 和唯一断言。矩阵按变更聚合结果，避免在两个文件重复维护用例路径。运行 `uv run --locked python scripts/scenario_trace.py` 核对覆盖数量、断言和待验收任务的合法性。

结果以本页的主干常规门禁为自动化基线。映射中单列浏览器的 SB-B02 有独立历史运行记录。所有用例应在冻结候选上按适用条件核对，旧版证据的差异须登记。责任用项目角色表示，正式评测时指定实名。

| 变更 | 自动入口 / 场景数 | 实现组可运行证据 | 变更收尾与课程复验入口 | 正式人工卡片及责任 |
| --- | --- | --- | --- | --- |
| 骨架 | 31 / 37 | [骨架证据](../docs/changes/2026-11-04-add-skeleton.md) | 主干双门禁。CK-F01、CK-F04–06、CK-B01 归最终验收 1.4，CK-F10 归 1.3。 | 2.8，运维负责人和复验同伴 |
| 认证资料 | 28 / 28 | [认证交付](../docs/changes/2026-11-04-add-class-auth-material-ingest.md) | 主干双门禁，复用真实双班与迁移场景。 | 2.1、2.6–2.7，认证资料实施人和验收人 |
| 限流与追溯 | 13 / 13 | [限流交付](../docs/changes/2026-11-05-fix-rate-limits-traceability.md) | 主干双门禁，源码映射由静态子门禁验证。 | 1.3、2.8，实施人和验收人 |
| 资料检索及索引 | 39 / 39 | [检索交付](../docs/changes/2026-11-04-add-traceable-retrieval.md) | 主干双门禁，浏览器和真实模型见命令清单。 | 2.1、2.3–2.4，资料与检索实施人和验收人 |
| 流式助手 | 32 / 32 | [流式交付](../docs/changes/2026-11-04-add-streaming-ai-assistant.md) | 主干双门禁，容量与取消走真实 HTTPS 代理夹具。 | 2.1、2.3、2.9，流式助手实施人和验收人 |
| 受控 MCP | 32 / 32 | [MCP 交付](../docs/changes/2026-11-04-add-controlled-mcp-tools.md) | 主干双门禁，真实服务与工具审计自动回归。 | 2.10，MCP 实施人和验收人 |
| 异步教学 | 39 / 39 | [异步交付](../docs/changes/2026-11-04-add-async-teaching-workflows.md) | 主干双门禁、异步三判据、显式浏览器入口与真实网关烟测。 | 2.2–2.3，教学实施人和验收人 |
| 课末安全预检 | 11 / 16 | [预检记录](security-precheck.md) | 主干独立安全门禁。五条待验收场景见下。 | 4.1，安全负责人和复验同伴 |
| 合计 | 225 / 236 | 25 份增量规格 | 11 条已绑定待办 | 全部人工操作等待冻结 |

### 待验收及选做范围

| 场景 | 目前状态与进入条件 | 责任 |
| --- | --- | --- |
| CK-F01、CK-F04–06、CK-B01 | 独立会话、跨成员冷启动和课程复核待最终验收 1.4，历史自动化证据保留。 | 复验同伴 |
| CK-F10 | 候选准入和人工评审效果待最终验收 1.3。 | 验收人 |
| PSC-F05 | 正向请求 400 已记录修正，预检 1.3 的专项矩阵交接未完成。 | 安全负责人 |
| PSC-N03、PSC-F10、PSC-B01 | 预检已有实测，独立复核及对应结论归最终验收 4.1。 | 复验同伴 |
| PSC-B02 | 第 8 课选做素材已跳过。第 9 课 SEC-08 必做四步已实测（替身与真实网关各一轮，第四步执行层拒绝、零发包、六表无变化并有审计），5.2 完成，真人观察归最终验收 4.3。 | 最终验收 4.3 |
| PSC-N04 | AI 候选题 202 与异步作业受理 202 及三态均已实测（安全修复 6.1），正式交卷为 201。课程作业 202 等价待最终验收 1.5。 | 验收人与课程方 |
| 异步后台索引 IX-N01、IX-B01–02、IX-F01–06 | 用户已选择跳过异步索引 202。现行同步索引用例归资料检索变更。 | 资料与检索实施人 |

## 安全修复与课程专项场景

以下两份规格在通用映射中为专项计划。表内用例或人工任务与同一行的规格 THEN 对照，查看原始状态和复测的版本边界。未执行的技术验证先记实际缺口，再由责任变更补齐。

| 安全修复场景 | 用例或证据与判据 | 状态及责任 |
| --- | --- | --- |
| SR-N01、SR-F01 | 固定候选冷启动，重跑双门禁，核对基线输入及非零结果。[基线与复跑](../docs/changes/2026-11-04-remediate-security-findings.md) | 基线已重放与完整收口完成，1.2 完成。 |
| SR-F02、SR-F03、SR-F04 | `test_PSC_N01_PSC_F01_PSC_F02_PSC_F03_PSC_F04_security_precheck` 检查匿名、班级、角色和无副作用。[SEC-01–03](security-fix-log.md) | 自动化有实测，安全负责人及最终验收 4.2 复核。 |
| SR-F05、SR-F06 | `test_TD_N01_TD_N02_TD_F07_AU_N01_controlled_tool_dialogue` 核对撤权和无写入。[SEC-04](security-fix-log.md) | 工具回归已有证据，2.3 完成；独立评分写入口的课程等价待最终验收 1.5。 |
| SR-F07、SR-F08、SR-F09 | `make check-injection` 从三份三段式清单选择检索冷启动、标题浏览器与安全预检共享用例。`make check` 的静态和集成阶段强制核对并收集。[专项用例与证据](security-fix-log.md#注入回归记录) | 基于 `cd695bd` 的三件套两轮各 23 项通过，三类故意破坏均退出 1；缺验收段使静态 Make 退出 2，恢复后通过。3.1、3.3 技术交付完成，人工评审待执行。 |
| SR-F10、SR-F11 | `make check-security` 和资产红绿对照核对七个范围及非零阻断。[红绿记录](gate-red-green.md) | 独立门禁与对照已有实测，安全负责人。 |
| SR-N02、SR-F12、SR-F13 | 安全预检集成核对七组审计字段、去内容查询、权限与故障无写入。[SEC-07](security-fix-log.md) | 自动化有实测，安全负责人及最终验收 4.2 复核。 |
| SR-B01、SR-B02 | [安全修复 5.2 和最终验收 4.3](../openspec/changes/2026-11-04-remediate-security-findings/tasks.md)的 SEC-08 必做验收卡。 | 四步实测完成（替身 29.80 秒、真实网关 47.61 秒），第四步执行层拒绝、零发包、六表无变化并有审计，真实模型引述偏差如实记录。[固定报告](sec08-experiment.md)；真人观察归最终验收 4.3。 |
| SR-N03、SR-F14 | 异步三判据及 `security_normal_delivery`，核对四步结果、失败与复跑。[四步及复验索引](security-fix-log.md#63-可重复复验索引) | 同一候选三组回归全绿（make check 462.19 秒、异步 108.08 秒、注入 208.97 秒），6.1、6.2 完成；独立复验待最终验收 4.2。 |

| 第 10 课场景 | 执行入口与判据 | 结果及责任 |
| --- | --- | --- |
| L10-F01 | 本矩阵、`scripts/scenario_trace.py`、[5.1 候选清单](candidate-checklist.md)，核对缺项和版本。 | 前四组核对完毕，候选固定为 `a0dd0a0`（CI 44506786210 三任务全绿，镜像摘要、配置与演示数据见清单）。4.1 两项真人确认与 4.3 课程结论已登记去向；评测人员指定与冻结决定待验收负责人，当前候选未冻结。 |
| L10-N01 | 隔离集成 `cold_start_and_recovery` 运行 [两轮解题引导](../tests/integration/ai_apps_runtime.py)，通过会话消息 API 核对 SSE 增量、持久回复及引用。 | 固定替身下两轮通过，2026-11-19 复跑退出 0、161.21 秒。人工教学意图待最终验收。教学实施人、验收人。 |
| L10-N02 | 核对测验正式提交和成绩查询。当前有规则评分与教师审题，独立改分和迟到模型结果竞态缺实现。 | 人工改分优先无实现入口，1.2 已登记缺项，课程等价或补齐业务能力归最终验收 1.5。教学实施人、验收人。 |
| L10-N03 | 隔离集成运行 [错题回顾](../tests/integration/teaching_runtime.py)，核对开放前隐藏、开放后本人答案解析、同班与教师对照。解题引导另有录入错误思路后的提示。 | 底层答案开放和本人边界已通过（2026-11-19 复跑退出 0、161.21 秒）；独立错题讲解的技能入口缺实现，1.2 已登记，等价确认归最终验收 1.5。教学实施人。 |
| L10-F02 | 隔离集成运行 [关键词、向量与混合检索](../tests/integration/retrieval_runtime.py)，核对两班各自有命中，跨班无内容和出处。 | MySQL 与 Qdrant 实测通过（2026-11-19 复跑退出 0、161.21 秒），人工卡待最终验收。资料与检索实施人。 |
| L10-F03 | 同一断言前后执行 `make check` 和 CI，核对合入与构建的阻断及恢复。 | 红绿实测通过；两条命令于 2026-11-19 在候选 `d7ac3d1` 复核退出 0（make check 引用 6.1 等价运行）。管理员同日将 `make check-security` 加入 main 必需状态检查，与 `make check` 并列，双门禁均为主干准入条件。实施人、仓库管理员。 |
| L10-N04、L10-F04 | 候选构建与隔离 `cold_start_and_recovery`，核对版本、制品、配置失败和停库撤流。 | 实测通过，证据见制品运行报告。运维负责人。 |
| L10-N05 | 4.1 复用审计关联、`cold_start_and_recovery`、`real_kafka` 及 `tests/unit/test_observability_dashboard.py`。 | 同一隔离候选的三种技能、接口 P95 和真实队列已出图，浏览器对照通过。持续失败与本地 HTTPS 告警送达由 2026-11-18 实际时间演练覆盖；剩正式阈值评审确认与负责人收件。运维负责人。[面板实测](delivery-runtime.md#第-10-课运行观测面板41-部分) |
| L10-F05 | 4.1，规则、`tests/unit/test_alert_delivery.py`、`tests/integration/test_alert_receiver.py` 和 `tests/integration/test_alert_https.py` 核对缺样、TLS、回执和重试。 | 本地 HTTP/TLS 接收端与实际命令回归通过。持续故障演练证据见实际时间演练行；剩正式阈值、负责人收件与正式收件通道登记。运维负责人。[HTTPS 复验](delivery-runtime.md#2026-11-18-本地-https-命令行复验) |
| L10-N05、L10-F05 的轮询衔接 | `tests/unit/test_alert_watcher.py` 和既有 HTTPS 集成核对自动评估、未确认重试及恢复顺序。 | 注入时间回归、一轮真实 TLS 命令和下行的实际时间演练通过。[轮询入口](delivery-runtime.md#第-10-课告警轮询入口41-部分) |
| L10-N05、L10-F05 的实际时间演练 | `tests/drills/test_skill_alert_drill.py`，隔离 MySQL、真实应用入口、固定故障替身与本地 HTTPS。 | 690.43 秒演练通过，53 次失败和 33 次成功，1 次拒收后重试确认及恢复确认。正式负责人收件与阈值待确认。[实际取证](delivery-runtime.md#2026-11-18-实际结果) |
| L10-N06、L10-F06 | 4.2 同口径两轮，按提交、查询、检索和消费吞吐核对饱和与改进。 | 两轮有效测量通过。最初环境与夹具失败保留，未纳入对照。性能实施人。[压测取证](bench.md) |
| L10-N07 | `tests/browser/teaching.mjs`、`candidates.mjs` 实测登录、候选题 202 与三态、停询、刷新、交卷及换班。Kafka 投递和七列技能审计由各自集成回归覆盖。 | 2026-11-19 复跑退出 0（1 项、36.62 秒）。七列审计定义经课程来源核对（操作人、操作时间、操作类型、操作对象、结果状态、技能标识、用量与耗时）；候选题链路不写操作审计行，缺技能标识与用量耗时列，连同作业 202 等价登记设计表与最终验收 1.5，4.3 保持未完成。教学实施人、复验同伴。 |
| L10-F07 | `tests/browser/test_teaching.py` 验证未登记来源访问及合法来源跨班/缺失对照。安全预检集成验证服务器对错误来源返回 403/1200。 | 自动化通过。同源正向成功，跨来源读写被浏览器拦截，非本班与不存在的讲义公开响应相同。教学实施人。 |
| L10-F08 | [试用反馈](feedback.md)记录脱敏会话代号、接口、实际、预期与处置。最终验收 4.5 核对三名真实使用者。 | 记录结构已准备，真实试用未执行。验收人。 |
| L10-N08、L10-F09 | 5.1–5.4 和最终验收，在同一候选综合判定、独立复验、签署和返工。 | 未执行。验收人和复验同伴。 |

课程差异统一交最终验收 1.5。当前同源 Cookie、正式交卷 201、内部规则评分和教师审题的证据可供走查。Bearer Swagger、作业 202、独立批改写入和教师改分等价暂无课程方结论。[课程差异](../openspec/changes/2026-11-04-define-lesson-10-acceptance/design.md#需确认的课程行为)
