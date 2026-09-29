"""หา TSIC ของนิติบุคคลจาก "เลขทะเบียนนิติบุคคล" โดยตรง ผ่าน Playwright — คู่กับ
amr_mapping.dbd_lookup.lookup_business_type_for_company (Selenium, ค้นด้วยชื่อบริษัท) แต่ใช้
กลไกคนละแบบเพราะค้นด้วยเลขทะเบียนต้องพึ่งกล่องค้นหา+autocomplete บนหน้าเว็บจริง (ดู docstring
หัวแพ็กเกจ __init__.py และ scraper.search_company สำหรับรายละเอียด)

หลักการ: เข้าหน้าแรก → พิมพ์เลขทะเบียนในกล่องค้นหา → เลือกจาก autocomplete (หรือกด Enter/เข้า URL
โปรไฟล์ตรงๆ เป็นสำรอง) → อ่านการ์ด "ข้อมูลนิติบุคคล" (scraper.scrape_juristic) ได้ชื่อ/ประเภท/
สถานะนิติบุคคล จากนั้นหารหัส TSIC จากการ์ด "ประเภทธุรกิจที่ส่งงบการเงินปีล่าสุด" เท่านั้น (สะท้อน
กิจกรรมปัจจุบันของบริษัทมากกว่าการ์ด "ตอนจดทะเบียน" ที่อาจเก่ากว่ามาก — ไม่อ่านการ์ดนั้นเข้ามาเป็น
ตัวเลือกเลยตามที่ผู้ใช้ยืนยันชัดเจน ดู _build_candidates) fallback ไปใช้ "ตอนจดทะเบียน" เฉพาะตอน
หาการ์ด "ปีล่าสุด" ไม่เจอเลยจริงๆ (บริษัทตั้งใหม่ยังไม่เคยส่งงบการเงิน)

⚠️ ข้อสังเกตสำคัญเรื่องจริยธรรม/นโยบายของโปรเจกต์: โมดูลนี้ปลอม navigator.webdriver และคุณสมบัติ
อื่นๆ ของเบราว์เซอร์ (ดู config.STEALTH_JS) เพื่อผ่านระบบป้องกันบอท (Incapsula) ของเว็บ DBD —
ตรงข้ามกับหลักการที่ dbd_lookup.py (โมดูลเดิม) ประกาศไว้ชัดเจนว่า "ไม่พยายามหลีกเลี่ยง/ปลอมตัวให้
พ้นการตรวจจับนี้เด็ดขาด" ใช้ตรงนี้เพราะผู้ใช้ยืนยันจากการทดสอบจริงว่าจำเป็น (ค้นด้วยเลขทะเบียนแบบ
ไม่ปลอมตัวโดนบล็อกเกือบทุกครั้ง) และเป็นการดึงข้อมูลทะเบียนธุรกิจสาธารณะ ไม่ใช่ข้อมูลส่วนตัว/ต้อง
login ในอัตราที่มีการหน่วงเวลาให้เหมาะสม (DELAY_BETWEEN_COMPANIES_MS) ไม่ใช่การโจมตี/ดึงข้อมูล
จำนวนมหาศาล — แต่ก็ยังเป็นการปลอมตัวเพื่อเลี่ยงมาตรการที่เว็บตั้งใจทำขึ้นจริง ถ้าจะปิดการปลอมตัวนี้
(เช่น กังวลเรื่องข้อกำหนดการใช้งาน/robots.txt ของ DBD) ต้องแก้ config.STEALTH_JS/CHROME_CHANNEL
เอง — ไม่ใช่แค่ปิดสวิตช์เดียว

รองรับเฉพาะกรณี headless ต้องมี Google Chrome ตัวจริงติดตั้งอยู่ (channel="chrome" ใน
config.CHROME_CHANNEL) — Playwright's เบราว์เซอร์ Chromium ที่ bundle มาเองใช้ไม่ได้ (ยืนยันจากการ
ทดสอบจริงของผู้ใช้ว่ายังโดนบล็อกอยู่แม้จะปลอมตัวแล้วก็ตาม)
"""

from __future__ import annotations

import re
from typing import Callable, List, Optional, Tuple

from ..dbd_lookup import BlockedByAntiBot, CompanyBusinessInfo
from . import config
from . import scraper
from .browser_utils import ElementNotFound

ProgressCallback = Callable[[str], None]


def _noop(_: str) -> None:
    pass


# คำ/วลีที่บ่งชี้ว่าเว็บบล็อกการเข้าถึงอัตโนมัติ — เหมือนกับที่ dbd_lookup.py ใช้ (Selenium) เผื่อ
# Incapsula ยังหลุดผ่านการปลอมตัวมาบล็อกได้บางครั้ง (ยังไม่เคยพบจากการทดสอบของผู้ใช้ แต่เช็คไว้กันเหนียว)
_BLOCK_INDICATORS = ("incapsula", "request unsuccessful", "access denied", "are you a robot", "captcha")

