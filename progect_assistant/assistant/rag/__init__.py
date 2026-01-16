"""
RAG (Retrieval-Augmented Generation) for Code Analysis.

Two implementations available:
1. Legacy (index.py): Simple TF-IDF based, fast but limited
2. Code RAG (code_rag.py): AST-based chunking, hybrid search, reranking

Usage (new Code RAG):
    from assistant.rag import CodeRAG
    rag = CodeRAG(project_root=Path("."))
    rag.build_index()
    results = rag.search("How does authentication work?")

Usage (legacy):
    from assistant.rag import RagIndexer, RagSearch
    indexer = RagIndexer(project_root)
    index = indexer.build_index()
    searcher = RagSearch(index)
    results = searcher.search("query")
"""

# Legacy implementation (backward compatible)
from .index import Chunk, RagIndex, RagIndexer, RagSearch

# New Code RAG implementation
from .ast_chunker import CodeChunk, ASTChunker, chunk_codebase
from .hybrid_retriever import (
    HybridRetriever,
    RetrievalResult,
    BM25Index,
    InMemoryVectorStore,
    HuggingFaceEmbedder,
    OllamaEmbedder,
    BGEReranker,
    NoOpReranker,
)
from .context_builder import ContextBuilder, ContextConfig, build_rag_prompt
from .code_rag import CodeRAG, create_code_rag

__all__ = [
    # Legacy
    "Chunk", "RagIndex", "RagIndexer", "RagSearch",
    # New - Main entry point
    "CodeRAG", "create_code_rag",
    # New - Components
    "CodeChunk", "ASTChunker", "chunk_codebase",
    "HybridRetriever", "RetrievalResult", "BM25Index",
    "InMemoryVectorStore", "HuggingFaceEmbedder", "OllamaEmbedder",
    "BGEReranker", "NoOpReranker",
    "ContextBuilder", "ContextConfig", "build_rag_prompt",
]
