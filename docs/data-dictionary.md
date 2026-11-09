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

## 流式助手存储基础（0008，第 1 组）

本组只建立结构和资料删除时的副本去内容化原语，不启用应用、会话、SSE 或反馈 API。所有新主键沿用小写 UUID，时间为 UTC 微秒；`class_id`、`owner_id`、`creator_id` 由后续服务端身份解析器填写。新增 `accounts(class_id,id)` 唯一索引供同班账号组合外键引用，既有账号不改值。所有新表默认 RESTRICT；配置绑定随对应配置/原资料删除 CASCADE，历史出处的资料标识无原文外键，允许保留已删除状态。

| 表 | 字段与用途 | 约束与状态 |
| --- | --- | --- |
| `prompt_templates` | `id,class_id,creator_id,name,app_key,revision,enabled,created_at,updated_at` | 四类应用键；修订正整数，同班创建人外键；`(class_id,id)` 唯一 |
| `prompt_template_revisions` | `class_id,template_id,revision,creator_id,prompt,created_at` | 组合主键，模板及创建人同班；不可变修订由后续写服务只增，prompt 至多 2000 码点 |
| `assistants` | `id,class_id,creator_id,name,revision,enabled,created_at,updated_at` | 同班创建人；`(class_id,id)` 唯一 |
| `assistant_revisions` | `class_id,assistant_id,revision,creator_id,prompt,created_at` | 同班助手不可变修订，空提示词留空，由服务端使用默认角色 |
| `skills` | `id,class_id,creator_id,name,name_key,revision,enabled,builtin_key,created_at,updated_at` | `name_key` 是 NFKC+casefold 的 UTF-8 字节，班内唯一；内置键可空，非空为 problem_guidance/learning_plan，班内内置键唯一；定义只读由后续服务约束 |
| `skill_revisions` | `class_id,skill_id,revision,creator_id,definition,created_at` | 同班不可变技能版本；JSON 为数据，白名单校验在后续服务执行，不由数据库执行清单 |
| `assistant_materials` | `class_id,assistant_id,revision,material_id` | 同班助手修订与同班资料组合外键；删除资料仅移除绑定，不阻碍原文删除 |
| `assistant_skills` | `class_id,assistant_id,revision,skill_id` | 同班修订/技能组合外键；绑定不冻结技能启停，下轮重读当前技能版本 |
| `sessions` | `id,class_id,owner_id,assistant_id,mode,created_at,updated_at,expires_at` | mode 为 material_qa/problem_guidance；同班账号/助手外键；`(class_id,owner_id,id)` 唯一，所有私人子表沿此归属链 |
| `ai_operations` | `id,class_id,owner_id,session_id,app_key,operation_scope,request_key,fingerprint,input_payload,status,attempt_count,lease_token,lease_expires_at,created_at,updated_at,expires_at,active_session_id` | session 可空用于独立应用；作用域是会话 UUID 或应用键的 ASCII 字节，键 VARBINARY(64) 大小写敏感，摘要 BINARY(32)；`(class_id,owner_id,operation_scope,request_key)` 唯一。status running/succeeded/failed/interrupted/revoked，尝试 1–3；running 必须有租约及令牌，其余须为空。生成列 active_session_id 仅在 running 时取 session_id，联合唯一保证一会话最多一个在途轮次。会话与应用/作用域一致性有 CHECK |
| `messages` | `id,class_id,owner_id,session_id,operation_id,role,content,content_state,created_at,expires_at` | 归属链同时绑定操作与会话，role user/assistant，`(operation_id,role)` 唯一；只存已受理用户消息和已校验成功助手正文，失败不存模型原文；content_state available/revoked/expired，非 available 时正文须空 |
| `application_runs` | `id,class_id,owner_id,operation_id,attempt,status,configuration,details,error_code,duration_ms,created_at,updated_at,expires_at,successful_operation_id` | 同班本人操作，attempt 1–3 且每操作/尝试唯一；status running/succeeded/failed/interrupted/revoked；成功/已撤销成功的生成列唯一，保证一操作最多一条成功记录，去内容化后也不释放成功占位。configuration 只允许去密钥的模型/修订/参数；details 是成功的已验证步骤/结果，失败必须为空，error_code 仅固定码，不存上游错误原文 |
| `message_citations` | `class_id,owner_id,session_id,message_id,ordinal,material_id,source_version,index_version,index_config_version,start_offset,end_offset,title,excerpt,status,created_at,expires_at` | 同班本人消息外键，消息/编号唯一，ordinal 1–4，码点半开区间；status available/deleted/revoked/expired；失效时 title/excerpt 均空。不指向当前切片；重建保留旧快照，删除同事务去内容化 |
| `teaching_feedback` | `id,class_id,owner_id,session_id,message_id,chapter_id,rating,note,status,revision,creator_id,created_at,updated_at,expires_at` | 同班本人消息/账号及可空章节外键；消息唯一，rating helpful/unresolved，status pending/handled/unavailable，revision 正整数；未解决有效记录 note 1–500 码点。教师最小投影由后续服务实现，不能直接返回此表 |
| `ai_configuration_audits` | `id,class_id,actor_id,resource_type,resource_id,revision,event,created_at` | 配置及反馈写入的去内容审计；只记对象标识、修订与 create/update/disable/delete/handle，不含提示词、说明、问题或身份展示字段；服务只增，90 天 |

