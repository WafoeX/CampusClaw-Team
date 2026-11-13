# 异步教学事务与恢复复核

2026-11-13，候选源码 `4aa4953`。与[并发复核](risk-concurrency.md)同轮实测，2 项通过。

- 注入发件写失败，候选受理返回 `503/1500`，任务无新增。注入评分结果写失败，正式交卷和结果同时回滚，恢复后只保留一份评分。
- 消费者未运行时，候选受理返回 202，任务可读为 pending，任务与发件记录均存在。Kafka 停机时人工交卷仍返回 201，保持同一评分事务。
- 目标 topic 不可用时没有成功回执。真实回执丢失后使用同一事件标识重投。消费者在数据库提交后、提交 offset 前中断，重启后读到同事件两次，数据库仅一批草稿和一条结果。
- 另一条候选经实际租约进入 running，旧执行者回写被拒，新执行者完成后为 succeeded。投递器和 worker 在 broker 重启后排空夹具任务并正常退出。
- 课程异步作业 202 等价待确认。当前 202 是教师候选题，学生正式交卷返回 201。现有复跑能观察候选任务状态及重放结果。课程要求的异步作业入口和跨该入口的无孤儿演示未取得。

补跑 `uv run --locked python scripts/check_pytest.py -q -s tests/integration/test_compose.py -k real_kafka` 退出 0，1 项通过。新增候选正常路径在消费者尚未处理时完成 202 受理并可读 pending，经真实 Kafka 收到记录后取得租约并可读 running，提交结果后可读 succeeded。发件 1 条、结果 1 条、无对应发件的任务 0 条，下一次 relay 无待投递项。故障重投的两条 offset 单列在上面。

## 3.1 收尾复验

在合入 PR #29 的 `d50e91b` 上运行 `CAMPUSCLAW_REAL_CANDIDATES=1 uv run --locked python scripts/check_pytest.py -q -s --tb=short tests/integration/test_compose.py -k 'real_kafka or transactions_without_broker'`，退出 0，2 项通过。普通路径记录合成任务 `bf46319b-2aa3-413f-9736-333e7f7f4ca0`：教师受理 HTTP 202，Location 指向该任务，轮询依次得到 pending、running、succeeded。继承既有回滚、重放断言，新增断言同一事件仅一条成功投递回执。实测发件 1、结果 1、孤儿 0；故障重投两次仍只生效一批。真实课程模型的独立样本用时 2809.68 ms，返回带出处的待审草稿。

技术复核完成。课程异步作业 202 与 SEC-04 独立批改写入口的等价性仍由最终验收 1.5 确认。普通路径 202 来自教师候选题入口；学生正式交卷按现有同步契约返回 201。
