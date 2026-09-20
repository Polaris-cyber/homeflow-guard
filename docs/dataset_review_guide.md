# 评测集人工复核指南

评测集是合成数据，不是用户行为数据。AI 可以起草，但正式测试前必须由项目负责人逐条确认标签。

## 操作

1. 首次审核时运行 `python scripts/review_dataset.py export`。
2. 打开 `data/review_sheet.csv`，逐条核对：用户需求、应否澄清、实体、触发器、条件、动作、参数和风险标签。
3. `decision` 只填写 `approved` 或 `needs_revision`，必要时在 `reviewer_notes` 说明理由。
4. 若存在 `needs_revision`，先保留原表，再修改 `scripts/build_dataset.py` 中对应案例、重新生成数据，并运行 `python scripts/review_dataset.py refresh`。它仅继承内容完全未变的批准项；所有修订项必须再次确认。
5. 全部通过后运行 `python scripts/review_dataset.py apply`。
6. 提交评测前运行 `python scripts/evaluate.py --mode ollama --pipeline both --split test`；未完成复核时脚本会拒绝正式测试。

`apply` 命令不会从 CSV 覆盖标准答案，只记录审核状态和备注，以避免电子表格编辑损坏结构化标签。

注意：`build_dataset.py` 是源数据重建工具，会把审核状态恢复为 `pending_user_review`；审核通过后不要再次运行，除非确实修改了案例并准备重新逐条复核。

## 第二轮复核结果

2026-09-20 第一轮 50 条均有明确决定：40 条批准，10 条要求修订。原始表完整保存在 `data/reviews/round1.csv`。针对意见修订了室温属性、未授权亮度、卧室人体传感器和“日落后/日落时”语义。项目负责人第二轮批准全部 10 条，记录保存在 `data/reviews/round2.csv`；其余 40 条沿用内容未变的批准决定。当前 50 条 JSONL 均标记 `user_reviewed`。

逐条修改摘要见 [第二轮复核清单](review_round2_changes.md)。

`apply` 会逐字段比对表格与当前源数据，并拒绝缺失决定、重复 ID 或过时内容。若未来修改任何案例，需重新复核改动项，不能沿用当前批准状态。

## 防泄漏约束

- 15 条开发集可以用于 Prompt 调试。
- 35 条测试集只在 Prompt v1.0 冻结后运行。
- 查看测试结果后不得继续调 Prompt 并把新结果称为同一轮独立测试。
- 任何重测必须保留日期、代码提交、Prompt 版本和原因。