私人记录按所属学期结束后 30 天内到期，`expires_at` 在受理时固定，出处、操作、消息、执行和反馈不得晚于父对象到期。配置及其版本随班级/学期复核；日志14天、去内容审计90天、隔离备份14天轮转。具体学期、到期时间和实名清理执行人沿用既有安排，生产启用前由小组登记；本组只在随机 `campusclaw_test_` 合成库验证，未上线持久化真实个人数据。

新正文副本仅在 MySQL 的 `ai_operations.input_payload`、`messages.content`、`application_runs.details`、`message_citations.title/excerpt`，教学说明只由学生主动提供。无新增文件、Qdrant 或缓存副本。资料删除同事务按出处依赖清空整条消息正文、该操作的输入/步骤结果及该消息全部出处和反馈说明，保留安全状态与去内容标识；清理故障回滚删除事务。恢复先重放独立原文删除清单，再清理到期记录，完成前不接流量；本组对隔离还原的数据库行执行同一删除原语重放，不冒充生产备份恢复。会话/账号隐私删除及统一到期清理的入口随私有记录与历史治理组实现，存储基础阶段未启用新数据写入口；当前会话接入状态见本文末尾的3.1补充。

迁移0008仅增表和账号组合唯一索引，条件化重跑应对 MySQL DDL 中断。应用回退保留0008扩展表，新功能停流、收敛租约后回到原制品，并暂停涉及新副本协议的资料/章节删除与私人写入；恢复新制品后重放清单和到期清理再开放；物理降级会丢失本课新配置与私人数据，仅在专用合成库中演练，保留原文、认证、章节和索引。恢复所需独立删除清单不得随备份回退。业务授权、不可变修订写入和配置变化重验仍由后续服务实现，数据库约束不替代逐次授权。

## 应用配置与同步执行（0009，Task 2.1）

追加 `prompt_templates.deleted`（非空Boolean，默认false），删除同事务递增revision、保留修订及去内容审计；本班读取也隐藏deleted，不以90天审计记录充当删除事实。追加 `ai_configuration_requests(class_id,actor_id,resource_type,request_key,fingerprint,resource_id,created_at,expires_at)`，前四字段联合主键，actor有同班账号组合外键，request_key为VARBINARY(64)、fingerprint为BINARY(32)，类型template/assistant，24小时幂等；不保存提示词或请求正文。创建事务最多清除100条到期幂等行；停流残余由显式清理命令处理。0009单步降级只允许合成库，会丢失删除标记与幂等记录，须停新接口，不作为正式应用回退。

本组同步操作复用0008的 `ai_operations/application_runs`，session_id为空、作用域为应用键。configuration只存模型/参数/系统模板版本及班级模板id/修订；成功details存已校验text和该次rendered_prompt，input_payload存本人variables及模板id/修订，均为私人正文副本。失败details和input_payload清空，不存原始异常或无效模型输出。显式AI_DATA_EXPIRES_AT在受理时固定，未知学期时不启用持久执行；读取、重放都需当前身份、同班本人和未到期。`python -m app.ai_admin cleanup` 每批最多100个已过期同步操作，先删其执行记录再删操作，另清理最多100条过期配置创建幂等；无网络副作用。备份中的到期值不随恢复延长，恢复接流量前重做日期清理；没有新增文件/缓存/向量副本。账号/会话隐私删除及来源治理由后续组实现，上线前仍需登记学期及实名清理责任。

### 技能定义读写补充（2026-11-08，2.2组件）

沿用0008 `skills` 与 `skill_revisions`，不修改既有迁移。`name_key` 为NFKC、casefold、strip后的UTF-8字节；班级锁串行化不同教师同名创建，`uq_skills_name`继续兜底。内置实例用班级与 `builtin_key` 生成稳定UUID，`definition`保存经白名单校验的条件、工具和有序步骤，启停也追加修订与去内容审计。当前上传技能删除按既有外键级联删除定义修订及助手绑定，保留删除审计；未来会话执行必须保存当时生效的受控配置，不能依赖已删除定义回读。数据归属为教师所在班级，私人会话记录不因教师管理权限开放。配置回退保留原0008/0009表；无生产迁移或删除操作。

### 私有会话读写与到期治理（2026-11-08续做，3.1）

沿用0008实体，不改变已执行迁移。会话创建ID为班级/本人/创建幂等键的UUIDv5，绑定模式和助手在存续期不可换；重放相同输入不重复创建，到期值不延期。轮次指纹覆盖规范化 `question/chapter_scope/retrieval_mode`，幂等作用域仍为班级/本人/会话，成功回放不新增任何行；失败清除操作输入及步骤正文，保留一条原用户消息和去内容尝试，最多3次。受理与条件提交均重验当前身份、助手/技能修订及当前材料，来源锁与原文删除共用事务边界。

