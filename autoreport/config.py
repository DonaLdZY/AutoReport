from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 compatibility.
    import tomli as tomllib


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "config.yaml"


DEFAULT_TEXT_SUFFIXES = (
    ".md",
    ".txt",
    ".log",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".toml",
    ".py",
    ".csv",
)

DEFAULT_IMPORTANT_NAMES = (
    "data_description.md",
    "description.md",
    "data_cognition_report.json",
    "constraint_memory.json",
    "knowledge_base.json",
    "autorealize_context.md",
    "automl_context.md",
    "sample_submission.csv",
    "submission.csv",
    "submissions.csv",
    "assignments.csv",
    "unassigned_orders.csv",
    "metrics.json",
    "report.json",
    "report.md",
    "run_summary.json",
    "run_status.json",
    "current_state.json",
    "event_stream.jsonl",
    "journal.json",
    "filtered_journal.json",
    "node_summary_compact.json",
    "pending_nodes.json",
    "best_solution.py",
    "solution.py",
    "metric.txt",
    "node_id.txt",
    "model_path.txt",
    "model_artifacts_manifest.md",
    "llm_usage_brief.json",
    "llm_usage_summary.json",
    "mlevolve.log",
)


@dataclass
class EvidencePath:
    label: str
    path: str
    kind: str = "auto"
    required: bool = False


@dataclass
class CollectionConfig:
    max_files_per_path: int = 700
    max_text_chars_per_file: int = 40000
    include_raw_logs: bool = True
    include_code_excerpt: bool = True
    text_suffixes: tuple[str, ...] = DEFAULT_TEXT_SUFFIXES
    important_names: tuple[str, ...] = DEFAULT_IMPORTANT_NAMES
    jsonl_max_lines: int = 200
    json_key_limit: int = 80
    json_array_item_limit: int = 20
    json_compact_max_depth: int = 3
    csv_preview_rows: int = 8
    csv_cell_chars: int = 120


@dataclass
class ComparisonConfig:
    best_metric_excerpt_chars: int = 3000
    best_code_excerpt_chars: int = 12000
    model_manifest_excerpt_chars: int = 4000
    top_solution_limit: int = 8
    successful_node_limit: int = 12
    failed_node_limit: int = 10
    failure_pattern_limit: int = 12
    delivery_artifact_limit: int = 40
    node_plan_chars: int = 1000
    node_analysis_chars: int = 1400
    node_terminal_tail_chars: int = 1000


@dataclass
class GenerationConfig:
    max_report_chars_per_section: int = 60000
    max_prompt_chars: int = 60000
    selected_context_item_limit: int = 32
    evidence_index_limit: int = 160
    evidence_root_chars: int = 5000
    evidence_warning_chars: int = 5000
    solution_evidence_chars: int = 32000
    description_chars: int = 12000
    data_description_chars: int = 9000
    sample_submission_chars: int = 3000
    context_item_chars: int = 3000
    context_block_chars: int = 18000
    evidence_index_chars: int = 12000
    write_report_json: bool = True
    write_report_markdown: bool = True
    report_json_filename: str = "report.json"
    report_markdown_filename: str = "report.md"


@dataclass
class LLMConfig:
    enabled: bool = True
    model: str = "deepseek-chat"
    base_url: str = "https://api.deepseek.com"
    api_key: str | None = field(default_factory=lambda: os.environ.get("DEEPSEEK_API_KEY"))
    temperature: float = 0.25
    max_tokens: int | None = 8192
    request_timeout_seconds: int = 180
    max_retries: int = 5
    retry_base_sleep_seconds: float = 5.0
    retry_max_sleep_seconds: float = 30.0
    enable_thinking: bool | None = None
    reasoning_effort: str | None = None


