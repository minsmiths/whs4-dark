"""M2 완료 기준 검증: `어떤 곳인지`, `들어가는 법`(구조 단계 부분) 필드,
snapshot 저장을 로컬 fixture(tests/fixtures/forum_home.html)로 검증한다.

CLAUDE.md §3-8에 따라 실제 대상 사이트에는 접속하지 않는다 — file:// 로 연 로컬 fixture만 사용.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

import config
import site_profiles
from collectors import structure

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def _open(browser, filename: str):
    context = browser.new_context()
    page = context.new_page()
    page.goto((FIXTURES_DIR / filename).as_uri())
    return context, page


def test_run_collects_nav_categories_and_rules_text(tmp_path, monkeypatch, browser):
    monkeypatch.setattr(config, "SNAPSHOTS_DIR", str(tmp_path))
    context, page = _open(browser, "forum_home.html")
    origin_url = page.url

    result = structure.run(page, source={"name": "example-forum", "url": origin_url})

    assert "General Discussion" in result["어떤 곳인지"]["value"]
    assert "Market" in result["어떤 곳인지"]["value"]

    rules = result["_들어가는_법_구조"]
    assert "가입은 초대 코드" in rules["value"]  # 원문 그대로 인용, 요약 아님

    # 규칙 페이지를 보고 나서 원래 페이지로 복귀해야 다음 Collector가 정상 동작한다.
    assert page.url == origin_url

    context.close()


def test_run_strips_pm_notice_noise_from_rules_text(tmp_path, monkeypatch, browser):
    """실사고 회귀 테스트(2026-08-25): myBB 쪽지함 알림 배너("You have N unread private
    messages...")가 규칙 페이지 본문(rules_content_selector, 보통 #content) 안에 같이
    렌더링돼서 "들어가는 법" 칸 맨 앞에 그대로 섞여 나온 걸 사람 리뷰로 발견했다. 이건 그
    순간 로그인한 계정의 사적 알림이지 "규칙 원문"이 아니다.
    """
    monkeypatch.setattr(config, "SNAPSHOTS_DIR", str(tmp_path))
    context, page = _open(browser, "forum_home_pm_notice.html")

    result = structure.run(page, source={"name": "example-forum", "url": page.url})

    rules_text = result["_들어가는_법_구조"]["value"]
    assert "unread private messages" not in rules_text
    assert "Asaryumor" not in rules_text
    assert "가입은 초대 코드" in rules_text  # 진짜 규칙 본문은 그대로 남는다

    context.close()


def test_run_saves_rules_page_snapshot(tmp_path, monkeypatch, browser):
    monkeypatch.setattr(config, "SNAPSHOTS_DIR", str(tmp_path))
    context, page = _open(browser, "forum_home.html")

    structure.run(page, source={"name": "example-forum", "url": page.url})

    saved_files = list(tmp_path.rglob("*.html"))
    assert any("structure_rules_page" in f.name for f in saved_files)
    assert "포럼 규칙" in saved_files[0].read_text(encoding="utf-8")

    context.close()


def test_run_confirmed_absent_when_no_rules_link(tmp_path, monkeypatch, browser):
    monkeypatch.setattr(config, "SNAPSHOTS_DIR", str(tmp_path))
    context, page = _open(browser, "forum_home_no_rules.html")

    result = structure.run(page, source={"name": "example-forum", "url": page.url})

    assert result["_들어가는_법_구조"] == {"state": "CONFIRMED_ABSENT"}
    assert "General Discussion" in result["어떤 곳인지"]["value"]

    context.close()


def test_run_filters_account_menu_links_out_of_categories(tmp_path, monkeypatch, browser):
    """실제 크롤링에서 nav 선택자가 로그인 후 계정 메뉴까지 같이 잡았던 문제(darkforums.ru
    사례) 재발 방지용. 정확한 선택자가 없어도 흔한 계정 메뉴 문구는 걸러낸다."""
    monkeypatch.setattr(config, "SNAPSHOTS_DIR", str(tmp_path))
    context = browser.new_context()
    page = context.new_page()
    page.set_content(
        """
        <nav>
          <a href="/cat/general">General Discussion</a>
          <a href="/logout">Sign Out</a>
          <a href="/cp">Control Panel</a>
          <a href="/markread">Mark all as read</a>
        </nav>
        """
    )

    result = structure.run(page, source={"name": "x", "url": page.url})

    value = result["어떤 곳인지"]["value"]
    assert "General Discussion" in value
    assert "Sign Out" not in value
    assert "Control Panel" not in value
    assert "Mark all as read" not in value

    context.close()


def test_run_finds_rules_link_from_separate_selector_when_profile_specifies_it(
    tmp_path, monkeypatch, browser
):
    """darkforums.ru 사례: 진짜 카테고리(.forums__forum-name)랑 규칙 링크(.sidenav__menu)가
    서로 다른 곳에 있는 경우. 카테고리 목록에 규칙 링크 텍스트가 안 섞여야 하고, 규칙 페이지는
    별도 selector로 정상적으로 찾아야 한다."""
    monkeypatch.setattr(config, "SNAPSHOTS_DIR", str(tmp_path))
    monkeypatch.setitem(
        site_profiles.PROFILES,
        "test-platform",
        {"nav_link_selector": ".forums a", "rules_link_selector": ".sidenav a"},
    )

    context = browser.new_context()
    page = context.new_page()
    rules_uri = (FIXTURES_DIR / "forum_rules.html").as_uri()
    page.set_content(
        f"""
        <div class="sidenav"><a href="{rules_uri}">Rules &amp; Policies</a></div>
        <div class="forums"><a href="/cat/general">General</a></div>
        """
    )
    origin_url = page.url

    result = structure.run(
        page, source={"name": "x", "url": origin_url, "platform": "test-platform"}
    )

    assert result["어떤 곳인지"]["value"] == "General"  # 규칙 링크 텍스트가 안 섞임
    assert "가입은 초대 코드" in result["_들어가는_법_구조"]["value"]  # 규칙 페이지는 정상 수집

    context.close()


def test_run_uses_registered_platform_profile_selector(tmp_path, monkeypatch, browser):
    monkeypatch.setattr(config, "SNAPSHOTS_DIR", str(tmp_path))
    monkeypatch.setitem(site_profiles.PROFILES, "test-platform", {"nav_link_selector": ".real-cats a"})

    context = browser.new_context()
    page = context.new_page()
    page.set_content(
        """
        <nav><a href="/x">이건 잡히면 안 됨</a></nav>
        <div class="real-cats"><a href="/cat/general">General</a></div>
        """
    )

    result = structure.run(page, source={"name": "x", "url": page.url, "platform": "test-platform"})

    assert result["어떤 곳인지"]["value"] == "General"

    context.close()
