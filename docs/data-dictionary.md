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
| `materials` | `id`、`class_id`、`creator_id`、`title`、`sort_order`、`source_format`、`media_type`、`byte_size`、`character_count`、`content_version`、`revision`、`created_at`、`updated_at` | 班级和创建人分别外键关联。组合索引按班级、排序、资料 ID。正文版本为 1，编辑标题或排序仅递增元数据修订号。 |
| `material_bodies` | `material_id`、`content` | 资料主键兼外键，正文按原始字节保存，单份上限 1 MiB。与资料元数据同事务写入和删除。 |
| `material_uploads` | `class_id`、`creator_id`、`request_key`、`fingerprint`、`material_id`、`result`、`deleted`、`expires_at` | 班级、创建人和大小写敏感的请求键构成联合主键。24 小时内保存首个成功响应快照。删除清空结果快照并标记失效，仍处于有效期的键禁止重放。 |
| `material_deletions` | `material_id`、`deleted_at` | 去内容删除凭证，仅保留资料标识和 UTC 删除时间，支持在旧备份恢复后重放。 |

资料的在线原文只保存在 MySQL，应用层文件解析使用有界内存。部署时将 HTTPS 入口的请求体上限和缓冲方式与应用配置对齐。所属学期结束后 30 天内清理，备份隔离轮转 14 天。上线前由小组登记学期、清理日期和责任人，并保证独立保存的删除清单覆盖所有可恢复备份。应用制品回退时保留扩展表。隔离数据库降级会清除新增表，验证前保留可恢复备份。

隔离库可以用 `python -m app.auth_admin export-deletions` 导出 JSON，将清单保存在备份之外。恢复时在接流量前用 `python -m app.auth_admin replay-deletions --manifest <路径>` 重放清单，再处理过期数据。命令只对显式标记的 `campusclaw_test_` 数据库开放。缺少完整清单、到期清理记录或备份核验时，恢复验收保持待办。
