"""Главный модуль CLI персонализированного чата."""

import sys
import os
from pathlib import Path

# Добавляем корень проекта в путь для импорта
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich import print as rprint

from personal_chat.config import (
    load_app_config,
    save_app_config,
    save_profile,
    load_profile,
    create_example_profile,
    UserProfile,
    get_profile_path,
)
from personal_chat.history import HistoryManager, Conversation
from personal_chat.chat import ChatClient

console = Console()

# Проверяем доступность голосового модуля
_voice_available = False
try:
    import sounddevice  # noqa: F401
    import whisper  # noqa: F401
    _voice_available = True
except ImportError:
    pass


class PersonalChatCLI:
    """CLI для персонализированного чата."""

    def __init__(self):
        self.config = load_app_config()
        self.history_manager = HistoryManager()
        self.chat_client = None
        self.current_conversation = None
        self.streaming = True
        self.voice_enabled = _voice_available
        self.voice_duration = 5.0
        self.voice_model = "base"

    def print_welcome(self) -> None:
        """Выводит приветственное сообщение."""
        profile = self.config.profile

        welcome_text = f"""
[bold cyan]Personal Chat[/bold cyan] - Персонализированный ИИ-ассистент

[bold]Пользователь:[/bold] {profile.name}
[bold]Модель:[/bold] {self.config.gigachat_model}
[bold]История:[/bold] {'включена' if self.config.history_enabled else 'выключена'}

[dim]Команды:[/dim]
  /help     - справка по командам
  /new      - начать новый разговор
  /history  - показать историю разговоров
  /continue - продолжить последний разговор
  /profile  - показать/редактировать профиль
  /voice    - вкл/выкл голосовой ввод (Enter = запись)
  /clear    - очистить экран
  /exit     - выйти
"""
        console.print(Panel(welcome_text, border_style="cyan"))

    def print_help(self) -> None:
        """Выводит справку по командам."""
        table = Table(title="Команды", show_header=True, header_style="bold cyan")
        table.add_column("Команда", style="cyan")
        table.add_column("Описание")

        commands = [
            ("/help", "Показать эту справку"),
            ("/new", "Начать новый разговор"),
            ("/history", "Показать список разговоров"),
            ("/continue [id]", "Продолжить разговор (последний или по ID)"),
            ("/profile", "Показать текущий профиль"),
            ("/profile edit", "Редактировать профиль"),
            ("/profile reset", "Сбросить профиль к примеру"),
            ("/models", "Показать доступные модели"),
            ("/model <name>", "Сменить модель"),
            ("/stream", "Переключить потоковый режим"),
            ("/voice", "Вкл/выкл голосовой ввод (Enter без текста = запись)"),
            ("/delete <id>", "Удалить разговор"),
            ("/clear", "Очистить экран"),
            ("/exit, /quit, /q", "Выйти из программы"),
        ]

        for cmd, desc in commands:
            table.add_row(cmd, desc)

        console.print(table)

    def init_chat_client(self) -> bool:
        """Инициализирует клиент чата."""
        try:
            self.chat_client = ChatClient(self.config)
            return True
        except ValueError as e:
            console.print(f"[red]Ошибка:[/red] {e}")
            console.print(
                "\n[yellow]Подсказка:[/yellow] Установите переменную окружения "
                "GIGACHAT_CREDENTIALS или добавьте её в .env файл."
            )
            return False

    def handle_command(self, command: str) -> bool:
        """Обрабатывает команду. Возвращает False для выхода."""
        parts = command.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd in ("/exit", "/quit", "/q"):
            self.save_current_conversation()
            console.print("[cyan]До свидания![/cyan]")
            return False

        elif cmd == "/help":
            self.print_help()

        elif cmd == "/clear":
            console.clear()

        elif cmd == "/new":
            self.start_new_conversation()

        elif cmd == "/history":
            self.show_history()

        elif cmd == "/continue":
            self.continue_conversation(args if args else None)

        elif cmd == "/profile":
            if args == "edit":
                self.edit_profile()
            elif args == "reset":
                self.reset_profile()
            else:
                self.show_profile()

        elif cmd == "/models":
            self.show_models()

        elif cmd == "/model":
            if args:
                self.change_model(args)
            else:
                console.print(f"[cyan]Текущая модель:[/cyan] {self.config.gigachat_model}")

        elif cmd == "/stream":
            self.streaming = not self.streaming
            console.print(f"[cyan]Потоковый режим:[/cyan] {'включён' if self.streaming else 'выключен'}")

        elif cmd == "/voice":
            if not _voice_available:
                console.print("[red]Голосовой модуль недоступен.[/red] Установите: pip install openai-whisper sounddevice numpy")
                return True
            self.voice_enabled = not self.voice_enabled
            console.print(f"[cyan]Голосовой ввод:[/cyan] {'включён (Enter без текста = запись)' if self.voice_enabled else 'выключен'}")

        elif cmd == "/delete":
            if args:
                self.delete_conversation(args)
            else:
                console.print("[yellow]Укажите ID разговора для удаления[/yellow]")

        else:
            console.print(f"[yellow]Неизвестная команда:[/yellow] {cmd}. Введите /help для справки.")

        return True

    def start_new_conversation(self) -> None:
        """Начинает новый разговор."""
        self.save_current_conversation()
        self.current_conversation = self.history_manager.start_new_conversation()
        console.print("[green]Начат новый разговор[/green]")

    def continue_conversation(self, conv_id: str = None) -> None:
        """Продолжает существующий разговор."""
        self.save_current_conversation()

        if conv_id:
            conversation = self.history_manager.load_conversation(conv_id)
        else:
            conversation = self.history_manager.get_latest_conversation()

        if conversation:
            self.current_conversation = conversation
            self.history_manager.current_conversation = conversation
            console.print(f"[green]Продолжаем разговор:[/green] {conversation.title}")

            # Показываем последние сообщения
            if conversation.messages:
                console.print("\n[dim]Последние сообщения:[/dim]")
                for msg in conversation.messages[-4:]:
                    role = "[bold blue]Вы[/bold blue]" if msg.role == "user" else "[bold green]Ассистент[/bold green]"
                    content = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
                    console.print(f"  {role}: {content}")
                console.print()
        else:
            console.print("[yellow]Нет сохранённых разговоров. Начинаем новый.[/yellow]")
            self.start_new_conversation()

    def show_history(self) -> None:
        """Показывает историю разговоров."""
        conversations = self.history_manager.list_conversations(limit=10)

        if not conversations:
            console.print("[yellow]История пуста[/yellow]")
            return

        table = Table(title="История разговоров", show_header=True, header_style="bold cyan")
        table.add_column("ID", style="cyan")
        table.add_column("Заголовок")
        table.add_column("Сообщений", justify="right")
        table.add_column("Обновлён")

        for conv in conversations:
            updated = conv["updated_at"][:10]
            table.add_row(conv["id"], conv["title"][:40], str(conv["message_count"]), updated)

        console.print(table)
        console.print("\n[dim]Используйте /continue <id> для продолжения разговора[/dim]")

    def delete_conversation(self, conv_id: str) -> None:
        """Удаляет разговор."""
        if self.history_manager.delete_conversation(conv_id):
            console.print(f"[green]Разговор {conv_id} удалён[/green]")
        else:
            console.print(f"[red]Разговор {conv_id} не найден[/red]")

    def show_profile(self) -> None:
        """Показывает текущий профиль."""
        profile = self.config.profile

        table = Table(title=f"Профиль: {profile.name}", show_header=False, border_style="cyan")
        table.add_column("Поле", style="cyan")
        table.add_column("Значение")

        table.add_row("Имя", profile.name)
        table.add_row("Язык", profile.language)
        table.add_row("Стиль общения", profile.communication_style)
        table.add_row("Профессия", profile.profession or "-")
        table.add_row("Контекст работы", profile.work_context or "-")
        table.add_row("Навыки", ", ".join(profile.skills) if profile.skills else "-")
        table.add_row("Интересы", ", ".join(profile.interests) if profile.interests else "-")
        table.add_row("Хобби", ", ".join(profile.hobbies) if profile.hobbies else "-")
        table.add_row("Любимые темы", ", ".join(profile.favorite_topics) if profile.favorite_topics else "-")
        table.add_row("Привычки", ", ".join(profile.habits) if profile.habits else "-")
        table.add_row("Цели", ", ".join(profile.goals) if profile.goals else "-")
        table.add_row("Проекты", ", ".join(profile.current_projects) if profile.current_projects else "-")
        table.add_row("Часовой пояс", profile.timezone)
        table.add_row("Локация", profile.location or "-")

        console.print(table)
        console.print(f"\n[dim]Файл профиля: {get_profile_path()}[/dim]")

    def edit_profile(self) -> None:
        """Редактирует профиль интерактивно."""
        profile = self.config.profile
        console.print("[cyan]Редактирование профиля[/cyan] (Enter для пропуска)\n")

        def ask(prompt: str, default: str) -> str:
            result = Prompt.ask(prompt, default=default)
            return result if result else default

        def ask_list(prompt: str, default: list) -> list:
            default_str = ", ".join(default) if default else ""
            result = Prompt.ask(prompt, default=default_str)
            if result:
                return [x.strip() for x in result.split(",") if x.strip()]
            return default

        profile.name = ask("Имя", profile.name)
        profile.language = ask("Язык", profile.language)
        profile.communication_style = ask("Стиль (формальный/дружелюбный/краткий)", profile.communication_style)
        profile.profession = ask("Профессия", profile.profession)
        profile.work_context = ask("Контекст работы", profile.work_context)
        profile.skills = ask_list("Навыки (через запятую)", profile.skills)
        profile.interests = ask_list("Интересы", profile.interests)
        profile.hobbies = ask_list("Хобби", profile.hobbies)
        profile.favorite_topics = ask_list("Любимые темы", profile.favorite_topics)
        profile.habits = ask_list("Привычки", profile.habits)
        profile.goals = ask_list("Цели", profile.goals)
        profile.current_projects = ask_list("Текущие проекты", profile.current_projects)
        profile.timezone = ask("Часовой пояс", profile.timezone)
        profile.location = ask("Локация", profile.location)
        profile.notes = ask("Дополнительные заметки", profile.notes)

        save_profile(profile)
        self.config.profile = profile

        if self.chat_client:
            self.chat_client.update_profile(profile)

        console.print("\n[green]Профиль сохранён![/green]")

    def reset_profile(self) -> None:
        """Сбрасывает профиль к примеру."""
        create_example_profile()
        example_path = Path(__file__).parent / "profile_example.yaml"
        profile = load_profile(example_path)
        save_profile(profile)
        self.config.profile = profile

        if self.chat_client:
            self.chat_client.update_profile(profile)

        console.print("[green]Профиль сброшен к примеру[/green]")

    def show_models(self) -> None:
        """Показывает доступные модели."""
        if not self.chat_client:
            console.print("[yellow]Клиент не инициализирован[/yellow]")
            return

        models = self.chat_client.get_models()
        console.print("[cyan]Доступные модели:[/cyan]")
        for model in models:
            marker = " (текущая)" if model == self.config.gigachat_model else ""
            console.print(f"  - {model}{marker}")

    def change_model(self, model_name: str) -> None:
        """Меняет модель."""
        self.config.gigachat_model = model_name
        save_app_config(self.config)

        # Переинициализируем клиент
        if self.init_chat_client():
            console.print(f"[green]Модель изменена на:[/green] {model_name}")

    def save_current_conversation(self) -> None:
        """Сохраняет текущий разговор."""
        if self.current_conversation and self.current_conversation.messages:
            self.current_conversation.auto_title()
            self.history_manager.save_conversation(self.current_conversation)

    def send_message(self, user_message: str) -> None:
        """Отправляет сообщение и выводит ответ."""
        if not self.chat_client:
            console.print("[red]Клиент не инициализирован[/red]")
            return

        if not self.current_conversation:
            self.start_new_conversation()

        # Получаем историю для контекста
        history = self.current_conversation.get_messages_for_api(self.config.history_max_messages)

        # Добавляем сообщение пользователя
        self.current_conversation.add_message("user", user_message)

        console.print()

        try:
            if self.streaming:
                # Потоковый вывод
                console.print("[bold green]Ассистент:[/bold green] ", end="")
                full_response = ""
                for chunk in self.chat_client.send_message_stream(user_message, history):
                    console.print(chunk, end="")
                    full_response += chunk
                console.print("\n")
            else:
                # Обычный вывод
                with console.status("[cyan]Думаю...[/cyan]"):
                    full_response = self.chat_client.send_message(user_message, history)
                console.print("[bold green]Ассистент:[/bold green]")
                console.print(Markdown(full_response))
                console.print()

            # Сохраняем ответ
            self.current_conversation.add_message("assistant", full_response)

            # Периодически сохраняем разговор
            if len(self.current_conversation.messages) % 4 == 0:
                self.save_current_conversation()

        except Exception as e:
            console.print(f"\n[red]Ошибка при отправке:[/red] {e}")

    def _voice_record(self) -> str:
        """Записывает голос и возвращает распознанный текст."""
        try:
            from personal_chat.voice import record_audio, recognize

            console.print(f"[bold magenta]Говорите... ({self.voice_duration} сек)[/bold magenta]")
            audio = record_audio(duration=self.voice_duration)
            console.print("[dim]Распознаю...[/dim]")
            text = recognize(audio, model_name=self.voice_model, language="ru")
            if text:
                console.print(f"[bold blue]Вы (голос):[/bold blue] {text}")
            else:
                console.print("[yellow]Не удалось распознать речь[/yellow]")
            return text
        except Exception as e:
            console.print(f"[red]Ошибка голосового ввода:[/red] {e}")
            return ""

    def run(self) -> None:
        """Запускает CLI."""
        self.print_welcome()

        # Инициализируем клиент
        if not self.init_chat_client():
            return

        # Проверяем подключение
        with console.status("[cyan]Проверяю подключение к GigaChat...[/cyan]"):
            if not self.chat_client.test_connection():
                console.print("[red]Не удалось подключиться к GigaChat API[/red]")
                return

        console.print("[green]Подключение установлено![/green]\n")

        # Предлагаем продолжить последний разговор
        latest = self.history_manager.get_latest_conversation()
        if latest and latest.messages:
            choice = Prompt.ask(
                f"Продолжить последний разговор ({latest.title[:30]}...)?",
                choices=["y", "n"],
                default="y",
            )
            if choice == "y":
                self.continue_conversation()
            else:
                self.start_new_conversation()
        else:
            self.start_new_conversation()

        # Основной цикл
        while True:
            try:
                user_input = Prompt.ask("[bold blue]Вы[/bold blue]")

                if not user_input.strip():
                    if self.voice_enabled:
                        user_input = self._voice_record()
                        if not user_input:
                            continue
                    else:
                        continue

                if user_input.startswith("/"):
                    if not self.handle_command(user_input):
                        break
                else:
                    self.send_message(user_input)

            except KeyboardInterrupt:
                console.print("\n[yellow]Прервано. Используйте /exit для выхода.[/yellow]")

            except EOFError:
                self.save_current_conversation()
                console.print("\n[cyan]До свидания![/cyan]")
                break


def main():
    """Точка входа."""
    cli = PersonalChatCLI()
    cli.run()


if __name__ == "__main__":
    main()
