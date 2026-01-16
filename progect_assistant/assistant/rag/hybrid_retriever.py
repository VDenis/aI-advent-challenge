"""
Hybrid Retrieval Engine for Code RAG
=====================================
Combines Dense (semantic) + Sparse (BM25) search with Reranking.

Performance target: <500ms for retrieval from 10k+ chunks
"""

from __future__ import annotations

import json
import math
import logging
import hashlib
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import numpy as np

from .ast_chunker import CodeChunk

logger = logging.getLogger(__name__)


# ============================================================================
# EMBEDDING PROVIDERS
# ============================================================================

class EmbeddingProvider(ABC):
    """Abstract base for embedding providers."""

    @abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts."""
        pass

    @abstractmethod
    def embed_query(self, query: str) -> List[float]:
        """Generate embedding for a single query."""
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Embedding dimension."""
        pass


class HuggingFaceEmbedder(EmbeddingProvider):
    """
    Local embeddings using sentence-transformers.
    Recommended: BAAI/bge-m3 (multi-lingual, good for code)
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        device: str = "cpu",
        normalize: bool = True
    ):
        self.model_name = model_name
        self.normalize = normalize
        self._model = None
        self._device = device

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name, device=self._device)
            logger.info(f"Loaded embedding model: {self.model_name}")

    def embed(self, texts: List[str]) -> List[List[float]]:
        self._load_model()
        embeddings = self._model.encode(
            texts, normalize_embeddings=self.normalize,
            show_progress_bar=len(texts) > 100
        )
        return embeddings.tolist()

    def embed_query(self, query: str) -> List[float]:
        self._load_model()
        if "bge" in self.model_name.lower():
            query = f"query: {query}"
        return self._model.encode(query, normalize_embeddings=self.normalize).tolist()

    @property
    def dimension(self) -> int:
        self._load_model()
        return self._model.get_sentence_embedding_dimension()


class OllamaEmbedder(EmbeddingProvider):
    """Local embeddings using Ollama."""

    def __init__(self, model: str = "nomic-embed-text", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._dimension_cache: Optional[int] = None

    def embed(self, texts: List[str]) -> List[List[float]]:
        import requests
        embeddings = []
        for text in texts:
            resp = requests.post(f"{self.base_url}/api/embeddings", json={"model": self.model, "prompt": text})
            resp.raise_for_status()
            embeddings.append(resp.json()["embedding"])
        return embeddings

    def embed_query(self, query: str) -> List[float]:
        return self.embed([query])[0]

    @property
    def dimension(self) -> int:
        if self._dimension_cache is None:
            self._dimension_cache = len(self.embed_query("test"))
        return self._dimension_cache


# ============================================================================
# BM25 SPARSE INDEX
# ============================================================================

class BM25Index:
    """BM25 sparse retrieval for exact keyword matching."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.doc_freqs: Dict[str, int] = defaultdict(int)
        self.doc_lens: List[int] = []
        self.avg_doc_len: float = 0.0
        self.inverted_index: Dict[str, List[Tuple[int, float]]] = defaultdict(list)
        self.total_docs: int = 0

    def _tokenize(self, text: str) -> List[str]:
        import re
        tokens = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*|[0-9]+', text)
        result = []
        for t in tokens:
            result.append(t)
            if t.lower() != t:
                result.append(t.lower())
        return result

    def build(self, documents: List[str]):
        self.total_docs = len(documents)
        term_freqs: List[Dict[str, int]] = []

        for doc in documents:
            tokens = self._tokenize(doc)
            tf = defaultdict(int)
            for token in tokens:
                tf[token] += 1
            term_freqs.append(dict(tf))
            self.doc_lens.append(len(tokens))
            for term in tf.keys():
                self.doc_freqs[term] += 1

        self.avg_doc_len = sum(self.doc_lens) / max(len(self.doc_lens), 1)

        for doc_id, tf in enumerate(term_freqs):
            for term, freq in tf.items():
                self.inverted_index[term].append((doc_id, freq))

    def search(self, query: str, top_k: int = 50) -> List[Tuple[int, float]]:
        query_tokens = self._tokenize(query)
        scores = defaultdict(float)

        for token in query_tokens:
            if token not in self.inverted_index:
                continue
            df = self.doc_freqs[token]
            idf = math.log((self.total_docs - df + 0.5) / (df + 0.5) + 1.0)
            for doc_id, tf in self.inverted_index[token]:
                doc_len = self.doc_lens[doc_id]
                tf_norm = (tf * (self.k1 + 1)) / (tf + self.k1 * (1 - self.b + self.b * doc_len / self.avg_doc_len))
                scores[doc_id] += idf * tf_norm

        results = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def to_dict(self) -> Dict:
        return {
            "k1": self.k1, "b": self.b,
            "doc_freqs": dict(self.doc_freqs),
            "doc_lens": self.doc_lens,
            "avg_doc_len": self.avg_doc_len,
            "inverted_index": {k: v for k, v in self.inverted_index.items()},
            "total_docs": self.total_docs,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "BM25Index":
        idx = cls(k1=data["k1"], b=data["b"])
        idx.doc_freqs = defaultdict(int, data["doc_freqs"])
        idx.doc_lens = data["doc_lens"]
        idx.avg_doc_len = data["avg_doc_len"]
        idx.inverted_index = defaultdict(list, {k: [tuple(x) for x in v] for k, v in data["inverted_index"].items()})
        idx.total_docs = data["total_docs"]
        return idx


# ============================================================================
# VECTOR STORES
# ============================================================================

class VectorStore(ABC):
    @abstractmethod
    def add(self, ids: List[str], vectors: List[List[float]], metadata: List[Dict]): pass
    @abstractmethod
    def search(self, vector: List[float], top_k: int = 50) -> List[Tuple[str, float, Dict]]: pass
    @abstractmethod
    def delete(self, ids: List[str]): pass


class InMemoryVectorStore(VectorStore):
    """Simple numpy-based vector store for small-medium collections."""

    def __init__(self):
        self.ids: List[str] = []
        self.vectors: Optional[np.ndarray] = None
        self.metadata: List[Dict] = []

    def add(self, ids: List[str], vectors: List[List[float]], metadata: List[Dict]):
        new_vectors = np.array(vectors, dtype=np.float32)
        if self.vectors is None:
            self.vectors = new_vectors
        else:
            self.vectors = np.vstack([self.vectors, new_vectors])
        self.ids.extend(ids)
        self.metadata.extend(metadata)

    def search(self, vector: List[float], top_k: int = 50) -> List[Tuple[str, float, Dict]]:
        if self.vectors is None or len(self.vectors) == 0:
            return []
        query_vec = np.array(vector, dtype=np.float32)
        similarities = np.dot(self.vectors, query_vec)
        top_indices = np.argsort(similarities)[::-1][:top_k]
        return [(self.ids[i], float(similarities[i]), self.metadata[i]) for i in top_indices]

    def delete(self, ids: List[str]):
        ids_set = set(ids)
        keep = [i for i, id_ in enumerate(self.ids) if id_ not in ids_set]
        self.ids = [self.ids[i] for i in keep]
        self.metadata = [self.metadata[i] for i in keep]
        if self.vectors is not None:
            self.vectors = self.vectors[keep]

    def to_dict(self) -> Dict:
        return {"ids": self.ids, "vectors": self.vectors.tolist() if self.vectors is not None else [], "metadata": self.metadata}

    @classmethod
    def from_dict(cls, data: Dict) -> "InMemoryVectorStore":
        store = cls()
        store.ids = data["ids"]
        store.metadata = data["metadata"]
        if data["vectors"]:
            store.vectors = np.array(data["vectors"], dtype=np.float32)
        return store


# ============================================================================
# RERANKER
# ============================================================================

class Reranker(ABC):
    @abstractmethod
    def rerank(self, query: str, documents: List[str], top_k: int = 10) -> List[Tuple[int, float]]: pass


class BGEReranker(Reranker):
    """Local reranker using BGE-Reranker-v2."""

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3", device: str = "cpu"):
        self.model_name = model_name
        self.device = device
        self._model = None

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(self.model_name, device=self.device)

    def rerank(self, query: str, documents: List[str], top_k: int = 10) -> List[Tuple[int, float]]:
        self._load_model()
        if not documents:
            return []
        pairs = [[query, doc] for doc in documents]
        scores = self._model.predict(pairs)
        scored = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return [(i, float(s)) for i, s in scored[:top_k]]


class NoOpReranker(Reranker):
    def rerank(self, query: str, documents: List[str], top_k: int = 10) -> List[Tuple[int, float]]:
        return [(i, 1.0 - i * 0.01) for i in range(min(top_k, len(documents)))]


# ============================================================================
# HYBRID RETRIEVER
# ============================================================================

@dataclass
class RetrievalResult:
    """Single retrieval result with scores."""
    chunk: CodeChunk
    dense_score: float
    sparse_score: float
    rerank_score: float
    final_score: float


class HybridRetriever:
    """
    Main hybrid retrieval engine combining dense + sparse + reranking.
    Target latency: <500ms for 10k chunks
    """

    def __init__(
        self,
        embedder: EmbeddingProvider,
        vector_store: VectorStore,
        bm25_index: BM25Index,
        reranker: Optional[Reranker] = None,
        dense_weight: float = 0.6,
        rrf_k: int = 60,
    ):
        self.embedder = embedder
        self.vector_store = vector_store
        self.bm25_index = bm25_index
        self.reranker = reranker or NoOpReranker()
        self.dense_weight = dense_weight
        self.rrf_k = rrf_k
        self.chunks: Dict[str, CodeChunk] = {}

    def index_chunks(self, chunks: List[CodeChunk], batch_size: int = 32, progress_callback: Optional[callable] = None):
        if not chunks:
            return

        for chunk in chunks:
            self.chunks[chunk.id] = chunk

        # Prepare texts with context
        texts = []
        for chunk in chunks:
            parts = []
            if chunk.parent_class:
                parts.append(f"class {chunk.parent_class}")
            if chunk.signature:
                parts.append(chunk.signature)
            if chunk.docstring:
                parts.append(chunk.docstring)
            context = " | ".join(parts)
            texts.append(f"{context}\n\n{chunk.text}" if context else chunk.text)

        # Generate embeddings
        all_embeddings = []
        total = len(texts)
        for i in range(0, total, batch_size):
            batch = texts[i:i + batch_size]
            all_embeddings.extend(self.embedder.embed(batch))
            if progress_callback:
                progress_callback(min(i + batch_size, total), total)

        # Add to stores
        ids = [c.id for c in chunks]
        metadata = [{"file_path": c.file_path, "name": c.name, "chunk_type": c.chunk_type, "start_line": c.start_line, "end_line": c.end_line, "parent_class": c.parent_class} for c in chunks]
        self.vector_store.add(ids, all_embeddings, metadata)
        self.bm25_index.build(texts)
        logger.info(f"Indexed {len(chunks)} chunks")

    def search(
        self,
        query: str,
        top_k: int = 10,
        dense_top_k: int = 50,
        sparse_top_k: int = 50,
        rerank: bool = True,
        file_filter: Optional[List[str]] = None,
    ) -> List[RetrievalResult]:
        # 1. Dense search
        query_embedding = self.embedder.embed_query(query)
        dense_results = self.vector_store.search(query_embedding, top_k=dense_top_k)

        # 2. Sparse search
        sparse_results = self.bm25_index.search(query, top_k=sparse_top_k)

        # 3. Build score mappings
        dense_scores: Dict[str, float] = {id_: score for id_, score, _ in dense_results if id_ in self.chunks}
        sparse_scores: Dict[str, float] = {}
        chunk_ids = list(self.chunks.keys())
        for doc_idx, score in sparse_results:
            if doc_idx < len(chunk_ids):
                sparse_scores[chunk_ids[doc_idx]] = score

        # 4. RRF Fusion
        all_ids = set(dense_scores.keys()) | set(sparse_scores.keys())
        if file_filter:
            file_filter_set = set(file_filter)
            all_ids = {id_ for id_ in all_ids if self.chunks[id_].file_path in file_filter_set}

        fused_scores: Dict[str, Tuple[float, float, float]] = {}
        for id_ in all_ids:
            dense_rank = self._get_rank(id_, dense_results) or (dense_top_k + 1)
            sparse_rank = self._get_rank_from_idx(id_, sparse_results, chunk_ids) or (sparse_top_k + 1)
            dense_rrf = 1.0 / (self.rrf_k + dense_rank)
            sparse_rrf = 1.0 / (self.rrf_k + sparse_rank)
            fused = self.dense_weight * dense_rrf + (1 - self.dense_weight) * sparse_rrf
            fused_scores[id_] = (dense_scores.get(id_, 0.0), sparse_scores.get(id_, 0.0), fused)

        sorted_ids = sorted(fused_scores.keys(), key=lambda x: fused_scores[x][2], reverse=True)
        rerank_candidates = sorted_ids[:min(len(sorted_ids), top_k * 3)]

        # 5. Rerank
        if rerank and rerank_candidates:
            candidate_texts = [self.chunks[id_].text for id_ in rerank_candidates]
            reranked = self.reranker.rerank(query, candidate_texts, top_k=top_k)
            results = []
            for orig_idx, rerank_score in reranked:
                chunk_id = rerank_candidates[orig_idx]
                chunk = self.chunks[chunk_id]
                dense_s, sparse_s, _ = fused_scores[chunk_id]
                results.append(RetrievalResult(chunk=chunk, dense_score=dense_s, sparse_score=sparse_s, rerank_score=rerank_score, final_score=rerank_score))
            return results

        return [RetrievalResult(chunk=self.chunks[id_], dense_score=fused_scores[id_][0], sparse_score=fused_scores[id_][1], rerank_score=0.0, final_score=fused_scores[id_][2]) for id_ in sorted_ids[:top_k]]

    def _get_rank(self, id_: str, results: List[Tuple[str, float, Any]]) -> Optional[int]:
        for i, (rid, _, _) in enumerate(results):
            if rid == id_:
                return i + 1
        return None

    def _get_rank_from_idx(self, id_: str, results: List[Tuple[int, float]], chunk_ids: List[str]) -> Optional[int]:
        for i, (doc_idx, _) in enumerate(results):
            if doc_idx < len(chunk_ids) and chunk_ids[doc_idx] == id_:
                return i + 1
        return None

    def save(self, path: Path):
        data = {"chunks": {id_: c.to_dict() for id_, c in self.chunks.items()}, "bm25_index": self.bm25_index.to_dict(), "dense_weight": self.dense_weight, "rrf_k": self.rrf_k}
        if isinstance(self.vector_store, InMemoryVectorStore):
            data["vector_store"] = self.vector_store.to_dict()
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Path, embedder: EmbeddingProvider, reranker: Optional[Reranker] = None, vector_store: Optional[VectorStore] = None) -> "HybridRetriever":
        data = json.loads(path.read_text(encoding="utf-8"))
        bm25_index = BM25Index.from_dict(data["bm25_index"])
        if vector_store is None and "vector_store" in data:
            vector_store = InMemoryVectorStore.from_dict(data["vector_store"])
        elif vector_store is None:
            vector_store = InMemoryVectorStore()
        retriever = cls(embedder=embedder, vector_store=vector_store, bm25_index=bm25_index, reranker=reranker, dense_weight=data.get("dense_weight", 0.6), rrf_k=data.get("rrf_k", 60))
        retriever.chunks = {id_: CodeChunk.from_dict(c) for id_, c in data["chunks"].items()}
        return retriever
