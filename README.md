# Telegram боты с GigaChat и Hugging Face

Проект содержит Telegram-боты на Python (aiogram 3) и клиенты для GigaChat и Hugging Face Inference API:

- 🏗 `real_estate` — помощник по подбору и оценке квартир с разными стилями общения.
- ✍️ `literary` — демонстрирует, как меняются ответы модели при разных температурах.
- 🤖 `hf_demo` — тестирует модели Hugging Face (deepseek, llama3, qwen2).
- 🛠 `cli/hf_cli.py` — CLI для одиночных запросов и сравнения моделей Hugging Face.

## Требования

- Python 3.10+
- Токен Telegram-бота (`BOT_TOKEN`)
- Токен Telegram-бота для Hugging Face демо (`HF_BOT_TOKEN`)
- Токен Hugging Face Inference API (`HF_TOKEN`)
- Доступ к GigaChat API: `client_id` и `client_secret` в base64 (`GIGA_CLIENT_BASIC`)

Создай `.env` в корне:

```env
BOT_TOKEN=твой_telegram_токен
HF_BOT_TOKEN=токен_бота_для_hf_demo
HF_TOKEN=токен_hugging_face_api
GIGA_CLIENT_BASIC=base64(client_id:client_secret)
```

Установка зависимостей:

```bash
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Запуск

Реал-эстейт бот:

```bash
python -m bots.real_estate.bot
```

Литературный бот с разными температурами:

```bash
python -m bots.literary.bot
```

Hugging Face демо-бот:

```bash
python -m bots.hf_demo.bot
```

Универсальный запуск через селектор:

```bash
python main.py --bot real_estate
python main.py --bot literary
python main.py --bot hf_demo
```

CLI для Hugging Face (одиночный запрос):

```bash
python cli/hf_cli.py --model llama3 "Объясни разницу между этими моделями"
```

CLI сравнение трёх моделей:

```bash
python cli/hf_cli.py --compare_three "Один и тот же запрос для трёх моделей"
```

## Структура

```
.
├── bots/
│   ├── real_estate/      # Бот по недвижимости (entrypoint bot.py, handlers.py)
│   ├── literary/         # Бот с температурами (entrypoint bot.py, handlers.py)
│   └── hf_demo/          # Бот для теста моделей Hugging Face
├── cli/
│   └── hf_cli.py         # CLI для одиночных запросов и сравнения моделей HF
├── services/
│   ├── gigachat/         # Переиспользуемый клиент GigaChat
│   └── huggingface/      # Переиспользуемый клиент Hugging Face Inference API
├── main.py               # Запуск нужного бота через флаг
├── requirements.txt
├── README.md
└── REFACTORING_NOTES.md
```

## Замечания по GigaChat

- В `services/gigachat/config.py` задаются базовые URL и параметры по умолчанию.
- SSL-проверка выключена так же, как в исходном коде (connector `ssl=False`). При необходимости включи `verify_ssl=True` в конфиге.

## Hugging Face

- Конфиг и клиент: `services/huggingface/config.py` и `services/huggingface/client.py`.
- Поддерживаемые короткие имена моделей: `deepseek`, `llama3`, `qwen2` (мапятся на актуальные id в Hub).
- CLI (`cli/hf_cli.py`) позволяет делать одиночные запросы и сравнивать три модели по одному prompt, печатая время ответа, примерное число токенов и стоимость (заполни цены в конфиге при необходимости).

## Лицензия

MIT License
