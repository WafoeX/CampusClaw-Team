# 受控 MCP 工具工程回归

## 版本与输入

主干基线为 `7d581d51705a38cb2936e98076e710ab524ec2ac`，候选为当前变更工作区。先在主干导出目录运行 `python -m scripts.evaluate_assistant`，再以同一 Python 环境在候选运行。原固定资料问答和拒答集 SHA-256 为 `853ca1377a33313e124419c486ac354ffab958e5ecf5ec3f7dae455e4775b9a1`，原提示策略哈希为 `33469b1602317a863570cafa2cb44b8e6336940816f6ebfeed35da6e8c329690`，前后相同。

候选工具规划使用有界 JSON 提议，独立于原回答格式与出处校验。固定用例为 [会话工具集成夹具](../../tests/integration/tool_dialogue_runtime.py)和[代理夹具](../../tests/integration/tool_proxy_check.py)，分别使用合成账号、合成资料、确定性模型替身和真实 MCP 服务，数据库为独立 MySQL。两份夹具 SHA-256 分别为 `cab50bd719361cadd8350eed7c0b35cab826be5f3c2692f9e7501f3272627a86`、`9688246d5db6e8ec0b05188d3c1ad7fd72b23d1657c9219010c0497e48b61cad`。

## 结果

| 回归 | 判据与实际结果 |
| --- | --- |
| 既有回答和拒答 | 同一合成样本集，主干 20/20、候选 20/20，均退出 0。固定出处、无证据零模型调用、恶意技能、非法出处和受控解题结果覆盖保持。 |
| 本课候选与授权 | 只向规划发送当前技能与本轮选择的交集。真实提示及签发换算通过，未绑定工具、普通问答换算、改题或改参数均无发包。同键重放不重新规划或调用。 |
| 工具注入及预算 | 注入的结果被拒，原文没有进入模型和私有记录。最多两轮和三个已受理提议，重复提议不重发。审计写故障、发送前断开或在途撤销均无新成功结果。 |
| 停机和无证据 | TLS/NGINX 合成模型夹具下，停机和断开分别呈现出错和被拒，已验证的正文与出处仍正常完成。无证据分支保持零对话模型调用。 |
| 真实课程网关最小烟测 | `uv run --locked python -m scripts.evaluate_controlled_tools` 退出 0。模型为 `course-chat`、温度 0.2，版本指纹为 `33aa849bc8cbe9c9632b587c8c36a3455cdeb4dcdf35aa17f9cf5172c998dd2c`。固定合成问题触发 1 次真实模型提议、1 次本机回环 MCP 调用，成功返回预期提示编号。网关 1730.67 ms、握手发现 7.36 ms、工具调用 1.51 ms。 |

真实网关烟测与 Compose 替身证据分开。原始脱敏数据见本地 `reports/2026-11-04-add-controlled-mcp-tools/` 下的 `assistant-before.json`、`assistant-after.json`、`real-gateway.json` 和 `proxy-tools.json`。真人语义评估、同伴复验与课程确认留给项目最终验收。
