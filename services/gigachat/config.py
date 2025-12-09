"""Configuration for the GigaChat client."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass
class GigaChatConfig:
    """Runtime configuration for the GigaChat API client."""

    oauth_url: str = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    chat_url: str = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
    scope: str = "GIGACHAT_API_PERS"
    basic_auth: str = os.getenv("GIGA_CLIENT_BASIC", "")
    model: str = "GigaChat"
    default_temperature: float = 0.7
    token_skew_seconds: float = 30.0
    verify_ssl: bool = False
