"""content_sample.crawl_site() 검증 (2026-08-23 도입, 사이트 전체 헤드라인 재귀 순회).

CLAUDE.md §3-8에 따라 실제 대상 사이트에는 접속하지 않는다 — 로컬 fixture(file://)만 사용.

검증 대상:
- 홈페이지에서 발견한 모든 카테고리(하위 서브포럼 포함)를 재귀적으로 다 도는지
- 카테고리당 페이지네이션이 config.SITE_MAP_MAX_PAGES_PER_CATEGORY를 넘지 않는지
- 이미 방문한 URL은 다시 안 가는지(무한 루프 방지)
- 챌린지 감지 시 CrawlInterrupted를 던지고 체크포인트를 남기는지(자동 재로그인은 안 함, §3-3)
- --resume(resume=True)이 체크포인트에서 이어서 진행하는지
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

import config
from collectors import content_sample

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _uri(filename: str) -> str:
    return (FIXTURES_DIR / filename).as_uri()


@pytest.fixture
def page():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        pg.set_content("<html><head><title>origin</title></head><body>origin page</body></html>")
        yield pg
        browser.close()


@pytest.fixture(autouse=True)
def _fast_and_isolated(tmp_path, monkeypatch):
    # 실제 지연(3~5초)까지 기다릴 필요는 없다 — 이 테스트 파일 안에서만 0으로 낮춘다.
    monkeypatch.setattr(config, "REQUEST_DELAY_MIN_SEC", 0)
    monkeypatch.setattr(config, "REQUEST_DELAY_MAX_SEC", 0)
    # 체크포인트/스냅샷이 실제 프로젝트 디렉터리를 오염시키지 않도록 격리한다.
    monkeypatch.setattr(config, "CHECKPOINT_DIR", str(tmp_path / "sessions"))
    monkeypatch.setattr(config, "SNAPSHOTS_DIR", str(tmp_path / "snapshots"))


def test_crawl_site_recurses_into_subcategories_and_respects_pagination_cap(page, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "SITE_MAP_MAX_PAGES_PER_CATEGORY", 2)

    seed = [
        {"text": "Category A", "url": _uri("sitemap_cat_a.html")},
        {"text": "Category B", "url": _uri("sitemap_cat_b.html")},
    ]

    result = content_sample.crawl_site(page, source={"name": "x", "url": page.url}, category_seed=seed)

    titles = {p["title"] for p in result["_표본_게시글"]}
    assert "Category A first post" in titles
    assert "Category A second post" in titles
    assert "Category A page2 post" in titles  # 2페이지째까진 감
    assert "Category A page3 post (should never be collected)" not in titles  # 상한 2 초과라 안 감
    assert "Leaked korea database dump in category B" in titles
    assert "Sub A1 post" in titles  # 하위 서브포럼까지 재귀적으로 들어감

    assert set(result["_사이트맵_방문_카테고리"]) == {"Category A", "Category B", "Sub A1"}
    assert result["한국 관련 유출"]["value"] == "후보 1건"  # Category B의 게시글 1건만 매칭

    # 2026-08-24: "이번 크롤에서 실제로 어느 URL을 돌았는지" MD에 남기려면(§ 사용자 요청)
    # crawl_site()가 카테고리/페이지별 방문 URL을 함께 반환해야 한다.
    visited_urls = {(v["category"], v["page"]): v["url"] for v in result["_사이트맵_방문_URL"]}
    assert visited_urls[("Category A", 1)] == _uri("sitemap_cat_a.html")
    assert visited_urls[("Category A", 2)] == _uri("sitemap_cat_a_p2.html")
    assert visited_urls[("Category B", 1)] == _uri("sitemap_cat_b.html")
    assert ("Category A", 3) not in visited_urls  # 상한 2 초과라 안 감

    # "Sellers Place 4페이지 헤드라인 보여줘" 같은 질문에 나중에 답할 수 있으려면 게시글마다
    # 어느 카테고리·몇 페이지에서 나왔는지 표시돼 있어야 한다.
    by_title = {p["title"]: p for p in result["_표본_게시글"]}
    assert by_title["Category A first post"]["category"] == "Category A"
    assert by_title["Category A first post"]["page"] == 1
    assert by_title["Category A page2 post"]["category"] == "Category A"
    assert by_title["Category A page2 post"]["page"] == 2
    assert by_title["Sub A1 post"]["category"] == "Sub A1"

    # 끝까지 돌았으면 체크포인트는 남지 않는다(다음 실행은 새로 시작).
    assert not list(Path(config.CHECKPOINT_DIR).glob("*.sitemap_checkpoint.json"))

    # 원래 페이지(카테고리를 돌기 전 위치)로 복귀했는지도 확인한다.
    assert page.url == "about:blank"

    # selector 확정용으로 처음 방문에 성공한 카테고리 페이지 1개는 스냅샷이 남아야 한다.
    snapshot_files = list((tmp_path / "snapshots").rglob("*.html"))
    assert any("sitemap_first_category" in f.name for f in snapshot_files)
    assert len(snapshot_files) == 1  # 카테고리/페이지마다 다 찍으면 볼륨이 커지므로 딱 1개만

    # 끝까지 다 돈 실행의 헤드라인 전체 목록은 MD가 아니라 별도 파일로 남아서, 나중에
    # "OO 카테고리 N페이지 헤드라인 보여줘" 같은 질문에 실제로 답할 수 있어야 한다.
    dump_path = content_sample._headline_dump_path("x")
    assert dump_path.exists()
    dump = json.loads(dump_path.read_text(encoding="utf-8"))
    assert len(dump["posts"]) == len(result["_표본_게시글"])
    assert {p["title"] for p in dump["posts"]} == titles


def test_crawl_site_follows_numbered_pagination_without_explicit_next_link(page, monkeypatch):
    # 2026-08-24: darkforums 실크롤에서 "다음" 화살표/rel=next 없이 페이지 번호(1 2 3 ...)만
    # 있는 마크업을 만나 1페이지에서 멈췄던 사례 — 이 프로젝트는 darkforums 전용이 아니므로
    # site_profiles.py에 매번 selector를 등록하는 대신 범용 폴백(_find_next_page_href)이
    # 번호 링크만으로도 다음 페이지를 찾아가는지 검증한다.
    monkeypatch.setattr(config, "SITE_MAP_MAX_PAGES_PER_CATEGORY", 5)

    seed = [{"text": "Category C", "url": _uri("sitemap_cat_c.html")}]

    result = content_sample.crawl_site(page, source={"name": "x", "url": page.url}, category_seed=seed)

    titles = {p["title"] for p in result["_표본_게시글"]}
    assert "Category C first post" in titles
    assert "Category C page2 post" in titles  # 번호 링크 폴백으로 2페이지까지 감

    by_title = {p["title"]: p for p in result["_표본_게시글"]}
    assert by_title["Category C page2 post"]["page"] == 2


def test_crawl_site_accepts_per_category_page_limit(page):
    seed = [{"text": "Category A", "url": _uri("sitemap_cat_a.html")}]

    result = content_sample.crawl_site(
        page,
        source={"name": "x", "url": page.url},
        category_seed=seed,
        pages_per_category=1,
    )

    assert all(post["page"] == 1 for post in result["_표본_게시글"])
    assert result["_crawl_completion"]["pages_per_category"] == 1
    assert result["_crawl_completion"]["complete"] is True


def test_crawl_site_does_not_revisit_the_same_url_twice(page):
    seed = [
        {"text": "Category B", "url": _uri("sitemap_cat_b.html")},
        {"text": "Category B (중복)", "url": _uri("sitemap_cat_b.html")},
    ]

    result = content_sample.crawl_site(page, source={"name": "x", "url": page.url}, category_seed=seed)

    # 같은 URL이 큐에 두 번 있어도 실제로 방문(=게시글 수집)은 한 번만 일어난다.
    assert len(result["_표본_게시글"]) == 1


def test_crawl_site_raises_and_checkpoints_on_challenge_detection(page):
    seed = [
        {"text": "Challenge Page", "url": _uri("sitemap_challenge.html")},
        {"text": "Category B", "url": _uri("sitemap_cat_b.html")},
    ]

    with pytest.raises(content_sample.CrawlInterrupted) as exc_info:
        content_sample.crawl_site(page, source={"name": "x", "url": page.url}, category_seed=seed)

    assert "챌린지" in exc_info.value.reason

    checkpoint_files = list(Path(config.CHECKPOINT_DIR).glob("*.sitemap_checkpoint.json"))
    assert len(checkpoint_files) == 1
    state = json.loads(checkpoint_files[0].read_text(encoding="utf-8"))
    # 챌린지가 뜬 카테고리 자체를 큐 맨 앞에 되돌려서, 재로그인 후 --resume하면 그 카테고리부터
    # 다시 시도한다(건너뛰지 않는다).
    assert state["queue"][0]["text"] == "Challenge Page"
    assert any(entry["text"] == "Category B" for entry in state["queue"])
    assert state["posts"] == []  # 챌린지 화면 자체에선 게시글을 못 모았으므로 비어있어야 정상


def test_crawl_site_raises_on_title_less_rate_limit_page(page):
    """2026-08-26 pwnforums 실크롤 사고 재발 방지: title 태그가 없는 속도 제한(flood control)
    응답도 챌린지처럼 감지해 CrawlInterrupted를 던져야 한다 — 그렇지 않으면 이후 모든 카테고리가
    조용히 게시글 0건으로 끝나고 "확인했는데 없음"으로 잘못 기록된다."""
    seed = [{"text": "Rate Limited", "url": _uri("sitemap_rate_limited.html")}]

    with pytest.raises(content_sample.CrawlInterrupted) as exc_info:
        content_sample.crawl_site(page, source={"name": "x", "url": page.url}, category_seed=seed)

    assert "챌린지" in exc_info.value.reason


def test_crawl_site_interrupts_after_consecutive_connection_failures(page, monkeypatch):
    """2026-08-27 cracked.st: DDoS-Guard가 응답을 안 주고 타임아웃으로만 끝나면 goto가 예외로
    죽고 challenge.detect도 못 돌아, 수백 개 카테고리를 전부 "접속 실패"로 갈아넣고 게시글 0건으로
    조용히 끝났다. 연속 실패가 임계치에 닿으면 체크포인트를 남기고 CrawlInterrupted를 던져야 한다."""
    monkeypatch.setattr(config, "CHALLENGE_MAX_CONSECUTIVE_FAILURES", 3)

    seed = [{"text": f"Dead {i}", "url": f"http://127.0.0.1:9/dead-{i}"} for i in range(3)]
    seed.append({"text": "Category B", "url": _uri("sitemap_cat_b.html")})

    with pytest.raises(content_sample.CrawlInterrupted) as exc_info:
        content_sample.crawl_site(page, source={"name": "x", "url": page.url}, category_seed=seed)

    assert "연속" in exc_info.value.reason

    checkpoint_files = list(Path(config.CHECKPOINT_DIR).glob("*.sitemap_checkpoint.json"))
    assert len(checkpoint_files) == 1
    state = json.loads(checkpoint_files[0].read_text(encoding="utf-8"))
    # 죽은 URL 3개는 재시도해도 소용없으니 visited/failures로 넘기고 큐에서 뺀다.
    assert not any(e["text"].startswith("Dead") for e in state["queue"])
    assert len(state["failures"]) == 3
    # 아직 안 가본 정상 카테고리는 큐에 남는다 — --resume 하면 여기서부터 이어간다.
    assert any(e["text"] == "Category B" for e in state["queue"])


def test_crawl_site_resume_continues_from_saved_checkpoint(page):
    source = {"name": "x", "url": page.url}
    checkpoint_path = content_sample._checkpoint_path("x")
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(
        json.dumps(
            {
                "queue": [{"text": "Category B", "url": _uri("sitemap_cat_b.html")}],
                "visited": [],
                "posts": [{"title": "이전에 이미 모아둔 글", "author": "x", "date": "2026-08-01"}],
                "visited_categories": ["이전 세션에서 방문함"],
            }
        ),
        encoding="utf-8",
    )

    # resume=True로 호출할 땐 category_seed를 새로 안 줘도 된다 — 체크포인트가 우선한다.
    result = content_sample.crawl_site(page, source=source, category_seed=[], resume=True)

    titles = {p["title"] for p in result["_표본_게시글"]}
    assert "이전에 이미 모아둔 글" in titles  # 체크포인트에 있던 결과가 안 사라짐
    assert "Leaked korea database dump in category B" in titles  # 이어서 실제로 수집됨
    assert "이전 세션에서 방문함" in result["_사이트맵_방문_카테고리"]
    assert "Category B" in result["_사이트맵_방문_카테고리"]

    # 이어서 끝까지 돌았으니 체크포인트는 정리된다.
    assert not checkpoint_path.exists()
