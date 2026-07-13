from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .collector import EvidenceBundle, EvidenceItem
from .config import AutoReportConfig, dump_config
from .events import ReportEventWriter


def generate_report(
    cfg: AutoReportConfig,
    bundle: EvidenceBundle,
    events: ReportEventWriter,
) -> dict[str, Any]:
    events.log("autoreport.generator", "ACTIVATED", task_name=cfg.task_name)
    settings = _validate_llm_config(cfg)
    briefing = _build_llm_briefing(cfg, bundle)
    article_md = _generate_article_with_llm(cfg, settings, briefing, events)
    article_md = _normalize_article_markdown(cfg, article_md)
    sections = _sections_from_markdown(article_md)

    payload = {
        "schema_version": "autoreport.report.v3",
        "task_name": cfg.task_name,
        "report_title": cfg.report_title or f"{cfg.task_name} 方案交付报告",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "config": dump_config(cfg),
        "summary": {
            "evidence_paths": len(bundle.roots),
            "evidence_items": len(bundle.items),
            "warnings": len(bundle.warnings),
            "kind_counts": bundle.derived.get("kind_counts", {}),
            "solution_evidence": _solution_evidence_summary_for_payload(bundle),
            "llm_model": settings["model"],
            "llm_base_url": settings["base_url"],
        },
        "sections": sections,
        "article_markdown": article_md,
        "evidence_index": [asdict(item) for item in bundle.items],
        "warnings": bundle.warnings,
    }

    out_dir = Path(cfg.output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if cfg.generation.write_report_json:
        json_path = out_dir / cfg.generation.report_json_filename
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        events.log("autoreport.generator", "GENERATED_FILE", file=json_path.name)
    if cfg.generation.write_report_markdown:
        markdown_path = out_dir / cfg.generation.report_markdown_filename
        markdown_path.write_text(article_md, encoding="utf-8")
        events.log("autoreport.generator", "GENERATED_FILE", file=markdown_path.name)

    events.log(
        "autoreport.generator",
        "COMPLETED",
        sections=len(sections),
        llm_model=settings["model"],
    )
    return payload


def render_markdown(report: dict[str, Any]) -> str:
    article = str(report.get("article_markdown") or "").strip()
    if article:
        return article + "\n"
    title = str(report.get("report_title") or "AutoDecision 方案交付报告")
    lines = [f"# {title}", ""]
    for section in report.get("sections", []) or []:
        lines.extend(
            [
                f"## {section.get('title', '')}",
                "",
                str(section.get("content", "")).strip(),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _validate_llm_config(cfg: AutoReportConfig) -> dict[str, Any]:
    llm = cfg.llm
    if not llm.enabled:
        raise ValueError("AutoReport requires llm.enabled=true.")
    model = str(llm.model or "").strip()
    base_url = str(llm.base_url or "").strip()
    api_key = str(llm.api_key or os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    if not model:
        raise ValueError("AutoReport llm.model is required.")
    if not base_url:
        raise ValueError("AutoReport llm.base_url is required.")
    if not api_key:
        raise ValueError(
            "AutoReport llm.api_key is missing and DEEPSEEK_API_KEY is not set."
        )
    return {
        "model": model,
        "base_url": _normalize_base_url(model, base_url),
        "api_key": api_key,
        "timeout": max(1, int(llm.request_timeout_seconds)),
        "max_tokens": llm.max_tokens,
        "temperature": float(llm.temperature),
        "max_retries": max(1, int(llm.max_retries)),
        "retry_base_sleep_seconds": max(0.0, float(llm.retry_base_sleep_seconds)),
        "retry_max_sleep_seconds": max(0.0, float(llm.retry_max_sleep_seconds)),
        "enable_thinking": llm.enable_thinking,
        "reasoning_effort": llm.reasoning_effort,
    }


def _normalize_base_url(model: str, base_url: str) -> str:
    base = base_url.rstrip("/")
    if model.strip().lower().startswith("deepseek") and base in {
        "https://api.deepseek.com",
        "https://api.deepseek.com/v1",
    }:
        return "https://api.deepseek.com/beta"
    return base


def _chat_completions_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def _generate_article_with_llm(
    cfg: AutoReportConfig,
    settings: dict[str, Any],
    briefing: str,
    events: ReportEventWriter,
) -> str:
    language = "中文" if cfg.language.lower().startswith("zh") else "English"
    system_prompt = """
你是 AutoDecision 的方案交付报告撰写专家。报告的主语必须是最终模型、算法或求解器，而不是 AutoML 搜索流程。

硬性要求：
- 详细说明最终方案的数据读取、预处理、特征/状态/动作、模型或求解算法、约束处理、评分与输出构造。
- 说明如何复用代码：输入目录、运行命令、predict()/solver 接口、模型或求解器 artifact、输出路径与格式。
- 使用真实证据比较其它候选方案；没有证据时明确写“现有证据未显示”，不得编造。
- 给出指标、产物、运行限制、已知风险和下一步改进。
- 不大段粘贴源代码、日志或 JSON，只引用关键数字、路径和短证据。
""".strip()
    user_prompt = f"""
请为任务 {cfg.task_name} 写一份面向 {cfg.audience} 读者的方案交付报告，使用{language}，输出完整 Markdown。

建议章节：
1. 摘要与交付结论
2. 问题与验收口径
3. 最终方案方法设计
4. 代码复用与部署方式
5. 验证结果与交付物
6. 与其它候选方案的比较
7. 风险、限制与下一步改进
8. 交付检查清单

以下是压缩后的证据简报：

{briefing}
""".strip()

    payload: dict[str, Any] = {
        "model": settings["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": settings["temperature"],
        "stream": False,
    }
    if settings["max_tokens"] not in {None, 0}:
        payload["max_tokens"] = int(settings["max_tokens"])
    if settings["enable_thinking"] is not None:
        payload["thinking"] = {
            "type": "enabled" if bool(settings["enable_thinking"]) else "disabled"
        }
    if settings["reasoning_effort"]:
        payload["reasoning_effort"] = str(settings["reasoning_effort"])

    events.log(
        "autoreport.generator",
        "LLM_REQUEST",
        model=settings["model"],
        base_url=settings["base_url"],
        briefing_chars=len(briefing),
    )
    raw = _post_json_with_retry(
        _chat_completions_url(settings["base_url"]),
        payload,
        api_key=settings["api_key"],
        timeout=settings["timeout"],
        max_attempts=settings["max_retries"],
        retry_base_sleep_seconds=settings["retry_base_sleep_seconds"],
        retry_max_sleep_seconds=settings["retry_max_sleep_seconds"],
        events=events,
    )
    content = _extract_chat_content(raw)
    if not content.strip():
        raise RuntimeError("AutoReport LLM returned empty content.")
    events.log("autoreport.generator", "LLM_COMPLETED", chars=len(content))
    return content


def _post_json_with_retry(
    url: str,
    payload: dict[str, Any],
    *,
    api_key: str,
    timeout: int,
    max_attempts: int,
    retry_base_sleep_seconds: float,
    retry_max_sleep_seconds: float,
    events: ReportEventWriter,
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        request = urllib.request.Request(
            url=url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                text = response.read().decode("utf-8", errors="replace")
                return json.loads(text) if text else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            last_error = RuntimeError(f"HTTP {exc.code}: {detail[:500]}")
            retryable = exc.code in {429, 500, 502, 503, 504}
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            retryable = _is_retryable_error(exc)

        events.log(
            "autoreport.generator",
            "LLM_RECONNECTING",
            attempt=attempt,
            max_attempts=max_attempts,
            retryable=retryable,
            error=str(last_error)[:240],
        )
        if not retryable or attempt >= max_attempts:
            raise RuntimeError(_format_llm_network_error(last_error, url))
        time.sleep(
            min(
                retry_max_sleep_seconds,
                retry_base_sleep_seconds * attempt,
            )
        )
    raise RuntimeError(_format_llm_network_error(last_error, url))


def _is_retryable_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        token in message
        for token in (
            "timeout",
            "timed out",
            "connection reset",
            "connection aborted",
            "connection refused",
            "temporary failure",
            "temporarily unavailable",
            "bad gateway",
            "rate limit",
            "too many requests",
            "getaddrinfo",
            "name resolution",
            "name or service not known",
            "10061",
            "11001",
            "502",
            "503",
            "504",
        )
    )


def _format_llm_network_error(exc: Exception | None, url: str) -> str:
    message = str(exc or "unknown error")
    if "getaddrinfo" in message.lower() or "name resolution" in message.lower():
        return (
            "AutoReport LLM request failed because DNS resolution failed. "
            f"Check llm.base_url, DNS, proxy/VPN, and firewall. url={url}; error={message}"
        )
    return f"AutoReport LLM request failed: {message}"


def _extract_chat_content(raw: dict[str, Any]) -> str:
    choices = raw.get("choices") or []
    if not choices:
        return ""
    first = choices[0] or {}
    message = first.get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
    if content is not None:
        return str(content)
    return str(first.get("text") or "")


def _build_llm_briefing(cfg: AutoReportConfig, bundle: EvidenceBundle) -> str:
    generation = cfg.generation
    parts: list[str] = []

    def add(title: str, value: Any, limit: int) -> None:
        text = str(value or "").strip()
        if text:
            parts.append(f"## {title}\n{_clip(text, limit)}")

    roots = "\n".join(
        f"- {root.get('label')} ({root.get('kind')}): "
        f"exists={root.get('exists')} path={root.get('path')}"
        for root in bundle.roots
    )
    add("证据入口", roots, generation.evidence_root_chars)
    if bundle.warnings:
        add(
            "证据告警",
            "\n".join(f"- {warning}" for warning in bundle.warnings),
            generation.evidence_warning_chars,
        )

    solution_evidence = bundle.derived.get("solution_evidence") or {}
    add(
        "方案证据总包",
        json.dumps(
            _solution_evidence_for_prompt(solution_evidence, cfg),
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        generation.solution_evidence_chars,
    )
    add(
        "任务定义 description.md",
        bundle.derived.get("description", ""),
        generation.description_chars,
    )
    add(
        "数据认知 data_description.md",
        bundle.derived.get("data_description", ""),
        generation.data_description_chars,
    )
    add(
        "样例提交预览",
        json.dumps(
            bundle.derived.get("sample_submission_preview") or [],
            ensure_ascii=False,
            indent=2,
        ),
        generation.sample_submission_chars,
    )

    context_lines: list[str] = []
    for item in _select_context_items(bundle, cfg):
        context_lines.append(
            f"### {Path(item.path).name}\npath: {item.path}\nkind: {item.kind}"
        )
        if item.json_summary:
            detail = json.dumps(
                item.json_summary,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        elif item.table_preview:
            detail = json.dumps(
                item.table_preview,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        else:
            detail = item.text_excerpt
        context_lines.append(_clip(detail, generation.context_item_chars))
    add(
        "关键证据摘录",
        "\n\n".join(context_lines),
        generation.context_block_chars,
    )

    evidence_index = "\n".join(
        f"- [{item.kind}] {item.path}"
        for item in bundle.items[: generation.evidence_index_limit]
    )
    add("证据索引", evidence_index, generation.evidence_index_chars)
    return _clip("\n\n".join(parts), generation.max_prompt_chars)


def _select_context_items(
    bundle: EvidenceBundle,
    cfg: AutoReportConfig,
) -> list[EvidenceItem]:
    priority_names = {
        "description.md",
        "data_description.md",
        "automl_context.md",
        "autorealize_context.md",
        "metrics.json",
        "model_artifacts_manifest.md",
        "node_summary_compact.json",
        "journal.json",
        "filtered_journal.json",
        "metric.txt",
        "best_solution.py",
        "solution.py",
        "submission.csv",
        "assignments.csv",
        "unassigned_orders.csv",
    }
    scored: list[tuple[int, str, EvidenceItem]] = []
    for item in bundle.items:
        name = Path(item.path).name.lower()
        score = 100
        if name in priority_names:
            score -= 60
        if item.kind == "solution":
            score -= 35
        elif item.kind == "runtime_trace":
            score -= 15
        elif item.kind == "data_cognition":
            score -= 20
        elif item.kind == "task_definition":
            score -= 25
        normalized_path = item.path.lower().replace("\\", "/")
        if any(part in normalized_path for part in ("best_solution", "top_solution", "/submission/")):
            score -= 20
        scored.append((score, normalized_path, item))
    return [
        item
        for _, _, item in sorted(scored, key=lambda row: (row[0], row[1]))[
            : cfg.generation.selected_context_item_limit
        ]
    ]


def _normalize_article_markdown(cfg: AutoReportConfig, article: str) -> str:
    text = article.strip()
    text = re.sub(r"^\x60\x60\x60(?:markdown|md)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\x60\x60\x60$", "", text)
    if not text.startswith("#"):
        title = cfg.report_title or f"{cfg.task_name} 方案交付报告"
        text = f"# {title}\n\n{text}"
    return text.strip() + "\n"


def _sections_from_markdown(markdown: str) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    current_title = "导言"
    current_lines: list[str] = []
    heading_seen = False

    def flush() -> None:
        nonlocal current_lines
        content = "\n".join(current_lines).strip()
        if content or current_title != "导言":
            sections.append(
                {
                    "id": f"section_{len(sections) + 1}",
                    "title": current_title,
                    "content": content,
                    "evidence": [],
                }
            )
        current_lines = []

    for line in markdown.splitlines():
        if line.startswith("# "):
            current_lines.append(line)
            continue
        if line.startswith("## "):
            if heading_seen or current_lines:
                flush()
            heading_seen = True
            current_title = line.lstrip("#").strip()
            continue
        current_lines.append(line)
    flush()
    return sections


def _solution_evidence_for_prompt(
    evidence: Any,
    cfg: AutoReportConfig,
) -> dict[str, Any]:
    if not isinstance(evidence, dict):
        return {}
    best = evidence.get("best_solution") if isinstance(evidence.get("best_solution"), dict) else {}
    candidate = (
        evidence.get("candidate_comparison")
        if isinstance(evidence.get("candidate_comparison"), dict)
        else {}
    )
    reusable = (
        evidence.get("reusable_code_interface")
        if isinstance(evidence.get("reusable_code_interface"), dict)
        else {}
    )
    return {
        "best_solution": {
            "metric": best.get("metric"),
            "metric_text": str(best.get("metric_text") or "")[
                : cfg.comparison.best_metric_excerpt_chars
            ],
            "metric_path": best.get("metric_path"),
            "node_id": best.get("node_id"),
            "solution_path": best.get("solution_path"),
            "code_functions": best.get("code_functions"),
            "code_excerpt_head": str(best.get("code_excerpt") or "")[
                : cfg.comparison.best_code_excerpt_chars
            ],
            "model_artifacts_manifest": str(
                best.get("model_artifacts_manifest") or ""
            )[: cfg.comparison.model_manifest_excerpt_chars],
            "model_artifacts_manifest_path": best.get(
                "model_artifacts_manifest_path"
            ),
        },
        "reusable_code_interface": reusable,
        "candidate_comparison": {
            "node_count": candidate.get("node_count"),
            "maximize": candidate.get("maximize"),
            "method_signals": candidate.get("method_signals"),
            "successful_metric_nodes": candidate.get(
                "successful_metric_nodes", []
            )[: cfg.comparison.successful_node_limit],
            "failed_nodes": candidate.get("failed_nodes", [])[
                : cfg.comparison.failed_node_limit
            ],
            "failure_patterns": candidate.get("failure_patterns", [])[
                : cfg.comparison.failure_pattern_limit
            ],
        },
        "top_solutions": (evidence.get("top_solutions") or [])[
            : cfg.comparison.top_solution_limit
        ],
        "delivery_artifacts": (evidence.get("delivery_artifacts") or [])[
            : cfg.comparison.delivery_artifact_limit
        ],
        "available_evidence_files": evidence.get("available_evidence_files") or {},
    }


def _solution_evidence_summary_for_payload(
    bundle: EvidenceBundle,
) -> dict[str, Any]:
    evidence = (
        bundle.derived.get("solution_evidence")
        if isinstance(bundle.derived, dict)
        else {}
    )
    if not isinstance(evidence, dict):
        return {}
    candidate = (
        evidence.get("candidate_comparison")
        if isinstance(evidence.get("candidate_comparison"), dict)
        else {}
    )
    best = (
        evidence.get("best_solution")
        if isinstance(evidence.get("best_solution"), dict)
        else {}
    )
    metric = best.get("metric")
    return {
        "best_metric": metric.get("metric") if isinstance(metric, dict) else None,
        "best_solution_path": best.get("solution_path"),
        "top_solution_count": len(evidence.get("top_solutions") or []),
        "candidate_node_count": candidate.get("node_count"),
        "successful_metric_node_count": len(
            candidate.get("successful_metric_nodes") or []
        ),
        "failure_pattern_count": len(candidate.get("failure_patterns") or []),
        "delivery_artifact_count": len(evidence.get("delivery_artifacts") or []),
        "has_predict": (
            evidence.get("reusable_code_interface") or {}
        ).get("has_predict")
        if isinstance(evidence.get("reusable_code_interface"), dict)
        else None,
    }


def _clip(text: Any, limit: int) -> str:
    value = str(text or "").strip()
    limit = max(1, int(limit))
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "\n\n...(truncated / 已截断)"
