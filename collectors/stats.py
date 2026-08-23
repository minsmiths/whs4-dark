"""③ 통계 크롤. 요구사항 4 대응: 사이트 활성화 정도 파악 (로드맵 M3).

포럼 하단 통계 영역("Threads: N, Posts: N, Members: N" 형태)을 우선 시도하고,
없으면 목록 페이지 페이지네이션으로 총 게시글 수를 추정한다. 최근 게시일이
활성도의 실질 지표이므로 반드시 확보한다.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from typing import TYPE_CHECKING, Any

import site_profiles
from collectors import content_sample

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

logger = logging.getLogger(__name__)

# TODO(M3): 실제 대상 사이트 마크업 확인 후 확정.
STATS_AREA_SELECTOR = ".forum-stats, #stats"
PAGINATION_LAST_SELECTOR = ".pagination li:last-child a"
LATEST_POST_TIMESTAMP_SELECTOR = ".thread-list .thread:first-child time"


def _parse_last_page_number(pagination: Locator) -> int | None:
    """페이지네이션 마지막 링크에서 페이지 번호를 뽑는다. 텍스트("42") 우선, 실패하면 href의
    `page=42` 형태 쿼리스트링을 본다. 둘 다 실패하면 추정 불가(None)."""
    try:
        text = pagination.first.inner_text().strip()
        match = re.search(r"\d+", text)
        if match:
            return int(match.group(0))
    except Exception:  # noqa: BLE001
        logger.debug("페이지네이션 텍스트 파싱 실패", exc_info=True)

    try:
        href = pagination.first.get_attribute("href") or ""
        match = re.search(r"(?:page|p)=(\d+)", href)
        if match:
            return int(match.group(1))
    except Exception:  # noqa: BLE001
        logger.debug("페이지네이션 href 파싱 실패", exc_info=True)

    return None


def run(page: Page, source: dict[str, Any]) -> dict[str, Any]:
    today = dt.date.today().isoformat()
    result: dict[str, Any] = {}
    profile = site_profiles.get_profile(source)
    stats_selector = profile.get("stats_area_selector", STATS_AREA_SELECTOR)
    pagination_selector = profile.get("pagination_last_selector", PAGINATION_LAST_SELECTOR)
    latest_selector = profile.get("latest_post_timestamp_selector", LATEST_POST_TIMESTAMP_SELECTOR)
    post_row_selector = profile.get("post_row_selector", content_sample.POST_ROW_SELECTOR)

    stats_locator = page.locator(stats_selector)
    if stats_locator.count() > 0:
        try:
            text = stats_locator.first.inner_text()
            result["규모"] = {"value": text.strip(), "observed_at": today, "source": "포럼 통계 영역"}
        except Exception:  # noqa: BLE001
            result["규모"] = {"state": "BLOCKED", "reason": "통계 영역 파싱 실패"}
    else:
        # 통계 영역이 없으면(또는 로그인 필요) 페이지네이션 기반 추정으로 대체
        pagination = page.locator(pagination_selector)
        if pagination.count() > 0:
            last_page = _parse_last_page_number(pagination)
            items_per_page = page.locator(post_row_selector).count()
            if last_page and items_per_page:
                estimate = last_page * items_per_page
                result["규모"] = {
                    "value": (
                        f"추정 약 {estimate}건 (마지막 페이지 {last_page} × 페이지당 {items_per_page}건)"
                    ),
                    "observed_at": today,
                    "source": "페이지네이션 추정 — 정확한 통계 아님",
                }
            else:
                result["규모"] = {"state": "BLOCKED", "reason": "페이지네이션 숫자 파싱 실패"}
        else:
            result["규모"] = {"state": "BLOCKED", "reason": "로그인 없이 보이는 화면에 표시되지 않음"}

    latest = page.locator(latest_selector)
    if latest.count() > 0:
        try:
            # CLAUDE.md §7.1: 상대 시간("2 hours ago") 대신 항상 절대 날짜를 쓴다. HTML5
            # <time datetime="..."> 를 우선 보고, 없으면 title 속성(툴팁으로 절대 시각을 넣어두는
            # 테마가 흔함, darkforums.ru Knox 테마도 이 경우다)을 본다. 둘 다 없으면 화면에
            # 보이는 텍스트를 그대로 쓴다 — 상대 시간일 수 있으니 사람이 검토해야 한다.
            ts = (
                latest.first.get_attribute("datetime")
                or latest.first.get_attribute("title")
                or latest.first.inner_text()
            )
            result["최근 게시일"] = {
                "value": ts,
                "observed_at": today,
                "source": "목록 첫 페이지 최상단 게시글",
            }
        except Exception:  # noqa: BLE001
            result["최근 게시일"] = {"state": "BLOCKED", "reason": "타임스탬프 파싱 실패"}
    else:
        result["최근 게시일"] = {"state": "CONFIRMED_ABSENT"}

    return result
