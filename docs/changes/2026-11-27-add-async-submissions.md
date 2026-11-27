# 2026-11-27 学生异步提交三状态

## 变更说明

本变更把学生正式交卷从同步 `201` 调整为持久 `202` 受理和本人任务轮询，保持规则评分、唯一提交、答案开放、教师改分与班级隔离边界。规划和实施以 [OpenSpec 变更](../../openspec/changes/2026-11-27-add-async-submissions/proposal.md)为准。

## 验证记录

### 任务 1.1：规划与旧行为基线

| 命令 | 实际结果 |
| --- | --- |
| `openspec validate 2026-11-27-add-async-submissions --strict` | 退出 0，proposal、design、spec、tasks 共 4/4 产物齐备。 |
| `uv run --locked pytest -q tests/api/test_teaching.py -k 'SB_N01 or SB_B01 or SB_F04'` | 退出 0，1 项通过、28 项未选择；固定当前提交接口为 `201/0`、只返回提交标识和受理时间且不提前返回成绩。 |
| `uv run --locked pytest -q tests/integration/test_compose.py -k RT_N01_RT_F03_RT_B01_RT_B04_cold_start_and_recovery` | 首轮未进入测试：Docker Hub 拉取锁定 Qdrant 镜像时网络超时，1 项 setup error；不是业务断言失败。 |
| `CAMPUSCLAW_TEST_DOCKER_MIRROR=docker.m.daocloud.io uv run --locked pytest -q tests/integration/test_compose.py -k RT_N01_RT_F03_RT_B01_RT_B04_cold_start_and_recovery` | 同标签和摘要的隔离镜像来源复跑退出 0，1 项通过、12 项未选择，253.48 秒；真实 MySQL/Qdrant 路径固定同步提交、事务评分、幂等、失败回滚、答案开放、并发唯一性及恢复基线。 |

本阶段只记录旧行为，尚未把 `201` 改为 `202`。真实课程模型不适用于确定性规则评分，未调用模型；人工评审未执行。

### 任务 2.1：0019 只增任务结构

新增 `quiz_submission_jobs`，以参与者复合外键和每人每测验唯一约束固定归属及单任务边界，以唯一预分配提交标识衔接正式表。任务仅在处理中保存作答副本，成功状态将副本置空；租约、尝试次数、稳定失败码及时间字段均有界。数据字典登记归属、留存、备份恢复、排空回退和合成物理降级协议。

| 命令 | 实际结果 |
| --- | --- |
| `uv run --locked pytest -q tests/unit/test_submission_jobs.py` | 退出 0，8 项通过；覆盖确定性评分、重复恢复、资源变化失败、空队列及丢失租约。 |
| `CAMPUSCLAW_TEST_DOCKER_MIRROR=docker.m.daocloud.io uv run --locked pytest -q tests/integration/test_compose.py -k ASJ_data_migration` | 首轮迁移和建表成功，但测试误写既有改分表名，兼容断言失败；修正为真实表名后复跑退出 0，1 项通过、13 项未选择，23.36 秒。验证空库、重复升级、0018 旧结构仍在、合成降级后旧表保留及重新升级。 |
| `uv run --locked ruff check ...`、`ruff format --check ...` | 受影响 Python 文件检查通过；一次格式检查发现新迁移脚本需换行，自动格式化后复核通过。 |

生产数据库未执行迁移或降级；所有数据验证只使用 `campusclaw_test_` 隔离合成库。真实备份恢复不在本次本地迁移用例内，正式候选恢复检查仍待任务 3.3。

### 任务 2.2、3.1：worker 与 202 受理

正式交卷现持久写入本人任务，返回 `202`、稳定任务/提交标识和 `Location`。独立 worker 以 `SKIP LOCKED`、租约令牌和最多五次领取完成确定性评分；成功事务唯一写入正式提交、规则结果和原有审计，并清空任务作答副本。本人可读取最小任务投影；教师、匿名、同班他人、外班和不存在资源按各自认证或同构隐藏规则处理。

