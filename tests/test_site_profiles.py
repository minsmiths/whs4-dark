"""site_profiles.py: platform 필드로 collector 선택자를 오버라이드하는 배선 검증."""

from __future__ import annotations

import site_profiles


def test_get_profile_returns_empty_when_no_platform_field():
    assert site_profiles.get_profile({}) == {}
    assert site_profiles.get_profile({"url": "http://x.onion"}) == {}


def test_get_profile_returns_empty_when_platform_unregistered():
    assert site_profiles.get_profile({"platform": "no-such-platform"}) == {}


def test_get_profile_returns_registered_profile(monkeypatch):
    monkeypatch.setitem(site_profiles.PROFILES, "test-platform", {"nav_link_selector": ".x a"})

    assert site_profiles.get_profile({"platform": "test-platform"}) == {"nav_link_selector": ".x a"}
