"""① 가용성 체크. 요구사항 대응: 사이트 상태 확인 (로드맵 M2).

절대 자동 확정하지 않는 것: OFFLINE 여부. 압수배너/파킹 페이지 키워드가 매칭돼도
"후보-OFFLINE(사람 확인 필요)"까지만 기록한다 (CLAUDE.md §1 핵심 안전장치).
"""

from __future__ import annotations

import datetime as dt
import re
import time
from typing import TYPE_CHECKING, Any

import config

if TYPE_CHECKING:
    from playwright.sync_api import Page

ONION_RE = re.compile(r"\b[a-z2-7]{16,56}\.onion\b", re.IGNORECASE)


def run(page: Page, source: dict[str, Any]) -> dict[str, Any]:
    url = source["url"]
    today = dt.date.today().isoformat()
    result: dict[str, Any] = {}

    start = time.monotonic()
    try:
        response = page.goto(url, timeout=config.PAGE_LOAD_TIMEOUT_MS, wait_until=config.PAGE_WAIT_UNTIL)
    except Exception:  # noqa: BLE001 - 타임아웃 등 Playwright 예외 전반
        result["상태"] = {"state": "BLOCKED", "reason": "타임아웃 또는 접속 실패"}
        return result
    elapsed_ms = int((time.monotonic() - start) * 1000)

    body_text = page.content().lower()

    if any(kw in body_text for kw in config.SEIZED_BANNER_KEYWORDS):
        result["상태"] = {
            "value": "후보-OFFLINE(사람 확인 필요)",
            "observed_at": today,
            "source": "압수배너 키워드 매칭",
        }
    elif any(kw in body_text for kw in config.DOMAIN_PARKING_KEYWORDS):
        result["상태"] = {
            "value": "후보-OFFLINE(도메인 파킹, 사람 확인 필요)",
            "observed_at": today,
            "source": "파킹 페이지 키워드 매칭",
        }
    elif response is not None and response.ok:
        result["상태"] = {"value": "online", "observed_at": today, "source": "직접 접속"}
    else:
        status = response.status if response else "unknown"
        result["상태"] = {"state": "BLOCKED", "reason": f"응답 코드 {status}"}

    result["_응답시간_ms"] = elapsed_ms  # report_generator 는 참조하지 않음, 로깅/디버그용

    onion_location = response.headers.get("onion-location") if response else None
    onion_match = ONION_RE.search(body_text)
    if onion_location:
        result["어니언 주소"] = {
            "value": onion_location,
            "observed_at": today,
            "source": "Onion-Location 헤더",
        }
    elif onion_match:
        result["어니언 주소"] = {
            "value": onion_match.group(0),
            "observed_at": today,
            "source": "본문 정규식 매칭 (후보)",
        }
    else:
        result["어니언 주소"] = {"state": "CONFIRMED_ABSENT"}

    return result
