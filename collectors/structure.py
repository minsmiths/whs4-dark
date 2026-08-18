"""② 구조 크롤. 요구사항 3·6 대응: 사이트 구조 파악, 운영 방식 파악 (로드맵 M2).

selector는 대상 사이트의 실제 마크업에 맞춰 조정해야 한다 (예: `nav a`, `.forumbit a`).
개발자 도구·우클릭이 막힌 사이트는 `page.content()`를 파일로 저장해 텍스트 에디터로
확인한다 (브라우저로 다시 열지 않아 안전). curl로 받은 원문과 비교하면 안티봇 챌린지
페이지만 받은 것인지 실제 컨텐츠인지도 구분된다.

MVP는 AI 요약을 쓰지 않는다 — 규칙/FAQ 원문은 요약하지 않고 그대로 인용한다.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.sync_api import Page

logger = logging.getLogger(__name__)

# TODO(M2): 실제 대상 사이트 마크업 확인 후 확정. 지금은 흔한 포럼 구조에 대한 추측값.
NAV_LINK_SELECTOR = "nav a, .forumbit a"
RULES_PAGE_KEYWORDS = ("rules", "faq", "register", "가입", "규칙")


def run(page: Page, source: dict[str, Any]) -> dict[str, Any]:
    today = dt.date.today().isoformat()
    result: dict[str, Any] = {}

    try:
        links = page.locator(NAV_LINK_SELECTOR).all()
    except Exception:  # noqa: BLE001
        result["어떤 곳인지"] = {"state": "BLOCKED", "reason": "nav selector 매칭 실패"}
        return result

    categories = []
    rules_candidates = []
    for link in links:
        try:
            text = (link.inner_text() or "").strip()
            href = link.get_attribute("href") or ""
        except Exception:  # noqa: BLE001 - 개별 요소 stale 등
            logger.debug("nav 링크 파싱 실패, 건너뜀", exc_info=True)
            continue
        if not text:
            continue
        categories.append(text)
        if any(kw in text.lower() or kw in href.lower() for kw in RULES_PAGE_KEYWORDS):
            rules_candidates.append((text, href))

    if categories:
        result["어떤 곳인지"] = {
            "value": ", ".join(dict.fromkeys(categories)),  # 순서 유지 중복 제거
            "observed_at": today,
            "source": "홈페이지 nav 1단계 depth",
        }
    else:
        result["어떤 곳인지"] = {"state": "CONFIRMED_ABSENT"}

    # 규칙/FAQ/가입 페이지 원문 인용 (요약하지 않음, CLAUDE.md §6 요구사항 6)
    if rules_candidates:
        # TODO(M2): href로 이동해 본문 원문(page.inner_text('body'))을 요약 없이 그대로 수집한다.
        result["들어가는 법"] = {"state": "BLOCKED", "reason": "규칙 페이지 원문 수집 미구현"}
    else:
        result["들어가는 법"] = {"state": "CONFIRMED_ABSENT"}

    return result
