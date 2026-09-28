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
from typing import Any, Callable, Optional

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from . import browser_utils as bu
from . import config
from .browser_utils import ElementNotFound

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


# คำ/วลีที่บ่งชี้ว่าโดนหน้า Access Denied ของ Imperva (ไม่ใช่แค่ "ยังไม่พบผลลัพธ์" ธรรมดา) — เช็ค
# แบบ case-insensitive
_BLOCK_INDICATORS = ("access denied", "request unsuccessful", "incapsula", "powered by imperva", "are you a robot")


def _simulate_mouse_activity(page: Page, duration_ms: int) -> None:
    """ขยับเมาส์ไปมาแบบสุ่มระหว่างรอ (ใช้ page.mouse ซึ่งส่งผ่าน CDP เป็น input event จริง
    isTrusted=true เหมือนคนใช้เมาส์จริงๆ — ต่างจาก JS synthetic event ที่หน้าเว็บตรวจจับได้ว่าไม่จริง)

    ยืนยันจากผู้ใช้จริง: คลิก reload เองด้วยมือผ่านหน้าบล็อกของ Incapsula ได้ทันที แต่โค้ดสั่ง
    page.reload() (แม้รอเวลาเท่ากัน) ไม่ผ่าน — บ่งชี้ว่า Incapsula (ที่ใช้ behavioral fingerprinting
    เป็นส่วนหนึ่งของการตรวจจับบอทอยู่แล้ว) น่าจะเช็ค "มีการขยับเมาส์จริงไหม" ไม่ใช่แค่เวลาที่ผ่านไป
    เฉยๆ — จึงจำลองการขยับเมาส์แทนการรอเฉยๆ ก่อน reload ทุกรอบ (ยังไม่ยืนยัน 100% ว่าเป็นสาเหตุจริง
    เพราะทดสอบกับเว็บจริงจากตรงนี้ไม่ได้ ต้องให้ผู้ใช้ทดสอบซ้ำ)"""

    import random

    x, y = 400.0, 300.0
    elapsed = 0
    step_ms = 300
    while elapsed < duration_ms:
        x = max(50.0, min(1200.0, x + random.uniform(-80, 80)))
        y = max(50.0, min(800.0, y + random.uniform(-60, 60)))
        try:
            page.mouse.move(x, y, steps=5)
        except PlaywrightError:
            return
        page.wait_for_timeout(step_ms)
        elapsed += step_ms


def _looks_blocked(page: Page, *, poll_ms: int = 3000, interval_ms: int = 500) -> bool:
    """เช็คซ้ำหลายครั้งในช่วงเวลาสั้นๆ (ไม่ใช่เช็คทีเดียวจบ) ว่าหน้าปัจจุบันเป็นหน้า "Access denied"
    ของ Incapsula ไหม — ยืนยันจาก debug dump จริงของผู้ใช้ว่าเช็คครั้งเดียวทันทีหลังโหลดหน้าพลาดได้
    จริง เพราะหน้า Access denied อาจยังโหลด/redirect ไม่เสร็จตอนนั้น (มี JS/redirect เพิ่มอีกขั้น)
    คืน True ทันทีที่เจอ ไม่ต้องรอครบ poll_ms เสมอไป

    บั๊กที่เจอจาก screenshot ของผู้ใช้ (ยังโดนบล็อกอยู่แต่ script พังไปเลยแทนที่จะหยุดถามให้ reload
    เอง): page.inner_text("body") โยน PlaywrightError ได้ตอนหน้ากำลัง reload/เปลี่ยนหน้าพอดี (frame
    detached ชั่วคราว) — เดิมเจอ error แล้วคืน False ทันที (ตีความว่า "ไม่บล็อกแน่นอน") ทั้งที่ความจริง
    แค่ "ยังอ่านไม่ได้ตอนนี้" ทำให้ _reload_if_blocked คิดว่าผ่านแล้ว ข้ามการ reload/prompt ที่เหลือไปเลย
    ทั้งที่จริงยังอยู่หน้า Access denied — แก้โดยถือว่า error ระหว่างอ่านเป็นแค่ "ยังไม่รู้ผล" ให้ poll
    ต่อเหมือนเดิมจนกว่าจะครบ poll_ms แทนที่จะปัดเป็น False ทันที"""

    elapsed = 0
    while True:
        try:
            text = page.inner_text("body").lower()
        except PlaywrightError:
            pass  # หน้ากำลัง transition อยู่พอดี — ยังไม่รู้ผล ไม่ใช่ "ไม่บล็อกแน่นอน" ให้ poll ต่อ
        else:
            if any(indicator in text for indicator in _BLOCK_INDICATORS):
                return True
        if elapsed >= poll_ms:
            return False
        page.wait_for_timeout(interval_ms)
        elapsed += interval_ms


