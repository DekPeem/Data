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
from datetime import datetime
from typing import Callable, List, Optional

BASE_URL = "https://www.amr.pea.co.th"
LOGIN_URL = f"{BASE_URL}/AMRWEB/MainCust.aspx"
SEL_PERIOD_URL = f"{BASE_URL}/AMRWEB/selPeriodProfile.aspx"
DASHBOARD_URL = f"{BASE_URL}/AMRWEB/CustDashboard.aspx"

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
    """สร้าง URL ของหน้า CustDashboard.aspx (ข้อมูลผู้ใช้ไฟ: ประเภทธุรกิจ/อัตรา/KVA ฯลฯ)
    จากค่าที่ได้จาก extract_dashboard_params() — เปิด URL นี้ตรงๆ แทนการพึ่ง iframe"""

    url = f"{DASHBOARD_URL}?CustCode={custcode}&Custid={custid}"
    if peano:
        url += f"&PeaNo={peano}"
    return url


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


def _wait_for_download(download_dir: str, timeout: int = 180) -> Optional[str]:
    end_time = time.time() + timeout
    while time.time() < end_time:
        files = [f for f in os.listdir(download_dir) if f.endswith((".xls", ".xlsx", ".zip"))]
        downloading = [f for f in os.listdir(download_dir) if f.endswith(".crdownload")]
        if files and not downloading:
            latest = max(files, key=lambda f: os.path.getmtime(os.path.join(download_dir, f)))
            return os.path.join(download_dir, latest)
        time.sleep(1)
    return None


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

    downloaded = None
    try:
        _hide_overlays(driver)
        rdo = driver.find_element(By.ID, "rdoExcel")
        driver.execute_script("arguments[0].click();", rdo)
        random_delay(0.2, 0.3)
        _hide_overlays(driver)
        btn = driver.find_element(By.ID, "btnSubmit")
        driver.execute_script("arguments[0].click();", btn)
        log("⏳ กด ตกลง แล้ว — รอดาวน์โหลด ...")
        random_delay(2, 3)
        downloaded = _wait_for_download(download_dir, timeout=60)
    except Exception as e:  # noqa: BLE001
        log(f"❌ error ใน popup: {e}")

    try:
        driver.close()
    except Exception:  # noqa: BLE001
        pass
    driver.switch_to.window(main_handle)
    return downloaded


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

    log(f"❌ ไม่มี popup เปิดขึ้น (url={driver.current_url})")
    return None


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
            meters = get_meter_options(driver, account, log=log)
            if not meters:
                log(f"⚠️ ไม่พบมิเตอร์สำหรับบัญชี {account}")
                continue
            for meter in meters:
                for date_from, date_to in month_ranges:
                    try:
                        path = download_month(
                            driver, account, meter["value"], meter["text"], date_from, date_to,
                            download_dir, log=log,
                        )
                        results.append(
                            DownloadResult(
                                account_no=account, meter_text=meter["text"],
                                date_from=date_from, date_to=date_to,
                                file_path=path, success=bool(path),
                            )
                        )
                        if path:
                            log(f"✅ สำเร็จ: {os.path.basename(path)}")
                        else:
                            log(f"❌ ไม่สำเร็จ: {account} {meter['text']} {date_from}-{date_to}")
                    except Exception as e:  # noqa: BLE001
                        log(f"❌ error: {account} {meter['text']} {date_from}-{date_to}: {e}")
                        results.append(
                            DownloadResult(
                                account_no=account, meter_text=meter["text"],
                                date_from=date_from, date_to=date_to,
                                file_path=None, success=False, error=str(e),
                            )
                        )
                    random_delay(0.5, 1)
    finally:
        driver.quit()

    return results
