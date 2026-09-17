"""ตัวดาวน์โหลดรายงาน AMR (กิโลวัตต์ชั่วโมงแบบช่วงเวลา) จากเว็บ PEA ด้วย Selenium

ดัดแปลงจากสคริปต์ต้นฉบับของผู้ใช้ (AMR_PEA_Selenium.py) ให้:
  1. ไม่ hardcode username/password ในโค้ด — รับเป็นพารามิเตอร์เท่านั้น
     (เรียกจาก web/app.py ซึ่งอ่านจากตัวแปรสภาพแวดล้อม PEA_AMR_USERNAME /
     PEA_AMR_PASSWORD — ดู README หัวข้อ "นำเข้า AMR อัตโนมัติผ่านเว็บ")
  2. เป็นฟังก์ชัน/คลาสที่เรียกใช้ซ้ำได้ (ไม่ใช่สคริปต์ที่รันจาก __main__ อย่างเดียว)
  3. ส่ง progress กลับผ่าน callback แทนการพิมพ์ terminal UI ตรงๆ (ให้เว็บแอป
     เอาไปแสดงสถานะ job แบบ real-time ได้)

⚠️ ต้องรันในเครื่องที่มี Google Chrome ติดตั้งอยู่ และมี network เข้าถึง
https://www.amr.pea.co.th ได้จริง — ใช้งานไม่ได้ใน sandbox/CI ทั่วไป
"""

from __future__ import annotations

import calendar
import os
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, List, Optional

BASE_URL = "https://www.amr.pea.co.th"
LOGIN_URL = f"{BASE_URL}/AMRWEB/MainCust.aspx"
SEL_PERIOD_URL = f"{BASE_URL}/AMRWEB/selPeriodProfile.aspx"
# หน้า "ข้อมูลผู้ใช้ไฟฟ้า" (ประเภทอัตรา/ประเภทธุรกิจ/KVA/เลขมิเตอร์ ฯลฯ) — ยืนยันจาก
# HTML จริงแล้วว่าอยู่ที่ CustProfile.aspx (ไม่ใช่ CustDashboard.aspx ที่ iframe ชี้ไปตอนแรก
# ซึ่งเป็นหน้าภาพรวม/กราฟ คนละหน้ากัน) ไม่ต้องมี PeaNo ก็เข้าได้
PROFILE_URL = f"{BASE_URL}/AMRWEB/CustProfile.aspx"

ProgressCallback = Callable[[str], None]


def _noop(_: str) -> None:
    pass


def random_delay(mn: float, mx: float) -> None:
    time.sleep(random.uniform(mn, mx))


def generate_month_ranges(start: str, end: str) -> List[tuple]:
    """แบ่งช่วงวันที่ (YYYY-MM-DD) เป็นรายเดือน คืน list ของ (dd/mm/yyyy, dd/mm/yyyy)"""

    s = datetime.strptime(start, "%Y-%m-%d").date()
    e = datetime.strptime(end, "%Y-%m-%d").date()
    ranges, cur = [], s.replace(day=1)
    while cur <= e:
        last_day = calendar.monthrange(cur.year, cur.month)[1]
        month_end = cur.replace(day=last_day)
        ranges.append((max(s, cur).strftime("%d/%m/%Y"), min(e, month_end).strftime("%d/%m/%Y")))
        cur = cur.replace(month=cur.month + 1, day=1) if cur.month < 12 else cur.replace(year=cur.year + 1, month=1, day=1)
    return ranges


@dataclass
class DownloadResult:
    account_no: str
    meter_text: str
    date_from: str
    date_to: str
    file_path: Optional[str]
    success: bool
    error: Optional[str] = None


def _require_selenium():
    try:
        from selenium import webdriver  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "ต้องติดตั้ง selenium และ webdriver-manager ก่อนใช้งานตัวดาวน์โหลด AMR: "
            "pip install selenium webdriver-manager"
        ) from exc


def setup_driver(download_dir: str, headless: bool = True):
    """สร้าง Chrome WebDriver ที่ตั้งค่าดาวน์โหลดไฟล์ไปที่ download_dir"""

    _require_selenium()
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    chrome_opts = Options()
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "plugins.always_open_pdf_externally": True,
        "profile.default_content_setting_values.popups": 1,
    }
    chrome_opts.add_experimental_option("prefs", prefs)
    if headless:
        chrome_opts.add_argument("--headless=new")
    chrome_opts.add_argument("--disable-gpu")
    chrome_opts.add_argument("--no-sandbox")
    chrome_opts.add_argument("--disable-dev-shm-usage")
    chrome_opts.add_argument("--window-size=1280,900")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_opts)
    driver.implicitly_wait(5)

    # Chrome headless (--headless=new) บล็อกการดาวน์โหลดไฟล์โดย default เป็นเรื่องที่รู้กันดี —
    # ต้องอนุญาตผ่าน CDP command นี้อย่างชัดเจน ไม่งั้น browser จะสร้าง .crdownload ขึ้นมาได้
    # (เห็น element/คลิกได้ปกติ ไม่มี exception ใดๆ เลย) แต่ไฟล์ไม่มีวันเสร็จ/ไม่มีวันเขียนจริง —
    # ตรงกับอาการที่ผู้ใช้เจอจริง (.crdownload ค้างอยู่ทั้ง wait หลักและ grace period โดยไม่ error)
    # เดิมโค้ดนี้ไม่เคยส่งคำสั่งนี้เลย ทั้งที่ headless=True เป็นค่า default — เพิ่งพบตอนไล่หาสาเหตุ
    # ของ .crdownload ที่ค้างไม่จบ (ดู _wait_for_download diagnostics)
    try:
        driver.execute_cdp_cmd(
            "Page.setDownloadBehavior", {"behavior": "allow", "downloadPath": download_dir}
        )
    except Exception:  # noqa: BLE001 — บาง environment/เวอร์ชัน ChromeDriver อาจไม่รองรับ ไม่ควรทำให้ setup พังไปด้วย
        pass

    return driver


def amr_login(driver, username: str, password: str, log: ProgressCallback = _noop) -> bool:
    """Login เข้าเว็บ AMR ของ PEA

    ⚠️ username/password ต้องส่งเข้ามาเป็นพารามิเตอร์เท่านั้น ห้าม hardcode ในโค้ด
    """

    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    log("🔑 กำลัง Login ...")
    driver.delete_all_cookies()
    driver.get(LOGIN_URL)
    wait = WebDriverWait(driver, 15)

    u = wait.until(EC.presence_of_element_located((By.ID, "txtUsername")))
    p = driver.find_element(By.ID, "txtPassword")
    u.clear()
    u.send_keys(username)
    p.clear()
    p.send_keys(password)

    driver.find_element(By.ID, "btnOK").click()
    random_delay(1, 2)

    if "ยินดีต้อนรับ" in driver.page_source or "ออกจากระบบ" in driver.page_source:
        log("✅ Login สำเร็จ")
        return True
    if "MainCust.aspx" not in driver.current_url:
        log(f"✅ Login สำเร็จ (redirect → {driver.current_url})")
        return True
    log("❌ Login ไม่สำเร็จ (ตรวจสอบ username/password)")
    return False


