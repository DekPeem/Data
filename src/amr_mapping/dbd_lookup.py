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
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional
from urllib.parse import quote

BASE_URL = "https://datawarehouse.dbd.go.th"
SEARCH_PATH = "/juristic/searchInfo"

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


def build_search_url(keyword: str) -> str:
    return f"{BASE_URL}{SEARCH_PATH}?keyword={quote(keyword)}"


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


def search_company_business_type(
    driver, company_name: str, log: ProgressCallback = _noop, timeout: int = 15
) -> List[CompanyBusinessInfo]:
    """ค้นหาชื่อบริษัทใน DBD DataWarehouse คืนรายการผลลัพธ์ทั้งหมดที่พบ (การค้นหาแบบ keyword
    อาจเจอหลายบริษัทที่ชื่อคล้ายกัน — ผู้เรียกเลือกเอง หรือใช้ find_exact_match กรองชื่อที่ตรงเป๊ะ)

    ต้อง driver ที่เปิดอยู่แล้ว (ไม่ต้อง login เพราะเป็นข้อมูลสาธารณะ) — ฟังก์ชันนี้แค่ driver.get()
    ไปที่ URL ค้นหา แล้วรอให้ตารางผลลัพธ์ปรากฏก่อนอ่านค่า
    """

    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.common.by import By

    url = build_search_url(company_name)
    log(f"🔍 ค้นหาใน DBD DataWarehouse: {company_name}")
    driver.get(url)

    wait = WebDriverWait(driver, timeout)
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, _RESULT_ROW_SELECTOR)))
    except Exception:  # noqa: BLE001 — TimeoutException หรืออื่นๆ ถือว่าไม่พบผลลัพธ์เหมือนกัน
        log("⚠️ ไม่พบผลลัพธ์ (หรือหน้าเว็บของ DBD เปลี่ยนโครงสร้างไปแล้ว — ต้องอัปเดต selector)")
        return []

    results = _parse_result_rows(driver)
    log(f"✅ พบ {len(results)} รายการที่ตรงกับ '{company_name}'")
    return results


def find_exact_match(results: List[CompanyBusinessInfo], company_name: str) -> Optional[CompanyBusinessInfo]:
    """หาแถวที่ชื่อนิติบุคคลตรงเป๊ะกับที่ค้นหา (ไม่สนตัวพิมพ์ใหญ่เล็ก/ช่องว่างหัวท้าย) — คืน None
    ถ้าไม่มีตัวไหนตรงเป๊ะเลย (เช่น ค้นหากว้างๆ ได้หลายบริษัท ต้องให้ผู้ใช้เลือกเองแทน)"""

    normalized = company_name.strip().lower()
    for r in results:
        if r.juristic_name.strip().lower() == normalized:
            return r
    return None
