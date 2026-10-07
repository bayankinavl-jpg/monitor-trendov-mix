"""Общие константы проекта."""
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
EXPORTS_DIR = DATA_DIR / "exports"
MAIN_DB_PATH = DATA_DIR / "registry.sqlite3"
SMOKE_DB_PATH = DATA_DIR / "smoke_test_registry.sqlite3"

# Окно вступления в силу, которое интересует реестр.
FORCE_WINDOW_START = date(2026, 1, 1)
FORCE_WINDOW_END = date(2028, 12, 31)

# Ведомства и органы, акты которых собираем (п. 3-4 ТЗ).
ISSUER_WHITELIST = {
    "Евразийская экономическая комиссия",
    "ЕЭК",
    "Государственная Дума",
    "Совет Федерации",
    "Правительство Российской Федерации",
    "Правительство РФ",
    "Минпромторг",
    "Минфин",
    "ФНС",
    "ФТС",
    "Минсельхоз",
    "Россельхознадзор",
    "Роспотребнадзор",
    "Минстрой",
    "Росстандарт",
    "Минприроды",
}

HTTP_TIMEOUT = 15
HTTP_USER_AGENT = "AI-Lab-RegTracker/0.1 (+regulatory change registry for internal bank use)"
REQUEST_DELAY_SECONDS = 0.7
MAX_PAGES_SAFETY_CAP = 50

# Ключевые слова для отбрасывания актов без нормативной сути (п. "Чего не делать").
# Элемент — строка (ищется как подстрока) либо кортеж строк (все основы
# должны встретиться в тексте — учитывает разные падежи/окончания).
DISCARD_KEYWORDS = [
    "о назначении", "о награждении", "о присвоении звания", "о поощрении",
    "о выделении бюджетных средств", "о распределении субсидий",
    ("техническ", "правк"),
]

# Признаки "сквозного" акта.
CROSS_CUTTING_KEYWORDS = [
    "всех налогоплательщиков", "всех работодателей",
    "вне зависимости от вида деятельности", "независимо от применяемой системы налогообложения",
]

# Признаки продления срока (не создаёт новую карточку, обновляет существующую).
DEADLINE_EXTENSION_KEYWORDS = [
    "продлить срок", "продлении срока", "перенести срок", "перенос срока",
    "срок действия ... до", "продлевается до",
]

RSS_FEEDS = {
    "rbc": "https://www.rbc.ru/rbcfreenews/rss.xml",
    "kommersant": "https://www.kommersant.ru/RSS/news.xml",
    "interfax": "https://www.interfax.ru/rss.asp",
    "tass": "https://tass.ru/rss/v2.xml",
    "vedomosti": "https://www.vedomosti.ru/rss/news",
    "garant": "https://www.garant.ru/rss/news.rss",
    "consultant": "https://www.consultant.ru/rss/fed.xml",
    "agroinvestor": "https://www.agroinvestor.ru/rss/",
    "retail_ru": "https://www.retail.ru/rss/",
}

# Ключевые слова для грубой фильтрации новостных заголовков на релевантность
# теме "опт и производство" + регуляторика. Чисто сигнальный фильтр, не финальный.
NEWS_RELEVANCE_KEYWORDS = [
    "закон", "законопроект", "постановлен", "приказ", "регламент", "ставк",
    "налог", "пошлин", "маркировк", "сертификац", "технический регламент",
    "перечень товаров", "опт", "производств", "промышленност",
]