_HEADER_LATEST_FINANCIAL_STATEMENT = "ประเภทธุรกิจที่ส่งงบการเงินปีล่าสุด"
_HEADER_AT_REGISTRATION = "ประเภทธุรกิจตอนจดทะเบียน"


def _extract_tsic_after_header(text: str, header: str, next_header: Optional[str] = None) -> Optional[Tuple[str, str]]:
    """หารหัส+ชื่อ TSIC (บรรทัด "ประเภทธุรกิจ" ตามด้วยรหัส 5 หลัก + ชื่อ) ในช่วงข้อความหลังหัวข้อ
    header จนถึงก่อน next_header ถัดไป (กันอ่านข้ามโซนผิดถ้ามีหัวข้อ "ประเภทธุรกิจ" ซ้ำกันหลายจุด
    ในหน้าเดียว) คืน (code, name) หรือ None ถ้าไม่เจอ header หรือไม่เจอรหัสในช่วงนั้นเลย"""

    start = text.find(header)
    if start == -1:
        return None
    segment_end = -1
    if next_header:
        segment_end = text.find(next_header, start + len(header))
    segment = text[start:segment_end] if segment_end != -1 else text[start : start + 600]

    m = re.search(r"ประเภทธุรกิจ\s*\n?\s*(\d{5})\s+(.+)", segment)
    if not m:
        return None
    return m.group(1), m.group(2).strip()


def _extract_tsic_from_juristic_dict(data: dict) -> List[Tuple[str, str, str]]:
    """เผื่อการ์ด "ข้อมูลนิติบุคคล" (scraper.scrape_juristic อ่านด้วย .prompt selector ที่ยืนยัน
    โครงสร้างแล้วจริง) มีคีย์ที่เป็นรหัส TSIC ปนอยู่ด้วย (ไม่ทราบแน่ชัดว่าการ์ดประเภทธุรกิจ 2 การ์ด
    ใช้โครงสร้าง .prompt เดียวกันหรือคนละแบบ — เช็คทางนี้ก่อนเพราะน่าเชื่อถือกว่าถ้ามีจริง) คืน
    [(code, name, key), ...] ของทุกคีย์ที่มีคำว่า "ประเภทธุรกิจ" อยู่และค่าขึ้นต้นด้วยรหัส 5 หลัก"""

    found = []
    for key, value in data.items():
        if "ประเภทธุรกิจ" not in key:
            continue
        m = re.match(r"\s*(\d{5})\s+(.+)", value or "")
        if m:
            found.append((m.group(1), m.group(2).strip(), key))
    return found


