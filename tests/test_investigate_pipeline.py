"""M5 완료 기준 검증: investigate.py 전체 파이프라인 통합 테스트.

- run_pipeline()이 로컬 fixture만으로 ①~⑦ Collector를 전부 돌리고, 그 결과를
  report_generator.generate_markdown()에 넣으면 23개 칸이 통째로 누락되지 않는다.
- M1 완료 기준 (c): 세션이 없으면 BLOCKED 대신 record_session_expired 로 기록하고
  프로그램(run_pipeline)이 죽지 않고 끝까지 진행한다.
- main()이 Chromium을 Tor SOCKS5 프록시로만 띄우고 샌드박스 비활성화 플래그를 쓰지 않는지 검증한다
  (실제 Tor 데몬 없이도 검증할 수 있도록 playwright.sync_api.sync_playwright를 가짜로 교체).

CLAUDE.md §3-8에 따라 실제 대상 사이트에는 접속하지 않는다 — 로컬 fixture(file://)만 사용.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

import config
import investigate
import report_generator

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def page():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        pg.goto((FIXTURES_DIR / "forum_home_full.html").as_uri())
        yield pg
        browser.close()


def test_run_pipeline_end_to_end_fills_every_column_without_crashing(tmp_path, monkeypatch, page):
    monkeypatch.setattr(config, "SNAPSHOTS_DIR", str(tmp_path / "snapshots"))

    source = {"name": "example-forum", "url": page.url}
    results = investigate.run_pipeline(page, source)
    md = report_generator.generate_markdown(source, results)

    for field in report_generator.FIELD_ORDER:
        if field in ("확인일", "주소") or field in report_generator.INTERNAL_ONLY_FIELDS:
            continue
        assert f"- {field}:" in md, f"{field} 칸이 통째로 빠짐"

    # 실제로 값을 채운 대표 필드 몇 개는 tri-state가 아니라 진짜 값이어야 한다.
    assert "General Discussion" in md  # 어떤 곳인지
    assert "가입은 초대 코드" in md  # 들어가는 법(내부 섹션) — 규칙 페이지 원문
    assert "후보 1건" in md  # 한국 관련 유출: "Leaked korea database dump" 1건

    # snapshot 저장 확인 (M2 산출물)
    snapshot_files = list((tmp_path / "snapshots").rglob("*.html"))
    assert any("availability_home" in f.name for f in snapshot_files)
    assert any("structure_rules_page" in f.name for f in snapshot_files)


def test_run_pipeline_records_expired_session_and_keeps_running(tmp_path, monkeypatch, page):
    monkeypatch.setattr(config, "SNAPSHOTS_DIR", str(tmp_path / "snapshots"))
    log_path = tmp_path / "run_log.json"
    monkeypatch.setattr(config, "RUN_LOG_PATH", str(log_path))

    source = {
        "name": "example-forum",
        "url": page.url,
        "requires_login": True,
        "logged_in_selector": "#mypage-link-that-does-not-exist",
    }

    results = investigate.run_pipeline(page, source)  # 죽지 않고 끝까지 진행해야 함

    assert results["상태"]["value"] == "online"  # 파이프라인이 실제로 끝까지 돌았다는 증거
    entries = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert entries == [{"source_id": "example-forum", "event": "session_expired", "reason": "세션 만료"}]


def test_run_pipeline_navigates_to_sample_list_url_before_stats_and_content_sample(tmp_path, monkeypatch):
    """darkforums.ru 사례 재발 방지: 홈페이지엔 게시글이 없어서, sample_list_url이 지정되면
    거기로 이동한 뒤 stats/content_sample을 돌려야 한다."""
    monkeypatch.setattr(config, "SNAPSHOTS_DIR", str(tmp_path / "snapshots"))

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto((FIXTURES_DIR / "forum_home_no_rules.html").as_uri())  # 게시글 없는 홈페이지

        source = {
            "name": "example-forum",
            "url": page.url,
            "sample_list_url": (FIXTURES_DIR / "forum_thread_list.html").as_uri(),
        }
        results = investigate.run_pipeline(page, source)

        assert results["_표본_게시글"]  # 홈페이지가 아니라 목록 페이지에서 실제로 수집됨
        assert "210" in results["규모"]["value"]  # forum_thread_list.html 기준 페이지네이션 추정치
        browser.close()


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
        return object()  # run_pipeline은 아래에서 스텁으로 교체하므로 실제 Page API 불필요


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


def test_main_launches_chromium_through_tor_proxy_without_sandbox_flags(tmp_path, monkeypatch):
    whitelist_path = tmp_path / "whitelist.yaml"
    whitelist_path.write_text(
        "sites:\n"
        "  - name: example-forum\n"
        "    url: http://exampleexampleexampleexampleexampleexampleexampleexamp.onion\n"
        "    source_type: forum\n"
        "    approved_by: tester\n"
        "    approved_at: '2026-08-18'\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(investigate.config, "WHITELIST_PATH", str(whitelist_path))
    monkeypatch.setattr(investigate.config, "OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setattr(investigate, "run_pipeline", lambda page, source: {})

    launches: list[dict] = []
    import playwright.sync_api as pw_api

    monkeypatch.setattr(pw_api, "sync_playwright", lambda: _FakeSyncPlaywright(launches))

    exit_code = investigate.main(
        ["http://exampleexampleexampleexampleexampleexampleexampleexamp.onion", "--type", "forum"]
    )

    assert exit_code == 0
    assert len(launches) == 1
    assert launches[0]["proxy"] == {"server": config.TOR_SOCKS_PROXY}  # §4.2: Tor SOCKS5만 경유
    # config.BROWSER_LAUNCH_ARGS는 빈 리스트다 — 이 동등성 검증만으로 샌드박스 비활성화 플래그
    # (§4.2-1)가 섞여 들어가지 않았음이 함께 증명된다. CI(security.yml)의 grep 검사는 코드 전체를
    # 훑어 실제 문자열 사용 여부를 잡아내므로, 테스트 코드에 그 문자열을 그대로 적지 않는다.
    assert launches[0]["args"] == config.BROWSER_LAUNCH_ARGS

    out_files = list((tmp_path / "output").glob("*.md"))
    assert len(out_files) == 1  # M5 완료 기준: output/ 에 MD 파일 1개 생성
