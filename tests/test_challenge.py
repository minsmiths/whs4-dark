"""challenge.detect() 검증 (CLAUDE.md §4.2-6 — 감지만 한다, 우회는 안 함).

CLAUDE.md §3-8에 따라 실제 대상 사이트에는 접속하지 않는다 — page.set_content()로
로컬 HTML만 렌더링한다.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright

import challenge
import config


class _Response:
    def __init__(self, status: int):
        self.status = status


def test_detects_rate_limit_http_status(page):
    page.set_content("<html><body>ordinary-looking response</body></html>")

    assert challenge.detect(page, _Response(429)) == "HTTP 429"
    assert challenge.detect(page, _Response(503)) == "HTTP 503"
    assert challenge.detect(page, _Response(200)) is None


def test_detects_403_as_challenge_status(page):
    """DDoS-Guard/WAF가 챌린지를 200이 아니라 403으로 주는 경우 — 2026-08-27 cracked.st
    실크롤에서 사이트 전체 순회가 카테고리마다 조용히 실패로 갈리던 원인 중 하나."""
    page.set_content("<html><body>forbidden</body></html>")

    assert challenge.detect(page, _Response(403)) == "HTTP 403"


@pytest.fixture
def page():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        yield pg
        browser.close()


def test_detect_matches_cloudflare_title_keyword(page):
    page.set_content("<html><head><title>Just a moment...</title></head><body></body></html>")
    assert challenge.detect(page) == "Just a moment"


def test_detect_matches_title_less_rate_limit_body(page):
    """2026-08-26 pwnforums 실크롤: title 태그가 아예 없고 짧은 본문("Slow down now")만
    있는 속도 제한 응답 — title 기반 검사만으론 못 잡는다."""
    page.set_content(
        '<html><head></head><body><pre style="white-space: pre-wrap;">Slow down now</pre></body></html>'
    )
    assert challenge.detect(page) == "slow down"


def test_detect_ignores_long_real_page_even_if_keyword_appears_in_a_post_title(page):
    """오탐 방지: 실제 게시판 페이지처럼 본문이 긴 경우엔, 게시글 제목에 우연히 "slow down"이
    섞여 있어도 챌린지로 오판하지 않는다(config.CHALLENGE_BODY_MAX_CHARS 초과)."""
    padding = "Normal forum content. " * 30  # CHALLENGE_BODY_MAX_CHARS(200자)를 넉넉히 넘긴다
    page.set_content(f"<html><head><title>Forum</title></head><body>{padding} slow down</body></html>")
    assert challenge.detect(page) is None


def test_detect_returns_none_for_normal_page(page):
    page.set_content("<html><head><title>Home</title></head><body>Welcome</body></html>")
    assert challenge.detect(page) is None


def test_detect_body_check_is_case_insensitive(page):
    page.set_content("<html><head></head><body>SLOW DOWN NOW</body></html>")
    assert challenge.detect(page) == "slow down"


def test_challenge_body_max_chars_is_a_positive_int():
    assert isinstance(config.CHALLENGE_BODY_MAX_CHARS, int)
    assert config.CHALLENGE_BODY_MAX_CHARS > 0


def test_detects_ddos_guard_title(page):
    page.set_content("<html><head><title>DDoS-Guard</title></head><body>Checking</body></html>")
    assert challenge.detect(page) == "DDoS-Guard"


def test_detects_ddos_guard_interstitial_without_title(page):
    """DDoS-Guard 인터스티셜은 title 없이 짧은 안내문만 있는 경우가 있다 —
    body 키워드로도 잡아야 crawl_site()가 조용히 빈 결과를 내지 않는다."""
    page.set_content(
        "<html><head></head><body>Checking your browser before accessing. "
        "Protected by DDoS-Guard</body></html>"
    )
    assert challenge.detect(page) in {"ddos-guard", "checking your browser"}
