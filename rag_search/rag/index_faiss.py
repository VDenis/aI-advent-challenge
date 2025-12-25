from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

import faiss
import numpy as np
from tqdm import tqdm

from rag.chunking import chunk_text
from rag.ollama_client import embed_texts


SUPPORTED_EXTENSIONS = {".md", ".txt", ".py"}


@dataclass
class ChunkRecord:
    chunk_id: int
    source_path: str
    start_char: int
    end_char: int
    text: str


def _iter_corpus_files(corpus_path: str) -> Iterable[str]:
    for root, _, files in os.walk(corpus_path):
        for name in files:
            if os.path.splitext(name)[1].lower() in SUPPORTED_EXTENSIONS:
                yield os.path.join(root, name)


def _read_file(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        logging.warning("Пропуск файла (ошибка UTF-8): %s", path)
    except OSError as exc:
        logging.warning("Не удалось прочитать %s: %s", path, exc)
    return None


def _prepare_chunks(corpus_path: str, chunk_size: int, overlap: int) -> List[ChunkRecord]:
    records: List[ChunkRecord] = []
    chunk_id = 0
    paths = list(_iter_corpus_files(corpus_path))
    logging.info("Найдено файлов для инжеста: %s", len(paths))

    for file_path in tqdm(paths, desc="Чтение файлов"):
        text = _read_file(file_path)
        if text is None:
            continue

        rel_path = os.path.relpath(file_path, corpus_path)
        for span in chunk_text(text, chunk_size=chunk_size, overlap=overlap):
            records.append(
                ChunkRecord(
                    chunk_id=chunk_id,
                    source_path=rel_path,
                    start_char=span["start_char"],
                    end_char=span["end_char"],
                    text=span["text"],
                )
            )
            chunk_id += 1

    logging.info("Сформировано чанков: %s", len(records))
    return records


def _write_meta(meta_path: str, records: Sequence[ChunkRecord]) -> None:
    with open(meta_path, "w", encoding="utf-8") as f:
        for rec in records:
            json_line = {
                "id": rec.chunk_id,
                "source_path": rec.source_path,
                "start_char": rec.start_char,
                "end_char": rec.end_char,
                "text": rec.text,
            }
            f.write(json.dumps(json_line, ensure_ascii=False) + "\n")


def ingest_corpus(
    corpus_path: str,
    store_path: str,
    model: str,
    chunk_size: int = 900,
    overlap: int = 150,
    batch_size: int = 32,
) -> None:
    corpus_path = os.path.abspath(corpus_path)
    store_path = os.path.abspath(store_path)
    logging.info("Начинаем ingest. Корпус: %s. Store: %s", corpus_path, store_path)

    if not os.path.isdir(corpus_path):
        raise FileNotFoundError(f"Корпус не найден: {corpus_path}")

    records = _prepare_chunks(corpus_path, chunk_size=chunk_size, overlap=overlap)
    if not records:
        raise RuntimeError("Не удалось сформировать чанки: проверьте содержимое корпуса.")

    embeddings = embed_texts([r.text for r in records], model=model, batch_size=batch_size)
    if len(embeddings) != len(records):
        raise RuntimeError("Число эмбеддингов не совпадает с числом чанков.")

    vectors = np.array(embeddings, dtype="float32")
    faiss.normalize_L2(vectors)
    dim = vectors.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(vectors)
    logging.info("FAISS индекс построен: %s векторов, размерность %s", index.ntotal, dim)

    if os.path.exists(store_path):
        shutil.rmtree(store_path)
    os.makedirs(store_path, exist_ok=True)

    index_path = os.path.join(store_path, "index.faiss")
    meta_path = os.path.join(store_path, "meta.jsonl")
    faiss.write_index(index, index_path)
    _write_meta(meta_path, records)
    logging.info("Индекс сохранен: %s, метаданные: %s", index_path, meta_path)

    _self_check(store_path, model)


def _load_meta(meta_path: str) -> List[ChunkRecord]:
    records: List[ChunkRecord] = []
    with open(meta_path, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            records.append(
                ChunkRecord(
                    chunk_id=obj["id"],
                    source_path=obj["source_path"],
                    start_char=obj["start_char"],
                    end_char=obj["end_char"],
                    text=obj["text"],
                )
            )
    return records


def search_store(
    store_path: str, query: str, model: str, k: int = 5, threshold: float | None = None
) -> List[Tuple[float, ChunkRecord]]:
    store_path = os.path.abspath(store_path)
    index_path = os.path.join(store_path, "index.faiss")
    meta_path = os.path.join(store_path, "meta.jsonl")
    if not os.path.isfile(index_path) or not os.path.isfile(meta_path):
        raise FileNotFoundError(f"Store не найден: {store_path}")

    index = faiss.read_index(index_path)
    records = _load_meta(meta_path)
    if index.ntotal == 0:
        return []

    query_vecs = embed_texts([query], model=model, batch_size=1)
    if not query_vecs or len(query_vecs[0]) != index.d:
        raise RuntimeError("Размерность эмбеддинга запроса не совпадает с индексом.")

    query_np = np.array(query_vecs, dtype="float32")
    faiss.normalize_L2(query_np)

    top_k = min(k, index.ntotal)
    scores, ids = index.search(query_np, top_k)

    results: List[Tuple[float, ChunkRecord]] = []
    for score, idx in zip(scores[0], ids[0]):
        if idx == -1 or idx >= len(records):
            continue
        
        f_score = float(score)
        if threshold is not None and f_score < threshold:
            continue
            
        results.append((f_score, records[idx]))
    return results


def _self_check(store_path: str, model: str) -> None:
    """Lightweight sanity check after ingest."""
    meta_path = os.path.join(store_path, "meta.jsonl")
    if not os.path.isfile(meta_path):
        return
    records = _load_meta(meta_path)
    if not records:
        return

    sample_words = [w.strip(".,;:!?()[]{}\"'") for w in records[0].text.split()]
    sample_word = next((w for w in sample_words if len(w) >= 4), None)
    if not sample_word:
        return

    try:
        results = search_store(store_path, sample_word, model=model, k=1)
        if results:
            score, rec = results[0]
            logging.info(
                "Self-check: запрос '%s' вернул %s (score=%.4f)",
                sample_word,
                rec.source_path,
                score,
            )
    except Exception as exc:  # noqa: BLE001
        logging.warning("Self-check не удался: %s", exc)

