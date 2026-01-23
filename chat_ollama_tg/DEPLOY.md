# Деплой chat_ollama_tg на сервер

Сервер: `ssh root@31.41.154.209` (Ubuntu 24.04, 2 CPU, 16GB RAM, без GPU)

## 1. Подготовка сервера

```bash
# Обновление и Docker
apt update && apt upgrade -y
apt install -y docker.io docker-compose-v2
systemctl enable docker

# Swap 1GB (опционально)
fallocate -l 1G /swapfile && chmod 600 /swapfile
mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

## 2. Установка Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh

# Настройка для Docker (слушать на всех интерфейсах, держать модель в RAM)
mkdir -p /etc/systemd/system/ollama.service.d
cat > /etc/systemd/system/ollama.service.d/override.conf << EOF
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
Environment="OLLAMA_KEEP_ALIVE=-1"
EOF

systemctl daemon-reload && systemctl restart ollama

# Скачать модель (выбрать одну)
ollama pull gemma2:2b      # 1.6GB, быстрая, без thinking
ollama pull llama3.2:3b    # 2.0GB, хороший баланс
ollama pull qwen3:4b       # 2.5GB, качественная, но имеет thinking режим
```

## 3. Загрузка кода на сервер

```bash
# С локальной машины
rsync -avz --exclude 'venv*' --exclude '__pycache__' --exclude '*.db' \
  ./chat_ollama_tg/ root@31.41.154.209:/opt/chat-ollama-bot/
```

## 4. Конфигурация на сервере

### Dockerfile (`/opt/chat-ollama-bot/Dockerfile`)

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . ./chat_ollama_tg/
RUN mkdir -p /app/data /app/logs
CMD ["python", "-m", "chat_ollama_tg"]
```

### docker-compose.yml (`/opt/chat-ollama-bot/docker-compose.yml`)

```yaml
services:
  bot:
    build: .
    container_name: tg-ollama-bot
    restart: unless-stopped
    network_mode: host
    env_file:
      - .env
    environment:
      - OLLAMA_BASE_URL=http://localhost:11434
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
```

### .env (`/opt/chat-ollama-bot/.env`)

```bash
TELEGRAM_BOT_TOKEN=your_token_here
LLM_ENGINE=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma2:2b
MAX_RESPONSE_TOKENS=400
LLM_TIMEOUT=60
MAX_HISTORY_MESSAGES=10
```

## 5. Запуск

```bash
cd /opt/chat-ollama-bot
docker compose up -d --build
```

## 6. Полезные команды

```bash
# Логи
docker logs tg-ollama-bot -f
docker logs tg-ollama-bot --tail 50

# Управление ботом
docker compose restart
docker compose down && docker compose up -d

# Ollama
ollama list                    # список моделей
ollama rm model_name           # удалить модель
systemctl status ollama        # статус сервиса
systemctl restart ollama       # перезапуск

# Мониторинг
df -h                          # место на диске
htop                           # CPU/RAM
docker exec tg-ollama-bot env  # переменные в контейнере
```

## 7. Оптимизация модели (опционально)

Создать кастомную модель с оптимизированными параметрами:

```bash
cat > /tmp/Modelfile << EOF
FROM gemma2:2b
PARAMETER num_ctx 2048
PARAMETER num_thread 2
PARAMETER num_predict 512
EOF

ollama create gemma2-fast -f /tmp/Modelfile
```

Затем в `.env`: `OLLAMA_MODEL=gemma2-fast`

## 8. Выбор модели

| Модель | Размер | Скорость (2 CPU) | Особенности |
|--------|--------|------------------|-------------|
| gemma2:2b | 1.6GB | ~6 tok/s | Быстрая, без thinking |
| llama3.2:3b | 2.0GB | ~5 tok/s | Хороший баланс |
| qwen3:4b | 2.5GB | ~5.5 tok/s | Качественная, но thinking тратит токены |

## 9. Troubleshooting

**Таймаут при генерации:**
- Увеличить `LLM_TIMEOUT` в `.env`
- Уменьшить `MAX_RESPONSE_TOKENS`
- Использовать меньшую модель

**Пустые ответы (qwen3):**
- Модель тратит токены на thinking
- Увеличить `MAX_RESPONSE_TOKENS` до 512+
- Или переключиться на gemma2/llama3.2

**Бот не видит Ollama:**
- Проверить `OLLAMA_HOST=0.0.0.0:11434` в override.conf
- Использовать `network_mode: host` в docker-compose
- `curl http://localhost:11434/api/tags` для проверки

**Не хватает места:**
- `ollama rm` для удаления ненужных моделей
- Использовать меньшую модель
