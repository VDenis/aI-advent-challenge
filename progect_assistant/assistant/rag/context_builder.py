"""
Context Builder for Code RAG
=============================
Assembles retrieved chunks into structured LLM prompts.
Includes file tree visualization and parent context injection.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set
import textwrap

from .ast_chunker import CodeChunk
from .hybrid_retriever import RetrievalResult


@dataclass
class ContextConfig:
    """Configuration for context building."""
    max_context_tokens: int = 8000        # Max tokens for context
    include_file_tree: bool = True         # Add visual file tree
    include_line_numbers: bool = True      # Show line numbers
    include_imports: bool = True           # Show imports
    include_parent_context: bool = True    # Show class for methods
    group_by_file: bool = True             # Group chunks by file
    show_relevance_scores: bool = False    # Show retrieval scores


class FileTreeBuilder:
    """Builds ASCII file tree from file paths."""

    def build(self, file_paths: List[str], highlight_files: Optional[Set[str]] = None) -> str:
        """
        Build ASCII tree from list of file paths.

        Args:
            file_paths: List of relative file paths
            highlight_files: Files to mark with [*]
        """
        highlight_files = highlight_files or set()

        # Build tree structure
        tree: Dict = {}
        for path in sorted(set(file_paths)):
            parts = Path(path).parts
            current = tree
            for part in parts:
                if part not in current:
                    current[part] = {}
                current = current[part]

        # Render tree
        lines = ["📁 Project Structure", ""]
        self._render_tree(tree, lines, "", highlight_files, "")

        return "\n".join(lines)

    def _render_tree(
        self,
        tree: Dict,
        lines: List[str],
        prefix: str,
        highlight: Set[str],
        current_path: str
    ):
        items = list(tree.items())
        for i, (name, subtree) in enumerate(items):
            is_last = (i == len(items) - 1)
            connector = "└── " if is_last else "├── "

            full_path = f"{current_path}/{name}" if current_path else name
            marker = " [*]" if full_path in highlight or name in highlight else ""

            # Determine if it's a file or directory
            if subtree:
                icon = "📁"
            else:
                icon = self._get_file_icon(name)

            lines.append(f"{prefix}{connector}{icon} {name}{marker}")

            if subtree:
                extension = "    " if is_last else "│   "
                self._render_tree(subtree, lines, prefix + extension, highlight, full_path)

    def _get_file_icon(self, filename: str) -> str:
        """Get emoji icon based on file extension."""
        ext = Path(filename).suffix.lower()
        icons = {
            ".py": "🐍",
            ".js": "📜",
            ".ts": "📘",
            ".jsx": "⚛️",
            ".tsx": "⚛️",
            ".json": "📋",
            ".yaml": "📋",
            ".yml": "📋",
            ".md": "📝",
            ".html": "🌐",
            ".css": "🎨",
            ".sql": "🗃️",
            ".sh": "🖥️",
            ".env": "🔐",
        }
        return icons.get(ext, "📄")


class ContextBuilder:
    """
    Builds structured context for LLM from retrieval results.

    Features:
    - Groups chunks by file
    - Adds file tree visualization
    - Injects parent context (class definitions for methods)
    - Formats with line numbers
    - Respects token limits
    """

    SYSTEM_PROMPT_TEMPLATE = """You are a code assistant analyzing a codebase.
Answer questions using ONLY the provided code context below.
If the answer is not in the context, say "I don't have enough information in the provided code context."

When referencing code:
- Always mention the file path and line numbers
- Quote relevant code snippets
- Explain the code's purpose and how it relates to the question

{file_tree}

