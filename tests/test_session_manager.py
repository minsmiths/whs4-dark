"""M1 완료 기준 (b)(c) 검증용 유닛테스트.

development-plan.md M1 완료 기준:
    (a) VNC로 로그인 가능            — 사람이 VNC 화면으로 직접 확인해야 함, AI가 검증 불가
    (b) 세션 파일 유지한 채 재실행 → is_session_valid() True   — 이 파일에서 검증
    (c) 세션 파일 비운 뒤 재실행 → BLOCKED 기록되고 프로그램이 죽지 않고 계속 진행
        — session_manager 레벨(로그 기록)은 이 파일에서 검증하고,
          "죽지 않고 다음 단계로 진행"은 investigate.py 파이프라인 레벨이므로
          tests/test_investigate.py 에서 통합 검증한다.

실제 대상 사이트에는 접속하지 않는다 (CLAUDE.md §3-8) — Playwright로 로컬 in-memory 페이지만 연다.
"""

from __future__ import annotations

import json

import pytest
from playwright.sync_api import sync_playwright

import config
import session_manager


@pytest.fixture
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def test_load_session_returns_none_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SESSIONS_DIR", str(tmp_path))
    assert session_manager.load_session("no-such-source") is None


def test_save_session_then_load_session_roundtrip(tmp_path, monkeypatch, browser):
    monkeypatch.setattr(config, "SESSIONS_DIR", str(tmp_path))
    context = browser.new_context()
    context.new_page()  # 로그인 완료 후를 흉내: 컨텍스트에 페이지가 열려 있음

    saved_path = session_manager.save_session(context, "example-forum")
    context.close()

    assert saved_path.exists()
    state = json.loads(saved_path.read_text(encoding="utf-8"))
    assert "cookies" in state  # storage_state() 표준 포맷

    loaded_path = session_manager.load_session("example-forum")
    assert loaded_path == str(saved_path)


def test_is_session_valid_true_when_logged_in_element_present(browser):
    context = browser.new_context()
    page = context.new_page()
    page.set_content("<html><body><a id='mypage-link' href='/mypage'>마이페이지</a></body></html>")

    assert session_manager.is_session_valid(page, "#mypage-link") is True
    context.close()


def test_is_session_valid_false_when_logged_in_element_missing(browser):
    context = browser.new_context()
    page = context.new_page()
    page.set_content("<html><body><a href='/login'>로그인</a></body></html>")

    assert session_manager.is_session_valid(page, "#mypage-link") is False
    context.close()


def test_is_session_valid_false_on_unstable_page(browser):
    """페이지가 닫혀 예외가 나도 크래시하지 않고 False로 취급한다."""
    context = browser.new_context()
    page = context.new_page()
    page.close()

    assert session_manager.is_session_valid(page, "#mypage-link") is False
    context.close()


def test_record_session_expired_appends_json_line_without_crashing(tmp_path, monkeypatch):
    log_path = tmp_path / "run_log.json"
    monkeypatch.setattr(config, "RUN_LOG_PATH", str(log_path))

    session_manager.record_session_expired("example-forum", reason="세션 만료")
    session_manager.record_session_expired("example-forum", reason="세션 만료")  # 두 번째 실행에서도 안전

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    entry = json.loads(lines[0])
    assert entry == {
        "source_id": "example-forum",
        "event": "session_expired",
        "reason": "세션 만료",
    }


def test_cleared_session_file_leads_to_none_load(tmp_path, monkeypatch, browser):
    """(c) 전반부: 세션 파일이 없으면(비워지면) load_session 이 None을 반환해
    호출부(investigate.py)가 BLOCKED 로 처리할 수 있는 신호를 준다."""
    monkeypatch.setattr(config, "SESSIONS_DIR", str(tmp_path))
    context = browser.new_context()
    context.new_page()
    saved_path = session_manager.save_session(context, "example-forum")
    context.close()

    saved_path.unlink()  # 세션 파일을 비움(삭제)

    assert session_manager.load_session("example-forum") is None