def extract_dashboard_params(page_source: str) -> dict:
    """ดึง CustCode / Custid / PeaNo จาก HTML ของหน้า MainCust.aspx หลัง login สำเร็จ

    ค่าเหล่านี้ฝังอยู่ในหน้าเป็น query string 2 จุด (ไม่ใช่ hidden input ธรรมดา):
      1. ในฟังก์ชัน JS `openUrl()`: var param = "?CustCode=...&Custid=...";
      2. ใน src ของ <iframe id="frmMain">: CustDashboard.aspx?CustCode=...&Custid=...&PeaNo=...

    คืนค่า dict {"custcode":..., "custid":..., "peano":...} (ค่าใดหาไม่เจอเป็น None)
    """

    def find(pattern: str) -> Optional[str]:
        m = re.search(pattern, page_source)
        return m.group(1) if m else None

    return {
        "custcode": find(r"CustCode=(\d+)"),
        "custid": find(r"Custid=(\d+)"),
        "peano": find(r"PeaNo=(\d+)"),
    }


def build_dashboard_url(custcode: str, custid: str, peano: Optional[str] = None) -> str:
    """สร้าง URL ของ iframe เดิม (CustDashboard.aspx — หน้าภาพรวม/กราฟ) จากค่าที่ได้จาก
    extract_dashboard_params() — เก็บไว้เผื่อใช้ในอนาคต ไม่ใช่หน้าที่มีข้อมูลอัตรา/ธุรกิจ/KVA
    (ดู build_profile_url สำหรับหน้านั้น)"""

    url = f"{BASE_URL}/AMRWEB/CustDashboard.aspx?CustCode={custcode}&Custid={custid}"
    if peano:
        url += f"&PeaNo={peano}"
    return url


def build_profile_url(custcode: str, custid: str) -> str:
    """สร้าง URL ของหน้า "ข้อมูลผู้ใช้ไฟฟ้า" (CustProfile.aspx) จากค่าที่ได้จาก
    extract_dashboard_params() — หน้านี้มีประเภทอัตรา/ประเภทธุรกิจ/KVA/เลขมิเตอร์ที่ต้องการ"""

    return f"{PROFILE_URL}?CustCode={custcode}&Custid={custid}"


def parse_business_type(raw: str) -> tuple:
    """แยกข้อความ "34111 : การผลิตเยื่อกระดาษ ..." เป็น (รหัส TSIC, ชื่อธุรกิจ)

    คืนค่า ("", "") ถ้า raw ว่างเปล่า; ถ้าไม่มี " : " คั่น จะถือทั้งสตริงเป็นรหัส (ชื่อว่าง)
    """

    raw = (raw or "").strip()
    if not raw:
        return "", ""
    if ":" in raw:
        code, _, name = raw.partition(":")
        return code.strip(), name.strip()
    return raw, ""


def parse_ct_vt(combined: str) -> tuple:
    """แยกข้อความ "100/5 A. , 115000/115 V." เป็น (ct_ratio, vt_ratio) แยกกัน
    เพื่อส่งต่อให้ pea_ingest.compute_meter_multiplier — คืน (None, None) ถ้า parse ไม่ได้"""

    combined = (combined or "").strip()
    parts = [p.strip() for p in combined.split(",")]
    if len(parts) != 2:
        return None, None
    return parts[0], parts[1]


# แผนผัง element id จริงบนหน้า CustProfile.aspx -> ชื่อฟิลด์ที่ใช้ในระบบนี้
# ⚠️ ระบบ PEA ตั้งชื่อ id สลับกับ label ที่แสดงผลจริง (ยึดตาม id เป็นหลัก เพราะ label
# เป็นข้อความที่เปลี่ยนได้ตามภาษา แต่ id คงที่): id "lblCustomerBussType" แสดงผลเป็น
# label "ประเภทอัตรา" (คือรหัสอัตรา เช่น "40") ส่วน id "lblCustomerTypeBuss" แสดงผลเป็น
# label "ประเภทธุรกิจ" (คือรหัส TSIC เช่น "34111 : การผลิต...")
_PROFILE_FIELD_IDS = {
    "pea_site": "lblSitename",
    "account_no": "lblCustomerAcct",
    "name": "lblCustomerName",
    "address": "lblCustomerAdd",
    "phone": "lblCustomerPhone",
    "fax": "lblCustomerFax",
    "contact_person": "lblCustomerContact",
    "email": "lblCustomerEmail",
    "website": "lblCustomerWeb",
    "rate_code": "lblCustomerBussType",  # label แสดงผล "ประเภทอัตรา"
    "billing_method": "lblCustomerAcctT",
    "industrial_estate": "lblCustomerIndust",
    "business_type_raw": "lblCustomerTypeBuss",  # label แสดงผล "ประเภทธุรกิจ" -> "รหัส : ชื่อ"
    "business_size": "lblCustomerRateType",
    "meter_no": "lblCustomerMeterNo",
    "ct_vt": "lblCustomerCTVT",
    "kva": "lblCustomerKVA",
    "bill_reset": "lblCustomerReset",
}


def get_customer_profile(driver, custcode: str, custid: str, log: ProgressCallback = _noop) -> dict:
    """ดึงข้อมูลผู้ใช้ไฟ (ประเภทอัตรา/ประเภทธุรกิจ/KVA/เลขมิเตอร์ ฯลฯ) จากหน้า CustProfile.aspx

    ต้อง login (amr_login) มาก่อนแล้วเท่านั้น (ใช้ session/cookie เดิมของ driver)
    คืนค่า dict ตาม key ใน _PROFILE_FIELD_IDS บวก "business_type_code"/"business_type_name"
    ที่แยกจาก business_type_raw ให้แล้ว (ช่องใดหาไม่เจอ/ว่างเปล่าจะเป็น "")
    """

    from selenium.common.exceptions import NoSuchElementException
    from selenium.webdriver.common.by import By

    url = build_profile_url(custcode, custid)
    log(f"📋 เปิดหน้าข้อมูลผู้ใช้ไฟ: {url}")
    driver.get(url)
    random_delay(0.5, 1)

    def text(elem_id: str) -> str:
        try:
            return driver.find_element(By.ID, elem_id).text.strip()
        except NoSuchElementException:
            return ""

    profile = {field: text(elem_id) for field, elem_id in _PROFILE_FIELD_IDS.items()}
    business_type_code, business_type_name = parse_business_type(profile["business_type_raw"])
    profile["business_type_code"] = business_type_code
    profile["business_type_name"] = business_type_name

    log(
        f"✅ ข้อมูลผู้ใช้ไฟ: {profile['name']} | อัตรา {profile['rate_code']} | "
        f"ธุรกิจ {business_type_code} : {business_type_name} | KVA {profile['kva']}"
    )
    return profile


