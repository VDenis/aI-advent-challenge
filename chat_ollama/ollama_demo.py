#!/usr/bin/env python3
"""
Ollama Local LLM Demo
Самодостаточная программа для работы с локальной LLM через Ollama API.
Требования: Python 3.7+, установленный и запущенный Ollama.
"""

import argparse
import json
import sys
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, List


class Colors:
    """ANSI цвета для красивого вывода"""
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'


class OllamaClient:
    """Клиент для работы с Ollama API"""

    DEFAULT_HOST = "http://localhost:11434"
    DEFAULT_MODEL = "qwen3:4b"

    def __init__(self, host: str = DEFAULT_HOST, timeout: int = 300):
        self.host = host.rstrip('/')
        self.timeout = timeout

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

    def generate(self, model: str, prompt: str) -> str:
        """Сгенерировать ответ модели"""
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False  # Отключаем streaming для простоты
        }

        try:
            response = self._make_request("/api/generate", method="POST", data=payload)
            return response.get("response", "").strip()
        except Exception as e:
            raise RuntimeError(f"Ошибка генерации: {str(e)}")


def print_error(message: str):
    """Вывести ошибку"""
    print(f"{Colors.RED}{Colors.BOLD}❌ ОШИБКА:{Colors.END} {message}", file=sys.stderr)


def print_success(message: str):
    """Вывести успех"""
    print(f"{Colors.GREEN}✓{Colors.END} {message}")


def print_warning(message: str):
    """Вывести предупреждение"""
    print(f"{Colors.YELLOW}⚠{Colors.END}  {message}")


def print_info(message: str):
    """Вывести информацию"""
    print(f"{Colors.BLUE}ℹ{Colors.END}  {message}")


def print_installation_guide():
    """Вывести инструкцию по установке Ollama"""
    print("\n" + "="*70)
    print(f"{Colors.BOLD}📦 ИНСТРУКЦИЯ ПО УСТАНОВКЕ OLLAMA{Colors.END}")
    print("="*70)

    print(f"\n{Colors.BOLD}macOS:{Colors.END}")
    print("  brew install ollama")
    print("  ollama serve")

    print(f"\n{Colors.BOLD}Linux:{Colors.END}")
    print("  curl -fsSL https://ollama.com/install.sh | sh")
    print("  ollama serve")

    print(f"\n{Colors.BOLD}Windows:{Colors.END}")
    print("  Скачать с https://ollama.com/download/windows")
    print("  Установить и запустить (автоматически запускается как служба)")

    print(f"\n{Colors.BOLD}Проверка установки:{Colors.END}")
    print("  ollama --version")

    print("\n" + "="*70 + "\n")


def print_model_guide(model_name: str):
    """Вывести инструкцию по загрузке модели"""
    print("\n" + "="*70)
    print(f"{Colors.BOLD}📥 МОДЕЛЬ '{model_name}' НЕ НАЙДЕНА{Colors.END}")
    print("="*70)

    print(f"\n{Colors.BOLD}Загрузите модель командой:{Colors.END}")
    print(f"  ollama pull {model_name}")

    print(f"\n{Colors.BOLD}Альтернативные лёгкие модели:{Colors.END}")
    print("  ollama pull llama3.2:1b      # Самая лёгкая (~1.3 GB)")
    print("  ollama pull llama3.2:3b      # Рекомендуемая (~2 GB)")
    print("  ollama pull phi3:mini        # Compact (~2.3 GB)")
    print("  ollama pull qwen2.5:3b       # Быстрая (~2 GB)")

    print(f"\n{Colors.BOLD}Проверка установленных моделей:{Colors.END}")
    print("  ollama list")

    print("\n" + "="*70 + "\n")


