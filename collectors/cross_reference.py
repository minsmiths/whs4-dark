"""⑤ 교차참조 크롤. 요구사항 3 대응: 사이트 간 연결 "발견" (로드맵 M4).

수집한 텍스트에서 URL, `.onion` 주소, 텔레그램 채널 패턴을 정규식으로 추출해
후보 목록으로만 기록한다. 자동으로 "연결된 곳"에 확정하지 않는다 — 사람이 검토 후 확정.
report_generator.py 의 FORBIDDEN_AUTO_FIELDS 가 "연결된 곳" 확정 필드를 별도로 막는다.
"""

from __future__ import annotations

import re
from typing import Any

URL_RE = re.compile(r"https?://\S+")
ONION_RE = re.compile(r"\b[a-z2-7]{16,56}\.onion\b", re.IGNORECASE)
TELEGRAM_RE = re.compile(r"t\.me/\w+")


def extract_mentions(text: str, context_label: str = "") -> list[str]:
    """텍스트에서 외부 언급 후보를 추출해 사람이 읽을 수 있는 문자열 목록으로 반환한다."""
    found = set(URL_RE.findall(text)) | set(ONION_RE.findall(text)) | set(TELEGRAM_RE.findall(text))
    label = f' ("{context_label}"에서 발견)' if context_label else ""
    return [f"{item}{label}" for item in sorted(found)]


def run(collected_texts: dict[str, str], source: dict[str, Any]) -> dict[str, Any]:
    """collected_texts: {"게시글 제목 또는 페이지 라벨": "원문 텍스트", ...}

    이전 Collector(structure, content_sample)가 수집한 텍스트를 모아서 investigate.py 가
    이 함수에 넘겨준다. Playwright page를 직접 열지 않는다 — 이미 가져온 텍스트만 정규식으로 훑는다.
    """
    result: dict[str, Any] = {}
    mentions: list[str] = []
    for label, text in collected_texts.items():
        mentions.extend(extract_mentions(text, context_label=label))

    deduped = sorted(set(mentions))
    result["_발견된_외부_언급"] = deduped
    # "연결된 곳" 자체는 §7.2 금지 필드(확정 부분)이므로 여기서 값을 채우지 않는다.
    return result
