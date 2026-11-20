# 候选题任务审计变更证据

## 变更说明

本次建立 `2026-11-19-add-teaching-job-audit` 的 proposal、能力规约、设计和任务清单，供第 10 课 L10-N07 技术缺口的后续实现及人工评审使用。现有候选任务可返回 202、轮询状态，但没有与班级操作审计关联；规划保留正式交卷 201 契约，不虚构技能 ID，不预先判定课程作业链路等价。PR 门禁发现新规格缺少场景实现状态声明后，在 `tests/scenario-map.json` 登记为 `planned`；未修改应用代码、迁移、实际测试用例、主干或既有门禁。

按 `openspec-propose` 读取了 `AGENTS.md`、`README.md`、OpenSpec 配置、候选任务服务/仓储、worker、模型适配器、审计接口与 0013/0015 迁移，生成四类规划文件；按 `project-review` 读取规划文件与安全开发、AI 应用、数据、评审规范，核对授权范围、失败路径、数据兼容和评审状态。`project-data-change` 与 `project-add-tests` 留待实施相应任务时调用，本次没有假称迁移或测试已完成。

## 验证记录

| 项目 | 实际结果 | 状态 |
| --- | --- | --- |
| `openspec context --json`、`openspec status --change 2026-11-19-add-teaching-job-audit --json` | 定位仓库 OpenSpec 根目录；proposal、specs、design、tasks 均为 `done`，规划集合完整 | 通过 |
| `openspec validate 2026-11-19-add-teaching-job-audit --strict` | 退出码 0，变更有效 | 通过 |
| `openspec validate --all --strict` | 退出码 0，13 个变更通过、0 失败；其他旧变更有归档提示信息 | 通过 |
| `git diff --check` | 退出码 0；本次新增文件提交后再复核差异 | 通过 |
| PR #64 初始两次 CI `make check` | 作业 `135636288316` 与 `135639059983` 均在 `scripts/scenario_trace.py` 报“规格未声明实现状态”，退出码 2；此前 OpenSpec、格式、lint、分层检查通过 | 失败，已定位并修正声明 |
| PR #64 初始两次 CI `make check-security` | 两次通过；后续镜像构建因 `make check` 未通过而跳过 | 通过 / 依赖跳过 |
| `make check-static` 复测 | 初次本地执行因 uv 缓存目录无写入权限退出 2，未运行到场景追溯；获授权复跑退出码 0，含 OpenSpec 13/13、格式、lint、分层、场景追溯及接口清单 | 通过 |
| 复测 CI `make check`、应用 pytest、MySQL/Kafka、H5 浏览器、迁移和恢复演练 | 场景状态修正提交前未执行；应用行为留待 tasks 对应实现组 | 未执行 |

规约场景包含正常受理与重放、用量缺失、非法输入、跨班和学生拒绝、重复消息/旧租约、审计存储故障、撤权与来源失效、到期及恢复。每项实施任务均写明后续可观察验证方式；当前场景为验收约定，并非运行结果。

## 评审结论

规划文件齐备、严格校验通过，属于可提交评审的规划版本。对照 SEC-02–04、SEC-11、AI-07/10、DATA 留存与副本规则、REV-07–09：服务端班级过滤、跨班同构、去内容、原子性、90 天清理及迁移回退均已列为实施约束；未发现本次规划文件放宽门禁或修改现行授权。应用行为、性能和课程方等价性仍未验证；第 10 课 4.3 与最终验收 1.5 保持未完成。OpenSpec 属约束文件，依据 REV-08 待实际评审人复核；助手自检不构成人工批准，也不授权合并。

## 第 1 组：数据契约与迁移（2026-11-20）

### 变更说明

基于已合并的 PR #64 与 `main` `19f2066` 实施 tasks 1.1–1.2。`0016_teaching_job_audit_data` 只增加任务用量列及配对约束、扩展审计终态结果、增加班级内对象查询索引；旧任务/审计不回填。更新运行表定义和数据字典，增加一次性 Compose/MySQL 迁移回归，不改变 HTTP 或 worker 行为。`project-data-change` 以本变更的任务、0012/0013/0015 结构、数据字典及 DATA/BE/OPS/SEC 规则核对归属链、唯一约束、留存、副本和回退；`project-add-tests` 依 TEST-04/06/07/12 增加真实 MySQL 正向、失败及边界断言；`project-review` 核对本组任务及证据。