def get_meter_options(driver, cust_code: str, log: ProgressCallback = _noop) -> List[dict]:
    """ดึงรายการมิเตอร์ของบัญชีผู้ใช้ไฟรายหนึ่ง"""

    from selenium.common.exceptions import TimeoutException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    driver.get(f"{SEL_PERIOD_URL}?CustCode={cust_code}")
    wait = WebDriverWait(driver, 10)
    random_delay(0.5, 1)

    meters: List[dict] = []
    try:
        ddl = wait.until(EC.presence_of_element_located((By.ID, "ddlMeter")))
        for opt in ddl.find_elements(By.TAG_NAME, "option"):
            v = opt.get_attribute("value")
            t = opt.text.strip()
            if v:
                meters.append({"value": v, "text": t})
    except TimeoutException:
        pass

    log(f"🔍 {cust_code}: พบ {len(meters)} มิเตอร์")
    return meters


def _sanitize_for_filename(value: str) -> str:
    """แทนอักขระที่ใช้เป็นชื่อไฟล์ไม่ได้ (เช่น "/" ในวันที่ dd/mm/yyyy) ด้วย "-" """

    return re.sub(r"[^\w.-]", "-", value or "")


def _cache_key(account: str, meter_value: str, date_from: str, date_to: str) -> str:
    """ชื่อไฟล์แบบระบุตัวตนได้แน่นอน (deterministic) สำหรับ 1 บัญชี + 1 มิเตอร์ + 1 ช่วงวันที่

    ใช้เช็คว่าเคยดาวน์โหลดไฟล์นี้ไว้ใน download_dir แล้วหรือยัง (cache) — ไฟล์ที่ดาวน์โหลด
    จากเว็บ PEA จริงมีชื่อที่เว็บตั้งให้เอง ไม่ deterministic จึงต้อง rename เป็นชื่อนี้ทุกครั้ง
    หลังดาวน์โหลดสำเร็จ (ดู _download_reports_for_account)
    """

    parts = [account, meter_value, date_from, date_to]
    return "_".join(_sanitize_for_filename(p) for p in parts)


def _find_cached_file(download_dir: str, cache_key: str) -> Optional[str]:
    """หาไฟล์ที่เคยดาวน์โหลด+ตั้งชื่อด้วย cache_key นี้ไว้แล้วใน download_dir (ไม่สนนามสกุล)"""

    if not os.path.isdir(download_dir):
        return None
    for name in os.listdir(download_dir):
        if os.path.splitext(name)[0] == cache_key:
            return os.path.join(download_dir, name)
    return None


def _wait_for_download(
    download_dir: str, timeout: int = 180, log: ProgressCallback = _noop
) -> Optional[str]:
    """รอไฟล์ .xls/.xlsx/.zip โผล่ใน download_dir สูงสุด timeout วินาที

    ถ้าใกล้หมดเวลาแล้วแต่ยังเห็นไฟล์ .crdownload (กำลังดาวน์โหลดอยู่จริง แค่ยังไม่เสร็จ) จะ
    ต่อเวลาให้อีก (สูงสุด 60 วินาที) แทนที่จะตัดทิ้งกลางคัน — ยืนยันจากผู้ใช้จริงว่าบัญชี/เดือน
    ที่มีข้อมูลเต็มเดือน (~30 วัน) ฝั่งเซิร์ฟเวอร์ใช้เวลาสร้างไฟล์ export นานไม่คงที่เหมือนกับที่
    เคยเจอตอน render หน้า showPeriodProfile.aspx ช้า (จุดนั้นแก้ไปแล้วด้วยการขยาย timeout
    15->30->60 วินาที) จุดนี้จึงน่าจะเป็นปัญหาเดียวกันแค่คนละขั้นตอน — ถ้าดาวน์โหลดเริ่มขึ้นแล้ว
    (มี .crdownload) ไม่ควรตัดทิ้งแค่เพราะนาฬิกาหมดพอดี ควรรอให้ดาวน์โหลดเสร็จจริงๆ"""

    end_time = time.time() + timeout
    grace_end_time = None
    next_heartbeat = time.time() + 15
    last_size = None  # ขนาดไฟล์ .crdownload ตอน heartbeat ก่อนหน้า — ใช้เช็คว่ายังโตอยู่จริง
    # (กำลังดาวน์โหลดจริง) หรือค้างนิ่ง (0 ไบต์/ขนาดเดิมไม่ขยับเลย เช่นเซิร์ฟเวอร์ปิด connection
    # ไปแล้วแต่ Chrome ยังไม่ finalize ไฟล์ หรือโปรแกรมป้องกันไวรัสถือไฟล์ค้างไว้สแกน) — ยืนยันจาก
    # ผู้ใช้จริงว่ามี .crdownload ค้างอยู่นานเกิน grace period เดิม (60 วินาที) ยังไม่รู้ว่าโตอยู่จริง
    # หรือค้างนิ่งตาย ต้องเก็บ evidence นี้ไว้วินิจฉัยครั้งต่อไปแทนที่จะเดา
    while True:
        now = time.time()
        files = [f for f in os.listdir(download_dir) if f.endswith((".xls", ".xlsx", ".zip"))]
        downloading = [f for f in os.listdir(download_dir) if f.endswith(".crdownload")]
        if files and not downloading:
            latest = max(files, key=lambda f: os.path.getmtime(os.path.join(download_dir, f)))
            return os.path.join(download_dir, latest)

        cur_size = None
        if downloading:
            try:
                cur_size = os.path.getsize(os.path.join(download_dir, downloading[0]))
            except OSError:
                cur_size = None

        if now >= end_time:
            if downloading and grace_end_time is None:
                grace_end_time = now + 60
                log(f"⏳ ไฟล์กำลังดาวน์โหลดอยู่ ({downloading[0]}, {cur_size} ไบต์) แต่ครบเวลาแล้ว — ต่อเวลาให้อีก 60 วินาที")
            if grace_end_time is None or now >= grace_end_time:
                if downloading:
                    log(f"❌ ไฟล์ {downloading[0]} ยังไม่เสร็จหลังต่อเวลาให้แล้ว (ขนาดล่าสุด {cur_size} ไบต์) — ยอมแพ้")
                return None

        if now >= next_heartbeat:
            if downloading:
                growth = "" if last_size is None or cur_size is None else (
                    f" (+{cur_size - last_size} ไบต์ จากรอบก่อน)" if cur_size != last_size
                    else " ⚠️ ขนาดไฟล์ไม่ขยับเลยตั้งแต่รอบก่อน — อาจค้างนิ่ง"
                )
                log(f"⏳ รอไฟล์ดาวน์โหลดอยู่ (กำลังดาวน์โหลด {downloading[0]}, {cur_size} ไบต์{growth}) ...")
                last_size = cur_size
            else:
                log("⏳ รอไฟล์ดาวน์โหลดอยู่ (ยังไม่มีไฟล์ปรากฏ) ...")
            next_heartbeat = now + 15

        time.sleep(1)


