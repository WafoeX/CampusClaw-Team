# 教师改分优先

## 变更说明

课程第 10 课明确要求“教师改分优先”。本变更保留不可变规则评分，新增本班教师最终分覆盖、修订重放、当前记录与只增历史，并让学生开放后成绩、教师提交列表和班级平均分采用同一最终分。学生作业异步 `202` 与错题讲解技能不在本变更内。

## 数据变更记录

- 归属链：当前数据库教师 → 本班测验 → 本班正式提交 → 规则结果；客户端不提交班级或教师。`quiz_score_overrides` 以提交为主键及同班组合外键，`quiz_score_override_events` 以提交/修订唯一并关联当前记录。
- 原始 `quiz_results` 不更新。新增数据只有 MySQL 与 14 天轮转备份副本；无文件、向量、Kafka 或缓存副本。理由不进日志、检索、会话或 MCP，沿用教学个人数据学期结束后 30 天内清理要求；自动学期清理仍待上线责任登记。
- 0017 只增两表和提交复合唯一索引，无业务回填。应用回退保留两表并暂停改分；物理降级只允许合成库，删除新增两表但保留正式提交和规则评分。恢复后须核对当前修订与事件最大修订一致。

## 验证记录

- `uv run --locked openspec validate 2026-11-25-teacher-score-override --strict` 退出 0。
- API 测试先运行 `-k TSO`，因入口尚不存在得到 7 个 404、退出 1；实现后同组 7 项通过。服务/API/投影定向 37 项通过；首次 cookie 夹具格式错误导致 6 项 401，改为合法合成 Cookie 后复测通过。
- `uv run --locked python scripts/check_pytest.py -q --disable-socket tests/unit tests/api` 退出 0，569 项通过。
- 补齐并发、开放前投影和场景映射后，`make check-static CHANGE=2026-11-25-teacher-score-override` 退出 0；`make check-test CHANGE=...` 退出 0，571 项单元/API 与 4 项启动检查通过。
- 首次真实 Compose/MySQL 回归因把包含不同 `request_id` 的两份 404 整体比较而退出 1；按既有同形口径改为比较 `code/message/data` 后，同一命令退出 0。加入两名同班教师并发后再次运行退出 0，1 项通过；并发结果为一笔 200、一笔 409，当前修订为 2，只增事件修订为 1、2，操作者均为当前班教师。实际覆盖 0017 空库升级、重复升级、降至 0014 后重升、规则评分保留、学生拒绝、跨班与不存在同形、等价重放只一条事件、学生/教师/平均分使用覆盖分，以及事件插入故障时当前记录整笔回滚。
- 实际命令：`CAMPUSCLAW_TEST_DOCKER_MIRROR=docker.m.daocloud.io uv run --locked python scripts/check_pytest.py -q -s tests/integration/test_compose.py -k TSO_real_mysql`。依赖镜像保持仓库完整摘要，隔离容器和卷在结束后删除。
- 390px Chromium 回归已加入教师页面改分断言。本机实际执行 `... tests/browser/test_teaching.py` 时，隔离浏览器镜像在 `apk add --no-cache chromium` 的 900 秒上限处超时，仅安装到 44/233 个包，pytest 1 项失败；业务浏览器步骤未开始。未提高超时、跳过断言或把该结果计为通过，待 PR 独立 CI 复跑。

## 评审结论

服务端和真实 MySQL 主路径已通过，本机浏览器构建超时使浏览器回归未通过；完整门禁、Harness 七类自审、远端 CI 和人工评审仍待完成。没有真实模型依赖，不把本次结果写成学生作业 `202`、错题讲解或项目最终验收通过。
