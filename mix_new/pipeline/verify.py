"""Жёсткое правило: карточка без рабочей ссылки на первоисточник не
становится обычной карточкой — только «не подтверждено»."""
from __future__ import annotations

import requests

from config import HTTP_TIMEOUT, HTTP_USER_AGENT
from sources.base import CandidateAct


def verify_primary_source(candidate: CandidateAct, check_reachability: bool = True) -> tuple[bool, str | None]:
    """Возвращает (ok, reason). ok=False — не хватает ссылки или она не
    открывается; карточка в этом случае создаётся со статусом
    "не подтверждено", а не отбрасывается молча."""
    if not candidate.source_url:
        return False, "нет ссылки на первоисточник"

    if not check_reachability:
        return True, None

    try:
        resp = requests.head(
            candidate.source_url,
            timeout=HTTP_TIMEOUT,
            headers={"User-Agent": HTTP_USER_AGENT},
            allow_redirects=True,
        )
        if resp.status_code >= 400:
            resp = requests.get(
                candidate.source_url,
                timeout=HTTP_TIMEOUT,
                headers={"User-Agent": HTTP_USER_AGENT},
                allow_redirects=True,
            )
        if resp.status_code >= 400:
            return False, f"ссылка на первоисточник не открывается (HTTP {resp.status_code})"
    except requests.exceptions.RequestException as exc:
        return False, f"ссылка на первоисточник недоступна: {exc}"

    return True, None
