from __future__ import annotations

from pathlib import Path

from autoreport.collector import collect_evidence
from autoreport.config import AutoReportConfig, EvidencePath
from autoreport.context import SourceWorkspace
from autoreport.events import ReportEventWriter


def test_long_source_keeps_head_tail_and_can_retrieve_middle(tmp_path: Path) -> None:
    best = tmp_path / "automl" / "best_solution"
    best.mkdir(parents=True)
    lines = ["import json"]
    lines.extend(f"VALUE_{index} = {index}" for index in range(1, 500))
    lines.extend(["def predict(data):", "    return data"])
    solution_path = best / "solution.py"
    solution_path.write_text("\n".join(lines), encoding="utf-8")
    (best / "metric.txt").write_text("Metric: 1\nMaximize: True\n", encoding="utf-8")

    cfg = AutoReportConfig(
        task_name="demo",
        output_dir=str(tmp_path / "report"),
        evidence_paths=[EvidencePath(label="automl", path=str(tmp_path / "automl"))],
        analysis={"initial_source_chars": 1200, "retrieval_chunk_lines": 30},
    )
    bundle = collect_evidence(cfg, ReportEventWriter(tmp_path / "events", run_id="test"))
    workspace = SourceWorkspace(cfg, bundle)
    source = next(item for item in workspace.documents if item.path == solution_path.resolve())

    initial = workspace.initial_sources(1800)
    assert "OMITTED" in initial
    assert "function predict" in initial

    retrieved = workspace.retrieve(
        [{"source_id": source.source_id, "start_line": 245, "end_line": 255}]
    )
    assert len(retrieved) == 1
    assert "VALUE_250" in retrieved[0]["content"]
    assert workspace.retrieve([{"source_id": "not-allowed", "start_line": 1, "end_line": 10}]) == []
