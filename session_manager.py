"""로그인 세션 저장/재사용. 담당 요구사항 1 (CLAUDE.md §6, 로드맵 M1).

절대 하지 않는 것: 자동 재로그인, 자동 회원가입. 세션이 없거나 만료되면
BLOCKED 상태를 반환하고 사람이 VNC로 다시 로그인할 때까지 기다린다.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import config

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext, Page

logger = logging.getLogger(__name__)


def _session_path(source_id: str) -> Path:
    return Path(config.SESSIONS_DIR) / f"{source_id}.json"


def save_session(context: BrowserContext, source_id: str) -> Path:
    """사람이 VNC로 로그인 완료한 뒤 호출한다.

    사용 예 (M1 §세부 작업 2):
        context = browser.new_context()
        page = context.new_page()
        page.goto(login_url)
        input("로그인 완료 후 Enter를 누르세요...")
        session_manager.save_session(context, source_id)
    """
    path = _session_path(source_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(path))
    logger.info("세션 저장됨: %s", path)
    return path


def load_session(source_id: str) -> str | None:
    """저장된 세션 파일 경로를 반환한다. 없으면 None.

    사용 예:
        storage_state = session_manager.load_session(source_id)
        context = browser.new_context(storage_state=storage_state)
    """
    path = _session_path(source_id)
    if not path.exists():
        return None
    return str(path)


def is_session_valid(page: Page, logged_in_selector: str) -> bool:
    """로그인 후에만 보이는 요소(예: 마이페이지 링크)가 있는지 확인한다.

    `logged_in_selector`는 대상 사이트별로 다르므로 M2에서 실제 마크업을 보고 확정한다.
    """
    try:
        return page.locator(logged_in_selector).count() > 0
    except Exception:  # noqa: BLE001 - 페이지 상태가 불안정할 수 있음, 무효로 취급
        return False


def record_session_expired(source_id: str, reason: str = "세션 만료") -> None:
    """세션 무효 시 run_log.json 에 이벤트를 남긴다.

    자동 재로그인은 시도하지 않는다 — 호출부(investigate.py)가 해당 Collector
    단계를 BLOCKED(reason)로 처리하고 다음 단계로 진행해야 한다.
    """
    entry = {"source_id": source_id, "event": "session_expired", "reason": reason}
    log_path = Path(config.RUN_LOG_PATH)
    lines = []
    if log_path.exists():
        lines = log_path.read_text(encoding="utf-8").splitlines()
    lines.append(json.dumps(entry, ensure_ascii=False))
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.warning("세션 만료 — 재로그인 필요 (source_id=%s)", source_id)
