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
