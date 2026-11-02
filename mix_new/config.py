"""Общие константы проекта."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
EXPORTS_DIR = DATA_DIR / "exports"
LOGS_DIR = BASE_DIR / "logs"
MAIN_DB_PATH = DATA_DIR / "registry.sqlite3"

KEYWORDS_PATH = BASE_DIR / "keywords.yml"
SOURCES_PATH = BASE_DIR / "sources.yml"
TRENDS_PATH = BASE_DIR / "trends.yml"
LAW_ALIASES_PATH = BASE_DIR / "reference" / "law_aliases.json"

MOSCOW_TZ_NAME = "Europe/Moscow"

HTTP_TIMEOUT = 10
HTTP_RETRY_COUNT = 1
HTTP_USER_AGENT = "AI-Lab-RegNewsTracker/0.2 (+regulatory news registry for internal bank use)"
REQUEST_DELAY_SECONDS = 1.0

# Автоматические карточки трендов (pipeline/trend_cards.py). Текст карточек
# пишет Claude API, если задан ключ ANTHROPIC_API_KEY; без ключа карточки
# собираются только из цифр и сигналов.
TREND_CARDS_MODEL = "claude-opus-5-5"
TREND_CARDS_MAX = 10  # не больше стольких активных карточек — и вызовов модели за запуск

# Домены, к которым парсер не обращается (tz_news_parser.md, раздел
# "Источники новостей", правило 5). Запрет на pravo.gov.ru снят 11.10.2026.
FORBIDDEN_DOMAINS = {
    "regulation.gov.ru",
    "sozd.duma.gov.ru",
}
