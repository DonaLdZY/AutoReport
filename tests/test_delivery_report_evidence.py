import json
from pathlib import Path

from autoreport.collector import collect_evidence
from autoreport.config import AutoReportConfig, EvidencePath
from autoreport.events import ReportEventWriter
from autoreport.generator import _build_llm_briefing


def test_collects_solution_evidence_for_delivery_report(tmp_path: Path) -> None:
    automl = tmp_path / "automl"
    best = automl / "workspaces" / "run_001" / "best_solution"
    best.mkdir(parents=True)
    (best / "metric.txt").write_text(
        "Metric: 12.5\nMaximize: False\nBranch ID: 2\nStage: improve\nExecution Time(s): 3.2\n",
        encoding="utf-8",
    )
    (best / "node_id.txt").write_text("node_best", encoding="utf-8")
    (best / "solution.py").write_text(
        """
def load_problem_data(input_dir):
    return {"input_dir": input_dir}

def validate_solution(solution):
    return True

def score_solution(solution):
    return 12.5

def predict(model_path=None, data=None):
    return {"ok": True}

def main():
    print("Final Validation Score: 12.5")
""".strip(),
        encoding="utf-8",
    )

    top1 = automl / "workspaces" / "run_001" / "top_solution" / "top1"
    top1.mkdir(parents=True)
    (top1 / "metric.txt").write_text("Metric: 12.5\nMaximize: False\n", encoding="utf-8")
    (top1 / "solution.py").write_text("def predict(model_path=None, data=None):\n    return data\n", encoding="utf-8")

    submission = automl / "workspaces" / "run_001" / "submission"
    submission.mkdir(parents=True)
    (submission / "metrics.json").write_text(
        json.dumps({"score": 12.5, "unassigned_units": 0}, ensure_ascii=False),
        encoding="utf-8",
    )
    (submission / "submission.csv").write_text("id,value\nA,1\n", encoding="utf-8")

    logs = automl / "logs" / "run_001"
    logs.mkdir(parents=True)
    (logs / "node_summary_compact.json").write_text(
        json.dumps(
            [
                {
                    "id": "root",
                    "stage": "root",
                    "step": 0,
                    "metric": None,
                    "buggy": None,
                },
                {
                    "id": "node_bad",
                    "stage": "draft",
                    "step": 1,
                    "metric": 99.0,
                    "buggy": False,
                    "valid": False,
                    "search_eligible": True,
                    "delivery_ready": False,
                    "delivery_certified": False,
                    "method_mode": "non_rl_solver",
                    "plan": "simple greedy",
                    "analysis": "Too many unassigned units.",
                    "has_greedy": True,
                    "has_rl_env": False,
                    "has_decision_summary": True,
                },
                {
                    "id": "node_best",
                    "stage": "improve",
                    "step": 2,
                    "metric": 12.5,
                    "buggy": False,
                    "valid": True,
                    "search_eligible": True,
                    "delivery_ready": True,
                    "delivery_certified": False,
                    "certification_source": "candidate_reported_score",
                    "method_mode": "non_rl_solver",
                    "plan": "improved solver",
                    "analysis": "All constraints satisfied.",
                    "has_greedy": True,
                    "has_rl_env": False,
                    "has_decision_summary": True,
                },
                {
                    "id": "node_fail",
                    "stage": "debug",
                    "step": 3,
                    "metric": None,
                    "buggy": True,
                    "exc_type": "KeyError",
                    "exc_msg": "missing column",
                    "analysis": "schema mismatch",
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    cfg = AutoReportConfig(
        task_name="demo",
        output_dir=str(tmp_path / "report"),
        evidence_paths=[EvidencePath(label="automl", path=str(automl), kind="automl")],
    )
    bundle = collect_evidence(cfg, ReportEventWriter(tmp_path / "events", run_id="test"))
    evidence = bundle.derived["solution_evidence"]

    assert evidence["best_solution"]["metric"]["metric"] == 12.5
    assert evidence["best_solution"]["node_id"] == "node_best"
    assert evidence["reusable_code_interface"]["has_predict"] is True
    assert evidence["candidate_comparison"]["node_count"] == 4
    assert evidence["candidate_comparison"]["successful_metric_nodes"][0]["id"] == "node_best"
    assert evidence["candidate_comparison"]["search_candidate_nodes"][0]["id"] == "node_best"
    assert {n["id"] for n in evidence["candidate_comparison"]["search_candidate_nodes"]} == {
        "node_best",
    }
    assert evidence["candidate_comparison"]["failure_patterns"][0]["type"] == "KeyError"
    assert any(item["name"] == "metrics.json" for item in evidence["delivery_artifacts"])


def test_interrupted_checkpoint_candidates_are_available_as_report_evidence(tmp_path: Path) -> None:
    automl = tmp_path / "automl"
    log_dir = automl / "logs" / "run_001"
    candidate = automl / "workspaces" / "run_001" / "checkpoint_candidates" / "top1"
    log_dir.mkdir(parents=True)
    candidate.mkdir(parents=True)
    (log_dir / "checkpoint_manifest.json").write_text(
        json.dumps(
            {
                "status": "interrupted_resumable",
                "resumable": True,
                "top_solutions": [],
                "provisional_top": [{"node_id": "partial-1", "metric": 42.0}],
            }
        ),
        encoding="utf-8",
    )
    (candidate / "metric.txt").write_text(
        "Metric: 42\nMaximize: False\nDelivery Ready: False\n",
        encoding="utf-8",
    )
    (candidate / "node_id.txt").write_text("partial-1", encoding="utf-8")
    (candidate / "solution.py").write_text(
        "def predict(model_path=None, data=None):\n    return data\n",
        encoding="utf-8",
    )

    cfg = AutoReportConfig(
        task_name="interrupted",
        output_dir=str(tmp_path / "report"),
        evidence_paths=[EvidencePath(label="automl", path=str(automl), kind="automl")],
    )
    bundle = collect_evidence(cfg, ReportEventWriter(tmp_path / "events", run_id="test"))
    evidence_files = bundle.derived["solution_evidence"]["available_evidence_files"]
    solution_evidence = bundle.derived["solution_evidence"]

    assert evidence_files["checkpoint_manifests"] == [str(log_dir / "checkpoint_manifest.json")]
    assert any("checkpoint_candidates" in path for path in evidence_files["solution_files"])
    assert solution_evidence["checkpoint_candidates"][0]["node_id"] == "partial-1"
    assert solution_evidence["best_solution"]["node_id"] == ""


def test_briefing_prioritizes_solution_delivery_evidence(tmp_path: Path) -> None:
    automl = tmp_path / "automl"
    best = automl / "workspaces" / "run_001" / "best_solution"
    best.mkdir(parents=True)
    (best / "metric.txt").write_text("Metric: 1\nMaximize: True\n", encoding="utf-8")
    (best / "solution.py").write_text("def predict(model_path=None, data=None):\n    return data\n", encoding="utf-8")
    logs = automl / "logs" / "run_001"
    logs.mkdir(parents=True)
    (logs / "node_summary_compact.json").write_text(
        json.dumps([{"id": "node_best", "stage": "draft", "metric": 1, "buggy": False}], ensure_ascii=False),
        encoding="utf-8",
    )
    cfg = AutoReportConfig(
        task_name="demo",
        output_dir=str(tmp_path / "report"),
        evidence_paths=[EvidencePath(label="automl", path=str(automl), kind="automl")],
        llm={"max_prompt_chars": 20000},
    )
    bundle = collect_evidence(cfg, ReportEventWriter(tmp_path / "events", run_id="test"))
    briefing = _build_llm_briefing(cfg, bundle)

    assert "candidate_comparison" in briefing
    assert "reusable_code_interface" in briefing
    assert "AutoML 如何搜索" not in briefing
