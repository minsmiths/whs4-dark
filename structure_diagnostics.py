"""페이지 구조를 읽기 전용으로 진단해 selector 후보 자료를 남긴다.

진단 결과는 raw HTML 스냅샷과 같은 격리 디렉터리에만 저장한다. 링크를 따라가거나
본문/사용자 텍스트를 복사하지 않고, DOM 모양과 URL 패턴만 기록한다.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qsl, urljoin, urlsplit

import snapshot

if TYPE_CHECKING:
    from playwright.sync_api import Page

logger = logging.getLogger(__name__)


def _url_pattern(href: str, origin_url: str) -> str:
    """식별 가능성이 있는 URL 값을 제거하고 경로/쿼리 키 모양만 반환한다."""
    try:
        parsed = urlsplit(urljoin(origin_url, href))
    except ValueError:
        return "?"
    path = re.sub(r"(?<=/)\d+(?=/|$)", "N", parsed.path)
    path = re.sub(r"(?<=/)[0-9a-f]{16,}(?=/|$)", "HEX", path, flags=re.IGNORECASE)
    path = re.sub(r"(?<=/)[^/]{20,}(?=/|$)", "LONG", path)
    query_keys = sorted({key for key, _ in parse_qsl(parsed.query, keep_blank_values=True)})
    return path + ("?" + "&".join(query_keys) if query_keys else "")


def inspect(page: Page) -> dict[str, Any]:
    """현재 DOM의 반복 구조, 링크 패턴, 클래스 및 페이지네이션 후보를 반환한다."""
    dom = page.evaluate(
        """() => {
            const shape = (el) => {
                const classes = typeof el.className === "string"
                    ? el.className.trim().split(/\\s+/).filter(Boolean).slice(0, 3)
                    : [];
                return el.tagName.toLowerCase() + (classes.length ? "." + classes.join(".") : "");
            };
            const ancestry = (el) => {
                const parts = [];
                let node = el;
                for (let depth = 0; node && node !== document.body && depth < 6; depth += 1) {
                    parts.push(shape(node));
                    node = node.parentElement;
                }
                return parts.join(" < ");
            };
            const repeated = [];
            for (const parent of document.querySelectorAll("body *")) {
                const counts = new Map();
                for (const child of parent.children) {
                    const key = shape(child);
                    counts.set(key, (counts.get(key) || 0) + 1);
                }
                for (const [childShape, count] of counts) {
                    if (count >= 3) repeated.push({count, child_shape: childShape, parent: ancestry(parent)});
                }
            }
            repeated.sort((a, b) => b.count - a.count);

            const classCounts = new Map();
            for (const el of document.querySelectorAll("[class]")) {
                if (typeof el.className !== "string") continue;
                for (const name of el.className.trim().split(/\\s+/)) {
                    if (name) classCounts.set(name, (classCounts.get(name) || 0) + 1);
                }
            }
            const classes = [...classCounts.entries()]
                .sort((a, b) => b[1] - a[1]).slice(0, 20)
                .map(([name, count]) => ({name, count}));
            const links = [...document.querySelectorAll("a[href]")].map((a) => ({
                href: a.getAttribute("href") || "",
                text: (a.textContent || "").replace(/\\s+/g, " ").trim().slice(0, 20),
            }));
            return {
                title: document.title,
                element_count: document.querySelectorAll("*").length,
                links,
                repeated_blocks: repeated.slice(0, 10),
                class_frequency: classes,
            };
        }"""
    )

    link_patterns = Counter(_url_pattern(link["href"], page.url) for link in dom.pop("links"))
    pagination = []
    for link in page.locator("a[href]").all():
        href = link.get_attribute("href") or ""
        text = (link.inner_text() or "").strip()
        if re.search(r"(?:page[=/-]\d|/page-\d)", href, re.IGNORECASE) or text.isdigit():
            pagination.append({"text": text[:8], "url_pattern": _url_pattern(href, page.url)})
            if len(pagination) >= 15:
                break

    return {
        "url_scheme": urlsplit(page.url).scheme,
        "title": dom["title"],
        "link_count": sum(link_patterns.values()),
        "element_count": dom["element_count"],
        "link_path_patterns": [
            {"pattern": pattern, "count": count}
            for pattern, count in link_patterns.most_common(20)
        ],
        "repeated_blocks": dom["repeated_blocks"],
        "class_frequency": dom["class_frequency"],
        "pagination_candidates": pagination,
    }


def save(page: Page, source_id: str, label: str) -> Path | None:
    """구조 진단 JSON을 raw HTML 스냅샷과 같은 보호 위치에 저장한다."""
    try:
        result = inspect(page)
    except Exception:  # noqa: BLE001 - 진단 자료 실패가 본 수집을 중단하지 않게 한다
        logger.warning("페이지가 이동 중이어서 구조 진단을 건너뜀: %s", label)
        return None
    file_path = snapshot.snapshot_path(source_id, label, ".json")
    file_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return file_path