`application_runs.configuration` 保存模型参数、系统模板版本、助手ID/修订/启用状态、材料绑定和技能ID/修订，以及所选技能摘要，不存提示词或密钥；`details` 仅成功时保存已校验正文和步骤序号/文本。`messages`、`message_citations` 与成功状态同事务写入；失败不写成功助手消息或原始模型正文。本人回读同时检查来源状态，来源不可用时隐藏正文；历史出处详情及反馈的第4组接入见本文末尾。旧单次问答仍不写这三类私人记录。

统一清理命令每批额外锁定最多100个已过期会话，按反馈、出处、消息、执行、操作、会话顺序删除；读取在清理前即按父会话期限拒绝。恢复保留原expires_at，重放到期/删除清单后接流量。本轮仅做合成库行级回灌与重放验证，不冒充生产备份恢复、加密备份或RPO/RTO演练。应用回退保留既有扩展表、关闭新会话写入并排空在途，不能通过删表回退。实名清理与生产学期仍由小组登记。

### 第4组：历史出处与反馈读写

复用0008/0009，无新增表、字段或迁移。`message_citations` 的版本/区间/标题/摘录保持生成时值；当前同班原文存在且无删除凭证时才可读。当前版本不同标为historical，已删除/撤销不返回标题、摘录或定位。原文删除凭证同时用于私人消息、执行记录及教师列表的即时过滤；关联成功轮次的用户消息也按同一来源依赖隐藏，失效历史不得进入模型上下文。物理清除仍由既有删除事务与向量清理凭证负责。

`teaching_feedback` 的rating只接受helpful/unresolved；note去首尾空白后至多500码点，unresolved必填。首次expected_revision=0，创建revision=1；实质更新/教师处理递增。相同评价与说明重放保留修订和处理状态，不续期。学生实质改评重置pending；helpful不进入教师未解决列表。处理仅允许pending→handled（重放原处理幂等）。来源失效时过滤列表，物理删除清空note并标unavailable。chapter_id只取受理时已校验的chapter_scope且仍属本班，不接受客户端另行指定。

教师投影仅 `id,rating,note,status,revision,chapter,updated_at`；revision是并发控制元数据，chapter为当前本班可公开章节名或null，无学生标识/会话/消息/执行/出处引用。本人会话回读附本人反馈与可分享章节名供预览。写反馈与处理追加去内容审计，期限不晚于父会话/消息，过期清理沿用每批100个会话。保留期、隔离备份14天及恢复重放义务不变；真实学期和实名执行人由小组上线前登记。

## 人工教学闭环（0010，异步教学任务 2.1–2.3）

本次只建立人工题库、同步测验发布、学生草稿、正式提交和规则评分。未引入 Kafka、候选题批次或看板副本。新表均在 MySQL，班级及账号由现有认证数据约束；`materials` 增加 `(class_id,id)` 唯一索引供同班来源外键使用。应用回退保留扩展表，暂停本组写入口；0010 物理降级只允许随机 `campusclaw_test_` 合成库，删除本组数据但保留被上游外键使用的资料索引。

| 表 | 字段与约束 | 生命周期及访问 |
| --- | --- | --- |
| `questions`、`question_versions` | 题目当前修订、已审核修订；每次编辑只增版本，清除审核；版本记录题型、题干、选项、答案、解析、可空同班资料来源 | 仅本班教师管理；审核和编辑有去内容审计；未审核版本不得发布 |
| `question_audits` | 题目、版本、操作者、created/edited/reviewed、时间 | 不含题干、答案、解析；随教学数据按学期清理 |
| `quizzes`、`quiz_draft_items` | 本班标题、章节、截止与答案开放时刻、发布时刻、草稿题序和分值 | 发布时锁定审核版本与当前学生名单；发布后不可改；列表按班级及冻结资格过滤 |
| `quiz_items`、`quiz_participants` | 发布题目含答案、解析和来源的不可变快照；参与名单按 `(quiz_id,student_id)` 唯一 | 学生投影在开放前不含答案、解析；名单只在发布事务中写入。资料删除同事务清空来源指针，保留答题快照 |
| `quiz_drafts` | 每位学生每份测验一条答案及递增修订 | 本人读写；更新需匹配修订，正式提交后只读；不复制到文件或浏览器持久存储 |
| `quiz_submissions`、`quiz_results` | 每位冻结学生一条正式提交及幂等键；规则评分、逐题结果与总分同事务写入 | 正式提交 201；同键同请求重放，不同内容冲突。答案开放前学生回读隐藏分数及逐题正确答案；本班教师可读提交结果 |
| `quiz_audits` | 测验、操作者、created/published/submitted、时间 | 去内容审计，随教学数据清理 |

题目及测验记录随所属班级/学期结束后 30 天内清理，隔离备份按现有 14 天轮转；正式生产启用前仍需登记学期、清理日期和责任人。来源资料的删除凭证覆盖备份恢复重放；恢复旧备份后先重放原文删除清单，使题目与发布快照来源指针再次去内容化，再恢复服务。当前验证仅在一次性合成库执行迁移、业务写入、回退与重升，未演练生产备份恢复。
