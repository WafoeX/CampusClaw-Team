# CampusClaw 数据字典

## 认证

主键使用服务端生成的规范小写 UUID 字符串。时间以 UTC 写入，精度为微秒。MySQL 使用 InnoDB，外键默认限制删除。

| 表 | 字段 | 约束与用途 |
| --- | --- | --- |
| `classes` | `id`、`code`、`name`、`created_at` | 班级主键、唯一班级编码、显示名称和创建时间。 |
| `accounts` | `id`、`login_name`、`password_hash`、`enabled`、`class_id`、`role`、`created_at`、`updated_at` | 全局唯一规范登录名。口令仅存加盐哈希。每账号恰属一个班级，角色为 `teacher` 或 `student`。 |
| `auth_sessions` | `account_id`、`token_digest`、`issued_at`、`expires_at`、`revoked_at` | 账号外键同时是主键。每账号至多一条当前会话，SHA-256 摘要全局唯一；撤销时间为空时仍需校验到期及账号状态。 |
| `auth_audits` | `id`、`account_id`、`event`、`created_at` | 登录、注销、停用和重置口令的去内容记录。账号标识仅用于受限审计，审计不使用外键，以便账号到期清理后保留去内容记录。 |

班级和账号按所属学期复核留存。停用和改密立即撤销会话。会话有效期 30 分钟，到期或撤销后由后续换发覆盖或在 24 小时内清理。去内容审计保留 90 天。部署前由小组登记学期起止、具体到期日及实名运维责任人。隔离开发与测试使用合成账号，实验结束销毁专用库。

在线持久副本位于 MySQL。会话原值仅经安全 Cookie 发送，不写入数据库、日志或备份。数据库备份隔离保存，14 天轮转。应用回退时保留扩展表。恢复旧备份后接流量前应使所有备份中的会话失效并重放账号停用、口令变更及到期清理。数据库降级会移除认证表及记录，仅在合成隔离库演练。

## 班级资料

| 表 | 字段 | 约束与用途 |
| --- | --- | --- |
| `materials` | `id`、`class_id`、`creator_id`、`chapter_id`、`title`、`sort_order`、`source_format`、`media_type`、`byte_size`、`character_count`、`content_version`、`revision`、`created_at`、`updated_at` | 班级和创建人分别外键关联。`chapter_id` 可空，空值表示未分类；与 `class_id` 组成同班章节外键。按班级及章节、排序、资料 ID 建索引。正文版本为 1，改名、排序或归类仅递增元数据修订号。 |
| `chapters` | `id`、`class_id`、`creator_id`、`name`、`sort_order`、`revision`、`created_at`、`updated_at` | 本班教师创建的目录；班级及创建人外键关联，`(class_id,id)` 唯一供资料同班外键引用。按班级、排序、ID 稳定浏览。`未分类` 是保留入口，不占章节行。 |
| `chapter_idempotency` | `class_id`、`actor_id`、`method`、`resource_id`、`request_key`、`fingerprint`、`result`、`expires_at` | 章节创建与资料归类的 24 小时重放记录；联合主键限定班级、操作者、方法、资源和键。同键异内容冲突；结果仅为元数据，不含原文。后续成功写入的同一事务至多清理 100 条到期行；停流残余须由运维按到期时间有界清理。 |
| `material_bodies` | `material_id`、`content` | 资料主键兼外键，正文按原始字节保存，单份上限 1 MiB。与资料元数据同事务写入和删除。 |
| `material_uploads` | `class_id`、`creator_id`、`request_key`、`fingerprint`、`material_id`、`result`、`deleted`、`expires_at` | 班级、创建人和大小写敏感的请求键构成联合主键。24 小时内保存首个成功响应快照。删除清空结果快照并标记失效，仍处于有效期的键禁止重放。 |
| `material_deletions` | `material_id`、`deleted_at` | 去内容删除凭证，仅保留资料标识和 UTC 删除时间，支持在旧备份恢复后重放。 |

资料的在线原文只保存在 MySQL，应用层文件解析使用有界内存。章节是内部班级数据，随所属班级/学期复核，删除章节时资料同事务回到未分类。部署时将 HTTPS 入口的请求体上限和缓冲方式与应用配置对齐。所属学期结束后 30 天内清理，备份隔离轮转 14 天。上线前由小组登记学期、清理日期和责任人，并保证独立保存的删除清单覆盖所有可恢复备份。应用制品回退时保留扩展表。单步回退 0004 将丢失章节归类；只能在合成隔离库执行，验证前保留可恢复备份。

隔离库可以用 `python -m app.auth_admin export-deletions` 导出 JSON，将清单保存在备份之外。恢复时在接流量前用 `python -m app.auth_admin replay-deletions --manifest <路径>` 重放清单，再处理过期数据。命令只对显式标记的 `campusclaw_test_` 数据库开放。缺少完整清单、到期清理记录或备份核验时，恢复验收保持待办。

