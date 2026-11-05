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
