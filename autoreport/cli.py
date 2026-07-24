from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

from .collector import collect_evidence
from .config import (
    AutoReportConfig,
    DEFAULT_CONFIG_PATH,
    EvidencePath,
    config_from_dict,
    dump_config,
    load_config,
    write_config_yaml,
)
from .events import ReportEventWriter
from .generator import generate_report


def parse_evidence(value: str) -> EvidencePath:
    if "=" not in value:
        return EvidencePath(label=Path(value).name or "evidence", path=value)
    label, rest = value.split("=", 1)
    kind = "auto"
    path = rest
    if "::" in rest:
        path, kind = rest.rsplit("::", 1)
    return EvidencePath(
        label=label.strip() or "evidence",
        path=path.strip(),
        kind=kind.strip() or "auto",
    )


def build_config(args: argparse.Namespace) -> AutoReportConfig:
    if args.config:
        raw = dump_config(load_config(args.config), include_secrets=True)
    elif DEFAULT_CONFIG_PATH.exists():
        raw = dump_config(load_config(DEFAULT_CONFIG_PATH), include_secrets=True)
    else:
        raw = {
            "task_name": args.task_name or "autoreport_task",
            "output_dir": args.output_dir or "runs/autoreport",
            "report_title": args.report_title or "",
            "audience": args.audience or "technical",
            "language": args.language or "zh-CN",
            "evidence_paths": [],
        }

    for key, value in (
        ("task_name", args.task_name),
        ("output_dir", args.output_dir),
        ("report_title", args.report_title),
        ("audience", args.audience),
        ("language", args.language),
    ):
        if value:
            raw[key] = value

    llm = dict(raw.get("llm") or {})
    if args.llm_model:
        llm["model"] = args.llm_model
    if args.llm_base_url:
        llm["base_url"] = args.llm_base_url
    if args.llm_api_key:
        llm["api_key"] = args.llm_api_key
    llm["enabled"] = True
    raw["llm"] = llm

    if args.evidence:
        raw["evidence_paths"] = [
            item.__dict__ for item in (parse_evidence(value) for value in args.evidence)
        ]
    if not raw.get("evidence_paths"):
        raise ValueError(
            "At least one evidence path is required. "
            "Use evidence_paths in config/config.yaml or --evidence label=path."
        )
    return config_from_dict(raw)


def run(cfg: AutoReportConfig) -> dict:
    output_dir = Path(cfg.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    events = ReportEventWriter(
        output_dir,
        run_id=uuid.uuid4().hex,
        event_stream_filename=cfg.runtime.event_stream_filename,
        current_state_filename=cfg.runtime.current_state_filename,
        recent_events_limit=cfg.runtime.recent_events_limit,
        print_events_to_console=cfg.runtime.print_events_to_console,
    )
    events.log(
        "autoreport.pipeline",
        "STARTED",
        task_name=cfg.task_name,
        output_dir=str(output_dir),
    )
    try:
        if cfg.runtime.write_resolved_config:
            write_config_yaml(
                cfg,
                output_dir / cfg.runtime.resolved_config_filename,
            )
        bundle = collect_evidence(cfg, events)
        payload = generate_report(cfg, bundle, events)
        events.log(
            "autoreport.pipeline",
            "COMPLETED",
            report_json=str(output_dir / cfg.generation.report_json_filename)
            if cfg.generation.write_report_json
            else "",
            report_md=str(output_dir / cfg.generation.report_markdown_filename)
            if cfg.generation.write_report_markdown
            else "",
        )
        return payload
    except Exception as exc:
        events.log(
            "autoreport.pipeline",
            "FAILED",
            error=str(exc)[:1000],
        )
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate an AutoDecision evidence-driven report."
    )
    parser.add_argument(
        "--config",
        help="配置路径；默认读取 config/config.yaml，兼容 JSON/TOML。",
    )
    parser.add_argument("--task-name", help="Override task name.")
    parser.add_argument("--output-dir", help="Override report output directory.")
    parser.add_argument("--report-title", default="", help="Human-facing report title.")
    parser.add_argument("--audience", default="", help="technical | executive | delivery")
    parser.add_argument("--language", default="", help="zh-CN | en-US")
    parser.add_argument("--llm-model", default="", help="Override llm.model.")
    parser.add_argument("--llm-base-url", default="", help="Override llm.base_url.")
    parser.add_argument("--llm-api-key", default="", help="Override llm.api_key.")
    parser.add_argument(
        "--evidence",
        action="append",
        help="Evidence path: label=path or label=path::kind. Repeatable.",
    )
    args = parser.parse_args(argv)
    try:
        run(build_config(args))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"AutoReport failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
