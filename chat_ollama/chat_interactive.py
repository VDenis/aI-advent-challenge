#!/usr/bin/env python3
"""
Ollama Interactive Chat
Интерактивный диалог с локальной LLM через Ollama API.
Поддерживает историю сообщений и контекст разговора.
"""

import argparse
import json
import sys
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional
from datetime import datetime


class Colors:
    """ANSI цвета для красивого вывода"""
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    END = '\033[0m'


class OllamaChatClient:
    """Клиент для диалога с Ollama API"""

    DEFAULT_HOST = "http://localhost:11434"
    DEFAULT_MODEL = "qwen3:4b"

    def __init__(self, host: str = DEFAULT_HOST, timeout: int = 300):
        self.host = host.rstrip('/')
        self.timeout = timeout
        self.messages: List[Dict[str, str]] = []

    def _make_request(
        self,
        endpoint: str,
        method: str = "GET",
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Универсальный метод для HTTP запросов"""
        url = f"{self.host}{endpoint}"

        try:
            if method == "GET":
                with urllib.request.urlopen(url, timeout=self.timeout) as response:
                    return json.loads(response.read().decode('utf-8'))

            elif method == "POST":
                headers = {'Content-Type': 'application/json'}
                json_data = json.dumps(data).encode('utf-8')
                req = urllib.request.Request(url, data=json_data, headers=headers, method='POST')

                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    return json.loads(response.read().decode('utf-8'))

        except urllib.error.URLError as e:
            raise ConnectionError(f"Не удалось подключиться к Ollama: {e.reason}")
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8') if e.fp else ""
            raise RuntimeError(f"HTTP {e.code}: {error_body}")
        except Exception as e:
            raise RuntimeError(f"Ошибка запроса: {str(e)}")

    def check_health(self) -> bool:
        """Проверка доступности Ollama"""
        try:
            url = f"{self.host}/"
            with urllib.request.urlopen(url, timeout=self.timeout) as response:
                return response.status == 200
        except Exception:
            return False

    def list_models(self) -> List[str]:
        """Получить список установленных моделей"""
        try:
            response = self._make_request("/api/tags")
            models = response.get("models", [])
            return [model.get("name", "") for model in models]
        except Exception as e:
            raise RuntimeError(f"Не удалось получить список моделей: {str(e)}")

    def add_message(self, role: str, content: str):
        """Добавить сообщение в историю"""
        self.messages.append({"role": role, "content": content})

    def chat(self, model: str, user_message: str) -> str:
        """Отправить сообщение и получить ответ с учетом контекста"""
        # Добавляем сообщение пользователя
        self.add_message("user", user_message)

        payload = {
            "model": model,
            "messages": self.messages,
            "stream": False
        }

        try:
            response = self._make_request("/api/chat", method="POST", data=payload)
            assistant_message = response.get("message", {}).get("content", "").strip()

            # Добавляем ответ ассистента в историю
            self.add_message("assistant", assistant_message)

            return assistant_message
        except Exception as e:
            # Убираем последнее сообщение пользователя, если произошла ошибка
            if self.messages and self.messages[-1]["role"] == "user":
                self.messages.pop()
            raise RuntimeError(f"Ошибка генерации: {str(e)}")

    def clear_history(self):
        """Очистить историю диалога"""
        self.messages = []

    def get_history_size(self) -> int:
        """Получить размер истории (количество сообщений)"""
        return len(self.messages)


def print_error(message: str):
    """Вывести ошибку"""
    print(f"{Colors.RED}{Colors.BOLD}❌ ОШИБКА:{Colors.END} {message}", file=sys.stderr)


def print_success(message: str):
    """Вывести успех"""
    print(f"{Colors.GREEN}✓{Colors.END} {message}")


def print_info(message: str):
    """Вывести информацию"""
    print(f"{Colors.CYAN}ℹ{Colors.END}  {message}")


def print_system(message: str):
    """Вывести системное сообщение"""
    print(f"{Colors.DIM}{message}{Colors.END}")


def print_separator():
    """Вывести разделитель"""
    print(f"{Colors.DIM}{'─' * 70}{Colors.END}")


def print_welcome():
    """Вывести приветствие"""
    print("\n" + "=" * 70)
    print(f"{Colors.BOLD}{Colors.CYAN}💬 Ollama Interactive Chat{Colors.END}")
    print("=" * 70)
    print(f"\n{Colors.YELLOW}Команды:{Colors.END}")
    print(f"  {Colors.BOLD}exit{Colors.END} или {Colors.BOLD}quit{Colors.END} - выход из чата")
    print(f"  {Colors.BOLD}clear{Colors.END} - очистить историю диалога")
    print(f"  {Colors.BOLD}history{Colors.END} - показать всю историю диалога")
    print(f"  {Colors.BOLD}help{Colors.END} - показать это сообщение")
    print("\n" + "=" * 70 + "\n")


def print_history(client: OllamaChatClient):
    """Вывести историю диалога"""
    if not client.messages:
        print_info("История диалога пуста")
        return

    print(f"\n{Colors.BOLD}📜 История диалога ({len(client.messages)} сообщений):{Colors.END}\n")
    print_separator()

    for i, msg in enumerate(client.messages, 1):
        role = msg["role"]
        content = msg["content"]

        if role == "user":
            print(f"\n{Colors.BLUE}{Colors.BOLD}[{i}] Вы:{Colors.END}")
            print(f"{content}")
        elif role == "assistant":
            print(f"\n{Colors.GREEN}{Colors.BOLD}[{i}] AI:{Colors.END}")
            print(f"{content}")

    print()
    print_separator()


def run_predefined_dialog(client: OllamaChatClient, model: str):
    """Запустить предопределенный диалог для теста"""
    print(f"\n{Colors.BOLD}{Colors.MAGENTA}🤖 Запуск тестового диалога...{Colors.END}\n")
    print_separator()

    # Предопределенные вопросы для диалога
    questions = [
        "Объясни простыми словами, что такое квантовый компьютер",
        "Напиши короткое четверостишье про программиста",
        "Я загадал число от 1 до 10. Ты можешь задать мне 3 вопроса, чтобы его угадать. Начинай!",
        "Почему небо голубое? Объясни за 30 секунд",
        "Если бы ты был senior разработчиком, какой совет дал бы начинающему программисту?"
    ]

    for i, question in enumerate(questions, 1):
        print(f"\n{Colors.BLUE}{Colors.BOLD}[{i}] Вы:{Colors.END}")
        print(question)

        print(f"\n{Colors.DIM}⏳ Ожидание ответа...{Colors.END}")

        try:
            response = client.chat(model, question)
            print(f"\n{Colors.GREEN}{Colors.BOLD}[{i}] AI:{Colors.END}")
            print(response)
        except Exception as e:
            print_error(f"Ошибка при получении ответа: {str(e)}")
            return 1

        if i < len(questions):
            print_separator()

    print(f"\n\n{Colors.BOLD}{Colors.GREEN}✅ Тестовый диалог завершён!{Colors.END}")
    print(f"{Colors.DIM}Всего сообщений в истории: {client.get_history_size()}{Colors.END}\n")

    return 0


def interactive_chat(client: OllamaChatClient, model: str):
    """Запустить интерактивный режим чата"""
    print_welcome()
    print_info(f"Используется модель: {Colors.BOLD}{model}{Colors.END}")
    print_info(f"Подключено к: {Colors.BOLD}{client.host}{Colors.END}\n")

    while True:
        try:
            # Получаем ввод от пользователя
            user_input = input(f"{Colors.BLUE}{Colors.BOLD}Вы:{Colors.END} ").strip()

            if not user_input:
                continue

            # Обработка команд
            if user_input.lower() in ['exit', 'quit', 'выход']:
                print(f"\n{Colors.YELLOW}Выход из чата...{Colors.END}")
                print_info(f"Всего сообщений: {client.get_history_size()}")
                print(f"\n{Colors.CYAN}До свидания! 👋{Colors.END}\n")
                break

            elif user_input.lower() == 'clear':
                client.clear_history()
                print_success("История диалога очищена")
                continue

            elif user_input.lower() == 'history':
                print_history(client)
                continue

            elif user_input.lower() == 'help':
                print_welcome()
                continue

            # Отправка сообщения модели
            print(f"\n{Colors.DIM}⏳ Генерация ответа...{Colors.END}\n")

            try:
                response = client.chat(model, user_input)
                print(f"{Colors.GREEN}{Colors.BOLD}AI:{Colors.END} {response}\n")
            except Exception as e:
                print_error(f"Не удалось получить ответ: {str(e)}\n")

        except KeyboardInterrupt:
            print(f"\n\n{Colors.YELLOW}Прервано пользователем (Ctrl+C){Colors.END}")
            print_info(f"Всего сообщений: {client.get_history_size()}")
            print(f"\n{Colors.CYAN}До свидания! 👋{Colors.END}\n")
            break
        except EOFError:
            print(f"\n\n{Colors.YELLOW}Конец ввода{Colors.END}\n")
            break

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Ollama Interactive Chat - интерактивный диалог с локальной LLM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  %(prog)s                        # Интерактивный режим
  %(prog)s --test                 # Запустить предопределенный тестовый диалог
  %(prog)s --model llama3.2:1b    # Использовать другую модель

Интерактивные команды:
  exit, quit  - выход из чата
  clear       - очистить историю диалога
  history     - показать всю историю
  help        - показать помощь
        """
    )

    parser.add_argument(
        '--model', '-m',
        type=str,
        default=OllamaChatClient.DEFAULT_MODEL,
        help=f'Имя модели (по умолчанию: {OllamaChatClient.DEFAULT_MODEL})'
    )

    parser.add_argument(
        '--host',
        type=str,
        default=OllamaChatClient.DEFAULT_HOST,
        help=f'Адрес Ollama (по умолчанию: {OllamaChatClient.DEFAULT_HOST})'
    )

    parser.add_argument(
        '--timeout', '-t',
        type=int,
        default=300,
        help='Таймаут запроса в секундах (по умолчанию: 300)'
    )

    parser.add_argument(
        '--test',
        action='store_true',
        help='Запустить предопределенный тестовый диалог'
    )

    args = parser.parse_args()

    # Создаем клиента
    client = OllamaChatClient(host=args.host, timeout=args.timeout)

    # Проверка доступности Ollama
    if not client.check_health():
        print_error("Ollama не запущен или недоступен")
        print_info("Запустите: ollama serve")
        return 1

    # Проверка наличия модели
    try:
        models = client.list_models()
        if args.model not in models:
            print_error(f"Модель '{args.model}' не найдена")
            if models:
                print_info(f"Доступные модели: {', '.join(models)}")
            else:
                print_info(f"Загрузите модель: ollama pull {args.model}")
            return 1
    except Exception as e:
        print_error(f"Не удалось получить список моделей: {str(e)}")
        return 1

    # Запуск нужного режима
    if args.test:
        return run_predefined_dialog(client, args.model)
    else:
        return interactive_chat(client, args.model)


if __name__ == "__main__":
    sys.exit(main())
