"""profile_report_generator.py(사용자 지정 템플릿, 2026-08-25) 검증.

CLAUDE.md §3-8에 따라 실제 대상 사이트에는 접속하지 않는다 — 손으로 만든 collector 결과
dict만 사용한다.
"""

from __future__ import annotations

from pathlib import Path

import profile_report_generator as prg


def _base_results(**overrides):
    results = {
        "상태": {"value": "online", "observed_at": "2026-08-24", "source": "직접 접속"},
        "어떤 곳인지": {
            "value": "Announcements, Databases, Sellers Place",
            "observed_at": "2026-08-24",
            "source": "홈페이지 nav 1단계 depth",
        },
        "규모": {
            "value": "1000 Total Posts",
            "observed_at": "2026-08-24",
            "source": "포럼 통계 영역",
        },
        "어니언 주소": {
            "value": "abc123.onion",
            "observed_at": "2026-08-24",
            "source": "본문 정규식 매칭 (후보)",
        },
        "_사용_언어_최다": {"lang": "en", "pct": 67, "top2": [("en", 67), ("de", 11)]},
        "사용 언어": {"value": "en 67건(67%)", "observed_at": "2026-08-24", "source": "langdetect"},
        "_운영자_후보": {"handles": ["Knox", "Lucifer"], "categories": ["Announcements"]},
        "_개인정보_유출_후보": [],
        "_한국_관련_유출_최근": [],
        "_들어가는_법_구조": {
            "value": "가입은 초대 코드가 필요합니다.",
            "observed_at": "2026-08-24",
            "source": '규칙/FAQ 페이지 원문 그대로 인용 ("Rules", http://abc123.onion/rules)',
        },
    }
    results.update(overrides)
    return results


def test_generate_profile_markdown_includes_all_requested_fields_in_order():
    md = prg.generate_profile_markdown({"name": "darkforums"}, _base_results())

    labels = [
        "포럼 이름", "상태", "확인일", "운영자(추정)", "어떤 곳인지", "개인정보 유출",
        "한국 관련 유출", "국가", "규모", "사용 언어", "클리어 주소", "어니언 주소", "비고",
        "들어가는 법",
    ]
    positions = [md.index(f"**{label}") for label in labels]
    assert positions == sorted(positions)  # 요청받은 순서 그대로


def test_generate_profile_markdown_does_not_write_narrative_summary():
    """"어떤 곳인지"는 코드가 서술하지 않는다 — 원문(카테고리 목록)만 그대로 노출해야 한다."""
    md = prg.generate_profile_markdown({"name": "darkforums"}, _base_results())

    assert "사람/AI가 이 크롤 데이터 보고 직접 서술 필요" in md
    assert "Announcements, Databases, Sellers Place" in md


def test_generate_profile_markdown_entering_line_does_not_summarize_rules():
    """"들어가는 법"도 마찬가지 — 원문 미리보기만 남기고 해석 문장은 쓰지 않는다."""
    md = prg.generate_profile_markdown({"name": "darkforums"}, _base_results())

    assert "사람/AI가 직접 서술 필요" in md
    assert "가입은 초대 코드가 필요합니다" in md


def test_generate_profile_markdown_country_derived_from_top_language():
    md = prg.generate_profile_markdown({"name": "darkforums"}, _base_results())

    assert "영어권" in md
    assert "67%" in md


def test_generate_profile_markdown_language_line_shows_top_language_only():
    """2026-08-24 사용자 요청: "제일 사용 비율이 높은 언어로 확정" — 전체 분포 대신 1개만."""
    md = prg.generate_profile_markdown({"name": "darkforums"}, _base_results())

    assert "영어(English) 67% (2026-08-24)" in md
    assert "독일어" not in md


def test_generate_profile_markdown_operator_line_lists_handles_without_counts():
    md = prg.generate_profile_markdown({"name": "darkforums"}, _base_results())

    assert "Knox, Lucifer (Announcements 게시판 공지 작성자 기준, 확정 아님)" in md


