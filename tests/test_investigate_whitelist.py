"""M2 완료 기준: '미등록 URL 입력 시 즉시 에러'를 검증한다.

CLAUDE.md §3-1: 승인된 대상 URL 1곳에 한해서만 동작한다. Playwright/Tor 를 띄우지 않고도
whitelist 검증 로직만 독립적으로 확인할 수 있다.
"""

from __future__ import annotations

import investigate


def _write_whitelist(tmp_path, monkeypatch):
    path = tmp_path / "whitelist.yaml"
    path.write_text(
        "sites:\n"
        "  - name: example-forum\n"
        "    url: http://exampleexampleexampleexampleexampleexampleexampleexamp.onion\n"
        "    source_type: forum\n"
        "    approved_by: tester\n"
        "    approved_at: '2026-08-18'\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(investigate.config, "WHITELIST_PATH", str(path))
    return path


def test_find_approved_source_returns_entry_for_registered_url(tmp_path, monkeypatch):
    _write_whitelist(tmp_path, monkeypatch)

    source = investigate.find_approved_source(
        "http://exampleexampleexampleexampleexampleexampleexampleexamp.onion", "forum"
    )

    assert source is not None
    assert source["source_type"] == "forum"


def test_find_approved_source_returns_none_for_unregistered_url(tmp_path, monkeypatch):
    _write_whitelist(tmp_path, monkeypatch)

    source = investigate.find_approved_source("http://not-registered.onion", "forum")

    assert source is None


def test_main_rejects_unregistered_url_immediately(tmp_path, monkeypatch, capsys):
    _write_whitelist(tmp_path, monkeypatch)

    exit_code = investigate.main(["http://not-registered.onion", "--type", "forum"])

    assert exit_code == 1


def test_main_rejects_registered_but_non_forum_type(tmp_path, monkeypatch):
    """MVP는 source_type=forum만 실제 구현되어 있다 (CLAUDE.md §1 표 / SRS)."""
    path = tmp_path / "whitelist.yaml"
    path.write_text(
        "sites:\n"
        "  - name: example-market\n"
        "    url: http://exampleexampleexampleexampleexampleexampleexampleexamp.onion\n"
        "    source_type: marketplace\n"
        "    approved_by: tester\n"
        "    approved_at: '2026-08-18'\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(investigate.config, "WHITELIST_PATH", str(path))

    exit_code = investigate.main(
        ["http://exampleexampleexampleexampleexampleexampleexampleexamp.onion", "--type", "marketplace"]
    )

    assert exit_code == 1
