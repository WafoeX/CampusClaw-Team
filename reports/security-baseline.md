# 候选资产扫描与依赖基线（SEC-05、SEC-06）

2026-11-13，候选 `4aa4953bd08cf0bb397ecce6416300a41c7c2ad5`。执行 `make check-security SECURITY_ASSETS=reports/security-release-4aa4953`。Gitleaks 与 Trivy 使用 [Makefile](../Makefile) 的固定镜像摘要，分项只打印脱敏计数和退出码。

| 范围 | 方式 | 实际 |
| --- | --- | --- |
| Git 历史 | 非浅克隆，本地引用可达范围，镜像副本执行 Gitleaks git | 156 个可达提交，分项 0，零命中。远端不可见和已删除且不可达历史不在扫描范围。 |
| 工作区候选文件 | Git 跟踪文件及未忽略新文件 | 分项 0，零命中。 |
| 前端 | 五个产物：登录、资料、测验、Swagger 和 OpenAPI | 分项 0，零命中。 |
| 运行日志 | 隔离 Compose 与预检请求及技能模型日志 | 分项 0，零命中。 |
| 镜像 | 应用与 MCP 两个 Docker 归档的文件及镜像配置 | 两个分项均 0，零命中。 |
| 锁定依赖 | 候选 Git 版本的 uv.lock，包含开发依赖 | 本轮漏洞库更新失败，分项 2、工具退出 1。High 与 Critical 计数均未取得。SEC-06 待复跑。 |

命令整体非零。GHCR 与 ECR 备用源均有更新失败记录，过期缓存未用于给出通过结论。已用真实 Gitleaks 验证无效合成样本命中 1 条，清理后为 0。扫描器替身用例验证高危计数、首项失败后继续、缺资产、工具错误及输出脱敏。候选扫描无明文凭据命中，未触发轮换。

## 2.2 复验

2026-11-13，仍扫描候选 `4aa4953` 的镜像、前端、日志与锁文件，工作区取证提交为 `a1c7614`。使用 [Trivy 官方文档列出的镜像源](https://trivy.dev/docs/latest/guide/configuration/db/)下载 schema 2 漏洞库，下载层 SHA-256 与 OCI 清单一致（`fd406c50cad6892a16b258bef67be31ebfd4ddfb00da80ce869b461e73116d4f`）。官方库更新时间为 2026-11-13 07:00:07 UTC，下一次更新为 2026-11-14 07:00:07 UTC。导入新的本地缓存，仅登记下载时间。保持现有阻断规则与漏洞库时效检查。

`make check-security TRIVY_CACHE="$PWD/reports/trivy-cache-import" SECURITY_ASSETS=reports/security-release-4aa4953 SECURITY_CANDIDATE=4aa4953bd08cf0bb397ecce6416300a41c7c2ad5` 退出 0。

| 分项 | 复验结果 |
| --- | --- |
| Git 历史 | 161 个本地可达提交，凭据命中 0。 |
| 工作区、前端、日志 | 每个范围凭据命中 0。 |
| 应用镜像、MCP 镜像 | 两个镜像各命中 0。 |
| 锁定依赖（含开发依赖） | High 0、Critical 0，分项退出 0。 |

SEC-05 和 SEC-06 本轮判绿，未发现需轮换的候选凭据或需处置的 High/Critical 发现。前轮下载失败记录保留。