def _fill_form(driver, meter_point: str, date_from: str, date_to: str, log: ProgressCallback) -> None:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import Select, WebDriverWait

    wait = WebDriverWait(driver, 10)
    try:
        Select(wait.until(EC.presence_of_element_located((By.ID, "ddlMeter")))).select_by_value(meter_point)
        random_delay(0.2, 0.3)
    except Exception as e:  # noqa: BLE001
        log(f"⚠️ เลือก meter ไม่ได้: {e}")

    try:
        driver.find_element(By.ID, "rdo15minute").click()
        random_delay(0.1, 0.2)
    except Exception:  # noqa: BLE001
        pass

    try:
        driver.execute_script(f"document.getElementById('txtDateFr').value = '{date_from}'")
        driver.execute_script(f"document.getElementById('txtDateTo').value = '{date_to}'")
        driver.execute_script("document.getElementById('txtDateFr').dispatchEvent(new Event('change'))")
        driver.execute_script("document.getElementById('txtDateTo').dispatchEvent(new Event('change'))")
        random_delay(0.2, 0.3)
    except Exception as e:  # noqa: BLE001
        log(f"⚠️ ใส่วันที่ไม่ได้: {e}")

    try:
        Select(driver.find_element(By.ID, "ddlReport")).select_by_value("kW")
        random_delay(0.1, 0.2)
    except Exception:  # noqa: BLE001
        pass

    try:
        driver.find_element(By.ID, "rdoData").click()
        random_delay(0.1, 0.2)
    except Exception:  # noqa: BLE001
        pass


def _hide_overlays(driver) -> None:
    driver.execute_script(
        """
        ['divProgress','divLoading','divOverlay','UpdateProgress1'].forEach(function(id){
            var el = document.getElementById(id);
            if (el) { el.style.display = 'none'; el.style.visibility = 'hidden'; el.style.pointerEvents = 'none'; }
        });
        document.querySelectorAll('div').forEach(function(el){
            var s = window.getComputedStyle(el);
            if (parseInt(s.zIndex) > 10 && (s.position === 'fixed' || s.position === 'absolute') && s.display !== 'none') {
                el.style.display = 'none';
            }
        });
        """
    )


def _handle_popup(driver, main_handle, download_dir: str, log: ProgressCallback) -> Optional[str]:
    from selenium.common.exceptions import NoSuchElementException, TimeoutException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    popup_handle = next((h for h in driver.window_handles if h != main_handle), None)
    if not popup_handle:
        log("❌ ไม่พบ popup handle")
        return None

    driver.switch_to.window(popup_handle)
    popup_wait = WebDriverWait(driver, 30)
    try:
        popup_wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
    except Exception:  # noqa: BLE001
        pass
    random_delay(0.5, 1)
    log(f"📄 popup url={driver.current_url}")

    downloaded = None
    try:
        _hide_overlays(driver)

        try:
            rdo = driver.find_element(By.ID, "rdoExcel")
        except NoSuchElementException:
            log("❌ ไม่พบ rdoExcel ใน popup (เลือกไฟล์ประเภท Excel ไม่ได้)")
            raise
        driver.execute_script("arguments[0].click();", rdo)
        random_delay(0.2, 0.3)
        # อ่านค่ากลับมาเช็คว่าคลิกติดจริง (ไม่ใช่แค่เรียก .click() แล้วเชื่อเฉยๆ) — ยืนยันจาก
        # สคริปต์ต้นฉบับของผู้ใช้ว่าเช็คแบบนี้ไว้ด้วยเหมือนกัน
        checked = driver.execute_script("return arguments[0].checked;", rdo)
        log(f"✅ เลือก Excel แล้ว (checked={checked})")

        _hide_overlays(driver)
        try:
            btn = popup_wait.until(EC.element_to_be_clickable((By.ID, "btnSubmit")))
        except TimeoutException:
            log("❌ ปุ่ม ตกลง ใน popup ไม่ clickable ภายใน 30 วินาที")
            raise
        driver.execute_script("arguments[0].click();", btn)
        log("⏳ กด ตกลง แล้ว — รอดาวน์โหลด ...")
        random_delay(2, 3)
        downloaded = _wait_for_download(download_dir, timeout=120, log=log)
        if not downloaded:
            # ไม่มี exception เลยตลอดขั้นตอน (เลือก Excel/กด ตกลง สำเร็จ) แต่ไฟล์ไม่มาเลยใน 120
            # วินาที — เก็บรายละเอียดโฟลเดอร์ดาวน์โหลดไว้วินิจฉัย (เช่นมีไฟล์ .crdownload ค้าง
            # ตลอด แปลว่าเริ่มดาวน์โหลดแล้วแต่ไม่จบ, หรือไม่มีไฟล์ใหม่เกิดขึ้นเลยแปลว่าคลิกไม่ทำงานจริง)
            try:
                entries = os.listdir(download_dir)
            except OSError as e:  # noqa: BLE001
                entries = [f"<list dir error: {e}>"]
            log(f"🔎 ไม่มีไฟล์ปรากฏใน download_dir หลังรอ 60 วินาที — รายการไฟล์ปัจจุบัน: {entries}")
    except Exception as e:  # noqa: BLE001
        log(f"❌ error ใน popup: {e}")

    try:
        driver.close()
    except Exception:  # noqa: BLE001
        pass
    driver.switch_to.window(main_handle)
    return downloaded


_DOWNLOAD_KEYWORDS = ("excel", "download", "ดาวน์โหลด", "ส่งออก", "export")


def _matches_download_keyword(*parts: str) -> bool:
    combined = " ".join(p for p in parts if p).lower()
    return any(kw in combined for kw in _DOWNLOAD_KEYWORDS)


