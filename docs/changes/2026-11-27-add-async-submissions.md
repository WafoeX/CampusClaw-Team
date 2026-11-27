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

## 评审结论

任务 1.1、2.1、2.2、3.1–3.3 和 4.1 已完成自动化实现与对应验证。完整双门禁、候选镜像构建、Harness 七类收尾和独立人工代码评审仍待 4.2–4.3；最终真人验收未执行。