数据归属链为任务 `class_id/creator_id` 到班级和账号、审计 `class_id/actor_id` 到当前身份；审计请求标识唯一，新增索引不代替查询授权。新增字段只在 MySQL 与其备份，未新增题干/答案副本、文件、向量或缓存。任务与审计分别按教学数据和 90 天去内容审计留存。应用回退保留 0016 扩展；物理降级测试仅在 `campusclaw_test_` 合成库运行。

### 验证记录

| 检查 | 实际结果 | 状态 |
| --- | --- | --- |
| `uv run --locked python scripts/check_pytest.py -q -s tests/integration/test_compose.py -k TJA_data_migration` | 首次因 Docker 未启动，在 fixture 建立前退出 1；启动 Docker 后复跑，发现测试脚本漏调用空库迁移，退出 1 | 失败并修复测试入口 |
| `uv run --locked python scripts/check_pytest.py -q --tb=short tests/integration/test_compose.py -k TJA_data_migration` | 首轮修复后 1 通过；增强无效用量断言时，MySQL 返回 3819 `OperationalError`，原断言只捕 `IntegrityError`，退出 1；修正为核对真实错误码后再次 1 通过 | 通过，保留失败与复测 |
| `uv run --locked python scripts/check_pytest.py -q --tb=short tests/integration/test_compose.py -k 'TJA_data_migration or JB_F05_mysql_job_transactions_without_broker'` | 一次性 Compose 启动，`/live` 与 `/health` 200；0016 空库升级、旧 0015 合成行保留、重复升级、用量约束拒绝、隔离降级与重升、既有候选任务事务回归；2 通过、8 未选，退出码 0 | 通过 |
| 审计恢复清理 | 合成过期审计行先由既有清理删 1 行，再重插同一备份行并清理删 1 行；这是行级恢复模拟，不是完整 MySQL 备份恢复演练 | 通过本组清理判据；完整恢复仍待最终演练 |
| `make check-static` | 首次因新增测试的导入顺序不符合 Ruff 而退出 2；调整导入后复跑退出码 0，OpenSpec 13/13、格式、lint、分层、场景追溯与接口清单均通过 | 通过，保留失败与复测 |
| `make check`、`make check-security`、课程人工等价性 | 本组提交前未执行；变更收尾及最终验收分别承担 | 未执行 |

PR #65 的首轮 CI：两套 `make check` 分别在作业 `136148847759`、`136149158688` 通过；后一套 `make check-security` 作业 `136149158331` 通过，镜像构建通过。前一套安全作业 `136148847501` 在拉取 MySQL 镜像时遇到 `toomanyrequests: Data limit exceeded`，测试未启动，不能记为代码通过。仅重跑失败作业后，`make check-security` 作业 `136154010558` 通过，镜像构建 `136154573902` 通过；PR 当前所需检查均通过。此次失败来自外部镜像拉取限额，没有修改测试、门禁或依赖版本来换取绿灯。课程人工评审仍未执行。

证据补充提交触发的 CI 中，一套 `make check` 作业 `136157980996` 通过，另一套 `136158001921` 在既有 `test_JB_QB_real_kafka_and_candidate_recovery` 中停止 Kafka 后立即检查容器退出状态时得到空值，退出码 2；同一提交的两套 `make check-security` 均通过。本机单独运行该 Kafka 恢复测试为 1 通过、退出码 0。仅重跑失败作业后，`make check` 作业 `136164621092` 通过，镜像构建 `136169086661` 通过。没有删除或修改该断言；此次时序失败仍保留为 CI 稳定性风险，后续若复现须单独定位。

### 评审结论

本组迁移、字典及受影响入口已有隔离真实依赖证据，tasks 1.1–1.2 标记完成。七类 Harness：接口入口与业务逻辑未改，按原候选事务回归；数据库由空/旧库、重跑、约束、降级核对；公共函数仅新增迁移内部 `_names` 并由重跑验证；错误处理核验 MySQL 3819 拒绝；安全核查班级键、无正文新副本及合成库限制；性能未做压测，新增索引的实际查询性能待第 3 组。README 无新增使用入口，保持现有阶段说明。OpenSpec 任务、数据字典和测试属于需人工复核文件；本次自检不是批准，PR 合并仍需真实门禁和同伴评审。课程 4.3 保持未完成。
