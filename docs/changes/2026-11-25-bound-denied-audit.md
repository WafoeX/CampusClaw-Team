# 拒绝审计写入预算与安全复验

## 变更说明

基于主干 `d4fd479`，独立处理 2026-11-24 API 审查记录的 P2 审计写入容量风险。范围见本变更规格 DAB-01；不改变权限拒绝及成功业务审计，新增每进程的审计写尝试预算。验收准备文档另见 PR #73。

## 验证记录

### 修复前

- `openspec validate 2026-11-25-bound-denied-audit --strict`：退出 0。
- `make check-test` 在文档准备分支的相同业务代码运行：520 项单元/API、4 项启动通过，说明原有回归没有覆盖本风险。
- `uv run --locked python scripts/check_pytest.py -q --disable-socket tests/api/test_denied_audit_budget.py`：默认预算的新 HTTP 回归失败，65 次学生同源越权请求全部返回 403，但发生 65 次审计追加，预期最多 60 次。此为事务替身层的写放大复现，不是实际容量中断。

## 评审结论

实现及隔离验证进行中。约束变化、预算内存生命周期与实际结果在交付前更新；人工评审和最终真人验收待执行。
