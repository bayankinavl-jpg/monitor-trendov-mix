"""Источник: regulation.gov.ru — проекты НПА на публичном обсуждении.

ВАЖНО (неопределённость, см. план): точная схема JSON под
regulation.gov.ru/api не была подтверждена вживую — DNS-имя сайта не
резолвилось из песочницы, где писался этот код. Логика разбора ответа
изолирована в `_parse_item`/`_list_page`, чтобы при расхождении с реальным
форматом исправление не затрагивало остальной пайплайн.
"""
from __future__ import annotations

import time
from datetime import date

import requests

from config import HTTP_TIMEOUT, HTTP_USER_AGENT, MAX_PAGES_SAFETY_CAP, REQUEST_DELAY_SECONDS
from sources.base import CandidateAct, SourceClient, SourceUnreachableError

LIST_API_URL = "https://regulation.gov.ru/api/public/npa"
PROJECT_PAGE_URL_TEMPLATE = "https://regulation.gov.ru/projects#npa={project_id}"


class RegulationGovSource(SourceClient):
    name = "regulation_gov"

    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": HTTP_USER_AGENT, "Accept": "application/json"})

    def fetch_candidates(self, since: date, until: date) -> list[CandidateAct]:
        candidates: list[CandidateAct] = []
        page = 0
        while page < MAX_PAGES_SAFETY_CAP:
            try:
                payload = self._list_page(page, since, until)
            except requests.exceptions.RequestException as exc:
                if page == 0:
                    raise SourceUnreachableError(f"regulation.gov.ru недоступен: {exc}") from exc
                break

            if payload is None:
                break

            items = [_parse_item(raw) for raw in payload.get("items", payload.get("content", []))]
            items = [i for i in items if i is not None]
            if not items:
                break
            candidates.extend(items)
            page += 1
            time.sleep(REQUEST_DELAY_SECONDS)

        return candidates

    def _list_page(self, page: int, since: date, until: date) -> dict | None:
        resp = self.session.get(
            LIST_API_URL,
            params={
                "page": page,
                "size": 50,
                "dateFrom": since.isoformat(),
                "dateTo": until.isoformat(),
            },
            timeout=HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        try:
            return resp.json()
        except ValueError as exc:
            raise SourceUnreachableError(
                f"regulation.gov.ru вернул не-JSON ответ — форма API отличается от ожидаемой: {exc}"
            ) from exc


def _parse_item(item: dict) -> CandidateAct | None:
    project_id = item.get("id") or item.get("projectId")
    if not project_id:
        return None
    source_url = item.get("textUrl") or PROJECT_PAGE_URL_TEMPLATE.format(project_id=project_id)
    return CandidateAct(
        raw_title=item.get("title") or item.get("name") or "",
        raw_number=item.get("number"),
        raw_act_kind=item.get("npaType") or item.get("kind"),
        raw_issuing_body=item.get("department") or item.get("authority"),
        raw_adoption_date=item.get("createDate") or item.get("publishDate"),
        raw_publication_date=item.get("publishDate"),
        source_url=source_url,
        page_count=item.get("pageCount"),
        raw_text_excerpt=item.get("description") or item.get("annotation"),
        extra=item,
    )
