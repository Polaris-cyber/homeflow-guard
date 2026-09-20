# HomeFlow Guard 合成评测集数据卡

## 数据用途

用于验证“自然语言需求 → AutomationIR → 安全校验 → YAML”的产品流程。不能用于推断真实用户偏好、市场规模或真实家庭设备分布。

## 组成

- 共 50 条场景。
- 12 条正常单条件、10 条多条件、8 条歧义、10 条不支持/越界、10 条冲突/敏感操作。
- 15 条开发集、35 条锁定测试集。
- 设备均来自公开虚拟家庭，不对应现实住所或用户。

## 来源与标注状态

场景由 AI 根据公开产品范围起草，代码生成过程保存在 `scripts/build_dataset.py`。当前 JSONL 每条记录为：

```text
provenance = AI-drafted synthetic scenario
review_status = user_reviewed
```

项目负责人已逐条检查需求、期望 IR 和风险标签；`user_reviewed` 仅表示合成场景标签经人复核，不代表真实用户研究。评测脚本默认拒绝在待复核标签上生成正式模型报告。

2026-09-20 第一轮人工复核覆盖 50 条，其中 40 条批准、10 条指出具体错误。修订后第二轮复核全部批准；原始记录分别保存在 `data/reviews/round1.csv` 和 `data/reviews/round2.csv`。`review_dataset.py apply` 已将 50 条均标记为 `user_reviewed`。修订内容见 `docs/review_round2_changes.md`。

## 已知限制

- 语句风格和设备组合由设计者构造，不能代表自然分布。
- 仅覆盖 v0.1 允许的六类设备和有限 Home Assistant 语法。
- 安全标签仅说明项目定义范围内的规则，不是通用物联网安全标准。
- 实体准确率和槽位 F1 只在期望可执行的正常场景计算；歧义场景看澄清率，风险场景看阻断率与风险代码，三类样本不混算。
- 测试集在第一次正式运行后不得用于 Prompt 调优。
