import json
import math
import os
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple


# Include Unicode word chars so Cyrillic and other alphabets are indexed/searched.
WORD_RE = re.compile(r"[\w\-/]+", re.UNICODE)


@dataclass
class Chunk:
    path: str
    section: str
    text: str
    vector: Dict[str, float]


@dataclass
class RagIndex:
    chunks: List[Chunk]

    def to_json(self) -> str:
        payload = {
            "chunks": [
                {
                    "path": chunk.path,
                    "section": chunk.section,
                    "text": chunk.text,
                    "vector": chunk.vector,
                }
                for chunk in self.chunks
            ]
        }
        return json.dumps(payload, ensure_ascii=True)

    @classmethod
    def from_json(cls, raw: str) -> "RagIndex":
        payload = json.loads(raw)
        chunks = [Chunk(**item) for item in payload.get("chunks", [])]
        return cls(chunks=chunks)


def _tokenize(text: str) -> List[str]:
    return [token.lower() for token in WORD_RE.findall(text)]


def _vectorize(tokens: Sequence[str]) -> Dict[str, float]:
    counts: Dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    total = float(sum(counts.values())) or 1.0
    return {token: count / total for token, count in counts.items()}


def _cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(val * b.get(key, 0.0) for key, val in a.items())
    norm_a = math.sqrt(sum(val * val for val in a.values()))
    norm_b = math.sqrt(sum(val * val for val in b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class RagIndexer:
    def __init__(self, project_root: str, cache_path: str) -> None:
        self.project_root = project_root
        self.cache_path = cache_path

    def discover_files(self) -> List[Path]:
        root = Path(self.project_root)
        cache_path = Path(self.cache_path).resolve()
        cache_dir = cache_path.parent
        ignored_roots = [
            Path("rag_search") / "test_corpus",
            Path("websearch") / "output",
        ]
        patterns = [
            "README.md",
            "docs/**/*.md",
            "docs/**/*.txt",
            "support/docs/**/*.md",
            "support/faq.json",
            "support/config.json",
            "**/*.md",
            "**/*.rst",
            "**/*.txt",
            "**/*.py",
            "**/*.js",
            "**/*.ts",
            "**/*.jsx",
            "**/*.tsx",
            "**/*.css",
            "**/*.html",
            "**/*.sh",
            "**/*.sql",
            "**/*.yaml",
            "**/*.yml",
            "**/*.json",
            "**/*.toml",
            "**/*.ini",
            "**/*.cfg",
            "**/.editorconfig",
        ]
        ignore_dirs = {".git", "node_modules", "__pycache__", "site-packages"}

        files: List[Path] = []
        for pattern in patterns:
            for path in root.glob(pattern):
                resolved = path.resolve()
                try:
                    rel_path = resolved.relative_to(root)
                except ValueError:
                    rel_path = resolved
                if any(rel_path.is_relative_to(ignored) for ignored in ignored_roots):
                    continue
                # Skip RAG cache itself and its directory to avoid re-indexing cache.
                if resolved == cache_path or (cache_dir.name.startswith(".") and cache_dir in resolved.parents):
                    continue
                # Skip hidden directories/files (starting with .) and known ignored/virtualenv dirs.
                if any(
                    part in ignore_dirs
                    or part.startswith(".")
                    or part.startswith("venv")
                    or part.startswith("env")
                    or part == "dist"
                    or part == "build"
                    for part in path.parts
                ):
                    continue
                if path.is_file():
                    files.append(path)
        return sorted(set(files))

    def build_index(
        self,
        progress_cb: Optional[Callable[[Dict[str, object]], None]] = None,
        verbose: bool = True,
    ) -> RagIndex:
        chunks: List[Chunk] = []
        files = self.discover_files()
        total = len(files)
        if verbose:
            print(f"RAG indexing started: {total} files.")
        if progress_cb:
            progress_cb({"event": "start", "total": total})
        for idx, path in enumerate(files, start=1):
            rel_path = os.path.relpath(path, self.project_root)
            if verbose:
                print(f"[{idx}/{total}] {rel_path}")
            if progress_cb:
                progress_cb({"event": "file", "index": idx, "total": total, "path": rel_path})
            chunks.extend(self._chunk_file(path))
        if verbose:
            print(f"RAG indexing complete: {len(chunks)} chunks.")
        if progress_cb:
            progress_cb({"event": "done", "total": total, "chunks": len(chunks)})
        index = RagIndex(chunks=chunks)
        self._persist(index)
        return index

    def load_or_build(self) -> RagIndex:
        cache = Path(self.cache_path)
        if cache.exists():
            try:
                return RagIndex.from_json(cache.read_text(encoding="utf-8"))
            except Exception:
                pass
        return self.build_index()

    def _persist(self, index: RagIndex) -> None:
        cache = Path(self.cache_path)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(index.to_json(), encoding="utf-8")

    def _chunk_file(self, path: Path) -> Iterable[Chunk]:
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel_path = os.path.relpath(path, self.project_root)
        if path.suffix.lower() in {".md", ".rst"}:
            return list(self._chunk_markdown(rel_path, text))
        return list(self._chunk_plain(rel_path, text))

    def _chunk_markdown(self, rel_path: str, text: str) -> Iterable[Chunk]:
        sections = []
        current_heading = "root"
        buffer: List[str] = []
        for line in text.splitlines():
            if line.startswith("#"):
                if buffer:
                    sections.append((current_heading, "\n".join(buffer)))
                    buffer = []
                current_heading = line.lstrip("#").strip() or "root"
            buffer.append(line)
        if buffer:
            sections.append((current_heading, "\n".join(buffer)))

        for heading, block in sections:
            yield from self._chunk_text(rel_path, heading, block)

    def _chunk_plain(self, rel_path: str, text: str) -> Iterable[Chunk]:
        return self._chunk_text(rel_path, "file", text)

    def _chunk_text(self, rel_path: str, section: str, text: str) -> Iterable[Chunk]:
        max_chars = 1000
        for i in range(0, len(text), max_chars):
            chunk_text = text[i : i + max_chars].strip()
            if not chunk_text:
                continue
            tokens = _tokenize(chunk_text)
            vector = _vectorize(tokens)
            yield Chunk(path=rel_path, section=section, text=chunk_text, vector=vector)


class RagSearch:
    def __init__(self, index: RagIndex) -> None:
        self._index = index

    def search(self, query: str, top_k: int = 5) -> List[Tuple[float, Chunk]]:
        query_tokens = _tokenize(query)
        query_vec = _vectorize(query_tokens)
        scored = [(_cosine(query_vec, chunk.vector), chunk) for chunk in self._index.chunks]
        scored.sort(key=lambda item: item[0], reverse=True)
        return [(score, chunk) for score, chunk in scored[:top_k] if score > 0.0]
