from __future__ import annotations

from collectors import user_activity


def test_run_counts_by_handle_and_tracks_last_seen():
    posts = [
        {"title": "a", "author": "Max987", "date": "2026-07-30"},
        {"title": "b", "author": "Max987", "date": "2026-08-01"},
        {"title": "c", "author": "otherUser", "date": "2026-08-02"},
    ]

    result = user_activity.run(posts, source={"url": "http://x.onion"})
    handles = {h["handle"]: h for h in result["_표본_핸들"]}

    assert handles["Max987"]["count"] == 2
    assert handles["Max987"]["last_seen"] == "2026-08-01"
    assert handles["otherUser"]["count"] == 1


def test_run_handles_empty_posts():
    result = user_activity.run([], source={"url": "http://x.onion"})
    assert result["_표본_핸들"] == []


def test_run_never_makes_identity_judgement():
    """동일인 여부 판단은 하지 않는다 — 반환 dict에 그런 필드가 없어야 한다."""
    posts = [{"title": "a", "author": "Max987", "date": "2026-08-01"}]
    result = user_activity.run(posts, source={"url": "http://x.onion"})

    for handle_entry in result["_표본_핸들"]:
        assert set(handle_entry.keys()) == {"handle", "count", "last_seen"}


def test_find_operator_candidates_uses_announcement_board_authors():
    posts = [
        {"title": "a", "author": "Knox", "category": "Announcements", "date": "2026-08-01"},
        {"title": "b", "author": "Knox", "category": "Announcements", "date": "2026-08-02"},
        {"title": "c", "author": "Lucifer", "category": "Announcements", "date": "2026-08-03"},
        {"title": "e", "author": "Lucifer", "category": "Announcements", "date": "2026-08-04"},
        {"title": "f", "author": "OneTimePoster", "category": "Announcements", "date": "2026-08-05"},
        {"title": "d", "author": "randomUser", "category": "General Discussion", "date": "2026-08-01"},
    ]

    result = user_activity.find_operator_candidates(posts)

    # 1회성 게시자(OneTimePoster)는 min_posts=2 임계치 미만이라 빠진다.
    assert result["handles"] == ["Knox", "Lucifer"]
    assert result["categories"] == ["Announcements"]


def test_find_operator_candidates_empty_without_announcement_board():
    posts = [{"title": "d", "author": "randomUser", "category": "General Discussion", "date": "2026-08-01"}]

    result = user_activity.find_operator_candidates(posts)

    assert result["handles"] == []


def test_find_operator_candidates_empty_without_category_field():
    """sample_list_url 단일 페이지 경로(category 없음)에서는 항상 빈 결과가 나온다."""
    posts = [{"title": "d", "author": "randomUser", "date": "2026-08-01"}]

    result = user_activity.find_operator_candidates(posts)

    assert result["handles"] == []
