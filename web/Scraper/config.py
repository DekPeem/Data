"""Configuration for the DBD DataWarehouse scraper.

Everything site-specific lives here. The site is a Vue SPA with no iframes and
no login, so all we need are selectors and the Thai labels used for navigation.

Selectors marked CONFIRMED were taken from the saved markup in html_source/;
the rest are fallbacks tried in order, so a class rename does not break the run.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


# --------------------------------------------------------------------------
# Site
# --------------------------------------------------------------------------
BASE_URL = os.getenv("DBD_BASE_URL", "https://datawarehouse.dbd.go.th/")

# The juristic-person page. CONFIRMED live: /company/profile/5<id> — note the
# leading 5 glued to the registration id (…/profile/50105532096634); the same
# path with a slash after the 5 returns 404. That prefix looks like an entity
# category and has only been verified for บริษัทจำกัด, so this stays a
# fallback: the search box is the path that works for any entity type.
PROFILE_URL = BASE_URL.rstrip("/") + "/company/profile/5{company_id}"


# --------------------------------------------------------------------------
# Bot protection
#
# The site sits behind Imperva. Plain headless Chromium is answered with a 403
# bot-block page (an #main-iframe pointing at /_Incapsula_Resource). What does
# get served, CONFIRMED by trial:
#   * headed Chromium — works as-is, no disguise needed
#   * real Google Chrome in --headless=new, with a desktop UA and the automation
#     giveaways below patched out
# Bundled Chromium in --headless=new is still blocked, so headless mode needs
# the "chrome" channel — i.e. Google Chrome installed locally.
# --------------------------------------------------------------------------
CHROME_CHANNEL = os.getenv("DBD_CHROME_CHANNEL", "chrome")

LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled"]
HEADLESS_ARGS = LAUNCH_ARGS + ["--headless=new"]

USER_AGENT = os.getenv(
    "DBD_USER_AGENT",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
)

# Runs before any page script. navigator.webdriver is the headline tell; the
# rest are the properties a real Chrome has and a bare automation build lacks.
STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = window.chrome || { runtime: {} };
Object.defineProperty(navigator, 'languages', { get: () => ['th-TH', 'th', 'en-US'] });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
"""


# --------------------------------------------------------------------------
# Overlays shown on first load
#
# CONFIRMED: #warningModal (a scam warning) opens over the home page and eats
# every click until dismissed via its ปิด button, #btnWarning. The cookie
# banner is bundled too, so its accept button is dismissed the same way.
# --------------------------------------------------------------------------
OVERLAY_DISMISS = [
    "#btnWarning",
    "#warningModal .modal-footer button",
    ".modal.show [data-bs-dismiss='modal']",
    ".modal.show .btn-close",
    "[class*='cookie'] button.btn-primary",
    "[class*='cookie'] button",
]

# How long to wait for a first-load overlay to actually render before deciding
# there is nothing to dismiss. The scam warning appears a beat after the page
# does, and on a slower/further host that beat can land after the fixed settle
# — so dismissing once and returning left the modal to pop up over the search
# box and eat the click. Bounded, and skipped the moment an overlay is seen.
OVERLAY_WAIT_MS = int(os.getenv("DBD_OVERLAY_WAIT_MS", "6000"))


# --------------------------------------------------------------------------
# Step 1 — the home search bar (html_source/search_bar.html)
# --------------------------------------------------------------------------
SEARCH_INPUT = [
    ".search-container input.form-control",
    "input[placeholder*='ค้นหาด้วยชื่อ']",
    "form.search input.form-control",
    "input.form-control",
]

# Autocomplete list that opens under the box while typing. Its <li> entries are
# the only reliable way in: pressing Enter goes to a results page whose layout
# differs between a name search and an id search.
SUGGESTION_ITEM = [
    "#suggestionContent li",
    "ul.dropdown-menu.search li",
]

SEARCH_ICON = ["#searchicon", ".icon-search"]


# --------------------------------------------------------------------------
# Step 2 — the juristic-data tab (html_source/juristic_data.html)
#
# Label/value pairs live in a .card-body .row as alternating columns:
#   <div class="col-6 bold prompt">ประเภทนิติบุคคล</div><div class="col-6">…</div>
# so the label carries .prompt and the value is simply the element after it.
# --------------------------------------------------------------------------
JURISTIC_CARD = [
    ".card-body .row",
    ".card-body",
]
JURISTIC_LABEL_CLASS = "prompt"

