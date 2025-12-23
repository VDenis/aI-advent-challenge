from __future__ import annotations

import logging
from typing import Iterable, List, Sequence

import requests

OLLAMA_URL = "http://localhost:11434/api/embed"


def _post_ollama(inputs: Sequence[str], model: str, timeout: int) -> List[List[float]]:
    payload = {"model": model, "input": list(inputs)}
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(
            "Ollama недоступна. Запустите `ollama serve` и проверьте порт 11434."
        ) from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"Ошибка запроса к Ollama: {exc}") from exc

    if response.status_code != 200:
        raise RuntimeError(
            f"Запрос к Ollama завершился с кодом {response.status_code}. "
            "Убедитесь, что запущен `ollama serve` на порту 11434. "
            f"Ответ: {response.text}"
        )

    data = response.json()
    if "embeddings" in data:
        embeddings = data["embeddings"]
    elif "embedding" in data:
        if len(inputs) != 1:
            raise RuntimeError("Ollama вернула один embedding для батча >1.")
        embeddings = [data["embedding"]]
    else:
        raise RuntimeError("Некорректный ответ Ollama: нет поля embedding/embeddings.")

    if len(embeddings) != len(inputs):
        raise RuntimeError(
            f"Число эмбеддингов ({len(embeddings)}) не совпадает с числом запросов ({len(inputs)})."
        )
    return embeddings


def embed_texts(
    texts: Iterable[str], model: str, batch_size: int = 32, timeout: int = 120
) -> List[List[float]]:
    """Embed a sequence of texts using Ollama REST API in batches."""
    batched_embeddings: List[List[float]] = []
    texts_list = list(texts)
    if not texts_list:
        return batched_embeddings

    for start in range(0, len(texts_list), batch_size):
        batch = texts_list[start : start + batch_size]
        logging.info("Embedding batch %s-%s of %s", start + 1, start + len(batch), len(texts_list))
        embeddings = _post_ollama(batch, model=model, timeout=timeout)
        batched_embeddings.extend(embeddings)

    return batched_embeddings

