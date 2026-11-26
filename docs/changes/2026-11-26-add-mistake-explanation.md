# 独立错题讲解变更证据

变更：`2026-11-26-add-mistake-explanation`。基线为已合并 PR #75、#76 的主干提交 `580c4f0bfb2061ed6659938cb25808137025eefa`。本记录区分确定性工程验证、真实依赖验证与尚未执行的真实模型/人工验收。

## 变更说明

- 新增 `mistake_explanation` 内置技能。模型只能选择 `diagnose`、`locate`、`retry`、`verify`，服务端验证后渲染固定中文提示，引用固定为空。
- 新增本人已开放错题的幂等会话启动端点。开场只含题干和本人错误作答；教师、跨班、未提交、未开放、正确题目及不存在资源按规约拒绝或隐藏。
- 错题页支持启动、SSE 增量、继续追问、取消和同轮重试。浏览器不发送标准答案字段，正文使用 `textContent`。
- 0018 只增迁移扩展内置技能约束；同步新建库、数据字典、OpenAPI、产品页面状态与场景映射。
- 隔离浏览器和流式代理补用与 Compose 相同的摘要锁定镜像来源；没有改变生产镜像或应用目标。

## 技能调用

| 技能 | 输入与读取 | 动作与结果 |
| --- | --- | --- |
| `openspec-propose` | 用户要求进入验收和安全功能扩展；读取 AGENTS、README、八规范及第 10 课缺项 | 建立 proposal、design、spec、tasks，严格校验通过 |
| `openspec-apply-change` | `2026-11-26-add-mistake-explanation` | 按任务组实现技能、迁移、入口、页面与回归 |
| `project-add-tests` | 新能力场景、API、技能、浏览器和真实依赖入口 | 补正常、参数、授权、隐藏、依赖故障、注入、畸形结构和短答案回归 |
| `project-data-change` | 0018、fresh schema、迁移清单和数据字典 | 核对只增兼容、合成降级前置和真实 MySQL 空库/旧库/重入/降级 |
| `project-prompt-eval` | 通用解题引导基线与独立错题讲解固定集 | 基线 29 项通过；修改后固定集通过；真实课程模型因无密钥未执行 |
| `project-review` | 规约、代码、测试、文档和门禁结果 | 七类自审见下表；人工评审保持待执行 |

## 验证记录

| 范围与命令 | 实际结果 |
| --- | --- |
| `uv run --locked pytest -q --disable-socket tests/api/test_openapi.py tests/api/test_teaching.py tests/unit/test_skills.py tests/unit/test_teaching_insights.py` | 退出 0，67 项通过 |
| `CAMPUSCLAW_TEST_DOCKER_MIRROR=docker.m.daocloud.io uv run --locked python scripts/check_pytest.py -q -s --tb=short tests/integration/test_compose.py -k ME_data_migration` | 退出 0，1 项通过、12 项未选择；真实 MySQL 覆盖空库、已有库、重复升级和合成降级 |
| 同上，`-k TSO_real_mysql` | 退出 0，1 项通过、12 项未选择；覆盖本人错题上下文、缺配置、权限/隐藏、幂等和事务失败 |
| 同上，`-k cold_start_and_recovery` | 修复镜像来源后退出 0，1 项通过、12 项未选择，257.06 秒；含 AI 固定槽位、短答案、注入、畸形结构、历史迁移、代理和恢复链路 |
| `CAMPUSCLAW_TEST_DOCKER_MIRROR=docker.m.daocloud.io uv run --locked python scripts/check_pytest.py -q -s --tb=short tests/browser/test_teaching.py` | 退出 0，1 项通过，43.82 秒；真实 Chromium 覆盖启动、增量、追问、取消和重试 |
| `uv run --locked pytest -q --disable-socket tests/unit/test_dependency_sources.py tests/unit/test_acceptance_environment.py` | 退出 0，15 项通过；镜像来源保持完整摘要并拒绝路径、凭据和未锁定镜像 |
| `uv run --locked python scripts/scenario_trace.py`、`uv run --locked openspec validate 2026-11-26-add-mistake-explanation --strict` | 均退出 0；9 个 ME 场景全部映射到实际 pytest 或隔离脚本断言 |
| `CAMPUSCLAW_TEST_DOCKER_MIRROR=docker.m.daocloud.io make check` | 退出 0；20 份 OpenSpec、Ruff、分层/场景/API 清单、587 项单元/API、4 项启动、秘密扫描、锁定依赖扫描及 16 项真实依赖/浏览器通过；集成 730.98 秒，HIGH/CRITICAL 为 0 |
| `CAMPUSCLAW_SECURITY_ASSETS=reports/security-assets-mistake-explanation-31f146b ... -k security_precheck` | 提交 `31f146b57665e05bc3fe3dd9f840dd12e85b9414` 资产采集退出 0，1 项通过、12 项未选择，39.80 秒 |
| `make check-security SECURITY_ASSETS=reports/security-assets-mistake-explanation-31f146b SECURITY_CANDIDATE=31f146b57665e05bc3fe3dd9f840dd12e85b9414` | 退出 0；历史、工作区、前端、日志、应用和 MCP 镜像秘密均为 0，依赖 HIGH/CRITICAL 为 0；数据库更新时间 `2026-11-26T13:14:47Z` |

