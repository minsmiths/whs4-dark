"""원문(raw HTML) 스냅샷 저장. 로드맵 M2 산출물: `snapshots/<source_id>/<timestamp>/`.

CLAUDE.md §4.1: 스냅샷은 컨테이너 안(named volume)에만 남고 자동으로 반출되지 않는다.
컨테이너 밖으로 나가는 파일은 결과 MD 하나뿐이므로, 이 모듈이 만드는 파일들은 절대
output/ 이나 네트워크 전송 코드로 이어지지 않는다.
"""

from __future__ import annotations

import datetime as dt
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

import config

if TYPE_CHECKING:
    from playwright.sync_api import Page

logger = logging.getLogger(__name__)


def snapshot_path(source_id: str, label: str, suffix: str) -> Path:
    """스냅샷 디렉터리 안의 안전한 출력 경로를 만들고 반환한다."""
    timestamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    dir_path = Path(config.SNAPSHOTS_DIR) / source_id / timestamp
    dir_path.mkdir(parents=True, exist_ok=True)
    safe_label = "".join(c for c in label if c.isalnum() or c in ("-", "_")) or "page"
    safe_suffix = suffix if suffix.startswith(".") else f".{suffix}"
    return dir_path / f"{safe_label}{safe_suffix}"


def capture_content(page: Page, attempts: int = 5, delay_sec: float = 0.25) -> str | None:
    """리다이렉트 중인 페이지의 DOM이 안정될 때까지 짧게 재시도한다.

    스냅샷은 보조 산출물이므로 계속 탐색 중이면 예외로 전체 파이프라인을 종료하지 않는다.
    """
    for attempt in range(attempts):
        try:
            return page.content()
        except Exception:  # noqa: BLE001 - Playwright의 navigation race를 보조 기능에서 흡수
            if attempt + 1 < attempts:
                time.sleep(delay_sec)
    return None


def save_snapshot(page: Page, source_id: str, label: str) -> Path | None:
    """현재 페이지의 원문 HTML을 `snapshots/<source_id>/<timestamp>/<label>.html`에 저장한다.

    호출부(investigate.py, collectors/structure.py 등)가 페이지 탐색 직후 호출한다.
    """
    content = capture_content(page)
    if content is None:
        logger.warning("페이지가 계속 이동 중이어서 스냅샷을 건너뜀: %s", label)
        return None
    file_path = snapshot_path(source_id, label, ".html")
    file_path.write_text(content, encoding="utf-8")
    logger.info("스냅샷 저장됨: %s", file_path)
    return file_path
