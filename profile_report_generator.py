"""사용자 지정 템플릿(2026-08-25) 자동 생성 — 포럼 이름/상태/확인일/운영자(추정)/어떤 곳인지/
개인정보 유출/한국 관련 유출/국가/규모/사용 언어/클리어 주소/어니언 주소/비고/들어가는 법 순서.

2026-08-25(사용자 확인): 노션 23칸 공식 스키마(`report_generator.py`)를 대체하는 파이프라인의
유일한 산출물이다 — 두 파일을 만들지 않는다(CLAUDE.md §4.1 "결과 MD 파일 1개").
`report_generator.py` 자체와 그 테스트는 그대로 남아 있지만(§8, CODEOWNERS 리뷰 대상이라
지우지 않음) `investigate.py`는 더 이상 그걸 호출하지 않는다.

각 필드는 값 + 날짜만 짧게 보여준다(2026-08-25, 사용자 확인 — 매 줄에 수집 방법론을 반복해서
붙이는 걸 원치 않음). 값을 어떻게 계산했는지는 이 파일과 `collectors/*.py`의 코드/주석이
출처다 — MD 안에는 안 넣는다.

**"어떤 곳인지"/"들어가는 법"은 이 모듈이 서술하지 않는다.** 창설 연혁·운영 배경 같은 서술형
소개글이나 규칙 원문의 해석(예: "가입 시 추가 권한 부여 구조로 추정")은 그 시점 데이터를 보고
사람(또는 대화형 AI 세션)이 직접 써야 하는 영역이다 — 이 파이프라인은 Tor 전용 아웃바운드에
외부 서비스 자격증명을 두지 않는 격리 컨테이너 안에서 도니(CLAUDE.md §4.1), LLM API 호출 자체가
없다. 그래서 코드가 자동으로 "서술"할 방법이 없고, 대신 사람이 바로 쓸 수 있게 원본(카테고리
목록/규칙 원문 앞부분)을 그 자리에 남겨만 둔다(2026-08-25, 사용자 확인).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

# langdetect(ISO 639-1/1-변형) 코드 → 한국어 표기. "국가"/"사용 언어" 요약 줄에 쓴다.
# 목록에 없는 코드는 코드 그대로 노출한다(새 대상 언어가 나와도 안 깨지게).
LANG_DISPLAY_NAMES: dict[str, str] = {
    "en": "영어(English)", "de": "독일어(German)", "pt": "포르투갈어", "ca": "카탈루냐어",
    "id": "인도네시아어", "it": "이탈리아어", "no": "노르웨이어", "vi": "베트남어",
    "fr": "프랑스어", "tl": "타갈로그어", "ro": "루마니아어", "et": "에스토니아어",
    "da": "덴마크어", "es": "스페인어", "so": "소말리어", "nl": "네덜란드어",
    "sw": "스와힐리어", "af": "아프리칸스어", "sv": "스웨덴어", "cy": "웨일스어",
    "fi": "핀란드어", "hu": "헝가리어", "pl": "폴란드어", "sk": "슬로바키아어",
    "hr": "크로아티아어", "sl": "슬로베니아어", "cs": "체코어", "lt": "리투아니아어",
    "tr": "터키어", "sq": "알바니아어", "lv": "라트비아어", "zh-cn": "중국어",
    "ru": "러시아어", "bg": "불가리아어", "bn": "벵골어", "ko": "한국어", "ja": "일본어",
    "unknown": "미상",
}  # noqa: E501 - 표 형태 매핑, 줄바꿈하면 더 안 읽힘

# "국가" 필드용 — 언어권을 국가/지역 명칭으로 단순 매핑. 이 매핑에 없는 언어는
# f"{언어명} 사용권"으로 대체한다(예: 크로아티아어 → "크로아티아어 사용권"). 콘텐츠 언어가
# 운영자 국적/서버 소재국을 보장하지 않으므로 항상 "약한 신호" 캐비엇과 함께 쓴다.
LANG_TO_REGION_HINT: dict[str, str] = {
    "en": "영어권", "ru": "러시아", "zh-cn": "중국", "ko": "한국", "ja": "일본", "de": "독일어권",
}

# "비고"는 report_generator.FORBIDDEN_AUTO_FIELDS의 "비고"와 같은 이유로 MANUAL 전용이다 —
# 이 모듈은 근거 없이 채우지 않고 항상 이 값으로 고정한다.
NOTES_PLACEHOLDER = "안 봄"

# "들어가는 법" 자리에 원문 미리보기로 남길 최대 글자 수 — 규칙 페이지 원문은 보통 수백 자라
# 그대로 다 박으면 이 필드 하나가 문서 절반을 차지한다.
RULES_PREVIEW_MAX_CHARS = 150


def _lang_name(lang: str) -> str:
    return LANG_DISPLAY_NAMES.get(lang, lang)


def _lang_short_name(lang: str) -> str:
    """"영어(English)" → "영어". "국가" 줄은 괄호 안에서 또 괄호를 쓰면 안 읽혀서 짧은 이름만 쓴다."""
    return _lang_name(lang).split("(")[0].strip()


def _value_and_date(result: dict[str, Any] | None) -> str:
    """값 + 날짜만 짧게. tri-state 규칙(CLAUDE.md §7.1)은 지키되 "source"(수집 방법론)는
    MD에 반복해서 넣지 않는다(2026-08-25, 사용자 확인) — 대신 이 모듈 docstring/주석이 출처다.
    """
    if result is None:
        return "안 봄"
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
        observed_at = result.get("observed_at", "날짜 미상")
        return f"{result['value']} ({observed_at})"
    return "안 봄"


def _country_line(top_lang: dict[str, Any] | None) -> str:
    if not top_lang:
        return "안 봄"
    lang = top_lang["lang"]
    region = LANG_TO_REGION_HINT.get(lang, f"{_lang_short_name(lang)} 사용권")
    return f"{region} (사용 언어 최다 비율 기준 — {_lang_short_name(lang)} {top_lang['pct']}%)"


def _language_line(top_lang: dict[str, Any] | None, observed_at: str) -> str:
    """최다 비율 언어 1개만 확정 표기한다(2026-08-24, 사용자 요청: "제일 사용 비율이 높은
    언어로 확정을 지어"). 전체 분포는 공식 스키마가 쓰던 "사용 언어" 원본 값에 남아 있다."""
    if not top_lang:
        return "안 봄"
    return f"{_lang_name(top_lang['lang'])} {top_lang['pct']}% ({observed_at})"


def _operator_line(operator_candidates: dict[str, Any] | None) -> str:
    handles = (operator_candidates or {}).get("handles") or []
    if not handles:
        return "안 봄"
    categories = ", ".join((operator_candidates or {}).get("categories") or []) or "공지"
    return f"{', '.join(handles)} ({categories} 게시판 공지 작성자 기준, 확정 아님)"


def _pii_block(items: list[dict[str, str]] | None, today: str) -> str:
    if not items:
        return " 없음"
    bullets = "\n".join(f'  - "{it["title"]}" ({it["category"]}, {it["author"]})' for it in items)
    return f"\n{bullets}\n  ({today})"


def _korea_block(items: list[dict[str, str]] | None) -> tuple[str, int]:
    if not items:
        return " 없음", 0
    lines = [
        f'  {i}. **"{it["title"]}"** — {it["category"]}, 작성자 {it["author"]}, {it["date"]}.'
        for i, it in enumerate(items, 1)
    ]
    return "\n" + "\n".join(lines), len(items)


def _entering_line(rules_result: dict[str, Any] | None) -> str:
    """"들어가는 법" — 규칙/FAQ 원문을 요약하지 않는다(CLAUDE.md §6). 코드는 원문 앞부분만
    미리보기로 남기고, 실제 해석·요약 문장은 사람/AI가 요청 시 직접 채운다."""
    raw = (rules_result or {}).get("value") if rules_result else None
    if not raw:
        return "(사람/AI가 직접 서술 필요 — 규칙/FAQ 원문 없음)"
    preview = " ".join(raw.split())  # 줄바꿈 제거해서 한 줄 미리보기로
    if len(preview) > RULES_PREVIEW_MAX_CHARS:
        preview = preview[:RULES_PREVIEW_MAX_CHARS] + "…"
    return f'(사람/AI가 직접 서술 필요 — 규칙/FAQ 원문 시작: "{preview}")'


def generate_profile_markdown(source: dict[str, Any], results: dict[str, Any]) -> str:
    """results: investigate.run_pipeline()이 만든 dict(+ 이 템플릿 전용 후보 필드들).

    호출부(investigate.py)가 다음 후보 필드를 미리 채워서 넘겨야 한다(비어 있으면 "안 봄"):
    "_운영자_후보"(user_activity.find_operator_candidates), "_개인정보_유출_후보"
    (content_sample.find_notable_leak_candidates), "_한국_관련_유출_최근"
    (content_sample.find_korea_specific_leaks).
    """
    today = dt.date.today().isoformat()
    name = source.get("name", source.get("url", "unknown"))
    top_lang = results.get("_사용_언어_최다")
    lang_observed_at = (results.get("사용 언어") or {}).get("observed_at", today)
    korea_block, korea_count = _korea_block(results.get("_한국_관련_유출_최근"))

    lines = [
        f"# {name} 위협 프로파일 (초안 — 검토 필요)",
        "",
        f"- **포럼 이름**: {name}",
        f"- **상태**: {_value_and_date(results.get('상태'))}",
        f"- **확인일**: {today}",
        f"- **운영자(추정)**: {_operator_line(results.get('_운영자_후보'))}",
        "",
        "- **어떤 곳인지**: (사람/AI가 이 크롤 데이터 보고 직접 서술 필요 — 카테고리 원문: "
        f"{_value_and_date(results.get('어떤 곳인지'))})",
        "",
        "- **개인정보 유출 (표본에서 발견된 주목할 만한 유출 게시물)**:"
        f"{_pii_block(results.get('_개인정보_유출_후보'), today)}",
        "",
        f"- **한국 관련 유출 (최근 유출건 {korea_count}건)**:{korea_block}",
        "",
        f"- **국가**: {_country_line(top_lang)}",
        "",
        f"- **규모**: {_value_and_date(results.get('규모'))}",
        "",
        f"- **사용 언어**: {_language_line(top_lang, lang_observed_at)}",
        "",
        "- **클리어 주소**: "
        + (f"{source['clear_url']} (미검증)" if source.get("clear_url") else "안 봄"),
        "",
        f"- **어니언 주소**: {_value_and_date(results.get('어니언 주소'))}",
        "",
        f"- **비고**: {NOTES_PLACEHOLDER}",
        "",
        "- **들어가는 법 (가입 조건)**: " + _entering_line(results.get("_들어가는_법_구조")),
    ]
    return "\n".join(lines) + "\n"


def _crawl_audit_markdown(results: dict[str, Any]) -> str:
    completion = results.get("_crawl_completion")
    if not completion:
        return ""
    state = "완료" if completion.get("complete") else "부분 완료"
    lines = [
        "",
        "## 크롤링 완료 감사",
        "",
        f"- 상태: {state}",
        f"- 방문 카테고리: {completion.get('categories', 0)}개",
        f"- 방문 목록 페이지: {completion.get('pages', 0)}개",
        f"- 수집 헤드라인: {completion.get('posts', 0)}개",
        f"- 카테고리당 페이지 제한: {completion.get('pages_per_category', 0)}페이지",
        f"- 실패: {completion.get('failures', 0)}건",
    ]
    for failure in results.get("_crawl_failures", []):
        lines.append(
            f"  - {failure.get('category', '?')} p{failure.get('page', '?')}: "
            f"{failure.get('reason', '알 수 없음')} ({failure.get('url', '')})"
        )
    return "\n".join(lines) + "\n"


def write_report(source: dict[str, Any], results: dict[str, Any], output_dir: str) -> str:
    """이 템플릿을 output/<source_id>_<timestamp>.md 로 저장한다 — 파이프라인의 유일한 산출물
    (CLAUDE.md §4.1 "결과 MD 파일 1개")."""
    from pathlib import Path

    profile_md = generate_profile_markdown(source, results) + _crawl_audit_markdown(results)

    source_id = source.get("name") or source.get("url", "unknown")
    safe_id = "".join(c for c in source_id if c.isalnum() or c in ("-", "_", ".")) or "unknown"
    timestamp = dt.datetime.now().strftime("%Y%m%d")
    out_path = Path(output_dir) / f"{safe_id}_{timestamp}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(profile_md, encoding="utf-8")
    return str(out_path)
