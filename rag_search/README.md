# local-rag-indexer

Локальный RAG на базе FAISS + Ollama embeddings.

## Виртуальное окружение (рекомендуется)
```bash
python -m venv .venv
source .venv/bin/activate  # или .venv\Scripts\activate в Windows
pip install -e .
```

## Предварительно
- Установите зависимости: `pip install .` или `pip install -r <(python -m pip freeze)` после активации окружения.
- Запустите Ollama: `ollama serve` (порт 11434 по умолчанию).
- Подтяните модель эмбеддингов: `ollama pull mxbai-embed-large`.

## Команды
- Инжест корпуса:  
  `python -m rag ingest --corpus ./corpus --store ./store --model mxbai-embed-large`

- Поиск:  
  `python -m rag search "your query text" --k 5 --store ./store --model mxbai-embed-large`

## Примечания
- Корпус: файлы `.md`, `.txt`, `.py` читаются как plain text (UTF-8; при ошибке файл пропускается с предупреждением).
- При новом ingest каталог `store` перезаписывается полностью.
- Индекс: FAISS `IndexFlatIP` с L2-нормировкой векторов; метаданные в `store/meta.jsonl`.