@dataclass
class RuntimeConfig:
    write_resolved_config: bool = True
    resolved_config_filename: str = "resolved_config.yaml"
    event_stream_filename: str = "event_stream.jsonl"
    current_state_filename: str = "current_state.json"
    recent_events_limit: int = 120
    print_events_to_console: bool = True
    snapshot_event_limit: int = 500
    snapshot_text_tail_chars: int = 60000
    service_log_tail_chars: int = 120000
    service_last_error_chars: int = 300
    service_stop_wait_seconds: float = 15.0


@dataclass
class AutoReportConfig:
    task_name: str
    output_dir: str
    report_title: str = ""
    audience: str = "technical"
    language: str = "zh-CN"
    evidence_paths: list[EvidencePath] = field(default_factory=list)
    collection: CollectionConfig = field(default_factory=CollectionConfig)
    comparison: ComparisonConfig = field(default_factory=ComparisonConfig)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)

    def __post_init__(self) -> None:
        self.evidence_paths = [_as_evidence_path(item) for item in self.evidence_paths]
        if all(
            (
                isinstance(self.collection, CollectionConfig),
                isinstance(self.comparison, ComparisonConfig),
                isinstance(self.generation, GenerationConfig),
                isinstance(self.llm, LLMConfig),
                isinstance(self.runtime, RuntimeConfig),
            )
        ):
            return

        # Programmatic callers historically passed nested dictionaries. Normalize
        # them through the same path as YAML/JSON/TOML loading.
        legacy_llm = self.llm if isinstance(self.llm, dict) else {}
        normalized = config_from_dict(
            {
                "task_name": self.task_name,
                "output_dir": self.output_dir,
                "report_title": self.report_title,
                "audience": self.audience,
                "language": self.language,
                "evidence_paths": [asdict(item) for item in self.evidence_paths],
                "collection": self.collection
                if isinstance(self.collection, dict)
                else asdict(self.collection),
                "comparison": self.comparison
                if isinstance(self.comparison, dict)
                else asdict(self.comparison),
                "generation": self.generation
                if isinstance(self.generation, dict)
                else asdict(self.generation),
                "llm": self.llm if isinstance(self.llm, dict) else asdict(self.llm),
                "runtime": self.runtime
                if isinstance(self.runtime, dict)
                else asdict(self.runtime),
            }
        )
        if legacy_llm.get("max_prompt_chars") not in {None, ""}:
            normalized.generation.max_prompt_chars = int(legacy_llm["max_prompt_chars"])
        self.collection = normalized.collection
        self.comparison = normalized.comparison
        self.generation = normalized.generation
        self.llm = normalized.llm
        self.runtime = normalized.runtime

    # Compatibility properties for existing collector/generator integrations.
    @property
    def max_files_per_path(self) -> int:
        return self.collection.max_files_per_path

    @property
    def max_text_chars_per_file(self) -> int:
        return self.collection.max_text_chars_per_file

    @property
    def include_raw_logs(self) -> bool:
        return self.collection.include_raw_logs

    @property
    def include_code_excerpt(self) -> bool:
        return self.collection.include_code_excerpt

    @property
    def max_report_chars_per_section(self) -> int:
        return self.generation.max_report_chars_per_section

    @property
    def use_llm(self) -> bool:
        return self.llm.enabled


def _as_evidence_path(item: Any) -> EvidencePath:
    if isinstance(item, EvidencePath):
        return item
    if isinstance(item, str):
        return EvidencePath(label=Path(item).name or "evidence", path=item)
    if isinstance(item, dict):
        return EvidencePath(
            label=str(item.get("label") or Path(str(item.get("path", ""))).name or "evidence"),
            path=str(item.get("path") or ""),
            kind=str(item.get("kind") or "auto"),
            required=bool(item.get("required", False)),
        )
    raise TypeError(f"Unsupported evidence path item: {item!r}")


def _section(raw: dict[str, Any], name: str, legacy_keys: tuple[str, ...]) -> dict[str, Any]:
    section = dict(raw.get(name) or {})
    for key in legacy_keys:
        if key in raw and key not in section:
            section[key] = raw[key]
    return section


