# AutoReport

AutoReport 是 AutoDecision 的证据驱动型方案交付报告生成器。它读取 AutoRealize、MLEvolve 或调用方指定目录中的任务事实、最优代码、候选指标、失败记录和交付物，将这些材料压缩成证据简报，再由 LLM 生成面向人类读者的 Markdown 报告。

AutoReport 的重点不是解释 AutoML 系统如何搜索，而是回答：最终方案做了什么、为什么可信、比其他候选好在哪里、有哪些限制，以及用户如何直接复用代码和产物。

## 报告目标

一份标准报告会尽量覆盖：

1. 摘要与交付结论。
2. 问题定义与验收口径。
3. 最终方案的数据处理、模型/算法/求解器和输出流程。
4. 输入格式、运行命令、`predict()` 或 solver 接口和 artifact 复用。
5. 指标、评分组件、验证结果和交付物。
6. 与 Top-K 或其他搜索候选的真实证据对比。
7. 已知风险、适用边界和后续改进。
8. 交付检查清单。

没有证据支持的内容必须明确标记为“现有证据未显示”，不能根据常识补写成既定事实。

## 工作流程

```text
AutoRealize 产物 + MLEvolve 日志/工作区 + 其他证据目录
                         |
                         v
                文件发现与类型识别
                         |
                         v
             最优方案、候选、失败模式提取
                         |
                         v
             确定性裁剪与压缩 evidence briefing
                         |
                         v
                  LLM 撰写交付报告
                         |
                         v
             report.md + report.json + 运行状态
```

## 主要功能

- 同时收集多个证据根目录，并标记其来源类型。
- 自动识别 AutoRealize、MLEvolve/AutoML 和通用证据。
- 提取任务说明、数据认知、评估协议、输出合同和样例提交。
- 提取 `best_solution`、Top-K 代码、metric、节点 insight 和模型 artifact。
- 从 `journal.json`、`filtered_journal.json` 或 compact summary 中整理成功/失败候选。
- 收集 `submission.csv`、`assignments.csv`、`metrics.json` 等交付文件。
- 将完整日志和大 journal 转换为有限长度的结构化证据，而不是全部放入 prompt。
- 按技术、管理或交付读者调整报告表达。
- 生成中文或英文报告。
- 输出 Markdown、结构化 JSON、resolved config、事件流和当前状态。
- 提供 FastAPI 服务供 AutoDecision Gateway 编排。

## 功能亮点

### 以最终方案为主语

报告描述的是最终模型、算法或求解器，不会把大篇幅用于介绍搜索树、agent 数量或系统内部工作流。方法章节应具体说明数据读取、预处理、特征/状态/动作、约束处理、评分和输出构造。

### 真实候选对比

AutoReport 会从最优方案、Top-K、成功节点、失败节点和日志证据中提取可比较信息。只有存在真实指标、方法或失败理由时才进行结论性比较。

### 面向代码复用

报告会尽量说明：

- 输入目录和文件结构。
- 依赖与运行命令。
- `predict(model_path, data)` 或求解器入口。
- 模型、预处理器、策略或求解器 artifact。
- 输出路径、列和格式。
- 是否需要重新训练或可直接推理。

### 控制 LLM 上下文成本

完整源代码、日志和 journal 保留在磁盘；prompt 只接收受配置预算控制的代码摘要、指标、候选比较和证据索引。这样可以减少重复输入 token，也避免长日志掩盖关键结果。

## 环境要求

- Python 3.11 或 3.12
- 可访问 OpenAI-compatible LLM API
- 已完成或部分完成的 AutoRealize/MLEvolve 证据目录
- 对证据目录和报告输出目录的读取/写入权限

AutoReport 当前要求 LLM 可用。缺少模型名、API 地址或 API Key 时会直接失败，而不是生成固定模板报告。

> 安全提示：服务模式下 API Key 通过子进程环境变量传递，生成的 `_service_config.yaml` 和 `resolved_config.yaml` 不保存真实 Key。AutoReport API 默认只应由本机 Gateway 调用，不应直接暴露公网。