| 命令 | 实际结果 |
| --- | --- |
| `.venv/bin/pytest -q tests/api/test_teaching.py tests/unit/test_submission_jobs.py` | 退出 0，38 项通过；覆盖 202/Location、角色拒绝、确定性评分、重复恢复、资源变化失败、空队列及丢失租约。 |
| `CAMPUSCLAW_TEST_DOCKER_MIRROR=docker.m.daocloud.io .venv/bin/pytest -q tests/integration/test_compose.py -k RT_N01_RT_F03_RT_B01_RT_B04_cold_start_and_recovery` | 首次执行 1 项失败、13 项未选择，197.58 秒。两个 worker 同时领取时，领取前的耗尽任务范围更新触发 MySQL 1213 死锁；隔离项目自动清理。改为在同一 `SKIP LOCKED` 有序领取循环内逐条终结耗尽任务后复跑退出 0，1 项通过、13 项未选择，258.29 秒。补本人最小投影及同班他人/外班/不存在任务同构断言后的末次复跑仍退出 0，1 项通过、13 项未选择，257.88 秒。覆盖 8 名学生集中受理、双 worker 排空、唯一提交/评分、事务故障恢复、worker 暂停与恢复、Qdrant 中断且 Kafka/模型未启动时继续规则评分。 |

上述真实回归使用合成隔离库和固定课程数据，不调用真实模型。生产进程退出演练未执行；隔离 Compose 中实际停止并重新启动 `submission-worker`，恢复后任务排空。

### 任务 3.2、3.3、4.1：页面、运行入口与契约

测验页保存每份测验的提交幂等键，显示待处理、处理中、成功和失败；处理中持续轮询，终态停止，失败仅以原键重试。Compose、开发默认入口和预验收状态纳入独立 `submission-worker`，不发布端口，也不依赖 Qdrant、Kafka或模型。空闲 worker 仅记录各状态数量与最老未完成秒数，不记录作答内容。

| 命令 | 实际结果 |
| --- | --- |
| `CAMPUSCLAW_TEST_DOCKER_MIRROR=docker.m.daocloud.io .venv/bin/python scripts/check_pytest.py -q -s --tb=short tests/browser/test_teaching.py` | 页面初次迁移后退出 0，1 项通过，44.79 秒。增加文件闸门后复跑退出 0，1 项通过，44.93 秒；真实 Chromium、HTTPS 和 MySQL 依次观察失败重试投影、待处理、刷新仍待处理、处理中、成功及重复点击仅一个 POST。 |
| `.venv/bin/pytest -q tests/api/test_openapi.py tests/api/test_teaching.py tests/unit/test_submission_jobs.py` | 退出 0，42 项通过；OpenAPI 将正式提交登记为 202，受影响 API 和 worker 单元回归通过。 |
| `.venv/bin/python scripts/scenario_trace.py 2026-11-27-add-async-submissions` | 退出 0，新增 9 个场景均映射到真实 pytest/Compose/浏览器入口及实际断言。 |
| `openspec validate 2026-11-27-add-async-submissions --strict` | 退出 0，严格校验通过。 |

README、数据字典、产品页面状态、第 10 课课程差异表、最终验收就绪表和场景映射已同步。作业 202 与任务轮询不再列为等价缺口；同源 Cookie、直接评分写入及 H5 七列审计语义仍待课程方或人工验收确认。

### 任务 4.2：完整回归与 Harness 自审

本组按 `project-add-tests` 读取本变更 spec/design/tasks、安全、测试及数据规范，把 ASJ-N01、B01–B02、F01–F06 映射到 API、单元、真实 MySQL/Compose 和浏览器断言。测试只使用合成 A/B 班、隔离库和临时容器；未访问生产数据。未临时破坏生产实现；双 worker 死锁由真实并发测试先红发现，修复后以同一断言复测。

| 命令 | 实际结果 |
| --- | --- |
| `make check CHANGE=2026-11-27-add-async-submissions` | 第一次在 Trivy 数据库下载阶段连续无进度，人工中断，未计通过。用 DaoCloud 获取同一 `aquasec/trivy-db:2` 数据库后再次执行：静态、598 项单元/API、4 项启动、秘密及依赖扫描通过，但 Docker Hub 的锁定 Qdrant 摘要拉取超时导致 14 项 setup error，另 3 项通过；没有业务断言失败。 |
| `CAMPUSCLAW_TEST_DOCKER_MIRROR=docker.m.daocloud.io make check CHANGE=2026-11-27-add-async-submissions` | 首轮真实集成为 15 通过、2 失败，754.31 秒；失败原因是默认 `submission-worker` 与测试内两个受控 worker 竞争排空，业务结果正确但受控计数小于 8。将暂停/恢复收进共享验证函数后，两个原失败场景定向复跑 2 通过、12 未选择，195.86 秒。末次完整复跑退出 0：静态/规约/分层/场景/OpenAPI 检查通过，598 项单元/API、4 项启动及 17 项真实集成/浏览器通过，集成部分 815.91 秒；全历史秘密扫描无发现，锁文件和候选镜像高危/严重漏洞均为 0。 |

