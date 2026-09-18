"""ดึงข้อมูลนิติบุคคล (จดทะเบียนตั้งใหม่ / เลิกกิจการ) จาก DBD Open Data (openapi.dbd.go.th) มา
เก็บเป็นฐานข้อมูล SQLite ในเครื่อง เพื่อค้นหาชื่อบริษัทแบบออฟไลน์ — ไม่ต้องยิง request ไปเว็บ DBD
DataWarehouse ที่มีระบบป้องกันบอท (Incapsula) บล็อกอยู่เสมอ (ดู dbd_lookup.BlockedByAntiBot) และ
ไม่ต้องพึ่งเว็บบุคคลที่สาม dataforthai.com ซึ่งหน้าค้นหาก็โดน Cloudflare Turnstile บล็อกเช่นกัน
(ดู dataforthai_lookup.py) — DBD Open Data เป็นไฟล์เปิดเผยตามสัญญาอนุญาตข้อมูลเปิดภาครัฐ ไม่ต้องใช้
API key และไม่มีระบบป้องกันบอทแบบเดียวกัน เพราะเจตนาให้ดาวน์โหลดไปใช้ต่อได้อยู่แล้ว

URL pattern ของแหล่งข้อมูล:
    ตั้งใหม่:   https://openapi.dbd.go.th/juristic_person/registration/99_YYYYMM_1.csv
    เลิกกิจการ: https://openapi.dbd.go.th/juristic_person/dissolution/99_YYYYMM_2.csv

⚠️ ข้อจำกัดสำคัญที่ต้องรู้ก่อนใช้: dataset นี้คือ "นิติบุคคลตั้งใหม่ / เลิกกิจการ" แบบรายเดือน
เท่านั้น ไม่ใช่ทะเบียนเต็มรูปแบบของทุกบริษัทที่จดทะเบียนอยู่ในประเทศไทย — บริษัทที่จดทะเบียนมานาน
แล้ว (ก่อนช่วงที่เริ่มดึงข้อมูล) และยังดำเนินกิจการอยู่ตามปกติ (ไม่ได้ "ตั้งใหม่" หรือ "เลิก" ในช่วง
เวลาที่ดึงมา) จะไม่มีอยู่ในฐานข้อมูลนี้เลย เช่น บริษัทที่จดทะเบียนปี 2542 แล้วดึงข้อมูลจากปี 2563
เป็นต้นไป จะไม่เจอบริษัทนั้นแน่นอน — ฟังก์ชัน search_juristic_person ในไฟล์นี้จึงต้องสื่อสารข้อจำกัด
นี้ให้ชัดเจนเสมอเวลาค้นหาไม่เจอ (ไม่ใช่แค่บอกว่า "ไม่พบ" เฉยๆ อาจทำให้เข้าใจผิดว่าบริษัทนั้นไม่มี
อยู่จริง ทั้งที่จริงๆ แค่ไม่อยู่ใน dataset ประเภทนี้)

⚠️ ยังไม่เคยทดสอบดึงข้อมูลจริงจากเว็บนี้เลย — สภาพแวดล้อมที่พัฒนาโค้ดนี้ต่อ openapi.dbd.go.th ไม่ได้
(โดน proxy บล็อกด้วย 403) เขียนโค้ดให้ทนทานที่สุดเท่าที่ทำได้ (ลอง decode หลาย encoding เพราะไฟล์
ภาครัฐไทยบางไฟล์ไม่ใช่ utf-8 เสมอไป, ข้าม 404 ของเดือนที่ยังไม่มีไฟล์ออก, retry เมื่อเจอ error
ชั่วคราว) แต่ยังไม่ยืนยันว่ารูปแบบไฟล์/ชื่อคอลัมน์จริงตรงกับที่เขียนไว้ 100% — ต้องรอผลทดสอบจริงจาก
เครื่องที่ต่อเน็ตไปเว็บนี้ได้ก่อนถึงจะมั่นใจได้
"""

from __future__ import annotations

import csv
import io
import sqlite3
from datetime import date
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "reference" / "dbd_juristic_local.db"
BASE_URL = "https://openapi.dbd.go.th/juristic_person"
DEFAULT_START_YEAR = 2020
DEFAULT_START_MONTH = 1
USER_AGENT = "Mozilla/5.0 (compatible; NoAMR-DBD-OpenData-Fetcher/1.0)"

ProgressCallback = Callable[[str], None]


def _noop(_: str) -> None:
    pass