# Best-effort handles for the company name shown above the card.
COMPANY_NAME = [
    ".company-name",
    ".card-header h4",
    ".page-content h4",
    "h4",
    "h3",
]


# --------------------------------------------------------------------------
# Step 3 — the ข้อมูลงบการเงิน navbar tab (html_source/navbar.html)
#
# CONFIRMED: <span id="menu2" class="tab2"><span>ข้อมูลงบการเงิน</span></span>
# inside a .dropdown <li>, whose menu holds ภาพรวมผลประกอบการ / งบการเงิน /
# ประวัติการส่งงบการเงิน. งบการเงิน is the one carrying the year picker and the
# statement buttons.
# --------------------------------------------------------------------------
FINANCE_TAB = [
    "#menu2",
    ".tab2",
    ".nav-tabs.main .dropdown > a",
]
FINANCE_TAB_TEXT = "ข้อมูลงบการเงิน"
FINANCE_SUBMENU_TEXT = os.getenv("DBD_FINANCE_SUBMENU", "งบการเงิน")
FINANCE_SUBMENU_ITEM = [
    ".nav-tabs.main .dropdown-menu li a",
    ".dropdown-menu li a",
]


# --------------------------------------------------------------------------
# Step 4 — year picker + statement buttons (html_source/financial_table.html)
#
# CONFIRMED: the sidebar card titled เลือกปีงบการเงิน holds a bare
# <select class="form-select"> of Buddhist years, and three
# <span class="btn … finMenu"> buttons; the shown one carries .active.
# --------------------------------------------------------------------------
YEAR_SELECT = [
    ".sidebar .card-infos.filter select.form-select",
    ".card-infos.filter select.form-select",
    ".sidebar select.form-select",
    "select.form-select",
]
STATEMENT_BUTTON = ["span.finMenu", ".finMenu"]

# The three statements the finMenu offers.
STATEMENT_INCOME = "งบกำไรขาดทุน"
STATEMENT_BALANCE = "งบแสดงฐานะการเงิน"
STATEMENT_RATIO = "อัตราส่วนทางการเงิน"
STATEMENTS = [STATEMENT_INCOME, STATEMENT_BALANCE, STATEMENT_RATIO]

# Pulled by default, in this order — all three. They live on the same page
# behind the same year picker, so taking them in one visit costs one extra
# click each rather than a second search + page load. Override with
# DBD_STATEMENTS="งบกำไรขาดทุน,…".
DEFAULT_STATEMENTS = [
    part.strip()
    for part in os.getenv(
        "DBD_STATEMENTS", ",".join(STATEMENTS)
    ).split(",")
    if part.strip()
]


# --------------------------------------------------------------------------
# Step 5 — the results table
#
# CONFIRMED: <table class="table table-hover text-end table-fixed"> with a
# two-row header (years spanning two columns each, then จำนวนเงิน / %เปลี่ยนแปลง)
# and a leading <th class="text-start col-fixed"> naming each line item.
# --------------------------------------------------------------------------
RESULT_TABLE = [
    ".cols.content table.table-fixed",
    ".card-infos table.table-fixed",
    ".table-responsive table",
    "table.table",
]
# The heading above the table, e.g. "งบกำไรขาดทุน ข้อมูลปีงบการเงิน 2564 - 2568".
RESULT_TITLE = [".cols.content .card-title", ".card-infos .card-title", "h5.card-title"]


# --------------------------------------------------------------------------
# Defaults
# --------------------------------------------------------------------------
DEFAULT_COMPANY_ID = os.getenv("DBD_COMPANY_ID", "0105532096634")
DEFAULT_YEAR = os.getenv("DBD_YEAR", "2568")


# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
OUTPUT_DIR = Path(os.getenv("DBD_OUTPUT_DIR", str(BASE_DIR / "output")))
DEBUG_DIR = BASE_DIR / "debug"


# --------------------------------------------------------------------------
# Timing
# --------------------------------------------------------------------------
DEFAULT_TIMEOUT_MS = int(os.getenv("DBD_TIMEOUT_MS", "45000"))
# The SPA swaps content without a navigation, so after each click we wait for
# the expected element rather than for a load event.
SETTLE_MS = int(os.getenv("DBD_SETTLE_MS", "700"))
# Politeness pause between consecutive company lookups in batch mode.
DELAY_BETWEEN_COMPANIES_MS = int(os.getenv("DBD_DELAY_MS", "2000"))
