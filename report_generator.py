"""Collector 결과 dict를 모아 노션 "다크웹 조사 가이드" 23개 칸 구조의 MD로 변환한다.

CLAUDE.md §7 참고. 이 파일에서 가장 중요한 불변식은 FORBIDDEN_AUTO_FIELDS 다:
이 목록에 있는 필드는 어떤 Collector가 값을 채워 보내더라도 절대 MD에 반영하지 않는다.
tests/test_report_generator.py 가 이 규칙만 전용으로 검증한다.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

# CLAUDE.md §7.2 — 절대 자동 채움 금지 필드. 값 자동 판단/자동 확정을 절대 하지 않는 칸.
# 이 상수는 실수로라도 값을 채우는 코드가 추가되면 유닛테스트가 즉시 잡아낼 수 있도록
# report_generator 안에서 단일 진실 공급원(single source of truth) 역할을 한다.
FORBIDDEN_AUTO_FIELDS: frozenset[str] = frozenset(
    {
        "웹에 올림",
        "조사 단계",
        "담당자",
        "국가",
        "유통 자리",
        "이전 이름·별칭",  # 확정 부분만 금지. "발견됨" 후보 기록은 별도 섹션에 남긴다.
        "연결된 곳",  # 확정 부분만 금지. cross_reference.py 의 "발견" 목록은 별도 섹션.
    }
)


def format_value(field_name: str, result: dict[str, Any] | None) -> str:
    """CLAUDE.md §7.1 값 포맷 규칙에 따라 Collector 반환값 하나를 MD 텍스트로 변환한다."""
    if field_name in FORBIDDEN_AUTO_FIELDS:
        return "안 봄"  # 사람 전결 — Collector가 무엇을 보내든 무시한다.

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


def generate_markdown(source: dict[str, Any], collector_results: dict[str, dict[str, Any]]) -> str:
    """source: whitelist.yaml 에서 읽은 대상 정보 (name, url, source_type ...).
    collector_results: {"상태": {...}, "규모": {...}, ...} 형태로 취합된 전체 필드.

    23개 칸 목록과 실제 매핑은 노션 "다크웹 조사 가이드" 스키마에 맞춰 M5에서 채운다.
    아래는 CLAUDE.md §7.3 출력 예시를 뼈대로 한 최소 구현이다.
    """
    today = dt.date.today().isoformat()
    lines = [
        f"# {source.get('name', source.get('url', 'unknown'))} 조사 결과 (자동 수집 초안 — 검토 필요)",
        "",
        f"- 확인일: {today}",
        f"- 상태: {format_value('상태', collector_results.get('상태'))}",
        f"- 주소: {source.get('url', '')}",
        f"- 규모: {format_value('규모', collector_results.get('규모'))}",
        f"- 사용 언어: {format_value('사용 언어', collector_results.get('사용 언어'))}",
        f"- 한국 관련 유출: {format_value('한국 관련 유출', collector_results.get('한국 관련 유출'))}",
    ]

    for field in FORBIDDEN_AUTO_FIELDS:
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
