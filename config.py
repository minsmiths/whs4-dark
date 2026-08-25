"""프로젝트 설정값.

CLAUDE.md §4.2 브라우저·네트워크 보안 규칙에 대응하는 값들을 여기에 모은다.
매직 넘버를 코드에 흩뿌리지 않는다 — 값을 바꿀 땐 이 파일만 수정한다.
"""

from __future__ import annotations

import os

# --- Tor ---
TOR_SOCKS_PROXY = os.environ.get("TOR_SOCKS_PROXY", "socks5://127.0.0.1:9050")

# --- 타임아웃 / 지연 ---
PAGE_LOAD_TIMEOUT_MS = 60_000  # §M2 availability: 타임아웃 시 "상태: 미확인"
# Playwright page.goto()의 기본 wait_until="load"는 이미지/폰트/광고·트래커 스크립트 등
# 페이지의 모든 리소스가 다 끝나야 완료로 친다 — Tor + darkforums.ru처럼 jQuery/커스텀 CSS가
# 많이 걸린 사이트에서는 정작 본문 DOM은 이미 다 그려졌는데도 이 기준 때문에
# PAGE_LOAD_TIMEOUT_MS 안에 안 끝나 "상태: 못 봄(타임아웃)"으로 잘못 기록되는 실제 사례가
# 있었다(2026-08-23 첫 실크롤). selector 기반 수집은 DOM만 있으면 되므로 더 이르게(그리고
# 더 안정적으로) 끝나는 "domcontentloaded"를 쓴다.
PAGE_WAIT_UNTIL = "domcontentloaded"
# 2026-08-24: 그래도 30초로는 부족한 사례가 나왔다 — darkforums 실크롤에서 page.goto()가
# 30초 만에 타임아웃됐는데, 그 시점 저장된 스냅샷을 보니 <head>만 받고 <body>가 아예
# 없었다(Tor 회선이 느려 응답 스트림이 중간에 끊긴 상태). domcontentloaded는 만족했어야
# 할 상황인데도 안 끝났다는 건 응답 자체가 그만큼 느렸다는 뜻 — 60초로 올린다. 이 값이
# 부족하면 LOGIN_PAGE_LOAD_TIMEOUT_MS(90초)에 맞춰 더 올리는 것도 고려.
# 부작용: availability가 진짜로 실패했을 때(사이트 다운 등) "못 봄" 판정까지 걸리는 시간도
# 그만큼 늘어난다 — 무인 크롤링이라 감수할 만한 트레이드오프로 판단.
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
# 사이트 전체 헤드라인 순회(content_sample.crawl_site) 중단 시 체크포인트 저장 위치.
# sessions/ 와 같은 named volume(darkweb-sessions)에 두면 컨테이너 재실행 사이에도 남는다.
CHECKPOINT_DIR = os.environ.get("CHECKPOINT_DIR", SESSIONS_DIR)

# --- 사이트 전체 헤드라인 순회 (content_sample.crawl_site, 요구사항 5 확장) ---
# 홈페이지에서 발견한 모든 카테고리(하위 서브포럼 포함)를 재귀적으로 다 돈다. 단, 게시글은
# 헤드라인(제목/작성자/날짜)만 수집하고 본문(개별 게시글 페이지)에는 들어가지 않는다.
# 카테고리 하나당 페이지네이션은 최대 이 값까지만 — 전체 아님을 리포트에 명시한다.
SITE_MAP_MAX_PAGES_PER_CATEGORY = 5

# --- 브라우저 launch 인자 ---
# 주의: --no-sandbox, --disable-setuid-sandbox 는 절대 추가하지 않는다 (CLAUDE.md §4.2-1).
# CI의 security.yml 이 이 파일을 포함한 전체 코드에서 해당 문자열을 grep 하여 검증한다.
BROWSER_LAUNCH_ARGS: list[str] = []
