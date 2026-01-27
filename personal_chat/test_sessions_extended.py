"""Расширенный тест: 4 дополнительные сессии по 10 вопросов."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from personal_chat.config import load_app_config
from personal_chat.history import HistoryManager
from personal_chat.chat import ChatClient

console = Console()


def run_session(
    chat_client: ChatClient,
    history_manager: HistoryManager,
    config,
    questions: list[str],
    session_name: str,
    continue_last: bool = True
) -> None:
    """Запускает тестовую сессию."""
    console.print(Panel(f"[bold cyan]{session_name}[/bold cyan]", expand=False))

    if continue_last:
        conversation = history_manager.get_latest_conversation()
        if conversation:
            console.print(f"[green]Продолжаем:[/green] {conversation.title[:50]}...")
            console.print(f"[dim]Сообщений: {len(conversation.messages)}[/dim]\n")
        else:
            conversation = history_manager.start_new_conversation()
    else:
        conversation = history_manager.start_new_conversation()

    history_manager.current_conversation = conversation

    for i, question in enumerate(questions, 1):
        console.print(f"[bold blue]Вопрос {i}:[/bold blue] {question}")

        history = conversation.get_messages_for_api(config.history_max_messages)
        conversation.add_message("user", question)

        try:
            response = chat_client.send_message(question, history)
            conversation.add_message("assistant", response)

            display = response[:400] + "..." if len(response) > 400 else response
            console.print(f"[bold green]Ответ:[/bold green] {display}\n")

        except Exception as e:
            console.print(f"[red]Ошибка:[/red] {e}\n")
            conversation.add_message("assistant", f"[Ошибка: {e}]")

    conversation.auto_title()
    history_manager.save_conversation(conversation)
    console.print(f"[cyan]Сохранено. Всего сообщений: {len(conversation.messages)}[/cyan]\n")


def main():
    console.print(Panel(
        "[bold]Расширенное тестирование Personal Chat[/bold]\n"
        "4 сессии по 10 вопросов",
        border_style="cyan"
    ))

    config = load_app_config()
    profile = config.profile

    console.print(f"[cyan]Профиль:[/cyan] {profile.name}")
    console.print(f"[cyan]Модель:[/cyan] {config.gigachat_model}\n")

    try:
        chat_client = ChatClient(config)
    except ValueError as e:
        console.print(f"[red]Ошибка:[/red] {e}")
        return

    if not chat_client.test_connection():
        console.print("[red]Не удалось подключиться[/red]")
        return

    console.print("[green]Подключено![/green]\n")

    history_manager = HistoryManager()

    # === СЕССИЯ 3: Глубокие технические вопросы ===
    session3 = [
        "Расскажи про паттерн RAG - как его лучше реализовать?",
        "Какие есть способы оптимизации запросов к LLM?",
        "Как организовать кэширование ответов модели?",
        "Сравни подходы: fine-tuning vs prompt engineering",
        "Как реализовать streaming ответов в Python?",
        "Запомни: я использую poetry для управления зависимостями",
        "Какие метрики важны для оценки качества RAG системы?",
        "Как правильно обрабатывать ошибки при работе с API?",
        "Посоветуй архитектуру для multi-agent системы",
        "Как тестировать LLM приложения?",
    ]

    run_session(chat_client, history_manager, config, session3,
                "СЕССИЯ 3: Глубокие технические вопросы", continue_last=True)

    # === СЕССИЯ 4: Практические задачи ===
    session4 = [
        "Напиши декоратор для retry с exponential backoff",
        "Какой пакетный менеджер я использую? Напомни",
        "Создай pydantic модель для конфига чат-бота",
        "Напиши async функцию для batch запросов к API",
        "Как добавить логирование в существующий проект?",
        "Запомни: предпочитаю structlog вместо стандартного logging",
        "Напиши простой rate limiter на Python",
        "Как организовать конфиги для разных окружений?",
        "Создай CLI команду с помощью typer",
        "Напиши unit тест для async функции",
    ]

    run_session(chat_client, history_manager, config, session4,
                "СЕССИЯ 4: Практические задачи", continue_last=True)

    # === СЕССИЯ 5: Проверка долгосрочной памяти ===
    session5 = [
        "Перечисли всё, что ты запомнил обо мне из наших разговоров",
        "Какой редактор и пакетный менеджер я использую?",
        "Какую библиотеку логирования я предпочитаю?",
        "Напомни структуру MCP сервера, которую ты советовал",
        "Какие книги ты рекомендовал мне ранее?",
        "Запомни: мой GitHub username - denisxab",
        "Вернёмся к RAG - какие метрики ты упоминал?",
        "Какой декоратор ты писал в прошлой сессии?",
        "Учитывая всё что знаешь, предложи идею для pet-проекта",
        "Как мои текущие проекты связаны друг с другом?",
    ]

    run_session(chat_client, history_manager, config, session5,
                "СЕССИЯ 5: Проверка долгосрочной памяти", continue_last=True)

    # === СЕССИЯ 6: Финальная проверка ===
    session6 = [
        "Кто я и чем занимаюсь? Максимально подробно",
        "Какой у меня GitHub?",
        "Составь список всех моих предпочтений из разговоров",
        "Какой стек технологий мне подходит для нового проекта?",
        "Напиши README для моего Personal Chat проекта",
        "Что я должен изучить в первую очередь из твоих рекомендаций?",
        "Запомни: планирую добавить поддержку голосового ввода",
        "Создай чеклист для code review под мой стиль",
        "Подготовь elevator pitch для моего AI ассистента",
        "Подведи полный итог всех наших 6 сессий общения",
    ]

    run_session(chat_client, history_manager, config, session6,
                "СЕССИЯ 6: Финальная проверка", continue_last=True)

    # Итоговая статистика
    conversations = history_manager.list_conversations()

    table = Table(title="Итоги расширенного тестирования", show_header=True, header_style="bold green")
    table.add_column("Метрика")
    table.add_column("Значение")

    table.add_row("Всего разговоров", str(len(conversations)))
    if conversations:
        table.add_row("Сообщений в последнем", str(conversations[0]["message_count"]))

    console.print(table)
    console.print("\n[bold green]Расширенное тестирование завершено![/bold green]")


if __name__ == "__main__":
    main()
