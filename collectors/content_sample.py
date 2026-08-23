"""④ 콘텐츠 표본 크롤. 요구사항 5 대응: 필터 기반 게시글 통계 (로드맵 M3).

이 통계는 사이트 전체가 아니라 수집한 표본(N건, 기본 50) 기준이다.
MD 출력 시 반드시 "샘플 N건 기준, 전체 아님"이라고 명시한다 (report_generator.py 가 처리).
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Any

import config
import site_profiles

try:
    from langdetect import DetectorFactory, LangDetectException, detect

    DetectorFactory.seed = 0  # 짧은 텍스트에서도 실행마다 같은 결과가 나오도록 고정
except ImportError:  # pragma: no cover - requirements.txt 에 있지만 방어적으로 처리
    detect = None
    LangDetectException = Exception  # type: ignore[assignment,misc]

if TYPE_CHECKING:
    from playwright.sync_api import Page

logger = logging.getLogger(__name__)

# CLAUDE.md §3-4: PII 원문은 저장하지 않는다 — 존재 여부와 유형만 기록한다.
# 아래 정규식은 표본 게시글 "제목"에만 적용한다(본문은 수집 대상이 아님, §5 표 참고).
# 매칭된 문자열 자체는 절대 결과 dict에 담지 않고, 유형 이름(이메일/전화번호)만 기록한다.
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"\b01[0-9]-?\d{3,4}-?\d{4}\b")

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


def collect_posts(
    page: Page, source: dict[str, Any] | None = None, limit: int = config.CONTENT_SAMPLE_SIZE
) -> list[dict[str, str]]:
    """카테고리 목록 페이지에서 상위 N건의 제목/날짜/작성자를 수집한다.

    source가 주어지고 platform 프로파일(site_profiles.py)이 등록돼 있으면 그 선택자를 쓰고,
    없으면 아래 범용 추측 선택자를 그대로 쓴다.
    """
    profile = site_profiles.get_profile(source or {})
    row_selector = profile.get("post_row_selector", POST_ROW_SELECTOR)
    title_selector = profile.get("post_title_selector", POST_TITLE_SELECTOR)
    author_selector = profile.get("post_author_selector", POST_AUTHOR_SELECTOR)
    date_selector = profile.get("post_date_selector", POST_DATE_SELECTOR)

    rows = page.locator(row_selector).all()[:limit]
    posts = []
    for row in rows:
        try:
            title = row.locator(title_selector).first.inner_text().strip()
            author = row.locator(author_selector).first.inner_text().strip()
            date = row.locator(date_selector).first.get_attribute("datetime") or ""
        except Exception:  # noqa: BLE001 - 행 구조가 selector와 안 맞는 경우 건너뜀
            logger.debug("게시글 행 파싱 실패, 건너뜀", exc_info=True)
            continue
        posts.append({"title": title, "author": author, "date": date})
    return posts


def _detect_language_distribution(posts: list[dict[str, str]]) -> Counter[str]:
    """표본 게시글 제목의 언어 비중을 집계한다. 감지 실패(너무 짧은 텍스트 등)는 'unknown'."""
    counts: Counter[str] = Counter()
    for post in posts:
        title = post.get("title", "").strip()
        if not title:
            continue
        try:
            lang = detect(title)
        except LangDetectException:
            lang = "unknown"
        counts[lang] += 1
    return counts


def _detect_pii_types(posts: list[dict[str, str]]) -> list[str]:
    """제목에서 PII 패턴 존재 여부만 확인한다. 매칭된 문자열은 절대 반환하지 않는다(§3-4)."""
    titles = [p.get("title", "") for p in posts]
    types = []
    if any(EMAIL_RE.search(t) for t in titles):
        types.append("이메일")
    if any(PHONE_RE.search(t) for t in titles):
        types.append("전화번호")
    return types


def run(page: Page, source: dict[str, Any]) -> dict[str, Any]:
    today = dt.date.today().isoformat()
    result: dict[str, Any] = {}

    posts = collect_posts(page, source)
    result["_표본_게시글"] = posts  # 다른 Collector(user_activity 등)가 재사용

    if not posts:
        result["사용 언어"] = {"state": "BLOCKED", "reason": "표본 게시글 수집 실패"}
        result["한국 관련 유출"] = {"state": "BLOCKED", "reason": "표본 게시글 수집 실패"}
        result["개인정보 유출"] = {"state": "BLOCKED", "reason": "표본 게시글 수집 실패"}
        return result

    if detect is None:
        result["사용 언어"] = {"state": "BLOCKED", "reason": "langdetect 미설치"}
    else:
        distribution = _detect_language_distribution(posts)
        total = sum(distribution.values())
        if total == 0:
            result["사용 언어"] = {"state": "CONFIRMED_ABSENT"}
        else:
            parts = [
                f"{lang} {count}건({count * 100 // total}%)" for lang, count in distribution.most_common()
            ]
            result["사용 언어"] = {
                "value": ", ".join(parts),
                "observed_at": today,
                "source": f"표본 {len(posts)}건 제목 기준 langdetect, 전체 아님",
            }

    keywords = _load_keywords()
    matches = [p for p in posts if any(kw in p["title"] for kw in keywords)]
    result["한국 관련 유출"] = {
        "value": f"후보 {len(matches)}건",
        "observed_at": today,
        "source": f"표본 {len(posts)}건 중 키워드 매칭 — 확정 필요",
    }

    pii_types = _detect_pii_types(posts)
    if pii_types:
        result["개인정보 유출"] = {
            "value": f"패턴 후보 발견: {', '.join(pii_types)} (원문 미저장, 유형만 기록)",
            "observed_at": today,
            "source": f"표본 {len(posts)}건 제목 기준 정규식 매칭, 본문 미포함 — 확정 필요",
        }
    else:
        result["개인정보 유출"] = {"state": "CONFIRMED_ABSENT"}

    return result
