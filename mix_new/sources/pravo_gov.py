"""Источник: publication.pravo.gov.ru — официальное опубликование актов.

ВАЖНО (неопределённость, см. план): точная форма поиска (JSON-эндпоинт или
только серверный HTML) и точный формат постоянной ссылки на текст акта
не были подтверждены вживую — из песочницы, где писался этот код, сайт
был недоступен по сети (TLS-хендшейк не завершался, похоже на блокировку
по IP/geo). Код ниже реализует разумный, изолированный вариант по
документированным публичным сведениям об API портала и должен быть
проверен и при необходимости скорректирован первым запуском из сети,
где сайт доступен (см. `_parse_search_response`, где и только где нужно
менять логику разбора, если реальная форма ответа будет отличаться).
"""
from __future__ import annotations

import time
from datetime import date, datetime

import requests

from config import HTTP_TIMEOUT, HTTP_USER_AGENT, MAX_PAGES_SAFETY_CAP, REQUEST_DELAY_SECONDS
from sources.base import CandidateAct, SourceClient, SourceUnreachableError

SEARCH_API_URL = "https://publication.pravo.gov.ru/api/Documents"
DOCUMENT_PAGE_URL_TEMPLATE = "https://publication.pravo.gov.ru/document/{doc_id}"


class PravoGovSource(SourceClient):
    name = "pravo_gov"

    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": HTTP_USER_AGENT, "Accept": "application/json"})

    def fetch_candidates(self, since: date, until: date) -> list[CandidateAct]:
        candidates: list[CandidateAct] = []
        page = 1
        while page <= MAX_PAGES_SAFETY_CAP:
            try:
                resp = self.session.get(
                    SEARCH_API_URL,
                    params={
                        "SignatoryAuthorityId": "",
                        "DocumentDateStart": since.strftime("%d.%m.%Y"),
                        "DocumentDateEnd": until.strftime("%d.%m.%Y"),
                        "page": page,
                        "pageSize": 50,
                    },
                    timeout=HTTP_TIMEOUT,
                )
                resp.raise_for_status()
            except requests.exceptions.RequestException as exc:
                if page == 1:
                    raise SourceUnreachableError(f"pravo.gov.ru недоступен: {exc}") from exc
                break

            try:
                payload = resp.json()
            except ValueError as exc:
                if page == 1:
                    raise SourceUnreachableError(
                        f"pravo.gov.ru вернул не-JSON ответ — форма API отличается от ожидаемой: {exc}"
                    ) from exc
                break

            items = _parse_search_response(payload)
            if not items:
                break
            candidates.extend(items)
            page += 1
            time.sleep(REQUEST_DELAY_SECONDS)

        return candidates


def _parse_search_response(payload: dict) -> list[CandidateAct]:
    """Единственное место, которое нужно править, если реальная форма
    ответа API publication.pravo.gov.ru отличается от предполагаемой."""
    items = payload.get("items") or payload.get("Items") or []
    result: list[CandidateAct] = []
    for item in items:
        doc_id = item.get("id") or item.get("eoNumber") or item.get("documentId")
        if not doc_id:
            continue
        source_url = DOCUMENT_PAGE_URL_TEMPLATE.format(doc_id=doc_id)
        result.append(
            CandidateAct(
                raw_title=item.get("name") or item.get("title") or "",
                raw_number=item.get("number") or item.get("documentNumber"),
                raw_act_kind=item.get("documentType") or item.get("kind"),
                raw_issuing_body=item.get("signatoryAuthority") or item.get("authority"),
                raw_adoption_date=item.get("documentDate") or item.get("signDate"),
                raw_publication_date=item.get("publishDate") or item.get("publishDateShort"),
                source_url=source_url,
                page_count=item.get("pageCount"),
                raw_text_excerpt=item.get("annotation") or item.get("summary"),
                extra=item,
            )
        )
    return result
