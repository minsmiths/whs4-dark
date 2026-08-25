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
}


def get_profile(source: dict[str, Any]) -> dict[str, str]:
    """source(whitelist.yaml 항목)의 platform 필드로 프로파일을 찾는다. 없으면 빈 dict."""
    platform = source.get("platform")
    if not platform:
        return {}
    return PROFILES.get(platform, {})
