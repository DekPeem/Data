"""Small helpers for driving the DBD DataWarehouse SPA with Playwright.

The site is Vue: clicks swap content in place without a navigation, and the
markup carries generated data-v-* attributes but very few ids. So the two
things worth centralising are "try a list of candidate selectors until one is
actually visible" and "click the element whose visible Thai text says X".
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator, Page

from . import config


class ElementNotFound(RuntimeError):
    """No candidate selector matched anything visible."""

    def __init__(self, selectors: Sequence[str], what: str = "element"):
        self.selectors = list(selectors)
        super().__init__(
            f"Could not find {what}. Tried:\n  "
            + "\n  ".join(self.selectors)
            + "\n\nThe page layout probably changed — update the candidate "
              "list in config.py. Re-run with --headed to watch it happen, or "
              "check the dump in debug/."
        )


def find(
    page: Page,
    selectors: Iterable[str],
    *,
    timeout_ms: int | None = None,
    what: str = "element",
    required: bool = True,
) -> Locator | None:
    """First visible match for any of the candidate selectors, in order."""
    selectors = list(selectors)
    timeout_ms = timeout_ms if timeout_ms is not None else config.DEFAULT_TIMEOUT_MS
    deadline = time.monotonic() + timeout_ms / 1000

    while True:
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if locator.count() > 0 and locator.is_visible():
                    return locator
            except PlaywrightError:
                continue
        if time.monotonic() >= deadline:
            break
        page.wait_for_timeout(300)

    if required:
        raise ElementNotFound(selectors, what)
    return None


def click_by_text(
    page: Page,
    selectors: Iterable[str],
    text: str,
    *,
    timeout_ms: int | None = None,
    what: str | None = None,
    required: bool = True,
) -> Locator | None:
    """Click the element matching a candidate selector whose text says `text`.

    Thai labels are the stable handle on this site — the classes are shared by
    every button in a group (all three statement buttons are `span.finMenu`),
    so text is what distinguishes them.
    """
    what = what or f"{text!r}"
    locator = find_by_text(
        page, selectors, text, timeout_ms=timeout_ms, what=what, required=required
    )
    if locator is None:
        return None
    locator.scroll_into_view_if_needed(timeout=5_000)
    locator.click(timeout=timeout_ms or config.DEFAULT_TIMEOUT_MS)
    page.wait_for_timeout(config.SETTLE_MS)
    return locator


def find_by_text(
    page: Page,
    selectors: Iterable[str],
    text: str,
    *,
    timeout_ms: int | None = None,
    what: str | None = None,
    required: bool = True,
) -> Locator | None:
    """Locate (without clicking) the element whose visible text contains `text`."""
    selectors = list(selectors)
    what = what or f"element with text {text!r}"
    timeout_ms = timeout_ms if timeout_ms is not None else config.DEFAULT_TIMEOUT_MS
    deadline = time.monotonic() + timeout_ms / 1000
    wanted = _norm(text)

    while True:
        for selector in selectors:
            try:
                candidates = page.locator(selector)
                count = min(candidates.count(), 40)
            except PlaywrightError:
                continue
            for i in range(count):
                candidate = candidates.nth(i)
                try:
                    if not candidate.is_visible():
                        continue
                    if wanted in _norm(candidate.inner_text()):
                        return candidate
                except PlaywrightError:
                    continue
        if time.monotonic() >= deadline:
            break
        page.wait_for_timeout(300)

    if required:
        raise ElementNotFound([f"{s} :text({text})" for s in selectors], what)
    return None


def _norm(value: str | None) -> str:
    """Collapse whitespace so 'งบกำไรขาดทุน\\n' matches 'งบกำไรขาดทุน'."""
    return "".join((value or "").split())


def dump_debug(page: Page, label: str) -> Path:
    """Save a screenshot + the rendered DOM so a failure stays diagnosable.

    page.content() on a Vue app gives the *rendered* DOM, which is what we
    actually matched against — that is the useful artefact here.
    """
    config.DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    stem = config.DEBUG_DIR / f"{datetime.now():%Y%m%d-%H%M%S}-{label}"

    try:
        page.screenshot(path=str(stem.with_suffix(".png")), full_page=True)
    except PlaywrightError:
        pass
    try:
        stem.with_suffix(".html").write_text(
            f"<!-- url: {page.url} -->\n{page.content()}", encoding="utf-8"
        )
    except (PlaywrightError, OSError):
        pass

    return stem
