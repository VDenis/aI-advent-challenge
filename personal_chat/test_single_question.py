"""Отправка одного вопроса в чат."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from personal_chat.config import load_app_config
from personal_chat.history import HistoryManager
from personal_chat.chat import ChatClient

console = Console()

def ask_question(question: str):
    config = load_app_config()
    chat_client = ChatClient(config)
    history_manager = HistoryManager()

    conversation = history_manager.get_latest_conversation()
    if conversation:
        console.print(f"[dim]Продолжаем разговор ({len(conversation.messages)} сообщений)[/dim]\n")
    else:
        conversation = history_manager.start_new_conversation()

    history_manager.current_conversation = conversation
    history = conversation.get_messages_for_api(config.history_max_messages)

    console.print(f"[bold blue]Вопрос:[/bold blue] {question}\n")

    conversation.add_message("user", question)
    response = chat_client.send_message(question, history)
    conversation.add_message("assistant", response)

    console.print(f"[bold green]Ответ:[/bold green]\n{response}\n")

    conversation.auto_title()
    history_manager.save_conversation(conversation)

if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "Привет!"
    ask_question(q)
