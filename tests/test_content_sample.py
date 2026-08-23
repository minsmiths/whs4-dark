"""M3 완료 기준 검증: `사용 언어`, `한국 관련 유출`(후보), 표본 50건 미만에서도 에러 없이 동작.
+ CLAUDE.md §3-4 PII 존재/유형만 기록(원문 미저장) 검증.

CLAUDE.md §3-8에 따라 실제 대상 사이트에는 접속하지 않는다 — 로컬 fixture만 사용.
fixture 속 이메일/전화번호는 PII 탐지 로직 검증용 가짜 예시이며 실존 정보가 아니다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

import site_profiles
from collectors import content_sample

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def page():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        pg.goto((FIXTURES_DIR / "forum_thread_list.html").as_uri())
        yield pg
        browser.close()


def test_collect_posts_reads_title_author_date(page):
    posts = content_sample.collect_posts(page)

    assert len(posts) == 5
    assert posts[0] == {
        "title": "Leaked korea database dump",
        "author": "Max987",
        "date": "2026-08-15",
    }


def test_run_language_distribution_covers_every_sampled_post(page):
    result = content_sample.run(page, source={"url": page.url})

    counts = [int(n) for n in re.findall(r"(\d+)건", result["사용 언어"]["value"])]
    assert sum(counts) == 5  # 표본 5건 전부 언어감지 결과에 반영됨
    assert "표본 5건" in result["사용 언어"]["source"]


def test_run_korea_keyword_candidate_is_not_auto_confirmed(page):
    result = content_sample.run(page, source={"url": page.url})

    # "Leaked korea database dump" 한 건만 keywords/korea_keywords.txt 와 매칭된다.
    assert result["한국 관련 유출"]["value"] == "후보 1건"
    assert "확정" in result["한국 관련 유출"]["source"]  # 자동 확정 아님이 명시됨


def test_run_detects_pii_types_without_storing_raw_match(page):
    result = content_sample.run(page, source={"url": page.url})

    pii = result["개인정보 유출"]
    assert "이메일" in pii["value"]
    assert "전화번호" in pii["value"]
    assert "test@example.com" not in pii["value"]  # 매칭된 원문은 절대 담지 않는다
    assert "010-1234-5678" not in pii["value"]


def test_run_confirmed_absent_pii_when_no_pattern_matches():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        pg.set_content(
            """
            <div class="thread-list">
              <div class="thread">
                <span class="title">Just a normal title</span>
                <span class="author">someone</span>
                <time datetime="2026-08-01">2026-08-01</time>
              </div>
            </div>
            """
        )

        result = content_sample.run(pg, source={"url": pg.url})

        assert result["개인정보 유출"] == {"state": "CONFIRMED_ABSENT"}
        browser.close()


def test_run_handles_fewer_than_50_posts_without_error():
    """표본 50건 미만에서도 에러 없이 동작해야 한다 (M3 완료 기준)."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        pg.set_content("<div class='thread-list'></div>")  # 게시글 0건

        result = content_sample.run(pg, source={"url": pg.url})

        assert result["_표본_게시글"] == []
        assert result["사용 언어"] == {"state": "BLOCKED", "reason": "표본 게시글 수집 실패"}
        assert result["개인정보 유출"] == {"state": "BLOCKED", "reason": "표본 게시글 수집 실패"}
        browser.close()


def test_collect_posts_uses_registered_platform_profile_selectors(monkeypatch):
    monkeypatch.setitem(
        site_profiles.PROFILES,
        "test-platform",
        {
            "post_row_selector": ".real-thread",
            "post_title_selector": ".t",
            "post_author_selector": ".a",
            "post_date_selector": ".d",
        },
    )

    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        pg.set_content(
            """
            <div class="thread-list"><div class="thread">
              <span class="title">이건 무시돼야 함</span>
              <span class="author">ignored</span><time datetime="2026-01-01"></time>
            </div></div>
            <div class="real-thread">
              <span class="t">Real Title</span>
              <span class="a">RealAuthor</span>
              <span class="d" datetime="2026-08-19"></span>
            </div>
            """
        )

        posts = content_sample.collect_posts(pg, source={"platform": "test-platform"})

        assert posts == [{"title": "Real Title", "author": "RealAuthor", "date": "2026-08-19"}]
        browser.close()