## 请求限流

追加迁移 0003 建立 `request_limits`。字段为 `scope_digest`（类型与来源或账号的 SHA-256 摘要，BINARY(32)）、`window_start`（数据库 UTC 自然分钟）及 `request_count`（非空，封顶 61）。前两字段联合主键，窗口时间有索引。摘要不含 Cookie，不存原始 IP 或账号名，无业务外键。

计数由 MySQL 的 `READ COMMITTED` 短事务原子更新，各 worker 共享。该事务避免过期范围清理持有新计数插入的间隙锁，配额仍由联合唯一键和原子 upsert 保证，不改变配额或窗口。每次计数至多删除 100 条早于当前窗口两分钟前的行，停流时残余由后续请求或运维按同一截止有界清理。数据库备份轮转沿用 14 天，恢复后按数据库当前 UTC 窗口校验，过期记录不参与配额。旧应用兼容新增表，回退应用保留表；隔离演练用 Alembic 单步降级 0002 后重升，核对既有账号、会话与资料不变。

## 索引基础（0005，Task 2.1）

本组只建立确定性切片与索引存储基础，发布、嵌入和 Qdrant 写入由 2.2 接入；删除撤权及补偿执行由 2.3 接入。旧资料默认没有活动/期望索引版本且 `vector_ready=false`，原文、章节和修订不变。

| 表/位置 | 字段与用途 | 约束及副本 |
| --- | --- | --- |
| `materials` 追加字段 | `active_index_version`、`desired_index_version` 可空，`vector_ready` 默认 false | 发布事实源；增加 `(class_id,id)` 唯一键供同班索引外键引用。 |
| `material_index_builds` | `id`、`class_id`、`material_id`、`creator_id`、`source_version`、`index_version`、`index_config_version`、`mode`、`window_size`、`overlap`、`status`、`stage`、`lease_expires_at`、`created_at`、`updated_at` | 同班资料组合外键；资料版本唯一，配置指纹 SHA-256；状态为 pending/building/published/keyword_only/failed/superseded。不存令牌或错误原文。 |
| `material_chunks` | `id`、`class_id`、`material_id`、`source_version`、`index_version`、`index_config_version`、`ordinal`、`start_offset`、`end_offset`、`content` | 指向同班资料构建版本；版本内 ordinal 唯一；0 基 Unicode 码点半开区间，正文逐字等于原文区间；utf8mb4、`utf8mb4_0900_ai_ci`，ngram FULLTEXT。 |
| `material_index_cleanups` | `id`、`class_id`、`material_id`、`source_version`、`index_version`、`index_config_version`、`scope_key`、`status`、`attempts`、`next_attempt_at`、`created_at`、`updated_at` | 无被删除资料外键；精确版本作用域键唯一；不含正文。用于跨存储补偿，具体执行及恢复防复活由 2.3 完成。 |
| Qdrant payload 契约 | `chunk_id`、`class_id`、`material_id`、`source_version`、`index_version`、`index_config_version`、`scope_key` | 点 ID 等于 chunk UUID；scope_key 由班级、资料、原文/索引版本及配置指纹确定。无正文、章节或令牌；本组未写 Qdrant。集合/模型/维度配置由 2.2 实施时登记。 |

切片参数固定版本 `slice-v1`、标题解析 `headings-v1`，自动窗口 600、重叠 80，自定义窗口 100–1200、重叠 0–min(200,window-1)，上限 64 片、原文 32,000 码点。原文 UTF-8 严格解码并忽略一个开头 BOM，保留 CRLF 和组合字符。版本 ID 使用固定命名空间的 UUIDv5，输入为资料 ID、索引版本与 ordinal。

