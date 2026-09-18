"""ค้นหาประเภทธุรกิจของนิติบุคคลจากชื่อบริษัท ผ่านเว็บ dataforthai.com — ใช้เป็น "ตัวสำรอง"
(fallback) เมื่อ dbd_lookup.py (เว็บทางการของกรมพัฒนาธุรกิจการค้าเอง) โดนบล็อกโดยระบบป้องกันบอท
(Incapsula — ยืนยันจากผู้ใช้จริงแล้ว ดู dbd_lookup.BlockedByAntiBot)

dataforthai.com เป็นเว็บบุคคลที่สาม (ไม่ใช่เว็บทางการของ DBD) ที่นำข้อมูลจดทะเบียนธุรกิจ (ข้อมูล
สาธารณะจาก DBD) มาแสดงผลต่ออีกที — ใช้เป็นทางเลือกสำรองเท่านั้น ไม่ใช่แหล่งข้อมูลหลัก

โครงสร้างที่ยืนยันจากผู้ใช้จริงผ่าน DevTools Network tab:
    1. GET https://www.dataforthai.com/api/suggest?q=<คำค้นหา>
       คืน JSON list ของ [{"label": "บริษัท xxx จำกัด", "value": "xxx"}, ...] — รายชื่อบริษัทที่
       ใกล้เคียง (autocomplete) เท่านั้น ไม่มีข้อมูลประเภทธุรกิจ/เลขทะเบียนมาด้วย — เป็น REST API
       ธรรมดาที่เรียกตรงได้เลยไม่ต้องใช้ Selenium (ยืนยันจาก response จริงที่ผู้ใช้ capture มา)
    2. คลิกเลือกชื่อจากรายการนั้นในหน้าเว็บ จะพาไปหน้า https://www.dataforthai.com/company/<เลข
       ทะเบียน>/ ซึ่งมีข้อความ "ประกอบธุรกิจ" / "หมวดธุรกิจ" อยู่ในหน้า (เห็นจาก screenshot จริง)
       — ⚠️ ยืนยันจากผู้ใช้จริงแล้วว่า "ทำแบบนี้ผ่าน Selenium ไม่ได้" หน้า /business ที่เปิดผ่าน
       เบราว์เซอร์อัตโนมัติถูก Cloudflare Turnstile บล็อก (input เดียวที่เจอในหน้าคือ
       cf-turnstile-response ตัว hidden ของ Turnstile เอง ไม่มีช่องค้นหาจริงให้เห็นเลย) — เหมือน
       Incapsula ของ DBD คนละระบบแต่หลักการเดียวกัน โมดูลนี้จึงไม่พยายามข้าม Cloudflare Turnstile
       เช่นกัน (ดูหลักการเดียวกันในหัวไฟล์ dbd_lookup.py) lookup_business_category() จะตรวจจับ
       สัญญาณนี้แล้ว log ให้ชัดเจนว่าโดนบล็อก ไม่ใช่แค่ "หาไม่เจอ" แล้วคืน None เสมอ — ฟีเจอร์ดึง
       "หมวดธุรกิจ" จาก dataforthai.com จึงใช้งานไม่ได้จริงในทางปฏิบัติ เหลือแค่ suggest_companies
       (ข้อ 1 ด้านบน) ที่ยังใช้ยืนยันชื่อบริษัทที่ใกล้เคียง/มีอยู่จริงได้
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Callable, List, Optional
from urllib.parse import quote
from urllib.request import Request, urlopen

from .dbd_lookup import _fallback_search_terms

BASE_URL = "https://www.dataforthai.com"
SUGGEST_URL = f"{BASE_URL}/api/suggest"
BUSINESS_SEARCH_URL = f"{BASE_URL}/business"

ProgressCallback = Callable[[str], None]


def _noop(_: str) -> None:
    pass


@dataclass(frozen=True)
class CompanySuggestion:
    """1 รายการจาก /api/suggest — แค่ชื่อบริษัทที่ใกล้เคียง ยังไม่มีประเภทธุรกิจ"""

    label: str  # ชื่อเต็ม เช่น "บริษัท ซีพี ออลล์ จำกัด (มหาชน)"
    value: str  # ชื่อแบบตัดคำนำหน้า/ต่อท้ายออก เช่น "ซีพี ออลล์"


def suggest_companies(query: str, timeout: float = 10.0, log: ProgressCallback = _noop) -> List[CompanySuggestion]:
    """เรียก /api/suggest?q=... ตรงๆ ด้วย HTTP GET ธรรมดา (ไม่ต้องใช้ Selenium — ยืนยันจาก
    response จริงแล้วว่าเป็น REST API เปิดเผย ไม่มีการเข้ารหัส/ป้องกันบอทแบบ DBD) คืน list ว่าง
    ถ้าไม่มีผลลัพธ์หรือเรียกไม่สำเร็จ (ไม่ raise — endpoint นี้เป็นแค่ตัวช่วยเดาชื่อ ไม่ใช่ผลลัพธ์
    สุดท้าย พังแล้วควรจะข้ามไปเฉยๆ ไม่ทำให้ทั้ง flow ล้ม)

    encode ด้วย safe="()" ให้วงเล็บไม่ถูกแปลงเป็น %28/%29 — ยืนยันจาก URL จริงที่ผู้ใช้ capture
    จาก DevTools ว่าเบราว์เซอร์ (encodeURIComponent ของ JS) ปล่อยวงเล็บไว้แบบนั้นไม่เข้ารหัส
    ต่างจาก Python quote() ปกติที่เข้ารหัสวงเล็บด้วย — เผื่อฝั่งเซิร์ฟเวอร์สนใจความต่างนี้

    ยืนยันจากผู้ใช้จริงว่าลองคำค้นหาสั้นๆ ("ซีพี" คำเดียว ซึ่งเคยเห็นเองในเบราว์เซอร์จริงว่ามี
    suggestion โผล่ขึ้นมาจริง) แล้วยัง "ไม่พบผลลัพธ์" ทุกครั้งจากโค้ดนี้ — ต่างจากตอนพิมพ์ในเบราว์เซอร์
    เอง จึงต้อง log สถานะ/เนื้อหาที่ตอบกลับมาจริงทุกครั้งที่ไม่ได้ผลลัพธ์ตามคาด (คล้าย dbd_lookup ที่
    เจอว่าเป็นเพราะระบบป้องกันบอทมาก่อนแล้ว) แทนที่จะรู้แค่ว่า "ไม่พบ" เฉยๆ โดยไม่รู้สาเหตุ"""

    url = f"{SUGGEST_URL}?q={quote(query, safe='()')}"
    # เพิ่ม Referer/Origin ให้เหมือน request จริงจากเบราว์เซอร์ (AJAX call ที่ยิงจากหน้า /business
    # เสมอ) — ยืนยันจากผู้ใช้จริงว่าคำค้นหาสั้นๆ ที่เคยเห็นเองว่ามี suggestion จริงในเบราว์เซอร์
    # (เช่น "ซีพี") กลับได้ [] ว่างเปล่าทุกครั้งจากโค้ดนี้ (ไม่ error แค่ไม่มีผลลัพธ์) ทั้งที่ URL/
    # การเข้ารหัสตรงกับที่เบราว์เซอร์จริงส่งแล้ว — ความต่างที่เหลือคือ header พวกนี้ที่ request
    # เปล่าๆ แบบนี้ไม่มีติดมาด้วยเหมือนเบราว์เซอร์จริง
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer": BUSINESS_SEARCH_URL,
            "Origin": BASE_URL,
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as resp:
            status = getattr(resp, "status", None)
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001 — เครือข่ายมีปัญหา/เว็บเปลี่ยน format ก็ถือว่าไม่มีผลลัพธ์
        body_snippet = ""
        try:
            body_snippet = e.read().decode("utf-8", errors="replace")[:300]  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 — ไม่ใช่ HTTPError หรืออ่าน body ไม่ได้ ก็แค่ไม่มี snippet
            pass
        log(f"⚠️ เรียก {url} ไม่สำเร็จ: {e}{f' — เนื้อหา: {body_snippet}' if body_snippet else ''}")
        return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log(f"⚠️ {url} ตอบกลับมา (status={status}) แต่ไม่ใช่ JSON ที่ถูกต้อง: {raw[:300]}")
        return []

    if not isinstance(data, list):
        log(f"⚠️ {url} ตอบกลับมาเป็น JSON แต่ไม่ใช่ list ตามที่คาด (status={status}): {raw[:300]}")
        return []

    results = []
    for item in data:
        if isinstance(item, dict) and item.get("label") and item.get("value"):
            results.append(CompanySuggestion(label=str(item["label"]), value=str(item["value"])))

    if not results:
        # parse สำเร็จ (status ปกติ, เป็น list จริง) แต่ไม่มีรายการเลย — ยัง log ไว้ เผื่อ list ว่าง
        # เปล่าๆ ([]) ต่างจาก "หา element/label/value ไม่เจอในแต่ละ item เลย" (data ผิดรูปแบบ)
        log(f"🔎 {url} ตอบกลับมา status={status} เป็น list จริง แต่มี {len(data)} รายการดิบ ({len(results)} ที่ parse สำเร็จ)")

    return results


def suggest_companies_with_fallback(
    company_name: str, log: ProgressCallback = _noop, timeout: float = 10.0
) -> List[CompanySuggestion]:
    """เหมือน suggest_companies แต่ลองค้นหาซ้ำด้วยคำที่กว้างขึ้นเรื่อยๆ ถ้าค้นด้วยชื่อเต็มแล้วไม่
    เจอเลย — ยืนยันจากผู้ใช้จริงว่าค้นด้วยชื่อเต็มพร้อมคำนำหน้า/ต่อท้ายนิติบุคคล (เช่น "บริษัท ซีพี
    ออลล์ จำกัด (มหาชน)") ไม่เจอผลลัพธ์เลยทั้งที่บริษัทนี้มีอยู่จริงแน่ๆ (เจอตอนพิมพ์ในหน้าเว็บจริง)
    — ใช้กลยุทธ์เดียวกับ dbd_lookup._fallback_search_terms (ตัดคำนำหน้า/ต่อท้ายออกก่อน แล้วค่อยๆ
    ตัดคำท้ายทีละคำ) เพราะน่าจะเป็นปัญหาแบบเดียวกัน (endpoint นี้อาจต้องการคำค้นหาที่ตรงกับชื่อ
    "แกน" ของบริษัทมากกว่าชื่อเต็มที่มีคำนำหน้า/ต่อท้ายกำกับ)"""

    log(f"🔍 ค้นหาใน dataforthai.com: {company_name}")
    results = suggest_companies(company_name, timeout=timeout)
    if results:
        log(f"✅ พบ {len(results)} รายการที่ตรงกับ '{company_name}'")
        return results
    log(f"⚠️ ไม่พบผลลัพธ์สำหรับ '{company_name}'")

    for fallback_keyword in _fallback_search_terms(company_name):
        log(f"🔁 ลองค้นหาอีกครั้งด้วยคำค้นหาที่กว้างขึ้น: '{fallback_keyword}'")
        results = suggest_companies(fallback_keyword, timeout=timeout)
        if results:
            log(f"✅ พบ {len(results)} รายการที่ตรงกับ '{fallback_keyword}'")
            return results
        log(f"⚠️ ไม่พบผลลัพธ์สำหรับ '{fallback_keyword}'")

    return []


def _require_selenium():
    try:
        from selenium import webdriver  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "ต้องติดตั้ง selenium และ webdriver-manager ก่อนใช้งาน dataforthai_lookup: "
            "pip install selenium webdriver-manager"
        ) from exc


def setup_driver(headless: bool = True):
    _require_selenium()
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    chrome_opts = Options()
    if headless:
        chrome_opts.add_argument("--headless=new")
    chrome_opts.add_argument("--disable-gpu")
    chrome_opts.add_argument("--no-sandbox")
    chrome_opts.add_argument("--disable-dev-shm-usage")
    chrome_opts.add_argument("--window-size=1280,900")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_opts)
    driver.implicitly_wait(5)
    return driver


# สคริปต์ JS หาช่องพิมพ์ค้นหาที่ "น่าจะใช่" ในหน้า dataforthai.com/business — สแกน <input> ที่
# มองเห็นได้ (ไม่ถูกซ่อน) และเป็นช่องพิมพ์ข้อความ (รวม type="search" ด้วย — ช่องค้นหาทั่วไปมักใช้
# type นี้ ไม่ใช่แค่ "text" เฉยๆ) คืน selector ที่ใช้หา element นั้นกลับมาได้อีกที — ใช้วิธีสแกน
# กว้างๆ แทนการเดา id/class ที่เจาะจงตายตัว เพราะยังไม่เคยยืนยัน selector จริงของช่องนี้ (ดู
# docstring หัวไฟล์) — ยืนยันจากผู้ใช้จริงว่ารอบแรกที่ลอง (เช็คแค่ type="text"/ไม่มี type) หาไม่เจอ
# เลยทั้งที่หน้ามีช่องค้นหาอยู่จริงแน่ๆ (เห็นในภาพหน้าจอ) จึงต้องกว้างขึ้น + เก็บ diagnostics ไว้ด้วย
_FIND_SEARCH_INPUT_JS = """
var inputs = document.querySelectorAll('input[type="text"], input[type="search"], input:not([type])');
for (var i = 0; i < inputs.length; i++) {
    var el = inputs[i];
    var rect = el.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0 && !el.disabled) {
        if (!el.id) { el.setAttribute('data-dft-search-input', '1'); return '[data-dft-search-input="1"]'; }
        return '#' + el.id;
    }
}
return null;
"""

# เก็บรายละเอียด <input> ทุกตัวในหน้า (type/id/name/placeholder/มองเห็นได้ไหม) — ใช้ตอนหาช่อง
# ค้นหาไม่เจอเลย เพื่อดูว่าจริงๆ แล้วหน้ามี input อะไรอยู่บ้าง (คนละทางกับ _FIND_SEARCH_INPUT_JS
# ที่กรองแล้ว ตัวนี้เอาข้อมูลดิบมาดูทั้งหมดเพื่อวินิจฉัย)
_DUMP_ALL_INPUTS_JS = """
var inputs = document.querySelectorAll('input');
var out = [];
for (var i = 0; i < inputs.length && i < 30; i++) {
    var el = inputs[i];
    var rect = el.getBoundingClientRect();
    out.push('type=' + (el.getAttribute('type') || '(none)') + ' id=' + (el.id || '(none)') +
        ' name=' + (el.getAttribute('name') || '(none)') +
        ' placeholder=' + (el.getAttribute('placeholder') || '(none)') +
        ' visible=' + (rect.width > 0 && rect.height > 0));
}
return out;
"""

# สแกนหา element ที่คลิกได้ (a/li/div ที่มี onclick หรือ cursor:pointer) ซึ่งมีข้อความตรงกับคำค้นหา
# (หรือใกล้เคียง) — ใช้ตอนต้องคลิกเลือกชื่อบริษัทจากรายการ suggestion ที่เด้งขึ้นมา
_FIND_SUGGESTION_ITEM_JS = """
var query = arguments[0].toLowerCase();
var candidates = document.querySelectorAll('a, li, div[onclick], [role="option"], [role="button"]');
for (var i = 0; i < candidates.length && i < 500; i++) {
    var el = candidates[i];
    var text = (el.childElementCount === 0 ? el.textContent : '').trim().toLowerCase();
    if (text && text.length > 2 && text.indexOf(query) !== -1) {
        var rect = el.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0) {
            if (!el.id) { el.setAttribute('data-dft-suggestion-match', '1'); return '[data-dft-suggestion-match="1"]'; }
            return '#' + el.id;
        }
    }
}
return null;
"""

# label ที่พบจริงในหน้ารายละเอียดบริษัท (ยืนยันจาก screenshot ผู้ใช้จริง) — สแกนหาในข้อความทั้งหน้า
# แทนการพึ่ง CSS selector เจาะจง (ทนทานกว่าถ้าโครงสร้างหน้าเปลี่ยนไปบ้าง)
_BUSINESS_CATEGORY_LABELS = ("หมวดธุรกิจ", "ประกอบธุรกิจ")


def _extract_business_category(body_text: str) -> Optional[str]:
    """ดึงข้อความหลัง label 'หมวดธุรกิจ' หรือ 'ประกอบธุรกิจ' จากข้อความเต็มของหน้า (ตัดที่ขึ้น
    บรรทัดใหม่หรือ label อื่นถัดไป) — คืน None ถ้าไม่เจอ label ไหนเลย"""

    for label in _BUSINESS_CATEGORY_LABELS:
        match = re.search(rf"{re.escape(label)}\s*[:：]\s*(.+)", body_text)
        if match:
            value = match.group(1).strip()
            # ตัดที่ label ถัดไปถ้าติดมาในบรรทัดเดียวกัน (เผื่อ body_text รวมหลายบรรทัดเป็นก้อนเดียว)
            for other_label in _BUSINESS_CATEGORY_LABELS + ("ธุรกิจที่ส่งงบการเงินล่าสุด", "สถานะ"):
                idx = value.find(other_label)
                if idx > 0:
                    value = value[:idx].strip()
            if value:
                return value
    return None


def lookup_business_category(
    driver, company_name: str, log: ProgressCallback = _noop, timeout: float = 20.0
) -> Optional[str]:
    """เปิดหน้า dataforthai.com/business พิมพ์ชื่อบริษัท คลิกเลือกจาก suggestion แล้วอ่านข้อความ
    "หมวดธุรกิจ"/"ประกอบธุรกิจ" จากหน้ารายละเอียดที่โหลดมา — คืน None ถ้าหาไม่เจอ/ทำตามขั้นตอนไม่
    สำเร็จ (log รายละเอียดไว้ให้วินิจฉัยได้เสมอ ไม่ raise ยกเว้น error ที่ไม่คาดคิดจริงๆ)

    ⚠️ ยังไม่เคยทดสอบกับเว็บจริง (ดูคำเตือนหัวไฟล์) — ใช้ diagnostics ละเอียดตั้งแต่รอบแรกเพื่อให้
    วินิจฉัยได้ทันทีถ้าไม่สำเร็จ แทนที่จะต้องเดาใหม่เหมือนตอนแรกที่แก้ amr_downloader"""

    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    log(f"🔍 เปิด {BUSINESS_SEARCH_URL} เพื่อค้นหา '{company_name}' (dataforthai.com — ตัวสำรองของ DBD)")
    driver.get(BUSINESS_SEARCH_URL)

    # รอ+ลองใหม่หาช่องค้นหาสูงสุด 10 วินาที (ไม่ใช่สแกนครั้งเดียวจบ) เผื่อ widget ค้นหาโหลด/mount
    # ช้ากว่าตัว body ของหน้า (พบรูปแบบนี้มาแล้วกับหน้า PEA — ดู amr_downloader._try_download_from_show_page)
    deadline = time.time() + 10
    input_selector = driver.execute_script(_FIND_SEARCH_INPUT_JS)
    while not input_selector and time.time() < deadline:
        time.sleep(0.5)
        input_selector = driver.execute_script(_FIND_SEARCH_INPUT_JS)

    if not input_selector:
        try:
            all_inputs = driver.execute_script(_DUMP_ALL_INPUTS_JS)
        except Exception as e:  # noqa: BLE001 — เก็บ diagnostics ไม่สำเร็จ ต้องไม่ทำให้ฟังก์ชันพังไปด้วย
            all_inputs = None
            log(f"⚠️ เก็บรายละเอียด input ไม่สำเร็จ: {e}")

        # ยืนยันจากผู้ใช้จริง: input ตัวเดียวที่เจอในหน้าคือ cf-turnstile-response (Cloudflare
        # Turnstile — ระบบป้องกันบอทของ Cloudflare) แปลว่าหน้าโดนบล็อกไม่ให้ Selenium เห็นเนื้อหา
        # จริงเลย ไม่ใช่แค่ "โครงสร้างหน้าเปลี่ยน" เฉยๆ — ตามหลักการเดียวกับที่ยึดถือมาตลอด (ไม่พยายาม
        # หลบเลี่ยงระบบป้องกันบอทของเว็บใคร ดู dbd_lookup.BlockedByAntiBot) จึงแค่รายงานให้ชัดเจน
        # แล้วหยุด ไม่พยายามข้ามไป
        is_cloudflare_blocked = bool(all_inputs) and any(
            "turnstile" in line.lower() or "cf-chl" in line.lower() for line in all_inputs
        )
        if is_cloudflare_blocked:
            log(
                "🚫 หน้า dataforthai.com/business ถูกบล็อกโดย Cloudflare Turnstile (ระบบป้องกันบอท) "
                "— ไม่ใช่ว่าหน้าเปลี่ยนโครงสร้าง แต่เนื้อหาจริงของหน้าไม่ถูกส่งมาให้เห็นเลย"
            )
        else:
            log("❌ ไม่พบช่องค้นหาในหน้า dataforthai.com/business เลย (โครงสร้างหน้าอาจเปลี่ยนไป)")

        if all_inputs:
            log(f"🔎 input ทั้งหมดที่เจอในหน้า ({len(all_inputs)} ตัว):")
            for line in all_inputs:
                log(f"🔎   {line}")
        elif all_inputs is not None:
            log("🔎 ไม่มี <input> เลยสักตัวในหน้านี้ (อาจจะยังโหลดไม่เสร็จ/ถูกบล็อก)")
        return None
    log(f"✅ พบช่องค้นหา ({input_selector})")

    try:
        search_input = driver.find_element(By.CSS_SELECTOR, input_selector)
    except Exception as e:  # noqa: BLE001
        log(f"❌ หา element ช่องค้นหาไม่สำเร็จ: {e}")
        return None

    search_input.click()
    search_input.send_keys(company_name)

    suggestion_selector = None
    deadline_wait = WebDriverWait(driver, timeout)
    try:
        suggestion_selector = deadline_wait.until(
            lambda d: d.execute_script(_FIND_SUGGESTION_ITEM_JS, company_name.split()[0] if company_name.split() else company_name)
        )
    except Exception:  # noqa: BLE001 — TimeoutException ถือว่าไม่พบ suggestion
        pass

    if not suggestion_selector:
        log(f"❌ ไม่เจอรายการแนะนำ (suggestion) ที่ตรงกับ '{company_name}' ภายใน {timeout} วินาที")
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text
            log(f"🔎 ข้อความในหน้า (300 ตัวอักษรแรก): {' '.join(body_text.split())[:300]}")
        except Exception:  # noqa: BLE001
            pass
        return None

    log(f"👉 คลิกรายการแนะนำ ({suggestion_selector})")
    try:
        suggestion_el = driver.find_element(By.CSS_SELECTOR, suggestion_selector)
        driver.execute_script("arguments[0].click();", suggestion_el)
    except Exception as e:  # noqa: BLE001
        log(f"❌ คลิกรายการแนะนำไม่สำเร็จ: {e}")
        return None

    try:
        WebDriverWait(driver, timeout).until(EC.url_contains("/company/"))
    except Exception:  # noqa: BLE001 — TimeoutException — อาจจะยังโหลดอยู่/URL ไม่เปลี่ยนตามคาด
        log(f"⚠️ URL ไม่เปลี่ยนไปเป็นหน้า /company/ ภายใน {timeout} วินาที (url ปัจจุบัน={driver.current_url})")

    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text
    except Exception as e:  # noqa: BLE001
        log(f"❌ อ่านข้อความหน้าไม่สำเร็จ: {e}")
        return None

    category = _extract_business_category(body_text)
    if category:
        log(f"✅ พบหมวดธุรกิจ: {category}")
    else:
        log(f"❌ ไม่พบ label 'หมวดธุรกิจ'/'ประกอบธุรกิจ' ในหน้า url={driver.current_url}")
        log(f"🔎 ข้อความในหน้า (300 ตัวอักษรแรก): {' '.join(body_text.split())[:300]}")
    return category
