"""Модуль работы с конфигурацией персонализации."""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
import yaml


@dataclass
class UserProfile:
    """Профиль пользователя для персонализации."""

    # Базовые данные
    name: str = "Пользователь"
    language: str = "русский"
    communication_style: str = "дружелюбный"  # формальный, дружелюбный, краткий

    # Профессиональные данные
    profession: str = ""
    work_context: str = ""
    skills: list[str] = field(default_factory=list)

    # Личные данные
    interests: list[str] = field(default_factory=list)
    hobbies: list[str] = field(default_factory=list)
    favorite_topics: list[str] = field(default_factory=list)

    # Привычки и предпочтения
    habits: list[str] = field(default_factory=list)
    preferences: dict = field(default_factory=dict)

    # Цели
    goals: list[str] = field(default_factory=list)
    current_projects: list[str] = field(default_factory=list)

    # Контекст
    timezone: str = "Europe/Moscow"
    location: str = ""

    # Дополнительные заметки
    notes: str = ""

    def to_system_prompt(self) -> str:
        """Генерирует системный промпт на основе профиля."""
        parts = [
            f"Ты персональный ассистент пользователя по имени {self.name}.",
            f"Общайся на {self.language} языке в {self.communication_style} стиле.",
        ]

        if self.profession:
            parts.append(f"Пользователь работает как {self.profession}.")

        if self.work_context:
            parts.append(f"Контекст работы: {self.work_context}.")

        if self.skills:
            parts.append(f"Навыки пользователя: {', '.join(self.skills)}.")

        if self.interests:
            parts.append(f"Интересы: {', '.join(self.interests)}.")

        if self.hobbies:
            parts.append(f"Хобби: {', '.join(self.hobbies)}.")

        if self.favorite_topics:
            parts.append(f"Любимые темы для обсуждения: {', '.join(self.favorite_topics)}.")

        if self.habits:
            parts.append(f"Привычки пользователя: {', '.join(self.habits)}.")

        if self.goals:
            parts.append(f"Текущие цели: {', '.join(self.goals)}.")

        if self.current_projects:
            parts.append(f"Текущие проекты: {', '.join(self.current_projects)}.")

        if self.timezone:
            parts.append(f"Часовой пояс пользователя: {self.timezone}.")

        if self.location:
            parts.append(f"Местоположение: {self.location}.")

        if self.preferences:
            pref_str = "; ".join(f"{k}: {v}" for k, v in self.preferences.items())
            parts.append(f"Предпочтения: {pref_str}.")

        if self.notes:
            parts.append(f"Дополнительно: {self.notes}")

        parts.append("\nУчитывай эту информацию при общении. Будь полезным и внимательным к контексту пользователя.")

        return "\n".join(parts)


@dataclass
class AppConfig:
    """Конфигурация приложения."""

    # GigaChat настройки
    gigachat_credentials: str = ""
    gigachat_model: str = "GigaChat"
    gigachat_scope: str = "GIGACHAT_API_PERS"

    # История
    history_enabled: bool = True
    history_max_messages: int = 50

    # Профиль пользователя
    profile: UserProfile = field(default_factory=UserProfile)


def get_config_dir() -> Path:
    """Возвращает директорию конфигурации."""
    config_dir = Path(__file__).parent / ".config"
    config_dir.mkdir(exist_ok=True)
    return config_dir


def get_profile_path() -> Path:
    """Возвращает путь к файлу профиля."""
    return get_config_dir() / "profile.yaml"


def get_app_config_path() -> Path:
    """Возвращает путь к файлу конфигурации приложения."""
    return get_config_dir() / "config.yaml"


def load_profile(path: Optional[Path] = None) -> UserProfile:
    """Загружает профиль пользователя из YAML файла."""
    profile_path = path or get_profile_path()

    if not profile_path.exists():
        return UserProfile()

    with open(profile_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    return UserProfile(**data)


def save_profile(profile: UserProfile, path: Optional[Path] = None) -> None:
    """Сохраняет профиль пользователя в YAML файл."""
    profile_path = path or get_profile_path()
    profile_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "name": profile.name,
        "language": profile.language,
        "communication_style": profile.communication_style,
        "profession": profile.profession,
        "work_context": profile.work_context,
        "skills": profile.skills,
        "interests": profile.interests,
        "hobbies": profile.hobbies,
        "favorite_topics": profile.favorite_topics,
        "habits": profile.habits,
        "preferences": profile.preferences,
        "goals": profile.goals,
        "current_projects": profile.current_projects,
        "timezone": profile.timezone,
        "location": profile.location,
        "notes": profile.notes,
    }

    with open(profile_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def load_app_config() -> AppConfig:
    """Загружает конфигурацию приложения."""
    config_path = get_app_config_path()

    # Сначала загружаем из .env
    credentials = os.getenv("GIGACHAT_CREDENTIALS", "")

    config = AppConfig(gigachat_credentials=credentials)

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        config.gigachat_model = data.get("gigachat_model", config.gigachat_model)
        config.gigachat_scope = data.get("gigachat_scope", config.gigachat_scope)
        config.history_enabled = data.get("history_enabled", config.history_enabled)
        config.history_max_messages = data.get("history_max_messages", config.history_max_messages)

        # Если credentials не в env, берём из конфига
        if not config.gigachat_credentials:
            config.gigachat_credentials = data.get("gigachat_credentials", "")

    # Загружаем профиль
    config.profile = load_profile()

    return config


def save_app_config(config: AppConfig) -> None:
    """Сохраняет конфигурацию приложения."""
    config_path = get_app_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "gigachat_model": config.gigachat_model,
        "gigachat_scope": config.gigachat_scope,
        "history_enabled": config.history_enabled,
        "history_max_messages": config.history_max_messages,
    }

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

    # Сохраняем профиль отдельно
    save_profile(config.profile)


def create_example_profile() -> None:
    """Создаёт пример профиля."""
    example = UserProfile(
        name="Денис",
        language="русский",
        communication_style="дружелюбный",
        profession="Software Engineer",
        work_context="Разработка AI/ML проектов, работа с LLM и MCP серверами",
        skills=["Python", "TypeScript", "Machine Learning", "LangChain"],
        interests=["искусственный интеллект", "автоматизация", "продуктивность"],
        hobbies=["программирование", "чтение технической литературы"],
        favorite_topics=["AI", "разработка", "новые технологии"],
        habits=["утренний кофе", "код-ревью по утрам"],
        preferences={
            "ответы": "структурированные с примерами кода",
            "длина": "средняя, по делу",
            "формат": "markdown когда нужно",
        },
        goals=["улучшить навыки ML", "автоматизировать рутинные задачи"],
        current_projects=["AI Assistant", "MCP интеграции"],
        timezone="Europe/Moscow",
        location="Россия",
        notes="Предпочитаю практические советы теоретическим рассуждениям.",
    )

    example_path = Path(__file__).parent / "profile_example.yaml"
    save_profile(example, example_path)