## 安装

```bash
git clone https://github.com/DonaLdZY/AutoReport.git
cd AutoReport
python -m venv .venv
```

Windows：

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Linux/macOS：

```bash
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

在 AutoDecision 主仓库中使用时，也可以由根 `requirements.txt` 统一安装。

## 配置

[`config/config.yaml`](config/config.yaml) 是唯一的正式默认配置，包含完整注释。CLI 未传 `--config` 时自动读取该文件；也可以通过 `--config` 指定任意其他位置的 YAML。

主要配置区：

| 配置 | 作用 |
| --- | --- |
| `task_name` | 任务标识 |
| `output_dir` | 报告与状态文件输出目录 |
| `report_title` | 人类可读标题 |
| `audience` | `technical`、`executive` 或 `delivery` |
| `language` | `zh-CN` 或 `en-US` |
| `evidence_paths` | 一个或多个证据目录、类型和必需性 |
| `collection` | 扫描上限、文件类型、日志/代码采集与预览预算 |
| `comparison` | Top-K、成功/失败节点和交付物数量预算 |
| `generation` | prompt 字符预算、输出格式和文件名 |
| `llm` | 模型、API、thinking、`reasoning_effort`、`max_tokens` 和重试 |
| `runtime` | resolved config、事件流、状态和服务日志行为 |

最小配置示例：

```yaml
task_name: "demo_task"
output_dir: "../../runs/demo_task/report"
report_title: "demo_task 方案交付报告"
audience: "delivery"
language: "zh-CN"

evidence_paths:
  - label: "autorealize"
    path: "../../runs/demo_task/autorealize"
    kind: "autorealize"
    required: true
  - label: "automl"
    path: "../../runs/demo_task/automl"
    kind: "mlevolve"
    required: false

llm:
  enabled: true
  model: "deepseek-v4-pro"
  base_url: "https://api.deepseek.com"
  api_key: null
  max_tokens: 8192
  enable_thinking: null
  reasoning_effort: null
```

`llm.api_key` 非空时优先使用配置值；为空时读取 `DEEPSEEK_API_KEY`。`max_tokens` 为 `null` 或 `0` 时由服务商决定。不要提交包含真实 API Key 的配置。

### 证据类型

`evidence_paths[].kind` 支持：

- `autorealize`：任务、数据、合同和上下文产物。
- `mlevolve` 或 `automl`：搜索日志、工作区、候选和最优方案。
- `generic`：调用方提供的普通证据目录。
- `auto`：根据文件结构自动判断。

`required: true` 的路径缺失时任务失败；可选路径缺失时记录 warning 并继续。

## CLI 运行

使用 YAML：

```bash
python -m autoreport.cli --config config/config.yaml
```

也可以用命令行直接覆盖：

```bash
python -m autoreport.cli \
  --task-name demo_task \
  --output-dir ../../runs/demo_task/report \
  --report-title "demo_task 方案交付报告" \
  --audience delivery \
  --language zh-CN \
  --evidence autorealize=../../runs/demo_task/autorealize::autorealize \
  --evidence automl=../../runs/demo_task/automl::mlevolve
```

PowerShell：

```powershell
python -m autoreport.cli `
  --task-name "demo_task" `
  --output-dir "..\..\runs\demo_task\report" `
  --report-title "demo_task 方案交付报告" `
  --audience "delivery" `
  --language "zh-CN" `
  --evidence "autorealize=..\..\runs\demo_task\autorealize::autorealize" `
  --evidence "automl=..\..\runs\demo_task\automl::mlevolve"
```

`--evidence` 可以重复使用，格式为 `label=path` 或 `label=path::kind`。模型参数也可通过 `--llm-model`、`--llm-base-url` 和 `--llm-api-key` 覆盖，但更推荐使用 YAML 或环境变量，避免密钥进入 shell 历史。

## 服务模式

```bash
python -m uvicorn service_api:app --host 127.0.0.1 --port 18104
```

常用接口：