### 失败与复测

1. 迁移脚本首次在空库缺少账号前置，补入仅用于合成库的最小账号后通过；没有把生产数据作为迁移前提。
2. AI 脚本先后发现短答案断言误把固定文案中的“标准答案”术语当泄露、追问没有关键词证据而未进入模型路径、合成技能阻断历史降级。分别改为核对真实短值、提供合成证据、在本段结束清理合成技能后通过。
3. 冷启动第一次在相关 AI 与教学脚本完成后，因流式 Nginx 代理直接拉取 Docker Hub 返回 125。补齐保留摘要的镜像来源及单元断言后，相同命令复测通过。
4. 浏览器首次因 Alpine 软件源 TLS 失败未进入测试；缓存镜像后暴露 MySQL 仍直连原来源，再补浏览器 Compose 镜像覆盖。随后发现 CDP 监听器未解包 `MessageEvent`，修正后完整复测通过。
5. `make check` 首轮在 Ruff 格式门禁发现技能文件两处换行不合规范；自动格式化并跑相关 30 项回归后修复。第二轮在 linked worktree 的秘密扫描发现 mirror clone 少复制另一个 detached worktree HEAD；改为复制公共 Git 引用和全部工作树 HEAD，完整扫描后无秘密。
6. Trivy 当天数据库从 `mirror.gcr.io` 与 GHCR 下载均长时间无数据；没有用过期数据库冒充结果。通过相同 schema/tag 的 Daocloud 代理取得 `2026-11-26` 数据库后，原判据扫描为 0。
7. 首次全量集成为 15 项通过、Kafka 项因后加载的 teaching Compose 仍直连 Docker Hub 超时。为 `kafka`、`kafka-topics` 增加保留摘要的后置覆盖；专项复测 `1 passed, 12 deselected in 105.57s`，随后聚合门禁 16 项全通过。

## Harness 七类自审

| 类别 | 手段、对象与判据 | 结果 |
| --- | --- | --- |
| 接口入口 | 对照 ME-N01/F01–F04 核路由、空 JSON、幂等键、角色和统一隐藏结果；API 与真实 MySQL 断言 | 通过 |
| 业务逻辑 | 核本人错误提交、答案开放、正确题排除、专用助手和重放不重复创建 | 通过；教学意图仍待人工确认 |
| 数据库 | 核班级/本人过滤、会话事务、0018 只增兼容、重入和受控合成降级 | 通过 |
| 公共函数 | 核技能选择、固定渲染和摘要锁定镜像函数；单元与既有回归 | 通过 |
| 错误处理 | 复现 400/1000、403/1200、404/1300、409/1400、503/1500、SSE 1501 | 通过 |
| 安全 | 核标准答案不进入模型答案字段、SSE、引用和持久正文；注入、跨班和短答案反例 | 自动化通过；专项人工安全评审待 PR |
| 性能 | 复用现有 SSE 容量和冷启动代理回归；本功能未新增独立吞吐目标 | 现有代理回归通过；真实体验归最终验收 |

## 评审结论

实现和适用自动化已形成 [PR #77](https://github.com/WafoeX/CampusClaw-Team/pull/77) 的可评审候选。当前没有课程模型密钥，因此真实模型调用、提示是否准确定位学生错因及真人体验均未执行；不能由固定替身结果替代。人工代码评审、PR 最新提交的 GitHub 门禁与最终人工验收尚未完成，不宣称已合并、已冻结或课程通过。
