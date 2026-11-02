#!/bin/bash
# Запуск парсера: активирует виртуальное окружение и запускает scripts/run_news.py.
# Аргументы передаются парсеру без изменений, например: ./run.sh --days 7
set -e
cd "$(dirname "$0")"
source .venv/bin/activate
# Локальные настройки, например ключ Claude API для карточек трендов:
# файл .env в папке проекта со строкой ANTHROPIC_API_KEY=... (в git не попадает).
if [ -f .env ]; then set -a; . ./.env; set +a; fi
python scripts/run_news.py "$@"
