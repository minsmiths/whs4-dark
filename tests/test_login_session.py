"""VNC 로그인 진입점(login_session.py) 검증.

CLAUDE.md §3-8에 따라 실제 대상 사이트에는 접속하지 않는다 — Playwright 자체를 가짜로 교체해
"Chromium을 headed(§4.2-2)로 Tor 프록시(§4.2)를 거쳐 띄우고, 로그인 완료 후 세션을 저장한다"는
배선만 검증한다. 실제 브라우저/Tor/사람 입력은 필요하지 않다.
"""

from __future__ import annotations

import config
import login_session
import session_manager


def _write_whitelist(tmp_path, monkeypatch):
    path = tmp_path / "whitelist.yaml"
    path.write_text(
        "sites:\n"
        "  - name: example-forum\n"
        "    url: http://exampleexampleexampleexampleexampleexampleexampleexamp.onion\n"
        "    source_type: forum\n"
        "    approved_by: tester\n"
        "    approved_at: '2026-08-18'\n"
        "    requires_login: true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "WHITELIST_PATH", str(path))
    return path


def test_find_source_by_name_or_url_matches_by_name(tmp_path, monkeypatch):
    _write_whitelist(tmp_path, monkeypatch)

    source = login_session.find_source_by_name_or_url("example-forum")

    assert source is not None
    assert source["url"] == "http://exampleexampleexampleexampleexampleexampleexampleexamp.onion"


def test_find_source_by_name_or_url_matches_by_url(tmp_path, monkeypatch):
    _write_whitelist(tmp_path, monkeypatch)

    source = login_session.find_source_by_name_or_url(
        "http://exampleexampleexampleexampleexampleexampleexampleexamp.onion"
    )

    assert source is not None
    assert source["name"] == "example-forum"


def test_find_source_by_name_or_url_returns_none_when_missing(tmp_path, monkeypatch):
    _write_whitelist(tmp_path, monkeypatch)

    assert login_session.find_source_by_name_or_url("not-registered") is None


def test_main_rejects_unregistered_source(tmp_path, monkeypatch):
    _write_whitelist(tmp_path, monkeypatch)

    assert login_session.main(["not-registered"]) == 1


class _FakeChromium:
    def __init__(self, launches: list[dict]):
        self._launches = launches

    def launch(self, **kwargs):
        self._launches.append(kwargs)
        return _FakeBrowser()


class _FakeBrowser:
    def new_context(self, **kwargs):
        return _FakeContext()

    def close(self):
        pass


class _FakeContext:
    def new_page(self):
        return _FakePage()


class _FakePage:
    def goto(self, *args, **kwargs):
        pass


class _FakeSyncPlaywright:
    def __init__(self, launches: list[dict]):
        self._launches = launches

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    @property
    def chromium(self):
        return _FakeChromium(self._launches)


def test_main_launches_headed_chromium_through_tor_and_saves_session(tmp_path, monkeypatch):
    _write_whitelist(tmp_path, monkeypatch)
    monkeypatch.setattr("builtins.input", lambda *a, **k: "")

    launches: list[dict] = []
    import playwright.sync_api as pw_api

    monkeypatch.setattr(pw_api, "sync_playwright", lambda: _FakeSyncPlaywright(launches))

    saved: list[str] = []
    monkeypatch.setattr(
        session_manager, "save_session", lambda context, source_id: saved.append(source_id)
    )

    exit_code = login_session.main(["example-forum"])

    assert exit_code == 0
    assert launches[0]["headless"] is False  # §4.2-2: 사람이 VNC로 봐야 하므로 headed
    assert launches[0]["proxy"] == {"server": config.TOR_SOCKS_PROXY}  # §4.2: Tor SOCKS5만 경유
    # config.BROWSER_LAUNCH_ARGS는 빈 리스트다 — 샌드박스 비활성화 플래그(§4.2-1)가 섞이지
    # 않았음은 이 동등성 검증으로 충분하다(CI의 grep 검사와 별개로, 테스트 코드에 그 문자열을
    # 그대로 적지 않는다).
    assert launches[0]["args"] == config.BROWSER_LAUNCH_ARGS
    assert saved == ["example-forum"]


class _FakeTimeoutPage:
    """.onion 히든서비스 접속이 시간 안에 안 끝나는 상황을 흉내낸다."""

    def goto(self, *args, **kwargs):
        from playwright.sync_api import Error as PlaywrightError

        raise PlaywrightError("Timeout 90000ms exceeded.")


class _FakeContextWithTimeoutPage(_FakeContext):
    def new_page(self):
        return _FakeTimeoutPage()


class _FakeBrowserWithTimeoutPage(_FakeBrowser):
    def new_context(self, **kwargs):
        return _FakeContextWithTimeoutPage()


class _FakeChromiumWithTimeoutPage(_FakeChromium):
    def launch(self, **kwargs):
        self._launches.append(kwargs)
        return _FakeBrowserWithTimeoutPage()


class _FakeSyncPlaywrightWithTimeoutPage(_FakeSyncPlaywright):
    @property
    def chromium(self):
        return _FakeChromiumWithTimeoutPage(self._launches)


def test_main_does_not_crash_when_page_load_times_out(tmp_path, monkeypatch):
    """M1/로그인 흐름: 접속이 타임아웃돼도 크래시하지 않고, 사람이 VNC로 재시도할 수 있게
    Enter 프롬프트까지 도달해서 세션 저장까지 끝까지 진행해야 한다."""
    _write_whitelist(tmp_path, monkeypatch)
    monkeypatch.setattr("builtins.input", lambda *a, **k: "")

    launches: list[dict] = []
    import playwright.sync_api as pw_api

    monkeypatch.setattr(pw_api, "sync_playwright", lambda: _FakeSyncPlaywrightWithTimeoutPage(launches))

    saved: list[str] = []
    monkeypatch.setattr(
        session_manager, "save_session", lambda context, source_id: saved.append(source_id)
    )

    exit_code = login_session.main(["example-forum"])

    assert exit_code == 0
    assert saved == ["example-forum"]
