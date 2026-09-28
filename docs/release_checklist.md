# v0.1.0 发布清单

本清单把代码完成与需要本人、测试者或平台账号的事项分开，避免把准备状态写成已完成结果。

## 已自动验证

- [x] 独立本地 Git 仓库，不复用 EchoInsight 代码。
- [x] 公开合成设备清单、初始状态和 50 条场景。
- [x] Schema、允许列表、安全校验、状态仿真和 YAML 编译。
- [x] 离线公开案例模式与本地 Ollama 模式。
- [x] 原始 YAML 基线和受控 IR 工作流的同模型评测入口。
- [x] Prompt、环境、原始输出哈希、重试、延迟和 digest 记录能力。
- [x] 测试、CI、数据卡、隐私说明、失败记录、演示与求职文案模板。
- [x] 实际运行 Ollama 0.34.1 与 `qwen3:14b-q4_K_M`，保存完整 digest 和硬件记录。
- [x] 在 15 条开发场景运行受控流程与同模型直接 YAML 基线，保留原始输出和版本历史。
- [x] 10 条开发压力场景各重复 3 次，并固化 8 条真实本地模型演示案例。

## 需要项目负责人本人完成

- [x] 第一轮逐条审核 50 条：40 条批准、10 条指出需要修订；保留原始复核表。
- [x] 在 `data/review_sheet.csv` 再次确认 10 条修订项，保存第二轮原表并运行 `review_dataset.py apply`；50 条均为 `user_reviewed`。
- [x] 基于修订后 15 条开发集选定 v0.12，内容不变地冻结为 Prompt v1.0；冻结输入哈希见 `artifacts/freeze_v1.json`。
- [x] 记录冻结版对应 Git commit：`8ad9c0b5c867ff139eafeb121aa4c11f2b560885`。
- [x] 在修订后 15 条开发集运行受控流程与基线，保留原始输出并复算指标；旧标注结果单独留存。
- [x] 冻结后首次运行 35 条测试集，保存原始输出、逐例和汇总结果；不因补丁重复宣称独立测试。
- [x] 检查失败案例，保留 A05、S06、M05、M10 等不利结果；A05 测试后证据拦截补丁只通过回归测试。
- [x] 从人工复核的合成案例生成 10 条代表性 YAML，并通过本地静态检查；文件保存在 `tests/ha_config/automations.yaml`。
- [x] 10 条 YAML 已在 [GitHub CI 的 Home Assistant stable 隔离容器](https://github.com/Polaris-cyber/homeflow-guard/actions/runs/36423711947)通过配置检查。本机 Docker Linux 引擎仍未连接；不把 CI 检查写成本机手工导入。
- [ ] 招募 3 名未参与开发者，完成 6 个测试任务并保留原始记录。
- [ ] 用真实结果替换申请表、作品集和视频稿中的占位符。

## 需要平台账号或发布授权

- [x] 安装 GitHub CLI 2.101.0，已完成 GitHub 授权登录。
- [x] 安装 Docker Desktop 4.91.0 / Docker CLI 29.8.0。
- [x] 重启 Windows 后确认虚拟化与 Docker Linux 引擎可用；`hello-world` 容器实际运行通过。
- [ ] 本机 Home Assistant stable 容器配置检查：2026-09-20 Docker Linux 引擎未连接，未能运行；不能记为已通过。
- [x] 创建并推送公开 [GitHub 仓库](https://github.com/Polaris-cyber/homeflow-guard)。
- [x] 配置 GitHub Actions；[运行 36423711947](https://github.com/Polaris-cyber/homeflow-guard/actions/runs/36423711947)中 Python job 与 Home Assistant stable 容器检查均通过。Python job 覆盖 Ruff、32 项 pytest 和 50 条夹具回归评测。
- [x] 发布公开 [GitHub Release v0.1.0](https://github.com/Polaris-cyber/homeflow-guard/releases/tag/v0.1.0)，并在发布说明中列出真实指标、未达标项和产品边界。
- [ ] 部署 Streamlit 公开样例模式。
- [ ] 录制并上传 2–3 分钟演示视频。
- [ ] 将最终 Demo、仓库和视频链接填回文档。

## 发布前真实性检查

- [x] 已扫描待发布项目，未发现真实 Token、地址、家庭成员、公司内部材料或未授权访谈；仍需在每次发布前复查新增内容。
- [x] 模型完整标签、Ollama 版本、digest、日期和硬件来自实际记录。
- [x] fixture 自检未被写成模型表现。
- [x] 合成评测未被写成真实用户研究。
- [ ] 3 人测试明确称为小样本可用性测试。
- [x] 当前报告中的比例可由仓库原始结果与重算脚本复算；基线延迟修正单独说明。
- [x] 当前未完成或未达标项如实说明；发布后继续保持。
