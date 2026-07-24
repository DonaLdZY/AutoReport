# AutoReport

AutoReport 是 AutoDecision 的最终方案报告生成器。它读取 AutoRealize 的问题定义和 MLEvolve 已接受的搜索节点，按需补读候选代码，先形成结构化方法分析，再生成并检查面向使用者的 Markdown 报告。

AutoReport 的重点不是解释 AutoML 系统如何搜索，而是回答：最终方案做了什么、为什么可信、比其他候选好在哪里、有哪些限制，以及用户如何直接复用代码和产物。

## 报告内容

标准报告会尽量覆盖：

1. 摘要与交付结论。
2. 问题定义与验收口径。
3. 最终方案的数据处理、模型、算法或求解器流程。
4. 输入格式、运行命令、`predict()` 或 solver 接口和 artifact 复用。
5. 指标、评分组件、验证结果和交付物。
6. 与 Top-K 或其他有效候选的方法和效果对比。
7. 已知风险、适用边界和后续改进。
8. 交付检查清单。

没有证据支持的内容应标记为“现有证据未显示”，不能根据常识补写成既定事实。

## 工作流程

```text
AutoRealize 产物 + MLEvolve 日志/工作区 + 其他证据
                         |
                         v
                文件发现与来源识别
                         |
                         v
             有效节点与 Top-K 提取
                         |
                         v
          代码索引、头尾上下文与按需补读
                         |
                         v
             LLM 方法分析与压缩记忆
                         |
                         v
                LLM 撰写并检查报告
                         |
                         v
     report.md + report.json + 内部 trace + 运行状态
```

## 主要功能

- 同时读取多个证据根目录，并记录来源类型。
- 自动识别 AutoRealize、MLEvolve/AutoML 和通用证据。
- 提取任务说明、数据认知、评估合同、输出合同和样例提交。
- 提取最佳方案、Top-K 代码、metric、节点 insight 和模型 artifact。
- 从 journal 或 compact summary 中筛选 `is_buggy=false`、`search_eligible=true` 且 `is_valid` 不为 false 的可比较节点。
- 收集 `submission.csv`、`assignments.csv`、`metrics.json` 等交付文件。
- 长代码保留结构、头尾和可取回的行号索引，分析模型可按需补读中间源码。
- 跨阶段只传递结构化问题理解、方法卡和候选比较，不重复发送全部原始代码。
- 按技术、管理或交付读者调整表达，并支持中文或英文报告。
- 输出 Markdown、结构化 JSON、resolved config、事件流和当前状态。
- 提供 FastAPI 服务供 AutoDecision Gateway 编排。

## 候选语义

AutoReport 不重新裁决节点，只比较 MLEvolve Result Review 已接受的节点。核心条件是 `is_buggy=false`、`search_eligible=true`、`is_valid` 不为 false且 metric 有限。`delivery_ready` 和 `delivery_certified` 仅为 MLEvolve 的兼容字段，不参与报告候选筛选。

## 环境要求

- Conda、Miniconda 或 Miniforge
- Python 3.11 或 3.12，推荐 Python 3.12
- 可访问 OpenAI-compatible LLM API
- 已完成或部分完成的 AutoRealize / MLEvolve 证据目录
- 对证据目录和输出目录的读写权限

AutoReport 当前要求 LLM 可用。缺少模型名、API 地址或 API Key 时会失败，不会用固定模板伪造一份报告。

## Conda 环境安装

### 在 AutoDecision 主仓库中使用

```bash
cd AutoDecision
conda env create -f environment.yml
conda activate automl
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 独立安装 AutoReport

```bash
git clone https://github.com/DonaLdZY/AutoReport.git
cd AutoReport
conda create -n autoreport python=3.12 pip -y
conda activate autoreport
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

验证当前解释器：

```bash
python -c "import sys; print(sys.executable); print(sys.version)"
```

## 配置

默认配置文件是 [`config/config.yaml`](config/config.yaml)，包含完整中英文注释。CLI 未传 `--config` 时自动读取该文件，也可以指定其他位置的 YAML。

主要配置区：

| 配置 | 作用 |
| --- | --- |
| `task_name` | 任务标识 |
| `output_dir` | 报告和状态文件输出目录 |
| `report_title` | 人类可读标题 |
| `audience` | `technical`、`executive` 或 `delivery` |
| `language` | `zh-CN` 或 `en-US` |
| `evidence_paths` | 一个或多个证据目录、类型和必需性 |
| `collection` | 扫描上限、文件类型、日志和代码采集预算 |
| `comparison` | Top-K、成功/失败节点和交付物数量预算 |
| `analysis` | 报告详细程度、候选数量、代码补读轮次和终稿检查 |
| `generation` | prompt 字符预算、输出格式和文件名 |
| `llm` | 模型、API、thinking、输出 token 和重试 |
| `runtime` | resolved config、事件流、状态和服务日志 |

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
  context_window_tokens: 131072

analysis:
  detail_level: "detailed"
  comparison_candidate_limit: 6
  max_retrieval_rounds: 2
  enable_report_audit: true
