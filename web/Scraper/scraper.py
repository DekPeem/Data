"""The DBD DataWarehouse flow: search → juristic data → financial statement.

One company per run:

  1. type the registration id into the home search box and take the suggestion
  2. read the ข้อมูลนิติบุคคล card into label/value pairs
  3. open the ข้อมูลงบการเงิน tab › งบการเงิน
  4. pick the fiscal year, then each statement in turn — by default all three:
     งบกำไรขาดทุน, งบแสดงฐานะการเงิน, อัตราส่วนทางการเงิน
  5. read the table that appears

Parsing happens in the browser (page.evaluate) rather than by pulling HTML out
and re-parsing it here: the DOM we want is already built, and doing it in one
pass avoids a second HTML parser dependency.
"""

from __future__ import annotations

import re
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

import browser_utils as bu
import config

_IS_REGISTRATION_ID = re.compile(r"^\d{13}$")


class OverlayBlocked(RuntimeError):
    """The DBD warning popup could not be cleared off the search box.

    Transient by nature — the modal opens a beat after the page and clears on
    its own given a moment, so a fresh attempt usually lands. Raised (instead of
    letting the click run out its long timeout) so the caller can tell the user
    to try again rather than surfacing a raw Playwright timeout.
    """


# --------------------------------------------------------------------------
# Step 0 — get the modals out of the way
# --------------------------------------------------------------------------
def dismiss_overlays(page: Page, *, rounds: int = 4) -> None:
    """Close the warning modal / cookie banner that cover the home page.

    Bootstrap's backdrop swallows every click while a modal is open, so this
    has to happen before anything else — and it has to be repeatable, since
    dismissing one overlay can reveal the next.

    The #warningModal renders a beat after the page, and on a slow or distant
    host that beat can fall after the caller's fixed settle. Firing the dismiss
    once and returning (nothing visible yet) then left the modal to open over
    the search box and intercept its click — the failure seen on the deployed
    server. So first wait a bounded time for an overlay to appear, and if a
    close button will not take (Bootstrap's fade can eat a click mid-animation,
    and a variant may carry an id we do not list) force the overlay out of the
    DOM as a last resort, so it can no longer swallow pointer events.
    """
    # Let the modal render before deciding there is nothing to do. Returns the
    # instant one is visible; only the no-overlay case waits the whole timeout.
    try:
        page.wait_for_selector(
            ".modal.show, [class*='cookie']",
            state="visible",
            timeout=config.OVERLAY_WAIT_MS,
        )
    except PlaywrightError:
        return  # nothing appeared — the home page is already clickable

    for _ in range(rounds):
        clicked = False
        for selector in config.OVERLAY_DISMISS:
            try:
                button = page.locator(selector).first
                if button.count() == 0 or not button.is_visible():
                    continue
                button.click(timeout=5_000)
                page.wait_for_timeout(config.SETTLE_MS)
                clicked = True
            except PlaywrightError:
                continue
        if not clicked:
            break

    _force_clear_overlays(page)


def _force_clear_overlays(page: Page) -> None:
    """Remove any modal still shown, plus its backdrop and the body lock.

    The escape hatch for the two cases a click cannot solve: an overlay stuck
    part-way through its fade transition, and a modal whose close control is not
    one of the selectors above. Editing only this automation page's DOM — the
    site is untouched — it strips the `show` state, hides the dialog, drops the
    `.modal-backdrop`, and clears the `modal-open` lock so the page underneath
    takes clicks again. A no-op when nothing is open.
    """
    try:
        page.evaluate(
            """() => {
                document
                  .querySelectorAll('.modal.show, .modal.modal-inform')
                  .forEach((m) => {
                    m.classList.remove('show');
                    m.style.display = 'none';
                    m.setAttribute('aria-hidden', 'true');
                  });
                document
                  .querySelectorAll('.modal-backdrop')
                  .forEach((b) => b.remove());
                document.body.classList.remove('modal-open');
                document.body.style.removeProperty('overflow');
                document.body.style.removeProperty('padding-right');
            }"""
        )
    except PlaywrightError:
        pass


