# local-rag-indexer

Локальный RAG на базе FAISS + Ollama (embeddings & generation).

## Быстрый старт

1. Подготовка окружения:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -e .
   ```
2. Запусти/проверь Ollama:
   ```bash
   python -m rag ensure-ollama
   # embeddings по умолчанию: mxbai-embed-large (подтяните: ollama pull mxbai-embed-large)
   ```
3. Инжест корпуса (md/txt/py) в индекс:
   ```bash
   python -m rag ingest --corpus ./corpus --store ./store
   ```
4. Поиск или вопрос агенту:
   ```bash
   python -m rag search "ваш запрос" --k 3 --threshold 0.5
   python -m rag ask "Ваш вопрос" --mode rag --rerank --threshold 0.4 -v
   ```

## Команды

- `python -m rag ingest --corpus ./corpus --store ./store`
  - `--chunk-size`/`--overlap`/`--batch-size` — настройка чанкинга и батча.
- `python -m rag search "q"` — векторный поиск (`--k`, `--threshold`).
- `python -m rag ask "q"` — режимы `rag` / `no-rag` / `compare`, флаг `--rerank` включает LLM-реранкер, `--gen-model` задаёт генеративную модель (по умолчанию `llama3`).
- `python -m rag youtube <url>` — скачать субтитры YouTube (`--lang ru,en`, сохраняются в `./corpus/youtube`), затем прогнать `ingest`.
- `python -m rag ensure-ollama` — проверить/поднять Ollama сервис (macOS: `open -a Ollama`, fallback `ollama serve`).

## Технические детали
- Индекс: FAISS `IndexFlatIP` с L2-нормировкой.
- Реранкер: дополнительный LLM-проход для фильтрации чанков.
- Чанкинг: фиксированный размер с перекрытием (параметры `--chunk-size`/`--overlap`).
