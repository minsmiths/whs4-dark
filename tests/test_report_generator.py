"""CLAUDE.md §7.2 "절대 자동 채움 금지 필드" 전용 유닛테스트.

docs/security-checklist.md 의 "자동 확정 금지" 항목이 이 테스트로 CI에서 검증된다.
Collector가 실수로 이 필드들에 값을 채워 보내더라도, report_generator는 항상 "안 봄"을
출력해야 한다.
"""

from __future__ import annotations

import report_generator


def test_forbidden_fields_are_never_auto_filled():
    """FORBIDDEN_AUTO_FIELDS 의 모든 필드는, 그럴듯한 값이 주어져도 "안 봄"으로 출력된다."""
    suspicious_value = {"value": "확정됨(자동)", "observed_at": "2026-08-18", "source": "테스트"}

    for field in report_generator.FORBIDDEN_AUTO_FIELDS:
        output = report_generator.format_value(field, suspicious_value)
        assert output == "안 봄", f"{field} 필드가 자동으로 채워짐: {output!r}"


def test_forbidden_fields_stay_unfilled_even_with_blocked_state():
    for field in report_generator.FORBIDDEN_AUTO_FIELDS:
        output = report_generator.format_value(field, {"state": "BLOCKED", "reason": "테스트"})
        assert output == "안 봄"


def test_normal_field_value_format():
    result = {"value": "online", "observed_at": "2026-08-18", "source": "직접 접속"}
    assert report_generator.format_value("상태", result) == "online (2026-08-18, 직접 접속)"


def test_normal_field_confirmed_absent():
    assert report_generator.format_value("규모", {"state": "CONFIRMED_ABSENT"}) == "없음"


def test_normal_field_blocked():
    output = report_generator.format_value("규모", {"state": "BLOCKED", "reason": "로그인 필요"})
    assert output.startswith("못 봄. 로그인 필요")


def test_normal_field_missing_key_is_not_seen():
    assert report_generator.format_value("규모", None) == "안 봄"


def test_field_order_has_exactly_23_columns():
    """노션 '다크웹 조사 가이드' 스키마(2026-08-19 확정)는 23개 칸이다."""
    assert len(report_generator.FIELD_ORDER) == 23


def test_generate_markdown_never_omits_a_column_entirely():
    """M5 완료 기준: 23개 칸 전부 값/tri-state/빈칸 중 하나로 채워지고 통째로 누락된 칸이 없다."""
    source = {"name": "example-forum", "url": "http://example.onion"}
    md = report_generator.generate_markdown(source, {})

    exportable_fields = [f for f in report_generator.FIELD_ORDER if f not in ("확인일", "주소")]
    for field in exportable_fields:
        if field in report_generator.INTERNAL_ONLY_FIELDS:
            continue  # 내부 참고자료 섹션에서 별도로 검증(아래 테스트)
        assert f"- {field}:" in md, f"{field} 칸이 MD에서 통째로 빠짐"
    assert "- 확인일:" in md
    assert "- 주소:" in md


def test_generate_markdown_puts_entering_field_in_internal_section_only():
    """'들어가는 법'(#19)은 게시범위 INTERNAL_ONLY라 공개 칸 목록이 아니라
    '내부 참고자료' 섹션에만 나와야 한다."""
    source = {"name": "example-forum", "url": "http://example.onion"}
    rules_entry = {
        "value": "가입은 초대 코드가 필요합니다",
        "observed_at": "2026-08-18",
        "source": "규칙 페이지",
    }
    register_entry = {
        "value": "요구 필드: username, email",
        "observed_at": "2026-08-18",
        "source": "가입 페이지",
    }
    collector_results = {
        "들어가는 법": [
            ("규칙/FAQ 페이지 원문", rules_entry),
            ("가입 페이지 입력 필드", register_entry),
        ]
    }

    md = report_generator.generate_markdown(source, collector_results)

    assert "## 내부 참고자료 — 들어가는 법" in md
    assert "가입은 초대 코드가 필요합니다" in md
    assert "요구 필드: username, email" in md
    # 공개 칸 목록 줄("- 들어가는 법: ...")로는 나오지 않는다.
    assert "- 들어가는 법:" not in md


def test_newly_added_forbidden_fields_rank_and_notes_never_auto_filled():
    """23칸 스키마에서 순수 MANUAL 소유인 '순위'·'비고'도 FORBIDDEN_AUTO_FIELDS에 포함된다."""
    assert "순위" in report_generator.FORBIDDEN_AUTO_FIELDS
    assert "비고" in report_generator.FORBIDDEN_AUTO_FIELDS

    suspicious_value = {"value": "1위(자동)", "observed_at": "2026-08-18", "source": "테스트"}
    assert report_generator.format_value("순위", suspicious_value) == "안 봄"
    assert report_generator.format_value("비고", suspicious_value) == "안 봄"


def test_generate_markdown_forces_forbidden_fields_blank_end_to_end():
    """report_generator.write_report 이 사용하는 generate_markdown() 까지 통합 검증."""
    source = {"name": "example-forum", "url": "http://example.onion"}
    collector_results = {
        "상태": {"value": "online", "observed_at": "2026-08-18", "source": "직접 접속"},
        # 아래는 Collector가 절대 채우면 안 되는 필드에 실수로 값을 넣어본 경우를 흉내낸다.
        "담당자": {"value": "누군가", "observed_at": "2026-08-18", "source": "실수"},
        "국가": {"value": "KR", "observed_at": "2026-08-18", "source": "실수"},
    }

    md = report_generator.generate_markdown(source, collector_results)

    assert "- 담당자: 안 봄" in md
    assert "- 국가: 안 봄" in md
    assert "누군가" not in md
