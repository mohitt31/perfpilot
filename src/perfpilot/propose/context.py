"""Deterministic, byte-bounded repository context assembly."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from perfpilot.evidence.schema import Hotspot, ProposalConfig

_SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"}
_SKIPPED_PARTS = {".git", "build", "_build", "cmake-build-debug", "cmake-build-release"}


class ContextError(RuntimeError):
    """The hotspot context could not be assembled safely."""


@dataclass(frozen=True)
class ContextSection:
    kind: str
    path: str
    start_line: int
    end_line: int
    content: str


class _Budget:
    def __init__(self, maximum_bytes: int) -> None:
        self.maximum_bytes = maximum_bytes
        self.used_bytes = 0
        self.sections: list[ContextSection] = []
        self.truncated = False

    def add(self, section: ContextSection) -> None:
        encoded = section.content.encode("utf-8")
        remaining = self.maximum_bytes - self.used_bytes
        if remaining <= 0:
            self.truncated = True
            return
        if len(encoded) > remaining:
            content = encoded[:remaining].decode("utf-8", errors="ignore")
            if not content:
                self.truncated = True
                return
            consumed_lines = max(1, content.count("\n") + 1)
            section = ContextSection(
                kind=section.kind,
                path=section.path,
                start_line=section.start_line,
                end_line=min(section.end_line, section.start_line + consumed_lines - 1),
                content=content,
            )
            encoded = content.encode("utf-8")
            self.truncated = True
        self.sections.append(section)
        self.used_bytes += len(encoded)


def _read_lines(path: Path) -> list[str]:
    if path.is_symlink():
        raise ContextError(f"refusing to read symlinked context file: {path}")
    try:
        return path.read_text(encoding="utf-8").splitlines(keepends=True)
    except (OSError, UnicodeDecodeError) as exc:
        raise ContextError(f"could not read text context file {path}: {exc}") from exc


def _section(
    root: Path,
    relative: str,
    kind: str,
    center_line: int,
    window_lines: int,
) -> ContextSection:
    path = (root / relative).resolve(strict=True)
    if not path.is_relative_to(root.resolve()):
        raise ContextError(f"context path escapes repository: {relative}")
    lines = _read_lines(path)
    half = window_lines // 2
    start = max(1, center_line - half)
    end = min(len(lines), start + window_lines - 1)
    content = "".join(lines[start - 1 : end])
    return ContextSection(kind, relative, start, end, content)


def _candidate_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and not any(part in _SKIPPED_PARTS for part in path.relative_to(root).parts)
        and (
            path.suffix.lower() in _SOURCE_SUFFIXES
            or "test" in path.name.lower()
            or path.name in {"CMakeLists.txt", "CONTRIBUTING.md", "CONTRIBUTING.rst"}
        )
    )


def assemble_context(root: Path, hotspot: Hotspot, config: ProposalConfig) -> bytes:
    if hotspot.source_path is None or hotspot.source_line is None:
        raise ContextError("proposal context requires a source-mapped hotspot")
    budget = _Budget(config.maximum_context_bytes)
    budget.add(
        _section(
            root,
            hotspot.source_path,
            "hotspot_source",
            hotspot.source_line,
            config.source_window_lines,
        )
    )
    symbol_token = hotspot.symbol.split("::")[-1].split("(")[0].strip()
    seen = {hotspot.source_path}
    for path in _candidate_files(root):
        relative = path.relative_to(root).as_posix()
        if relative in seen:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        line_number: int | None = None
        kind: str | None = None
        if symbol_token and symbol_token in text:
            line_number = text[: text.index(symbol_token)].count("\n") + 1
            kind = "symbol_reference"
        elif "test" in path.name.lower() and path.stat().st_size <= 50_000:
            line_number = 1
            kind = "test"
        elif path.name == "CMakeLists.txt" and path.parent == root:
            line_number = 1
            kind = "build_configuration"
        elif path.name.startswith("CONTRIBUTING"):
            line_number = 1
            kind = "contribution_guidelines"
        if line_number is None or kind is None:
            continue
        budget.add(_section(root, relative, kind, line_number, config.source_window_lines))
        seen.add(relative)

    payload = {
        "hotspot": hotspot.model_dump(mode="json"),
        "byte_budget": config.maximum_context_bytes,
        "content_bytes": budget.used_bytes,
        "truncated": budget.truncated,
        "sections": [section.__dict__ for section in budget.sections],
    }

    def serialize() -> bytes:
        return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()

    encoded = serialize()
    while len(encoded) > config.maximum_context_bytes:
        sections = payload["sections"]
        assert isinstance(sections, list)
        if not sections:
            raise ContextError("context metadata alone exceeds maximum_context_bytes")
        last = sections[-1]
        assert isinstance(last, dict)
        content = str(last["content"])
        content_bytes = content.encode("utf-8")
        overflow = len(encoded) - config.maximum_context_bytes
        keep = max(0, len(content_bytes) - max(1, overflow))
        shortened = content_bytes[:keep].decode("utf-8", errors="ignore")
        if not shortened:
            sections.pop()
        else:
            last["content"] = shortened
            last["end_line"] = int(last["start_line"]) + shortened.count("\n")
        payload["content_bytes"] = sum(
            len(str(section["content"]).encode("utf-8")) for section in sections
        )
        payload["truncated"] = True
        encoded = serialize()
    return encoded