def month_range(start_year: int, start_month: int, end_year: int, end_month: int) -> Iterable[Tuple[int, int]]:
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def build_url(kind: str, year: int, month: int) -> str:
    yyyymm = f"{year:04d}{month:02d}"
    if kind == "registration":
        return f"{BASE_URL}/registration/99_{yyyymm}_1.csv"
    if kind == "dissolution":
        return f"{BASE_URL}/dissolution/99_{yyyymm}_2.csv"
    raise ValueError(f"unknown kind: {kind}")


def fetch_csv_text(
    url: str, log: ProgressCallback = _noop, retries: int = 3, timeout: float = 30.0
) -> Optional[str]:
    """ดึงไฟล์ CSV จาก url แล้วลอง decode ด้วยหลาย encoding (ไฟล์ภาครัฐไทยบางไฟล์ไม่ได้เป็น
    utf-8 เสมอไป — พบบ่อยว่าเป็น cp874/tis-620 แทน) คืน None ถ้าไม่มีไฟล์ (404 — ปกติสำหรับเดือน
    ที่ยังไม่ถึง/ยังไม่ปล่อยไฟล์) หรือดึงไม่สำเร็จแม้ retry ครบแล้ว"""

    import time as _time

    request = Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, retries + 1):
        try:
            with urlopen(request, timeout=timeout) as resp:
                raw = resp.read()
            for enc in ("utf-8-sig", "utf-8", "cp874", "tis-620"):
                try:
                    return raw.decode(enc)
                except UnicodeDecodeError:
                    continue
            log(f"⚠️ decode {url} ไม่สำเร็จด้วย encoding ที่รู้จักเลย ({len(raw)} ไบต์)")
            return None
        except HTTPError as e:
            if e.code == 404:
                return None  # ไม่มีไฟล์เดือนนี้ (เช่น เดือนอนาคต) ถือเป็นปกติ ไม่ใช่ error
            if attempt == retries:
                log(f"⚠️ [HTTPError {e.code}] {url}")
                return None
        except URLError as e:
            if attempt == retries:
                log(f"⚠️ [URLError] {url}: {e}")
                return None
        _time.sleep(1.5 * attempt)
    return None


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS juristic_person (
            reg_id TEXT,
            name TEXT,
            reg_date TEXT,
            capital TEXT,
            purpose_code TEXT,
            purpose TEXT,
            address TEXT,
            subdistrict TEXT,
            district TEXT,
            province TEXT,
            postcode TEXT,
            status TEXT,        -- 'registration' หรือ 'dissolution'
            source_month TEXT,  -- 'YYYY-MM' ไฟล์ต้นทาง
            UNIQUE(reg_id, status, source_month)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_juristic_person_name ON juristic_person(name)")
    conn.commit()


def _get_field(row: Dict[str, str], *keys: str) -> str:
    """หัวคอลัมน์ของไฟล์ DBD อาจเปลี่ยนเล็กน้อยตามช่วงเวลาที่ปล่อยไฟล์ (เช่น "ชื่อนิติบุคคล" กับ
    "ชื่อนิติบุคคล (ไทย)") — เทียบแบบยืดหยุ่นโดยไล่หาคีย์ที่ใกล้เคียงที่สุดในลิสต์ที่ให้มา"""

    for k in keys:
        for col in row:
            if col and col.strip() == k:
                return (row[col] or "").strip()
    return ""


def normalize_row(row: Dict[str, str], status: str, source_month: str) -> tuple:
    return (
        _get_field(row, "เลขทะเบียน", "เลขทะเบียนนิติบุคคล"),
        _get_field(row, "ชื่อนิติบุคคล", "ชื่อนิติบุคคล (ไทย)"),
        _get_field(row, "วันที่จดทะเบียน", "วันที่จดทะเบียนเลิก", "วันที่จดทะเบียนจัดตั้ง"),
        _get_field(row, "ทุนจดทะเบียน"),
        _get_field(row, "รหัสวัตถุประสงค์"),
        _get_field(row, "วัตถุประสงค์"),
        _get_field(row, "ที่ตั้งสำนักงานใหญ่"),
        _get_field(row, "ตำบล"),
        _get_field(row, "อำเภอ"),
        _get_field(row, "จังหวัด"),
        _get_field(row, "รหัสไปรษณีย์"),
        status,
        source_month,
    )


def load_csv_into_db(conn: sqlite3.Connection, csv_text: str, status: str, source_month: str) -> int:
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = [normalize_row(row, status, source_month) for row in reader]
    if not rows:
        return 0
    conn.executemany(
        """
        INSERT OR IGNORE INTO juristic_person
        (reg_id, name, reg_date, capital, purpose_code, purpose,
         address, subdistrict, district, province, postcode, status, source_month)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def fetch_all(
    start_year: int = DEFAULT_START_YEAR,
    start_month: int = DEFAULT_START_MONTH,
    end_date: Optional[Tuple[int, int]] = None,
    kinds: Tuple[str, ...] = ("registration", "dissolution"),
    db_path: Path = DEFAULT_DB_PATH,
    log: ProgressCallback = _noop,
) -> dict:
    """ดึงไฟล์ CSV รายเดือนทุกเดือนตั้งแต่ start_year/start_month จนถึง end_date (ค่าเริ่มต้น:
    เดือนปัจจุบัน) แล้วโหลดเข้าฐานข้อมูล SQLite ที่ db_path (สร้างไฟล์ใหม่ถ้ายังไม่มี, เพิ่มข้อมูล
    ต่อจากเดิมถ้ามีอยู่แล้ว — ใช้ UNIQUE constraint กันไม่ให้ซ้ำถ้ารันซ้ำ) คืน dict สรุปผล"""

    if end_date is None:
        today = date.today()
        end_year, end_month = today.year, today.month
    else:
        end_year, end_month = end_date

    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    init_db(conn)

    total_rows = 0
    months_with_data = 0
    months_tried = 0
    try:
        for y, m in month_range(start_year, start_month, end_year, end_month):
            source_month = f"{y:04d}-{m:02d}"
            for kind in kinds:
                months_tried += 1
                url = build_url(kind, y, m)
                log(f"📥 ดึง {kind} {source_month} ...")
                text = fetch_csv_text(url, log=log)
                if text is None:
                    log(f"⏭️ ไม่มีไฟล์/ดึงไม่สำเร็จ ข้าม ({kind} {source_month})")
                    continue
                n = load_csv_into_db(conn, text, kind, source_month)
                total_rows += n
                if n:
                    months_with_data += 1
                log(f"✅ {kind} {source_month}: {n} แถว")
    finally:
        conn.close()

    log(f"🏁 เสร็จสิ้น รวมทั้งหมด {total_rows} แถว จาก {months_with_data}/{months_tried} ไฟล์ที่มีข้อมูล (บันทึกลง {db_path})")
    return {
        "total_rows": total_rows,
        "months_with_data": months_with_data,
        "months_tried": months_tried,
        "db_path": str(db_path),
    }


def is_db_available(db_path: Path = DEFAULT_DB_PATH) -> bool:
    """เช็คว่ามีฐานข้อมูลที่ดึงไว้แล้วในเครื่องนี้หรือยัง (มีไฟล์ + มีตาราง + มีข้อมูลอย่างน้อย
    1 แถว) — ใช้บอกผู้ใช้ว่าต้องกด "ดึงข้อมูล" ก่อนถึงจะค้นหาได้ ไม่ใช่ปล่อยให้ error ไม่ชัดเจน"""

    db_path = Path(db_path)
    if not db_path.exists():
        return False
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            cur = conn.execute("SELECT COUNT(*) FROM juristic_person LIMIT 1")
            return (cur.fetchone() or (0,))[0] > 0
        finally:
            conn.close()
    except sqlite3.Error:
        return False


def search_juristic_person(name_query: str, db_path: Path = DEFAULT_DB_PATH, limit: int = 50) -> List[dict]:
    """ค้นหาชื่อบริษัทจากฐานข้อมูลที่ดึงไว้ในเครื่องแล้ว (ไม่ต่อเน็ต) — คืน list ว่างถ้ายังไม่เคย
    ดึงข้อมูลมาเลย (ไม่มีไฟล์ db) หรือค้นหาไม่เจอ — ดู docstring หัวไฟล์เรื่องข้อจำกัดของ dataset
    (ครอบคลุมแค่บริษัทตั้งใหม่/เลิกกิจการ ไม่ใช่ทะเบียนเต็ม) ผู้เรียกควรสื่อสารข้อจำกัดนี้ต่อผู้ใช้
    เสมอเวลาค้นหาไม่เจอ"""

    db_path = Path(db_path)
    if not db_path.exists():
        return []

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            """
            SELECT * FROM juristic_person
            WHERE name LIKE ?
            ORDER BY reg_date DESC
            LIMIT ?
            """,
            (f"%{name_query}%", limit),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