def _reload_if_blocked(
    page: Page, *, max_attempts: int = 3, on_still_blocked: Optional[Callable[[], None]] = None
) -> None:
    """หน้าแรกบางครั้งโดน Imperva บล็อก ("Access denied — Error 15") ตอนโหลดครั้งแรก — ทั่วไปคือ
    Incapsula ทำ JS challenge เบื้องหลังแล้วค่อยปล่อยผ่านตอนโหลดซ้ำ เมื่อ challenge ทำงานเสร็จ (ตั้ง
    cookie ยืนยันแล้ว) แต่ challenge อาจใช้เวลาไม่เท่ากันทุกครั้ง — reload ครั้งเดียวทันทีอาจยังไม่พอ
    (challenge ยังไม่ทันเสร็จ) จึงลองซ้ำได้ถึง max_attempts ครั้ง โดยจำลองการขยับเมาส์ระหว่างรอ (ดู
    _simulate_mouse_activity) แทนการรอเฉยๆ ก่อน reload แต่ละรอบ เงียบๆ ถ้าไม่เจอหน้าบล็อกเลย

    กด F5 จำลอง (page.keyboard.press) แทนเรียก page.reload() ตรงๆ เพราะ page.reload() (คำสั่ง
    ควบคุมเบราว์เซอร์ผ่าน CDP โดยตรง ไม่ผ่าน input event เลย) ยืนยันจากผู้ใช้จริงว่าไม่ผ่าน — แต่
    ถึงกด F5 จำลองแล้วก็ยังไม่ผ่านอีก ทั้งที่คลิกปุ่ม reload ในเบราว์เซอร์เองด้วยมือผ่านทันทีทุกครั้ง
    บ่งชี้ว่า Incapsula อาจตรวจจับการเชื่อมต่อ CDP ของ Playwright เองได้เลย ไม่ว่าจะจำลอง input
    event แบบไหนก็ตาม (ไม่ใช่แค่เรื่อง "input event จริงหรือปลอม" อย่างที่คาดไว้แต่แรก)

    ใช้ wait_until="networkidle" ตอนกด F5/reload (ผูก timeout สั้นแค่ 15s ไม่ใช่ DEFAULT_TIMEOUT_MS
    45s) — ยืนยันจากวิดีโอทดสอบจริงของผู้ใช้ว่ารอบที่ใช้ networkidle ผ่านหน้าบล็อกของ Incapsula ได้
    จริง (เห็น TSIC ออกมา) ส่วนรอบที่เปลี่ยนไปใช้ domcontentloaded (กลัว networkidle ค้างเพราะหน้า
    challenge อาจมี background polling ตลอดเวลา) กลับยังโดนบล็อกอยู่เหมือนเดิม — เดาว่า
    domcontentloaded fire เร็วเกินไปจนเช็คบล็อกก่อนหน้า/cookie ของ Incapsula ตั้งเสร็จ ส่วนความกลัว
    เรื่องค้างไม่จบ แก้ด้วยการผูก timeout สั้นแทน (ไม่ใช่เลิกใช้ networkidle ไปเลย) — timeout แล้ว
    fallback ไป domcontentloaded ธรรมดา

    on_still_blocked (ไม่บังคับ) — ถ้าลองอัตโนมัติครบ max_attempts รอบแล้วยังโดนบล็อกอยู่ จะเรียก
    callback นี้ซ้ำไปเรื่อยๆ (เช็คบล็อกก่อนเรียกทุกครั้ง) จนกว่าจะไม่โดนบล็อกแล้ว — ตัว callback เอง
    ต้อง "block จนกว่าจะมีคนคลิก reload เองในหน้าต่างเบราว์เซอร์จริงด้วยมือจริงๆ" (วิธีเดียวที่ยืนยัน
    แล้วว่าผ่านได้ทุกครั้ง) เช่น scripts/lookup_tsic.py ส่ง callback ที่ print+input() รอกด Enter ใน
    terminal ส่วน web/app.py ส่ง callback ที่ตั้งสถานะ job แล้วรอ threading.Event ที่ปุ่มยืนยันใน
    หน้าเว็บเป็นคน set() ให้ — ไม่ส่ง (None ค่าเริ่มต้น) แปลว่าไม่มีทางให้คนช่วยเลย คืนเงียบๆ ทันที
    (เช่น ตอนเปิดเบราว์เซอร์แบบ headless ที่ไม่มีหน้าต่างให้คลิก)"""

    for attempt in range(max_attempts):
        if not _looks_blocked(page):
            return

        print(f"  ⚠️ เจอหน้าบล็อกของ Incapsula — กำลังลอง reload อัตโนมัติ (รอบที่ {attempt + 1}/{max_attempts})...")
        wait_ms = config.SETTLE_MS * (attempt + 3)  # รอนานขึ้นเรื่อยๆ ทุกรอบ (2.1s, 2.8s, 3.5s ที่ SETTLE_MS=700)
        _simulate_mouse_activity(page, wait_ms)
        try:
            # networkidle (ไม่ใช่ domcontentloaded) เพื่อรอให้ challenge/redirect ของ Incapsula
            # settle ก่อนค่อยเช็คซ้ำ — วิดีโอทดสอบจริงยืนยันว่ารันครั้งที่ใช้ networkidle ผ่านได้
            # จริง ส่วนรันที่เปลี่ยนกลับไป domcontentloaded ยังโดนบล็อกอยู่ แต่ผูก timeout สั้นไว้
            # (15s ไม่ใช่ DEFAULT_TIMEOUT_MS 45s) เผื่อหน้าบล็อกมี background polling ค้างตลอดจน
            # networkidle ไม่มีวันเกิด — timeout แล้ว fallback ไป domcontentloaded ธรรมดาแทน
            with page.expect_navigation(wait_until="networkidle", timeout=15_000):
                page.keyboard.press("F5")
        except PlaywrightError:
            try:
                page.reload(wait_until="domcontentloaded")
            except PlaywrightError:
                return
        page.wait_for_timeout(config.SETTLE_MS)

    while on_still_blocked is not None:
        if not _looks_blocked(page):
            return
        on_still_blocked()
        page.wait_for_timeout(500)


