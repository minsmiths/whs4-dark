"""④ 콘텐츠 표본 크롤. 요구사항 5 대응: 필터 기반 게시글 통계 (로드맵 M3).

이 통계는 사이트 전체가 아니라 수집한 표본 기준이다. MD 출력 시 반드시 표본 규모를
명시한다 (report_generator.py 가 처리). 표본은 두 가지 방식으로 모인다:

- `run()`: 현재 page 1개에서만 상위 N건(기본 50) — sample_list_url이 지정된 대상용.
- `crawl_site()`: 홈페이지에서 발견한 모든 카테고리(하위 서브포럼 포함)를 재귀적으로
  다 돌며 카테고리당 페이지네이션 최대 SITE_MAP_MAX_PAGES_PER_CATEGORY 페이지까지 헤드라인만
  모은다. 개별 게시글 본문 페이지에는 들어가지 않는다. 세션 만료/챌린지 감지 시 자동
  재로그인은 하지 않고(CLAUDE.md §3-3) CrawlInterrupted를 던진다 — 체크포인트를 남겨서
  사람이 VNC로 재로그인한 뒤 --resume 으로 이어서 진행할 수 있게 한다.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import random
import re
import time
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

from tqdm import tqdm

import challenge
import config
import site_profiles
import snapshot

try:
    from langdetect import DetectorFactory, LangDetectException, detect

    DetectorFactory.seed = 0  # 짧은 텍스트에서도 실행마다 같은 결과가 나오도록 고정
except ImportError:  # pragma: no cover - requirements.txt 에 있지만 방어적으로 처리
    detect = None
    LangDetectException = Exception  # type: ignore[assignment,misc]

if TYPE_CHECKING:
    from playwright.sync_api import Page

logger = logging.getLogger(__name__)

# CLAUDE.md §3-4: PII 원문은 저장하지 않는다 — 존재 여부와 유형만 기록한다.
# 아래 정규식은 표본 게시글 "제목"에만 적용한다(본문은 수집 대상이 아님, §5 표 참고).
# 매칭된 문자열 자체는 절대 결과 dict에 담지 않고, 유형 이름(이메일/전화번호)만 기록한다.
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"\b01[0-9]-?\d{3,4}-?\d{4}\b")

# TODO(M3): 실제 대상 사이트 마크업 확인 후 확정.
POST_ROW_SELECTOR = ".thread-list .thread"
POST_TITLE_SELECTOR = ".title"
POST_AUTHOR_SELECTOR = ".author"
POST_DATE_SELECTOR = "time"
# 이 프로젝트는 darkforums 한 곳만을 위한 도구가 아니다 — 승인 대상이 늘어날 때마다 매번
# site_profiles.py에 selector를 새로 등록해야만 페이지네이션이 동작하면 안 된다. 그래서
# 페이지네이션 "다음 페이지" 탐지는 두 단계로 한다:
#   1) 아래 범용 selector(또는 site_profiles.py의 pagination_next_selector 오버라이드) —
#      "다음"이라는 명시적 링크/화살표(rel=next, class=next 등)가 있는 사이트용.
#   2) 그런 링크가 전혀 없어도(2026-08-24 darkforums 실크롤에서 실제로 겪음 — "다음" 화살표
#      없이 페이지 번호(1 2 3 ...)만 나열돼 있었다) _find_next_page_href()가 pagination/pager
#      영역 안에서 "현재 페이지+1"과 텍스트가 정확히 일치하는 번호 링크를 찾는다. 포럼
#      소프트웨어가 뭐든(MyBB/XenForo/phpBB/vBulletin 등) 페이지 번호 링크 자체는 대체로
#      있다는 사실에 기댄, 사이트 프로파일 없이도 동작하는 범용 폴백이다.
PAGINATION_NEXT_SELECTOR = "a.next, a[rel='next'], .pagination .next a"
PAGINATION_AREA_LINK_SELECTOR = (
    "[class*='pagination' i] a, [class*='pager' i] a, [class*='pagenav' i] a, "
    "nav[aria-label*='age' i] a"
)


def _find_next_page_href(page: Page, next_selector: str, next_page_num: int) -> str:
    """"다음 페이지" 링크의 href를 찾는다. 못 찾으면 빈 문자열(그 카테고리는 여기서 멈춤).

    next_selector가 매칭되면 그대로 쓰고(명시적 "다음" 링크), 없으면 pagination 영역에서
    페이지 번호가 next_page_num과 정확히 같은 링크로 폴백한다(§ 위 PAGINATION_NEXT_SELECTOR
    주석 참고). 둘 다 없으면 실제로 마지막 페이지이거나, 사이트 마크업이 두 방식 모두와
    안 맞는 경우다 — 후자면 site_profiles.py에 pagination_next_selector를 등록해서 해결한다.
    """
    next_link = page.locator(next_selector)
    if next_link.count() > 0:
        href = next_link.first.get_attribute("href") or ""
        if href:
            return href

    numbered = page.locator(PAGINATION_AREA_LINK_SELECTOR).filter(
        has_text=re.compile(rf"^\s*{next_page_num}\s*$")
    )
    if numbered.count() > 0:
        return numbered.first.get_attribute("href") or ""
    return ""


class CrawlInterrupted(Exception):
    """crawl_site() 도중 세션 만료/챌린지가 감지돼 더 진행할 수 없다는 신호.

    CLAUDE.md §3-3·§4.2-6: 자동 재로그인·자동 챌린지 우회는 만들지 않는다. 이 예외가
    발생하면 investigate.py가 크롤링을 멈추고, 사람이 VNC로 재로그인/챌린지를 직접 해결한
    뒤 `--resume`으로 이어서 실행하라는 안내만 출력한다. 이미 모은 결과는 체크포인트 파일에
    저장돼 있어 처음부터 다시 돌 필요가 없다.
    """

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _load_keywords() -> list[str]:
    """keywords/korea_keywords.txt 를 읽어 키워드 목록만 반환한다.

    파일 맨 위 안내 주석(`#`로 시작하는 줄)은 키워드가 아니다 — 이 필터링이 없으면 그 중
    빈 주석 줄(`#`만 있는 줄)이 그대로 "키워드"로 취급돼, 제목에 `#` 문자만 있어도(예:
    "... #1", "#2 ...") 한국 관련 유출 후보로 잘못 집계되는 실사고가 있었다
    (2026-08-25, darkforums 실크롤 감사 중 발견 — 사이트 전체 후보 수가 109건이 아니라
    136건으로 27건 부풀려져 있었다).
    """
    path = Path(config.KOREA_KEYWORDS_PATH)
    if not path.exists():
        return []
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def collect_posts(
    page: Page, source: dict[str, Any] | None = None, limit: int = config.CONTENT_SAMPLE_SIZE
) -> list[dict[str, str]]:
    """카테고리 목록 페이지에서 상위 N건의 제목/날짜/작성자를 수집한다.

    source가 주어지고 platform 프로파일(site_profiles.py)이 등록돼 있으면 그 선택자를 쓰고,
    없으면 아래 범용 추측 선택자를 그대로 쓴다.
    """
    profile = site_profiles.get_profile(source or {})
    row_selector = profile.get("post_row_selector", POST_ROW_SELECTOR)
    title_selector = profile.get("post_title_selector", POST_TITLE_SELECTOR)
    author_selector = profile.get("post_author_selector", POST_AUTHOR_SELECTOR)
    date_selector = profile.get("post_date_selector", POST_DATE_SELECTOR)

    rows = page.locator(row_selector).all()[:limit]
    posts = []
    for row in rows:
        try:
            title = row.locator(title_selector).first.inner_text().strip()
            author = row.locator(author_selector).first.inner_text().strip()
            # CLAUDE.md §7.1: 상대 시간 대신 항상 절대 날짜. HTML5 <time datetime="..."> 우선,
            # 없으면 title 속성(툴팁), 그것도 없으면 화면에 보이는 텍스트를 그대로 쓴다 — darkforums
            # Knox 테마의 게시글 날짜(.forum-display__thread-date)는 datetime 속성이 없고 텍스트만
            # 있다(예: "18-11-22, 11:26 AM", 절대 시각이라 여기선 문제없음). stats.py와 같은 순서.
            date_el = row.locator(date_selector).first
            date = (
                date_el.get_attribute("datetime")
                or date_el.get_attribute("title")
                or (date_el.inner_text() or "").strip()
            )
        except Exception:  # noqa: BLE001 - 행 구조가 selector와 안 맞는 경우 건너뜀
            logger.debug("게시글 행 파싱 실패, 건너뜀", exc_info=True)
            continue
        posts.append({"title": title, "author": author, "date": date})
    return posts


def _detect_language_distribution(posts: list[dict[str, str]]) -> Counter[str]:
    """표본 게시글 제목의 언어 비중을 집계한다. 감지 실패(너무 짧은 텍스트 등)는 'unknown'."""
    counts: Counter[str] = Counter()
    for post in posts:
        title = post.get("title", "").strip()
        if not title:
            continue
        try:
            lang = detect(title)
        except LangDetectException:
            lang = "unknown"
        counts[lang] += 1
    return counts


def _detect_pii_types(posts: list[dict[str, str]]) -> list[str]:
    """제목에서 PII 패턴 존재 여부만 확인한다. 매칭된 문자열은 절대 반환하지 않는다(§3-4)."""
    titles = [p.get("title", "") for p in posts]
    types = []
    if any(EMAIL_RE.search(t) for t in titles):
        types.append("이메일")
    if any(PHONE_RE.search(t) for t in titles):
        types.append("전화번호")
    return types


def summarize_posts(posts: list[dict[str, str]], sample_note: str) -> dict[str, Any]:
    """수집된 게시글 헤드라인 목록에서 "사용 언어"/"한국 관련 유출"/"개인정보 유출" 세 필드를
    계산한다. run()(현재 page 1개)과 crawl_site()(사이트 전체 재귀 순회)가 공통으로 쓴다.

    sample_note: MD의 source 칸에 그대로 들어갈 표본 설명 문구(예: "표본 50건 제목 기준").
    "전체 아님"을 항상 명시해야 하므로(CLAUDE.md §6 요구사항 5), 호출부가 표본 규모에 맞는
    문구를 넘긴다.
    """
    today = dt.date.today().isoformat()
    result: dict[str, Any] = {}

    if not posts:
        result["사용 언어"] = {"state": "BLOCKED", "reason": "표본 게시글 수집 실패"}
        result["한국 관련 유출"] = {"state": "BLOCKED", "reason": "표본 게시글 수집 실패"}
        result["개인정보 유출"] = {"state": "BLOCKED", "reason": "표본 게시글 수집 실패"}
        return result

    if detect is None:
        result["사용 언어"] = {"state": "BLOCKED", "reason": "langdetect 미설치"}
    else:
        distribution = _detect_language_distribution(posts)
        total = sum(distribution.values())
        if total == 0:
            result["사용 언어"] = {"state": "CONFIRMED_ABSENT"}
        else:
            parts = [
                f"{lang} {count}건({count * 100 // total}%)" for lang, count in distribution.most_common()
            ]
            result["사용 언어"] = {
                "value": ", ".join(parts),
                "observed_at": today,
                "source": f"{sample_note} langdetect, 전체 아님",
            }
            # profile_report_generator.py("국가"/간단 "사용 언어" 표기)가 위 "사용 언어" 문자열을
            # 다시 정규식으로 파싱하지 않도록, 최다 언어만 구조화해서 별도로 남겨둔다(2026-08-25,
            # 사용자 요청 — "사용 언어는 최다 비율로 확정"). 공개 필드가 아니라 내부 전용(_ 접두사).
            top2 = distribution.most_common(2)
            result["_사용_언어_최다"] = {
                "lang": top2[0][0],
                "pct": top2[0][1] * 100 // total,
                "top2": [(lang, count * 100 // total) for lang, count in top2],
            }

    keywords = _load_keywords()
    matches = [p for p in posts if any(kw in p["title"] for kw in keywords)]
    result["한국 관련 유출"] = {
        "value": f"후보 {len(matches)}건",
        "observed_at": today,
        "source": f"{sample_note} 중 키워드 매칭 — 확정 필요",
    }

    pii_types = _detect_pii_types(posts)
    if pii_types:
        result["개인정보 유출"] = {
            "value": f"패턴 후보 발견: {', '.join(pii_types)} (원문 미저장, 유형만 기록)",
            "observed_at": today,
            "source": f"{sample_note} 정규식 매칭, 본문 미포함 — 확정 필요",
        }
    else:
        result["개인정보 유출"] = {"state": "CONFIRMED_ABSENT"}

    return result


# --- darkforums_profile_*.md 템플릿 전용 후보 계산 (2026-08-25, 사용자 요청) ---
#
# "한국 관련 유출"(위 summarize_posts)은 keywords/korea_keywords.txt 전체(leak/database 같은
# 일반 유출 단어까지 포함)로 넓게 잡는 "후보 건수" 집계용이다. 반면 프로파일 문서의 "한국 관련
# 유출(최근 유출건 N개)"은 한국을 실제로 지칭하는 게시물만 골라야 하므로, 키워드를 korea/korean/
# .kr로 좁혀서 별도 함수로 분리한다 — 안 그러면 "leak"만 매칭된 무관한 글이 "한국 관련"으로 섞인다.
KOREA_SPECIFIC_KEYWORDS = ("korea", "korean", ".kr")

# 유출/DB 판매 게시물 중 "규모"를 내세우는 것(제목에 큰 숫자+단위)만 "주목할 만한 유출" 후보로
# 추린다 — 전체 매칭이 너무 많아(사이트 전체 100건 이상) 다 보여주면 오히려 안 읽힌다. 실제
# 표본 제목엔 "500M users"/"250k" 처럼 약어 단위가 붙거나("million" 아닌 "M" 한 글자),
# "26+ millions"처럼 숫자 뒤에 "+"가 붙는 경우가 흔해서(2026-08-25 확인) 그것도 잡아야 한다.
_SCALE_HINT_RE = re.compile(
    r"\d[\d,.+]*\s*(?:million|billion|thousand)s?\b"
    r"|\d[\d,.+]*\s*(?:gb|tb|mb|kb)\b"
    r"|\d[\d,.+]*\s*[mkbg]\b"
    r"|\d[\d,.+]*\s*(?:users?|rows?|lines?|records?|accounts?)\b",
    re.IGNORECASE,
)

_ABS_DATE_RE = re.compile(r"^(\d{2})-(\d{2})-(\d{2}),\s*\d{1,2}:\d{2}\s*[AP]M$", re.IGNORECASE)
_RELATIVE_UNIT_RE = re.compile(r"^(\d+)\s+(second|minute|hour|day|week)s?\s+ago$", re.IGNORECASE)
_RELATIVE_UNIT_DELTA = {
    "second": lambda n: dt.timedelta(seconds=n),
    "minute": lambda n: dt.timedelta(minutes=n),
    "hour": lambda n: dt.timedelta(hours=n),
    "day": lambda n: dt.timedelta(days=n),
    "week": lambda n: dt.timedelta(weeks=n),
}


def _parse_post_date(date_str: str, reference: dt.date) -> dt.date | None:
    """"최근 N건" 정렬 전용 best-effort 파서. 실패하면 None(정렬 시 가장 뒤로 밀림).

    darkforums 표본의 날짜 문자열은 절대 표기("18-11-22, 11:26 AM", DD-MM-YY)와 상대 표기
    ("Yesterday, ...", "3 hours ago", "Less than 1 minute ago")가 섞여 있다. DD-MM-YY 문자열을
    그대로 사전식(lexical) 비교하면 연도가 맨 뒤라 순서가 틀어지므로(예: "05-07-26"이 "22-08-24"
    보다 사전식으로 앞서지만 실제로는 2년 더 나중) 제대로 파싱해서 비교해야 한다. MD에 실제로
    찍는 날짜 문자열은 원본 그대로 쓴다 — 이 함수는 정렬 순서 계산에만 쓰고 표시용 변환은 안 한다.
    """
    s = date_str.strip()
    if not s:
        return None
    low = s.lower()
    if low.startswith("less than") and "ago" in low:
        return reference
    if low.startswith("today"):
        return reference
    if low.startswith("yesterday"):
        return reference - dt.timedelta(days=1)
    m = _RELATIVE_UNIT_RE.match(low)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        return reference - _RELATIVE_UNIT_DELTA[unit](n)
    m = _ABS_DATE_RE.match(s)
    if m:
        dd, mm, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return dt.date(2000 + yy, mm, dd)
        except ValueError:
            return None
    return None


def find_korea_specific_leaks(
    posts: list[dict[str, str]], limit: int = 2, reference: dt.date | None = None
) -> list[dict[str, str]]:
    """한국을 직접 지칭하는(korea/korean/.kr) 게시물 중 최근 순으로 limit건을 후보로 뽑는다.

    darkforums_profile_*.md 템플릿의 "한국 관련 유출(최근 유출건 N개)" 전용 — 게시글 제목만
    확인했고 본문·첨부는 열람·다운로드하지 않는다(§3-5). 매칭 없으면 빈 리스트.

    각 항목의 "date"는 _parse_post_date()로 파싱 성공하면 절대 날짜(ISO, YYYY-MM-DD)로
    정규화한다(CLAUDE.md §7.1: 상대 시간 표기 금지 — 원본엔 "3 hours ago" 같은 표기가 섞여
    있다). 파싱 실패하면 원본 문자열을 그대로 둔다. 정렬도 이 파싱 결과 기준(최신순)이다.
    """
    reference = reference or dt.date.today()
    matched = [p for p in posts if any(kw in p.get("title", "").lower() for kw in KOREA_SPECIFIC_KEYWORDS)]
    if not matched:
        return []

    ordered = sorted(
        matched, key=lambda p: _parse_post_date(p.get("date", ""), reference) or dt.date.min, reverse=True
    )[:limit]
    items = []
    for p in ordered:
        parsed = _parse_post_date(p.get("date", ""), reference)
        items.append(
            {
                "title": p.get("title", ""),
                "category": p.get("category", "?"),
                "author": p.get("author", "?"),
                "date": parsed.isoformat() if parsed else p.get("date", "?"),
            }
        )
    return items


def find_notable_leak_candidates(posts: list[dict[str, str]], limit: int = 5) -> list[dict[str, str]]:
    """유출/DB 키워드 + 규모 표기가 같이 있는 게시물을 "주목할 만한 유출 후보"로 추린다.

    darkforums_profile_*.md 템플릿의 "개인정보 유출" 전용. 게시자 주장 그대로 인용한 것이라
    진위·규모 모두 미검증이다 — 본문·첨부는 열람·다운로드하지 않는다(§3-5). 매칭 없으면 빈 리스트.
    """
    # 여기선 대소문자를 구분하지 않는다 — "한국 관련 유출"(summarize_posts)의 대소문자 구분
    # 매칭과 달리, 마케팅용 대문자 제목("DUOLINGO Database 500M users" 같은)이 흔해서 구분하면
    # 대부분 놓친다(2026-08-25, 실제 표본 확인).
    keywords = [kw.lower() for kw in _load_keywords()]
    matched = [
        p
        for p in posts
        if any(kw in p.get("title", "").lower() for kw in keywords)
        and _SCALE_HINT_RE.search(p.get("title", ""))
    ]
    if not matched:
        return []

    picked = matched[:limit]
    return [
        {"title": p.get("title", ""), "category": p.get("category", "?"), "author": p.get("author", "?")}
        for p in picked
    ]


def run(page: Page, source: dict[str, Any]) -> dict[str, Any]:
    posts = collect_posts(page, source)
    result = summarize_posts(posts, sample_note=f"표본 {len(posts)}건 제목 기준")
    result["_표본_게시글"] = posts  # 다른 Collector(user_activity 등)가 재사용
    return result


# --- 사이트 전체 재귀 순회 (crawl_site) ---


def _checkpoint_path(source_id: str) -> Path:
    return Path(config.CHECKPOINT_DIR) / f"{source_id}.sitemap_checkpoint.json"


def _load_checkpoint(source_id: str) -> dict[str, Any] | None:
    path = _checkpoint_path(source_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _save_checkpoint(source_id: str, state: dict[str, Any]) -> None:
    path = _checkpoint_path(source_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("체크포인트 저장됨: %s (방문 %d, 대기 %d)", path, len(state["visited"]), len(state["queue"]))


def _clear_checkpoint(source_id: str) -> None:
    path = _checkpoint_path(source_id)
    if path.exists():
        path.unlink()


def _headline_dump_path(source_id: str) -> Path:
    # 원문 스냅샷(snapshot.py)과 같은 원칙: 컨테이너 안 named volume에만 남고 output/ 밖으로
    # 자동 반출되지 않는다(CLAUDE.md §4.1). 매 실행마다 새 타임스탬프 폴더를 만드는
    # snapshot.save_snapshot()과 달리, 이건 "가장 최근에 다 끝까지 돈 실행의 전체 헤드라인
    # 목록"을 소스별로 하나만 유지한다 — "지금 크롤링한 걸 바탕으로" 같은 질문에 바로 답하기
    # 위한 용도라 여러 실행분을 다 쌓아둘 필요는 없다.
    return Path(config.SNAPSHOTS_DIR) / source_id / "collected_headlines.json"


def _save_headline_dump(source_id: str, posts: list[dict[str, str]]) -> None:
    path = _headline_dump_path(source_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"observed_at": dt.date.today().isoformat(), "posts": posts},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.info("헤드라인 전체 목록 저장됨: %s (%d건)", path, len(posts))


def _random_delay() -> None:
    # CLAUDE.md §4.2-6: 요청 간 3~5초 랜덤 지연. 암호학적 난수가 필요한 용도가 아니다(S311).
    time.sleep(random.uniform(config.REQUEST_DELAY_MIN_SEC, config.REQUEST_DELAY_MAX_SEC))  # noqa: S311


def crawl_site(
    page: Page,
    source: dict[str, Any],
    category_seed: list[dict[str, str]],
    *,
    resume: bool = False,
) -> dict[str, Any]:
    """홈페이지에서 발견한 모든 카테고리(하위 서브포럼 포함)를 재귀적으로 다 돌며 게시글
    헤드라인(제목/작성자/날짜)만 모은다 — 개별 게시글 본문 페이지에는 들어가지 않는다.

    - 카테고리 하나당 페이지네이션은 최대 config.SITE_MAP_MAX_PAGES_PER_CATEGORY 페이지까지.
    - 이미 방문한 URL은 다시 안 간다(무한 루프 방지).
    - 세션 만료/챌린지 감지 시 CrawlInterrupted를 던진다. 자동 재로그인은 하지 않는다
      (§3-3) — 체크포인트를 남기고 사람에게 넘긴다.
    - resume=True면 이전에 남긴 체크포인트가 있는지 먼저 확인하고, 있으면 거기서부터
      이어서 진행한다(처음부터 다시 돌지 않음).
    """
    from collectors import structure  # 지연 import: structure.py는 이 모듈을 참조하지 않음

    source_id = source.get("name") or source.get("url", "unknown")
    profile = site_profiles.get_profile(source)
    origin_url = page.url

    checkpoint = _load_checkpoint(source_id) if resume else None
    if checkpoint:
        queue: list[dict[str, str]] = checkpoint["queue"]
        visited: set[str] = set(checkpoint["visited"])
        posts: list[dict[str, str]] = checkpoint["posts"]
        visited_categories: list[str] = checkpoint["visited_categories"]
        # .get(..., []): 이 필드가 없던 예전 체크포인트에서 --resume 해도 KeyError 없이 진행되게.
        visited_urls: list[dict[str, str]] = checkpoint.get("visited_urls", [])
        logger.info("체크포인트에서 이어서 진행: 방문 %d개, 대기 %d개", len(visited), len(queue))
    else:
        queue = list(category_seed)
        visited = set()
        posts = []
        visited_categories = []
        visited_urls = []

    def checkpoint_state(remaining_queue: list[dict[str, str]]) -> dict[str, Any]:
        return {
            "queue": remaining_queue,
            "visited": sorted(visited),
            "posts": posts,
            "visited_categories": visited_categories,
            "visited_urls": visited_urls,
        }

    # 카테고리 목록/게시글 selector(post_row_selector 등)는 실제 마크업을 봐야 채울 수 있다
    # (site_profiles.py). 매 페이지를 다 스냅샷하면 볼륨이 금방 커지므로, 이번 실행에서 처음
    # 방문에 성공한 카테고리 페이지 딱 1개만 저장해서 selector 확정용 참고자료로 남긴다.
    snapshotted_first_category = bool(checkpoint)  # 이어서 진행하는 경우는 이미 저장된 적 있다고 본다

    # 사이트 전체 순회는 카테고리 수 × 페이지 수만큼 오래 걸릴 수 있어서(각 요청 사이
    # 3~5초 지연 + .onion 자체가 느림) 지금 어디까지 갔는지 눈으로 볼 수 있게 진행바를
    # 띄운다. 큐가 재귀적으로 늘어나(하위 서브포럼 발견) 총량을 미리 알 수 없으므로
    # total은 고정하지 않고, 방문+대기 합계로 매 카테고리마다 갱신해 대략치만 보여준다.
    page_bar = tqdm(desc=f"{source_id} 사이트맵 순회", unit="page")

    try:
        while queue:
            entry = queue.pop(0)
            url = entry.get("url", "")
            if not url or url in visited:
                continue

            _random_delay()
            try:
                page.goto(url, timeout=config.PAGE_LOAD_TIMEOUT_MS, wait_until=config.PAGE_WAIT_UNTIL)
            except Exception:  # noqa: BLE001 - 개별 카테고리 접속 실패는 건너뛰고 계속 진행
                logger.warning("카테고리 접속 실패, 건너뜀: %s", url)
                visited.add(url)
                continue

            # 챌린지 감지는 상시로 한다(§4.2-6). 세션 만료 자체는 여기서 다시 확인하지 않는다
            # — run_pipeline()이 이미 크롤링 시작 시점에 한 번 확인·기록했고(M1 완료 기준),
            # 카테고리 페이지마다 logged_in_selector가 다시 보일 거란 보장이 없어서(예: 로그인
            # 표시 요소가 홈페이지에만 있는 테마) 오탐으로 매번 멈추는 걸 피한다.
            #
            # 주의: 챌린지로 막힌 URL은 visited에 아직 넣지 않는다 — 체크포인트 큐 맨 앞에
            # 되돌려서, --resume 시 "이미 방문함"으로 건너뛰지 않고 진짜로 다시 시도하게 한다.
            reason = challenge.detect(page)
            if reason:
                _save_checkpoint(source_id, checkpoint_state([entry, *queue]))
                raise CrawlInterrupted(f"챌린지 감지: {reason} ({url})")

            visited.add(url)
            visited_categories.append(entry.get("text", url))
            page_bar.total = len(visited) + len(queue)  # 재귀로 늘어나는 대략치, 매번 갱신

            if not snapshotted_first_category:
                snapshot.save_snapshot(page, source_id, "sitemap_first_category")
                snapshotted_first_category = True

            # 이 카테고리 안에 또 하위 서브포럼이 있으면 큐에 추가한다(재귀 — "수집된 모든
            # 카테고리를 다 들어간다").
            for sub in structure.discover_categories(page, profile):
                if sub["url"] and sub["url"] not in visited:
                    queue.append(sub)

            # 헤드라인 수집 — 페이지네이션 최대 SITE_MAP_MAX_PAGES_PER_CATEGORY 페이지까지.
            # 게시글 본문(개별 스레드 페이지)에는 들어가지 않는다. 어느 카테고리·몇 페이지째에서
            # 나온 헤드라인인지 나중에(예: "Sellers Place 4페이지 헤드라인 보여줘") 되짚어볼 수
            # 있도록 각 게시글에 category/page를 같이 표시해둔다.
            category_name = entry.get("text", url)
            visited_urls.append({"category": category_name, "page": 1, "url": url})
            next_selector = profile.get("pagination_next_selector", PAGINATION_NEXT_SELECTOR)
            for page_num in range(1, config.SITE_MAP_MAX_PAGES_PER_CATEGORY + 1):
                for post in collect_posts(page, source, limit=config.CONTENT_SAMPLE_SIZE):
                    post["category"] = category_name
                    post["page"] = page_num
                    posts.append(post)
                page_bar.set_postfix_str(f"{category_name} p{page_num}")
                page_bar.update(1)

                if page_num >= config.SITE_MAP_MAX_PAGES_PER_CATEGORY:
                    break
                next_href = _find_next_page_href(page, next_selector, page_num + 1)
                if not next_href:
                    break
                next_url = urljoin(page.url, next_href)
                if next_url in visited:
                    break

                _random_delay()
                try:
                    page.goto(
                        next_url, timeout=config.PAGE_LOAD_TIMEOUT_MS, wait_until=config.PAGE_WAIT_UNTIL
                    )
                except Exception:  # noqa: BLE001 - 다음 페이지 접속 실패는 이 카테고리만 중단
                    logger.warning("페이지네이션 접속 실패, 이 카테고리는 여기까지: %s", next_url)
                    break

                reason = challenge.detect(page)
                if reason:
                    _save_checkpoint(source_id, checkpoint_state(queue))
                    raise CrawlInterrupted(f"챌린지 감지: {reason} ({next_url})")

                visited.add(next_url)
                visited_urls.append({"category": category_name, "page": page_num + 1, "url": next_url})

            _save_checkpoint(source_id, checkpoint_state(queue))
    finally:
        page_bar.close()
        try:
            page.goto(origin_url, timeout=config.PAGE_LOAD_TIMEOUT_MS, wait_until=config.PAGE_WAIT_UNTIL)
        except Exception:  # noqa: BLE001 - 원래 페이지 복귀 실패해도 다음 단계는 계속
            logger.warning("사이트 전체 순회 후 원래 페이지로 복귀 실패: %s", origin_url)

    _clear_checkpoint(source_id)  # 큐가 다 빌 때까지 끝까지 돌았으면 다음 실행은 새로 시작
    _save_headline_dump(source_id, posts)  # MD엔 집계만 남지만, 원본 헤드라인 목록도 따로 보존한다

    sample_note = (
        f"사이트 전체 {len(visited_categories)}개 카테고리 × 최대 "
        f"{config.SITE_MAP_MAX_PAGES_PER_CATEGORY}페이지 헤드라인 기준"
    )
    result = summarize_posts(posts, sample_note)
    result["_표본_게시글"] = posts
    result["_사이트맵_방문_카테고리"] = visited_categories
    result["_사이트맵_방문_URL"] = visited_urls  # report_generator가 MD에 감사(audit)용으로 남김
    return result
