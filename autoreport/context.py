from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .collector import EvidenceBundle, EvidenceItem
from .config import AutoReportConfig


SOURCE_NAMES = {
    "description.md",
    "data_description.md",
    "automl_context.md",
    "autorealize_context.md",
    "solution.py",
    "best_solution.py",
    "metric.txt",
    "node_id.txt",
    "model_artifacts_manifest.md",
    "model_path.txt",
    "sample_submission.csv",
    "submission.csv",
}


@dataclass(frozen=True)
class SourceDocument:
    source_id: str
    path: Path
    display_path: str
    kind: str
    size: int
    line_count: int
    outline: tuple[str, ...]

    def metadata(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "path": self.display_path,
            "kind": self.kind,
            "size": self.size,
            "line_count": self.line_count,
            "outline": list(self.outline),
        }


class SourceWorkspace:
    """Read-only, allowlisted source retrieval for report analysis."""

    def __init__(self, cfg: AutoReportConfig, bundle: EvidenceBundle) -> None:
        self.cfg = cfg
        self.bundle = bundle
        self.documents = self._build_documents()
        self.by_id = {document.source_id: document for document in self.documents}
        self.retrieval_log: list[dict[str, Any]] = []

    def _build_documents(self) -> list[SourceDocument]:
        unique: dict[str, EvidenceItem] = {}
        for item in self.bundle.items:
            path = Path(item.path).expanduser().resolve()
            if not path.exists() or not path.is_file():
                continue
            normalized = str(path).lower()
            existing = unique.get(normalized)
            if existing is None or _source_priority(item) < _source_priority(existing):
                unique[normalized] = item

        selected = sorted(unique.values(), key=lambda item: (_source_priority(item), item.path.lower()))
        limit = max(16, self.cfg.analysis.comparison_candidate_limit * 4 + 12)
        documents: list[SourceDocument] = []
        for item in selected:
            path = Path(item.path).expanduser().resolve()
            name = path.name.lower()
            normalized_path = str(path).lower().replace("\\", "/")
            if name not in SOURCE_NAMES and not any(
                part in normalized_path
                for part in ("/best_solution/", "/top_solution/", "/checkpoint_candidates/")
            ):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            source_id = "src_" + hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:12]
            documents.append(
                SourceDocument(
                    source_id=source_id,
                    path=path,
                    display_path=_display_path(item, path),
                    kind=item.kind,
                    size=path.stat().st_size,
                    line_count=max(1, len(text.splitlines())),
                    outline=tuple(_python_outline(text) if path.suffix.lower() == ".py" else ()),
                )
            )
            if len(documents) >= limit:
                break
        return documents

    def catalog(self) -> list[dict[str, Any]]:
        return [document.metadata() for document in self.documents]

    def initial_sources(self, max_chars: int) -> str:
        if not self.documents or max_chars <= 0:
            return ""
        blocks: list[str] = []
        remaining = max_chars
        per_source = max(1200, min(self.cfg.analysis.initial_source_chars, max_chars // len(self.documents)))
        for document in self.documents:
            if remaining < 400:
                break
            budget = min(per_source, remaining)
            block = self._source_block(document, budget)
            blocks.append(block)
            remaining -= len(block)
        return "\n\n".join(blocks)

    def retrieve(self, requests: Any) -> list[dict[str, Any]]:
        if not isinstance(requests, list):
            return []
        results: list[dict[str, Any]] = []
        request_limit = self.cfg.analysis.max_retrieval_requests_per_round
        max_lines = self.cfg.analysis.retrieval_chunk_lines
        for raw in requests[:request_limit]:
            if not isinstance(raw, dict):
                continue
            source_id = str(raw.get("source_id") or "").strip()
            document = self.by_id.get(source_id)
            if document is None:
                continue
            try:
                start_line = max(1, int(raw.get("start_line") or 1))
                end_line = max(start_line, int(raw.get("end_line") or start_line + max_lines - 1))
            except (TypeError, ValueError):
                continue
            end_line = min(document.line_count, end_line, start_line + max_lines - 1)
            lines = document.path.read_text(encoding="utf-8", errors="replace").splitlines()
            content = "\n".join(lines[start_line - 1 : end_line])
            result = {
                "source_id": source_id,
                "path": document.display_path,
                "start_line": start_line,
                "end_line": end_line,
                "content": content,
            }
            results.append(result)
            self.retrieval_log.append(
                {
                    key: value
                    for key, value in result.items()
                    if key != "content"
                }
            )
        return results

    def _source_block(self, document: SourceDocument, max_chars: int) -> str:
        text = document.path.read_text(encoding="utf-8", errors="replace")
        header = (
            f"<source id=\"{document.source_id}\" path=\"{document.display_path}\" "
            f"kind=\"{document.kind}\" lines=\"{document.line_count}\">"
        )
        outline = "\n".join(document.outline)
        body_budget = max(200, max_chars - len(header) - len(outline) - 80)
        body = _head_tail(text, body_budget, document.line_count)
        outline_block = f"\nOUTLINE:\n{outline}" if outline else ""
        return f"{header}{outline_block}\nCONTENT:\n{body}\n</source>"


def estimate_tokens(text: str) -> int:
    ascii_chars = sum(1 for char in text if ord(char) < 128)
    non_ascii_chars = len(text) - ascii_chars
    return max(1, ascii_chars // 4 + non_ascii_chars + 24)


def fit_text_to_token_budget(text: str, token_budget: int) -> str:
    if estimate_tokens(text) <= token_budget:
        return text
    char_budget = max(1000, token_budget * 2)
    return _head_tail(text, char_budget, max(1, len(text.splitlines())))


def _source_priority(item: EvidenceItem) -> int:
    path = item.path.lower().replace("\\", "/")
    name = Path(item.path).name.lower()
    if "/best_solution/" in path:
        return 0
    if name in {"description.md", "data_description.md", "automl_context.md"}:
        return 1
    if "/top_solution/" in path and name in {"solution.py", "metric.txt", "node_id.txt"}:
        return 2
    if name in {"model_artifacts_manifest.md", "model_path.txt"}:
        return 3
    if "/checkpoint_candidates/" in path:
        return 4
    if name in SOURCE_NAMES:
        return 5
    return 20


def _display_path(item: EvidenceItem, path: Path) -> str:
    try:
        relative = path.relative_to(Path(item.source_root).expanduser().resolve())
        return f"{item.label}/{relative.as_posix()}"
    except ValueError:
        return f"{item.label}/{path.name}"


def _python_outline(text: str) -> list[str]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    outline: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            outline.append(
                f"function {node.name}: lines {node.lineno}-{getattr(node, 'end_lineno', node.lineno)}"
            )
        elif isinstance(node, ast.ClassDef):
            outline.append(
                f"class {node.name}: lines {node.lineno}-{getattr(node, 'end_lineno', node.lineno)}"
            )
    return outline[:160]


def _head_tail(text: str, max_chars: int, line_count: int) -> str:
    if len(text) <= max_chars:
        return text
    head_chars = max_chars * 3 // 5
    tail_chars = max_chars - head_chars
    head = text[:head_chars]
    tail = text[-tail_chars:]
    omitted = max(0, len(text) - len(head) - len(tail))
    return (
        f"{head}\n\n[OMITTED {omitted} CHARS FROM THE MIDDLE; "
        f"USE source_id WITH LINE RANGE TO RETRIEVE. TOTAL_LINES={line_count}]\n\n{tail}"
    )
