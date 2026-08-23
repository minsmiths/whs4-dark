"""Collector 결과 dict를 모아 노션 "다크웹 조사 가이드" 23개 칸 구조의 MD로 변환한다.

CLAUDE.md §7 참고. 이 파일에서 가장 중요한 불변식은 FORBIDDEN_AUTO_FIELDS 다:
이 목록에 있는 필드는 어떤 Collector가 값을 채워 보내더라도 절대 MD에 반영하지 않는다.
tests/test_report_generator.py 가 이 규칙만 전용으로 검증한다.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

# CLAUDE.md §7.2 — 절대 자동 채움 금지 필드. 값 자동 판단/자동 확정을 절대 하지 않는 칸.
# 노션 "다크웹 조사 가이드" 23개 칸 스키마(2026-08-19 확정) 기준 "자동화 소유권"이 순수
# MANUAL인 칸 전부 + 확정 부분만 금지되는 후보성 칸(이전 이름·별칭, 연결된 곳) 이다.
# 이 상수는 실수로라도 값을 채우는 코드가 추가되면 유닛테스트가 즉시 잡아낼 수 있도록
# report_generator 안에서 단일 진실 공급원(single source of truth) 역할을 한다.
FORBIDDEN_AUTO_FIELDS: frozenset[str] = frozenset(
    {
        "순위",  # MANUAL
        "조사 단계",  # MANUAL
        "담당자",  # MANUAL(person)
        "유통 자리",  # MANUAL(판단)
        "이전 이름·별칭",  # 확정 부분만 금지. "발견됨" 후보 기록은 별도 섹션에 남긴다.
        "비고",  # MANUAL
        "국가",  # MANUAL(판단)
        "연결된 곳",  # 확정 부분만 금지. cross_reference.py 의 "발견" 목록은 별도 섹션.
        "웹에 올림",  # MANUAL 전용, 자동화 절대 변경 금지 — 레코드 전체 게시 게이트
    }
)

# 게시범위(23칸 스키마 #19 "들어가는 법")가 INTERNAL_ONLY인 칸. FORBIDDEN_AUTO_FIELDS와는 다른
# 축이다 — 자동 채움 자체는 허용되지만(AUTO-append), 노션에 옮겨 적는 공개 칸 목록에서는 빠지고
# generate_markdown()이 별도의 "내부 참고자료" 섹션에만 출력한다.
INTERNAL_ONLY_FIELDS: frozenset[str] = frozenset({"들어가는 법"})

# 노션 "다크웹 조사 가이드" 23개 칸의 순서(2026-08-19 사용자 제공 스키마) 그대로다.
# "확인일"과 "주소"는 tri-state dict가 아니라 계산값이라 generate_markdown()에서 따로 다루고,
# "들어가는 법"은 INTERNAL_ONLY라 이 루프에서 제외하고 별도 섹션에서만 출력한다.
FIELD_ORDER: tuple[str, ...] = (
    "순위",
    "조사 단계",
    "담당자",
    "확인일",
    "유통 자리",
    "주소",
    "어니언 주소",
    "이전 주소",
    "이전 이름·별칭",
    "어떤 곳인지",
    "규모",
    "사용 언어",
    "개인정보 유출",
    "한국 관련 유출",
    "출처",
    "비고",
    "가입 필요",
    "국가",
    "들어가는 법",
    "상태",
    "연결된 곳",
    "웹에 올림",
    "위키 반영",
)


def _format_tristate(result: dict[str, Any] | None) -> str:
    """CLAUDE.md §7.1 tri-state 포맷 규칙. FORBIDDEN_AUTO_FIELDS 검사는 하지 않는다 —
    호출부(format_value, 내부 전용 섹션 포맷터)가 각자 필요할 때만 그 검사를 적용한다.
    """
    if result is None:
        return "안 봄"  # 키 자체가 없음

    if "state" in result:
        state = result["state"]
        if state == "CONFIRMED_ABSENT":
            return "없음"
        if state == "BLOCKED":
            reason = result.get("reason", "사유 미상")
            today = dt.date.today().isoformat()
            return f"못 봄. {reason} ({today})"
        return "안 봄"

    if "value" in result:
        value = result["value"]
        observed_at = result.get("observed_at", "날짜 미상")
        source = result.get("source", "출처 미상")
        return f"{value} ({observed_at}, {source})"

    return "안 봄"


def format_value(field_name: str, result: dict[str, Any] | None) -> str:
    """CLAUDE.md §7.1 값 포맷 규칙에 따라 Collector 반환값 하나를 MD 텍스트로 변환한다."""
    if field_name in FORBIDDEN_AUTO_FIELDS:
        return "안 봄"  # 사람 전결 — Collector가 무엇을 보내든 무시한다.

    return _format_tristate(result)


def generate_markdown(source: dict[str, Any], collector_results: dict[str, dict[str, Any]]) -> str:
    """source: whitelist.yaml 에서 읽은 대상 정보 (name, url, source_type ...).
    collector_results: {"상태": {...}, "규모": {...}, ...} 형태로 취합된 전체 필드.

    FIELD_ORDER(노션 "다크웹 조사 가이드" 23개 칸 순서)를 그대로 순회하며 한 줄도 통째로
    누락하지 않는다(M5 완료 기준). "들어가는 법"만 게시범위 INTERNAL_ONLY라 이 목록에서
    빠지고 맨 아래 별도 섹션에서 다룬다 — 노션에는 옮기지 않는 내부 참고용이라는 뜻이다.
    """
    today = dt.date.today().isoformat()
    lines = [
        f"# {source.get('name', source.get('url', 'unknown'))} 조사 결과 (자동 수집 초안 — 검토 필요)",
        "",
    ]

    for field in FIELD_ORDER:
        if field == "확인일":
            lines.append(f"- 확인일: {today}")
        elif field == "주소":
            lines.append(f"- 주소: {source.get('url', '')}")
        elif field in INTERNAL_ONLY_FIELDS:
            continue  # 아래 "내부 참고자료" 섹션에서만 출력 — 공개 칸 목록에는 넣지 않는다.
        else:
            lines.append(f"- {field}: {format_value(field, collector_results.get(field))}")

    mentions = collector_results.get("_발견된_외부_언급", [])
    if mentions:
        lines += ["", "## 발견된 외부 언급 (검토 필요, 자동 확정 아님)"]
        lines += [f"- {m}" for m in mentions]

    handles = collector_results.get("_표본_핸들", [])
    if handles:
        lines += ["", "## 표본 내 자주 등장하는 핸들 (판단 아님, 관찰만)"]
        for h in handles:
            lines.append(f"- {h['handle']} — {h['count']}건, 최근 {h['last_seen']}")
            lines.append("  - 판단 근거: (빈칸, 사람이 작성)")
            lines.append("  - 반대 근거: (빈칸, 사람이 작성)")

    # "들어가는 법" — structure.py(규칙 페이지 원문) + access_probe.py(가입 폼 필드)를
    # investigate.py가 [(라벨, tri-state dict), ...] 로 합쳐 넘긴다(AUTO-append, §19).
    # 게시범위 INTERNAL_ONLY이므로 위 공개 칸 목록에는 없고 여기서만 출력한다.
    entering_entries = collector_results.get("들어가는 법", [])
    if entering_entries:
        lines += ["", "## 내부 참고자료 — 들어가는 법 (게시 금지, 노션에 옮기지 않음)"]
        for label, entry in entering_entries:
            lines.append(f"- {label}: {_format_tristate(entry)}")
        lines.append("- 사람 보완: (빈칸, 필요 시 직접 작성)")

    return "\n".join(lines) + "\n"


def write_report(
    source: dict[str, Any], collector_results: dict[str, dict[str, Any]], output_dir: str
) -> str:
    from pathlib import Path

    source_id = source.get("name") or source.get("url", "unknown")
    safe_id = "".join(c for c in source_id if c.isalnum() or c in ("-", "_", ".")) or "unknown"
    timestamp = dt.datetime.now().strftime("%Y%m%d")
    out_path = Path(output_dir) / f"{safe_id}_{timestamp}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(generate_markdown(source, collector_results), encoding="utf-8")
    return str(out_path)
