"""⑦ 유저 활동 집계. 요구사항 7 대응 (로드맵 M4).

동일인 여부 판단은 하지 않는다. 다른 사이트에서 같은 핸들이 나와도 자동으로
연결하지 않고, "판단 근거 / 반대 근거" 빈 칸을 MD에 만들어 사람이 채우게 한다.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import config


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
