#!/bin/bash
# Запуск парсера: активирует виртуальное окружение и запускает scripts/run_news.py.
# Аргументы передаются парсеру без изменений, например: ./run.sh --days 7
set -e
cd "$(dirname "$0")"
source .venv/bin/activate
python scripts/run_news.py "$@"