MySQL 启动固定 `ngram_token_size=2` 与 `innodb_ft_enable_stopword=OFF`，不使用停用词表；迁移核对会话有效配置后建索引。已有部署先按 Compose 配置重建 MySQL 进程（保留卷），再执行升级。调整这些全文配置需要重建索引；本次仅新建空索引，不重写既有全文数据。依据：[MySQL ngram](https://dev.mysql.com/doc/refman/8.4/en/fulltext-search-ngram.html)、[全文配置与重建](https://dev.mysql.com/doc/refman/8.4/en/fulltext-fine-tuning.html)。

切片与向量随资料/学期生命周期清理，学期结束后 30 天内清理；本轮沿用用户已确认的功能优先安排，具体日期/责任人上线前登记。去内容清理凭证至少覆盖 14 天备份与在途写入窗口，迟到写入收敛前保留；备份隔离轮转。应用回退保留扩展结构；0005 单步降级仅在隔离副本执行，会丢失索引及构建信息，但保留原文和章节，重升后需重建索引。本组无发布指针写入，无新增文件、缓存或问答快照副本。

## 索引构建候选（0006，Task 2.2）

`material_index_operations` 保存 `(class_id,actor_id,material_id,request_key)` 联合主键、配置指纹二进制摘要 `fingerprint`、`build_id` 和 `expires_at`。班级/操作者有外键，资料和构建只存去内容标识，便于删除时清理；不保存 Cookie、正文或模型 key。幂等期限 24 小时，新受理时最多清理 100 条过期记录，删除资料时同事务移除其记录。追加迁移可重跑；0006 单步回退只移除幂等记录，不改原文、章节或 0005 派生结构，回退前须暂停索引新请求。

构建按账号→班级→资料顺序加行锁；班级行锁仅用于受理/发布等短事务，执行期由最长 35 秒的数据库租约排斥同班并发。切片在事务外计算并于受理时重验原文版本；同一事务写完整切片和首次关键词发布指针。模型与 Qdrant I/O 位于事务外，发布前重验当前账号/会话、资料、期望版本和租约。过期记录可用 `python -m app.index_admin recover` 显式处理，每批最多 100 条、可重跑。故障阶段只保留固定标识，不保留上游错误正文。

课程嵌入配置为用户指定的网关、`course-embedding`、2048 维、Cosine，集合名称为 `campusclaw_` 加不含 key 的模型/地址/维度/距离版本摘要。构建配置指纹另包含切片版本摘要。每批最多 32 片、总计最多 64 片；实际模型尝试（含一次瞬态重试）通过共享 `request_limits` 的 `model-call` 作用域限制为每账号每分钟 6 次。密钥缺失时嵌入失败关闭，保留首次关键词版本；不会生成假向量冒充课程模型。

资料删除同事务登记每个索引版本的去内容清理凭证、删除切片/构建及构建幂等记录，再清原文。失败构建也登记凭证，并在剩余预算内尝试精确版本向量删除和零残留核对。凭证继续保留供 Task 2.3 处理迟到写入收敛、删除补偿及备份恢复；补偿、故障及隔离旧行还原后重放已自动验证，详见后续0007及本变更证据。旧应用不具备索引删除协议，回退时须按设计暂停资料删除及索引写入。

## 索引清理候选（0007，Task 2.3）

0007 在构建及清理凭证中追加可空 `vector_collection`，锁定每次写入的集合名，避免更换模型后误清理新集合；历史 0005 基础数据没有真实向量写入，列保持空。补偿遇到缺集合名或当前活动完整版本时转人工，不做宽范围删除。升级按已存在列条件重跑；隔离降级会丢失集合定位和旧出处映射，须暂停索引/清理、保留外部清理清单并重升后核对，正式应用回退继续保留扩展库，不执行该破坏性降级。

`material_chunk_tombstones` 保存退役切片的 `id,class_id,material_id,source_version,index_version,index_config_version,created_at,expires_at`，不保留正文或区间，供后续出处接口区分真实旧出处和伪造 ID。新版本发布同事务将旧切片转成去内容映射、清理旧正文、标记旧构建 superseded 并登记精确清理凭证；删除资料时同步删除映射。映射保留 90 天，过期后不可作为真实旧出处。

`python -m app.index_admin cleanup` 显式处理每批最多 100 条凭证，总 HTTP 预算 35 秒。短事务领取时以尝试次数 CAS，最多 3 次，失败按 1/5 分钟等待后继续，耗尽转人工；30 分钟档为保留配置但不突破三次上限。失败或已有人工项时命令非零退出。远端仅按原集合、班级及精确 scope_key 删除，随后精确 count 确认零残留。完成凭证继续保留并在显式批处理中重查，迟到 upsert 可再次清理；零残留复核不消耗删除尝试。每批另外各清理至多 100 条过期构建幂等、过期映射及创建超过 90 天的完成凭证；未收敛/待人工凭证不自动丢弃。运行频率和实名执行责任仍为上线前登记项，不等于已有后台调度。

本组没有新增文件正文副本或问答快照。隔离恢复应先重放独立保留的原文删除清单，再运行过期构建恢复和精确向量清理；完成前不接流量。检索与出处入口已接通，真实 MySQL/Qdrant 的三模式删除不可见、旧出处409及删除后404已复验；没有实际恢复生产备份或进行真人演练。


## 单次检索问答的副本边界（2026-11-07）

`/search`、`/ask` 不新增持久会话、回答快照或聊天历史表。一次问答只在内存保留当前问题、至多8片/12000码点证据、模型结构与已验证出处；日志只记服务器请求标识、固定模型/配置摘要、模板版本、token用量及耗时/结果，不记原文、问题、回答、Cookie或密钥。提供方未返回的不可变模型版本记缺项，不编造。跨 worker 模型并发使用数据库名+账号摘要的 MySQL 连接命名锁，连接自动提交、不持有行事务，最终释放；每次实际模型尝试仍消耗共享每分钟6次配额。