```

`llm.api_key` 非空时优先使用配置值；为空时读取 `DEEPSEEK_API_KEY`。不要提交包含真实 API Key 的 YAML。

Linux / macOS：

```bash
export DEEPSEEK_API_KEY="your_api_key"
```

Windows PowerShell：

```powershell
$env:DEEPSEEK_API_KEY = "your_api_key"
```

### 证据类型

`evidence_paths[].kind` 支持：

- `autorealize`：任务、数据、合同和上下文产物。
- `mlevolve` 或 `automl`：搜索日志、工作区、候选和最佳方案。
- `generic`：调用方提供的普通证据目录。
- `auto`：根据文件结构自动判断。

`required: true` 的路径缺失时任务失败；可选路径缺失时记录 warning 并继续。

## CLI 运行

使用默认或指定 YAML：

```bash
python -m autoreport.cli --config config/config.yaml
```

也可以从命令行覆盖关键参数：

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

Windows PowerShell：

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

`--evidence` 可以重复使用，格式为 `label=path` 或 `label=path::kind`。模型参数可以通过 `--llm-model`、`--llm-base-url` 和 `--llm-api-key` 覆盖；API Key 更推荐使用 YAML 临时配置或环境变量，避免进入 shell 历史。

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

访问 `http://127.0.0.1:18104/docs` 查看 OpenAPI 文档。`POST /jobs/start` 可以传入 `config_path`，也可以直接接收前端生成的配置对象。

## 读取的关键证据

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
- `top_solution/top*/solution.py` 和 `metric.txt`
- `journal.json`、`filtered_journal.json`、`node_summary_compact.json`
- `run_status.json`、`llm_usage_brief.json`

### 交付物

- `submission.csv`
- `assignments.csv`
- `unassigned_orders.csv`
- `metrics.json`
- 其他由最佳方案生成的 CSV、JSON、模型或说明文件

具体文件数量和字符上限由 `collection`、`comparison` 和 `generation` 控制。

## 输出目录

```text
<output-dir>/
|-- report.md
|-- report.json
|-- report_trace.json
|-- resolved_config.yaml
|-- event_stream.jsonl
`-- current_state.json
```

- `report.md`：完整人类可读报告。
- `report.json`：结构化报告、章节和运行摘要。
- `report_trace.json`：内部方法分析、补读记录和终稿检查结果；不在用户报告中展示。
- `resolved_config.yaml`：实际运行配置，API Key 会被清除。
- `event_stream.jsonl`：采集与生成阶段事件。
- `current_state.json`：供服务和前端轮询的状态快照。

## Prompt 与成本控制

AutoReport 不会把整个运行目录拼接成一个超长 prompt：

1. 先完整发现相关文件，再按重要性应用内容读取预算，避免遍历顺序漏掉最佳方案。
2. 长代码提供 AST 函数/类索引和头尾片段；模型可用 `source_id + 行号` 补读中间内容。
3. 分析轮次将上一轮完整原文压缩为结构化方法卡，原始文件仍可取回。
4. 写作和审查阶段复用结构化分析，不重复携带全部代码。
5. 固定语言版 system prompt 始终位于消息前缀，动态材料和最新阶段指令位于后部，便于 provider 前缀缓存命中。
6. 接近上下文窗口时保留任务摘要、方法卡、源索引和最新补读内容，并预留输出 headroom。

降低候选数量、补读轮次或报告详细程度可以减少输入费用；终稿检查会增加一次模型调用。

## 测试

```bash
conda activate autoreport
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

在 AutoDecision 根环境中：

```bash
conda activate automl
python -m pytest core/AutoReport/tests -q
```

默认测试使用 mock，不调用真实 LLM。

## 常见问题

### 提示缺少 API Key

确认 `llm.api_key` 非空，或在启动 CLI/服务的同一 Conda 环境中设置 `DEEPSEEK_API_KEY`。AutoReport 不提供无 LLM 的固定模板 fallback。

### 报告没有比较其他方案

检查 MLEvolve 证据目录是否包含 `journal.json`、`top_solution/` 或 compact summary，并确认候选预算不为零。没有真实候选证据时，报告不会编造对比。

### 报告没有写清如何复用

检查最佳方案目录是否包含 `solution.py`、artifact、运行说明和实际输出。AutoReport 可以总结已有证据，但不能推断一个从未实现的 `predict()` 或 solver 接口。

### 扫描大型运行目录很慢

调整 `collection.max_files_per_path`、`include_raw_logs`、文本后缀和重要文件名列表。通常不需要读取每个节点的完整 stdout 和全部工作区副本。

### 报告纳入了无效节点

检查 compact summary 是否提供当前 `is_buggy`、`search_eligible` 和 `is_valid` 字段。AutoReport 不再使用 `delivery_ready` 兼容字段或缺字段时的乐观 fallback。

## 安全、边界与许可证

- 服务模式下 API Key 通过子进程环境变量或任务配置传递，resolved config 不应保存真实密钥。
- AutoReport API 默认只应由本机 Gateway 调用，不应直接暴露公网。
- AutoReport 基于现有证据组织交付文档，不替代独立模型审计、统计检验、安全评估或领域验收。
- 最终报告中的关键数字应能回溯到 metric、代码输出或结构化合同。
- 仓库加入明确许可证前，不应视为已经授权自由使用、修改或再分发。
