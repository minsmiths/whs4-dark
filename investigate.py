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
from tqdm import tqdm

import challenge
import config
import profile_report_generator
import session_manager
import snapshot
import structure_diagnostics
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


def run_pipeline(
    page, source: dict[str, Any], *, resume: bool = False, pages_per_category: int | None = None
) -> dict[str, Any]:
    """Collector ①~⑦을 순서대로 호출하고 report_generator 가 쓸 dict로 취합한다.

    resume=True면 content_sample.crawl_site()가 이전 체크포인트(세션 만료/챌린지로 중단된
    사이트 전체 헤드라인 순회)부터 이어서 진행한다. crawl_site()가 다시 막히면
    content_sample.CrawlInterrupted가 그대로 위로 전파된다 — 호출부(main())가 처리한다.
    """
    results: dict[str, Any] = {}
    source_id = source.get("name") or source.get("url", "unknown")

    # --resume 인데 이전 사이트 순회 체크포인트가 남아 있으면, 이번 실행에서 홈페이지가
    # 챌린지로 막혀 카테고리 시드를 못 뽑아도 crawl_site()를 체크포인트 큐로 이어서 돈다.
    # (아래 stats/content_sample 분기에서 사용.)
    resume_checkpoint_exists = resume and content_sample.has_checkpoint(source_id)

    # Collector ①~⑦ 진행 상황을 눈으로 볼 수 있게 진행바를 띄운다(§ 사용자 요청,
    # 2026-08-24). .onion은 회선이 느려 한 단계가 몇 분씩 걸릴 수 있어서, "지금 죽은 건지
    # 그냥 느린 건지" 구분이 잘 안 되는 문제가 있었다 — Docker에서 TTY 없이 돌 때도 tqdm은
    # 알아서 매 update마다 한 줄씩 찍는 방식으로 대체 출력한다.
    with tqdm(total=7, desc="investigate", unit="step") as pbar:
        pbar.set_description("① availability")
        results.update(availability.run(page, source))
        snapshot.save_snapshot(page, source_id, "availability_home")
        pbar.update(1)

        # 홈페이지 로딩 시점에도 챌린지를 상시로 확인한다(§4.2-6). 여기서 잡히면 이후 단계는
        # 어차피 빈손이고, --resume 재개 경로(content_sample.crawl_site 체크포인트)에 진입도
        # 못한 채 빈 리포트로 기존 진행분을 덮어쓰게 된다(2026-08-27 cracked.st). 자동 우회는
        # 하지 않고(§3-3) 즉시 중단해 사람이 VNC로 풀고 --resume 하도록 넘긴다.
        home_challenge = challenge.detect(page)
        if home_challenge:
            raise content_sample.CrawlInterrupted(f"홈페이지 챌린지 감지: {home_challenge}")
        home_state = results.get("상태")
        home_blocked = isinstance(home_state, dict) and home_state.get("state") == "BLOCKED"
        if home_blocked and resume_checkpoint_exists:
            raise content_sample.CrawlInterrupted(
                f"홈페이지 접속 실패({home_state.get('reason')}) — 저장된 체크포인트를 빈 "
                "결과로 덮어쓰지 않도록 중단합니다. VNC로 접속/차단을 해결한 뒤 --resume 하세요."
            )

        if source.get("requires_login"):
            selector = source.get("logged_in_selector")
            if not selector:
                logger.info(
                    "logged_in_selector 미설정 — 세션 유효성 자동 확인을 건너뜁니다"
                    "(whitelist.yaml에 추가 가능)."
                )
            elif session_manager.is_session_valid(page, selector):
                logger.info("세션 유효함 확인됨 (logged_in_selector 매칭)")
            else:
                # M1 완료 기준 (c): 자동 재로그인 없이 만료만 기록하고 파이프라인은 계속 진행한다.
                session_manager.record_session_expired(source_id)

        pbar.set_description("② structure")
        time.sleep(config.REQUEST_DELAY_MIN_SEC)
        results.update(structure.run(page, source))
        # structure.run()은 규칙 페이지를 봤다가 원래 페이지로 복귀한다 — 복귀 후 상태를 스냅샷.
        snapshot.save_snapshot(page, source_id, "structure_home_after")
        structure_diagnostics.save(page, source_id, "structure_home_diagnostic")
        pbar.update(1)

        # stats/content_sample은 "게시글이 실제로 나열된 목록 페이지"를 전제로 한다.
        #
        # sample_list_url이 지정돼 있으면 사람이 직접 골라준 페이지를 우선한다(기존 동작 그대로).
        # 없으면, structure()가 홈페이지에서 찾은 카테고리(하위 서브포럼 포함)가 있는 경우
        # content_sample.crawl_site()로 사이트 전체를 재귀적으로 돌며 게시글 헤드라인만 모은다
        # (개별 게시글 본문에는 들어가지 않음). 둘 다 없으면 기존처럼 현재 페이지에서 시도한다.
        sample_list_url = source.get("sample_list_url")
        category_seed = results.get("_사이트_카테고리_시드", [])

        if sample_list_url:
            try:
                page.goto(
                    sample_list_url, timeout=config.PAGE_LOAD_TIMEOUT_MS, wait_until=config.PAGE_WAIT_UNTIL
                )
                snapshot.save_snapshot(page, source_id, "sample_list_page")
            except Exception:  # noqa: BLE001 - 이동 실패해도 stats/content_sample이 BLOCKED로 처리
                logger.warning("sample_list_url 접속 실패: %s", sample_list_url)

            pbar.set_description("③ stats")
            time.sleep(config.REQUEST_DELAY_MIN_SEC)
            results.update(stats.run(page, source))
            pbar.update(1)

            pbar.set_description("④ content_sample")
            time.sleep(config.REQUEST_DELAY_MIN_SEC)
            results.update(content_sample.run(page, source))
            pbar.update(1)
        elif category_seed or resume_checkpoint_exists:
            pbar.set_description("③ stats (홈페이지 기준)")
            time.sleep(config.REQUEST_DELAY_MIN_SEC)
            results.update(stats.run(page, source))
            pbar.update(1)

            # resume_checkpoint_exists 로 여기 들어온 경우 category_seed가 비어 있을 수 있다 —
            # crawl_site()가 resume=True 면 체크포인트 큐를 우선하므로 그대로 넘겨도 된다.
            pbar.set_description("④ content_sample (사이트 전체 카테고리 재귀 순회)")
            results.update(
                content_sample.crawl_site(
                    page,
                    source,
                    category_seed,
                    resume=resume,
                    pages_per_category=pages_per_category,
                )
            )
            pbar.update(1)
        else:
            logger.info(
                "카테고리도 sample_list_url도 없음 — 현재 페이지(보통 홈페이지)에서 표본을 "
                "시도합니다. 게시글 목록이 없는 페이지면 규모/표본 관련 필드가 BLOCKED로 나올 수 있습니다."
            )
            pbar.set_description("③ stats")
            time.sleep(config.REQUEST_DELAY_MIN_SEC)
            results.update(stats.run(page, source))
            pbar.update(1)

            pbar.set_description("④ content_sample")
            time.sleep(config.REQUEST_DELAY_MIN_SEC)
            results.update(content_sample.run(page, source))
            pbar.update(1)
            results["_crawl_failures"] = [
                {
                    "category": "사이트 구조",
                    "page": 1,
                    "url": page.url,
                    "reason": "카테고리 selector 자동 판별 실패",
                }
            ]
            results["_crawl_completion"] = {
                "complete": False,
                "categories": 0,
                "pages": 0,
                "posts": len(results.get("_표본_게시글", [])),
                "failures": 1,
                "pages_per_category": pages_per_category
                or config.SITE_MAP_MAX_PAGES_PER_CATEGORY,
            }

        pbar.set_description("⑤ cross_reference")
        # 이전 단계에서 모은 텍스트를 재사용한다 (새 페이지 요청을 만들지 않음).
        collected_texts = {
            "표본 게시글 제목": " ".join(p.get("title", "") for p in results.get("_표본_게시글", []))
        }
        rules_text = results.get("_들어가는_법_구조", {})
        if "value" in rules_text:
            collected_texts["규칙/FAQ 페이지 원문"] = rules_text["value"]
        results.update(cross_reference.run(collected_texts, source))
        pbar.update(1)

        pbar.set_description("⑥ access_probe")
        time.sleep(config.REQUEST_DELAY_MIN_SEC)
        results.update(access_probe.run(page, source))
        pbar.update(1)

        pbar.set_description("⑦ user_activity")
        results.update(user_activity.run(results.get("_표본_게시글", []), source))
        pbar.update(1)

    # "들어가는 법"(23칸 스키마 #19, AUTO-append, INTERNAL_ONLY)은 structure(규칙 페이지)와
    # access_probe(가입 폼) 두 Collector가 채운다. 같은 dict 키에 update()로 이어붙이면
    # 한쪽이 다른 쪽을 덮어쓰므로, 여기서 [(라벨, tri-state dict), ...] 리스트로 합친다.
    entering_entries: list[tuple[str, dict[str, Any]]] = []
    if "_들어가는_법_구조" in results:
        entering_entries.append(("규칙/FAQ 페이지 원문", results["_들어가는_법_구조"]))
    if "_들어가는_법_가입폼" in results:
        entering_entries.append(("가입 페이지 입력 필드", results["_들어가는_법_가입폼"]))
    results["들어가는 법"] = entering_entries

    # profile_report_generator.py(사용자 지정 템플릿, 2026-08-25) 전용 후보 필드. category 필드가
    # 있어야 의미가 있는 계산이라(_사이트맵_방문_URL 재귀 순회 경로에서만 채워짐) sample_list_url
    # 단일 페이지 경로에서는 그냥 CONFIRMED_ABSENT로 나온다 — 정상 동작이다.
    posts_full = results.get("_표본_게시글", [])
    results["_운영자_후보"] = user_activity.find_operator_candidates(posts_full)
    results["_개인정보_유출_후보"] = content_sample.find_notable_leak_candidates(posts_full)
    results["_한국_관련_유출_최근"] = content_sample.find_korea_specific_leaks(posts_full)

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
    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "이전 실행이 세션 만료/챌린지 감지로 사이트 전체 헤드라인 순회 도중 중단됐을 때, "
            "체크포인트부터 이어서 진행합니다. 사람이 VNC로 재로그인/챌린지를 먼저 해결한 "
            "뒤에 쓰세요 — 자동 재로그인은 하지 않습니다(CLAUDE.md §3-3)."
        ),
    )
    parser.add_argument(
        "--pages-per-category",
        type=int,
        default=config.SITE_MAP_MAX_PAGES_PER_CATEGORY,
        help="각 게시판에서 수집할 목록 페이지 수(기본값: 5)",
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
        browser_type = getattr(p, config.BROWSER_ENGINE)
        browser = browser_type.launch(
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
            try:
                results = run_pipeline(
                    page,
                    source,
                    resume=args.resume,
                    pages_per_category=max(1, args.pages_per_category),
                )
            except content_sample.CrawlInterrupted as exc:
                # CLAUDE.md §3-3·§4.2-6: 자동 재로그인/자동 챌린지 우회는 하지 않는다.
                # 사이트 순회 중 중단이면 체크포인트가 crawl_site() 안에서 저장돼 있고, 홈페이지
                # 챌린지로 중단이면 이전 체크포인트가 그대로 보존된다 — 여기선 안내만 하고 멈춘다.
                logger.error(
                    "크롤링이 중단됐습니다 (%s). 결과가 불완전하므로 리포트를 만들지 않습니다. "
                    "VNC로 재로그인/챌린지 해결 후 --resume 옵션으로 이어서 실행하세요.",
                    exc.reason,
                )
                return 2
        finally:
            browser.close()

    # 2026-08-25(사용자 확인): 노션 23칸 공식 스키마(report_generator.py) 대신 사용자 지정
    # 프로파일 템플릿(profile_report_generator.py)으로 전면 교체됨. CLAUDE.md §4.1은 그대로
    # 지킨다 — output/ 에 MD 파일 1개만 나간다.
    out_path = profile_report_generator.write_report(source, results, config.OUTPUT_DIR)
    logger.info("결과 저장됨: %s", out_path)
    print(out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