def test_generate_profile_markdown_operator_line_unseen_without_candidates():
    md = prg.generate_profile_markdown(
        {"name": "darkforums"}, _base_results(_운영자_후보={"handles": [], "categories": []})
    )

    assert "**운영자(추정)**: 안 봄" in md


def test_generate_profile_markdown_pii_block_renders_bullet_list():
    results = _base_results(
        _개인정보_유출_후보=[
            {"title": "DUOLINGO Database 500M users", "category": "Sellers Place", "author": "Xzero"},
        ]
    )

    md = prg.generate_profile_markdown({"name": "darkforums"}, results)

    assert '  - "DUOLINGO Database 500M users" (Sellers Place, Xzero)' in md


def test_generate_profile_markdown_korea_block_renders_numbered_bold_list():
    results = _base_results(
        _한국_관련_유출_최근=[
            {
                "title": "[south korea] SK Telecom 26+ millions",
                "category": "Leaks Market",
                "author": "SpartanX",
                "date": "2026-07-08",
            },
        ]
    )

    md = prg.generate_profile_markdown({"name": "darkforums"}, results)

    assert '**한국 관련 유출 (최근 유출건 1건)**' in md
    assert '1. **"[south korea] SK Telecom 26+ millions"** — Leaks Market, 작성자 SpartanX, 2026-07-08.' in md


def test_generate_profile_markdown_clear_url_from_whitelist_when_present():
    md = prg.generate_profile_markdown({"name": "darkforums", "clear_url": "darkforums.ru"}, _base_results())

    assert "**클리어 주소**: darkforums.ru (미검증)" in md


def test_generate_profile_markdown_clear_url_unseen_when_absent():
    md = prg.generate_profile_markdown({"name": "darkforums"}, _base_results())

    assert "**클리어 주소**: 안 봄" in md


def test_generate_profile_markdown_notes_always_unseen():
    """"비고"는 report_generator.FORBIDDEN_AUTO_FIELDS의 "비고"와 같은 이유로 항상 안 봄."""
    md = prg.generate_profile_markdown({"name": "darkforums"}, _base_results())

    assert "**비고**: 안 봄" in md


def test_generate_profile_markdown_drops_verbose_source_citations():
    """2026-08-25 사용자 요청: 매 필드에 수집 방법론 문구를 반복해서 붙이지 않는다."""
    md = prg.generate_profile_markdown({"name": "darkforums"}, _base_results())

    assert "홈페이지 nav 1단계 depth" not in md
    assert "직접 접속" not in md
    assert "본문 정규식 매칭" not in md


def test_write_report_produces_single_file(tmp_path):
    """CLAUDE.md §4.1: 결과 MD 파일은 1개만 반출. 2026-08-25(사용자 확인)부터 노션 23칸 공식
    스키마 대신 이 템플릿 하나로 전면 교체됐다 — report_generator.generate_markdown()은 더 이상
    안 쓴다."""
    out_path = prg.write_report({"name": "darkforums"}, _base_results(), str(tmp_path))

    md_files = list(tmp_path.glob("*.md"))
    assert len(md_files) == 1
    content = md_files[0].read_text(encoding="utf-8")
    assert "darkforums 위협 프로파일" in content
    assert content.count("darkforums 위협 프로파일") == 1
    assert "darkforums 조사 결과" not in content  # 공식 23칸 스키마 헤더는 이제 안 나온다
    assert out_path == str(md_files[0])


def test_write_report_appends_crawl_completion_audit(tmp_path):
    results = {
        "_crawl_completion": {
            "complete": False,
            "categories": 3,
            "pages": 11,
            "posts": 42,
            "failures": 1,
            "pages_per_category": 5,
        },
        "_crawl_failures": [
            {
                "category": "Sellers Place",
                "page": 4,
                "url": "https://example.test/p4",
                "reason": "접속 실패",
            }
        ],
    }

    output = prg.write_report(
        {"name": "example", "url": "https://example.test"}, results, str(tmp_path)
    )
    text = Path(output).read_text(encoding="utf-8")

    assert "## 크롤링 완료 감사" in text
    assert "상태: 부분 완료" in text
    assert "Sellers Place p4" in text
