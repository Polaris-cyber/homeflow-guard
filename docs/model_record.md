# 模型与运行环境记录

## 已实际使用

- 运行日期：2026-09-18、2026-09-20（Asia/Shanghai）
- Ollama：0.34.1
- 模型完整标签：`qwen3:14b-q4_K_M`
- Manifest digest：`bdbd181c33f2ed1b31c972991882db3cf4d192569092138a7d29e973cd9debe8`
- 已运行 Prompt/工作流版本：`compiler-dev-v0.8`、`compiler-dev-v0.9-review-corrections`、`compiler-dev-v0.10-repair-gate`、`compiler-dev-v0.11-repair-context`、`compiler-dev-v0.12-threshold-schema`、冻结版 `compiler-v1.0`。v0.12 仅使用 15 条开发集选定，内容不变地冻结为 v1.0；2026-09-20 在 v1.0 上首次运行 35 条测试集。
- 测试后新增 `compiler-v1.0.1-post-test-safety` 确定性需求证据拦截；它只通过代码回归测试，**尚未作为模型工作流运行，也没有独立测试集成绩**。
- 当前 Schema 版本：`automation-ir-v0.4`。数值触发器/条件在模型输出 Schema 中必须显式包含 `above` 与 `below`，未用项为 `null`；运行时仍要求至少一项为数值。
- 生成配置：temperature 0、seed 42、num_ctx 8192、think false
- Python：3.13.12
- GPU：NVIDIA GeForce RTX 5070 Ti，16GB，驱动 595.79

## 未使用或未完成

- `qwen3:8b-q4_K_M` 未安装、未运行，只是 14B 无法稳定运行时的预设降级方案。
- 35 条锁定测试集已在冻结版 v1.0 上运行一次；不能将该成绩归于测试后的 v1.0.1 补丁。
- 公开 Streamlit 环境不调用在线模型，只展示 8 条固化的实际本地运行结果。

机器可读环境记录见 `artifacts/environment.json`；每次推理的模型、digest、Prompt、延迟、哈希、重试和解析状态见 `artifacts/model_runs/`。该文件不记录用户名、主机名、IP、Token 或真实设备清单。