def _find_download_element(driver):
    """ไล่หาปุ่ม/ลิงก์ที่มีคำว่า download/excel/ดาวน์โหลด/ส่งออก อยู่บนหน้าปัจจุบัน — เช็คทั้ง
    <input> (ASP.NET classic webform รวมถึง <input type="image"> ปุ่มรูปภาพที่คำใบ้อยู่ใน
    alt/src/name/id แทน value — ยืนยันจาก diagnostics จริงว่าหน้าที่หาปุ่มไม่เจอมี input=24
    แต่ไม่มีตัวไหน value ตรงเลย น่าจะเป็นปุ่มรูปภาพแบบนี้), <a> (ลิงก์ เช็ค href/title ด้วยเผื่อ
    เป็นลิงก์ไอคอนไม่มีข้อความ), และ <button> คืน (element, ข้อความที่จับคู่ได้) หรือ
    (None, None) ถ้าไม่เจอเลย"""

    from selenium.webdriver.common.by import By

    for b in driver.find_elements(By.TAG_NAME, "input"):
        value = b.get_attribute("value") or ""
        alt = b.get_attribute("alt") or ""
        src = b.get_attribute("src") or ""
        name = b.get_attribute("name") or ""
        elem_id = b.get_attribute("id") or ""
        if _matches_download_keyword(value, alt, src, name, elem_id):
            return b, (value or alt or src or name or elem_id).strip().lower()

    for a in driver.find_elements(By.TAG_NAME, "a"):
        text = (a.text or "").strip()
        href = a.get_attribute("href") or ""
        title_attr = a.get_attribute("title") or ""
        if _matches_download_keyword(text, href, title_attr):
            return a, (text or title_attr or href).strip().lower()

    for btn in driver.find_elements(By.TAG_NAME, "button"):
        text = (btn.text or btn.get_attribute("value") or "").strip()
        if _matches_download_keyword(text):
            return btn, text.lower()

    return None, None


def _try_download_from_show_page(
    driver, main_handle, download_dir: str, log: ProgressCallback, timeout: float = 60.0
) -> Optional[str]:
    """กรณีกด "ตกลง" แล้วเว็บไม่เปิด popup แต่ redirect ไปหน้า showPeriodProfile.aspx ตรงๆ
    แทน (พบจริงจากผู้ใช้ — เว็บ PEA มีพฤติกรรมนี้ได้บางครั้ง ไม่ใช่แค่ทาง popup เท่านั้น)

    ไล่หาปุ่มดาวน์โหลดด้วย _find_download_element แบบ "รอ+ลองใหม่" นานสูงสุด timeout วินาที
    (ไม่ใช่สแกนครั้งเดียวจบแบบเดิม) เพราะยืนยันจากผู้ใช้จริงแล้วว่าบัญชี/เดือนเดียวกัน บางรอบ
    หาปุ่มเจอ บางรอบหาไม่เจอ ทั้งที่หน้าเว็บมีข้อมูล+ปุ่ม Download อยู่จริงเหมือนกันทุกครั้ง —
    สาเหตุน่าจะเป็นความช้าไม่คงที่ของการโหลดหน้า (เดือนที่มีข้อมูลราย 15 นาทีเยอะกว่า/ช่วงเวลา
    เต็มเดือน ~30 วัน ~2,880 แถว render ช้ากว่ามาก) — เดิมเพิ่มจาก 15 เป็น 30 วินาทีไปแล้วครั้งหนึ่ง
    (ยืนยันจาก diagnostics จริงว่าปุ่ม input#btnDownload/btnDownload2 มี value/id ตรงกับ keyword
    อยู่แล้ว แค่ยังไม่ทันปรากฏใน DOM ภายในเวลาที่ scan) แต่ยืนยันเพิ่มเติมจากผู้ใช้จริงอีกครั้งว่า
    30 วินาทียังไม่พอสำหรับช่วงเวลาเต็มเดือน (diagnostics เจอปุ่มทันทีหลัง scan หมดเวลาไปแล้ว
    เหมือนเดิม แค่ margin กว้างกว่ารอบก่อน) จึงเพิ่มเป็น 60 วินาที พร้อม log heartbeat ระหว่างรอ
    ทุก 10 วินาที กันดูเหมือน job ค้างเฉยๆ

    กดแล้วดูว่ามี popup เปิดขึ้นตามมา (เรียก _handle_popup ต่อ) หรือดาวน์โหลดไฟล์ลงมาตรงๆ เลย
    """

    initial_handles = set(driver.window_handles)

    def click_and_wait(element) -> Optional[str]:
        # รอ popup เปิดขึ้นนานสูงสุด 20 วินาที (เดิม 5 วินาทีสั้นเกินไป — ยืนยันจากผู้ใช้จริงว่า
        # เว็บ PEA เปิด popup "เลือกเอกสารที่ต้องการ" เสมอหลังกดปุ่มนี้ ไม่เคยดาวน์โหลดตรงๆ เลย
        # แต่ log กลับขึ้น "ไม่มี popup" เพราะ popup เปิดช้ากว่า 5 วินาทีที่เคยรอ ทำให้ตกไปรอไฟล์
        # ดาวน์โหลดตรงๆ ที่ไม่มีวันมาถึง 60 วินาทีโดยเปล่าประโยชน์)
        handles_before = set(driver.window_handles)
        element.click()

        deadline = time.time() + 20
        while time.time() < deadline:
            time.sleep(0.25)
            if set(driver.window_handles) - handles_before:
                log("✅ มี popup เปิดขึ้นหลังกดปุ่มดาวน์โหลดในหน้านี้")
                return _handle_popup(driver, main_handle, download_dir, log)

        log("⏳ ไม่มี popup หลังกดปุ่ม — รอดาวน์โหลดไฟล์ตรงๆ ...")
        random_delay(1, 2)
        return _wait_for_download(download_dir, timeout=120, log=log)

    try:
        start = time.time()
        deadline = start + timeout
        next_heartbeat = start + 10
        element, matched_text = _find_download_element(driver)
        while element is None and time.time() < deadline:
            time.sleep(0.5)
            element, matched_text = _find_download_element(driver)
            now = time.time()
            if element is None and now >= next_heartbeat:
                log(f"⏳ ยังหาปุ่มดาวน์โหลดในหน้า showPeriodProfile.aspx ไม่เจอ รอต่อ ({int(now - start)}s/{int(timeout)}s) ...")
                next_heartbeat = now + 10

        if element is not None:
            log(f"👉 กดปุ่ม/ลิงก์ดาวน์โหลดในหน้า showPeriodProfile: {matched_text}")
            result = click_and_wait(element)
            if result:
                return result

        log("⚠️ ไม่พบปุ่ม/ลิงก์ดาวน์โหลดในหน้า showPeriodProfile.aspx")
        _log_show_page_diagnostics(driver, log)
    except Exception as e:  # noqa: BLE001
        log(f"⚠️ สแกนหาปุ่มดาวน์โหลดผิดพลาด: {e}")

    return None


