"""Дедупликация новостей (шаг 4 ТЗ): точное совпадение по нормализованной
ссылке, затем кластеризация близких заголовков из разных СМИ в одну
запись. Перепечатка новости агентства в другом издании считается тем же
источником, что и агентство (правило 6 раздела «Источники новостей»)."""
from __future__ import annotations

import difflib
from dataclasses import dataclass, field

from pipeline.classify_news import extract_act_requisites
from pipeline.normalize import normalize_text, normalize_url
from sources.news_scan import NewsLead

FUZZY_TITLE_THRESHOLD = 0.6

# Распознаём упоминание агентства в тексте перепечатки, чтобы считать её
# тем же источником, что и агентство, а не отдельным независимым СМИ.
AGENCY_NAME_HINTS = {
    "tass": ["тасс"],
    "interfax": ["интерфакс"],
    "kommersant": ["коммерсант"],
    "vedomosti": ["ведомост"],
    "rbc": ["рбк"],
}


@dataclass
class NewsCluster:
    title: str
    links: list[str] = field(default_factory=list)
    canonical_sources: list[str] = field(default_factory=list)
    leads: list[NewsLead] = field(default_factory=list)


def canonical_source(lead: NewsLead) -> str:
    text = normalize_text(f"{lead.title} {lead.annotation}")
    for agency, hints in AGENCY_NAME_HINTS.items():
        if agency == lead.source_name:
            continue
        if any(hint in text for hint in hints):
            return agency
    return lead.source_name


def same_act_possible(title_a: str, title_b: str) -> bool:
    """Заголовки разных актов бывают почти одинаковыми («… № 2826-р» и
    «… № 2827-р»). Если в обоих указан номер акта и номера разные, это
    разные акты, даже при похожих заголовках."""
    number_a, _ = extract_act_requisites(title_a)
    number_b, _ = extract_act_requisites(title_b)
    return not (number_a and number_b and number_a != number_b)


def cluster_leads(leads: list[NewsLead]) -> list[NewsCluster]:
    clusters: list[NewsCluster] = []
    cluster_by_link: dict[str, NewsCluster] = {}

    for lead in leads:
        norm_link = normalize_url(lead.link)

        cluster = cluster_by_link.get(norm_link)
        if cluster is None:
            for candidate in clusters:
                if not same_act_possible(candidate.title, lead.title):
                    continue
                score = difflib.SequenceMatcher(None, candidate.title.lower(), lead.title.lower()).ratio()
                if score >= FUZZY_TITLE_THRESHOLD:
                    cluster = candidate
                    break

        if cluster is None:
            cluster = NewsCluster(title=lead.title)
            clusters.append(cluster)

        if norm_link not in cluster.links:
            cluster.links.append(norm_link)
        src = canonical_source(lead)
        if src not in cluster.canonical_sources:
            cluster.canonical_sources.append(src)
        cluster.leads.append(lead)
        cluster_by_link[norm_link] = cluster

    return clusters


def independent_source_count(cluster: NewsCluster) -> int:
    return len(cluster.canonical_sources)
