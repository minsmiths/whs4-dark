from __future__ import annotations

from collectors import cross_reference


def test_extract_mentions_finds_url_onion_and_telegram():
    onion_addr = "abcdefghijklmnopqrstuvwxyz234567abcdefghijklmnop.onion"  # v3 형식(a-z2-7), 유효한 fixture
    text = f"이거 t.me/RaidForums 에서 봤고 https://pastebin.com/abc123 도 있고 {onion_addr} 도 언급됨"
    mentions = cross_reference.extract_mentions(text, context_label="게시글 제목")

    assert any("t.me/RaidForums" in m for m in mentions)
    assert any("pastebin.com" in m for m in mentions)
    assert any(".onion" in m for m in mentions)
    assert all('게시글 제목"에서 발견' in m for m in mentions)


def test_run_does_not_set_confirmed_link_field():
    """cross_reference.run() 은 '발견'만 하고 '연결된 곳'을 확정하지 않는다 (CLAUDE.md §1)."""
    result = cross_reference.run({"a": "t.me/example"}, source={"url": "http://x.onion"})

    assert "연결된 곳" not in result
    assert "_발견된_외부_언급" in result
    assert any("t.me/example" in m for m in result["_발견된_외부_언급"])
