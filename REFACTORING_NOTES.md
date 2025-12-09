## Refactoring Notes

- Перенесён бот по недвижимости в `bots/real_estate/` (`bot.py`, `handlers.py`).
- Перенесён литературный бот в `bots/literary/` (`bot.py`, `handlers.py`).
- Общий клиент GigaChat выделен в `services/gigachat/` (`client.py`, `config.py`, `__init__.py`).
- Добавлен корневой запускатор `main.py` с выбором бота через флаг `--bot`.
- Удалена старая директория `app/` с исходными монолитными файлами.
- Все импорты обновлены на новую структуру, боты используют общий `chat_gigachat` из `services.gigachat`.
