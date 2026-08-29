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


def test_load_keywords_ignores_comment_lines(tmp_path, monkeypatch):
    """실사고 회귀 테스트(2026-08-25): keywords/korea_keywords.txt 맨 위 안내 주석 중
    `#`만 있는 빈 주석 줄이 그대로 "키워드"로 로드되면, 제목에 `#` 문자만 있어도(예: 스레드
    제목의 "#1", "#2" 같은 번호 표기) 한국 관련 유출 후보로 잘못 잡힌다. 실제 darkforums
    크롤 데이터 감사 중 이 버그로 사이트 전체 후보 수가 109건이 아니라 136건으로 27건
    부풀려진 걸 확인했다.
    """
    keywords_file = tmp_path / "korea_keywords.txt"
    keywords_file.write_text(
        "# 안내 주석\n#\n# 또 다른 안내 주석\n\nkorea\nleak\n", encoding="utf-8"
    )
    monkeypatch.setattr(content_sample.config, "KOREA_KEYWORDS_PATH", str(keywords_file))

    keywords = content_sample._load_keywords()

    assert keywords == ["korea", "leak"]
    assert "#" not in keywords


def test_run_korea_keyword_candidate_ignores_hash_in_title(tmp_path, monkeypatch):
    """제목에 `#`만 들어있는 게시글(예: "Config #1")이 한국 관련 후보로 오탐되지 않아야 한다."""
    keywords_file = tmp_path / "korea_keywords.txt"
    keywords_file.write_text("#\nkorea\n", encoding="utf-8")
    monkeypatch.setattr(content_sample.config, "KOREA_KEYWORDS_PATH", str(keywords_file))

    posts = [{"title": "Config #1", "author": "a", "date": "2026-08-01"}]
    result = content_sample.summarize_posts(posts, sample_note="표본 1건 제목 기준")

    assert result["한국 관련 유출"]["value"] == "후보 0건"


def test_summarize_posts_reports_top_language():
    """profile_report_generator.py("국가"/"사용 언어" 요약)가 쓰는 _사용_언어_최다 필드."""
    posts = [
        {"title": "Welcome to the forum everyone", "author": "a", "date": "2026-08-01"},
        {"title": "Hello and welcome, glad you joined", "author": "b", "date": "2026-08-01"},
        {"title": "Willkommen im Forum, viel Spass", "author": "c", "date": "2026-08-01"},
    ]

    result = content_sample.summarize_posts(posts, sample_note="표본 3건")

    top = result["_사용_언어_최다"]
    assert top["lang"] == "en"
    assert top["pct"] == 66
    assert top["top2"][0][0] == "en"


def test_find_korea_specific_leaks_ignores_generic_leak_keywords():
    """"leak"/"database" 같은 일반 키워드만 매칭된 글은 한국 관련 후보에서 빠져야 한다."""
    posts = [
        {"title": "Huge database leak", "author": "a", "category": "Databases", "date": "01-08-26, 09:00 AM"},
        {
            "title": "[South Korea] SK Telecom 26+ millions",
            "author": "b",
            "category": "Leaks Market",
            "date": "08-07-26, 08:46 PM",
        },
    ]

    items = content_sample.find_korea_specific_leaks(posts)

    assert len(items) == 1
    assert "SK Telecom" in items[0]["title"]
    assert items[0]["date"] == "2026-07-08"  # DD-MM-YY 절대 표기 → ISO로 정규화


def test_find_korea_specific_leaks_empty_without_match():
    posts = [
        {
            "title": "Huge database leak",
            "author": "a",
            "category": "Databases",
            "date": "01-08-26, 09:00 AM",
        }
    ]

    assert content_sample.find_korea_specific_leaks(posts) == []


def test_find_korea_specific_leaks_orders_by_recency_across_years():
    """DD-MM-YY 문자열을 사전식으로 비교하면 순서가 틀어진다 — 제대로 파싱해서 비교해야 한다."""
    posts = [
        {
            "title": "Old Korea leak from 2024",
            "author": "a",
            "category": "Databases",
            "date": "22-08-24, 10:00 PM",  # 2024-08-22
        },
        {
            "title": "New Korea leak from 2026",
            "author": "b",
            "category": "Leaks Market",
            "date": "05-07-26, 06:49 AM",  # 2026-07-05, 사전식으로는 위보다 앞섬(잘못된 순서)
        },
    ]

    items = content_sample.find_korea_specific_leaks(posts, limit=1)

    assert items[0]["title"] == "New Korea leak from 2026"


def test_find_notable_leak_candidates_requires_scale_hint():
    posts = [
        {"title": "Selling some database", "author": "a", "category": "Sellers Place"},
        {"title": "DUOLINGO Database 500M users", "author": "b", "category": "Sellers Place"},
    ]

    items = content_sample.find_notable_leak_candidates(posts)

    assert len(items) == 1
    assert "DUOLINGO" in items[0]["title"]


def test_find_notable_leak_candidates_empty_without_match():
    posts = [{"title": "Just chatting", "author": "a", "category": "The Lounge"}]

    assert content_sample.find_notable_leak_candidates(posts) == []


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


def test_collect_posts_uses_darkforums_profile_with_no_datetime_attribute():
    """darkforums(Knox 테마) 실제 마크업 재현(2026-08-23, sitemap_first_category.html 스냅샷에서
    확인). 게시글 행은 <tr class="inline_row">, 제목은 [id^="tid_"] a(읽음 상태에 따라
    subject_old/subject_new로 클래스가 갈리므로 id 접두어로 잡는다), 날짜 요소엔 datetime 속성이
    없고 화면 텍스트만 있다 — collect_posts()가 title 속성 없이도 텍스트로 폴백해야 한다."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        pg.set_content(
            """
            <table>
              <tbody>
                <tr><td>구분선(무시돼야 함)</td></tr>
                <tr class="inline_row">
                  <td>
                    <span class=" subject_old" id="tid_2"><a href="Thread-Welcome">Welcome</a></span>
                    <div><span class="author smalltext"><a href="/User-Lucifer"><s>Lucifer</s></a></span>
                    <span class="forum-display__thread-date">18-11-22, 11:26 AM</span></div>
                  </td>
                </tr>
                <tr class="inline_row">
                  <td>
                    <span class=" subject_new" id="tid_9"><a href="Thread-Other">Other Thread</a></span>
                    <div><span class="author smalltext">AnonOne</span>
                    <span class="forum-display__thread-date">09-09-23, 09:09 AM</span></div>
                  </td>
                </tr>
              </tbody>
            </table>
            """
        )

        posts = content_sample.collect_posts(pg, source={"platform": "darkforums"})

        assert posts == [
            {"title": "Welcome", "author": "Lucifer", "date": "18-11-22, 11:26 AM"},
            {"title": "Other Thread", "author": "AnonOne", "date": "09-09-23, 09:09 AM"},
        ]
        browser.close()


def test_collect_posts_falls_back_to_thread_url_patterns():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.set_content(
            """
            <section class="unknown-list">
              <div><a href="/Thread-First-123">First topic</a></div>
              <div><a href="/Thread-Second-456">Second topic</a></div>
              <div><a href="/Thread-First-123#pid1">First topic duplicate</a></div>
            </section>
            """
        )

        posts = content_sample.collect_posts(page)

        assert [post["title"] for post in posts] == ["First topic", "Second topic"]
        assert all(post["url"] for post in posts)
        browser.close()
