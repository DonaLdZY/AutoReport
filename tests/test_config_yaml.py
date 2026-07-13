from __future__ import annotations

import json
from pathlib import Path

import yaml

from autoreport.config import (
    AutoReportConfig,
    LLMConfig,
    config_schema,
    load_config,
    write_config_yaml,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_commented_default_yaml_loads(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-test-key")
    cfg = load_config(REPO_ROOT / "config" / "config.yaml")

    assert cfg.task_name == "demo_task"
    assert cfg.llm.api_key == "env-test-key"
    assert cfg.collection.max_files_per_path == 700
    assert cfg.generation.report_markdown_filename == "report.md"
    assert cfg.runtime.snapshot_event_limit == 500
    assert cfg.runtime.service_stop_wait_seconds == 15.0
    assert "证据采集" in config_schema()["description_zh"]
    assert config_schema()["example"]["llm"]["api_key"] is None


def test_yaml_round_trip_and_legacy_inputs(tmp_path: Path) -> None:
    cfg = AutoReportConfig(
        task_name="demo",
        output_dir=str(tmp_path / "report"),
        llm={"model": "demo-model", "max_prompt_chars": 12345},
    )
    assert isinstance(cfg.llm, LLMConfig)
    assert cfg.generation.max_prompt_chars == 12345

    yaml_path = tmp_path / "config.yaml"
    cfg.llm.api_key = "test-only"
    write_config_yaml(cfg, yaml_path)
    loaded = load_config(yaml_path)
    assert loaded.llm.model == "demo-model"
    written = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    assert written["task_name"] == "demo"
    assert written["llm"]["api_key"] is None

    json_path = tmp_path / "legacy.json"
    json_path.write_text(
        json.dumps(
            {
                "task_name": "legacy",
                "output_dir": str(tmp_path / "legacy-report"),
                "use_llm": True,
                "max_files_per_path": 12,
                "llm": {"model_name": "legacy-model", "baseUrl": "https://example.invalid"},
            }
        ),
        encoding="utf-8",
    )
    legacy = load_config(json_path)
    assert legacy.collection.max_files_per_path == 12
    assert legacy.llm.model == "legacy-model"


def test_config_api_key_has_priority_over_environment(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "environment-key")
    path = tmp_path / "config.yaml"
    path.write_text(
        "task_name: demo\noutput_dir: report\nllm:\n  api_key: config-key\n",
        encoding="utf-8",
    )

    assert load_config(path).llm.api_key == "config-key"
