# 第 10 课交付运行证据

## 本地候选构建与启动

2026-11-16，对源码 `a0c2a5afd5869ee19127392c294f32669d726e9c` 的 Dockerfile、应用、MCP 和锁文件运行 `uv run --locked python -m scripts.build_candidate "$(git rev-parse HEAD)"`，退出 0。使用本地 Docker Desktop 与 Buildx，Compose 从本次构建的标签加载，两个运行容器的镜像 ID 均和构建结果相同。

| 服务 | 镜像标签 | Buildx 输出摘要 |
| --- | --- | --- |
| 应用 | `campusclaw-skeleton:a0c2a5afd5869ee19127392c294f32669d726e9c` | `sha256:6f733c70d5add479eecb589e8f0af780d90dc3dd95e7cf46c6f9065d80abc0b5` |
| MCP | `campusclaw-mcp:a0c2a5afd5869ee19127392c294f32669d726e9c` | `sha256:1749150486fd70d8813b574e6b0b3a17a5898a2f2dae92eaa60ac88c4e40c8df` |

`/live` 和 `/health` 的 GET、HEAD 均为 200。`/health` 的 MySQL、Qdrant 均为 `ready`，运行版本为上述完整提交。独立 MCP 的容器健康探针通过。隔离容器和卷清理完成。

