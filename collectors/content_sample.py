"""④ 콘텐츠 표본 크롤. 요구사항 5 대응: 필터 기반 게시글 통계 (로드맵 M3).

이 통계는 사이트 전체가 아니라 수집한 표본(N건, 기본 50) 기준이다.
MD 출력 시 반드시 "샘플 N건 기준, 전체 아님"이라고 명시한다 (report_generator.py 가 처리).
"""

from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import config

if TYPE_CHECKING:
    from playwright.sync_api import Page

logger = logging.getLogger(__name__)

# TODO(M3): 실제 대상 사이트 마크업 확인 후 확정.
POST_ROW_SELECTOR = ".thread-list .thread"
POST_TITLE_SELECTOR = ".title"
POST_AUTHOR_SELECTOR = ".author"
POST_DATE_SELECTOR = "time"


def _load_keywords() -> list[str]:
    path = Path(config.KOREA_KEYWORDS_PATH)
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def collect_posts(page: Page, limit: int = config.CONTENT_SAMPLE_SIZE) -> list[dict[str, str]]:
    """카테고리 목록 페이지에서 상위 N건의 제목/날짜/작성자를 수집한다."""
    rows = page.locator(POST_ROW_SELECTOR).all()[:limit]
    posts = []
    for row in rows:
        try:
            title = row.locator(POST_TITLE_SELECTOR).first.inner_text().strip()
            author = row.locator(POST_AUTHOR_SELECTOR).first.inner_text().strip()
            date = row.locator(POST_DATE_SELECTOR).first.get_attribute("datetime") or ""
        except Exception:  # noqa: BLE001 - 행 구조가 selector와 안 맞는 경우 건너뜀
            logger.debug("게시글 행 파싱 실패, 건너뜀", exc_info=True)
            continue
        posts.append({"title": title, "author": author, "date": date})
    return posts


def run(page: Page, source: dict[str, Any]) -> dict[str, Any]:
    today = dt.date.today().isoformat()
    result: dict[str, Any] = {}

    posts = collect_posts(page)
    result["_표본_게시글"] = posts  # 다른 Collector(user_activity 등)가 재사용

    if not posts:
        result["사용 언어"] = {"state": "BLOCKED", "reason": "표본 게시글 수집 실패"}
        result["한국 관련 유출"] = {"state": "BLOCKED", "reason": "표본 게시글 수집 실패"}
        return result

    # TODO(M3): langdetect 등으로 실제 언어감지 후 비중 집계
    result["사용 언어"] = {
        "value": "TODO(M3): langdetect 비중 집계",
        "observed_at": today,
        "source": f"표본 {len(posts)}건 기준, 전체 아님",
    }

    keywords = _load_keywords()
    matches = [p for p in posts if any(kw in p["title"] for kw in keywords)]
    result["한국 관련 유출"] = {
        "value": f"후보 {len(matches)}건",
        "observed_at": today,
        "source": f"표본 {len(posts)}건 중 키워드 매칭 — 확정 필요",
    }

    return result
