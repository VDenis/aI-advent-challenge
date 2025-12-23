from __future__ import annotations

import logging
from typing import Any, Iterable, List, Sequence, Dict

import requests

OLLAMA_BASE_URL = "http://localhost:11434/api"

def _post_ollama(endpoint: str, payload: Dict[str, Any], timeout: int) -> Any:
    url = f"{OLLAMA_BASE_URL}/{endpoint}"
    try:
        response = requests.post(url, json=payload, timeout=timeout)
    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(
            f"Ollama недоступна по адресу {url}. Запустите `ollama serve` и проверьте порт 11434."
        ) from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"Ошибка запроса к Ollama: {exc}") from exc

    if response.status_code != 200:
        raise RuntimeError(
            f"Запрос к Ollama ({endpoint}) завершился с кодом {response.status_code}. "
            f"Ответ: {response.text}"
        )
    return response.json()


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
        
        payload = {"model": model, "input": batch}
        data = _post_ollama("embed", payload, timeout)

        if "embeddings" in data:
            embeddings = data["embeddings"]
        elif "embedding" in data:
            if len(batch) != 1:
                raise RuntimeError("Ollama вернула один embedding для батча >1.")
            embeddings = [data["embedding"]]
        else:
            raise RuntimeError("Некорректный ответ Ollama: нет поля embedding/embeddings.")

        if len(embeddings) != len(batch):
            raise RuntimeError(
                f"Число эмбеддингов ({len(embeddings)}) не совпадает с числом запросов ({len(batch)})."
            )
        batched_embeddings.extend(embeddings)

    return batched_embeddings


def generate_completion(
    prompt: str, model: str, system: str | None = None, stream: bool = False, timeout: int = 120
) -> str:
    """Generate a completion for a single prompt."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": stream,
    }
    if system:
        payload["system"] = system

    # NOTE: For this simple implementation, we assume stream=False.
    # If stream=True, we'd need to yield lines.
    data = _post_ollama("generate", payload, timeout)
    return data.get("response", "")


def chat_completion(
    messages: List[Dict[str, str]], model: str, stream: bool = False, timeout: int = 120
) -> str:
    """Generate a chat completion from a list of messages."""
    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
    }
    data = _post_ollama("chat", payload, timeout)
    
    # Ollama chat response format: {"message": {"role": "assistant", "content": "..."}}
    msg = data.get("message", {})
    return msg.get("content", "")





