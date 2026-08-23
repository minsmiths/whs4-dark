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
import report_generator
import session_manager
import snapshot
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


def load_whitelist(path: str | None = None) -> list[dict[str, Any]]:
    # 기본값을 함수 시그니처(모듈 임포트 시점)에 고정하지 않고 호출 시점에 config.WHITELIST_PATH
    # 를 다시 읽는다 — 그래야 런타임에 config 값이 바뀌어도(예: 테스트의 monkeypatch) 반영된다.
    p = Path(path if path is not None else config.WHITELIST_PATH)
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
    source_id = source.get("name") or source.get("url", "unknown")

    logger.info("① availability")
    results.update(availability.run(page, source))
    snapshot.save_snapshot(page, source_id, "availability_home")

    if source.get("requires_login"):
        selector = source.get("logged_in_selector")
        if not selector:
            logger.info(
                "logged_in_selector 미설정 — 세션 유효성 자동 확인을 건너뜁니다(whitelist.yaml에 추가 가능)."
            )
        elif session_manager.is_session_valid(page, selector):
            logger.info("세션 유효함 확인됨 (logged_in_selector 매칭)")
        else:
            # M1 완료 기준 (c): 자동 재로그인 없이 만료만 기록하고 파이프라인은 계속 진행한다.
            session_manager.record_session_expired(source_id)

    logger.info("② structure")
    time.sleep(config.REQUEST_DELAY_MIN_SEC)
    results.update(structure.run(page, source))
    # structure.run()은 규칙 페이지를 봤다가 원래 페이지로 복귀한다 — 복귀 후 상태를 스냅샷.
    snapshot.save_snapshot(page, source_id, "structure_home_after")

    # stats/content_sample은 "게시글이 실제로 나열된 목록 페이지"를 전제로 한다. 홈페이지엔
    # 보통 카테고리만 있고 게시글은 없어서, whitelist.yaml에 sample_list_url이 지정돼 있으면
    # 거기로 이동한 뒤에 두 Collector를 돌린다 (미지정 시 기존처럼 현재 페이지에서 시도).
    sample_list_url = source.get("sample_list_url")
    if sample_list_url:
        try:
            page.goto(sample_list_url, timeout=config.PAGE_LOAD_TIMEOUT_MS)
            snapshot.save_snapshot(page, source_id, "sample_list_page")
        except Exception:  # noqa: BLE001 - 이동 실패해도 stats/content_sample이 BLOCKED로 처리
            logger.warning("sample_list_url 접속 실패: %s", sample_list_url)
    else:
        logger.info(
            "sample_list_url 미설정 — 현재 페이지(보통 홈페이지)에서 표본을 시도합니다. "
            "게시글 목록이 없는 페이지면 규모/표본 관련 필드가 BLOCKED로 나올 수 있습니다."
        )

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
    rules_text = results.get("_들어가는_법_구조", {})
    if "value" in rules_text:
        collected_texts["규칙/FAQ 페이지 원문"] = rules_text["value"]
    results.update(cross_reference.run(collected_texts, source))

    logger.info("⑥ access_probe")
    time.sleep(config.REQUEST_DELAY_MIN_SEC)
    results.update(access_probe.run(page, source))

    logger.info("⑦ user_activity")
    results.update(user_activity.run(results.get("_표본_게시글", []), source))

    # "들어가는 법"(23칸 스키마 #19, AUTO-append, INTERNAL_ONLY)은 structure(규칙 페이지)와
    # access_probe(가입 폼) 두 Collector가 채운다. 같은 dict 키에 update()로 이어붙이면
    # 한쪽이 다른 쪽을 덮어쓰므로, 여기서 [(라벨, tri-state dict), ...] 리스트로 합친다.
    entering_entries: list[tuple[str, dict[str, Any]]] = []
    if "_들어가는_법_구조" in results:
        entering_entries.append(("규칙/FAQ 페이지 원문", results["_들어가는_법_구조"]))
    if "_들어가는_법_가입폼" in results:
        entering_entries.append(("가입 페이지 입력 필드", results["_들어가는_법_가입폼"]))
    results["들어가는 법"] = entering_entries

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

    source_id = source.get("name") or source.get("url", "unknown")

    # Playwright/Tor 연결부 (CLAUDE.md §4.1·§4.2): 아웃바운드는 Tor SOCKS5 프록시만 거치고,
    # BROWSER_LAUNCH_ARGS(config.py)에는 --no-sandbox 등을 절대 추가하지 않는다(§4.2-1).
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            proxy={"server": config.TOR_SOCKS_PROXY}, args=config.BROWSER_LAUNCH_ARGS
        )
        try:
            storage_state = session_manager.load_session(source_id)
            if source.get("requires_login") and storage_state is None:
                logger.warning(
                    "로그인 필요 대상인데 저장된 세션이 없습니다. "
                    "VNC로 먼저 로그인하고 session_manager.save_session()으로 저장하세요."
                )
            context = browser.new_context(storage_state=storage_state)
            page = context.new_page()
            results = run_pipeline(page, source)
        finally:
            browser.close()

    out_path = report_generator.write_report(source, results, config.OUTPUT_DIR)
    logger.info("결과 저장됨: %s", out_path)
    print(out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
