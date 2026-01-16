"""
Code RAG - High Performance Retrieval-Augmented Generation for Code
====================================================================
Main entry point that orchestrates AST chunking, hybrid retrieval, and context building.

Usage:
    from assistant.rag.code_rag import CodeRAG

    # Initialize
    rag = CodeRAG(project_root=Path("."))

    # Index codebase
    rag.build_index(progress_callback=lambda cur, total: print(f"{cur}/{total}"))

    # Search
    results = rag.search("How does authentication work?", top_k=5)

    # Get formatted context for LLM
    context = rag.get_context(results, query="How does authentication work?")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any
import json

from .ast_chunker import ASTChunker, CodeChunk, chunk_codebase
from .hybrid_retriever import (
    HybridRetriever,
    RetrievalResult,
    BM25Index,
    InMemoryVectorStore,
    HuggingFaceEmbedder,
    OllamaEmbedder,
    EmbeddingProvider,
    BGEReranker,
    NoOpReranker,
    Reranker,
)
from .context_builder import (
    ContextBuilder,
    AdaptiveContextBuilder,
    ContextConfig,
    build_rag_prompt,
)

logger = logging.getLogger(__name__)


class CodeRAG:
    """
    High-Performance Code RAG System.

    Features:
    - AST-based smart chunking (preserves function/class context)
    - Hybrid search (dense semantic + sparse BM25)
    - Reranking for improved relevance
    - Structured context for LLM

    Performance targets:
    - Indexing: 500 files in < 60 seconds
    - Retrieval: < 500ms for 10k chunks
    """

    DEFAULT_INDEX_PATH = ".cache/code_rag_index.json"

    def __init__(
        self,
        project_root: Path,
        embedding_provider: str = "ollama",  # "ollama", "huggingface", "openai"
        embedding_model: Optional[str] = None,
        use_reranker: bool = False,
        reranker_model: Optional[str] = None,
        cache_dir: Optional[Path] = None,
        device: str = "cpu",
    ):
        """
        Initialize Code RAG system.

        Args:
            project_root: Root directory of the codebase
            embedding_provider: "ollama", "huggingface", or "openai"
            embedding_model: Model name (provider-specific)
            use_reranker: Whether to use reranking (slower but more accurate)
            reranker_model: Reranker model name
            cache_dir: Directory for index cache
            device: Device for local models ("cpu", "cuda", "mps")
        """
        self.project_root = Path(project_root).resolve()
        self.cache_dir = cache_dir or (self.project_root / ".cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.index_path = self.cache_dir / "code_rag_index.json"

        # Initialize components
        self.embedder = self._create_embedder(embedding_provider, embedding_model, device)
        self.reranker = self._create_reranker(use_reranker, reranker_model, device)
        self.context_builder = AdaptiveContextBuilder()

        # Retriever (lazy init on first use)
        self._retriever: Optional[HybridRetriever] = None

    def _create_embedder(
        self,
        provider: str,
        model: Optional[str],
        device: str
    ) -> EmbeddingProvider:
        """Create embedding provider based on configuration."""
        if provider == "ollama":
            return OllamaEmbedder(model=model or "nomic-embed-text")
        elif provider == "huggingface":
            return HuggingFaceEmbedder(
                model_name=model or "BAAI/bge-m3",
                device=device
            )
        elif provider == "openai":
            import os
            api_key = os.environ.get("OPENAI_API_KEY", "")
            from .hybrid_retriever import OpenAIEmbedder
            return OpenAIEmbedder(api_key=api_key, model=model or "text-embedding-3-small")
        else:
            logger.warning(f"Unknown provider {provider}, falling back to Ollama")
            return OllamaEmbedder(model=model or "nomic-embed-text")

    def _create_reranker(
        self,
        use_reranker: bool,
        model: Optional[str],
        device: str
    ) -> Reranker:
        """Create reranker based on configuration."""
        if not use_reranker:
            return NoOpReranker()
        return BGEReranker(
            model_name=model or "BAAI/bge-reranker-v2-m3",
            device=device
        )

    @property
    def retriever(self) -> HybridRetriever:
        """Get or create retriever (loads from cache if available)."""
        if self._retriever is None:
            if self.index_path.exists():
                logger.info(f"Loading index from {self.index_path}")
                self._retriever = HybridRetriever.load(
                    self.index_path,
                    embedder=self.embedder,
                    reranker=self.reranker
                )
            else:
                # Create empty retriever
                self._retriever = HybridRetriever(
                    embedder=self.embedder,
                    vector_store=InMemoryVectorStore(),
                    bm25_index=BM25Index(),
                    reranker=self.reranker,
                )
        return self._retriever

    def build_index(
        self,
        file_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
        save: bool = True
    ) -> int:
        """
        Build or rebuild the RAG index.

        Args:
            file_patterns: Glob patterns for files to include
            exclude_patterns: Glob patterns for files to exclude
            progress_callback: Called with (current_file, processed, total)
            save: Whether to save index to disk

        Returns:
            Number of chunks indexed
        """
        logger.info(f"Building index for {self.project_root}")

        # Default patterns
        if file_patterns is None:
            file_patterns = ["**/*.py", "**/*.js", "**/*.ts", "**/*.jsx", "**/*.tsx"]

        if exclude_patterns is None:
            exclude_patterns = [
                "**/node_modules/**", "**/.git/**", "**/venv/**", "**/venv*/**",
                "**/__pycache__/**", "**/dist/**", "**/build/**",
                "**/.cache/**", "**/.*/**", "**/*.min.js", "**/*.bundle.js"
            ]

        # Chunk codebase
        chunks = chunk_codebase(
            project_root=self.project_root,
            file_patterns=file_patterns,
            exclude_patterns=exclude_patterns,
            progress_callback=progress_callback
        )

        logger.info(f"Generated {len(chunks)} chunks")

        if not chunks:
            logger.warning("No chunks generated. Check file patterns.")
            return 0

        # Create fresh retriever
        self._retriever = HybridRetriever(
            embedder=self.embedder,
            vector_store=InMemoryVectorStore(),
            bm25_index=BM25Index(),
            reranker=self.reranker,
        )

        # Index chunks
        def embedding_progress(current: int, total: int):
            if progress_callback:
                progress_callback("Embedding chunks", current, total)

        self._retriever.index_chunks(chunks, progress_callback=embedding_progress)

        # Save to disk
        if save:
            self._retriever.save(self.index_path)
            logger.info(f"Saved index to {self.index_path}")

        return len(chunks)

    def search(
        self,
        query: str,
        top_k: int = 10,
        rerank: bool = True,
        file_filter: Optional[List[str]] = None
    ) -> List[RetrievalResult]:
        """
        Search the codebase.

        Args:
            query: Natural language query or code snippet
            top_k: Number of results to return
            rerank: Whether to apply reranking
            file_filter: Optional list of file paths to search in

        Returns:
            List of RetrievalResult sorted by relevance
        """
        if not self.retriever.chunks:
            logger.warning("Index is empty. Run build_index() first.")
            return []

        return self.retriever.search(
            query=query,
            top_k=top_k,
            rerank=rerank,
            file_filter=file_filter
        )

    def get_context(
        self,
        results: List[RetrievalResult],
        query: Optional[str] = None,
        max_tokens: int = 8000
    ) -> str:
        """
        Build formatted context for LLM from search results.

        Args:
            results: Search results from search()
            query: Original query (for reference)
            max_tokens: Maximum context tokens

        Returns:
            Formatted context string
        """
        return self.context_builder.build_context_with_budget(
            results=results,
            token_budget=max_tokens,
            query=query
        )

    def query(
        self,
        question: str,
        top_k: int = 10,
        max_context_tokens: int = 8000
    ) -> Dict[str, Any]:
        """
        Complete RAG query: search + context building.

        Args:
            question: User's question
            top_k: Number of chunks to retrieve
            max_context_tokens: Max context size

        Returns:
            Dict with 'results', 'context', 'files' keys
        """
        results = self.search(question, top_k=top_k)
        context = self.get_context(results, question, max_context_tokens)

        files = list(set(r.chunk.file_path for r in results))

        return {
            "results": results,
            "context": context,
            "files": files,
            "query": question,
            "num_chunks": len(results)
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        if not self.retriever.chunks:
            return {"status": "empty", "chunks": 0, "files": 0}

        files = set(c.file_path for c in self.retriever.chunks.values())
        chunk_types = {}
        for c in self.retriever.chunks.values():
            chunk_types[c.chunk_type] = chunk_types.get(c.chunk_type, 0) + 1

        return {
            "status": "ready",
            "chunks": len(self.retriever.chunks),
            "files": len(files),
            "chunk_types": chunk_types,
            "index_path": str(self.index_path),
        }


# Convenience function for quick setup
def create_code_rag(
    project_root: str = ".",
    use_gpu: bool = False,
    use_reranker: bool = False
) -> CodeRAG:
    """
    Quick setup for Code RAG.

    Args:
        project_root: Path to codebase
        use_gpu: Use GPU for embeddings (if available)
        use_reranker: Enable reranking (slower but better)

    Returns:
        Configured CodeRAG instance
    """
    device = "cuda" if use_gpu else "cpu"

    return CodeRAG(
        project_root=Path(project_root),
        embedding_provider="ollama",  # Change to "huggingface" if needed
        use_reranker=use_reranker,
        device=device
    )


# CLI for testing
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m assistant.rag.code_rag <command> [args]")
        print("Commands:")
        print("  index [path]    - Build index for codebase")
        print("  search <query>  - Search codebase")
        print("  stats           - Show index statistics")
        sys.exit(1)

    command = sys.argv[1]
    project_path = Path.cwd()

    rag = CodeRAG(project_root=project_path)

    if command == "index":
        if len(sys.argv) > 2:
            project_path = Path(sys.argv[2])
            rag = CodeRAG(project_root=project_path)

        def progress(file: str, current: int, total: int):
            print(f"\r[{current}/{total}] {file[:60]:<60}", end="", flush=True)

        count = rag.build_index(progress_callback=progress)
        print(f"\n\nIndexed {count} chunks")

    elif command == "search":
        if len(sys.argv) < 3:
            print("Usage: python -m assistant.rag.code_rag search <query>")
            sys.exit(1)

        query = " ".join(sys.argv[2:])
        results = rag.search(query, top_k=5)

        print(f"\nSearch results for: {query}\n")
        for i, r in enumerate(results, 1):
            print(f"{i}. [{r.final_score:.3f}] {r.chunk.file_path}:{r.chunk.start_line}")
            print(f"   {r.chunk.chunk_type}: {r.chunk.name}")
            print(f"   {r.chunk.text[:100]}...")
            print()

    elif command == "stats":
        stats = rag.get_stats()
        print(json.dumps(stats, indent=2))

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