# สคริปต์ JS หา element ที่ "น่าจะเกี่ยวกับดาวน์โหลด" ทั่วทั้งหน้า (คนละทางกับ
# _find_download_element ที่ไล่ทีละ tag ผ่าน Selenium API) — สแกนเฉพาะ tag ที่มักจะเป็นปุ่ม/ลิงก์
# กดได้จริง (input/a/button/img/[onclick]) กันไม่ให้ไปแมตช์ container element ใหญ่ๆ ที่มีลูกเป็น
# ร้อยตัว แล้วคืน outerHTML ของตัวที่แมตช์ (ตัดสั้นแค่ 300 ตัวอักษรกันยาวเกิน) — ใช้ตอน
# _find_download_element หาไม่เจอ เพื่อดูว่า "อะไรที่จริงๆ อยู่บนหน้านี้ที่เกี่ยวกับดาวน์โหลด"
# โดยไม่ต้องให้ผู้ใช้เปิด DevTools เอง (ยืนยันจากผู้ใช้จริงว่าเปิด DevTools เองแล้วจับ element
# ที่ถูกต้องได้ยาก เพราะปุ่มอยู่ใน ASP.NET UpdatePanel ที่ทำ postback ตอนคลิก)
_FIND_DOWNLOAD_SNIPPETS_JS = """
var keywords = ['download', 'ดาวน์โหลด', 'ส่งออก', 'export', 'excel'];
var candidates = document.querySelectorAll('input, a, button, img, [onclick]');
var matches = [];
for (var i = 0; i < candidates.length && matches.length < 8; i++) {
    var el = candidates[i];
    var haystack = [
        el.tagName, el.id, el.getAttribute('name'), el.getAttribute('value'),
        el.getAttribute('alt'), el.getAttribute('src'), el.getAttribute('href'),
        el.getAttribute('title'), el.getAttribute('onclick'),
        (el.childElementCount === 0 ? el.textContent : ''),
    ].join(' ').toLowerCase();
    for (var k = 0; k < keywords.length; k++) {
        if (haystack.indexOf(keywords[k]) !== -1) {
            matches.push(el.outerHTML.substring(0, 300));
            break;
        }
    }
}
return matches;
"""


def _log_show_page_diagnostics(driver, log: ProgressCallback) -> None:
    """เก็บรายละเอียดหน้าปัจจุบันไว้ใน log ตอนหาปุ่มดาวน์โหลดไม่เจอ (url/title/จำนวน element
    ต่างๆ/มี iframe ไหม/ข้อความบางส่วนในหน้า/HTML ดิบของ element ที่น่าจะเกี่ยวกับดาวน์โหลด) —
    ยืนยันจากผู้ใช้จริงว่ามีบางครั้งที่หน้ามีข้อมูล+ปุ่ม Download อยู่จริง (เช็คด้วยตาเองใน
    เบราว์เซอร์) แต่ _find_download_element ยังหาไม่เจอ ซึ่งยังไม่รู้สาเหตุแน่ชัด — เก็บรายละเอียด
    ตรงนี้ไว้เพื่อวินิจฉัยจากของจริงในครั้งต่อไปที่เจอ โดยไม่ต้องให้ผู้ใช้เปิด DevTools เอง (ลองแล้ว
    หลายรอบ จับ element ที่ถูกต้องได้ยากเพราะหน้าใช้ ASP.NET UpdatePanel ทำ postback ตอนคลิก)"""

    from selenium.webdriver.common.by import By

    try:
        n_input = len(driver.find_elements(By.TAG_NAME, "input"))
        n_a = len(driver.find_elements(By.TAG_NAME, "a"))
        n_button = len(driver.find_elements(By.TAG_NAME, "button"))
        n_iframe = len(driver.find_elements(By.TAG_NAME, "iframe"))
        n_table = len(driver.find_elements(By.TAG_NAME, "table"))
        log(
            f"🔎 รายละเอียดหน้า ณ ตอนหาปุ่มไม่เจอ: url={driver.current_url} title={driver.title!r} "
            f"input={n_input} a={n_a} button={n_button} iframe={n_iframe} table={n_table}"
        )
        body_text = driver.find_element(By.TAG_NAME, "body").text
        snippet = " ".join(body_text.split())[:300]
        if snippet:
            log(f"🔎 ข้อความในหน้า (300 ตัวอักษรแรก): {snippet}")
    except Exception as e:  # noqa: BLE001 — เก็บ diagnostics ไม่สำเร็จ ต้องไม่ทำให้ job หลักพังไปด้วย
        log(f"⚠️ เก็บรายละเอียดหน้าไม่สำเร็จ: {e}")

    try:
        snippets = driver.execute_script(_FIND_DOWNLOAD_SNIPPETS_JS)
        if snippets:
            for i, html in enumerate(snippets, start=1):
                log(f"🔎 HTML element ที่เกี่ยวกับดาวน์โหลด #{i}: {html}")
        else:
            log("🔎 ไม่เจอ element ใดๆ ในหน้าที่มีคำว่า download/ดาวน์โหลด/ส่งออก/export/excel เลย (แม้แต่ที่ไม่ใช่ปุ่ม)")
    except Exception as e:  # noqa: BLE001 — เก็บ diagnostics ไม่สำเร็จ ต้องไม่ทำให้ job หลักพังไปด้วย
        log(f"⚠️ สแกน HTML ที่เกี่ยวกับดาวน์โหลดด้วย JS ไม่สำเร็จ: {e}")


def download_month(
    driver, cust_code: str, meter_point: str, meter_text: str, date_from: str, date_to: str,
    download_dir: str, log: ProgressCallback = _noop,
) -> Optional[str]:
    """ดาวน์โหลดรายงาน kW ราย 15 นาที ของมิเตอร์หนึ่งตัว ช่วงวันที่หนึ่ง คืน path ไฟล์ที่ได้"""

    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    log(f"📥 {cust_code} {meter_text} | {date_from} → {date_to}")
    main_handle = driver.current_window_handle
    initial_handles = set(driver.window_handles)

    driver.get(f"{SEL_PERIOD_URL}?CustCode={cust_code}")
    random_delay(0.8, 1.2)
    _fill_form(driver, meter_point, date_from, date_to, log)
    random_delay(0.2, 0.3)

    try:
        btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "btnSubmit")))
        btn.click()
    except Exception as e:  # noqa: BLE001
        log(f"❌ กด ตกลง ไม่ได้: {e}")
        return None

    popup_opened = False
    for _ in range(40):
        time.sleep(0.25)
        if set(driver.window_handles) - initial_handles:
            popup_opened = True
            break

    if popup_opened:
        return _handle_popup(driver, main_handle, download_dir, log)

    if "showPeriodProfile" in driver.current_url:
        log("↪️ ไม่มี popup — เว็บ redirect ไปหน้า showPeriodProfile.aspx แทน กำลังหาปุ่มดาวน์โหลดในหน้านั้น ...")
        random_delay(1, 2)
        return _try_download_from_show_page(driver, main_handle, download_dir, log)

    log(f"❌ ไม่มี popup และไม่ได้ redirect ไปหน้า showPeriodProfile (url={driver.current_url})")
    return None