def _build_candidates(
    registration_no: str, juristic: dict, body_text: str, log: ProgressCallback
) -> List[CompanyBusinessInfo]:
    """อ่านรหัส TSIC จากการ์ด "ประเภทธุรกิจที่ส่งงบการเงินปีล่าสุด" เท่านั้น (สะท้อนกิจกรรมปัจจุบัน
    ของบริษัทมากกว่า "ตอนจดทะเบียน" ที่อาจเก่ากว่ามาก — ยืนยันตามที่ผู้ใช้ต้องการชัดเจน) — เคยลอง
    คืนทั้งสองค่าเป็น candidate แยกกันแล้วให้ web/app.py เลือก "ปีล่าสุด" เป็นตัวหลักแทน แต่ยังเจอ
    เคสจริงที่ตัว "ตอนจดทะเบียน" หลุดมาเป็นตัวที่ใช้อยู่ดี (โครงสร้างหน้าเว็บจริงไม่ตรงกับที่คาดไว้
    เป๊ะทุกกรณี) ตัดความกำกวมทั้งหมดด้วยการไม่อ่าน "ตอนจดทะเบียน" เข้ามาเป็นตัวเลือกเลยง่ายกว่า —
    fallback ไปใช้ "ตอนจดทะเบียน" เฉพาะตอนหาการ์ด "ปีล่าสุด" ไม่เจอเลยจริงๆ (เช่น บริษัทตั้งใหม่ยัง
    ไม่เคยส่งงบการเงินเลย จึงไม่มีการ์ดนี้ให้อ่าน)"""

    juristic_name = juristic.get("ชื่อนิติบุคคล") or ""
    juristic_type = juristic.get("ประเภทนิติบุคคล") or ""
    status = juristic.get("สถานะนิติบุคคล") or ""

    from_dict = _extract_tsic_from_juristic_dict(juristic)
    latest_entry = next((e for e in from_dict if _HEADER_LATEST_FINANCIAL_STATEMENT in e[2]), None)
    registered_entry = next((e for e in from_dict if _HEADER_AT_REGISTRATION in e[2]), None)

    if latest_entry is None and registered_entry is None:
        if len(from_dict) == 1:
            # หน้านี้ไม่มีการ์ด "ประเภทธุรกิจ" 2 ใบ (label ไม่ได้ถูกเปลี่ยนเป็นหัวข้อการ์ดโดย
            # scraper.py's _JURISTIC_JS เพราะไม่ชนกัน) — ใช้ค่าเดียวที่มีได้เลย ไม่ต้องเดาว่าเป็น
            # "ปีล่าสุด" หรือ "ตอนจดทะเบียน" (ไม่มีข้อมูลพอจะแยก แต่ก็ไม่มีความกำกวมให้เลือกผิดด้วย)
            code, name, _key = from_dict[0]
            log(f"✅ อ่านข้อมูลสำเร็จ: {juristic_name} — TSIC {code}")
            return [
                CompanyBusinessInfo(
                    registration_no=registration_no, juristic_name=juristic_name,
                    juristic_type=juristic_type, status=status, tsic_code=code, tsic_name_th=name,
                )
            ]
        # จากข้อความทั้งหน้าแทน (fallback เดียวกับตอนการ์ด "ข้อมูลนิติบุคคล" ไม่มีคีย์ TSIC ปนอยู่เลย)
        latest = _extract_tsic_after_header(body_text, _HEADER_LATEST_FINANCIAL_STATEMENT)
        registered = _extract_tsic_after_header(
            body_text, _HEADER_AT_REGISTRATION, next_header=_HEADER_LATEST_FINANCIAL_STATEMENT
        )
        latest_entry = (latest[0], latest[1], _HEADER_LATEST_FINANCIAL_STATEMENT) if latest else None
        registered_entry = (registered[0], registered[1], _HEADER_AT_REGISTRATION) if registered else None

    if latest_entry is not None:
        code, name, _key = latest_entry
        label = "ตามงบการเงินปีล่าสุด"
    elif registered_entry is not None:
        code, name, _key = registered_entry
        label = "ตอนจดทะเบียน (ยังไม่พบข้อมูลงบการเงินรอบล่าสุด)"
        log("ℹ️ ไม่พบการ์ด 'ประเภทธุรกิจที่ส่งงบการเงินปีล่าสุด' — ใช้ 'ตอนจดทะเบียน' แทน")
    else:
        code = name = None
        label = ""

    if code is None:
        log("⚠️ พบหน้าบริษัทแต่อ่านรหัส TSIC ไม่สำเร็จ (โครงสร้างหน้าอาจเปลี่ยนไป จาก dbd_scraper ที่ยืนยันไว้ล่าสุด)")
        return []

    log(f"✅ อ่านข้อมูลสำเร็จ: {juristic_name} — TSIC {code} ({label})")
    return [
        CompanyBusinessInfo(
            registration_no=registration_no,
            juristic_name=juristic_name,
            juristic_type=juristic_type,
            status=status,
            tsic_code=code,
            tsic_name_th=f"({label}) {name}",
        )
    ]


def _launch(playwright, headless: bool):
    """เปิดเบราว์เซอร์ตามที่ผู้ใช้ยืนยันไว้เดิม (ดู README.md/config.py หัวข้อ "Bot protection" —
    ตารางผลทดสอบจริงกับเว็บจริง):
        bundled Chromium, headless        → บล็อก (403)
        bundled Chromium, headed          → ผ่าน (ไม่ต้องปลอมตัวเลย)
        Google Chrome ตัวจริง (channel="chrome"), headless + stealth → ผ่าน

    ⚠️ กลับไปใช้ Chromium ธรรมดา (ไม่ระบุ channel) สำหรับโหมด headed แล้ว — เคยลองเปลี่ยนไปใช้
    channel="chrome" ทั้ง 2 โหมดเพื่อเลี่ยงต้องดาวน์โหลด Chromium เพิ่ม แต่ยืนยันจากผู้ใช้จริงว่าโดน
    Imperva บล็อก (Error 15) ทั้งที่เป็น headed! บ่งชี้ว่า Google Chrome ตัวจริงที่ขับผ่าน CDP protocol
    ของ Playwright ทิ้งร่องรอยอัตโนมัติที่ตรวจจับได้มากกว่า Chromium ที่ Playwright bundle มาเอง
    (ซึ่งถูก patch มาให้ automation-artifact น้อยกว่าโดยเฉพาะ) — ต้องรัน `playwright install
    chromium` (หรือ `playwright install` เฉยๆ) เพิ่มเติมจาก `playwright install chrome` เดิม
    เพื่อให้โหมด headed นี้ใช้ได้"""

    if headless:
        browser = playwright.chromium.launch(
            channel=config.CHROME_CHANNEL, headless=True, args=config.HEADLESS_ARGS
        )
    else:
        browser = playwright.chromium.launch(headless=False, args=config.LAUNCH_ARGS)

    context = browser.new_context(user_agent=config.USER_AGENT, locale="th-TH")
    context.add_init_script(config.STEALTH_JS)
    return browser, context