def healthcheck(client: OllamaClient, model: str) -> int:
    """Полная проверка работоспособности"""
    print(f"\n{Colors.BOLD}🔍 ПРОВЕРКА OLLAMA{Colors.END}\n")

    # 1. Проверка доступности
    print("1. Проверка доступности Ollama...")
    if not client.check_health():
        print_error("Ollama не запущен или недоступен")
        print_warning("Убедитесь, что Ollama запущен: ollama serve")
        print_installation_guide()
        return 1
    print_success(f"Ollama доступен на {client.host}")

    # 2. Получение списка моделей
    print("\n2. Получение списка моделей...")
    try:
        models = client.list_models()
        if not models:
            print_warning("Модели не установлены")
            print_model_guide(model)
            return 1
        print_success(f"Найдено моделей: {len(models)}")
        for m in models:
            marker = "✓" if m == model else " "
            print(f"   {marker} {m}")
    except Exception as e:
        print_error(str(e))
        return 1

    # 3. Проверка наличия нужной модели
    print(f"\n3. Проверка модели '{model}'...")
    if model not in models:
        print_error(f"Модель '{model}' не найдена")
        print_model_guide(model)
        return 1
    print_success(f"Модель '{model}' установлена")

    # 4. Тестовый запрос
    print("\n4. Тестовый запрос к модели...")
    try:
        response = client.generate(model, "Say 'OK' if you can hear me")
        print_success("Модель отвечает:")
        print(f"\n{Colors.BOLD}Ответ:{Colors.END} {response}\n")
    except Exception as e:
        print_error(f"Не удалось выполнить запрос: {str(e)}")
        return 1

    print(f"\n{Colors.GREEN}{Colors.BOLD}✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ{Colors.END}\n")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Ollama Local LLM Demo - работа с локальными языковыми моделями",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  %(prog)s --healthcheck
  %(prog)s --prompt "Объясни квантовую физику простыми словами"
  %(prog)s --prompt "What is Python?" --model llama3.2:1b
  %(prog)s --prompt "Привет, как дела?" --timeout 60

Для первого запуска рекомендуется выполнить:
  ollama serve                    # В отдельном терминале
  ollama pull qwen3:4b            # Загрузить модель
  %(prog)s --healthcheck          # Проверить работоспособность
        """
    )

    parser.add_argument(
        '--prompt', '-p',
        type=str,
        help='Текст запроса к модели'
    )

    parser.add_argument(
        '--model', '-m',
        type=str,
        default=OllamaClient.DEFAULT_MODEL,
        help=f'Имя модели (по умолчанию: {OllamaClient.DEFAULT_MODEL})'
    )

    parser.add_argument(
        '--host',
        type=str,
        default=OllamaClient.DEFAULT_HOST,
        help=f'Адрес Ollama (по умолчанию: {OllamaClient.DEFAULT_HOST})'
    )

    parser.add_argument(
        '--timeout', '-t',
        type=int,
        default=300,
        help='Таймаут запроса в секундах (по умолчанию: 300)'
    )

    parser.add_argument(
        '--healthcheck',
        action='store_true',
        help='Выполнить полную проверку работоспособности'
    )

    args = parser.parse_args()

    # Создаем клиента
    client = OllamaClient(host=args.host, timeout=args.timeout)

    # Режим healthcheck
    if args.healthcheck:
        return healthcheck(client, args.model)

    # Обычный режим - требуется prompt
    if not args.prompt:
        parser.print_help()
        print(f"\n{Colors.RED}Ошибка: требуется --prompt или --healthcheck{Colors.END}\n")
        return 1

    # Быстрая проверка доступности
    if not client.check_health():
        print_error("Ollama не запущен или недоступен")
        print_warning("Запустите: ollama serve")
        print_installation_guide()
        return 1

    # Проверка наличия модели
    try:
        models = client.list_models()
        if args.model not in models:
            print_error(f"Модель '{args.model}' не найдена")
            if models:
                print_info(f"Доступные модели: {', '.join(models)}")
            print_model_guide(args.model)
            return 1
    except Exception as e:
        print_error(f"Не удалось получить список моделей: {str(e)}")
        return 1

    # Генерация ответа
    print(f"\n{Colors.BOLD}💬 Запрос к модели '{args.model}':{Colors.END}")
    print(f"{Colors.BLUE}{args.prompt}{Colors.END}\n")

    print(f"{Colors.BOLD}⏳ Генерация ответа...{Colors.END}")

    try:
        response = client.generate(args.model, args.prompt)
        print(f"\n{Colors.BOLD}{Colors.GREEN}🤖 Ответ модели:{Colors.END}")
        print(f"{response}\n")
        return 0

    except Exception as e:
        print_error(str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
