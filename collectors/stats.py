"""③ 통계 크롤. 요구사항 4 대응: 사이트 활성화 정도 파악 (로드맵 M3).

포럼 하단 통계 영역("Threads: N, Posts: N, Members: N" 형태)을 우선 시도하고,
없으면 목록 페이지 페이지네이션으로 총 게시글 수를 추정한다. 최근 게시일이
활성도의 실질 지표이므로 반드시 확보한다.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.sync_api import Page

# TODO(M3): 실제 대상 사이트 마크업 확인 후 확정.
STATS_AREA_SELECTOR = ".forum-stats, #stats"
PAGINATION_LAST_SELECTOR = ".pagination li:last-child a"
LATEST_POST_TIMESTAMP_SELECTOR = ".thread-list .thread:first-child time"


def run(page: Page, source: dict[str, Any]) -> dict[str, Any]:
    today = dt.date.today().isoformat()
    result: dict[str, Any] = {}

    stats_locator = page.locator(STATS_AREA_SELECTOR)
    if stats_locator.count() > 0:
        try:
            text = stats_locator.first.inner_text()
            result["규모"] = {"value": text.strip(), "observed_at": today, "source": "포럼 통계 영역"}
        except Exception:  # noqa: BLE001
            result["규모"] = {"state": "BLOCKED", "reason": "통계 영역 파싱 실패"}
    else:
        # 통계 영역이 없으면(또는 로그인 필요) 페이지네이션 기반 추정으로 대체
        pagination = page.locator(PAGINATION_LAST_SELECTOR)
        if pagination.count() > 0:
            result["규모"] = {
                "value": "추정치 — TODO(M3): 마지막 페이지 번호 × 페이지당 항목 수",
                "observed_at": today,
                "source": "페이지네이션 추정",
            }
        else:
            result["규모"] = {"state": "BLOCKED", "reason": "로그인 없이 보이는 화면에 표시되지 않음"}

    latest = page.locator(LATEST_POST_TIMESTAMP_SELECTOR)
    if latest.count() > 0:
        try:
            ts = latest.first.get_attribute("datetime") or latest.first.inner_text()
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
