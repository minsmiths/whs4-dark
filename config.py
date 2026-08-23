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
# login_session.py 전용. 사람이 VNC로 직접 지켜보며 기다리거나 재시도할 수 있는 상황이라,
# 무인 자동 크롤링(PAGE_LOAD_TIMEOUT_MS)보다 여유를 둔다 — .onion 히든서비스는 clearnet보다
# 회선 구성이 느려서 특히 필요하다.
LOGIN_PAGE_LOAD_TIMEOUT_MS = 90_000
REQUEST_DELAY_MIN_SEC = 3.0  # CLAUDE.md §4.2-6: 요청 간 3~5초 랜덤 지연
REQUEST_DELAY_MAX_SEC = 5.0

# --- 콘텐츠 표본 ---
CONTENT_SAMPLE_SIZE = 50  # 요구사항 5: 표본 기본 50건
USER_ACTIVITY_TOP_N = 10  # 요구사항 7: 상위 10명 핸들

# --- 규칙/FAQ 원문 인용 (M2 structure) ---
RULES_TEXT_MAX_CHARS = 4000  # 원문 그대로 인용하되 MD가 지나치게 커지지 않도록 상한선만 둔다.

# --- nav 카테고리에서 계정/유틸리티 메뉴 걸러내기 (M2 structure) ---
# 플랫폼(MyBB, XenForo, phpBB 등)에 상관없이 포럼 계정 메뉴에 흔히 쓰이는 문구들.
# 정확한 선택자를 모를 때도(site_profiles.py 프로파일 없이도) "어떤 곳인지"에 로그인/알림
# 관련 텍스트가 섞여 들어가는 걸 줄여주는 범용 휴리스틱이다 — 완벽하지 않으니 site_profiles.py
# 로 실제 선택자를 좁히는 게 더 정확하다.
NAV_ACCOUNT_MENU_KEYWORDS = (
    "sign out",
    "log out",
    "logout",
    "control panel",
    "mark all as read",
    "today's posts",
    "my account",
    "private message",
    "profile",
    "reputation",
    "notifications",
)

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
