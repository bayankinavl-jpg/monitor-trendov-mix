"""Общие константы проекта."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
EXPORTS_DIR = DATA_DIR / "exports"
LOGS_DIR = BASE_DIR / "logs"
MAIN_DB_PATH = DATA_DIR / "registry.sqlite3"

KEYWORDS_PATH = BASE_DIR / "keywords.yml"
SOURCES_PATH = BASE_DIR / "sources.yml"

MOSCOW_TZ_NAME = "Europe/Moscow"

HTTP_TIMEOUT = 10
HTTP_RETRY_COUNT = 1
HTTP_USER_AGENT = "AI-Lab-RegNewsTracker/0.2 (+regulatory news registry for internal bank use)"
REQUEST_DELAY_SECONDS = 1.0

# Домены, к которым парсер не обращается никогда (см. tz_news_parser.md,
# раздел "Источники новостей", правило 5) — запрет снимается отдельным
# решением, если появится доступ из российской сети.
FORBIDDEN_DOMAINS = {
    "pravo.gov.ru",
    "publication.pravo.gov.ru",
    "regulation.gov.ru",
    "sozd.duma.gov.ru",
}
