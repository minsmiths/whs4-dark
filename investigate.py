#!/usr/bin/env python3
"""진입점 CLI. Collector ①~⑦을 CLAUDE.md §1 동작 흐름대로 고정 순서 호출한다.

사용법:
    python investigate.py https://example.onion --type forum

Docker 안에서는 Dockerfile의 CMD가 환경변수(TARGET_URL, SOURCE_TYPE)로 이 스크립트를 호출한다.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any

import yaml

import config
import report_generator  # noqa: F401 - TODO(M2): write_report 호출부에서 사용 예정 (현재 주석 처리됨)
import session_manager  # noqa: F401 - TODO(M2): load_session 호출부에서 사용 예정 (현재 주석 처리됨)
from collectors import (
    access_probe,
    availability,
    content_sample,
    cross_reference,
    stats,
    structure,
    user_activity,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("investigate")


def load_whitelist(path: str = config.WHITELIST_PATH) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return data.get("sites", [])


def find_approved_source(url: str, source_type: str) -> dict[str, Any] | None:
    for entry in load_whitelist():
        if entry.get("url") == url:
            entry = dict(entry)
            entry.setdefault("source_type", source_type)
            entry.setdefault("name", url)
            return entry
    return None


def run_pipeline(page, source: dict[str, Any]) -> dict[str, Any]:
    """Collector ①~⑦을 순서대로 호출하고 report_generator 가 쓸 dict로 취합한다."""
    results: dict[str, Any] = {}

    logger.info("① availability")
    results.update(availability.run(page, source))

    logger.info("② structure")
    time.sleep(config.REQUEST_DELAY_MIN_SEC)
    results.update(structure.run(page, source))

    logger.info("③ stats")
    time.sleep(config.REQUEST_DELAY_MIN_SEC)
    results.update(stats.run(page, source))

    logger.info("④ content_sample")
    time.sleep(config.REQUEST_DELAY_MIN_SEC)
    results.update(content_sample.run(page, source))

    logger.info("⑤ cross_reference")
    # 이전 단계에서 모은 텍스트를 재사용한다 (새 페이지 요청을 만들지 않음).
    collected_texts = {
        "표본 게시글 제목": " ".join(p.get("title", "") for p in results.get("_표본_게시글", []))
    }
    results.update(cross_reference.run(collected_texts, source))

    logger.info("⑥ access_probe")
    time.sleep(config.REQUEST_DELAY_MIN_SEC)
    results.update(access_probe.run(page, source))

    logger.info("⑦ user_activity")
    results.update(user_activity.run(results.get("_표본_게시글", []), source))

    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="대상 URL (whitelist.yaml에 등록되어 있어야 함)")
    parser.add_argument(
        "--type",
        dest="source_type",
        default="forum",
        choices=["forum", "marketplace", "dls", "paste"],
        help="사이트 유형. MVP는 forum만 실제 구현.",
    )
    args = parser.parse_args(argv)

    source = find_approved_source(args.url, args.source_type)
    if source is None:
        logger.error("화이트리스트에 없는 URL 입니다: %s (whitelist.yaml 확인)", args.url)
        return 1

    if source.get("source_type") != "forum":
        logger.error("MVP는 source_type=forum만 실제 구현되어 있습니다.")
        return 1

    # TODO(M2): Playwright/Tor 컨텍스트 초기화, session_manager 로 세션 로드.
    # 아래는 M2~M5에서 채울 실제 흐름이다 (지금은 스캐폴딩 단계라 여기서 중단한다):
    #
    # from playwright.sync_api import sync_playwright
    # with sync_playwright() as p:
    #     browser = p.chromium.launch(
    #         proxy={"server": config.TOR_SOCKS_PROXY}, args=config.BROWSER_LAUNCH_ARGS
    #     )
    #     storage_state = session_manager.load_session(source["name"])
    #     context = browser.new_context(storage_state=storage_state)
    #     page = context.new_page()
    #     results = run_pipeline(page, source)
    #     browser.close()
    # out_path = report_generator.write_report(source, results, config.OUTPUT_DIR)
    # logger.info("결과 저장됨: %s", out_path)
    # print(out_path)
    # return 0
    logger.error("Playwright/Tor 연결부는 M2에서 구현 예정입니다 (스캐폴딩 단계).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