# --------------------------------------------------------------------------
# Step 1 — search
# --------------------------------------------------------------------------
def search_company(page: Page, company_id: str) -> None:
    """Land on the company's page, starting from the home search bar.

    Typing into the box opens an autocomplete list; clicking its first entry is
    the path a user takes and the one the SPA is built around. If no suggestion
    appears (the box occasionally stays quiet on a cold cache) we fall back to
    submitting the search, and finally to the profile URL directly.
    """
    page.goto(config.BASE_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(config.SETTLE_MS)
    dismiss_overlays(page)

    box = bu.find(page, config.SEARCH_INPUT, what="the home search box")
    # The click is where a re-opened warning modal bites: it sits over the box
    # and swallows the click. Give it a short bound rather than the 45s default,
    # and if it is intercepted, clear the overlays once more and try again. If
    # it still will not take, the popup is winning the race today — raise
    # OverlayBlocked so the caller can say "try again" instead of letting the
    # click run out a long, opaque timeout.
    try:
        box.click(timeout=config.OVERLAY_WAIT_MS)
    except PlaywrightError:
        dismiss_overlays(page)
        try:
            box.click(timeout=config.OVERLAY_WAIT_MS)
        except PlaywrightError as exc:
            raise OverlayBlocked(
                "ไม่สามารถปิดหน้าต่างแจ้งเตือนของเว็บ DBD ได้ กรุณาลองดึงข้อมูลใหม่อีกครั้ง"
                " / Could not dismiss the DBD site's notice popup. Please try the pull again."
            ) from exc
    box.fill("")
    # type() rather than fill(): the suggestion list is driven by keystroke
    # events, and a one-shot fill() does not always trigger it.
    box.type(company_id, delay=60)
    print(f"Searching for {company_id} …")

    if not _click_suggestion(page, company_id):
        # Expected: the autocomplete does not open under automation. Submitting
        # an exact registration id goes straight to that company's page anyway.
        print("  no suggestion list — submitting the search")
        box.press("Enter")
        page.wait_for_timeout(config.SETTLE_MS * 2)

    if not _on_company_page(page):
        if not _IS_REGISTRATION_ID.match(company_id):
            bu.dump_debug(page, f"not-an-id-{company_id}")
            raise RuntimeError(
                f"{company_id!r} is not a 13-digit registration id, and the "
                "site's autocomplete — the only way to search by name — does "
                "not open for typed input under automation. Look the company "
                "up by hand once and pass its registration id."
            )
        url = config.PROFILE_URL.format(company_id=company_id)
        print(f"  search did not navigate — going straight to {url}")
        page.goto(url, wait_until="domcontentloaded")

    _wait_for_company_page(page, company_id)
    print(f"  opened {page.url}")


def _click_suggestion(page: Page, company_id: str) -> bool:
    """Click the autocomplete entry for this id. False if none showed up."""
    item = bu.find(
        page,
        config.SUGGESTION_ITEM,
        timeout_ms=4_000,
        what="a search suggestion",
        required=False,
    )
    if item is None:
        return False

    # Prefer the entry that actually mentions the id; some lists lead with a
    # "search for …" row that goes to the results page rather than the company.
    exact = bu.find_by_text(
        page, config.SUGGESTION_ITEM, company_id, timeout_ms=3_000, required=False
    )
    target = exact if exact is not None else item
    try:
        target.click(timeout=10_000)
    except PlaywrightError:
        return False
    page.wait_for_timeout(config.SETTLE_MS * 2)
    return True


def _on_company_page(page: Page) -> bool:
    """True once the juristic card (or its tab bar) is on screen."""
    try:
        if page.locator(".nav-tabs.main").count() > 0:
            return True
        return page.locator(f"text={config.FINANCE_TAB_TEXT}").count() > 0
    except PlaywrightError:
        return False


def _wait_for_company_page(page: Page, company_id: str) -> None:
    try:
        page.wait_for_selector(".nav-tabs.main", timeout=config.DEFAULT_TIMEOUT_MS)
    except PlaywrightError as exc:
        bu.dump_debug(page, f"no-company-page-{company_id}")
        raise RuntimeError(
            f"Search for {company_id} did not land on a company page "
            f"(url: {page.url}). A dump was written to debug/."
        ) from exc
    page.wait_for_timeout(config.SETTLE_MS)


# --------------------------------------------------------------------------
# Step 2 — the juristic-data card
# --------------------------------------------------------------------------
_JURISTIC_JS = """
() => {
  const norm = s => (s || '').replace(/\\u00a0/g, ' ').replace(/\\s+/g, ' ').trim();
  const out = [];
  const seen = new Set();

  // Labels carry .prompt; the value is the very next sibling column.
  for (const label of document.querySelectorAll('.card-body .row > .prompt')) {
    const key = norm(label.textContent);
    const value = norm(label.nextElementSibling ? label.nextElementSibling.textContent : '');
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push([key, value]);
  }
  return out;
}
"""

_NAME_JS = """
() => {
  const norm = s => (s || '').replace(/\\u00a0/g, ' ').replace(/\\s+/g, ' ').trim();
  // Headings on this page are labelled, e.g. "ชื่อนิติบุคคล : บริษัท … จำกัด"
  // and "เลขทะเบียน : 0105532096634". Drop the label, keep the value.
  const value = text => text.replace(/^[^:：]{0,40}[:：]\\s*/, '').trim();

  let id = '', name = '';
  for (const el of document.querySelectorAll('h1, h2, h3, h4, h5, .card-header')) {
    const text = norm(el.textContent);
    if (!text || text.length > 200) continue;
    if (!name && /ชื่อนิติบุคคล/.test(text)) name = value(text);
    if (!id) {
      const m = text.match(/\\b(\\d{13})\\b/);
      if (m) id = m[1];
    }
  }
  if (!name) {
    // No labelled heading — fall back to the first heading that reads like a
    // company name rather than a section title.
    for (const el of document.querySelectorAll('h1, h2, h3, h4')) {
      const text = value(norm(el.textContent));
      if (text.length > 3 && text.length < 200) { name = text; break; }
    }
  }
  return { id, name };
}
"""


def scrape_juristic(page: Page, company_id: str) -> dict[str, str]:
    """Read the ข้อมูลนิติบุคคล card into an ordered {label: value} mapping."""
    bu.find(page, config.JURISTIC_CARD, what="the juristic-data card")
    pairs: list[list[str]] = page.evaluate(_JURISTIC_JS)
    if not pairs:
        bu.dump_debug(page, f"empty-juristic-{company_id}")
        raise RuntimeError(
            "The juristic-data card rendered but held no label/value pairs. "
            "A dump was written to debug/."
        )

    heading: dict[str, str] = page.evaluate(_NAME_JS)
    data: dict[str, str] = {
        "เลขทะเบียนนิติบุคคล": heading.get("id") or company_id,
        "ชื่อนิติบุคคล": heading.get("name", ""),
    }
    data.update({key: value for key, value in pairs})
    print(f"  juristic data: {len(pairs)} fields")
    return data


# --------------------------------------------------------------------------
# Step 3/4 — the financial tab, year and statement
# --------------------------------------------------------------------------
def open_financial(page: Page) -> None:
    """Open ข้อมูลงบการเงิน › งบการเงิน from the tab bar."""
    bu.click_by_text(
        page, config.FINANCE_TAB, config.FINANCE_TAB_TEXT, what="the ข้อมูลงบการเงิน tab"
    )
    bu.click_by_text(
        page,
        config.FINANCE_SUBMENU_ITEM,
        config.FINANCE_SUBMENU_TEXT,
        what=f"the {config.FINANCE_SUBMENU_TEXT} menu item",
    )
    bu.find(page, config.YEAR_SELECT, what="the fiscal-year dropdown")
    print(f"  opened {config.FINANCE_TAB_TEXT} › {config.FINANCE_SUBMENU_TEXT}")


def select_year(page: Page, year: str) -> None:
    """Pick the fiscal year (Buddhist era, e.g. 2568) in เลือกปีงบการเงิน.

    The value is read back: this is a Vue-bound <select> and a change that does
    not stick would silently leave the previous year's numbers on screen.
    """
    select = bu.find(page, config.YEAR_SELECT, what="the fiscal-year dropdown")
    available = [
        (option or "").strip()
        for option in select.evaluate("el => [...el.options].map(o => o.value)")
    ]
    if year not in available:
        raise RuntimeError(
            f"Fiscal year {year} is not offered for this company. "
            f"Available: {', '.join(available) or '(none)'}"
        )

    select.select_option(year)
    page.wait_for_timeout(config.SETTLE_MS)
    if select.input_value().strip() != year:
        raise RuntimeError(f"Fiscal year {year} did not stay selected.")
    print(f"  fiscal year: {year}")


def select_statement(page: Page, statement: str) -> None:
    """Click one of the three finMenu buttons by its Thai label.

    The same call serves งบกำไรขาดทุน, งบแสดงฐานะการเงิน and อัตราส่วนทางการเงิน:
    all three are `span.finMenu` siblings differing only in text, and the table
    they swap in is read by the same layout-agnostic pass below.
    """
    bu.click_by_text(
        page, config.STATEMENT_BUTTON, statement, what=f"the {statement} button"
    )
    # The button that is showing carries .active — confirm the click landed on
    # the one we asked for before trusting the table below it.
    active = page.locator("span.finMenu.active, .finMenu.active").first
    try:
        if active.count() > 0 and statement not in active.inner_text():
            raise RuntimeError(
                f"Clicked {statement!r} but the active statement is "
                f"{active.inner_text().strip()!r}."
            )
    except PlaywrightError:
        pass
    print(f"  statement: {statement}")


# --------------------------------------------------------------------------
# Step 5 — the results table
#
# The three statements do not share a header shape:
#   งบกำไรขาดทุน / งบแสดงฐานะการเงิน — two header rows: a year spanning two
#     columns, then จำนวนเงิน / %เปลี่ยนแปลง under it; one label column
#     ("หน่วย : บาท").
#   อัตราส่วนทางการเงิน — one year per column with no sub-row, two label
#     columns (ลำดับที่ + อัตราส่วน), plus a full-width section row in the header.
# So rather than assume a layout: expand the spans into a grid, find the header
# row carrying the years, treat the columns to its left as labels, and accept a
# sub-label row only when it actually varies across columns (a full-width
# section title repeats, and would otherwise be glued onto every column name).
# --------------------------------------------------------------------------
_TABLE_JS = """
(selectors) => {
  const norm = s => (s || '').replace(/\\u00a0/g, ' ').replace(/\\s+/g, ' ').trim();
  const isYear = s => /^(19|20|25)\\d{2}$/.test((s || '').trim());

  let table = null;
  for (const selector of selectors) {
    for (const el of document.querySelectorAll(selector)) {
      if (el.offsetParent !== null && el.querySelector('tbody tr')) { table = el; break; }
    }
    if (table) break;
  }
  if (!table) return null;

  // Expand rowspan/colspan so every visual column has a value in every row.
  const grid = [];
  [...table.querySelectorAll('thead tr')].forEach((tr, r) => {
    let c = 0;
    for (const cell of tr.children) {
      while (grid[r] && grid[r][c] !== undefined) c++;
      const text = norm(cell.textContent);
      const rowspan = parseInt(cell.getAttribute('rowspan') || '1', 10);
      const colspan = parseInt(cell.getAttribute('colspan') || '1', 10);
      for (let dr = 0; dr < rowspan; dr++) {
        for (let dc = 0; dc < colspan; dc++) {
          grid[r + dr] = grid[r + dr] || [];
          grid[r + dr][c + dc] = text;
        }
      }
      c += colspan;
    }
  });
  if (!grid.length) return null;

  const width = Math.max(0, ...grid.map(row => row.length));
  const at = (r, c) => (grid[r] && grid[r][c]) || '';

  // The row with the most year cells is the one naming the fiscal years.
  let yearRow = 0, best = -1;
  grid.forEach((row, r) => {
    const count = row.filter(isYear).length;
    if (count > best) { best = count; yearRow = r; }
  });

  // Data starts at the first year column; everything left of it labels the row.
  let dataStart = 1;
  for (let c = 0; c < width; c++) {
    if (isYear(at(yearRow, c))) { dataStart = c; break; }
  }

  // A sub-label row (จำนวนเงิน / %เปลี่ยนแปลง) only counts if it varies.
  let subs = null;
  for (let r = grid.length - 1; r > yearRow; r--) {
    const values = [];
    for (let c = dataStart; c < width; c++) values.push(at(r, c));
    if (new Set(values).size > 1) { subs = grid[r]; break; }
  }

  const columns = [];
  for (let c = dataStart; c < width; c++) {
    const group = at(yearRow, c);
    const sub = subs ? (subs[c] || '') : '';
    columns.push({ group, sub: sub === group ? '' : sub });
  }

  // Label headers: the first non-empty header text in each label column.
  const labelHeaders = [];
  for (let c = 0; c < dataStart; c++) {
    let text = '';
    for (let r = 0; r < grid.length && !text; r++) text = at(r, c);
    labelHeaders.push(text);
  }

  const rows = [];
  for (const tr of table.querySelectorAll('tbody tr')) {
    const cells = [...tr.children];
    if (!cells.length) continue;
    // Section rows span the whole table and carry no figures — keep the text,
    // and let the writers decide what to do with a row that has no values.
    const labels = cells.slice(0, dataStart).map(td => norm(td.textContent));
    while (labels.length < dataStart) labels.push('');
    rows.push({
      labels,
      values: cells.slice(dataStart).map(td => norm(td.textContent)),
    });
  }

  const titles = [...document.querySelectorAll('.card-title')]
    .map(el => norm(el.textContent))
    .filter(Boolean);

  return { labelHeaders, columns, rows, titles };
}
"""


def scrape_financial_table(page: Page, statement: str) -> dict[str, Any]:
    """Read the statement table into {labelHeaders, columns, rows}."""
    try:
        page.wait_for_selector(
            ", ".join(config.RESULT_TABLE) + " tbody tr",
            timeout=config.DEFAULT_TIMEOUT_MS,
        )
    except PlaywrightError as exc:
        bu.dump_debug(page, "no-financial-table")
        raise RuntimeError(
            f"No {statement} table appeared. The company may not have filed for "
            "the selected year. A dump was written to debug/."
        ) from exc
    page.wait_for_timeout(config.SETTLE_MS)

    table = page.evaluate(_TABLE_JS, config.RESULT_TABLE)
    if not table or not table["rows"]:
        bu.dump_debug(page, "empty-financial-table")
        raise RuntimeError(
            f"The {statement} table rendered but held no rows. "
            "A dump was written to debug/."
        )

    title = next(
        (t for t in table["titles"] if statement in t and "กราฟ" not in t), statement
    )
    table["title"] = title
    print(f"  table: {title} ({len(table['rows'])} rows × {len(table['columns'])} cols)")
    return table


# --------------------------------------------------------------------------
# Number handling
# --------------------------------------------------------------------------
_NUMERIC = re.compile(r"^-?[\d,]+(\.\d+)?$")


def to_number(text: str) -> str:
    """Strip thousands separators so the CSV holds machine-readable numbers.

    A lone '-' means "not reported" on this site (see กำไร(ขาดทุน) ขั้นต้น for
    2564-2565) and becomes an empty cell rather than a zero, which would be a
    different claim. Anything non-numeric is passed through untouched.
    """
    text = (text or "").strip()
    if text in {"", "-", "N/A"}:
        return ""
    stripped = text.replace(",", "")
    return stripped if _NUMERIC.match(text) else text
