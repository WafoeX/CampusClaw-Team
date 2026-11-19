# 候选题任务审计规划证据

## 变更说明

本次只建立 `2026-11-19-add-teaching-job-audit` 的 proposal、能力规约、设计和任务清单，供第 10 课 L10-N07 技术缺口的后续实现及人工评审使用。现有候选任务可返回 202、轮询状态，但没有与班级操作审计关联；规划保留正式交卷 201 契约，不虚构技能 ID，不预先判定课程作业链路等价。未修改应用代码、迁移、测试、主干或既有门禁。

按 `openspec-propose` 读取了 `AGENTS.md`、`README.md`、OpenSpec 配置、候选任务服务/仓储、worker、模型适配器、审计接口与 0013/0015 迁移，生成四类规划文件；按 `project-review` 读取规划文件与安全开发、AI 应用、数据、评审规范，核对授权范围、失败路径、数据兼容和评审状态。`project-data-change` 与 `project-add-tests` 留待实施相应任务时调用，本次没有假称迁移或测试已完成。

## 验证记录

| 项目 | 实际结果 | 状态 |
| --- | --- | --- |
| `openspec context --json`、`openspec status --change 2026-11-19-add-teaching-job-audit --json` | 定位仓库 OpenSpec 根目录；proposal、specs、design、tasks 均为 `done`，规划集合完整 | 通过 |
| `openspec validate 2026-11-19-add-teaching-job-audit --strict` | 退出码 0，变更有效 | 通过 |
| `openspec validate --all --strict` | 退出码 0，13 个变更通过、0 失败；其他旧变更有归档提示信息 | 通过 |
| `git diff --check` | 退出码 0；本次新增文件提交后再复核差异 | 通过 |
| `make check`、`make check-security`、应用 pytest、MySQL/Kafka、H5 浏览器、迁移和恢复演练 | 本次仅规划，没有实施代码；留待 tasks 对应实现组 | 未执行 |

规约场景包含正常受理与重放、用量缺失、非法输入、跨班和学生拒绝、重复消息/旧租约、审计存储故障、撤权与来源失效、到期及恢复。每项实施任务均写明后续可观察验证方式；当前场景为验收约定，并非运行结果。

## 评审结论

规划文件齐备、严格校验通过，属于可提交评审的规划版本。对照 SEC-02–04、SEC-11、AI-07/10、DATA 留存与副本规则、REV-07–09：服务端班级过滤、跨班同构、去内容、原子性、90 天清理及迁移回退均已列为实施约束；未发现本次规划文件放宽门禁或修改现行授权。应用行为、性能和课程方等价性仍未验证；第 10 课 4.3 与最终验收 1.5 保持未完成。OpenSpec 属约束文件，依据 REV-08 待实际评审人复核；助手自检不构成人工批准，也不授权合并。
