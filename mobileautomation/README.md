# Android Emulator Orchestrator MCP (STDIO)

Локальный MCP-server, который управляет docker-эмулятором Android и ADB-инструментами. Все выводы логируются в `stderr`, чтобы не засорять STDIO-канал MCP.

## Требования
- Python 3.11+
- Docker + Docker Compose
- Доступ к ADB (ставится вместе с Android Platform Tools)

## Запуск MCP STDIO-сервера через Docker
1. Построить образ (из корня `mobileautomation`):
   ```bash
   docker build -t mobileautomation-mcp .
   ```
2. Запустить сервер (STDIO; нужно пробросить Docker socket):
   ```bash
   docker run --rm -i \
     -v /var/run/docker.sock:/var/run/docker.sock \
     mobileautomation-mcp
   ```
   Логи пишутся в stderr, STDIO остаётся чистым для MCP.

> Скрипт `./scripts/run_mcp.sh` делает те же шаги: билд образа и запуск контейнера.

## Подключение в Cursor
1) Добавить этот сервер:
   - Cursor → Add MCP server → Command
   - Command: `docker run --rm -i -v /var/run/docker.sock:/var/run/docker.sock mobileautomation-mcp`
   - Working directory: абсолютный путь к `mobileautomation` (используется только для удобства, образ уже содержит код).

2) Добавить второй сервер (готовый mobile-mcp):
   - Cursor → Add MCP server → Command
   - Command: `npx -y @mobilenext/mobile-mcp@latest`
   - Working directory: директория проекта с приложением.

Рекомендуемый сценарий: сначала инфраструктура через этот сервер, затем работа с приложением через `mobile-mcp`.

## Docker окружение
- Сервис: `docker-compose.yml` (budtmo/docker-android-x86-11.0).
- Порты: ADB `5554/5555`, noVNC `6080` (опционально для визуализации).
- Требуется аппаратная виртуализация, Docker Desktop должен иметь доступ к ней.
- Для использования своего compose-файла укажите `COMPOSE_FILE_PATH` при запуске контейнера.
- Для альтернативной команды compose установите `DOCKER_COMPOSE_CMD` (по умолчанию `docker compose`; можно указать `docker-compose`).

## MCP инструменты (имена = функции)
Примеры вызовов (последовательность):
1. `env_up()`
2. `env_status()`
3. `adb_connect(host="127.0.0.1", port=5555)`
4. `wait_boot_completed(serial=None, timeout_sec=300)`
5. `list_devices()`
6. `install_apk(apk_path="/absolute/path/app.apk", serial="emulator-5554")`
7. `launch_app(package="com.example.app", activity="com.example.app.MainActivity", serial="emulator-5554")`
8. `capture_screenshot(serial="emulator-5554", output_path="./shot.png")`
9. Работа через `mobile-mcp` (UI-автоматизация и т.п.)
10. `env_down()` когда закончите.

### Описание инструментов
- `env_up()` — поднять docker-compose с эмулятором.
- `env_down()` — остановить и удалить контейнеры.
- `env_status()` — статус сервисов compose.
- `adb_connect(host="127.0.0.1", port=5555)` — `adb connect host:port`.
- `list_devices()` — список подключённых устройств (serial).
- `wait_boot_completed(serial=None, timeout_sec=300)` — ждёт `sys.boot_completed=1` или `dev.bootcomplete=1`.
- `install_apk(apk_path, serial=None)` — `adb install -r` APK.
- `launch_app(package, activity=None, serial=None)` — запуск через `am start -n` или `monkey` (если `activity` не указан).
- `capture_screenshot(serial=None, output_path=None)` — `adb exec-out screencap`, сохраняет PNG локально (по умолчанию в текущей директории).

## Примечания
- Для `install_apk` указывайте полный путь к APK.
- Если подключено только одно устройство, можно не передавать `serial`.
- Используйте `env_status` для проверки, что эмулятор запущен и слушает ADB.

## Быстрый сценарий: калькулятор + два скриншота
Минимальные шаги в Cursor с двумя MCP:
1) Orchestrator (этот сервер)
   - `env_up()`
   - `adb_connect(host="127.0.0.1", port=5555)`
   - `wait_boot_completed(serial=None)`
   - `launch_app(package="com.android.calculator2", serial="emulator-5554")`
   - `capture_screenshot(serial="emulator-5554", output_path="./calc_before.png")`
2) mobile-mcp
   - Нажать цифры/операцию (например, `2 + 3 =`), используя его UI-инструменты.
   - Сделать второй скриншот (его инструмент), например `calc_after.png`.
   - Выполнить сравнение/проверку результата (визуально или через его команды сравнения, если доступны).
3) Завершение
   - `env_down()` в orchestrator.

Итог: orchestrator отвечает за эмулятор/ADB и первый снимок; автоматизация действий, второй снимок и сравнение — через `mobile-mcp`.

