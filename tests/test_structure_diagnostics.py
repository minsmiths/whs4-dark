from __future__ import annotations

import json

from playwright.sync_api import sync_playwright

import config
import structure_diagnostics


def test_inspect_finds_patterns_without_copying_body_text():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.set_content(
            """
            <div class="thread-list">
              <article class="thread row"><a href="/thread/123?page=1">Secret title A</a></article>
              <article class="thread row"><a href="/thread/456?page=2">Secret title B</a></article>
              <article class="thread row"><a href="/thread/789?page=3">Secret title C</a></article>
            </div>
            """
        )

        result = structure_diagnostics.inspect(page)

        assert result["link_count"] == 3
        assert any(item["count"] == 3 for item in result["repeated_blocks"])
        assert any(item["name"] == "thread" and item["count"] == 3 for item in result["class_frequency"])
        assert result["pagination_candidates"]
        assert "Secret title" not in json.dumps(result)
        browser.close()


def test_save_writes_diagnostic_beside_snapshots(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SNAPSHOTS_DIR", str(tmp_path))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.set_content("<nav><a href='/forum/42'>Forum</a></nav>")

        path = structure_diagnostics.save(page, "example", "home diagnostic")

        assert path.suffix == ".json"
        assert path.is_file()
        assert json.loads(path.read_text(encoding="utf-8"))["link_count"] == 1
        browser.close()
