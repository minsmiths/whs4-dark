"""⑥ 접근성 프로빙. 요구사항 6 대응: 가입 조건 파악 (로드맵 M4).

절대 하지 않는 것: 가입 폼 제출. 입력 필드 목록만 수집하고 값을 채워 넣거나
전송하는 코드는 만들지 않는다 (CLAUDE.md §3-2, §3-3).
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.sync_api import Page

logger = logging.getLogger(__name__)

# TODO(M4): 실제 대상 사이트 마크업 확인 후 확정.
PASSWORD_INPUT_SELECTOR = "input[type=password]"  # noqa: S105 - 비밀번호 값이 아니라 CSS selector 문자열
REGISTER_FORM_FIELD_SELECTOR = "form input"


def run(page: Page, source: dict[str, Any]) -> dict[str, Any]:
    today = dt.date.today().isoformat()
    result: dict[str, Any] = {}

    has_login_form = page.locator(PASSWORD_INPUT_SELECTOR).count() > 0
    result["가입 필요"] = {"value": has_login_form, "observed_at": today, "source": "로그인 폼 존재 여부"}

    if not has_login_form:
        return result

    # 입력 필드 목록만 수집한다 — 절대 값을 채워 제출하지 않는다.
    fields = page.locator(REGISTER_FORM_FIELD_SELECTOR).all()
    field_names = []
    for field in fields:
        try:
            name = field.get_attribute("name") or field.get_attribute("placeholder") or ""
        except Exception:  # noqa: BLE001
            logger.debug("가입 필드 파싱 실패, 건너뜀", exc_info=True)
            continue
        if name:
            field_names.append(name)

    if field_names:
        result["들어가는 법"] = {
            "value": f"요구 필드: {', '.join(dict.fromkeys(field_names))}",
            "observed_at": today,
            "source": "가입 페이지 입력 필드 (제출하지 않음)",
        }
    else:
        result["들어가는 법"] = {"state": "BLOCKED", "reason": "가입 폼 필드 파싱 실패"}

    return result
