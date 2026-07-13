from __future__ import annotations

import json
from pathlib import Path

import yaml

from autoreport.config import AutoReportConfig, write_config_yaml
from service_api import EvidencePathModel, StartReportRequest, _build_snapshot, _write_generated_config


def test_snapshot_uses_resolved_yaml_runtime_settings(tmp_path: Path) -> None:
    cfg = AutoReportConfig(task_name="demo", output_dir=str(tmp_path))
    cfg.runtime.current_state_filename = "state.custom.json"
    cfg.runtime.event_stream_filename = "events.custom.jsonl"
    cfg.runtime.snapshot_event_limit = 1
    cfg.runtime.snapshot_text_tail_chars = 4
    cfg.generation.report_json_filename = "result.custom.json"
    cfg.generation.report_markdown_filename = "result.custom.md"
    write_config_yaml(cfg, tmp_path / "resolved_config.yaml")

    (tmp_path / "state.custom.json").write_text(
        json.dumps({"status": "running"}),
        encoding="utf-8",
    )
    (tmp_path / "events.custom.jsonl").write_text(
        '{"seq": 1}\n{"seq": 2}\n',
        encoding="utf-8",
    )
    (tmp_path / "result.custom.json").write_text(
        json.dumps({"ok": True}),
        encoding="utf-8",
    )
    (tmp_path / "result.custom.md").write_text("report", encoding="utf-8")
    (tmp_path / "_service_stdout.log").write_text("abcdefgh", encoding="utf-8")

    snapshot = _build_snapshot(str(tmp_path))

    assert snapshot["current_state"]["status"] == "running"
    assert snapshot["events"] == [{"seq": 2}]
    assert snapshot["report"] == {"ok": True}
    assert snapshot["report_markdown"] == "report"
    assert snapshot["stdout"] == "efgh"


def test_generated_temporary_config_redacts_request_api_key(tmp_path: Path) -> None:
    request = StartReportRequest(
        task_name="demo",
        output_dir=str(tmp_path),
        evidence_paths=[EvidencePathModel(label="demo", path=str(tmp_path))],
        config={
            "llm": {
                "enabled": True,
                "model": "demo-model",
                "base_url": "https://example.invalid",
                "api_key": "ui-key",
            }
        },
    )

    path = _write_generated_config(request)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert raw["llm"]["api_key"] is None
