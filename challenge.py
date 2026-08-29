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
    from playwright.sync_api import Page, Response


def detect(page: Page, response: Response | None = None) -> str | None:
    """현재 page가 챌린지/차단 화면으로 보이면 매칭된 키워드를 반환한다. 아니면 None.

    HTTP 상태 코드, title 태그 기반(Cloudflare 등), 본문 텍스트 기반(속도 제한 등, title 자체가 없는
    경우가 많다) 두 가지를 모두 본다 — 2026-08-26 pwnforums 실크롤에서 title 없는
    "Slow down now" 류 응답이 감지 안 돼 크롤이 조용히 빈 결과를 냈던 사고 이후 추가.
    """
    # 차단 페이지가 일정한 문구나 title을 주지 않아도 429/503 자체는 명확한 중단 신호다.
    # 재시도는 하지 않고 호출부가 체크포인트를 저장한 뒤 사람에게 넘긴다.
    response_status = getattr(response, "status", None)
    if response_status in config.CHALLENGE_HTTP_STATUSES:
        return f"HTTP {response_status}"

    try:
        title = page.title()
    except Exception:  # noqa: BLE001 - 페이지 상태가 불안정할 수 있음
        title = ""
    lowered_title = title.lower()
    for keyword in config.CHALLENGE_TITLE_KEYWORDS:
        if keyword.lower() in lowered_title:
            return keyword

    try:
        body_text = page.inner_text("body")
    except Exception:  # noqa: BLE001 - 페이지 상태가 불안정할 수 있음
        body_text = ""
    # 실제 게시판 페이지는 nav/게시글 목록/footer가 다 들어가 본문이 길다 — "slow down" 같은
    # 흔한 문구가 실제 게시글 제목에 우연히 섞여 있어도 오탐하지 않도록, 본문 전체가 아주 짧은
    # (차단 안내 페이지 특유의) 경우에만 이 검사를 적용한다.
    stripped_body = body_text.strip()
    if stripped_body and len(stripped_body) <= config.CHALLENGE_BODY_MAX_CHARS:
        lowered_body = stripped_body.lower()
        for keyword in config.CHALLENGE_BODY_KEYWORDS:
            if keyword.lower() in lowered_body:
                return keyword

    return None
