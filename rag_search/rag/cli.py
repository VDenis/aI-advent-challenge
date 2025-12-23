from __future__ import annotations

import argparse
import logging
from typing import Iterable, Tuple

from rag.index_faiss import ChunkRecord, ingest_corpus, search_store


def _configure_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(message)s")


def _add_shared_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--model",
        default="mxbai-embed-large",
        help="Имя модели Ollama embeddings (по умолчанию mxbai-embed-large)",
    )
    parser.add_argument(
        "--store",
        default="./store",
        help="Путь к каталогу с индексом и метаданными (по умолчанию ./store)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rag", description="Local RAG (FAISS + Ollama)")
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Уровень логирования: -v (INFO), -vv (DEBUG)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="Индексировать корпус")
    _add_shared_args(ingest_parser)
    ingest_parser.add_argument(
        "--corpus",
        default="./corpus",
        help="Каталог с исходными файлами (.md/.txt/.py) (по умолчанию ./corpus)",
    )
    ingest_parser.add_argument(
        "--chunk-size",
        type=int,
        default=900,
        help="Размер чанка (символы, по умолчанию 900)",
    )
    ingest_parser.add_argument(
        "--overlap",
        type=int,
        default=150,
        help="Перекрытие чанков (символы, по умолчанию 150)",
    )
    ingest_parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Размер батча для вызова Ollama (по умолчанию 32)",
    )

    search_parser = subparsers.add_parser("search", help="Поиск по индексу")
    _add_shared_args(search_parser)
    search_parser.add_argument("query", help="Текст запроса")
    search_parser.add_argument(
        "--k",
        type=int,
        default=5,
        help="Сколько результатов вернуть (по умолчанию 5)",
    )

    return parser


def _print_results(results: Iterable[Tuple[float, ChunkRecord]]) -> None:
    found = False
    for score, rec in results:
        found = True
        snippet = rec.text.replace("\n", " ")[:300]
        print(f"{score:.4f} | {rec.source_path} [{rec.start_char}:{rec.end_char}] | {snippet}")
    if not found:
        print("Результатов нет.")


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)

    if args.command == "ingest":
        ingest_corpus(
            corpus_path=args.corpus,
            store_path=args.store,
            model=args.model,
            chunk_size=args.chunk_size,
            overlap=args.overlap,
            batch_size=args.batch_size,
        )
    elif args.command == "search":
        results = search_store(store_path=args.store, query=args.query, model=args.model, k=args.k)
        _print_results(results)


if __name__ == "__main__":
    main()

