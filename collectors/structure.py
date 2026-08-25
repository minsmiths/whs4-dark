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
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

import config
import site_profiles
import snapshot

if TYPE_CHECKING:
    from playwright.sync_api import Page

logger = logging.getLogger(__name__)

# TODO(M2): 실제 대상 사이트 마크업 확인 후 확정. 지금은 흔한 포럼 구조에 대한 추측값.
# whitelist.yaml에 platform이 지정돼 있고 site_profiles.py에 프로파일이 등록돼 있으면
# 아래 기본값 대신 그 값을 쓴다 (site_profiles.py 참고).
NAV_LINK_SELECTOR = "nav a, .forumbit a"
RULES_PAGE_KEYWORDS = ("rules", "faq", "register", "가입", "규칙")

# myBB 계열 사이트는 로그인한 계정에 쪽지가 있으면 "규칙/FAQ" 페이지 본문 영역(rules_content_selector,
# 보통 #content) 맨 위에도 계정 전용 쪽지함 알림 배너(#pm_notice)가 같이 렌더링된다. 이건 "규칙
# 페이지 원문"이 아니라 그 순간 로그인한 계정의 사적인 알림(발신자·쪽지 제목 포함)이라 CLAUDE.md
# §6 요구사항 6("원문 그대로 인용")의 "원문"과 무관한 노이즈다 — darkforums 실크롤(2026-08-24)에서
# "You have 13 unread private messages. The most recent is from Asaryumor titled ..."가 그대로
# "들어가는 법" 칸 맨 앞에 섞여 나온 걸 확인(2026-08-25, 사람 리뷰로 발견). myBB 표준 문구라 사이트
# 프로파일 없이도(darkforums 외 다른 myBB 대상에도) 범용으로 걸러낸다.
PM_NOTICE_RE = re.compile(r"^You have \d+ unread private messages?\..*$", re.MULTILINE)


def _source_id(source: dict[str, Any]) -> str:
    return source.get("name") or source.get("url", "unknown")


def discover_categories(page: Page, profile: dict[str, str]) -> list[dict[str, str]]:
    """현재 page에서 카테고리(서브포럼) 링크를 [{"text":..., "url": 절대주소}, ...]로 뽑는다.

    계정/알림 메뉴로 보이는 텍스트는 제외한다(NAV_ACCOUNT_MENU_KEYWORDS). run()의
    "어떤 곳인지" 계산과 content_sample.crawl_site()의 재귀 탐색(하위 서브포럼 발견)이
    이 함수를 공통으로 쓴다 — 로직을 두 곳에 중복해서 두지 않기 위해서다.
    """
    nav_selector = profile.get("nav_link_selector", NAV_LINK_SELECTOR)
    try:
        links = page.locator(nav_selector).all()
    except Exception:  # noqa: BLE001
        return []

    origin_url = page.url
    seen_text: set[str] = set()
    categories: list[dict[str, str]] = []
    for link in links:
        try:
            text = (link.inner_text() or "").strip()
            href = link.get_attribute("href") or ""
        except Exception:  # noqa: BLE001 - 개별 요소 stale 등
            logger.debug("nav 링크 파싱 실패, 건너뜀", exc_info=True)
            continue
        if not text or text in seen_text:
            continue
        if any(kw in text.lower() for kw in config.NAV_ACCOUNT_MENU_KEYWORDS):
            continue
        seen_text.add(text)
        categories.append({"text": text, "url": urljoin(origin_url, href) if href else ""})
    return categories


def run(page: Page, source: dict[str, Any]) -> dict[str, Any]:
    today = dt.date.today().isoformat()
    result: dict[str, Any] = {}
    profile = site_profiles.get_profile(source)
    nav_selector = profile.get("nav_link_selector", NAV_LINK_SELECTOR)
    # 규칙/FAQ 링크는 카테고리 목록과 다른 위치(예: 사이트 상단 메뉴)에 있는 경우가 많다
    # (darkforums.ru 사례: 진짜 카테고리는 `.forums__forum-name`, 규칙 링크는 `.sidenav__menu`
    # 안에 있었다). 프로파일에 따로 없으면 기존처럼 nav_selector와 같은 곳에서 찾는다.
    rules_link_selector = profile.get("rules_link_selector", nav_selector)

    category_entries = discover_categories(page, profile)
    # 하위 서브포럼 재귀 순회(content_sample.crawl_site)는 href가 있어야 의미가 있다.
    # "어떤 곳인지" 표시용 카테고리 이름은 href 없이 텍스트만 있어도 그대로 보여준다(기존 동작 유지).
    result["_사이트_카테고리_시드"] = [c for c in category_entries if c["url"]]
    categories = [c["text"] for c in category_entries]

    rules_candidates = []
    try:
        rule_links = page.locator(rules_link_selector).all()
    except Exception:  # noqa: BLE001
        rule_links = []
    for link in rule_links:
        try:
            text = (link.inner_text() or "").strip()
            href = link.get_attribute("href") or ""
        except Exception:  # noqa: BLE001 - 개별 요소 stale 등
            logger.debug("규칙 링크 파싱 실패, 건너뜀", exc_info=True)
            continue
        if text and any(kw in text.lower() or kw in href.lower() for kw in RULES_PAGE_KEYWORDS):
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
    # 주의: 결과 키는 "들어가는 법"이 아니라 "_들어가는_법_구조"다. 이 필드는
    # AUTO-append 소유(access_probe.py 도 같은 목적의 값을 채운다) — investigate.py가
    # 두 Collector의 결과를 하나로 합쳐 "들어가는 법"으로 만든다(덮어쓰기 방지).
    if rules_candidates:
        text, href = rules_candidates[0]
        origin_url = page.url
        target_url = urljoin(origin_url, href)
        content_selector = profile.get("rules_content_selector", "body")
        try:
            page.goto(target_url, timeout=config.PAGE_LOAD_TIMEOUT_MS, wait_until=config.PAGE_WAIT_UNTIL)
            body_text = page.inner_text(content_selector).strip()
            # 쪽지함 알림 노이즈 제거 후 그 자리에 남는 빈 줄도 같이 정리한다(§ 위 PM_NOTICE_RE 주석).
            body_text = re.sub(r"\n{3,}", "\n\n", PM_NOTICE_RE.sub("", body_text)).strip()
            snapshot.save_snapshot(page, _source_id(source), "structure_rules_page")
            if len(body_text) > config.RULES_TEXT_MAX_CHARS:
                body_text = body_text[: config.RULES_TEXT_MAX_CHARS] + " …(이하 생략, 스냅샷 참고)"
            result["_들어가는_법_구조"] = {
                "value": body_text,
                "observed_at": today,
                "source": f'규칙/FAQ 페이지 원문 그대로 인용 ("{text}", {target_url})',
            }
        except Exception:  # noqa: BLE001 - 규칙 페이지 접속 실패 전반
            logger.debug("규칙 페이지 원문 수집 실패", exc_info=True)
            result["_들어가는_법_구조"] = {"state": "BLOCKED", "reason": "규칙 페이지 접속 실패"}
        finally:
            try:
                page.goto(origin_url, timeout=config.PAGE_LOAD_TIMEOUT_MS, wait_until=config.PAGE_WAIT_UNTIL)
            except Exception:  # noqa: BLE001 - 원래 페이지 복귀 실패해도 파이프라인은 계속
                logger.warning("규칙 페이지 조회 후 원래 페이지로 복귀 실패: %s", origin_url)
    else:
        result["_들어가는_법_구조"] = {"state": "CONFIRMED_ABSENT"}

    return result
