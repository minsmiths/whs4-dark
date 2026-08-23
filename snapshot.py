"""원문(raw HTML) 스냅샷 저장. 로드맵 M2 산출물: `snapshots/<source_id>/<timestamp>/`.

CLAUDE.md §4.1: 스냅샷은 컨테이너 안(named volume)에만 남고 자동으로 반출되지 않는다.
컨테이너 밖으로 나가는 파일은 결과 MD 하나뿐이므로, 이 모듈이 만드는 파일들은 절대
output/ 이나 네트워크 전송 코드로 이어지지 않는다.
"""

from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import config

if TYPE_CHECKING:
    from playwright.sync_api import Page

logger = logging.getLogger(__name__)


def save_snapshot(page: Page, source_id: str, label: str) -> Path:
    """현재 페이지의 원문 HTML을 `snapshots/<source_id>/<timestamp>/<label>.html`에 저장한다.

    호출부(investigate.py, collectors/structure.py 등)가 페이지 탐색 직후 호출한다.
    """
    timestamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    dir_path = Path(config.SNAPSHOTS_DIR) / source_id / timestamp
    dir_path.mkdir(parents=True, exist_ok=True)
    safe_label = "".join(c for c in label if c.isalnum() or c in ("-", "_")) or "page"
    file_path = dir_path / f"{safe_label}.html"
    file_path.write_text(page.content(), encoding="utf-8")
    logger.info("스냅샷 저장됨: %s", file_path)
    return file_path
