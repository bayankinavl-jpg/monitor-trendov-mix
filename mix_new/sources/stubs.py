"""Заглушки источников, которые пока не реализуем, но для которых уже
зафиксирован интерфейс — добавление в будущем требует только одного
нового модуля, реализующего SourceClient.

eaeu: docs.eaeunion.org — сайт ЕЭК, нестабильная структура, не реализован.
sozd_duma: sozd.duma.gov.ru — robots.txt запрещает обход для всех UA
    кроме Яндекса/Google (`Disallow: /` для `User-agent: *`), и сайт
    представляет собой Angular SPA (данные грузятся через JS). Уважаем
    robots.txt и не скрапим напрямую; номера законопроектов пока
    подтверждаются только через pravo.gov.ru/regulation.gov.ru либо
    новостные наводки (news_check).
"""
from __future__ import annotations

from datetime import date

from sources.base import CandidateAct, SourceClient


class EaeuStubSource(SourceClient):
    name = "eaeu_docs"

    def fetch_candidates(self, since: date, until: date) -> list[CandidateAct]:
        raise NotImplementedError(
            "Источник docs.eaeunion.org пока не реализован — заготовка интерфейса под будущее расширение"
        )


class SozdDumaStubSource(SourceClient):
    name = "sozd_duma"

    def fetch_candidates(self, since: date, until: date) -> list[CandidateAct]:
        raise NotImplementedError(
            "sozd.duma.gov.ru не скрапится: запрещено robots.txt (Disallow: / для большинства UA) "
            "и требует JS-рендеринга (Angular SPA). Заготовка интерфейса под будущее расширение "
            "(например, при появлении официального API/выгрузки)."
        )
