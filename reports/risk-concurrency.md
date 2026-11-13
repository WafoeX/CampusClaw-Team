# 异步教学并发复核

2026-11-13，候选源码 `4aa4953`。使用隔离 MySQL 8.4、Kafka 4.1.2、合成账号和固定模型替身。`uv run --locked python scripts/check_pytest.py -q -s --tb=short tests/integration/test_compose.py -k 'real_kafka or transactions_without_broker'` 退出 0，2 项通过，88.76 秒。

| 手段 | 对象和判据 | 实际 |
| --- | --- | --- |
| 线程屏障、真实 MySQL | 八名学生同时正式交卷，提交和评分各只生效一次 | 8/8 返回 201，8 条有效提交，P95 233.43 ms。同人同键返回原提交，新键返回 409/1401。 |
| 暂停及恢复消费者、读取 Kafka offset | 已提交结果在消费位置重放后仍唯一 | 同事件两次投递、两个 offset、一个成功批次。 |
| 受理与完成独立计时 | 教师发起候选题 | 22 次 202，受理 P95 27.21 ms。完成样本 5531.17 和 71.78 ms，P95 5258.20 ms，较慢样本含故障注入。 |

样本仅支持隔离环境的行为验证。上一轮真实模型结果见[异步教学交付证据](../docs/changes/2026-11-04-add-async-teaching-workflows.md)。
