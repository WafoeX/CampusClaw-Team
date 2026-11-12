## Purpose

让组员从干净克隆启动同一套运行骨架，让运维在无账号的情况下核对运行版本、进程存活和依赖就绪，并用请求标识定位故障。

## ADDED Requirements

### Requirement: RT-01 外置配置与冷启动

服务 MUST 在监听前校验所有必需配置，缺失、空白或格式非法即非零退出。版本来自构建元数据，与制品可追溯关联。连接配置与凭据由环境注入，`.env.example` 只含空值赋值行，正常启动不得依赖源代码内的凭据或本机配置残留。

#### Scenario: RT-N01 干净克隆后启动

- **GIVEN** 新克隆、空运行卷、锁定构建输入和 README 指定的有效外部配置
- **WHEN** 运行 `docker compose up --build -d` 并按 README 等待就绪
- **THEN** 仅应用端口可从宿主机访问，匿名探针返回该构建版本且核心就绪

#### Scenario: RT-F01 必需配置缺失或为空

- **GIVEN** 其余必需项有效
- **WHEN** 逐项取消必需键、传空值或只传空白，再直接启动应用
- **THEN** 每次均在监听前非零退出，脱敏诊断指出键名，应用无可访问探针

#### Scenario: RT-F02 配置格式非法

- **GIVEN** 所有必需键均有值
- **WHEN** 将 MySQL 端口设为 65536 或将向量服务地址设为非 HTTP(S) URL 后启动
- **THEN** 启动非零退出且不监听，诊断指出键名，响应与日志均无配置原值

### Requirement: RT-02 独立存活和就绪契约

公开探针 SHALL 允许匿名 GET 和 HEAD，HEAD 保留状态与响应头且无正文。响应 MUST 含 `X-Request-ID`、`Cache-Control: no-store`，使用固定安全字段，不泄露连接细节、凭据、业务数据或堆栈。`/live` 只确认进程可响应；`/health` 以 MySQL 为核心就绪依赖、Qdrant 为可降级依赖，每项探测截止 1 秒且无重试。部署入口按就绪结果撤流；普通业务不主动采样全局探针，按自身依赖契约处理故障。停止时先撤就绪并拒绝新业务，再于最多 30 秒内有界排空。

#### Scenario: RT-N02 两个探针正常

- **GIVEN** 应用在运行，两项依赖通过连通检查
- **WHEN** 匿名 GET 两个探针
- **THEN** 两端均为 200；`/live` 返回 `{"status":"alive","request_id":"…"}` 且不探测依赖；`/health` 顶层包含 `status=ready`、`version`、UTC RFC 3339 `time`（`Z`）、`dependencies` 和 `request_id`，依赖仅有 `mysql`、`qdrant`，值均为 `ready`，响应头请求标识与正文一致

#### Scenario: RT-F03 MySQL 连接被拒

- **GIVEN** 应用已就绪、Qdrant 可用，且在专用 Compose 项目内
- **WHEN** 停止真实 MySQL 后访问两个探针，再启动 MySQL 并等待恢复
- **THEN** 故障时 `/live` 保持 200，`/health` 为 503、`status=not_ready`、`mysql=unavailable`、`qdrant=ready`，不泄露连接细节；恢复后无需重启应用即可重新就绪

#### Scenario: RT-F04 核心探测超时

- **GIVEN** 应用已运行，核心探测连接接受请求但不回包，Qdrant 可用
- **WHEN** 调用 `/health`，并发调用 `/live`
- **THEN** 核心探测达到 1 秒截止后判为不可用且不重试，`/health` 返回 503，`/live` 仍为 200；探测不会继续占用无界工作资源

#### Scenario: RT-B01 仅可降级依赖中断

- **GIVEN** 核心 MySQL 可用
- **WHEN** 在独立 Compose 项目停止真实 Qdrant 并匿名请求 `/health`
- **THEN** 返回 200、`status=degraded`、`mysql=ready`、`qdrant=unavailable`；恢复 Qdrant 后状态恢复为 `ready`

#### Scenario: RT-B02 探测截止边界

- **GIVEN** 使用固定时钟和可控探测结果，另一依赖正常
- **WHEN** 分别在 999 毫秒、1000 毫秒和 1001 毫秒收到 MySQL 成功信号
- **THEN** 仅 999 毫秒为就绪，另外两次均为 503 且核心不可用

#### Scenario: RT-B03 HEAD 和不可缓存

- **GIVEN** 应用可响应探针
- **WHEN** 在就绪和核心故障时分别发送 HEAD，并对照同状态下的 GET
- **THEN** HEAD 与 GET 状态、媒体类型和缓存指令一致，HEAD 无正文，每次响应各有请求标识

#### Scenario: RT-B04 正常终止

- **GIVEN** 实例就绪且隔离环境中有在途请求
- **WHEN** 发送正常停止信号
- **THEN** 可观察的排空阶段先将 `/health` 撤为 503，切换入口不再导入新流量，在途请求在最多 30 秒内完成或因到期结束，保留脱敏退出记录

#### Scenario: RT-B05 业务与探测并发隔离
- **GIVEN** 隔离装配中探测槽已被两次就绪探测占用，而测试业务依赖可用
- **WHEN** 并发发送十个已授权业务请求，随后设置排空标志并重试一次
- **THEN** 排空前十个请求成功且没有增加探测次数；排空后返回 503/1500，未执行业务处理器，存活仍返回 200

### Requirement: RT-03 单行请求关联日志

应用 MUST 为每个请求生成独立的服务端请求标识，贯穿响应和日志。日志每条一行 JSON，含 UTC `ts`、`level`、`module`、`request_id`、`version`。无请求的启动或停止事件使用 `request_id=null`。请求日志可记录 `duration_ms`、状态和安全依赖类别，禁止记录未经筛选的请求头、URL 查询、正文、连接字符串和凭据。

#### Scenario: RT-N03 请求关联可复核

- **GIVEN** 收集应用日志且服务已启动
- **WHEN** 分别发起一次健康请求和一次拒绝请求
- **THEN** 两个响应请求标识互异，各自可在单行 JSON 日志关联，版本一致，启动事件可单独识别

#### Scenario: RT-F05 不可信日志输入

- **GIVEN** 运行环境只使用合成凭据与可识别的测试哨兵
- **WHEN** 请求附带伪造请求标识、含换行的编码查询和哨兵 Authorization，再注入含内部地址的依赖异常
- **THEN** 服务端使用自己生成的标识；日志均可按行独立解析；日志与响应不含哨兵、原始查询、地址和堆栈

匿名探针无调用者角色和业务资源 ID，业务授权与资源查无分类不适用于本能力。RT-F01 至 RT-F05 是真实失败场景，分类不适用由评审确认，未计入场景数。