def _tuple_strings(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)


def config_from_dict(raw: dict[str, Any]) -> AutoReportConfig:
    evidence = [_as_evidence_path(x) for x in raw.get("evidence_paths", [])]

    collection_raw = _section(
        raw,
        "collection",
        (
            "max_files_per_path",
            "max_text_chars_per_file",
            "include_raw_logs",
            "include_code_excerpt",
        ),
    )
    comparison_raw = _section(raw, "comparison", ())
    generation_raw = _section(raw, "generation", ("max_report_chars_per_section",))
    llm_raw = dict(raw.get("llm") or {})
    runtime_raw = dict(raw.get("runtime") or {})

    if "use_llm" in raw and "enabled" not in llm_raw:
        llm_raw["enabled"] = raw["use_llm"]
    if "max_prompt_chars" in llm_raw and "max_prompt_chars" not in generation_raw:
        generation_raw["max_prompt_chars"] = llm_raw["max_prompt_chars"]

    collection = CollectionConfig(
        max_files_per_path=int(collection_raw.get("max_files_per_path", 700)),
        max_text_chars_per_file=int(collection_raw.get("max_text_chars_per_file", 40000)),
        include_raw_logs=bool(collection_raw.get("include_raw_logs", True)),
        include_code_excerpt=bool(collection_raw.get("include_code_excerpt", True)),
        text_suffixes=_tuple_strings(collection_raw.get("text_suffixes"), DEFAULT_TEXT_SUFFIXES),
        important_names=_tuple_strings(collection_raw.get("important_names"), DEFAULT_IMPORTANT_NAMES),
        jsonl_max_lines=int(collection_raw.get("jsonl_max_lines", 200)),
        json_key_limit=int(collection_raw.get("json_key_limit", 80)),
        json_array_item_limit=int(collection_raw.get("json_array_item_limit", 20)),
        json_compact_max_depth=int(collection_raw.get("json_compact_max_depth", 3)),
        csv_preview_rows=int(collection_raw.get("csv_preview_rows", 8)),
        csv_cell_chars=int(collection_raw.get("csv_cell_chars", 120)),
    )
    comparison = ComparisonConfig(
        **{
            key: int(comparison_raw.get(key, getattr(ComparisonConfig(), key)))
            for key in ComparisonConfig.__dataclass_fields__
        }
    )
    generation = GenerationConfig(
        **{
            key: (
                bool(generation_raw.get(key, getattr(GenerationConfig(), key)))
                if key in {"write_report_json", "write_report_markdown"}
                else str(generation_raw.get(key, getattr(GenerationConfig(), key)))
                if key in {"report_json_filename", "report_markdown_filename"}
                else int(generation_raw.get(key, getattr(GenerationConfig(), key)))
            )
            for key in GenerationConfig.__dataclass_fields__
        }
    )
    llm = LLMConfig(
        enabled=bool(llm_raw.get("enabled", True)),
        model=str(llm_raw.get("model") or llm_raw.get("model_name") or "deepseek-chat"),
        base_url=str(llm_raw.get("base_url") or llm_raw.get("baseUrl") or "https://api.deepseek.com"),
        api_key=str(llm_raw.get("api_key") or llm_raw.get("apiKey") or "").strip()
        or os.environ.get("DEEPSEEK_API_KEY"),
        temperature=float(llm_raw.get("temperature", 0.25)),
        max_tokens=(
            None
            if llm_raw.get("max_tokens") in {None, "", 0, "0"}
            else int(llm_raw.get("max_tokens"))
        ),
        request_timeout_seconds=int(
            llm_raw.get("request_timeout_seconds") or llm_raw.get("timeout") or 180
        ),
        max_retries=int(llm_raw.get("max_retries", 5)),
        retry_base_sleep_seconds=float(llm_raw.get("retry_base_sleep_seconds", 5.0)),
        retry_max_sleep_seconds=float(llm_raw.get("retry_max_sleep_seconds", 30.0)),
        enable_thinking=llm_raw.get("enable_thinking"),
        reasoning_effort=llm_raw.get("reasoning_effort"),
    )
    runtime = RuntimeConfig(
        write_resolved_config=bool(runtime_raw.get("write_resolved_config", True)),
        resolved_config_filename=str(runtime_raw.get("resolved_config_filename", "resolved_config.yaml")),
        event_stream_filename=str(runtime_raw.get("event_stream_filename", "event_stream.jsonl")),
        current_state_filename=str(runtime_raw.get("current_state_filename", "current_state.json")),
        recent_events_limit=int(runtime_raw.get("recent_events_limit", 120)),
        print_events_to_console=bool(runtime_raw.get("print_events_to_console", True)),
        snapshot_event_limit=int(runtime_raw.get("snapshot_event_limit", 500)),
        snapshot_text_tail_chars=int(runtime_raw.get("snapshot_text_tail_chars", 60000)),
        service_log_tail_chars=int(runtime_raw.get("service_log_tail_chars", 120000)),
        service_last_error_chars=int(runtime_raw.get("service_last_error_chars", 300)),
        service_stop_wait_seconds=float(runtime_raw.get("service_stop_wait_seconds", 15.0)),
    )

    return AutoReportConfig(
        task_name=str(raw.get("task_name") or raw.get("run_name") or "autoreport_task"),
        output_dir=str(raw.get("output_dir") or raw.get("report_dir") or "runs/autoreport"),
        report_title=str(raw.get("report_title") or ""),
        audience=str(raw.get("audience") or "technical"),
        language=str(raw.get("language") or "zh-CN"),
        evidence_paths=evidence,
        collection=collection,
        comparison=comparison,
        generation=generation,
        llm=llm,
        runtime=runtime,
    )


