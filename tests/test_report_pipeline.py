from __future__ import annotations

import json
from pathlib import Path

from autoreport.collector import collect_evidence
from autoreport.config import AutoReportConfig, EvidencePath
from autoreport.events import ReportEventWriter
from autoreport.generator import generate_report


def test_report_pipeline_uses_stable_system_and_writes_clean_report(tmp_path: Path, monkeypatch) -> None:
    evidence_root = tmp_path / "evidence"
    best = evidence_root / "best_solution"
    best.mkdir(parents=True)
    (evidence_root / "description.md").write_text("预测设备故障。", encoding="utf-8")
    (best / "metric.txt").write_text("Metric: 0.91\nMaximize: True\n", encoding="utf-8")
    (best / "node_id.txt").write_text("node-1", encoding="utf-8")
    (best / "solution.py").write_text(
        "def predict(data):\n    return [0 for _ in data]\n",
        encoding="utf-8",
    )
    log_dir = evidence_root / "logs"
    log_dir.mkdir()
    (log_dir / "node_summary_compact.json").write_text(
        json.dumps(
            [
                {
                    "id": "node-1",
                    "metric": 0.91,
                    "maximize": True,
                    "buggy": False,
                    "valid": True,
                    "search_eligible": True,
                    "review_verdict": "accept",
                }
            ]
        ),
        encoding="utf-8",
    )

    responses = [
        {
            "problem": {"objective": "预测设备故障"},
            "method_cards": [{"node_id": "node-1", "method_name": "分类模型"}],
            "best_method": {"node_id": "node-1"},
            "comparison": [],
            "reuse": {"direct_use": "调用 predict"},
            "retrieve_requests": [],
            "analysis_complete": True,
        },
        "# 设备故障预测报告\n\n## 摘要与最终方案\n\n最佳方法使用分类模型。",
        {
            "status": "pass",
            "issues": [],
            "revised_markdown": "# 设备故障预测报告\n\n## 摘要与最终方案\n\n最佳方法使用分类模型，可调用 `predict`。",
        },
    ]
    requests: list[dict] = []

    def fake_post(_url, payload, **_kwargs):
        requests.append(payload)
        response = responses.pop(0)
        content = response if isinstance(response, str) else json.dumps(response, ensure_ascii=False)
        return {
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

    monkeypatch.setattr("autoreport.generator._post_json_with_retry", fake_post)
    cfg = AutoReportConfig(
        task_name="demo",
        output_dir=str(tmp_path / "report"),
        language="zh-CN",
        evidence_paths=[EvidencePath(label="run", path=str(evidence_root))],
        llm={
            "model": "test-model",
            "base_url": "https://example.invalid",
            "api_key": "test-key",
        },
    )
    events = ReportEventWriter(tmp_path / "events", run_id="test", print_events_to_console=False)
    bundle = collect_evidence(cfg, events)
    report = generate_report(cfg, bundle, events)

    assert len(requests) == 3
    assert all(request["max_tokens"] == 32768 for request in requests)
    systems = [request["messages"][0]["content"] for request in requests]
    assert len(set(systems)) == 1
    assert report["article_markdown"].startswith("# 设备故障预测报告")
    assert "source_id" not in report["article_markdown"]
    assert (tmp_path / "report" / "report.md").exists()
    trace = json.loads((tmp_path / "report" / "report_trace.json").read_text(encoding="utf-8"))
    assert trace["analysis"]["best_method"]["node_id"] == "node-1"
    assert len(trace["llm_usage"]) == 3
