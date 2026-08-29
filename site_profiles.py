"""사이트별(오픈소스 포럼 플랫폼별) 선택자 프로파일.

collectors/*.py 는 기본적으로 "흔한 포럼 구조"를 가정한 범용 추측 선택자를 쓴다. 실제
대상 마크업을 확인해서 정확한 값을 알아내면, 매번 collectors/*.py 코드를 직접 고치는
대신 여기에 프로파일로 등록해두고 whitelist.yaml의 `platform` 필드로 지정한다.

CLAUDE.md §3-8: 이 프로파일의 값은 사람이 실제 대상 마크업(snapshot.py가 저장한 파일 등)을
직접 확인해서 채운다 — AI가 실제 대상 사이트에 접속해서 알아낸 값이 아니다.

프로파일이 없거나(platform 필드 없음) 등록 안 된 platform 이면, 각 collector는 기존
범용 선택자를 그대로 쓴다 — 프로파일을 안 쓰던 기존 동작과 100% 호환된다.
"""

from __future__ import annotations

from typing import Any

# 각 최상위 키는 whitelist.yaml의 platform 값과 대응한다. 값을 채우지 않은 선택자 키는
# 생략해도 된다 — 생략된 키는 collector의 기존 기본값으로 자동 대체된다.
#
# 프로파일 키에 담기는 값들 (전부 선택):
#   nav_link_selector               structure.py: 진짜 카테고리 목록
#   rules_link_selector             structure.py: 규칙/FAQ 링크를 찾을 위치(카테고리 목록과
#                                    다른 곳에 있을 수 있음 — 없으면 nav_link_selector와 동일)
#   rules_content_selector          structure.py: 규칙 페이지 "본문"만(사이드바/헤더 제외)
#   post_row_selector                content_sample.py / stats.py: 게시글 행 1개
#   post_title_selector / post_author_selector / post_date_selector
#   stats_area_selector              stats.py: 통계 영역
#   pagination_last_selector         stats.py: 페이지네이션 마지막 페이지 링크
#   pagination_next_selector         content_sample.py crawl_site(): "다음 페이지" 링크
#                                    (카테고리당 최대 config.SITE_MAP_MAX_PAGES_PER_CATEGORY까지)
#   latest_post_timestamp_selector   stats.py: 목록 최상단 게시글 시각
PROFILES: dict[str, dict[str, str]] = {
    # 2026-08-27 저장된 cracked.st 홈 스냅샷에서 확인한 MyBB 계열 구조.
    # 범용 selector는 헤더 바로가기 6개만 잡았지만 실제 게시판 표에는
    # a.largetext 형태의 포럼 링크가 53개 있었다.
    "cracked": {
        "nav_link_selector": "table.index_table a.largetext, table.index_table .forum-subforums a",
        "rules_link_selector": "a[href*='misc.php?action=help'], a[href*='misc?action=help']",
        "rules_content_selector": "#content",
        # 첫 목록 요청은 DDoS-Guard 페이지로 바뀌어 직접 검증하지 못했다.
        # 저장된 홈의 MyBB 마크업과 기존 검증 프로필을 근거로 표준 목록 구조를 쓴다.
        "post_row_selector": "tr.inline_row",
        "post_title_selector": '[id^="tid_"] a',
        "post_author_selector": ".author",
        "post_date_selector": ".thread_start_datetime, .forum-display__thread-date",
    },
    # 2026-08-19, 실제 크롤링에서 저장된 snapshot(tmp_snapshots/darkforums/...)을 사람이
    # 직접 확인해서 채운 값. Knox 테마는 MyBB 기본 템플릿과 class 이름이 다르므로 범용
    # "mybb" 프로파일이 아니라 이 대상 전용으로 등록한다.
    "darkforums": {
        # 사이트 상단 사이드 메뉴(.sidenav__menu)는 계정 메뉴랑 섞여 있어서 대신
        # 진짜 서브포럼 목록 테이블의 링크만 쓴다 — 계정 메뉴가 원천적으로 안 섞인다.
        "nav_link_selector": ".forums__forum-name",
        # "Rules & Policies" 링크는 카테고리 목록이 아니라 상단 사이드 메뉴 쪽에 있었다.
        "rules_link_selector": ".sidenav__menu a",
        # <main id="content"> 가 본문 wrapper — 상단 사이드바/계정 메뉴는 제외된다
        # (페이지 하단 검색창/푸터 일부는 포함될 수 있음, RULES_TEXT_MAX_CHARS로 상한만 둠).
        "rules_content_selector": "#content",
        # 홈페이지 하단의 사이트 전체 통계 블록("Total Posts/Threads/Members/...").
        # 서브포럼별 통계(.forums__stats)는 사이트 규모를 대표하지 않아서 안 쓴다.
        "stats_area_selector": ".index-stats__forum",
        # 각 서브포럼 행의 "최근 게시글" 칸. 화면엔 "2 hours ago"(상대 시간)로 보이지만
        # title 속성에 절대 시각("19-08-26, 08:29 PM")이 들어있다 — stats.py가 그 순서로 본다.
        "latest_post_timestamp_selector": ".forums__last-post span[title]",
        # 2026-08-23, crawl_site()가 처음 방문한 카테고리(Announcements) 스냅샷
        # (snapshots/darkforums/.../sitemap_first_category.html)을 사람이 직접 확인해서 채움.
        # 게시글 행 하나 = <tr class="inline_row">...</tr> (MyBB 표준 클래스, 체크박스로 선택
        # 가능한 스레드 행에 항상 붙는다 — 서브포럼 안내/구분선 <tr>과는 구분됨).
        "post_row_selector": "tr.inline_row",
        # 제목 <span id="tid_123" class=" subject_old">(또는 subject_new, 안 읽음 여부에 따라
        # 클래스가 갈림) 안의 <a>. id 접두어(tid_ = thread id)로 잡으면 읽음 상태 클래스 차이에
        # 상관없이 항상 매칭된다.
        "post_title_selector": '[id^="tid_"] a',
        # 범용 기본값(".author")과 우연히 같다 — 명시적으로 남겨둔다(다른 스킨으로 바뀌어도
        # 여기부터 고치면 되도록).
        "post_author_selector": ".author",
        # datetime 속성이 없다(darkforums Knox 테마) — collect_posts()가 title 속성 → 화면 텍스트
        # 순으로 폴백한다. 이 칸은 절대 시각 텍스트라 폴백해도 §7.1(상대 시간 금지)에 안 걸린다.
        "post_date_selector": ".forum-display__thread-date",
        # pagination_next_selector는 일부러 안 채운다 — darkforums(Knox 테마)는 "다음" 화살표가
        # 없고 페이지 번호(1 2 3 ...)만 나열돼 있어서, content_sample.py의 범용 폴백
        # (_find_next_page_href, 2026-08-24 도입)이 알아서 처리한다. 이 프로젝트는 darkforums
        # 전용 도구가 아니라서 이런 selector는 정말 필요할 때만(범용 폴백도 안 맞을 때) 채운다.
    },
    # 2026-08-26, 실제 첫 크롤링에서 저장된 홈페이지 스냅샷(tmp_snapshots/spear.cx/
    # 20260826T040916/structure_home_after.html)을 사람이 직접 확인해서 채운 값. MyBB 기반이지만
    # darkforums(Knox)와는 다른 테마(theme15)라 class 이름이 전혀 다르다.
    "spear": {
        # 진짜 서브포럼 링크는 <div class="forum" id="forum-13"><div class="name"><a href="Forum-...">
        # 구조 안에만 있다. 범용 기본값("nav a, .forumbit a")은 상단 헤더 메뉴(#header-menu,
        # Home/Leaks/Upgrade/Search/Extras 드롭다운)와 하단 footer-nav 링크까지 다 걸려서
        # discover_categories()가 진짜 카테고리를 하나도 못 걸렀다(2026-08-26 첫 실크롤에서
        # "카테고리도 sample_list_url도 없음"으로 확인) — 이 selector로 그 문제를 없앤다.
        "nav_link_selector": ".forum .name a",
        # "Rules" 링크는 카테고리 목록이 아니라 footer 하단 "Help" 메뉴에 있다
        # (<a href="misc?action=help&hid=10" title="Rules">). 상단 헤더의 Extras 드롭다운에도
        # 같은 링크가 있지만 footer-nav 쪽이 더 단순해서 이걸 쓴다.
        "rules_link_selector": ".footer-nav a",
        # MyBB 표준 본문 wrapper. darkforums와 마찬가지로 헤더/사이드바 노이즈를 제외한다.
        # 실제 규칙 페이지(misc?action=help&hid=10) 스냅샷으로 아직 검증 전 — 다음 실크롤에서
        # structure_rules_page.html이 저장되면 재확인 필요.
        "rules_content_selector": "#content",
        # 주의: 범용 기본값(".forum-stats, #stats")은 사이트 전체 통계가 아니라 맨 위 서브포럼
        # (Announcements)의 "Posts: 15" 칸에 우연히 먼저 매칭돼서 "규모: 15"로 잘못 나왔다
        # (stats.py가 stats_locator.first를 쓰기 때문). 진짜 사이트 전체 통계
        # (Threads/Posts/Members/Newest Member)는 페이지 맨 아래 "Board Statistics" 블록에 있다.
        "stats_area_selector": ".board-stats",
        # 서브포럼별 "최근 게시글" 칸(.latestpost)은 행마다 있어서 순서가 "최근순"이 아니다
        # (Announcements가 맨 위지만 실제로 제일 최근 활동한 포럼이 아닐 수 있음). 대신 사이드바의
        # "Latest Posts" 표(사이트 전체 게시글을 실제 최근순으로 정렬해서 보여줌)의 첫 행이
        # 진짜 최신 게시글이다. title 속성에 절대 시각("08-26-2026, 04:06 AM")이 들어있다
        # (화면엔 "2 minutes ago"로 보임 — CLAUDE.md §7.1 상대시간 금지라 title을 쓴다).
        "latest_post_timestamp_selector": ".sidebar-column .latestpost span[title]",
        # 2026-08-26, nav_link_selector 고친 뒤 실제로 서브포럼까지 들어간 크롤에서 저장된
        # 첫 카테고리 스냅샷(snapshots/spear.cx/.../sitemap_first_category.html, Announcements
        # 게시판)을 사람이 직접 확인해서 채운 값. darkforums와 똑같은 MyBB 표준 스레드 목록
        # 마크업이라(테마만 다름) selector도 거의 같다.
        "post_row_selector": "tr.inline_row",
        # 제목은 <span id="tid_568" class=" subject_new"><a class="thread-title tid-568">...</a></span>
        # 구조 — darkforums와 동일하게 id 접두어(tid_)로 잡으면 읽음 상태 클래스 차이에 안 흔들린다.
        "post_title_selector": '[id^="tid_"] a',
        # 범용 기본값(".author")과 우연히 같다 — darkforums 프로파일과 같은 이유로 명시적으로
        # 남겨둔다(<span class="author smalltext"><a>...</a></span> 구조 확인함).
        "post_author_selector": ".author",
        # 스레드 "작성일"은 .thread_start_datetime에 절대 시각 텍스트로 그대로 있다
        # (예: "03-18-2026, 04:08 AM") — datetime/title 속성 없이도 이미 절대 표기라 §7.1
        # 문제 없음. (참고: .lastpost는 "최근 답글" 시각이라 다른 값 — 작성일이 아니라서 안 씀.)
        "post_date_selector": ".thread_start_datetime",
        # pagination_next_selector는 안 채운다 — Announcements(5개 스레드)엔 페이지네이션
        # 위젯 자체가 없어서 이 스냅샷만으론 확인 불가. 게시글 많은 보드(Databases 등)에서
        # content_sample.py의 범용 폴백(_find_next_page_href)이 못 찾으면 그때 다시 본다.
    },

    # 2026-08-26, VNC 로그인 성공 후 첫 자동 크롤에서 저장된 홈페이지 스냅샷
    # (snapshots/pwnforums/.../structure_home_after.html)을 사람이 직접 확인해서 채운 값.
    # darkforums와 class 이름이 글자 그대로 동일한 MyBB 테마(다른 포럼 소프트웨어가 아니라
    # 같은 상용 테마를 공유하는 것으로 보임) — 그래서 대부분 darkforums 값을 그대로 재사용한다.
    "pwnforums": {
        # 범용 기본값으로는 홈페이지 사이드 메뉴(.sidenav__menu — Databases/Upgrades/Search/
        # Escrow/Wall of Shame 등 사이트 전체 링크 + 계정 메뉴 seucBluechessCake22/Threads/
        # Posts 같은 개인 통계까지 섞여서 잡혔다(2026-08-26 첫 크롤 확인). 게다가 그 중
        # "Databases" 링크는 실제 서브포럼이 아니라 공지 게시글(Announcement-Database-Index)
        # 하나로 연결돼 있어서, crawl_site()가 그걸 "첫 카테고리"로 착각해 방문하는 오류까지
        # 있었다. 진짜 서브포럼 목록은 darkforums와 동일하게 .forums__forum-name 이다
        # (Announcements/Introductions/World News/Ransomware Section Rules 등 확인함).
        "nav_link_selector": ".forums__forum-name",
        # "Rules & Policies" 링크도 darkforums와 동일하게 사이드 메뉴 쪽에 있다.
        "rules_link_selector": ".sidenav__menu a",
        "rules_content_selector": "#content",  # <main id="content"> 확인함(darkforums와 동일).
        # 사이트 전체 통계 블록도 darkforums와 클래스가 같다: "Total 857,461 posts in
        # 82,570 threads." / "364,982 Total Members" 등.
        "stats_area_selector": ".index-stats__forum",
        # darkforums와 달리 서브포럼 목록의 "최근 게시글" 칸(.forums__last-post)은 행마다
        # span[title]이 있는 게 아니라(첫 행은 그냥 절대 시각 텍스트만 있었음, 2026-08-26
        # 확인) 순서도 사이트 전체 최신순이 아니다. 대신 홈페이지에 spear.cx와 비슷한
        # "Latest Posts" 위젯이 따로 있고(.latestposts .lp-item), 이게 사이트 전체를
        # 진짜 최신순으로 보여준다 — 그 첫 항목의 절대 시각(title 속성)을 쓴다.
        "latest_post_timestamp_selector": ".latestposts .lp-meta span[title]",
        # 2026-08-26, nav_link_selector 고친 뒤 2차 크롤에서 실제 서브포럼(Announcements)
        # 스레드 목록 스냅샷(snapshots/pwnforums/.../sitemap_first_category.html)을 사람이
        # 직접 확인해서 채운 값. 예상대로 darkforums와 마크업이 완전히 동일하다(같은 테마).
        "post_row_selector": "tr.inline_row",
        "post_title_selector": '[id^="tid_"] a',
        "post_author_selector": ".author",
        "post_date_selector": ".forum-display__thread-date",
        # pagination_next_selector는 darkforums와 동일한 이유로 안 채운다 — 이 스냅샷에도
        # 페이지 번호(1 2 3 ... 16)만 있고 "다음" 화살표가 없어서, content_sample.py의
        # 범용 폴백(_find_next_page_href)이 처리한다.
    },
}


def get_profile(source: dict[str, Any]) -> dict[str, str]:
    """source(whitelist.yaml 항목)의 platform 필드로 프로파일을 찾는다. 없으면 빈 dict."""
    platform = source.get("platform")
    if not platform:
        return {}
    return PROFILES.get(platform, {})