def lookup_tsic_by_registration_no(
    registration_no: str,
    log: ProgressCallback = _noop,
    headless: bool = True,
    on_blocked: Optional[Callable[[], None]] = None,
) -> List[CompanyBusinessInfo]:
    """entry point ที่ web/app.py เรียก — เปิดเบราว์เซอร์ใหม่ทุกครั้ง ค้นหาด้วยเลขทะเบียน แล้วปิด
    เบราว์เซอร์ทิ้งเสมอไม่ว่าจะสำเร็จหรือพัง คืน [] (ไม่ raise) เมื่อไม่พบบริษัทนี้/หา TSIC ไม่ได้
    เลย — raise BlockedByAntiBot ถ้าตรวจพบข้อความของระบบป้องกันบอทแม้จะปลอมตัวแล้วก็ตาม (ยังไม่เคย
    เกิดขึ้นจากการทดสอบของผู้ใช้ แต่เช็คไว้กันเหนียว เหมือน dbd_lookup.py เดิม)

    on_blocked (ไม่บังคับ) — ถ้าลองผ่านหน้าบล็อกของ Incapsula อัตโนมัติหมดโควตาแล้วยังไม่ผ่าน จะ
    เรียก callback นี้ (ดู scraper._reload_if_blocked) ซึ่งต้อง "block จนกว่าจะมีคนคลิก reload เอง
    ในหน้าต่างเบราว์เซอร์จริงด้วยมือจริงๆ" (วิธีเดียวที่ยืนยันแล้วว่าผ่านได้ทุกครั้ง ต่างจากการ
    reload/กด F5 ผ่านโค้ด) — ใช้ได้จริงเฉพาะตอน headless=False (มีหน้าต่างให้คลิกจริง) เท่านั้น
    scripts/lookup_tsic.py ส่ง callback ที่ print+input() รอกด Enter ใน terminal ส่วน web/app.py
    ส่ง callback ที่ตั้งสถานะ job ให้หน้าเว็บโชว์ปุ่มยืนยัน แล้วรอ threading.Event ที่ endpoint ของ
    ปุ่มนั้นเป็นคน set() ให้แทน — ไม่ส่ง (None ค่าเริ่มต้น) แปลว่าไม่มีทางให้คนช่วยเลย ปล่อยผ่านไป
    เงียบๆ ถ้ายังโดนบล็อกอยู่หลังลองอัตโนมัติครบ (เช่น ตอนเปิดเบราว์เซอร์แบบ headless)

    ⚠️ ต้องรันในเครื่องที่ติดตั้ง Playwright + Google Chrome จริง (ดู docstring หัวไฟล์นี้) —
    ใช้งานไม่ได้ในสภาพแวดล้อมที่ไม่มีเบราว์เซอร์จริง/ไม่มี network ออกไปเว็บภายนอกได้"""

    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    normalized = registration_no.strip()
    log(f"🔍 เปิดเว็บ DBD DataWarehouse ค้นหาเลขทะเบียน: {normalized}")

    with sync_playwright() as p:
        log("🌐 กำลังเปิดเบราว์เซอร์...")
        browser, context = _launch(p, headless)
        log("✅ เปิดเบราว์เซอร์แล้ว กำลังโหลดหน้าแรก...")
        try:
            page = context.new_page()
            try:
                scraper.search_company(page, normalized, on_still_blocked=on_blocked)
            except scraper.OverlayBlocked as e:
                log(f"⚠️ {e}")
                return []
            except ElementNotFound as e:
                log(f"⚠️ ไม่พบหน้าบริษัทของเลขทะเบียน '{normalized}': {e}")
                return []

            body_text = page.inner_text("body")
            lowered = body_text.lower()
            if any(indicator in lowered for indicator in _BLOCK_INDICATORS):
                log("🚫 เว็บ DBD บล็อกการเข้าถึงอัตโนมัติ (ตรวจพบข้อความของระบบป้องกันบอท แม้จะปลอมตัวแล้วก็ตาม)")
                raise BlockedByAntiBot(" ".join(body_text.split())[:300])

            try:
                juristic = scraper.scrape_juristic(page, normalized)
            except RuntimeError as e:
                log(f"⚠️ อ่านข้อมูลนิติบุคคลไม่สำเร็จ: {e}")
                return []

            return _build_candidates(normalized, juristic, body_text, log)
        except PlaywrightError as e:
            log(f"⚠️ เกิดข้อผิดพลาดระหว่างเปิดเว็บ: {e}")
            return []
        finally:
            browser.close()