# จำนวนครั้งสูงสุดที่ลองดาวน์โหลด 1 ช่วงวันที่ใหม่ทั้งหมด (โหลดหน้าใหม่ ไม่ใช่แค่สแกนซ้ำ) ก่อนจะ
# ยอมแพ้ (หรือลองแบ่งครึ่งช่วงแทน) — ดูเหตุผลใน _download_month_range
_MAX_MONTH_ATTEMPTS = 3

# ช่วงวันที่สั้นสุดที่ยังยอมแบ่งครึ่งต่อ — ต่ำกว่านี้ไม่แบ่งอีก (กันแบ่งจนเหลือช่วงสั้นเกินไปจะ
# ไร้ประโยชน์ ยิ่งดาวน์โหลดยิ่งช้าลงเรื่อยๆ)
_MIN_SPLIT_RANGE_DAYS = 6


def _split_date_range_in_half(date_from: str, date_to: str) -> Optional[tuple]:
    """แบ่งช่วงวันที่ (dd/mm/yyyy) เป็น 2 ช่วงย่อยเท่าๆ กัน คืน None ถ้าสั้นเกินกว่าจะแบ่งต่อ
    (< _MIN_SPLIT_RANGE_DAYS วัน)

    ยืนยันจากผู้ใช้จริงว่าบัญชี/เดือนที่มีข้อมูลเต็มเดือน (~30 วัน) ดาวน์โหลดไฟล์ export ค้างที่
    .crdownload ขนาด "เท่าเดิมเป๊ะ" (562,145 ไบต์) ซ้ำกันทุกรอบ แม้ลองใหม่ทั้งหน้าครบ
    _MAX_MONTH_ATTEMPTS ครั้งแล้วก็ตาม — ค่าคงที่ซ้ำเป๊ะแบบนี้ต่างจากความช้าแบบสุ่มที่เจอมาก่อน
    หน้านี้ (ซึ่งแก้ด้วยการขยาย timeout ไปแล้ว) ชี้ว่าเซิร์ฟเวอร์ PEA เองน่าจะสร้างไฟล์ export ให้
    ไม่ครบ/ขาดกลางคันแบบ deterministic สำหรับ request ขนาดใหญ่แบบนี้ (ใกล้ขีดจำกัด 45 วันที่
    หน้าเว็บระบุไว้เอง) — รอ/ลองซ้ำด้วย request ขนาดเดิมจะพังซ้ำเดิมไปเรื่อยๆ ทางแก้คือแบ่ง
    request ให้เล็กลงแทน"""

    d_from = datetime.strptime(date_from, "%d/%m/%Y")
    d_to = datetime.strptime(date_to, "%d/%m/%Y")
    total_days = (d_to - d_from).days + 1
    if total_days < _MIN_SPLIT_RANGE_DAYS:
        return None
    mid = d_from + timedelta(days=total_days // 2 - 1)
    mid_next = mid + timedelta(days=1)
    if mid_next > d_to:
        return None
    return (date_from, mid.strftime("%d/%m/%Y")), (mid_next.strftime("%d/%m/%Y"), date_to)


def _download_month_range(
    driver, account: str, meter: dict, date_from: str, date_to: str, download_dir: str,
    log: ProgressCallback,
) -> List[tuple]:
    """ดาวน์โหลดช่วงวันที่หนึ่งช่วงของมิเตอร์หนึ่งตัว คืน list ของ
    (date_from, date_to, path หรือ None, error หรือ None) — ปกติมี 1 รายการ แต่จะมีมากกว่า 1
    ถ้าช่วงเดิมดาวน์โหลดไม่สำเร็จแล้วถูกแบ่งครึ่ง (ดู _split_date_range_in_half)

    ไฟล์ที่เคยดาวน์โหลดไว้แล้ว (บัญชี+มิเตอร์+ช่วงวันที่เดียวกัน แม้เป็นช่วงที่แบ่งครึ่งมาแล้วก็
    เช็คแคชแยกตามช่วงย่อยนั้นได้) จะถูกใช้ซ้ำแทนการดาวน์โหลดใหม่ (ดู _cache_key/_find_cached_file)

    ลองใหม่ทั้งช่วง (โหลดหน้าใหม่ทั้งหมด ไม่ใช่แค่สแกนซ้ำในหน้าเดิม) สูงสุด _MAX_MONTH_ATTEMPTS
    ครั้งก่อน — ยืนยันจากผู้ใช้จริงว่าบัญชี/เดือนเดียวกัน บางรอบหาปุ่มดาวน์โหลดเจอ บางรอบไม่เจอ
    ทั้งที่หน้าเว็บมีข้อมูลอยู่จริงเหมือนกันทุกครั้ง น่าจะเป็นปัญหาโหลดหน้า/เซิร์ฟเวอร์แบบไม่คงที่
    (ดู _try_download_from_show_page) — ถ้าลองซ้ำครบแล้วยังไม่สำเร็จ และช่วงยาวพอจะแบ่งได้ ค่อย
    ลองแบ่งครึ่งแล้วดาวน์โหลดแต่ละครึ่งแยกกันแทน"""

    cache_key = _cache_key(account, meter["value"], date_from, date_to)
    cached_path = _find_cached_file(download_dir, cache_key)
    if cached_path:
        log(f"♻️ ใช้ไฟล์ที่เคยดาวน์โหลดไว้แล้ว (ข้ามการโหลดซ้ำ): {os.path.basename(cached_path)}")
        return [(date_from, date_to, cached_path, None)]

    path = None
    last_error: Optional[str] = None
    for attempt in range(1, _MAX_MONTH_ATTEMPTS + 1):
        try:
            path = download_month(
                driver, account, meter["value"], meter["text"], date_from, date_to,
                download_dir, log=log,
            )
            last_error = None
        except Exception as e:  # noqa: BLE001
            path = None
            last_error = str(e)

        if path:
            break
        if attempt < _MAX_MONTH_ATTEMPTS:
            log(
                f"🔁 ลองใหม่ (ครั้งที่ {attempt + 1}/{_MAX_MONTH_ATTEMPTS}): "
                f"{account} {meter['text']} {date_from}-{date_to}"
            )
            random_delay(2, 4)

    if path:
        # เว็บ PEA ตั้งชื่อไฟล์ที่ดาวน์โหลดมาเอง (ไม่ deterministic) — เปลี่ยนชื่อเป็น
        # cache_key ก่อนเก็บไว้ เพื่อให้รอบถัดไปหาไฟล์แคชนี้เจอ
        ext = os.path.splitext(path)[1]
        cached_target = os.path.join(download_dir, cache_key + ext)
        try:
            os.replace(path, cached_target)
            path = cached_target
        except OSError as e:  # noqa: BLE001
            log(f"⚠️ เปลี่ยนชื่อไฟล์เป็นชื่อแคชไม่ได้ (ใช้ไฟล์เดิมต่อได้ปกติ แค่รอบหน้าจะหาไม่เจอ): {e}")
        log(f"✅ สำเร็จ: {os.path.basename(path)}")
        return [(date_from, date_to, path, None)]

    split = _split_date_range_in_half(date_from, date_to)
    if split:
        (f1, t1), (f2, t2) = split
        log(
            f"✂️ ช่วง {date_from}-{date_to} ดาวน์โหลดไม่สำเร็จหลังลอง {_MAX_MONTH_ATTEMPTS} ครั้ง "
            f"— ลองแบ่งครึ่งเป็น {f1}-{t1} และ {f2}-{t2} แทน (เผื่อเซิร์ฟเวอร์สร้างไฟล์ export "
            f"ขนาดใหญ่ไม่ครบ)"
        )
        return (
            _download_month_range(driver, account, meter, f1, t1, download_dir, log)
            + _download_month_range(driver, account, meter, f2, t2, download_dir, log)
        )

    if last_error:
        log(f"❌ error หลังลอง {_MAX_MONTH_ATTEMPTS} ครั้ง: {account} {meter['text']} {date_from}-{date_to}: {last_error}")
    else:
        log(f"❌ ไม่สำเร็จหลังลอง {_MAX_MONTH_ATTEMPTS} ครั้ง: {account} {meter['text']} {date_from}-{date_to}")
    return [(date_from, date_to, None, last_error)]


def _download_reports_for_account(
    driver, account: str, month_ranges: List[tuple], download_dir: str, log: ProgressCallback
) -> List[DownloadResult]:
    """ดาวน์โหลดรายงาน kW ราย 15 นาทีของทุกมิเตอร์ในบัญชีเดียว ครอบคลุมทุกเดือนใน
    month_ranges — ใช้ driver ที่ login อยู่แล้ว (เรียกจาก download_amr_kw_reports และ
    download_amr_with_profile ทั้งคู่ เพื่อไม่ให้ต้องเขียน loop ซ้ำ)

    แต่ละช่วงวันที่ดาวน์โหลดผ่าน _download_month_range ซึ่งจะแบ่งช่วงให้เล็กลงเองถ้าดาวน์โหลด
    ทั้งช่วงไม่สำเร็จ (ดูเหตุผลที่นั่น) — ผลลัพธ์ต่อ (มิเตอร์, ช่วงวันที่ที่ขอมา) จึงอาจมีมากกว่า
    1 DownloadResult ถ้าถูกแบ่งช่วง แต่ไม่กระทบขั้นตอน import ต่อ เพราะที่นั่นรวมไฟล์จากทุก
    DownloadResult ที่สำเร็จเป็น list เดียวอยู่แล้ว ไม่ได้ผูกกับช่วงวันที่เดิมที่ขอมา"""

    results: List[DownloadResult] = []
    meters = get_meter_options(driver, account, log=log)
    if not meters:
        log(f"⚠️ ไม่พบมิเตอร์สำหรับบัญชี {account}")
        return results

    for meter in meters:
        for date_from, date_to in month_ranges:
            for f, t, path, err in _download_month_range(driver, account, meter, date_from, date_to, download_dir, log):
                results.append(
                    DownloadResult(
                        account_no=account, meter_text=meter["text"],
                        date_from=f, date_to=t,
                        file_path=path, success=bool(path), error=err if not path else None,
                    )
                )
                random_delay(0.5, 1)

    return results


def download_amr_kw_reports(
    username: str,
    password: str,
    accounts: List[str],
    start_date: str,
    end_date: str,
    download_dir: str,
    log: ProgressCallback = _noop,
    headless: bool = True,
) -> List[DownloadResult]:
    """ล็อกอินเว็บ AMR ของ PEA แล้วดาวน์โหลดรายงาน kW ราย 15 นาทีของทุกมิเตอร์ในทุกบัญชี
    ที่ระบุ ครอบคลุมทุกเดือนในช่วง start_date..end_date (รูปแบบ YYYY-MM-DD)

    คืนค่าเป็น list ของ DownloadResult (1 รายการต่อ 1 มิเตอร์ต่อ 1 เดือน)

    ⚠️ username/password รับเข้ามาเป็นพารามิเตอร์เท่านั้น — ห้าม hardcode หรือ log
    ค่าจริงออกไปที่ใดทั้งสิ้น (รวมถึงไฟล์ log)
    """

    os.makedirs(download_dir, exist_ok=True)
    month_ranges = generate_month_ranges(start_date, end_date)
    results: List[DownloadResult] = []

    driver = setup_driver(download_dir, headless=headless)
    try:
        if not amr_login(driver, username, password, log=log):
            raise RuntimeError("Login ไม่สำเร็จ — ตรวจสอบ username/password")

        for account in accounts:
            results.extend(_download_reports_for_account(driver, account, month_ranges, download_dir, log))
    finally:
        driver.quit()

    return results


def download_amr_with_profile(
    username: str,
    password: str,
    start_date: str,
    end_date: str,
    download_dir: str,
    log: ProgressCallback = _noop,
    headless: bool = True,
) -> tuple:
    """เวอร์ชัน "ใส่แค่ Username/Password" — login ครั้งเดียว แล้วทั้งดึงข้อมูลผู้ใช้ไฟ
    (ประเภทอัตรา/ประเภทธุรกิจ/KVA จากหน้า CustProfile.aspx) และดาวน์โหลดรายงาน AMR ของ
    บัญชีนั้นในเซสชันเดียวกัน (username คือเลขบัญชีอยู่แล้ว — 1 login = 1 บัญชี)

    คืนค่า (profile: dict, results: List[DownloadResult])
    """

    os.makedirs(download_dir, exist_ok=True)
    month_ranges = generate_month_ranges(start_date, end_date)

    driver = setup_driver(download_dir, headless=headless)
    try:
        if not amr_login(driver, username, password, log=log):
            raise RuntimeError("Login ไม่สำเร็จ — ตรวจสอบ username/password")

        params = extract_dashboard_params(driver.page_source)
        custcode = params.get("custcode") or username
        custid = params.get("custid")
        if not custid:
            raise RuntimeError(
                "ไม่พบ Custid จากหน้าหลัง login — ระบบ AMR ของ PEA อาจเปลี่ยนโครงสร้างหน้าไปแล้ว "
                "(ลองกรอกประเภทธุรกิจ/อัตรา/KVA เองแทนการให้ระบบตรวจจับอัตโนมัติ)"
            )

        profile = get_customer_profile(driver, custcode, custid, log=log)
        results = _download_reports_for_account(driver, custcode, month_ranges, download_dir, log)
    finally:
        driver.quit()

    return profile, results
