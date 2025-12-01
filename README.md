# Telegram GigaChat Proxy Bot

Telegram-бот на Python и Aiogram, который проксирует сообщения пользователей в GigaChat API (Сбер). Пользователь отправляет сообщение — бот получает ответ от GigaChat и возвращает в чат.

***

## Возможности

- Проксирование сообщений в GigaChat API  
- Автоматическое получение OAuth-токена  
- Асинхронная работа (aiogram + aiohttp)  
- Простая настройка через `.env`  
- Поддержка SSL-сертификатов Минцифры  

***

## Установка

### Предварительные требования

- Python 3.10+  
- Токен Telegram-бота от BotFather  
- GigaChat API: `client_id` и `client_secret` (base64-кодированные)  

### Переменные окружения

Создай файл `.env`:

```env
BOT_TOKEN=твой_telegram_токен
GIGA_CLIENT_BASIC=base64(client_id:client_secret)
```

***

### Развёртывание

```bash
git clone https://github.com/your-repo/gigachat-telegram-bot.git
cd gigachat-telegram-bot
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows
pip install aiogram aiohttp python-dotenv
```

***

### Запуск

```bash
python bot.py
```

***

## Структура файлов

```
gigachat_bot/
├── bot.py              # Основная логика Telegram-бота
├── gigachat_client.py          # Клиент GigaChat API
└── .env               # Токены (не коммить!)
```

***

## Использование

1. Запусти бота: `python bot.py`  
2. В Telegram найди бота → `/start`  
3. Отправь любое сообщение — получишь ответ от GigaChat  

***

## Настройка SSL для GigaChat (Ubuntu/Debian)

```bash
sudo mkdir -p /usr/local/share/ca-certificates/russian-trusted
curl -k "https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt" -o /usr/local/share/ca-certificates/russian-trusted/russian_trusted_root_ca_pem.crt
curl -k "https://gu-st.ru/content/lending/russian_trusted_sub_ca_pem.crt" -o /usr/local/share/ca-certificates/russian-trusted/russian_trusted_sub_ca_pem.crt
sudo update-ca-certificates -v
```

Проверь: `trust list | grep Russian`

***

## Деплой на VPS

```bash
# Screen для фоновой работы
apt install screen
screen -S gigabot
cd ~/gigachat_bot
source venv/bin/activate
python bot.py
# Ctrl+A, D — отсоединиться
# screen -r gigabot — вернуться
```

***

## Лицензия

MIT License

***

## Поддержка

Создавай Issues в репозитории для вопросов и предложений.
