#!/bin/bash
# Пульт монитора: открывает лендинг с кнопкой запуска парсера в браузере.
# Остановить — Ctrl+C в этом окне терминала.
set -e
cd "$(dirname "$0")"
source .venv/bin/activate
(sleep 1 && open "http://127.0.0.1:8765") &
python scripts/monitor_server.py --port 8765 "$@"
