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

    search_parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Минимальный порог схожести (0.0 - 1.0, по умолчанию без фильтра)",
    )

    ask_parser = subparsers.add_parser("ask", help="Задать вопрос агенту")
    _add_shared_args(ask_parser)
    ask_parser.add_argument("query", help="Текст вопроса")
    ask_parser.add_argument(
        "--gen-model",
        default="llama3",
        help="Модель генерации (по умолчанию llama3)",
    )
    ask_parser.add_argument(
        "--mode",
        choices=["rag", "no-rag", "compare"],
        default="compare",
        help="Режим работы: rag, no-rag, compare (по умолчанию compare)",
    )
    ask_parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Минимальный порог схожести (по умолчанию без фильтра)",
    )
    ask_parser.add_argument(
        "--rerank",
        action="store_true",
        help="Использовать LLM-реранкер для уточнения результатов",
    )

    yt_parser = subparsers.add_parser("youtube", help="Скачать субтитры с YouTube")
    yt_parser.add_argument("url", help="Ссылка на видео YouTube или ID")
    yt_parser.add_argument(
        "--lang",
        default="ru,en",
        help="Приоритет языков через запятую (по умолчанию ru,en)",
    )
    yt_parser.add_argument(
        "--output",
        default="./corpus/youtube",
        help="Куда сохранить файл (по умолчанию ./corpus/youtube)",
    )

    subparsers.add_parser("ensure-ollama", help="Проверить и запустить сервис Ollama")

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
        results = search_store(
            store_path=args.store, 
            query=args.query, 
            model=args.model, 
            k=args.k,
            threshold=args.threshold
        )
        _print_results(results)
    
    elif args.command == "ask":
        from rag.agent import Agent
        agent = Agent(args.store, embed_model=args.model, gen_model=args.gen_model)
        
        print(f"--- Mode: {args.mode} | Threshold: {args.threshold} | Rerank: {args.rerank} ---")
        if args.mode == "rag":
            ans, chunks = agent.answer_with_rag(args.query, threshold=args.threshold, rerank=args.rerank)
            print(f"\n[RAG Answer]\n{ans}")
            if args.verbose > 0:
                print("\n[Chunks used]")
                for i, c in enumerate(chunks, 1):
                    snippet = c.replace("\n", " ")[:200]
                    print(f"{i}. {snippet}...")
        
        elif args.mode == "no-rag":
            ans = agent.answer_no_rag(args.query)
            print(f"\n[No-RAG Answer]\n{ans}")
            
        elif args.mode == "compare":
            res = agent.compare(args.query, threshold=args.threshold, rerank=args.rerank)
            print(f"\n=> Question: {res.question}")
            print(f"\n[RAG Answer]\n{res.rag_answer}")
            print(f"\n[No-RAG Answer]\n{res.no_rag_answer}")
            print(f"\n[Judge's Conclusion]\n{res.conclusion}")

    elif args.command == "youtube":
        from rag.youtube import extract_video_id, get_transcript, save_transcript
        
        video_id = extract_video_id(args.url)
        if not video_id:
            logging.error("Некорректный URL видео: %s", args.url)
            return

        try:
            langs = args.lang.split(",")
            text = get_transcript(video_id, languages=langs)
            path = save_transcript(video_id, text, output_dir=args.output)
            print(f"Субтитры сохранены в: {path}")
            print(f"Теперь запустите `ingest`, чтобы добавить этот файл в индекс.")
        except Exception as exc:
            logging.error("Ошибка при скачивании субтитров: %s", exc)

    elif args.command == "ensure-ollama":
        from rag.ollama_client import is_ollama_running, start_ollama_service
        
        if is_ollama_running():
            print("Ollama уже запущена.")
        else:
            print("Ollama не запущена. Пытаюсь запустить...")
            if start_ollama_service():
                print("Ollama успешно запущена!")
            else:
                print("Не удалось запустить Ollama автоматически.")
                print("Пожалуйста, запустите приложение Ollama или выполните `ollama serve` вручную.")

if __name__ == "__main__":
    main()

