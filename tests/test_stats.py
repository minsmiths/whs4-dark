"""M3 완료 기준 검증: `규모`(페이지네이션 추정), `상태(신선도)`인 `최근 게시일`.

CLAUDE.md §3-8에 따라 실제 대상 사이트에는 접속하지 않는다 — 로컬 fixture만 사용.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

import site_profiles
from collectors import stats

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def page():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        pg.goto((FIXTURES_DIR / "forum_thread_list.html").as_uri())
        yield pg
        browser.close()


def test_run_estimates_scale_from_pagination_when_stats_area_missing(page):
    result = stats.run(page, source={"url": page.url})

    # 마지막 페이지 42 × 페이지당 5건(fixture의 .thread 5개) = 210
    assert "210" in result["규모"]["value"]
    assert "42" in result["규모"]["value"]
    assert result["규모"]["source"] == "페이지네이션 추정 — 정확한 통계 아님"


def test_run_reads_latest_post_timestamp(page):
    result = stats.run(page, source={"url": page.url})

    assert result["최근 게시일"]["value"] == "2026-08-15"


def test_run_blocked_when_no_stats_and_no_pagination():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        pg.set_content("<html><body><div class='thread-list'></div></body></html>")

        result = stats.run(pg, source={"url": pg.url})

        assert result["규모"] == {"state": "BLOCKED", "reason": "로그인 없이 보이는 화면에 표시되지 않음"}
        assert result["최근 게시일"] == {"state": "CONFIRMED_ABSENT"}
        browser.close()


def test_run_prefers_title_attribute_absolute_time_over_relative_text(monkeypatch):
    """CLAUDE.md §7.1: 상대 시간("2 hours ago") 대신 절대 날짜를 쓴다. darkforums.ru 처럼
    <time datetime=...> 없이 title 속성에만 절대 시각을 담은 테마 대응."""
    monkeypatch.setitem(
        site_profiles.PROFILES,
        "test-platform",
        {"latest_post_timestamp_selector": ".last-post span[title]"},
    )

    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        pg.set_content(
            '<span class="last-post"><span title="19-08-26, 08:29 PM">2 hours ago</span></span>'
        )

        result = stats.run(pg, source={"url": pg.url, "platform": "test-platform"})

        assert result["최근 게시일"]["value"] == "19-08-26, 08:29 PM"
        browser.close()


def test_run_uses_registered_platform_profile_selector(monkeypatch):
    monkeypatch.setitem(site_profiles.PROFILES, "test-platform", {"stats_area_selector": ".real-stats"})

    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        pg.set_content("<div class='real-stats'>Threads: 5, Posts: 12</div>")

        result = stats.run(pg, source={"url": pg.url, "platform": "test-platform"})

        assert result["규모"]["value"] == "Threads: 5, Posts: 12"
        browser.close()
