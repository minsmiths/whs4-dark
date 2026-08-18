"""프로젝트 설정값.

CLAUDE.md §4.2 브라우저·네트워크 보안 규칙에 대응하는 값들을 여기에 모은다.
매직 넘버를 코드에 흩뿌리지 않는다 — 값을 바꿀 땐 이 파일만 수정한다.
"""

from __future__ import annotations

import os

# --- Tor ---
TOR_SOCKS_PROXY = os.environ.get("TOR_SOCKS_PROXY", "socks5://127.0.0.1:9050")

# --- 타임아웃 / 지연 ---
PAGE_LOAD_TIMEOUT_MS = 30_000  # §M2 availability: 타임아웃 시 "상태: 미확인"
REQUEST_DELAY_MIN_SEC = 3.0  # CLAUDE.md §4.2-6: 요청 간 3~5초 랜덤 지연
REQUEST_DELAY_MAX_SEC = 5.0

# --- 콘텐츠 표본 ---
CONTENT_SAMPLE_SIZE = 50  # 요구사항 5: 표본 기본 50건
USER_ACTIVITY_TOP_N = 10  # 요구사항 7: 상위 10명 핸들

# --- Cloudflare 등 챌린지 감지 키워드 ---
CHALLENGE_TITLE_KEYWORDS = ("Just a moment", "Checking your browser")

# --- 압수배너 / 도메인 파킹 감지 키워드 (M2 availability) ---
SEIZED_BANNER_KEYWORDS = (
    "seized",
    "domain has been seized",
    "law enforcement",
)
DOMAIN_PARKING_KEYWORDS = (
    "domain is for sale",
    "buy this domain",
)

# --- 경로 ---
WHITELIST_PATH = os.environ.get("WHITELIST_PATH", "whitelist.yaml")
SESSIONS_DIR = os.environ.get("SESSIONS_DIR", "sessions")
SNAPSHOTS_DIR = os.environ.get("SNAPSHOTS_DIR", "snapshots")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output")
RUN_LOG_PATH = os.environ.get("RUN_LOG_PATH", "run_log.json")
KOREA_KEYWORDS_PATH = os.environ.get("KOREA_KEYWORDS_PATH", "keywords/korea_keywords.txt")

# --- 브라우저 launch 인자 ---
# 주의: --no-sandbox, --disable-setuid-sandbox 는 절대 추가하지 않는다 (CLAUDE.md §4.2-1).
# CI의 security.yml 이 이 파일을 포함한 전체 코드에서 해당 문자열을 grep 하여 검증한다.
BROWSER_LAUNCH_ARGS: list[str] = []