- `GET /health`
- `GET /usage`
- `GET /config/schema`
- `POST /jobs/start`
- `GET /jobs/{job_id}`
- `POST /jobs/stop`
- `POST /snapshot`

访问 `http://127.0.0.1:18104/docs` 查看 OpenAPI 文档。`POST /jobs/start` 可接收 `config_path`，也可以直接接收前端生成的配置对象。

## 读取的关键证据

AutoReport 会优先识别以下材料；具体数量和字符上限由配置控制：

### AutoRealize

- `description.md`
- `sample_submission.csv`
- `realize_report/data_description.md`
- `realize_report/automl_context.md`
- `realize_report/evaluation_contract_report.json`
- `realize_report/data_cognition_report.json`
- `realize_report/question_investigation_report.json`

### MLEvolve

- `best_solution/solution.py`
- `best_solution/metric.txt`
- `best_solution/node_id.txt`
- 模型或求解器 artifact manifest
- `top_solution/top*/solution.py` 与 `metric.txt`
- `journal.json`、`filtered_journal.json`、`node_summary_compact.json`
- `run_status.json`、`llm_usage_brief.json`

### 交付产物

- `submission.csv`
- `assignments.csv`
- `unassigned_orders.csv`
- `metrics.json`
- 其他由最佳方案生成的 CSV、JSON、模型或说明文件

## 输出目录

```text
<output-dir>/
|-- report.md
|-- report.json
|-- resolved_config.yaml
|-- event_stream.jsonl
`-- current_state.json
```

- `report.md`：完整人类可读报告。
- `report.json`：包含 schema version、标题、完整 Markdown、章节切分、证据摘要和元数据。
- `resolved_config.yaml`：实际运行配置，API Key 会被清除。
- `event_stream.jsonl`：采集与生成阶段事件。
- `current_state.json`：适合服务和前端轮询的状态快照。

输出文件名和是否生成 Markdown/JSON 均可在 `generation`、`runtime` 中修改。

## Prompt 与成本控制

AutoReport 不会把所有文件串接成一个超长 prompt。生成前会：

1. 按重要文件名和来源类型筛选证据。
2. 对 JSON、JSONL、CSV、日志和代码做确定性裁剪。
3. 单独提取最优方案、候选比较、失败模式和交付物。
4. 根据 `generation.max_prompt_chars` 等预算构建 evidence briefing。
5. 将完整证据路径保留在索引中，供报告引用和人工复核。

降低预算可以减少输入费用，但也可能削弱方法细节和候选比较。应优先减少无关日志和重复候选，而不是裁掉评估合同、最佳 metric 或复用入口。

## 测试

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m ruff check autoreport service_api.py tests --select E9,F63,F7,F82
```

测试覆盖 YAML 配置、证据收集、候选比较、prompt briefing、报告输出、服务配置和状态事件。默认测试应使用 mock，不调用真实 LLM。

## 常见问题

### 提示缺少 API Key

确认 `llm.api_key` 非空，或设置 `DEEPSEEK_API_KEY`。AutoReport 不提供无 LLM 的固定模板 fallback。

### 报告没有比较其他方案

检查 MLEvolve 证据目录是否包含 `journal.json`、`top_solution/` 或 compact summary，并确认 `comparison.top_solution_limit` 等预算不为零。没有真实候选证据时，报告不会编造对比。

### 报告没有写清如何复用

检查最佳方案目录是否包含 `solution.py`、artifact、运行说明和实际输出。AutoReport 可以总结已有证据，但不能推断一个从未实现的 `predict()` 或部署接口。

### 扫描大型运行目录很慢

调整 `collection.max_files_per_path`、`include_raw_logs`、文本后缀和重要文件名列表。通常不需要读取每个节点的完整 stdout 和全部工作区副本。

## 使用边界

AutoReport 负责基于现有证据组织交付文档，不替代独立的模型审计、统计显著性检验、安全评估或领域验收。最终报告中的关键数字应能回溯到 metric、代码输出或结构化合同。
