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

## 评审结论

任务 1.1 的规划与基线证据齐备，可以进入数据结构和 worker 实施。最终交付、自检、人工评审及最终真人验收尚未执行。