首次以宿主 Python 3.9 直接运行时，探针辅助模块所用的 `datetime.UTC` 无法导入，复跑改用仓库锁定的 Python 3.13。Buildx 首轮构建成功，但 Docker Desktop 的容器存储返回 OCI 索引摘要，缺少独立的镜像配置摘要字段。根据实际 Buildx 元数据和已加载镜像 ID 校验 OCI 摘要或配置摘要，复跑通过。摘要语义见 [Docker Buildx 元数据说明](https://docs.docker.com/reference/cli/docker/buildx/build/#metadata-file)。

## 首轮 CI 与依赖仓库限流

2026-11-16，推送候选 `13d6a3452301182128009459e0dbd166a7d00815` 的 `make check` 和 `make check-security` 均通过，随后构建和启动通过。应用镜像 `campusclaw-skeleton:13d6a3452301182128009459e0dbd166a7d00815` 的 OCI 摘要为 `sha256:4c2f975828faa9bb0613042715f55f426e22dbe2fa27984b717e2b4d94c0a30d`，MCP 镜像 `campusclaw-mcp:13d6a3452301182128009459e0dbd166a7d00815` 为 `sha256:5ac326732e36d568ee67f8c1c5567a37ae8b1d17cfd872f79ce8f9f02fe69944`。`/live` 和 `/health` 返回 200，运行版本与源码一致。[推送构建 43822312011](https://github.com/WafoeX/CampusClaw-Team/actions/runs/43822312011/job/133150295337)

同一分支的 PR 合并候选 `6f507db51dec20b124215cc0fad434fa7f5f9bf2` 两项门禁通过，应用与 MCP 构建成功，隔离启动拉取依赖时镜像仓库返回 `toomanyrequests: Rate exceeded`，构建作业退出 1。[首轮 PR 构建 43822443769](https://github.com/WafoeX/CampusClaw-Team/actions/runs/43822443769/job/133150766376)

修复后逐一预拉取 Compose 固定摘要的 MySQL、Qdrant 镜像。仅明确限流时在 10 秒及 30 秒后重试，重试耗尽或其他错误仍失败。启动使用本地已取得的镜像。限流后成功、持续限流、非限流错误 3 项断网回归通过。基于 `13d6a34` 的构建输入，按新脚本在本地实际构建、启动并复核版本，双探针为 200，临时容器和数据卷正常清理。

## 修复后推送取证（3.2）

2026-11-16，推送 `eb740998083c2c9186d3452404d6493a20aa92ec` 自动触发流水线 `43860255221`。`make check` 通过，12 项 OpenSpec、470 项单元/API、4 项启动和 8 项集成通过。`make check-security` 通过，两项完成后构建作业退出 0。[推送流水线](https://github.com/WafoeX/CampusClaw-Team/actions/runs/43860255221)

| 服务 | 镜像标签 | Buildx 输出摘要 |
| --- | --- | --- |
| 应用 | `campusclaw-skeleton:eb740998083c2c9186d3452404d6493a20aa92ec` | `sha256:7b82600984231ccd1edc1801ec7d5f48c41a6574538df6a9c0387a8dd1f47d25` |
| MCP | `campusclaw-mcp:eb740998083c2c9186d3452404d6493a20aa92ec` | `sha256:3a1c8511db6d53c3dff9304489d2f5c0f90729e73a8141a6f22389f0fe46c4a5` |

两个容器的镜像 ID 与构建结果一致。`/live` 和 `/health` 通过，`/health` 报告运行版本为 `eb740998083c2c9186d3452404d6493a20aa92ec`，MySQL 和 Qdrant 均为 `ready`。此次 CI 未出现限流重试，重试行为由断网用例验证。此组为流水线编排及成品验证，数据库结构与索引无改动，扩迁和物理回退不适用。[构建实测](https://github.com/WafoeX/CampusClaw-Team/actions/runs/43860255221/job/133277811400)

## 2026-11-17 运行镜像源码剥离（3.1 部分）

以 `bf854f9` 加运行镜像改动为构建输入，用随机测试标识 `d33db579107ef3b2b95a0c46b46dd62c38f04244` 构建隔离镜像。应用归档 5 层、MCP 归档 4 层，逐层扫描确认无项目 `.py` 和受检工具路径，两个字节码入口均存在。应用和 MCP 容器采用刚构建的镜像，`/live`、`/health` 的 GET 和 HEAD 均为 200，`/health` 版本和测试标识一致。正常运行后回收容器、网络和卷。

`uv run --locked python scripts/check_pytest.py -q --disable-socket tests/unit/test_build_candidate.py` 7 项通过，包含早期层写入源码、uv 或 ensurepip 后在后一层隐藏时仍失败的对照。扫描检查 Docker 导出归档而非容器合并视图。固定安全门禁另行检查同一候选资产中的凭据和依赖漏洞。

本地真实集成 8 项通过，311.93 秒，覆盖字节码镜像中的 0001–0014 迁移和旧库回退重升、MCP 与 Kafka。PR #41 的干净检出候选 `80e8f8cabfd3b8713c955fb660024936ba09fc3a` 两项门禁和构建作业均通过。应用镜像摘要为 `sha256:425d8a46c87a685e2743ee0265ff59c3f37749cf2e975d25361812bfac290c7f`，MCP 为 `sha256:b9e0a9e29ff6f217ae388a05452e417face3c8fa4444fefb3065ffd0102f9a66`。构建作业再次检查应用 5 层和 MCP 4 层，`/live`、`/health` 均为 200，运行版本与候选一致。[CI 构建日志](https://github.com/WafoeX/CampusClaw-Team/actions/runs/43914670990/job/133470099552)

## 2026-11-17 Compose 就绪与依赖故障（3.1 部分）

以 `05e4926` 加 Compose 改动执行 `uv run --locked python scripts/check_pytest.py -q --tb=short tests/integration/test_compose.py -k cold_start_and_recovery`。Compose 等待 MySQL 健康才启动应用，Qdrant 保留启动依赖和运行降级契约。应用容器探针使用 `/health`，`/live` 单独确认进程还在服务。

| 场景 | 隔离环境实测 |
| --- | --- |
| 冷启动 | MySQL 容器健康后启动应用，`/live`、`/health` 返回 200，运行版本和两项依赖状态通过核对。 |
| 运行镜像缺配置 | 将一次性应用容器的 `MYSQL_PASSWORD` 留空，进程退出 1，结构化诊断定位该配置键。 |
| MySQL 停止和恢复 | `/health` 返回 503、`/live` 返回 200，容器由 `healthy` 变为 `unhealthy`。恢复 MySQL 后 `/health` 为 200，容器重新 `healthy`。 |
| Qdrant 停止 | `/health` 返回 200 和 `degraded`，确定性教学流程继续通过。 |

首轮上述就绪与恢复断言已执行，后续已有 SSE 取消用例在终态前断开，测试退出 1。保持同一 Compose 和断言复跑，1 项通过、171.30 秒。原始结果保留在本机临时日志。入口运行中按就绪状态撤流仍需独立实证，3.1 保持待验收。

## 2026-11-17 HTTPS 入口撤流与恢复（3.1）

以 `8dcd9f0` 的运行制品为基线，在隔离 MySQL、Gunicorn 和仓库锁定的真实 NGINX 容器中执行 `uv run --locked python scripts/check_pytest.py -q --tb=short tests/integration/test_compose.py -k cold_start_and_recovery`。网关后台独立探测 `/health`，请求仅检查本地就绪标记。

| 检查 | HTTPS 实际结果 |
| --- | --- |
| 正常启动 | `/health` 为 `ready`，登录页返回 `200` 并带有应用的 `X-Request-ID`。 |
| 停止 MySQL | `/health` 返回 `503`，`/live` 返回 `200`。网关临时撤流，登录页返回 `503`，响应没有应用的 `X-Request-ID`。 |
| 恢复 MySQL | `/health` 回到 `ready`，登录页重新返回 `200` 并恢复应用请求标识。 |

首轮夹具在已挂载的只读目录内再挂载脚本，容器启动退出 `125`。修正为复制脚本至已有夹具目录。临时克隆保留旧 NGINX 配置时，新断言在登录页撤流处失败，退出 `1`，137.21 秒。当前网关配置通过全部冷启动、撤流、恢复及后续 SSE 回归，退出 `0`，1 项通过、147.99 秒。Compose 演示配置语法校验通过。原始日志仅保存在本机临时目录。

## 第 10 课技能观测数据源（4.1 部分）

候选基线为 `8b8a676`。应用日志中的 `skill_execution` 由本人会话的实际技能执行产生，按 `skill_id`、`status` 聚合，以 `completed_at` 进入时间窗。成功记录的请求 ID、技能 ID、完成时间及耗时与同一事务写入的第 9 课技能审计一致。操作审计继续走原有权限接口。

| 状态 | 触发条件 |
| --- | --- |
| `succeeded` | 技能结果及消息提交成功。 |
| `failed` | 流终帧为 1500 或 1501，且该尝试的终态已落库。 |
| `interrupted` | 客户端断开或其他未完成的流在终态落库时记录。 |

同一已完成请求的幂等重放不增加技能执行计数；未选中技能的会话不产生该事件。日志只记录运行元数据。数据库未确认终态、进程退出遗漏和日志采集故障可能缺样，缺样不能作为错误率为零的证据。

本轮交付数据源。三张面板、错误率时间窗与阈值、收件端、送达时限和恢复演练留待 4.1 后续取证。候选冻结和最终验收状态沿用任务清单。

## 第 10 课运行观测面板（4.1 部分）

运维在部署工作目录生成本地报告。沿用教学 Compose 扩展和环境配置，取同一候选的完整 `APP_BUILD_REVISION`，填写三个已登记的技能 ID。样本窗口使用带时区的 `OBS_START`、`OBS_END`，采用左闭右开区间，最长 24 小时。

```sh
set -o pipefail
mkdir -p reports/observability
docker compose -f docker-compose.yml -f docker-compose.teaching.yml --profile teaching \
  logs --no-log-prefix --since "$OBS_START" --until "$OBS_END" app teaching-relay |
  uv run --locked python -m scripts.observability_dashboard \
    --version "$APP_BUILD_REVISION" --start "$OBS_START" --end "$OBS_END" \
    --skill "$SKILL_ID_A" --skill "$SKILL_ID_B" --skill "$SKILL_ID_C" \
    > reports/observability/panel.html
```

成功后在本地浏览器打开 `reports/observability/panel.html`。面板按起始时刻每五分钟分桶，时间以 UTC 显示。

| 面板 | 采样与判据 |
| --- | --- |
| 技能调用量 | 按 `completed_at` 归属窗口。每条分线为一个已登记技能，成功、失败及中断均计入观测次数。 |
| 技能错误率 | 每个技能用该窗口 `failed / calls × 100%`。观测次数为零时标记无样本。 |
| 接口 P95 与待处理队列 | 接口采用已登记 `/api/v1/` 路由的响应准备耗时，按最近秩计算 P95。SSE 时长以技能事件单列。队列取每个窗口内最近一条投递器观测的 `pending` 数。已观测到空队列显示为 0，缺采样保留为空。 |

报告只含候选、技能 ID、时间窗与聚合数值，可展开数据表核对。生成文件沿用报告目录忽略规则。告警采用独立的滚动窗口和通知流程，阈值、收件端及送达恢复证据待后续验收。

### 2026-11-18 隔离面板实测

源码基线为 `5f3d99a`。用同一个隔离 Compose 候选 `00000000a0a24dff2a864d0986fb8a057f99c08d` 的技能终态、实际 Flask 接口日志和 Kafka 教学投递器日志生成报告。采用合成班级及固定模型替身。样本时间为 2026-11-18 00:11:01 至 00:11:22（Asia/Shanghai），落在一个不足五分钟的窗口内。

| 观测 | 实际值 |
| --- | --- |
| 三种技能调用量 | 3、1、1 次，其中第一种有 1 次失败、1 次中断。 |
| 三种技能错误率 | 33.33%、0%、0%。 |
| 接口 P95 | 8 条接口样本，25.29 ms。 |
| 教学队列 | 投递器实际观测到 20 项待处理。 |

在断网 Chromium 中核对图例切换、数值表和 1120／390px 两种布局。宽屏并排显示 P95 和队列，窄屏按同一顺序堆叠。脱敏报告和截图留在本机忽略目录 `reports/observability/`。

## 第 10 课告警规则评估（4.1 部分）

源码基线为 `fd42a9f`。离线命令 `uv run --locked python -m scripts.evaluate_skill_alerts` 接受面板命令相同的 `--version`、可重复 `--skill`、`--start` 与 `--end` 参数，从标准输入读取完整结构化日志。输出到运维控制的忽略目录，例如 `reports/observability/alerts.json`。

采用设计中初拟规则，每 15 秒评估一次此前五分钟的技能完成记录，窗口为左开右闭。至少 20 次调用且失败率严格大于 1% 时进入 `pending`；连续满足五分钟后进入 `firing` 并标记 `notification=required`。失败率回落进入 `normal`；不足 20 次调用进入 `no_data`，重置持续计时。样本不足单独记录，通知流程应继续核对告警的收件状态。相同候选、输入与时间范围可重复计算相同转换，调用者应保留转换时间作为后续投递幂等依据。

规则沿用技能完成时间与结果分类，输出只有候选、技能 ID、窗口口径、状态和计数。验证使用合成日志与注入时间，覆盖触发、恢复、缺样和阈值边界。初拟阈值与接收端配置待评审，真实连续失败、通知送达和恢复演练待执行，4.1 保持未完成。

## 第 10 课通知投递与回执（4.1 部分）

源码基线为 `9821161`。部署负责人登记收件端与负责人后，通过环境设置 `ALERT_RECEIVER_URL`、`ALERT_RECEIVER_TOKEN`、`ALERT_PANEL_URL`。两个地址采用 HTTPS，排除地址内凭据、查询和片段。令牌仅通过 Authorization 发送至配置的收件端。投递采用标准库 HTTPS，核验证书，每次请求超时五秒，重定向作为失败处理。

```sh
uv run --locked python -m scripts.deliver_skill_alerts \
  < reports/observability/alerts.json \
  > reports/observability/deliveries.json
```

每个触发事件及后继恢复事件通过候选、技能 ID、转换时间与状态生成稳定的 `event_id`，请求头 `Idempotency-Key` 使用该值。请求正文仅包含这些字段及面板链接。接收端须保存事件、按该键去重，并在重复请求时返回首次收件的同一回执。

接收端确认格式为 `{"event_id":"匹配请求","delivered":true,"received_at":"带时区的首次收件时间"}`，HTTP 为 200 或 201，正文至多 8 KiB。时间不得早于触发时间或晚于本机确认时间五秒以上。首次收件在触发后两分钟内记为 `delivered`，超过时限记为 `late`。网络故障、缺回执、错误标识或重定向记为 `failed`。命令逐项处理，任一失败或迟到均非零退出，输出仅含事件 ID、状态与已确认时间。失败后可使用同一报告重跑，最终结论结合接收端留存记录复核。

样本不足的转换保持待核对收件状态；恢复通知须在曾触发后出现 `normal` 才生成。本次使用环回 HTTP 合成接收端测试标准库传输，生产命令仅接受 HTTPS 配置。实名负责人、正式收件端、阈值确认及真实连续故障和送达演练仍待完成。

### 2026-11-18 本地 HTTPS 命令行复验

基于 `4f22f2b`，运行 `uv run --locked python scripts/check_pytest.py -q tests/integration/test_alert_https.py`。用临时生成的 localhost 证书、环回 TLS 接收端和独立命令进程验证真实 HTTPS；仅对子进程设置 `SSL_CERT_FILE` 指向本次临时证书，沿用证书和主机名校验。

| 检查 | 实际结果 |
| --- | --- |
| 未信任证书与主机名不匹配 | 命令退出 1、每项投递为 failed，接收端未收到 HTTP 请求。 |
| 正确信任与接收端 503 | 命令退出 1，保留失败且没有收件记录。 |
| 可信 TLS 但令牌错误 | 命令退出 1，接收端没有确认记录。 |
| 触发与恢复、重放 | 两轮命令都退出 0，回执相同，接收端仅留两条唯一事件。 |

日志样本由注入时间生成，实际 TLS 传输使用当前时间。恢复转换是合成夹具的显式输入。首次 1 项通过、1.22 秒；临时将成功退出码期望改成 1 时，测试退出 1，恢复后退出 0、1 项通过、1.27 秒。真实模型持续故障及正式负责人收件仍待 4.1 验收。

## 第 10 课告警轮询入口（4.1 部分）

基于 `c9c1b69`，轮询入口每 15 秒读取一次候选日志，复用既有五分钟窗口与投递回执契约。部署负责人配置通知环境后，先将同一候选的应用日志持续追加到本地受控文件，再运行下列命令。保持 `OBS_START` 固定且保留此前五分钟的样本，`OBS_UNTIL` 指定停止发起新轮询的时间，两者跨度至多 24 小时；在途投递按既有请求超时处理。

```sh
uv run --locked python -m scripts.watch_skill_alerts \
  --log reports/observability/events.jsonl \
  --version "$APP_BUILD_REVISION" \
  --skill "$SKILL_ID_A" --skill "$SKILL_ID_B" --skill "$SKILL_ID_C" \
  --start "$OBS_START" --until "$OBS_UNTIL" \
  > reports/observability/watch.jsonl
```

每轮输出评估时刻、逐技能状态和本轮回执，省略令牌、收件地址及正文。失败事件在下一轮继续使用相同幂等标识；已确认或已迟到的事件停止重复发送。某技能的触发事件失败时，该技能后续恢复通知等待确认，其余技能可继续投递。到期仍有未确认或迟到事件时非零退出。

进程重启时使用相同起点、完整日志和收件端首次回执重建状态。日志截短时明确报错，运维恢复完整输入后重启。输入缺样会显示 `no_data`，进程正常结束的退出码不代表课程告警验收通过。

自动化验证采用注入时间覆盖重试、去重、顺序、缺样相关状态和截止；实际 TLS 子进程验证一轮轮询、回执复用及接收端去重。真实持续故障、正式接收端与负责人确认仍待 4.1 验收。
