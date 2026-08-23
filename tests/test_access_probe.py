"""M4 완료 기준 검증: `가입 필요`, `_들어가는_법_가입폼`(가입조건) 채워짐,
가입 페이지에 POST 요청 없음(네트워크 로그 확인).

CLAUDE.md §3-2·§3-3에 따라 가입 폼은 절대 제출하지 않는다 — 로컬 fixture로만 검증.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from collectors import access_probe

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def page():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        pg.goto((FIXTURES_DIR / "forum_login.html").as_uri())
        yield pg
        browser.close()


def test_run_detects_login_form_and_lists_register_fields(page):
    result = access_probe.run(page, source={"url": page.url})

    assert result["가입 필요"]["value"] is True
    fields = result["_들어가는_법_가입폼"]["value"]
    for expected in ("username", "email", "password", "invite_code"):
        assert expected in fields


def test_run_never_submits_the_registration_form(page):
    """네트워크 로그에서 가입 페이지에 대한 POST 요청이 0건이어야 한다 (M4 완료 기준)."""
    requests_seen = []
    page.on("request", lambda req: requests_seen.append(req))

    access_probe.run(page, source={"url": page.url})

    post_requests = [r for r in requests_seen if r.method == "POST"]
    assert post_requests == []


def test_run_confirmed_absent_when_no_login_form():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        pg.set_content("<html><body><p>로그인 폼 없음</p></body></html>")

        result = access_probe.run(pg, source={"url": pg.url})

        assert result["가입 필요"]["value"] is False
        assert "_들어가는_법_가입폼" not in result  # 로그인 폼이 없으면 더 볼 것도 없음
        browser.close()
