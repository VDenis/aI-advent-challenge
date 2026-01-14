"""Build review context using RAG."""

import os
import re
import sys
from typing import List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../progect_assistant"))

from assistant.rag import RagIndexer, RagSearch

from .config import CodeReviewConfig
from .models import PRData, PRFile, ReviewContext


class ContextBuilder:
    """Builds review context using RAG and token budget management."""

    def __init__(self, config: CodeReviewConfig):
        self.config = config

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation (1 token ≈ 4 chars for English/Russian mix)."""
        return len(text) // 4

    def _extract_key_terms(self, pr_data: PRData, pr_files: List[PRFile]) -> str:
        """Extract key terms from PR for RAG search."""
        terms = []

        # PR title and description
        terms.append(pr_data.title)
        if pr_data.description:
            terms.append(pr_data.description[:500])  # First 500 chars

        # File paths (extract directory and filename)
        for pr_file in pr_files:
            parts = pr_file.path.split("/")
            terms.extend(parts)

        # Extract keywords from patches
        for pr_file in pr_files[:10]:  # Limit to first 10 files
            if pr_file.patch:
                # Extract function/class names from diff
                patch_keywords = re.findall(
                    r"(?:def|class|function|const|let|var)\s+(\w+)", pr_file.patch
                )
                terms.extend(patch_keywords[:5])  # Top 5 per file

        return " ".join(terms)

    def _truncate_to_budget(self, text: str, token_budget: int) -> str:
        """Truncate text to fit token budget."""
        estimated = self._estimate_tokens(text)
        if estimated <= token_budget:
            return text

        # Truncate to approximately fit budget
        target_chars = token_budget * 4
        if len(text) <= target_chars:
            return text

        return text[:target_chars] + "\n... (truncated)"

    def _build_diff_context(self, pr_files: List[PRFile]) -> str:
        """Build diff context from PR files."""
        diff_lines = []

        for pr_file in pr_files:
            diff_lines.append(f"\n## File: {pr_file.path}")
            diff_lines.append(f"Status: {pr_file.status}")
            diff_lines.append(f"Additions: +{pr_file.additions}, Deletions: -{pr_file.deletions}")

            if pr_file.patch:
                diff_lines.append("\nDiff:")
                diff_lines.append(pr_file.patch)
            else:
                diff_lines.append("(No diff available)")

            diff_lines.append("")

        return "\n".join(diff_lines)

    async def build_context(self, pr_data: PRData, pr_files: List[PRFile]) -> ReviewContext:
        """Build full review context with RAG and token management."""
        # Load or build RAG index
        indexer = RagIndexer(
            project_root=self.config.project_root, cache_path=self.config.rag_cache_path
        )
        rag_index = indexer.load_or_build()
        rag_search = RagSearch(rag_index)

        # Extract key terms for RAG search
        query = self._extract_key_terms(pr_data, pr_files)

        # Search for relevant documentation and patterns
        results = rag_search.search(query, top_k=10)

        # Separate documentation from code patterns
        relevant_docs = []
        existing_patterns = []

        for score, chunk in results:
            if score < 0.1:  # Skip low relevance
                continue

            # Categorize by file type
            if any(
                doc in chunk.path.lower()
                for doc in ["readme", "contributing", "docs/", ".md"]
            ):
                relevant_docs.append(f"[{chunk.path}:{chunk.section}]\n{chunk.text}")
            else:
                existing_patterns.append(f"[{chunk.path}:{chunk.section}]\n{chunk.text}")

        # Build context strings
        docs_text = "\n\n".join(relevant_docs[:5]) if relevant_docs else "No relevant documentation found."
        patterns_text = "\n\n".join(existing_patterns[:5]) if existing_patterns else "No similar patterns found."

        # Truncate to token budgets
        docs_text = self._truncate_to_budget(docs_text, self.config.rag_context_tokens // 2)
        patterns_text = self._truncate_to_budget(patterns_text, self.config.rag_context_tokens // 2)

        # Build diff context
        diff_text = self._build_diff_context(pr_files)
        diff_text = self._truncate_to_budget(diff_text, self.config.diff_context_tokens)

        # Estimate total tokens
        total_tokens = (
            self._estimate_tokens(docs_text)
            + self._estimate_tokens(patterns_text)
            + self._estimate_tokens(diff_text)
            + self.config.pr_metadata_tokens
        )

        return ReviewContext(
            pr_data=pr_data,
            pr_files=pr_files,
            relevant_docs=docs_text,
            existing_patterns=patterns_text,
            token_count=total_tokens,
        )

    async def build_minimal_context(self, pr_data: PRData, pr_files: List[PRFile]) -> ReviewContext:
        """Build minimal context when RAG index is unavailable."""
        # Just use PR data and diffs, no RAG context
        diff_text = self._build_diff_context(pr_files)
        diff_text = self._truncate_to_budget(diff_text, self.config.diff_context_tokens)

        total_tokens = (
            self._estimate_tokens(diff_text) + self.config.pr_metadata_tokens
        )

        return ReviewContext(
            pr_data=pr_data,
            pr_files=pr_files,
            relevant_docs="(RAG context unavailable)",
            existing_patterns="(RAG context unavailable)",
            token_count=total_tokens,
        )
