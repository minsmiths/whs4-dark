"""Cloudflare 등 안티봇 챌린지 감지 공통 유틸 (CLAUDE.md §4.2-6).

"챌린지 감지는 최초 로그인 시점뿐만 아니라 크롤링 도중 모든 요청에서 상시로 수행한다.
재발해도 자동 우회 코드는 만들지 않고 그때마다 VNC로 사람이 다시 푼다." — 이 모듈은
"감지"만 한다. 우회/재시도는 절대 하지 않는다. 감지되면 호출부(content_sample.crawl_site 등)가
크롤링을 멈추고 사람에게 넘긴다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import config

if TYPE_CHECKING:
    from playwright.sync_api import Page


def detect(page: Page) -> str | None:
    """현재 page가 챌린지 화면으로 보이면 매칭된 키워드를 반환한다. 아니면 None."""
    try:
        title = page.title()
    except Exception:  # noqa: BLE001 - 페이지 상태가 불안정할 수 있음
        title = ""
    lowered = title.lower()
    for keyword in config.CHALLENGE_TITLE_KEYWORDS:
        if keyword.lower() in lowered:
            return keyword
    return None
