# 独立错题讲解提示评测

变更：`2026-11-26-add-mistake-explanation`。本文件记录工程固定回归的前后对比；真实课程模型效果与最终人工判断分开记录。

## 固定条件

| 项 | 固定值 |
| --- | --- |
| 基线提交 | `580c4f0bfb2061ed6659938cb25808137025eefa` |
| 基线技能版本 | `bounded-skills-v1` |
| 基线模式 | `problem_guidance` |
| 模型输出契约 | 仅允许 `identify`、`relate`、`plan`、`check` 提示槽位 |
| 最终正文 | 服务端固定中文提示；引用为空 |
| 数据 | `tests/unit/test_skills.py` 与 `tests/api/test_sessions.py` 的合成非生产夹具 |
| 判据 | 正常槽位可渲染；未知、重复、空或越界槽位拒绝；无证据不调用模型；注入内容不进入固定正文 |

## 修改前基线

2026-11-26 在上述提交新建的干净工作树运行：

```text
uv run --locked pytest -q --disable-socket tests/unit/test_skills.py tests/api/test_sessions.py
.............................                                            [100%]
29 passed in 0.54s
```

退出码 0。基线证明通用解题引导已有固定提示和接口拒绝回归，但不存在 `mistake_explanation` 内置技能、本人错题启动接口或对应页面交互，因此不能作为 L10-N03 完成证据。

## 修改后结果

待实现后使用相同基线集合并追加错题讲解固定集运行，保留样本数、失败与复测。当前环境没有课程模型密钥；真实模型调用和提示质量人工裁决未执行，不能用确定性替身结果替代。
