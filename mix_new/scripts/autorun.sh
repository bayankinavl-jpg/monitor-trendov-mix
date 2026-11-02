#!/bin/bash
# Автозапуск парсера каждый день в 9:00 через launchd (планировщик macOS).
#   scripts/autorun.sh install  — включить
#   scripts/autorun.sh remove   — выключить
#   scripts/autorun.sh status   — включён ли и чем закончился последний запуск
#   scripts/autorun.sh now      — запустить задачу сейчас, не дожидаясь 9:00
set -e
LABEL=com.ailab.mixnews
SCRIPTS_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPTS_DIR")"
SRC="$SCRIPTS_DIR/$LABEL.plist"
DST="$HOME/Library/LaunchAgents/$LABEL.plist"
TARGET="gui/$(id -u)/$LABEL"

case "$1" in
  install)
    mkdir -p "$HOME/Library/LaunchAgents" "$PROJECT_DIR/logs"
    # В шаблоне вместо пути стоит __PROJECT_DIR__: подставляем папку проекта.
    sed "s|__PROJECT_DIR__|$PROJECT_DIR|g" "$SRC" > "$DST"
    launchctl bootout "$TARGET" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$DST"
    echo "Автозапуск включён: каждый день в 9:00. Журнал: logs/autorun.log"
    ;;
  remove)
    launchctl bootout "$TARGET" 2>/dev/null || true
    rm -f "$DST"
    echo "Автозапуск выключен"
    ;;
  status)
    launchctl print "$TARGET" 2>/dev/null | grep -E "state|last exit code|runs" \
      || echo "Автозапуск не включён"
    ;;
  now)
    launchctl kickstart "$TARGET"
    echo "Запущено. Ход сбора: tail -f logs/autorun.log"
    ;;
  *)
    echo "Использование: $0 install|remove|status|now"
    exit 1
    ;;
esac
