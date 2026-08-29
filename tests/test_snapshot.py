from __future__ import annotations

import config
import snapshot


class _NavigatingPage:
    def __init__(self, failures: int):
        self.failures = failures
        self.calls = 0

    def content(self):
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError("page is navigating")
        return "<html><body>ready</body></html>"


def test_save_snapshot_retries_navigation_race(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SNAPSHOTS_DIR", str(tmp_path))
    page = _NavigatingPage(failures=2)

    path = snapshot.save_snapshot(page, "example", "home")

    assert path is not None
    assert path.read_text(encoding="utf-8") == "<html><body>ready</body></html>"
    assert page.calls == 3


def test_save_snapshot_skips_when_page_never_stabilizes(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SNAPSHOTS_DIR", str(tmp_path))
    page = _NavigatingPage(failures=99)

    path = snapshot.save_snapshot(page, "example", "home")

    assert path is None
    assert not list(tmp_path.rglob("*.html"))
