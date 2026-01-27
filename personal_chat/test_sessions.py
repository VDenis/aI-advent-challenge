"""Тестовый скрипт для проверки персонализации и истории."""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from personal_chat.config import load_app_config, load_profile
from personal_chat.history import HistoryManager
from personal_chat.chat import ChatClient

console = Console()


def run_session(
    chat_client: ChatClient,
    history_manager: HistoryManager,
    config,
    questions: list[str],
    session_name: str,
    continue_last: bool = False
) -> None:
    """Запускает тестовую сессию с вопросами."""

    console.print(Panel(f"[bold cyan]{session_name}[/bold cyan]", expand=False))

    # Начинаем или продолжаем разговор
    if continue_last:
        conversation = history_manager.get_latest_conversation()
        if conversation:
            console.print(f"[green]Продолжаем разговор:[/green] {conversation.title}")
            console.print(f"[dim]Сообщений в истории: {len(conversation.messages)}[/dim]\n")
        else:
            conversation = history_manager.start_new_conversation()
    else:
        conversation = history_manager.start_new_conversation()
        console.print("[green]Начат новый разговор[/green]\n")

    history_manager.current_conversation = conversation

    for i, question in enumerate(questions, 1):
        console.print(f"[bold blue]Вопрос {i}:[/bold blue] {question}")

        # Получаем историю для контекста
        history = conversation.get_messages_for_api(config.history_max_messages)

        # Добавляем вопрос
        conversation.add_message("user", question)

        try:
            # Получаем ответ
            response = chat_client.send_message(question, history)

            # Добавляем ответ в историю
            conversation.add_message("assistant", response)

            # Выводим ответ (обрезаем если длинный)
            display_response = response[:500] + "..." if len(response) > 500 else response
            console.print(f"[bold green]Ответ:[/bold green] {display_response}\n")

        except Exception as e:
            console.print(f"[red]Ошибка:[/red] {e}\n")
            conversation.add_message("assistant", f"[Ошибка: {e}]")

    # Сохраняем разговор
    conversation.auto_title()
    history_manager.save_conversation(conversation)
    console.print(f"[cyan]Разговор сохранён: {conversation.id}[/cyan]")
    console.print(f"[cyan]Всего сообщений: {len(conversation.messages)}[/cyan]\n")


def main():
    """Основной тест."""

    console.print(Panel(
        "[bold]Тестирование Personal Chat[/bold]\n"
        "Проверка персонализации и истории разговоров",
        border_style="cyan"
    ))

    # Загружаем конфиг
    config = load_app_config()
    profile = config.profile

    console.print(f"\n[cyan]Профиль:[/cyan] {profile.name}")
    console.print(f"[cyan]Профессия:[/cyan] {profile.profession}")
    console.print(f"[cyan]Модель:[/cyan] {config.gigachat_model}\n")

    # Инициализируем клиент
    try:
        chat_client = ChatClient(config)
    except ValueError as e:
        console.print(f"[red]Ошибка:[/red] {e}")
        return

    # Проверяем подключение
    console.print("[cyan]Проверяю подключение...[/cyan]")
    if not chat_client.test_connection():
        console.print("[red]Не удалось подключиться к GigaChat[/red]")
        return
    console.print("[green]Подключение OK[/green]\n")

    # Очищаем старую историю для чистого теста
    history_manager = HistoryManager()
    history_manager.clear_all_history()
    console.print("[yellow]История очищена для чистого теста[/yellow]\n")

    # === СЕССИЯ 1: Проверка персонализации ===
    session1_questions = [
        "Привет! Как меня зовут?",
        "Какая у меня профессия?",
        "Какие технологии я использую в работе?",
        "Над какими проектами я сейчас работаю?",
        "Какой стиль ответов я предпочитаю?",
        "Посоветуй книгу по машинному обучению для практика",
        "Как лучше организовать структуру MCP сервера на Python?",
        "Напиши короткий пример использования GigaChat API",
        "Какие у меня цели?",
        "Запомни: мой любимый редактор - VS Code с Vim mode",
    ]

    run_session(
        chat_client, history_manager, config,
        session1_questions,
        "СЕССИЯ 1: Проверка персонализации",
        continue_last=False
    )

    console.print(Panel("[yellow]Пауза между сессиями...[/yellow]", expand=False))

    # === СЕССИЯ 2: Проверка истории ===
    session2_questions = [
        "Напомни, о чём мы говорили?",
        "Какой редактор я упоминал?",
        "Ты показывал пример кода - про что он был?",
        "Какую книгу ты рекомендовал?",
        "Вернёмся к MCP серверам - что ты советовал по структуре?",
        "Учитывая мои проекты, что мне изучить следующим?",
        "Напиши улучшенную версию примера GigaChat из нашего разговора",
        "Как мои навыки помогут в достижении моих целей?",
        "Составь план изучения на неделю под мой профиль",
        "Спасибо за помощь! Подведи итог нашего общения",
    ]

    run_session(
        chat_client, history_manager, config,
        session2_questions,
        "СЕССИЯ 2: Проверка истории",
        continue_last=True
    )

    # Итоговая статистика
    conversations = history_manager.list_conversations()

    table = Table(title="Итоги тестирования", show_header=True, header_style="bold green")
    table.add_column("Метрика")
    table.add_column("Значение")

    table.add_row("Разговоров", str(len(conversations)))
    if conversations:
        table.add_row("Сообщений всего", str(conversations[0]["message_count"]))
        table.add_row("ID разговора", conversations[0]["id"])

    console.print(table)
    console.print("\n[bold green]Тестирование завершено![/bold green]")


if __name__ == "__main__":
    main()
