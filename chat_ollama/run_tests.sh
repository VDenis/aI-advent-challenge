#!/bin/bash
# Скрипт для быстрого тестирования обеих программ

set -e  # Выход при ошибке

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║           🧪 Тестирование Chat Ollama                               ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo ""

# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Проверка Ollama
echo -e "${BLUE}[1/4]${NC} Проверка доступности Ollama..."
if ! curl -s http://localhost:11434/ > /dev/null 2>&1; then
    echo -e "${RED}❌ Ollama не запущен!${NC}"
    echo -e "${YELLOW}Запустите: ollama serve${NC}"
    exit 1
fi
echo -e "${GREEN}✓${NC} Ollama доступен"
echo ""

# Healthcheck базовой программы
echo -e "${BLUE}[2/4]${NC} Запуск healthcheck (ollama_demo.py)..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if python3 ollama_demo.py --healthcheck; then
    echo -e "${GREEN}✓${NC} Healthcheck пройден"
else
    echo -e "${RED}❌ Healthcheck провалился${NC}"
    exit 1
fi
echo ""

# Одиночный запрос
echo -e "${BLUE}[3/4]${NC} Тест одиночного запроса (ollama_demo.py)..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if python3 ollama_demo.py --prompt "Скажи 'Тест пройден' если ты меня слышишь"; then
    echo -e "${GREEN}✓${NC} Одиночный запрос выполнен"
else
    echo -e "${RED}❌ Ошибка при выполнении запроса${NC}"
    exit 1
fi
echo ""

# Тестовый диалог
echo -e "${BLUE}[4/4]${NC} Тест диалога с историей (chat_interactive.py)..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if python3 chat_interactive.py --test; then
    echo -e "${GREEN}✓${NC} Тестовый диалог завершён"
else
    echo -e "${RED}❌ Ошибка в тестовом диалоге${NC}"
    exit 1
fi
echo ""

# Итог
echo "╔══════════════════════════════════════════════════════════════════════╗"
echo -e "║  ${GREEN}✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!${NC}                                  ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo ""
echo -e "${YELLOW}Теперь можно запустить интерактивный чат:${NC}"
echo -e "  python3 chat_interactive.py"
echo ""