# --------------------------------------------------------------------------
# Step 1 — search
# --------------------------------------------------------------------------
def search_company(
    page: Page, company_id: str, *, on_still_blocked: Optional[Callable[[], None]] = None
) -> None:
    """Land on the company's page.

    For a 13-digit registration id (this package's whole use case) goes
    straight to the profile URL — one navigation, no search box, no
    autocomplete. Only when that guessed URL does not land on a company page
    (or the id was not a registration number, e.g. a bare name) does it fall
    back to the home search bar: type into the box, click the autocomplete
    entry if one opens, or press Enter to submit if it does not.

    on_still_blocked — ดู _reload_if_blocked
    """
    if _IS_REGISTRATION_ID.match(company_id):
        # เลขทะเบียน 13 หลัก: ไปที่ URL โปรไฟล์ตรงๆ (PROFILE_URL) ก่อนเสมอ แทนที่จะพึ่งกล่องค้นหา +
        # autocomplete ของหน้าแรก — README เดิมของผู้ใช้เองยืนยันไว้แล้วว่า autocomplete "ไม่เปิดเลย
        # สำหรับ input ที่พิมพ์ผ่าน automation" (กด Enter ไปหน้าผลลัพธ์เป็นทางเดียวที่ได้ผลจริง) และ
        # PROFILE_URL ก็ยืนยันใช้งานได้จริงแล้ว (เป็น fallback เดิมที่เคยผ่าน, ตรงกับ URL ที่ผู้ใช้เดิน
        # ด้วยมือเองก็ลงเอยที่รูปแบบเดียวกันนี้) — พิมพ์+คลิก suggestion/กด Enter บนหน้าแรกมีหลายขั้น
        # ตอนกว่า แต่ละขั้นเป็นจุดที่พลาด/ถูกตรวจจับได้เพิ่ม ไปตรงๆ ครั้งเดียวจึงน่าเชื่อถือกว่า แล้ว
        # ค่อย fallback ไปกล่องค้นหาของหน้าแรกถ้าทางตรงไม่ได้ผล (เช่น entity ไม่ใช่บริษัทจำกัด ที่
        # prefix "5" ยังไม่เคยยืนยันว่าใช้ได้กับทุกประเภท)
        url = config.PROFILE_URL.format(company_id=company_id)
        print(f"  ลองเปิดโปรไฟล์ตรงๆ ที่ {url} ...")
        try:
            page.goto(url, wait_until="networkidle", timeout=15_000)
        except PlaywrightError:
            pass
        page.wait_for_timeout(config.SETTLE_MS)
        _reload_if_blocked(page, on_still_blocked=on_still_blocked)
        if _on_company_page(page):
            _wait_for_company_page(page, company_id)
            print(f"  opened {page.url}")
            return
        print("  ไปตรงๆ ไม่ถึงหน้าบริษัท — ลองผ่านกล่องค้นหาของหน้าแรกแทน")

    # ยืนยันจาก debug dump จริงของผู้ใช้: ตอนโดนบล็อก หน้า "Access denied" ของ Incapsula ยังไม่ทัน
    # render ตอน domcontentloaded fire (อาจมี redirect/JS เพิ่มอีกขั้น) — เช็คบล็อกครั้งเดียวทันที
    # ตอนนั้นจึงพลาดได้ ใช้ wait_until="networkidle" ให้หน้า/challenge settle ก่อน (วิดีโอทดสอบจริง
    # ยืนยันว่ารอบที่ใช้ networkidle ผ่านได้จริง ส่วนรอบที่เปลี่ยนกลับไป domcontentloaded ยังโดน
    # บล็อกอยู่) แต่ผูก timeout สั้น (15s) กันไว้เผื่อหน้าบล็อกมี background polling ค้างตลอดจน
    # networkidle ไม่มีวันเกิด — timeout แล้วไปต่อเลย (หน้าก็ navigate ไปแล้วจริง แค่ wait ไม่ทัน)
    # แทนที่จะรอค้างไม่จบ แล้วให้ _reload_if_blocked/_looks_blocked poll เช็คซ้ำอีกชั้นแทน
    try:
        page.goto(config.BASE_URL, wait_until="networkidle", timeout=15_000)
    except PlaywrightError:
        pass
    page.wait_for_timeout(config.SETTLE_MS)
    print("  หน้าแรกโหลดแล้ว กำลังเช็คว่าโดนบล็อกไหม...")
    _reload_if_blocked(page, on_still_blocked=on_still_blocked)
    dismiss_overlays(page)

    try:
        box = bu.find(page, config.SEARCH_INPUT, what="the home search box")
    except ElementNotFound:
        # ยืนยันจาก debug dump จริงของผู้ใช้อีกครั้ง: หน้าบล็อกของ Incapsula บางครั้ง render ช้ากว่า
        # 3 วินาทีที่ initial check ด้านบนรอ (challenge/scoring ของ Incapsula เอง) — ตอนนั้นเลยยัง
        # ไม่เจอ แต่ bu.find เพิ่งรอไปนานสุดถึง 45s (DEFAULT_TIMEOUT_MS) หาช่องค้นหาไม่เจอ ซึ่งนานพอ
        # ที่หน้าบล็อกจะ render จนเห็นผลจริงแล้ว ก่อนจะยอมแพ้เลย เช็คซ้ำอีกทีตรงนี้ — ถ้าเจอบล็อกจริง
        # ตอนนี้ ให้ไล่ reload/interactive prompt อีกรอบ (ดู _reload_if_blocked) แล้วลองหาใหม่อีกครั้ง
        # เดียว ก่อนค่อยยอมแพ้จริงๆ
        if _looks_blocked(page):
            print("  ⚠️ หน้าบล็อกเพิ่งปรากฏช้ากว่าที่เช็คไว้ตอนแรก — ลอง reload อีกรอบ")
            _reload_if_blocked(page, on_still_blocked=on_still_blocked)
            dismiss_overlays(page)
            try:
                box = bu.find(page, config.SEARCH_INPUT, what="the home search box")
            except ElementNotFound:
                bu.dump_debug(page, f"no-search-box-{company_id}")
                raise
        else:
            # เก็บ screenshot + HTML ไว้ดูว่าตอนพังจริงๆ หน้าตาเป็นยังไง (bu.find เดิมไม่เคยเก็บตรงนี้
            # ไว้เลย ข้อความ error แค่บอกให้ไปดู debug/ เฉยๆ ทั้งที่ไม่เคยมีไฟล์ให้ดูจริง) — ช่วยแยกให้
            # ชัดว่าติดหน้า Incapsula ที่ _BLOCK_INDICATORS ยังไม่ครอบคลุม หรือเป็นปัญหาอื่นไปเลย
            bu.dump_debug(page, f"no-search-box-{company_id}")
            raise
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
