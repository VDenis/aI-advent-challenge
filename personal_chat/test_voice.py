"""Тест голосового ввода: запись → распознавание → отправка в GigaChat."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from personal_chat.voice import record_audio, recognize, voice_input
from personal_chat.config import load_app_config
from personal_chat.chat import ChatClient

console = Console()


def test_stt_only():
    """Тест только распознавания речи (без LLM)."""
    console.print("[bold cyan]== Тест STT (Whisper) ==[/bold cyan]\n")

    prompts = [
        "Скажите: «посчитай два плюс два»",
        "Скажите: «дай определение рекурсии»",
        "Скажите: «расскажи анекдот»",
    ]

    for i, prompt in enumerate(prompts, 1):
        console.print(f"[bold]Тест {i}/3:[/bold] {prompt}")
        text = voice_input(duration=5.0, model_name="base", language="ru")
        console.print(f"  Распознано: [green]{text}[/green]\n")


def test_voice_to_llm():
    """Полный тест: голос → текст → GigaChat → ответ."""
    console.print("[bold cyan]== Тест Voice → LLM ==[/bold cyan]\n")

    config = load_app_config()
    client = ChatClient(config)

    if not client.test_connection():
        console.print("[red]Нет подключения к GigaChat[/red]")
        return

    test_phrases = [
        "посчитай два плюс два",
        "дай определение рекурсии",
        "расскажи анекдот",
    ]

    for i, expected in enumerate(test_phrases, 1):
        console.print(f"[bold]Тест {i}/3:[/bold] Скажите: «{expected}»")
        console.print("  Запись через 1 сек...")

        text = voice_input(duration=5.0)
        if not text:
            console.print("  [yellow]Не распознано, пропускаю[/yellow]\n")
            continue

        console.print(f"  Распознано: [green]{text}[/green]")
        console.print("  Отправляю в GigaChat...")

        response = client.send_message(text, history=[])
        console.print(f"  Ответ: [cyan]{response[:300]}[/cyan]\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Тест голосового ввода")
    parser.add_argument("--stt", action="store_true", help="Только распознавание (без LLM)")
    args = parser.parse_args()

    if args.stt:
        test_stt_only()
    else:
        test_voice_to_llm()