Harness 七类核查：

| 类别 | 手段、对象与判据 | 结果 |
| --- | --- | --- |
| 接口入口 | 对照 OpenAPI、Flask 路由、策略表及 202/Location/任务 GET；参数、角色和同构隐藏由 API/真实集成断言 | 通过 |
| 业务逻辑 | 对照任务状态、重放、截止、刷新恢复、成功后统计；单元、浏览器和真实 MySQL 判据一致 | 通过 |
| 数据库 | 检查参与者外键、唯一任务/提交、事务评分、租约条件更新、双 worker、迁移/合成降级 | 通过；生产迁移未执行 |
| 公共函数 | 复核 `TeachingRepository` 与 `SubmissionJobWorker` 契约，运行全部单元/API 回归 | 通过 |
| 错误处理 | 复现受理数据库失败、评分事务失败、资源变化、租约恢复和依赖源超时；公开响应不含内部异常 | 通过；外部镜像超时按失败与复测分别记录 |
| 安全 | 当前数据库身份与班级归属、本人任务最小投影、答案开放、秘密扫描及高危依赖扫描 | 通过；专项 `make check-security` 归 4.3 |
| 性能 | 真实 8 人集中提交记录受理 P95，并核对排空后 8 份唯一结果；未执行生产容量压测 | 隔离样本通过，生产容量不外推 |

AI 提示词、模型、检索参数及技能行为未改变，`project-prompt-eval` 不适用；本地未做真人体验、跨机器复验或人工批准。

### 任务 4.3：安全门禁、候选与评审准备

本组按 `project-review` 读取本变更全部规划产物、评审规范和实际差异，核对任务、文档、权限、数据副本、命令与失败记录。约束文件的修订只更新已实现的作业 202 现状和剩余验收缺口，没有删除断言、降低门禁或自填人工批准。

| 命令 | 实际结果 |
| --- | --- |
| `make check-security SECURITY_CANDIDATE=2266898...` | 首轮非零：历史、工作区和依赖为 0 发现，但前端、日志及两个镜像资产缺失，四项 exit 2；不计通过。随后以 `CAMPUSCLAW_SECURITY_ASSETS=reports/security-assets-2266898 ... -k security_precheck` 采集同提交资产，1 项通过、13 未选择，39.53 秒；安全门禁七范围全部 exit 0。 |
| `.venv/bin/python -m scripts.build_candidate 2266898...` | 首次因本机缺 buildx 插件未开始；安装 Ubuntu `docker-buildx 0.30.1` 后，第二次在 Python 包源连接超时；重试成功构建镜像，但启动阶段因工具没有依赖镜像代理参数而访问 Docker Hub 超时。新增显式 `--mirror-host`，复用锁定摘要转换，相关单元 20 项通过。 |
| `.venv/bin/python -m scripts.build_candidate 83ebe65... --mirror-host=docker.m.daocloud.io` | 退出 0。app 镜像摘要 `sha256:1da2c141...e920f`、检查 5 层；MCP 镜像摘要 `sha256:74df8391...62e4b`、检查 4 层。app、submission-worker、MCP、MySQL、Qdrant 均健康，运行版本与提交一致，`/live`、`/health` 均 200，结束后隔离容器和卷已清理。 |
| `CAMPUSCLAW_SECURITY_ASSETS=reports/security-assets-83ebe65 ... -k security_precheck` | 最终提交资产采集退出 0，1 项通过、13 未选择，39.33 秒。 |
| `make check-security SECURITY_ASSETS=reports/security-assets-83ebe65 SECURITY_CANDIDATE=83ebe65...` | 退出 0；可达历史 391 提交、工作区、前端、日志、app 与 MCP 镜像秘密均为 0，锁定依赖 High 0、Critical 0，漏洞库更新时间为 2026-11-27。 |

交付自检结论：规约与代码范围通过，权限和答案边界通过，迁移/回退证据通过，README、产品清单、数据字典和课程差异同步通过，自动化门禁与候选启动通过。真实课程模型评测不适用；生产迁移、生产容量、真人体验、跨机器复验未执行。实际同伴代码评审、PR 必需检查和最终真人验收待执行，助手自检不构成人工批准。

## 评审结论

任务 1.1、2.1、2.2、3.1–3.3、4.1 和 4.2 已完成；4.3 的安全门禁、候选镜像与评审准备已完成，分支推送、独立 PR 及远端必需检查尚待执行。实际同伴代码评审和最终真人验收未执行。