---
CODE CONTEXT:
{context}
---"""

    def __init__(self, config: Optional[ContextConfig] = None):
        self.config = config or ContextConfig()
        self.tree_builder = FileTreeBuilder()

    def build_context(
        self,
        results: List[RetrievalResult],
        query: Optional[str] = None
    ) -> str:
        """
        Build formatted context string from retrieval results.

        Args:
            results: List of RetrievalResult from HybridRetriever
            query: Original query (for reference)

        Returns:
            Formatted context string
        """
        if not results:
            return "No relevant code found."

        chunks = [r.chunk for r in results]

        # Build file tree
        file_tree = ""
        if self.config.include_file_tree:
            file_paths = list(set(c.file_path for c in chunks))
            highlight = set(file_paths)
            file_tree = self.tree_builder.build(file_paths, highlight)

        # Group chunks by file
        if self.config.group_by_file:
            context = self._build_grouped_context(results)
        else:
            context = self._build_flat_context(results)

        return self.SYSTEM_PROMPT_TEMPLATE.format(
            file_tree=file_tree,
            context=context
        )

    def _build_grouped_context(self, results: List[RetrievalResult]) -> str:
        """Group chunks by file for better readability."""
        # Group by file
        by_file: Dict[str, List[RetrievalResult]] = defaultdict(list)
        for r in results:
            by_file[r.chunk.file_path].append(r)

        sections = []

        for file_path in sorted(by_file.keys()):
            file_results = by_file[file_path]
            # Sort by line number within file
            file_results.sort(key=lambda r: r.chunk.start_line)

            file_section = [f"## File: {file_path}"]

            # Add imports once per file
            if self.config.include_imports:
                imports = file_results[0].chunk.imports
                if imports:
                    file_section.append("\n**Imports:**")
                    file_section.append("```python")
                    file_section.extend(imports[:10])  # Limit imports
                    file_section.append("```\n")

            # Add each chunk
            for result in file_results:
                chunk = result.chunk
                chunk_section = self._format_chunk(chunk, result)
                file_section.append(chunk_section)

            sections.append("\n".join(file_section))

        return "\n\n---\n\n".join(sections)

    def _build_flat_context(self, results: List[RetrievalResult]) -> str:
        """Simple flat list of chunks."""
        sections = []
        for result in results:
            sections.append(self._format_chunk(result.chunk, result))
        return "\n\n---\n\n".join(sections)

    def _format_chunk(self, chunk: CodeChunk, result: RetrievalResult) -> str:
        """Format a single chunk with metadata."""
        lines = []

        # Header with location
        header_parts = [f"### {chunk.chunk_type.title()}: `{chunk.name}`"]
        if self.config.include_line_numbers:
            header_parts.append(f"(lines {chunk.start_line}-{chunk.end_line})")
        if self.config.show_relevance_scores:
            header_parts.append(f"[score: {result.final_score:.3f}]")
        lines.append(" ".join(header_parts))

        # Parent context for methods
        if self.config.include_parent_context and chunk.parent_class:
            lines.append(f"\n**Parent class:** `{chunk.parent_class}`")
            if chunk.parent_context:
                lines.append(f"```python\n{chunk.parent_context}\n```")

        # Docstring/summary
        if chunk.summary:
            lines.append(f"\n**Summary:** {chunk.summary}")
        elif chunk.docstring:
            lines.append(f"\n**Docstring:** {chunk.docstring[:200]}...")

        # Decorators
        if chunk.decorators:
            lines.append(f"\n**Decorators:** {', '.join(chunk.decorators)}")

        # Code
        lines.append("\n```python")
        if self.config.include_line_numbers:
            code_lines = chunk.text.split("\n")
            for i, line in enumerate(code_lines):
                line_num = chunk.start_line + i
                lines.append(f"{line_num:4d} | {line}")
        else:
            lines.append(chunk.text)
        lines.append("```")

        # Dependencies
        if chunk.dependencies:
            deps = ", ".join(chunk.dependencies[:10])
            lines.append(f"\n**Calls:** {deps}")

        return "\n".join(lines)

    def build_chat_messages(
        self,
        results: List[RetrievalResult],
        user_query: str,
        conversation_history: Optional[List[Dict]] = None
    ) -> List[Dict[str, str]]:
        """
        Build complete chat messages for LLM API.

        Args:
            results: Retrieval results
            user_query: User's question
            conversation_history: Previous messages (optional)

        Returns:
            List of message dicts for OpenAI-compatible API
        """
        context = self.build_context(results, user_query)

        messages = [{"role": "system", "content": context}]

        # Add conversation history
        if conversation_history:
            messages.extend(conversation_history)

        # Add current query
        messages.append({"role": "user", "content": user_query})

        return messages

    def estimate_tokens(self, text: str) -> int:
        """Rough token estimation (4 chars per token)."""
        return len(text) // 4


class AdaptiveContextBuilder(ContextBuilder):
    """
    Advanced context builder with token budget management.
    Dynamically adjusts context based on available token budget.
    """

    def build_context_with_budget(
        self,
        results: List[RetrievalResult],
        token_budget: int,
        query: Optional[str] = None
    ) -> str:
        """
        Build context that fits within token budget.

        Prioritizes:
        1. Most relevant chunks (by score)
        2. Chunks with parent context
        3. Complete code over truncated
        """
        if not results:
            return "No relevant code found."

        # Reserve tokens for structure
        structure_tokens = 500
        available = token_budget - structure_tokens

        # Sort by relevance
        sorted_results = sorted(results, key=lambda r: r.final_score, reverse=True)

        # Greedily add chunks
        selected: List[RetrievalResult] = []
        current_tokens = 0

        for result in sorted_results:
            chunk_text = self._format_chunk(result.chunk, result)
            chunk_tokens = self.estimate_tokens(chunk_text)

            if current_tokens + chunk_tokens <= available:
                selected.append(result)
                current_tokens += chunk_tokens
            elif not selected:
                # Always include at least one (truncated if needed)
                selected.append(result)
                break

        # Build context with selected chunks
        return super().build_context(selected, query)


# Convenience functions

def build_rag_prompt(
    results: List[RetrievalResult],
    query: str,
    max_tokens: int = 8000
) -> str:
    """Quick function to build RAG prompt."""
    builder = AdaptiveContextBuilder()
    return builder.build_context_with_budget(results, max_tokens, query)


def build_chat_messages(
    results: List[RetrievalResult],
    query: str,
    history: Optional[List[Dict]] = None
) -> List[Dict[str, str]]:
    """Quick function to build chat messages."""
    builder = ContextBuilder()
    return builder.build_chat_messages(results, query, history)
