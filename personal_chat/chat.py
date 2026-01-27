"""Модуль интеграции с GigaChat."""

from typing import Generator, Optional
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole

from .config import AppConfig, UserProfile


class ChatClient:
    """Клиент для общения с GigaChat."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.profile = config.profile
        self.system_prompt = self.profile.to_system_prompt()

        if not config.gigachat_credentials:
            raise ValueError(
                "Не указаны credentials для GigaChat. "
                "Установите переменную окружения GIGACHAT_CREDENTIALS или добавьте в конфиг."
            )

        self.client = GigaChat(
            credentials=config.gigachat_credentials,
            scope=config.gigachat_scope,
            model=config.gigachat_model,
            verify_ssl_certs=False,
        )

    def _build_messages(self, history: list[dict], user_message: str) -> list[Messages]:
        """Собирает список сообщений для API."""
        messages = []

        # Системный промпт с персонализацией
        messages.append(Messages(role=MessagesRole.SYSTEM, content=self.system_prompt))

        # История разговора
        for msg in history:
            role = MessagesRole.USER if msg["role"] == "user" else MessagesRole.ASSISTANT
            messages.append(Messages(role=role, content=msg["content"]))

        # Текущее сообщение пользователя
        messages.append(Messages(role=MessagesRole.USER, content=user_message))

        return messages

    def send_message(self, user_message: str, history: list[dict] = None) -> str:
        """Отправляет сообщение и получает ответ."""
        history = history or []
        messages = self._build_messages(history, user_message)

        response = self.client.chat(Chat(messages=messages))

        return response.choices[0].message.content

    def send_message_stream(
        self, user_message: str, history: list[dict] = None
    ) -> Generator[str, None, None]:
        """Отправляет сообщение и получает ответ потоком."""
        history = history or []
        messages = self._build_messages(history, user_message)

        for chunk in self.client.stream(Chat(messages=messages)):
            content = chunk.choices[0].delta.content
            if content:
                yield content

    def update_profile(self, profile: UserProfile) -> None:
        """Обновляет профиль и перегенерирует системный промпт."""
        self.profile = profile
        self.system_prompt = profile.to_system_prompt()

    def get_models(self) -> list[str]:
        """Возвращает список доступных моделей."""
        try:
            models = self.client.get_models()
            return [m.id for m in models.data]
        except Exception:
            return ["GigaChat", "GigaChat-Plus", "GigaChat-Pro"]

    def test_connection(self) -> bool:
        """Проверяет подключение к API."""
        try:
            self.client.get_models()
            return True
        except Exception:
            return False
