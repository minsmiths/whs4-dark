#!/usr/bin/env python3
"""VNC로 사람이 직접 로그인해 세션을 저장하는 1회성 스크립트 (로드맵 M1).

CLAUDE.md §3-3, §4.2-2: 크롤러는 자동 로그인·자동 가입을 하지 않는다. 사람이 리서치 계정으로
VNC 화면을 보며 직접 로그인하고, 이 스크립트는 그 결과(storage_state)만 저장한다.
investigate.py(자동 크롤링)와는 별개의 진입점이며, 평소에는 실행하지 않는다 — 세션이 없거나
만료됐을 때만 담당자가 VNC로 접속한 상태에서 실행한다.

사용법 (컨테이너 안, VNC 뷰어로 화면을 보면서):
    python login_session.py <whitelist.yaml 의 name 또는 url> [--login-url URL]

Docker에서는 기본 CMD(자동 크롤링)와 별도로 이 스크립트용 진입점을 명시적으로 호출한다
(예: `docker run ... <image> ./docker/login.sh example-forum`).
"""

from __future__ import annotations

import argparse
import logging
import sys

import config
import investigate
import session_manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("login_session")


def find_source_by_name_or_url(identifier: str) -> dict | None:
    """whitelist.yaml에서 name 또는 url이 identifier와 일치하는 항목을 찾는다.

    investigate.find_approved_source()는 (url, source_type) 쌍으로만 찾으므로, 로그인 스크립트는
    이름만으로도 찾을 수 있도록 별도 조회 함수를 둔다.
    """
    for entry in investigate.load_whitelist():
        if entry.get("url") == identifier or entry.get("name") == identifier:
            return entry
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="whitelist.yaml에 등록된 name 또는 url")
    parser.add_argument(
        "--login-url",
        dest="login_url",
        default=None,
        help="로그인 페이지 URL. 생략하면 대상의 url(홈페이지)로 이동한다.",
    )
    args = parser.parse_args(argv)

    source = find_source_by_name_or_url(args.source)
    if source is None:
        logger.error("화이트리스트에 없는 대상입니다: %s (whitelist.yaml 확인)", args.source)
        return 1

    source_id = source.get("name") or source["url"]
    target_url = args.login_url or source["url"]

    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        # BROWSER_LAUNCH_ARGS(config.py)에 샌드박스 비활성화 플래그를 절대 추가하지 않는다(§4.2-1).
        browser = p.chromium.launch(
            headless=False,  # VNC로 사람이 직접 봐야 하므로 headed로 띄운다.
            proxy={"server": config.TOR_SOCKS_PROXY},
            args=config.BROWSER_LAUNCH_ARGS,
        )
        try:
            context = browser.new_context()
            page = context.new_page()
            try:
                page.goto(target_url, timeout=config.LOGIN_PAGE_LOAD_TIMEOUT_MS)
            except PlaywrightError:
                # .onion 히든서비스는 회선 구성이 느려 첫 시도가 자주 타임아웃된다. 여기서
                # 죽지 않는다 — VNC 화면은 계속 떠 있으니 사람이 직접 새로고침/재시도하면 된다.
                logger.warning(
                    "%s 접속이 시간 안에 끝나지 않았습니다. VNC 화면에서 직접 새로고침하거나 "
                    "재시도해보세요 (.onion 대상은 흔한 일입니다). 준비되면 아래에서 Enter.",
                    target_url,
                )

            input(
                f"[{source_id}] VNC 화면에서 로그인을 완료한 뒤, 이 터미널에서 Enter를 누르세요..."
            )

            session_manager.save_session(context, source_id)
        finally:
            browser.close()

    logger.info(
        "완료: sessions/%s.json 에 저장됨. investigate.py 실행 시 자동으로 재사용됩니다.", source_id
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