def load_config(path: str | Path) -> AutoReportConfig:
    config_path = Path(path).expanduser().resolve()
    text = config_path.read_text(encoding="utf-8-sig")
    suffix = config_path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        raw = yaml.safe_load(text)
    elif suffix == ".json":
        raw = json.loads(text)
    elif suffix in {".toml", ".tml"}:
        raw = tomllib.loads(text)
    else:
        raise ValueError(f"Unsupported config format: {config_path}. Use YAML, JSON, or TOML.")
    if not isinstance(raw, dict):
        raise ValueError("AutoReport config must be a mapping/object")
    return config_from_dict(raw)


def config_schema() -> dict[str, Any]:
    return {
        "schema_version": "autoreport.config.v2",
        "format": "YAML preferred; JSON/TOML compatible",
        "description_zh": "AutoReport 单文件配置，控制证据采集、候选比较、报告生成、模型与运行遥测。",
        "description_en": "Single-file AutoReport configuration for evidence collection, comparison, generation, LLM, and telemetry.",
        "example": dump_config(
            AutoReportConfig(task_name="demo_task", output_dir="runs/demo_task/report")
        ),
    }


def dump_config(
    cfg: AutoReportConfig,
    *,
    include_secrets: bool = False,
) -> dict[str, Any]:
    llm = asdict(cfg.llm)
    if not include_secrets:
        llm["api_key"] = None
    return {
        "task_name": cfg.task_name,
        "output_dir": cfg.output_dir,
        "report_title": cfg.report_title,
        "audience": cfg.audience,
        "language": cfg.language,
        "evidence_paths": [asdict(item) for item in cfg.evidence_paths],
        "collection": asdict(cfg.collection),
        "comparison": asdict(cfg.comparison),
        "generation": asdict(cfg.generation),
        "llm": llm,
        "runtime": asdict(cfg.runtime),
    }


def write_config_yaml(
    cfg: AutoReportConfig,
    path: str | Path,
    *,
    include_secrets: bool = False,
) -> None:
    Path(path).write_text(
        yaml.safe_dump(
            dump_config(cfg, include_secrets=include_secrets),
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
