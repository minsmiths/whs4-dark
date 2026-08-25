"""⑦ 유저 활동 집계. 요구사항 7 대응 (로드맵 M4).

동일인 여부 판단은 하지 않는다. 다른 사이트에서 같은 핸들이 나와도 자동으로
연결하지 않고, "판단 근거 / 반대 근거" 빈 칸을 MD에 만들어 사람이 채우게 한다.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import config

# darkforums_profile_*.md 템플릿의 "운영자(추정)" 전용(2026-08-25, 사용자 요청). 공지 게시판에
# 쓸 수 있었다는 정황일 뿐 실제 운영진 등급(Administrator 배지 등)을 확인한 게 아니다 — 동일인/
# 역할 판단은 여기서 하지 않는다(요구사항 7, 위 모듈 docstring).
ANNOUNCEMENT_CATEGORY_KEYWORDS = ("announce",)


def run(posts: list[dict[str, str]], source: dict[str, Any]) -> dict[str, Any]:
    """posts: content_sample.collect_posts() 가 반환한 표본 게시글 목록.

    investigate.py 가 content_sample 결과의 `_표본_게시글`을 이 함수에 그대로 전달한다.
    """
    result: dict[str, Any] = {}

    if not posts:
        result["_표본_핸들"] = []
        return result

    author_counts = Counter(p["author"] for p in posts if p.get("author"))
    top_authors = author_counts.most_common(config.USER_ACTIVITY_TOP_N)

    last_seen: dict[str, str] = {}
    for p in posts:
        author = p.get("author")
        date = p.get("date", "")
        if author and date and date > last_seen.get(author, ""):
            last_seen[author] = date

    result["_표본_핸들"] = [
        {"handle": handle, "count": count, "last_seen": last_seen.get(handle, "날짜 미상")}
        for handle, count in top_authors
    ]
    return result


def find_operator_candidates(
    posts: list[dict[str, str]],
    category_keywords: tuple[str, ...] = ANNOUNCEMENT_CATEGORY_KEYWORDS,
    min_posts: int = 2,
) -> dict[str, Any]:
    """공지 게시판(카테고리명에 "announce" 포함)에 min_posts건 이상 쓴 계정을 운영자 후보로
    추린다. 1회성 게시자는 임계치 미만이라 후보에서 빠진다 — 신뢰도를 조금이라도 높이려는
    거름망일 뿐 판단 근거는 아니다.

    content_sample.crawl_site()가 붙인 category 필드가 있어야 의미가 있다 — sample_list_url
    단일 페이지 경로(content_sample.run())의 posts에는 category가 없어서 항상 빈 결과가 된다.
    "handles"가 빈 리스트면 매칭 없음(카테고리 자체가 없거나 임계치를 넘는 계정이 없음).
    """
    matched = [p for p in posts if any(kw in p.get("category", "").lower() for kw in category_keywords)]
    counts = Counter(p["author"] for p in matched if p.get("author"))
    handles = [handle for handle, count in counts.most_common() if count >= min_posts]
    categories = sorted({p["category"] for p in matched})
    return {"handles": handles, "categories": categories}
