"""ค้นหาประเภทธุรกิจ (TSIC) ของนิติบุคคลจากชื่อบริษัท ผ่านเว็บ DBD DataWarehouse ของกรม
พัฒนาธุรกิจการค้า (datawarehouse.dbd.go.th) — ข้อมูลจดทะเบียนธุรกิจเป็นข้อมูลสาธารณะ เปิดให้
ค้นหาได้ฟรีผ่านหน้าเว็บ ใช้สำหรับกรณีมีแค่ "ชื่อบริษัท" (ไม่มี AMR ไม่ได้เลือกประเภทธุรกิจเอง)
แล้วอยากรู้ว่าบริษัทนั้นควรจัดอยู่ TSIC หมวดไหน

⚠️ สำคัญมาก: เว็บนี้เข้ารหัส response ของ API ภายในตัวเอง (พบว่า /api/v1/company-profiles/infos
คืนค่าเป็น {"kid","salt","iv","ct"} ซึ่งเป็นข้อมูลเข้ารหัส AES ไม่ใช่ JSON ธรรมดา) — ชัดเจนว่าเป็น
มาตรการป้องกันการดึงข้อมูลอัตโนมัติผ่าน API โดยเจตนา โมดูลนี้จึง "ไม่เรียก API นั้นตรงๆ เด็ดขาด"
และไม่พยายามถอดรหัส/reverse-engineer วิธีเข้ารหัสใดๆ ทั้งสิ้น — ใช้ Selenium ควบคุมเบราว์เซอร์จริง
พิมพ์ค้นหาในช่องค้นหาบนหน้าเว็บเหมือนผู้ใช้งานทั่วไป แล้วรอให้ "เว็บของเขาเองถอดรหัสและ render
ผลลัพธ์เป็นตาราง HTML ปกติก่อน" ค่อยอ่านค่าจาก DOM ที่ render เสร็จแล้ว (เหมือนที่ตาคนอ่านหน้าจอ)
ไม่ได้แตะหรือเลี่ยงระบบเข้ารหัสของเขาเลย

โครงสร้างตารางผลลัพธ์ (data-v-099134f5, ยืนยันจาก DOM จริงของหน้า /juristic/searchInfo):
    div#table-filter-data > table.table.table-bordered... > tbody > tr > td (11 คอลัมน์)
    คอลัมน์: [ปุ่มเปรียบเทียบ, ลำดับที่, เลขทะเบียนนิติบุคคล, ชื่อนิติบุคคล, ประเภทนิติบุคคล,
              สถานะ, รหัสประเภทธุรกิจ(TSIC), ชื่อประเภทธุรกิจ, ทุนจดทะเบียน, สินทรัพย์รวม, รายได้รวม]

ถ้ามีเลขทะเบียนนิติบุคคลอยู่แล้ว (registration_no) ให้ใช้ fetch_company_profile_by_registration_no
แทน search_company_business_type เสมอ — เข้าหน้าโปรไฟล์ตรงๆ ที่ /company/profile/<เลขทะเบียน> แทน
การพิมพ์ค้นหาในช่องค้นหา (/juristic/searchInfo?keyword=...) ยืนยันจากผู้ใช้จริงว่าค้นหาด้วยเลข
ทะเบียน (ตัวเลขล้วน) ผ่านช่องค้นหามักโดน Incapsula (ระบบป้องกันบอท) บล็อก ทั้งที่เข้าหน้าโปรไฟล์
ตรงๆ ด้วยเลขทะเบียนเดียวกันสำเร็จปกติ ไม่บล็อกเลย — ดู docstring ของฟังก์ชันนั้นสำหรับรายละเอียด
โครงสร้างหน้าโปรไฟล์ (ยืนยันจาก screenshot จริงของผู้ใช้ ไม่ใช่จาก DOM ที่ inspect เอง เพราะ
สภาพแวดล้อมที่พัฒนาโค้ดนี้ไม่มี Chrome/อินเทอร์เน็ตออกไปเว็บจริงได้เลย — ต้องให้ผู้ใช้ทดสอบยืนยันซ้ำ
อีกครั้งจริงๆ ก่อนเชื่อว่า parsing ถูกต้อง 100%)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple
from urllib.parse import quote

BASE_URL = "https://datawarehouse.dbd.go.th"
SEARCH_PATH = "/juristic/searchInfo"
COMPANY_PROFILE_PATH = "/company/profile"

# selector ของตารางผลลัพธ์ — ถ้าเว็บเปลี่ยนโครงสร้างในอนาคต แก้ตรงนี้ที่เดียว
_RESULT_ROW_SELECTOR = "div#table-filter-data table tbody tr"

ProgressCallback = Callable[[str], None]


def _noop(_: str) -> None:
    pass


@dataclass(frozen=True)
class CompanyBusinessInfo:
    """1 แถวผลลัพธ์จากการค้นหาชื่อบริษัทใน DBD DataWarehouse"""

    registration_no: str
    juristic_name: str
    juristic_type: str
    status: str
    tsic_code: str
    tsic_name_th: str

    @property
    def tsic_division_code(self) -> Optional[str]:
        """2 หลักแรกของรหัส TSIC (Division ตามมาตรฐาน ISIC/TSIC) — None ถ้ารหัสสั้นเกินไป
        จะเอาไปเทียบกับ BusinessType.division_code ของระบบเราได้ (ดู mapping.find_load_profile
        ชั้น DIVISION_ONLY) แต่ต้องเข้าใจว่า tsic_code นี้เป็นรหัส TSIC มาตรฐานจริงจาก DBD ซึ่ง
        "ไม่ใช่" รหัสภายในเดียวกับที่ กฟภ. ใช้ (เช่น "34111" ที่ scrape จากหน้า PEA เอง ไม่ใช่รูปแบบ
        TSIC มาตรฐาน) เทียบกันได้แค่ระดับ division_code เท่านั้น ไม่ใช่ตัวรหัสตรงๆ"""

        code = (self.tsic_code or "").strip()
        return code[:2] if len(code) >= 2 else None


def _require_selenium():
    try:
        from selenium import webdriver  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "ต้องติดตั้ง selenium และ webdriver-manager ก่อนใช้งาน dbd_lookup: "
            "pip install selenium webdriver-manager"
        ) from exc


def setup_driver(headless: bool = True):
    """สร้าง Chrome WebDriver แบบเบา (ไม่ต้องตั้งค่าดาวน์โหลดไฟล์เหมือน amr_downloader.setup_driver
    เพราะโมดูลนี้แค่เปิดหน้าเว็บอ่านผลลัพธ์ ไม่ได้ดาวน์โหลดไฟล์ใดๆ เลย)"""

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


def build_search_url(keyword: str) -> str:
    return f"{BASE_URL}{SEARCH_PATH}?keyword={quote(keyword)}"


def build_company_profile_url(registration_no: str) -> str:
    return f"{BASE_URL}{COMPANY_PROFILE_PATH}/{quote(registration_no.strip())}"


# คำนำหน้า/ต่อท้ายที่บ่งบอกประเภทนิติบุคคล — เรียงจากยาวไปสั้น เพื่อให้ตัดรูปเต็มก่อนรูปย่อ
# (เช่นตัด "ห้างหุ้นส่วนจำกัด" ก่อน ไม่ใช่ไปตัด "หจก." ซึ่งไม่ตรงอยู่แล้วถ้าพิมพ์เต็ม)
_LEGAL_FORM_PREFIXES = [
    "ห้างหุ้นส่วนสามัญนิติบุคคล",
    "ห้างหุ้นส่วนจำกัด",
    "ห้างหุ้นส่วนสามัญ",
    "หจก.",
    "บริษัท",
]
_LEGAL_FORM_SUFFIXES = [
    "จำกัด (มหาชน)",
    "จำกัด(มหาชน)",
    "จำกัด",
]


def _strip_legal_form(name: str) -> Optional[str]:
    """ตัดคำนำหน้า/ต่อท้ายที่บ่งบอกประเภทนิติบุคคล (เช่น "หจก.", "บริษัท", "จำกัด") ออก เหลือแค่
    ชื่อเฉพาะของกิจการ — ใช้เป็นคำค้นหาสำรองรอบสอง เผื่อรูปแบบคำนำหน้า/ต่อท้ายที่ผู้ใช้พิมพ์มาไม่ตรง
    กับที่ DBD บันทึกไว้เป๊ะๆ (เช่น พิมพ์ย่อ "หจก." แต่ DBD DataWarehouse ทำ keyword search แบบ
    ต้องตรงกับข้อความที่บันทึกไว้ค่อนข้างเป๊ะ) คืน None ถ้าตัดแล้วไม่มีอะไรเปลี่ยน (จะได้ไม่ค้นหา
    ซ้ำคำเดิมโดยเปล่าประโยชน์)"""

    original = name.strip()
    stripped = original
    for prefix in _LEGAL_FORM_PREFIXES:
        if stripped.startswith(prefix):
            stripped = stripped[len(prefix) :].strip()
            break
    for suffix in _LEGAL_FORM_SUFFIXES:
        if stripped.endswith(suffix):
            stripped = stripped[: -len(suffix)].strip()
            break

    return stripped if stripped and stripped != original else None


# ความยาวขั้นต่ำ (จำนวนตัวอักษร) ของคำค้นหาสำรองแต่ละคำ — กันไม่ให้ตัดจนเหลือคำสั้นเกินไป (เช่น
# 1 ตัวอักษร) ซึ่งกว้างเกินจะมีประโยชน์และอาจได้ผลลัพธ์เป็นพันรายการโดยเปล่าประโยชน์
_MIN_FALLBACK_KEYWORD_LEN = 2


def _fallback_search_terms(name: str) -> List[str]:
    """สร้างรายการคำค้นหาสำรอง เรียงจาก "เจาะจงที่สุด" ไปหา "กว้างขึ้นเรื่อยๆ" ใช้ตอนค้นด้วยชื่อ
    เต็มตามที่พิมพ์มาแล้วไม่พบผลลัพธ์เลย — ยืนยันจากการทดสอบจริงบนเว็บ DBD (ด้วยชื่อบริษัทจริงของ
    ผู้ใช้งานระบบ ไม่ได้บันทึกไว้ในโค้ด/comment นี้) ว่า keyword search ของ DBD ทำงานแบบ "ต้องมี
    คำค้นหาทั้งวลีอยู่ในชื่อ" (ไม่ใช่แค่มีคำใดคำหนึ่งอยู่) — ค้นด้วยวลี 2 คำที่ต่อกันอาจไม่เจอเลย
    ทั้งที่ค้นแค่คำแรกคำเดียวเจอเป็นพันรายการ — เป็นไปได้ว่าชื่อที่ระบบเราเห็น (สแกนมาจากหน้า PEA)
    มีคำเพิ่มเติม/สะกดคลาดเคลื่อนจากชื่อจดทะเบียนจริงบางส่วน

    ลำดับ: (1) ตัดคำนำหน้า/ต่อท้ายประเภทนิติบุคคลออกก่อน (ดู _strip_legal_form) แล้ว (2) ถ้ายังไม่พบ
    ค่อยๆ ตัดคำท้ายสุดออกทีละคำ จนเหลือคำแรกคำเดียว (หรือถึง _MIN_FALLBACK_KEYWORD_LEN) — ไม่เริ่ม
    จากคำเดียวตั้งแต่แรกเพราะกว้างเกินไป (อาจได้ผลลัพธ์เป็นพันรายการ) ใช้เป็นตัวเลือกสุดท้ายจริงๆ
    เท่านั้น ผลลัพธ์ที่ได้ยังต้องให้ผู้ใช้เลือกเองอยู่ดี (ไม่ auto-apply เพราะไม่ตรงชื่อเป๊ะ)
    """

    stripped = _strip_legal_form(name)
    core = stripped or name.strip()
    words = core.split()

    terms: List[str] = []
    if stripped:
        terms.append(stripped)
    for n in range(len(words) - 1, 0, -1):
        candidate = " ".join(words[:n])
        if len(candidate) >= _MIN_FALLBACK_KEYWORD_LEN and candidate not in terms:
            terms.append(candidate)
    return terms


def _parse_result_rows(driver) -> List[CompanyBusinessInfo]:
    """อ่านแถวผลลัพธ์จากตารางที่หน้าเว็บ render เสร็จแล้ว (ถอดรหัสให้เรียบร้อยแล้วโดยเว็บเขาเอง —
    ดูคำเตือนหัวไฟล์: เราไม่ได้แตะ API เข้ารหัสเลย)"""

    from selenium.webdriver.common.by import By

    results: List[CompanyBusinessInfo] = []
    rows = driver.find_elements(By.CSS_SELECTOR, _RESULT_ROW_SELECTOR)
    for row in rows:
        cells = row.find_elements(By.TAG_NAME, "td")
        if len(cells) < 8:
            continue  # แถวไม่ครบคอลัมน์ตามที่คาด (เช่น แถวข้อความ "ไม่พบผลลัพธ์") ข้ามไป
        results.append(
            CompanyBusinessInfo(
                registration_no=cells[2].text.strip(),
                juristic_name=cells[3].text.strip(),
                juristic_type=cells[4].text.strip(),
                status=cells[5].text.strip(),
                tsic_code=cells[6].text.strip(),
                tsic_name_th=cells[7].text.strip(),
            )
        )
    return results


class BlockedByAntiBot(Exception):
    """เว็บ DBD DataWarehouse บล็อกการเข้าถึงอัตโนมัติ (พบข้อความยืนยันจากผู้ใช้จริง: "Request
    unsuccessful. Incapsula incident ID: ..." — Incapsula คือระบบป้องกันบอท/WAF ของ Imperva)
    ไม่ใช่ว่าไม่พบบริษัทนี้จริงๆ — สำคัญมากที่ต้องแยกสองกรณีนี้ออกจากกันให้ชัดเจน เพราะ "ไม่พบ"
    ธรรมดาจะทำให้ผู้ใช้เข้าใจผิดว่าบริษัทที่ค้นหาไม่มีอยู่จริง ทั้งที่จริงๆ คือระบบป้องกันของเว็บ
    ทำงานอยู่ (ตามเจตนาของเขา)

    ⚠️ โมดูลนี้ไม่พยายามหลีกเลี่ยง/ปลอมตัวให้พ้นการตรวจจับนี้เด็ดขาด (เช่น ปลอม navigator.webdriver,
    หมุน user-agent/IP ฯลฯ) — ตรงกับหลักการเดียวกับที่ประกาศไว้หัวไฟล์นี้แล้วเรื่องไม่แตะ API ที่
    เข้ารหัสไว้: Incapsula คือมาตรการป้องกันที่เว็บตั้งใจทำขึ้นมาโดยเจตนา การพยายามหลบเลี่ยงจะขัดกับ
    หลักการที่ยึดถือมาตั้งแต่ต้น"""

    def __init__(self, snippet: str = ""):
        message = (
            "เว็บ DBD DataWarehouse บล็อกการเข้าถึงอัตโนมัติ (ระบบป้องกันบอทของเว็บ ไม่ใช่ว่าไม่พบ"
            "บริษัทนี้จริงๆ) — ลองค้นหาด้วยตัวเองที่ https://datawarehouse.dbd.go.th/juristic/searchInfo "
            f"แทน หรือรอสักครู่แล้วลองใหม่{f' (ข้อความจากเว็บ: {snippet})' if snippet else ''}"
        )
        super().__init__(message)


# คำ/วลีที่บ่งชี้ว่าเว็บบล็อกการเข้าถึงอัตโนมัติ (ไม่ใช่แค่ "ไม่พบผลลัพธ์" ธรรมดา) — เช็คแบบ
# case-insensitive เพราะภาษาอังกฤษบางทีสลับตัวพิมพ์เล็กใหญ่ได้
_BLOCK_INDICATORS = ("incapsula", "request unsuccessful", "access denied", "are you a robot", "captcha")


def _log_search_diagnostics(driver, log: ProgressCallback) -> None:
    """เก็บรายละเอียดหน้าไว้ใน log ตอนรอตารางผลลัพธ์ไม่เจอเลย (url/title/ข้อความในหน้า/มี
    div#table-filter-data อยู่ไหมแม้จะไม่มีแถวเลย) — ยืนยันจากผู้ใช้จริงว่าค้นหาด้วยคำสั้นๆ ที่
    ควรจะเจอผลลัพธ์เยอะมาก (เช่น "ซีพี" ซึ่งเป็นคำขึ้นต้นชื่อบริษัทในเครือเจริญโภคภัณฑ์นับสิบๆ
    แห่ง) กลับ "ไม่พบผลลัพธ์" ทุกครั้ง — ผิดปกติมากถ้าเว็บทำงานถูกต้อง จึงต้องเก็บหลักฐานว่า
    หน้าเว็บที่โหลดมาจริงๆ หน้าตาเป็นยังไง (เว็บ DBD เปลี่ยนโครงสร้าง DOM ไปจากตอนเขียนโค้ดนี้?
    ถูกบล็อก/ขึ้น CAPTCHA? หรือค้นหาแล้วไม่มีผลลัพธ์จริงๆ?) แทนที่จะรู้แค่ว่า "ไม่พบ" เฉยๆ"""

    from selenium.webdriver.common.by import By

    try:
        has_result_container = len(driver.find_elements(By.CSS_SELECTOR, "div#table-filter-data")) > 0
        body_text = driver.find_element(By.TAG_NAME, "body").text
        snippet = " ".join(body_text.split())[:300]
        log(
            f"🔎 รายละเอียดหน้า ณ ตอนหาผลลัพธ์ไม่เจอ: url={driver.current_url} title={driver.title!r} "
            f"มี div#table-filter-data={has_result_container}"
        )
        if snippet:
            log(f"🔎 ข้อความในหน้า (300 ตัวอักษรแรก): {snippet}")

        lowered = body_text.lower()
        if any(indicator in lowered for indicator in _BLOCK_INDICATORS):
            log("🚫 เว็บ DBD บล็อกการเข้าถึงอัตโนมัติ (ตรวจพบข้อความของระบบป้องกันบอท) — ไม่ใช่ว่าไม่พบบริษัทนี้จริงๆ")
            raise BlockedByAntiBot(snippet)
    except BlockedByAntiBot:
        raise
    except Exception as e:  # noqa: BLE001 — เก็บ diagnostics ไม่สำเร็จ ต้องไม่ทำให้การค้นหาหลักพังไปด้วย
        log(f"⚠️ เก็บรายละเอียดหน้าไม่สำเร็จ: {e}")


def _search_once(driver, keyword: str, log: ProgressCallback, timeout: int) -> List[CompanyBusinessInfo]:
    """ค้นหา 1 รอบด้วยคำค้นหาเดียว — ใช้ driver ที่เปิดอยู่แล้ว (ไม่ต้อง login เพราะเป็นข้อมูล
    สาธารณะ) แค่ driver.get() ไปที่ URL ค้นหา แล้วรอให้ตารางผลลัพธ์ปรากฏก่อนอ่านค่า"""

    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.common.by import By

    url = build_search_url(keyword)
    log(f"🔍 ค้นหาใน DBD DataWarehouse: {keyword}")
    driver.get(url)

    wait = WebDriverWait(driver, timeout)
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, _RESULT_ROW_SELECTOR)))
    except Exception:  # noqa: BLE001 — TimeoutException หรืออื่นๆ ถือว่าไม่พบผลลัพธ์เหมือนกัน
        log(f"⚠️ ไม่พบผลลัพธ์สำหรับ '{keyword}'")
        _log_search_diagnostics(driver, log)
        return []

    results = _parse_result_rows(driver)
    log(f"✅ พบ {len(results)} รายการที่ตรงกับ '{keyword}'")
    return results


def search_company_business_type(
    driver, company_name: str, log: ProgressCallback = _noop, timeout: int = 15
) -> List[CompanyBusinessInfo]:
    """ค้นหาชื่อบริษัทใน DBD DataWarehouse คืนรายการผลลัพธ์ทั้งหมดที่พบ (การค้นหาแบบ keyword
    อาจเจอหลายบริษัทที่ชื่อคล้ายกัน — ผู้เรียกเลือกเอง หรือใช้ find_exact_match กรองชื่อที่ตรงเป๊ะ)

    ถ้าค้นด้วยชื่อเต็มตามที่พิมพ์มาแล้วไม่พบเลย จะลองค้นซ้ำด้วยคำค้นหาที่เจาะจงน้อยลงเรื่อยๆ ตาม
    _fallback_search_terms() — ตัดคำนำหน้า/ต่อท้ายประเภทนิติบุคคลออกก่อน (เช่น "หจก.", "บริษัท",
    "จำกัด") แล้วถ้ายังไม่พบ ค่อยๆ ตัดคำท้ายสุดออกทีละคำ เพราะยืนยันจากการทดสอบจริงว่า DBD
    DataWarehouse ทำ keyword search แบบต้องมีคำค้นหาทั้งวลีอยู่ในชื่อ (ไม่ใช่แค่มีคำใดคำหนึ่ง) —
    ถ้าชื่อที่ระบบเราเห็นมีคำเพิ่มเติม/สะกดคลาดเคลื่อนจากชื่อจดทะเบียนจริงแม้แค่บางส่วน ค้นด้วยชื่อ
    เต็มก็จะไม่พบเลย ทั้งที่กิจการนั้นมีอยู่จริงในฐานข้อมูล
    """

    results = _search_once(driver, company_name, log, timeout)
    if results:
        return results

    for fallback_keyword in _fallback_search_terms(company_name):
        log(f"🔁 ลองค้นหาอีกครั้งด้วยคำค้นหาที่กว้างขึ้น: '{fallback_keyword}'")
        results = _search_once(driver, fallback_keyword, log, timeout)
        if results:
            return results

    return results


def lookup_business_type_for_company(
    company_name: str, log: ProgressCallback = _noop, headless: bool = True
) -> List[CompanyBusinessInfo]:
    """เปิดเบราว์เซอร์ใหม่ ค้นหาชื่อบริษัท แล้วปิดเบราว์เซอร์ทิ้งเสมอ (ใช้ครั้งเดียวจบ) —
    เป็น entry point หลักที่ web/app.py เรียกใช้ (ไม่ต้องยุ่งกับการจัดการ driver เอง)

    ⚠️ ต้องรันในเครื่องที่มี Google Chrome ติดตั้งอยู่ (เหมือน amr_downloader) ใช้งานไม่ได้ใน
    sandbox/CI ทั่วไปที่ไม่มีเบราว์เซอร์จริง/ไม่มี network ออกไปเว็บภายนอกได้
    """

    driver = setup_driver(headless=headless)
    try:
        return search_company_business_type(driver, company_name, log=log)
    finally:
        driver.quit()


# ── ค้นหาจากเลขทะเบียนนิติบุคคลโดยตรง (เข้าหน้าโปรไฟล์เลย ไม่ผ่านช่องค้นหา) ──
#
# หน้า /company/profile/<เลขทะเบียน> แสดงข้อมูลเป็นข้อความล้วนๆ แบบ "label ตามด้วยค่า" (ยืนยันจาก
# screenshot จริงของผู้ใช้ ไม่ใช่จาก DOM inspection เพราะสภาพแวดล้อมที่พัฒนาโค้ดนี้ไม่มี Chrome/
# อินเทอร์เน็ตจริง) ตัวอย่างที่เจอจริง:
#   ชื่อนิติบุคคล : บริษัท สยามคาสท์ไนล่อน จำกัด
#   เลขทะเบียนนิติบุคคล : 0145537000805
#   ...
#   ประเภทนิติบุคคล    บริษัทจำกัด
#   สถานะนิติบุคคล    ยังดำเนินกิจการอยู่
#   ...
#   ประเภทธุรกิจตอนจดทะเบียน
#   ประเภทธุรกิจ    28250 การผลิตเครื่องจักรที่ใช้ในกระบวนการผลิตอาหาร เครื่องดื่ม และ ยาสูบ
#   วัตถุประสงค์    การผลิตและจำหน่ายเครื่องกรองน้ำทุกชนิด
#   ประเภทธุรกิจที่ส่งงบการเงินปีล่าสุด
#   ประเภทธุรกิจ    32909 การผลิตผลิตภัณฑ์อื่นๆซึ่งไม่ได้จัดประเภทไว้ในที่อื่น
#   วัตถุประสงค์    ผลิตและจำหน่ายเครื่องกรองน้ำ ไส้กรองน้ำ
# อ่านด้วย regex บนข้อความที่ render เสร็จแล้วทั้งหน้า (driver.find_element(By.TAG_NAME,
# "body").text) แทนการอ้างอิง CSS class/id — ทนทานต่อการเปลี่ยน CSS มากกว่า แต่ถ้าเว็บเปลี่ยนคำที่
# ใช้เป็น label จะอ่านไม่เจอ (ต้องแก้ตรงนี้ตามข้อความจริงที่เจอ ถ้าผู้ใช้ทดสอบแล้วอ่านไม่ได้)

_HEADER_LATEST_FINANCIAL_STATEMENT = "ประเภทธุรกิจที่ส่งงบการเงินปีล่าสุด"
_HEADER_AT_REGISTRATION = "ประเภทธุรกิจตอนจดทะเบียน"


def _extract_labeled_value(text: str, label: str) -> Optional[str]:
    """หาค่าที่อยู่หลัง label หนึ่ง (รูปแบบ "label : value" หรือ "label\\nvalue" ก็ได้ เพราะ .text
    ของ Selenium render ตาราง/กริดออกมาไม่แน่นอนว่าจะมีตัวคั่นบรรทัดตรงไหนเป๊ะ) คืน None ถ้าไม่เจอ
    label เลย หรือเจอแต่ไม่มีอะไรตามหลัง (บรรทัดว่าง)"""

    m = re.search(re.escape(label) + r"\s*[:：]?\s*\n?\s*(.+)", text)
    if not m:
        return None
    value = m.group(1).strip()
    return value or None


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


def fetch_company_profile_by_registration_no(
    driver, registration_no: str, log: ProgressCallback = _noop, timeout: int = 15
) -> List[CompanyBusinessInfo]:
    """เข้าหน้าโปรไฟล์นิติบุคคลของ DBD DataWarehouse ตรงๆ ด้วยเลขทะเบียน (URL รูปแบบ
    /company/profile/<เลขทะเบียน>) แทนการค้นหาผ่านช่องค้นหา — ดูเหตุผลในคอมเมนต์เหนือฟังก์ชันกลุ่ม
    นี้ (ยืนยันจากผู้ใช้จริงว่าการค้นหาผ่านช่องค้นหาด้วยเลขทะเบียนมักโดนบล็อก แต่เข้าหน้าโปรไฟล์
    ตรงๆ ด้วยเลขทะเบียนเดียวกันสำเร็จปกติ)

    หน้านี้แสดง TSIC ได้ถึง 2 ชุด: "ตามงบการเงินปีล่าสุด" (จากงบการเงินฉบับล่าสุดที่ยื่น — ปกติเป็น
    ปัจจุบันกว่า เพราะธุรกิจอาจเปลี่ยนไปจากตอนจดทะเบียนครั้งแรกได้) กับ "ตอนจดทะเบียน" (ตอนจดทะเบียน
    ครั้งแรก) — คืนทั้ง 2 ชุดเป็นรายการแยกกัน (เอา "ปีล่าสุด" ขึ้นก่อนเสมอ ให้ผู้ใช้เลือกเอง) ถ้ารหัส
    ตรงกันทั้งคู่คืนแค่ 1 รายการ (ไม่ต้องให้เลือกซ้ำที่ไม่มีประโยชน์) คืน list ว่างถ้าไม่พบหน้าโปรไฟล์
    เลย (เช่น เลขทะเบียนผิด/ไม่มีอยู่จริง) หรือพบหน้าแต่อ่านรหัส TSIC ไม่ได้เลย (โครงสร้างหน้าเปลี่ยน)

    raise BlockedByAntiBot ถ้าตรวจพบข้อความของระบบป้องกันบอท (เผื่อไว้ — ยังไม่เคยพบว่าหน้าโปรไฟล์
    โดนบล็อกจริงจากการทดสอบของผู้ใช้ ต่างจากช่องค้นหาที่โดนบ่อย แต่เช็คไว้กันเหนียว)
    """

    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.common.by import By

    normalized = registration_no.strip()
    url = build_company_profile_url(normalized)
    log(f"🔍 เปิดหน้าโปรไฟล์นิติบุคคลจากเลขทะเบียน: {normalized}")
    driver.get(url)

    wait = WebDriverWait(driver, timeout)
    try:
        wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'เลขทะเบียนนิติบุคคล')]")))
    except Exception:  # noqa: BLE001 — TimeoutException หรืออื่นๆ ถือว่าไม่พบหน้าโปรไฟล์เหมือนกัน
        log(f"⚠️ ไม่พบหน้าโปรไฟล์ของเลขทะเบียน '{normalized}' (อาจไม่มีเลขนี้ในระบบ หรือเว็บช้า)")
        _log_search_diagnostics(driver, log)
        return []

    body_text = driver.find_element(By.TAG_NAME, "body").text
    lowered = body_text.lower()
    if any(indicator in lowered for indicator in _BLOCK_INDICATORS):
        log("🚫 เว็บ DBD บล็อกการเข้าถึงอัตโนมัติ (ตรวจพบข้อความของระบบป้องกันบอท)")
        raise BlockedByAntiBot(" ".join(body_text.split())[:300])

    juristic_name = _extract_labeled_value(body_text, "ชื่อนิติบุคคล") or ""
    juristic_type = _extract_labeled_value(body_text, "ประเภทนิติบุคคล") or ""
    status = _extract_labeled_value(body_text, "สถานะนิติบุคคล") or ""

    latest = _extract_tsic_after_header(body_text, _HEADER_LATEST_FINANCIAL_STATEMENT)
    registered = _extract_tsic_after_header(
        body_text, _HEADER_AT_REGISTRATION, next_header=_HEADER_LATEST_FINANCIAL_STATEMENT
    )

    candidates: List[CompanyBusinessInfo] = []
    seen_codes: set = set()

    def add(entry: Optional[Tuple[str, str]], label: str) -> None:
        if entry is None:
            return
        code, name = entry
        if code in seen_codes:
            return
        seen_codes.add(code)
        candidates.append(
            CompanyBusinessInfo(
                registration_no=normalized,
                juristic_name=juristic_name,
                juristic_type=juristic_type,
                status=status,
                tsic_code=code,
                tsic_name_th=f"({label}) {name}",
            )
        )

    add(latest, "ตามงบการเงินปีล่าสุด")
    add(registered, "ตอนจดทะเบียน")

    if not candidates:
        log(f"⚠️ พบหน้าโปรไฟล์แต่อ่านรหัส TSIC ไม่สำเร็จ (โครงสร้างหน้าอาจเปลี่ยนไป) — ดูที่ {url} เอง")
    else:
        log(f"✅ อ่านข้อมูลจากหน้าโปรไฟล์สำเร็จ: {juristic_name} — พบ TSIC {len(candidates)} รายการ")
    return candidates


def lookup_business_type_by_registration_no(
    registration_no: str, log: ProgressCallback = _noop, headless: bool = True
) -> List[CompanyBusinessInfo]:
    """เปิดเบราว์เซอร์ใหม่ เข้าหน้าโปรไฟล์นิติบุคคลตรงๆ ด้วยเลขทะเบียน แล้วปิดเบราว์เซอร์ทิ้งเสมอ —
    entry point คู่กับ lookup_business_type_for_company (web/app.py เลือกเรียกตัวไหนตามว่ามีเลข
    ทะเบียนมาหรือมีแค่ชื่อ)"""

    driver = setup_driver(headless=headless)
    try:
        return fetch_company_profile_by_registration_no(driver, registration_no, log=log)
    finally:
        driver.quit()


def find_exact_match(results: List[CompanyBusinessInfo], company_name: str) -> Optional[CompanyBusinessInfo]:
    """หาแถวที่ชื่อนิติบุคคลตรงเป๊ะกับที่ค้นหา (ไม่สนตัวพิมพ์ใหญ่เล็ก/ช่องว่างหัวท้าย) — คืน None
    ถ้าไม่มีตัวไหนตรงเป๊ะเลย (เช่น ค้นหากว้างๆ ได้หลายบริษัท ต้องให้ผู้ใช้เลือกเองแทน)"""

    normalized = company_name.strip().lower()
    for r in results:
        if r.juristic_name.strip().lower() == normalized:
            return r
    return None
