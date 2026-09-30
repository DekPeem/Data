"""รวบรวมข้อมูล AMR จริง (รายงาน 15 นาทีจาก PEA) ที่แอดมินอัปโหลดเข้ามา จัดเก็บแยกตามประเภทธุรกิจ
(TSIC) แล้ววาดกราฟ Boxplot แสดงการกระจายตัวจริงของการใช้ไฟรายชั่วโมง — ใช้เป็นข้อมูลอ้างอิงให้
ผู้ใช้ไฟรายที่ "ยังไม่มี AMR ของตัวเอง" ดูว่าธุรกิจประเภทเดียวกันในระบบใช้ไฟเป็นรูปแบบไหนบ้างจริงๆ
(ต่างจาก forecast_shape.py ที่สร้างเส้นโค้งสมมติจากแค่ตัวเลขบิล — อันนี้คือข้อมูลวัดจริง)

พอร์ตมาจากสคริปต์ CLI แบบ standalone (load_boxplot.py — วิ่งด้วย pandas/numpy/matplotlib ในเครื่อง
ผู้ใช้เอง) ตัดส่วน argparse/CLI + ฟีเจอร์จำลอง demand-response (--drop / เส้น target หลังลด peak)
ออก เพราะฟีเจอร์นั้นถูกตัดออกจากทั้งระบบไปแล้ว เหลือแค่การอ่านไฟล์ + คำนวณ box stats + วาดกราฟ

⚠️ ไฟล์ AMR ดิบที่อัปโหลดเข้ามามีข้อมูลระบุตัวตนลูกค้า (ชื่อบริษัท/เลขบัญชี/เลขมิเตอร์) — โมดูลนี้
อ่านเฉพาะตัวเลขกำลังไฟฟ้า (kW) รายช่วงเวลา 15 นาที เก็บลงไฟล์ local-only เท่านั้น
(amr_boxplot_intervals_local.csv — อยู่ใน .gitignore ห้าม commit เด็ดขาด เหมือนหลักการเดียวกับ
customers_local.csv) เดิมไม่เก็บชื่อ/เลขบัญชีลูกค้าเลยเพื่อความเป็นส่วนตัว แต่ผู้ใช้ยืนยันชัดเจน
ว่าอยากให้แยก/ระบุบัญชีที่มาของแต่ละแถวได้ (เพื่อดูว่าอัปโหลดบัญชีไหนไปแล้วบ้าง ไม่ต้องเดา) จึงเพิ่ม
คอลัมน์ account_no/company_name/registration_no เป็น "ไม่บังคับ" ทั้งหมด (ไม่ใส่ก็ยังใช้งานได้
ปกติ เว้นว่างไว้เฉยๆ) — account_no คือเลขบัญชีผู้ใช้ไฟของ PEA (ใช้กับหน้าดึง AMR อัตโนมัติ) ส่วน
registration_no คือเลขทะเบียนนิติบุคคล 13 หลักของ DBD (คนละความหมายกัน บริษัทเดียวมีได้หลายบัญชี
PEA แต่มีเลขทะเบียนเดียว) — ไฟล์นี้เป็น local-only อยู่แล้วไม่เคย commit เข้า git เลย จึงยังไม่
กระทบความเป็นส่วนตัวของใครนอกเครื่องที่รันอยู่ (ดู web/app.py จุดที่เรียก append_intervals_local
ว่าใส่ฟิลด์เหล่านี้มาจากไหนบ้าง — โหมดตรวจจับอัตโนมัติจาก PEA ได้ account_no/company_name มาฟรีจาก
หน้าโปรไฟล์อยู่แล้ว (PEA ไม่มีเลขทะเบียนนิติบุคคลให้) โหมดแนบไฟล์เองต้องกรอกเองทั้งหมด)
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import matplotlib

matplotlib.use("Agg")  # เซิร์ฟเวอร์ไม่มีจอแสดงผล — ต้องตั้งก่อน import pyplot เสมอ

import numpy as np
import pandas as pd

COLORS = {"P": "#eb6834", "OP": "#1baf7a", "H": "#6250d6"}
THAI_FONTS = ["Noto Sans Thai", "Sarabun", "TH Sarabun New", "Tahoma", "Leelawadee UI", "Thonburi"]

_INTERVAL_FIELDNAMES = ["business_type_code", "account_no", "company_name", "registration_no", "date", "hour", "rate", "kw"]

DEFAULT_SHUTDOWN_KW = 150.0


@dataclass(frozen=True)
class ParsedInterval:
    date: str  # YYYY-MM-DD
    hour: int
    minute: int  # 0/15/30/45 — เก็บไว้แค่แยกแยะ 4 จุดข้อมูลต่อชั่วโมงตอน dedup เท่านั้น ไม่ได้
    # เขียนลงไฟล์ storage (box stats จัดกลุ่มแค่ระดับชั่วโมง ไม่สนนาที)
    rate: str  # "P" | "OP" | "H"
    kw: float


def _strip_leading_index_row(df: pd.DataFrame) -> pd.DataFrame:
    """ไฟล์ .xlsx จริง (Excel 2007+ binary ไม่ใช่ HTML table ที่ตั้งนามสกุลเป็น .xls/.xlsx เฉยๆ แบบ
    เดิม) ที่ดาวน์โหลดจาก amr.pea.co.th มี 1 แถวขยะบนสุดของทุกชีตเป็นตัวเลข index คอลัมน์ล้วนๆ
    (0,1,2,...) ปนมาด้วยเสมอ (ไม่รู้สาเหตุ น่าจะเป็น artifact จากเครื่องมือ export ของ PEA เอง) ต้อง
    ตัดทิ้งก่อนเทียบโครงสร้างกับไฟล์ HTML-in-.xls แบบเดิม — เช็คว่าแถวแรกเท่ากับ index คอลัมน์ตัวเอง
    เป๊ะก่อนตัด กันพลาดตัดแถวข้อมูลจริงทิ้งถ้าไฟล์บางรูปแบบในอนาคตไม่มีแถวขยะนี้ (เทียบด้วย str()
    ทั้งสองฝั่งเสมอ เพราะ df อ่านมาด้วย dtype=str แต่ df.columns ยังเป็น int ธรรมดา — เทียบตรงๆ แบบ
    ไม่แปลงชนิดข้อมูลก่อนจะไม่ match กันเลยสักแถว)"""

    if len(df) and [str(x) for x in df.iloc[0]] == [str(x) for x in df.columns]:
        return df.iloc[1:].reset_index(drop=True)
    return df


def _load_report_tables(path: Union[str, Path]) -> List[pd.DataFrame]:
    """โหลดตาราง 3 ตัวจากไฟล์รายงาน AMR ดิบ 1 ไฟล์ (header/ข้อมูลจริง/ท้ายรายงาน) รองรับทั้ง 2
    รูปแบบไฟล์ที่ปล่อยให้โหลดจาก amr.pea.co.th: (1) ไฟล์ HTML table ที่ตั้งนามสกุลเป็น .xls/.xlsx
    เฉยๆ (รูปแบบเดิม แกะด้วย pd.read_html) และ (2) ไฟล์ .xlsx จริง (Excel 2007+ binary — เจอจากไฟล์
    ตัวอย่างจริงของผู้ใช้ที่อัปโหลดไม่ได้ด้วยโค้ดเดิม มี 3 ชีตเรียงลำดับตรงกับ 3 ตารางเดียวกันเป๊ะ:
    Sheet1=header, Sheet2=ข้อมูลจริง, Sheet3=ท้ายรายงาน) เช็คจาก magic bytes "PK" ของไฟล์ zip/xlsx
    จริงก่อนเสมอ ไม่เดาจากนามสกุลไฟล์ (นามสกุล .xlsx เจอได้ทั้ง 2 รูปแบบ)"""

    raw = Path(path).read_bytes()
    if raw[:2] == b"PK":  # ไฟล์ .xlsx จริง (Excel 2007+ เป็นไฟล์ zip ข้างใน)
        # dtype=str บังคับให้อ่านทุกคอลัมน์เป็นข้อความดิบเสมอ — ไม่งั้น pandas เดา dtype ของคอลัมน์
        # เอง แล้วคอลัมน์ที่ค่าดูเหมือนตัวเลขล้วน (เช่น เลขบัญชี/เลขมิเตอร์ที่ไม่มีเลข 0 นำหน้าปนอยู่
        # เลยสักแถว) จะถูกแปลงเป็น float ทั้งคอลัมน์ ทำให้เลขบัญชีที่มี 0 นำหน้าหายไป (เช่น
        # "020027862234" กลายเป็น "20027862234.0") เจอบั๊กนี้จริงจากไฟล์ตัวอย่างจริงของผู้ใช้ที่เลข
        # บัญชีในคอลัมน์นั้นไม่มีอักขระอื่นปนเลยสักแถว (ไฟล์แบบอื่นรอดเพราะมี "\xa0" ต่อท้ายอยู่แล้ว
        # ทำให้ pandas เดาว่าเป็นคอลัมน์ข้อความไปเอง ไม่ได้แก้บั๊กนี้จริง แค่บังเอิญไม่โดน)
        sheets = pd.read_excel(io.BytesIO(raw), sheet_name=None, header=None, dtype=str)
        return [_strip_leading_index_row(df) for df in sheets.values()]
    html = raw.decode("utf-8", errors="ignore")
    return pd.read_html(io.StringIO(html))


def _sheet_contains_text(df: pd.DataFrame, text: str, max_rows: int = 15) -> bool:
    """เช็คว่ามีเซลล์ไหนในชีต (แค่ max_rows แถวบนสุด — หัวรายงานอยู่ไม่กี่แถวบนสุดเสมอ ไม่ต้องไล่
    ทั้งชีตซึ่งอาจยาวเป็นพันแถว) มีข้อความ text อยู่บ้าง ใช้แยกแยะว่าไฟล์ .xlsx ชีตเดียวที่โหลดมาเป็น
    รายงานแบบไหน (ดู _read_one) จากชื่อรายงานที่พิมพ์ไว้ในไฟล์เอง แม่นยำกว่าเดาจากจำนวนคอลัมน์"""

    for _, row in df.head(max_rows).iterrows():
        for cell in row:
            if pd.notna(cell) and text in str(cell):
                return True
    return False


def _classify_tou_rate(start: pd.Series) -> np.ndarray:
    """เดา rate (P/OP/H) จากวัน/เวลาเริ่มต้นของแต่ละช่วง 15 นาทีเอง ตามกฎ TOU มาตรฐานทั่วไป (จันทร์-
    ศุกร์ 9:00-22:00 = Peak, จันทร์-ศุกร์ช่วงเวลาอื่น = Off-Peak, เสาร์-อาทิตย์ = Holiday) — ใช้เฉพาะ
    ไฟล์รายงาน "Custom kW Report" ที่ไม่มีคอลัมน์ rate แยกให้เลย (รายงานแบบอื่นทุกแบบอ่าน rate จาก
    ตำแหน่งคอลัมน์ในไฟล์ตรงๆ แม่นกว่านี้เสมอ ไม่ต้องเดา ฟังก์ชันนี้ไม่ถูกเรียกเลย) เป็นการประมาณการ
    ทั่วไปตามธรรมเนียมที่ระบบนี้ใช้อยู่แล้ว (ดู helper สร้างไฟล์ทดสอบใน tests/) ไม่ได้ตรวจสอบว่าบัญชี
    นี้ถือสัญญาอัตรา TOU จริงหรือไม่ และไม่รวมวันหยุดนักขัตฤกษ์ (ผู้ใช้ยืนยันให้ใช้วิธีนี้แทนที่จะ
    ปฏิเสธไฟล์รูปแบบนี้ไปเลย เพราะไม่มีข้อมูล rate จริงให้ใช้)"""

    weekday = start.dt.weekday  # 0=จันทร์ ... 5=เสาร์ 6=อาทิตย์
    is_weekday = weekday < 5
    is_peak_hour = (start.dt.hour >= 9) & (start.dt.hour < 22)
    return np.select([is_weekday & is_peak_hour, is_weekday & ~is_peak_hour], ["P", "OP"], "H")


def _read_one_custom_kw(sheet: pd.DataFrame) -> pd.DataFrame:
    """แกะตารางข้อมูลจากไฟล์รายงาน "Custom kW Report" ของ PEA (.xlsx จริง ชีตเดียว ภาษาอังกฤษล้วน
    ไม่มีคอลัมน์ RATE A/B/C หรือช่วงเวลาใดๆ เลย — มีแค่คอลัมน์ "Time"/"kW" คอลัมน์เดียว) หน่วยเป็น
    kW เฉลี่ยตรงๆ อยู่แล้ว (ชื่อรายงานบอกตรงๆ ว่า "kW Report" ไม่ใช่ kWh) แต่ไฟล์ไม่มีข้อมูลบอกเลยว่า
    แต่ละจุดเป็นช่วง Peak/Off-Peak/Holiday — คืน DataFrame คอลัมน์ ts,kw ตรงๆ (โครงสร้างต่างจาก
    รายงานแบบอื่นที่คืน a1/a2/b1/b2/c1/c2 เสมอ) ให้ parse_amr_file รู้ว่าต้องคำนวณ rate จากวัน/เวลา
    เอง (ดู _classify_tou_rate) แทนการอ่านจากตำแหน่งคอลัมน์"""

    d = sheet.iloc[:, :2].copy()
    d.columns = ["ts", "kw"]
    d["ts"] = d["ts"].astype(str).str.replace("\xa0", "", regex=False).str.strip()
    d = d[d["ts"].str.match(r"\d\d/\d\d/\d{4} \d\d\.\d\d")].copy()
    d["kw"] = pd.to_numeric(d["kw"], errors="coerce")
    return d


def _read_one_monthly_kw(sheet: pd.DataFrame) -> pd.DataFrame:
    """แกะตารางข้อมูลจากไฟล์รายงาน "กิโลวัตต์รายเดือน" ของ PEA (.xlsx จริง ชีตเดียว รวม header/
    ข้อมูล/ท้ายรายงานปนกัน เหมือน _read_one_monthly_kwh แต่คนละรายงาน — ไม่มีคำว่า "ชั่วโมง" ในชื่อ
    รายงาน) หน่วยข้อมูลเป็น kW เฉลี่ยตรงๆ อยู่แล้ว ไม่ต้องแปลงหน่วยเหมือนรายงาน "กิโลวัตต์ชั่วโมง
    รายเดือน" (ยืนยันจากแถวสรุป "กิโลวัตต์ต่ำสุด/เฉลี่ย/สูงสุด" ท้ายตารางที่คำนวณตรงจากค่าดิบในไฟล์
    ตัวอย่างจริงพอดีเป๊ะ ไม่ใช่ผลรวมพลังงานแบบรายงานกิโลวัตต์ชั่วโมง) คอลัมน์เป็นคู่เหมือนรายงาน
    "กิโลวัตต์แบบช่วงเวลา" (ts,a1,a2,b1,b2,c1,c2) แต่มีค่าจริงแค่คอลัมน์แรกของแต่ละคู่ (a1/b1/c1)
    คอลัมน์คู่ (a2/b2/c2) ว่างเสมอ — ไม่กระทบผลลัพธ์เพราะ parse_amr_file อ่านแค่ a1/b1/c1 อยู่แล้ว"""

    d = sheet.iloc[:, :7].copy()
    d.columns = ["ts", "a1", "a2", "b1", "b2", "c1", "c2"]
    d["ts"] = d["ts"].astype(str).str.replace("\xa0", "", regex=False).str.strip()
    d = d[d["ts"].str.match(r"\d\d/\d\d/\d{4} \d\d\.\d\d")].copy()
    for c in ("a1", "a2", "b1", "b2", "c1", "c2"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d


def _read_one_monthly_kwh(sheet: pd.DataFrame) -> pd.DataFrame:
    """แกะตารางข้อมูลจากไฟล์รายงาน "กิโลวัตต์ชั่วโมงรายเดือน" ของ PEA (.xlsx จริง ชีตเดียว รวม
    header/ข้อมูล/ท้ายรายงานปนกันหมด ไม่แยก 3 ชีต/ตารางแบบรายงาน "กิโลวัตต์แบบช่วงเวลา" ที่รองรับอยู่
    ก่อนแล้ว) หน่วยข้อมูลเป็น kWh (พลังงานสะสมของช่วง 15 นาทีนั้น ยืนยันจากแถว "ผลรวมทั้งหมด" ท้าย
    ตารางที่เป็นผลรวมพลังงานทั้งเดือน ไม่ใช่ผลรวม kW ซึ่งไม่มีความหมายทางฟิสิกส์) ต้องแปลงเป็น kW
    เฉลี่ยก่อน (หาร 0.25 ชม. เท่ากับคูณ 4) ไม่งั้นค่าจะต่ำกว่าความจริง ~4 เท่าเมื่อไปรวม Boxplot
    เดียวกันกับรายงานแบบ kW เฉลี่ยตรงๆ — คอลัมน์มีแค่ RATE A/B/C คอลัมน์ละ 1 (ไม่ใช่คู่ a1/a2 แบบ
    รายงานอีกแบบ) จึง duplicate ค่าลงคู่คอลัมน์เองให้โครงสร้างผลลัพธ์ตรงกัน ใช้โค้ดคำนวณ rate/kw ร่วม
    กับรายงานอีกแบบต่อได้เลยไม่ต้องแยก (ดู parse_amr_file)

    แถวหัวตาราง/ท้ายตาราง (เช่นแถว "ผลรวมทั้งหมด") ไม่ตรงรูปแบบวันที่จึงถูกกรองทิ้งเองโดย regex
    match ด้านล่าง ไม่ต้องรู้เลขแถวล่วงหน้าเลย — ts ของไฟล์จริงมี non-breaking space (\\xa0) นำหน้า
    เสมอ ต้องตัดออกก่อน match"""

    d = sheet.iloc[:, :5].copy()
    d.columns = ["ts", "a", "b", "c", "total"]
    d["ts"] = d["ts"].astype(str).str.replace("\xa0", "", regex=False).str.strip()
    d = d[d["ts"].str.match(r"\d\d/\d\d/\d{4} \d\d\.\d\d")].copy()
    for c in ("a", "b", "c"):
        d[c] = pd.to_numeric(d[c], errors="coerce") * 4.0
    return pd.DataFrame(
        {"ts": d["ts"], "a1": d["a"], "a2": d["a"], "b1": d["b"], "b2": d["b"], "c1": d["c"], "c2": d["c"]}
    )


def _read_one(tables: List[pd.DataFrame]) -> pd.DataFrame:
    """แกะตารางข้อมูลจริงจากตารางทั้งหมดของไฟล์รายงาน 1 ไฟล์ (จาก _load_report_tables) คืน
    DataFrame คอลัมน์ ts,a1,a2,b1,b2,c1,c2 มาตรฐานเดียวกันเสมอ (kW เฉลี่ยของช่วง 15 นาที) ไม่ว่าไฟล์
    ต้นทางจะเป็นรายงานแบบไหน ยกเว้นรายงาน "Custom kW Report" (ดู _read_one_custom_kw) ที่คืนแค่
    คอลัมน์ ts,kw เพราะไฟล์ไม่มีข้อมูล rate ให้เลย (parse_amr_file ต้องเช็คคอลัมน์ให้ดีก่อนใช้งาน) —
    ไฟล์ที่มีแค่ 1 ชีต/ตาราง (รวม header/ข้อมูล/ท้ายรายงานไว้ด้วยกันหมด) คือรายงานรายเดือน/รายงาน
    กำหนดเองแบบใดแบบหนึ่ง แยกอีกชั้นจากชื่อรายงานที่พิมพ์ไว้ในไฟล์เอง: "Custom kW Report" (ไม่มี
    rate เลย ต้องเดาจากวัน/เวลาเอง), "กิโลวัตต์ชั่วโมงรายเดือน" (หน่วย kWh ต้องแปลง — ดู
    _read_one_monthly_kwh), หรือ "กิโลวัตต์รายเดือน" เฉยๆ (หน่วย kW ตรงอยู่แล้ว — ดู
    _read_one_monthly_kw) ส่วนที่เหลือ (HTML-in-.xls เดิม หรือ .xlsx จริง 3 ชีตแยกกัน) คือรายงาน
    "กิโลวัตต์แบบช่วงเวลา" แบบเดิม — เหมือน load_boxplot.py ต้นฉบับทุกประการ"""

    if len(tables) == 1:
        if _sheet_contains_text(tables[0], "Custom kW Report"):
            return _read_one_custom_kw(tables[0])
        if _sheet_contains_text(tables[0], "กิโลวัตต์ชั่วโมงรายเดือน"):
            return _read_one_monthly_kwh(tables[0])
        return _read_one_monthly_kw(tables[0])

    d = tables[1].iloc[1:].copy()  # table 0 = ข้อมูลหัวรายงาน, 1 = ข้อมูลจริง, 2 = ท้ายรายงาน
    d.columns = ["ts", "a1", "a2", "b1", "b2", "c1", "c2"]
    d = d[d["ts"].astype(str).str.match(r"\d\d/\d\d/\d{4} \d\d\.\d\d")]
    for c in d.columns[1:]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d


def parse_amr_file(path: Union[str, Path]) -> List[ParsedInterval]:
    """อ่านไฟล์ AMR ดิบ 1 ไฟล์ คืนรายการ interval ที่แกะแล้ว (rate=P/OP/H, kw, date, hour) — คืน
    list ว่างถ้าอ่าน/แปลงไม่สำเร็จ (ไม่ raise ทำให้ไฟล์อื่นที่อัปโหลดมาพร้อมกันยังประมวลผลต่อได้)"""

    try:
        df = _read_one(_load_report_tables(path))
    except Exception:  # noqa: BLE001 — ไฟล์เสีย/รูปแบบไม่ตรง ข้ามไปเฉยๆ
        return []

    # ไฟล์ AMR จริงบางไฟล์ (โดยเฉพาะรายงาน AMI) ใช้ปี พ.ศ. (เช่น 2569) ในคอลัมน์วันที่ แทน ค.ศ.
    # (2026) ปนกับไฟล์รูปแบบอื่นที่ใช้ ค.ศ. ตรงๆ — เดาว่าเป็น พ.ศ. ถ้าปีเกิน 2400 (ปี ค.ศ. จริงยังไม่มี
    # ทางเกินหลักพันต้นๆ ไปอีกนาน) ต้องแปลงเป็น ค.ศ. "ก่อน" parse เป็น pd.Timestamp เสมอ (แก้ที่ตัว
    # string ปีตรงๆ) ห้ามลบ 543 ปีออกจาก Timestamp ที่ parse ไปแล้วทีหลังเด็ดขาด เพราะ pandas ประเมิน
    # ทั้งสอง branch ของ .where()/.mask() ล่วงหน้าเสมอ (ไม่ lazy) แถวที่เป็นปี ค.ศ. อยู่แล้ว (เช่น
    # 2026) พอถูกลบ 543 เข้าจะกลายเป็นปี 1483 ซึ่งต่ำกว่าปีต่ำสุดที่ pd.Timestamp รองรับได้ (~1677)
    # ทำให้ OverflowError ทั้งคอลัมน์ทันที ทั้งที่แถวนั้นไม่ควรถูกแตะเลยด้วยซ้ำ (เจอบั๊กนี้จริงจากไฟล์
    # AMR จริงของผู้ใช้ที่ปีมีทั้ง พ.ศ./ค.ศ. ปนกันในไฟล์ชุดเดียวกัน) — ปีอธิกสุรทินของไทยตรงกับปฏิทิน
    # สากลเป๊ะมาตั้งแต่ พ.ศ. 2484 ลบเลขปีตรงๆ ได้เลยไม่ต้องกังวลวันที่ 29 ก.พ. เพี้ยน
    date_part = df["ts"].str[:6]  # "DD/MM/"
    year_part = df["ts"].str[6:10].astype(int)
    is_be_year = year_part > 2400
    ce_year_part = (year_part - 543).where(is_be_year, year_part).astype(str).str.zfill(4)
    day = pd.to_datetime(date_part + ce_year_part, format="%d/%m/%Y", errors="coerce")
    mins = df["ts"].str[11:13].astype(int) * 60 + df["ts"].str[14:16].astype(int)
    end = day + pd.to_timedelta(mins, unit="m")
    start = end - pd.Timedelta(minutes=15)

    if "kw" in df.columns:
        # รายงาน "Custom kW Report" (ดู _read_one_custom_kw) ไม่มีคอลัมน์ rate แยกให้เลย ต้องเดาจาก
        # วัน/เวลาเอง (ผู้ใช้ยืนยันให้ใช้วิธีนี้แทนที่จะปฏิเสธไฟล์รูปแบบนี้ไปเลย — ดู _classify_tou_rate)
        rate = _classify_tou_rate(start)
        kw = df["kw"]
    else:
        rate = np.select([df.a1.notna(), df.b1.notna(), df.c1.notna()], ["P", "OP", "H"], "?")
        kw = df[["a1", "b1", "c1"]].bfill(axis=1).iloc[:, 0]

    out: List[ParsedInterval] = []
    for s, r, k in zip(start, rate, kw):
        if r == "?" or pd.isna(s) or pd.isna(k):
            continue
        out.append(ParsedInterval(date=s.strftime("%Y-%m-%d"), hour=int(s.hour), minute=int(s.minute), rate=str(r), kw=float(k)))
    return out


def parse_amr_files(paths: List[Union[str, Path]]) -> List[ParsedInterval]:
    """อ่านไฟล์ AMR ดิบหลายไฟล์รวมกัน (เช่น หลายเดือนของบริษัทเดียวกัน) — ตัดรายการซ้ำทิ้งด้วย
    (date, hour, minute, rate ตรงกันเป๊ะถือว่าซ้ำ — ไฟล์ที่มาซ้ำซ้อนกันบางเดือนจะไม่ถูกนับ 2 รอบ)
    ต้องเทียบถึงระดับนาทีด้วย ไม่ใช่แค่ชั่วโมง เพราะ 1 ชั่วโมงมี 4 จุดข้อมูล (ทุก 15 นาที) ถ้าเทียบ
    แค่ (date, hour) จะเข้าใจผิดว่าจุดข้อมูลปกติ 4 จุดต่อชั่วโมงเป็นของซ้ำกันแล้วทิ้งไป 3 ใน 4 จุด"""

    seen = set()
    out: List[ParsedInterval] = []
    for p in paths:
        for interval in parse_amr_file(p):
            key = (interval.date, interval.hour, interval.minute, interval.rate)
            if key in seen:
                continue
            seen.add(key)
            out.append(interval)
    return out


def extract_customer_info(path: Union[str, Path]) -> Tuple[str, str]:
    """หาเลขบัญชีผู้ใช้ไฟ + ชื่อผู้ใช้ไฟ จากตารางหัวรายงาน (tables[0] — ตัวที่ parse_amr_file ข้าม
    ไปเฉยๆ) ของไฟล์ AMR จริง 1 ไฟล์ — คืน ("", "") ถ้าอ่าน/หาไม่เจอ (ไม่ raise เหมือน parse_amr_file
    ปล่อยให้ผู้ใช้กรอกเองแทนตอนหาไม่เจอ) โครงสร้างยืนยันจากไฟล์ตัวอย่างจริงของผู้ใช้แล้ว (รายงาน
    "ข้อมูลกิโลวัตต์แบบช่วงเวลา" จากเว็บ amr.pea.co.th): tables[0] มีแถวหนึ่งที่คอลัมน์หนึ่งเป็น
    ข้อความ "บัญชีผู้ใช้ไฟ :" ตามด้วยเลขบัญชีในคอลัมน์ถัดไปทันที และอีกคู่คอลัมน์ในแถวเดียวกันเป็น
    "ชื่อผู้ใช้ไฟ :" ตามด้วยชื่อบริษัทในคอลัมน์ถัดไป (pandas.read_html แกะ &nbsp;/ช่องว่างหัวท้าย
    ให้เรียบร้อยแล้วในตัว ไม่ต้อง strip เพิ่ม แต่ strip ไว้กันเหนียวเผื่อโครงสร้างเปลี่ยนเล็กน้อย)"""

    try:
        header = _load_report_tables(path)[0]
    except Exception:  # noqa: BLE001 — ไฟล์เสีย/รูปแบบไม่ตรง/ไม่มี tables[0] เลย ถือว่าหาไม่เจอ
        return "", ""

    # รายงาน "Custom kW Report" เป็นภาษาอังกฤษล้วน ใช้ป้ายกำกับ "Contact Account :" แทน "บัญชีผู้ใช้ไฟ
    # :" (และไม่มีชื่อบริษัทให้เลย — company_name จะว่างเสมอสำหรับรายงานแบบนี้ ต้องกรอกเองในฟอร์ม)
    account_no = ""
    company_name = ""
    for _, row in header.iterrows():
        cells = [str(c).strip() if pd.notna(c) else "" for c in row]
        for i, cell in enumerate(cells):
            if ("บัญชีผู้ใช้ไฟ" in cell or "Contact Account" in cell) and i + 1 < len(cells):
                account_no = cells[i + 1]
            if "ชื่อผู้ใช้ไฟ" in cell and i + 1 < len(cells):
                company_name = cells[i + 1]
    return account_no, company_name


def extract_customer_info_from_files(paths: List[Union[str, Path]]) -> Tuple[str, str]:
    """เหมือน extract_customer_info แต่รับหลายไฟล์พร้อมกัน (เช่น อัปโหลดพร้อมกันหลายเดือนของบัญชี
    เดียวกัน) คืนค่าจากไฟล์แรกที่หาเจอครบทั้งคู่ (ทุกไฟล์ของบัญชีเดียวกันควรมีค่าตรงกันหมดอยู่แล้ว
    ไม่ต้องรวม/เช็คว่าตรงกันเป๊ะทุกไฟล์) คืน ("", "") ถ้าไม่มีไฟล์ไหนหาเจอเลย"""

    for p in paths:
        account_no, company_name = extract_customer_info(p)
        if account_no or company_name:
            return account_no, company_name
    return "", ""


def _migrate_intervals_file_header_if_needed(path: Path) -> None:
    """ไฟล์ local ที่มีอยู่แล้วจากก่อนเพิ่มคอลัมน์ account_no/company_name (header เก่ามีแค่
    business_type_code, date, hour, rate, kw) ต้อง migrate header ก่อนจะ append แถวใหม่ที่มี
    คอลัมน์มากกว่าเดิม ไม่งั้นคอลัมน์จะเลื่อนไม่ตรงกันทั้งไฟล์ — อ่านทั้งไฟล์เดิมมาเติมคอลัมน์ใหม่ว่าง
    ("" ไม่ทราบบัญชี/บริษัท — แถวเก่าไม่มีทางย้อนไปรู้ได้) แล้วเขียนทับด้วย header ใหม่ ทำครั้งเดียว
    ตอน append ครั้งแรกหลังอัปเดตโค้ด (ถ้า header ตรงกับปัจจุบันอยู่แล้วไม่ทำอะไรเลย)"""

    import csv

    if not path.exists():
        return
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames == _INTERVAL_FIELDNAMES:
            return  # header ตรงกับปัจจุบันอยู่แล้ว ไม่ต้อง migrate
        rows = list(reader)

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_INTERVAL_FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in _INTERVAL_FIELDNAMES})


def append_intervals_local(
    business_type_code: str,
    intervals: List[ParsedInterval],
    path: Path,
    account_no: str = "",
    company_name: str = "",
    registration_no: str = "",
) -> int:
    """เพิ่มข้อมูล interval ที่อ่านมาแล้วต่อท้ายไฟล์ local — account_no/company_name/registration_no
    ไม่บังคับทั้งหมด (เว้นว่างไว้ได้ถ้าไม่รู้/ไม่อยากระบุ) ใส่มาเพื่อให้แยกดูได้ภายหลังว่าข้อมูลแต่ละ
    ก้อนมาจากบัญชี/บริษัทไหนบ้าง (ดู summarize_available_by_account) คืนจำนวนแถวที่เพิ่มจริง"""

    import csv

    _migrate_intervals_file_header_if_needed(path)

    file_exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_INTERVAL_FIELDNAMES, lineterminator="\n")
        if not file_exists:
            writer.writeheader()
        for interval in intervals:
            writer.writerow(
                {
                    "business_type_code": business_type_code,
                    "account_no": account_no,
                    "company_name": company_name,
                    "registration_no": registration_no,
                    "date": interval.date,
                    "hour": interval.hour,
                    "rate": interval.rate,
                    "kw": interval.kw,
                }
            )
    return len(intervals)


def remove_interval_rows(path: Path, business_type_code: str, account_no: str) -> int:
    """ลบ interval ทั้งหมดของ (business_type_code, account_no) คู่หนึ่งทิ้งจากไฟล์ local ถาวร —
    account_no="" หมายถึงลบเฉพาะกลุ่ม "ไม่ระบุบัญชี" ของ TSIC นั้น (ไม่ใช่ลบทุกบัญชีของ TSIC นั้น
    ทั้งหมด) ใช้ตอนอยากล้างข้อมูลเก่าที่ไม่มีเลขบัญชีติดมา (ก่อนเพิ่มฟีเจอร์ account tracking) หรือ
    ข้อมูลที่อัปโหลดผิด — ไม่มีทาง undo ได้เลย (เขียนทับไฟล์ตรงๆ) ฝั่งเรียกใช้ (web/app.py) ต้องให้
    ผู้ใช้ยืนยันก่อนเสมอ คืนจำนวนแถวที่ลบจริง (0 ถ้าไม่มีไฟล์/ไม่มีแถวตรงเงื่อนไขเลย)"""

    import csv

    if not path.exists():
        return 0
    _migrate_intervals_file_header_if_needed(path)

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    keep = []
    removed = 0
    for row in rows:
        if row.get("business_type_code") == business_type_code and (row.get("account_no") or "") == account_no:
            removed += 1
        else:
            keep.append(row)

    if removed:
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_INTERVAL_FIELDNAMES, lineterminator="\n")
            writer.writeheader()
            for row in keep:
                writer.writerow({name: row.get(name, "") for name in _INTERVAL_FIELDNAMES})
    return removed


def load_intervals_local(path: Path, business_type_code: Optional[str] = None, account_no: Optional[str] = None) -> pd.DataFrame:
    """โหลดข้อมูล interval จริงทั้งหมด (หรือกรองเฉพาะ business_type_code/account_no) คืน DataFrame
    ว่างถ้ายังไม่มีไฟล์เลย/ไม่มีข้อมูลตรงเงื่อนไข — account_no=None (ค่าเริ่มต้น) คือไม่กรองตามบัญชี
    เลย (รวมทุกบัญชี) ส่วน account_no="" คือกรองเฉพาะกลุ่ม "ไม่ระบุบัญชี" เท่านั้น (คนละความหมายกับ
    None — ดู remove_interval_rows ที่ใช้ธรรมเนียมเดียวกันอยู่แล้ว)"""

    if not path.exists():
        return pd.DataFrame(columns=_INTERVAL_FIELDNAMES)
    # business_type_code/account_no ต้องอ่านเป็น string เสมอ (ไม่งั้น pandas เดาว่าเป็น int ถ้ารหัส/
    # เลขบัญชีเป็นตัวเลขล้วน เช่น "55101" ทำให้เทียบกับค่าที่ส่งเข้ามา (string) ไม่ตรงกันเงียบๆ)
    df = pd.read_csv(path, encoding="utf-8-sig", dtype={"business_type_code": str, "account_no": str, "registration_no": str})
    # ไฟล์เก่าก่อนเพิ่มคอลัมน์เหล่านี้ (ยังไม่เคย append ใหม่เลยหลังอัปเดตโค้ด — ดู
    # _migrate_intervals_file_header_if_needed) จะไม่มีคอลัมน์นี้เลย เติมว่างไว้กันโค้ดฝั่งเรียกใช้
    # (เช่น summarize_available_by_account) KeyError
    for col in ("account_no", "company_name", "registration_no"):
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("")
    if business_type_code:
        df = df[df["business_type_code"] == business_type_code]
    if account_no is not None:
        df = df[df["account_no"] == account_no]
    return df


def compute_bill_stats_from_intervals(intervals: List[ParsedInterval]) -> Dict[str, dict]:
    """สรุป Peak (kW) / หน่วยไฟ (kWh) / จำนวนวัน จาก interval จริงที่อ่านมาแล้ว แยกตาม rate
    (P/OP/H) — ใช้ป้อนให้ forecast_shape.forecast_shape_png แทนการให้แอดมินพิมพ์ตัวเลขจากบิลเอง
    (ดู web/app.py api_forecast_shape_from_files) แต่ละ interval คือช่วง 15 นาที (kw คือกำลังไฟฟ้า
    เฉลี่ยของช่วงนั้น ไม่ใช่หน่วยไฟสะสม) จึงต้องคูณ 0.25 ชม. ก่อนรวมเป็นหน่วยไฟ (kWh) ไม่ใช่บวก kw
    ตรงๆ — คืนเฉพาะ rate ที่มีข้อมูลจริงเท่านั้น (เช่น ไฟล์ที่แนบมาไม่มีวันหยุดเลย จะไม่มีคีย์ "H")"""

    by_rate: Dict[str, List[ParsedInterval]] = {}
    for iv in intervals:
        if iv.rate not in ("P", "OP", "H"):
            continue
        by_rate.setdefault(iv.rate, []).append(iv)

    out: Dict[str, dict] = {}
    for rate, ivs in by_rate.items():
        out[rate] = {
            "peak": max(iv.kw for iv in ivs),
            "energy_kwh": sum(iv.kw for iv in ivs) * 0.25,
            "days": len({iv.date for iv in ivs}),
        }
    return out


def summarize_available(path: Path) -> Dict[str, dict]:
    """สรุปว่าแต่ละ business_type_code มีข้อมูล AMR จริงสะสมไว้เท่าไหร่แล้ว (จำนวน interval +
    จำนวนวันที่ต่างกัน) — ใช้แสดงในหน้า Admin"""

    if not path.exists():
        return {}
    df = pd.read_csv(path, encoding="utf-8-sig", dtype={"business_type_code": str})
    if df.empty:
        return {}
    out: Dict[str, dict] = {}
    for code, sub in df.groupby("business_type_code"):
        out[str(code)] = {"intervals": len(sub), "days": sub["date"].nunique()}
    return out


def summarize_available_by_account(path: Path) -> List[dict]:
    """เหมือน summarize_available แต่แยกรายละเอียดเป็นราย (TSIC, เลขบัญชี) แทนที่จะรวมทุกบัญชีของ
    TSIC เดียวกันเข้าด้วยกันเป็นตัวเลขเดียว — ใช้แสดงในหน้า Admin ให้เห็นชัดๆ ว่าแต่ละบัญชี/บริษัท
    มีข้อมูลสะสมไว้เท่าไหร่แยกกัน (ผู้ใช้ยืนยันอยากได้แบบนี้ ไม่อยากเห็นแค่ยอดรวมต่อ TSIC) แถวที่ไม่
    เคยระบุเลขบัญชีไว้เลย (account_no ว่าง — เช่นอัปโหลดจากโหมดแนบไฟล์เองแบบเดิมก่อนมีฟีเจอร์นี้ หรือ
    ไม่ได้กรอกเลขบัญชีตอนอัปโหลด) จะถูกรวมเป็น 1 แถว "ไม่ระบุบัญชี" ต่อ TSIC แทน ไม่ใช่แยกทีละแถว
    เปล่าๆ (บอกไม่ได้อยู่ดีว่าเป็นคนละบัญชีกันจริงไหม) คืน list เรียงจากจุดข้อมูลเยอะไปน้อย"""

    if not path.exists():
        return []
    df = pd.read_csv(path, encoding="utf-8-sig", dtype={"business_type_code": str, "account_no": str, "registration_no": str})
    if df.empty:
        return []
    for col in ("account_no", "company_name", "registration_no"):
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("")

    out: List[dict] = []
    for (code, account_no), sub in df.groupby(["business_type_code", "account_no"], dropna=False):
        company_name = next((n for n in sub["company_name"] if n), "")
        registration_no = next((n for n in sub["registration_no"] if n), "")
        out.append(
            {
                "business_type_code": str(code),
                "account_no": str(account_no),
                "company_name": company_name,
                "registration_no": registration_no,
                "intervals": len(sub),
                "days": int(sub["date"].nunique()),
            }
        )
    out.sort(key=lambda r: r["intervals"], reverse=True)
    return out


def _box_stats(values_by_hour: Dict[int, List[float]]) -> List[dict]:
    """per-hour stats แบบ matplotlib bxp format (whiskers = P5..P95, flier = max) — เหมือน
    load_boxplot.py ต้นฉบับทุกประการ"""

    out = []
    for h in range(24):
        v = np.array(values_by_hour.get(h, []), dtype=float)
        if v.size == 0:
            out.append(dict(med=0, q1=0, q3=0, whislo=0, whishi=0, fliers=[]))
            continue
        p5, q1, med, q3, p95 = np.percentile(v, [5, 25, 50, 75, 95])
        out.append(dict(med=med, q1=q1, q3=q3, whislo=p5, whishi=p95, fliers=[v.max()]))
    return out


def _setup_font() -> bool:
    from matplotlib import font_manager as fm

    names = {f.name for f in fm.fontManager.ttflist}
    for n in THAI_FONTS:
        if n in names:
            matplotlib.rcParams["font.family"] = n
            return True
    return False


def _values_by_hour(df: pd.DataFrame) -> Dict[int, List[float]]:
    grouped: Dict[int, List[float]] = {h: [] for h in range(24)}
    for hour, kw in zip(df["hour"], df["kw"]):
        grouped[int(hour)].append(float(kw))
    return grouped


def render_boxplot_png(
    df: pd.DataFrame,
    business_type_code: str,
    business_type_name: str = "",
    shutdown_kw: float = DEFAULT_SHUTDOWN_KW,
    subtitle: str = "",
) -> bytes:
    """วาด boxplot จาก DataFrame ของ interval จริง (คอลัมน์ date/hour/rate/kw) คืน PNG bytes —
    แยกเป็น panel วันทำการ (P+OP) กับวันหยุด (H) เหมือน load_boxplot.py ต้นฉบับ วันหยุดจะถูกแยก
    เป็น "วันที่เดินเครื่อง"/"วันที่หยุดเครื่อง" อีกชั้นถ้ามีข้อมูลพอทั้งสองแบบ (ดูจากค่าเฉลี่ยรายวัน
    ต่ำกว่า shutdown_kw หรือไม่) raise ValueError ถ้าไม่มีข้อมูลเลย

    subtitle (ไม่บังคับ) ใส่ต่อท้ายหัวเรื่องกราฟได้ เช่น "บัญชี 0199000001 — บริษัท ทดสอบ จำกัด"
    เวลากราฟถูกกรองเหลือเฉพาะบัญชีเดียว (ดู web/app.py api_forecast_boxplot) กันสับสนว่ากราฟที่เห็น
    เป็นของ TSIC รวมทุกบัญชี หรือของบัญชีใดบัญชีหนึ่งโดยเฉพาะ

    เลือกภาษาไทย/อังกฤษของหัวเรื่องกราฟเองตามฟอนต์ที่มีอยู่จริงบนเซิร์ฟเวอร์ (กันตัวอักษรไทย
    กลายเป็นกล่องว่างถ้าเซิร์ฟเวอร์ไม่มีฟอนต์ไทยติดตั้งไว้ — ชื่อธุรกิจเป็นภาษาไทยเสมอ จึงตัดออก
    จากหัวเรื่องถ้าไม่มีฟอนต์ไทยจริงๆ เหลือแค่รหัส TSIC ซึ่งเป็น ASCII ล้วน)"""

    import matplotlib.pyplot as plt

    if df.empty:
        raise ValueError("ยังไม่มีข้อมูล AMR จริงสำหรับประเภทธุรกิจนี้เลย")

    daily_mean = df.groupby("date")["kw"].mean()
    df = df.copy()
    df["off"] = df["date"].map(daily_mean < shutdown_kw)

    thai = _setup_font()
    if thai:
        title = f"Boxplot การใช้ไฟจริง — {business_type_name} ({business_type_code})" if business_type_name else f"Boxplot การใช้ไฟจริง — {business_type_code}"
        if subtitle:  # subtitle (บัญชี/ชื่อบริษัท) เป็นภาษาไทยเสมอ ตัดออกถ้าไม่มีฟอนต์ไทยจริง เหมือน business_type_name
            title = f"{title}\n{subtitle}"
    else:
        title = f"Real AMR usage boxplot — business type {business_type_code}"
    L = dict(
        wd="วันทำการ (OP + P)" if thai else "Weekday (OP + P)",
        hd="วันหยุด (H)" if thai else "Holiday (H)",
        hrun="วันหยุด (H) - วันที่เดินเครื่อง" if thai else "Holiday (H) - running days",
        hoff="วันหยุด (H) - วันที่หยุดเครื่อง" if thai else "Holiday (H) - shutdown days",
        days="วัน" if thai else "days",
        hour="ชั่วโมงของวัน" if thai else "Hour of day",
    )

    wd, hd = df[df.rate != "H"], df[df.rate == "H"]
    h_run, h_off = hd[~hd.off], hd[hd.off]

    panels = []
    if not wd.empty:
        panels.append((wd, L["wd"], lambda h: "P" if 9 <= h < 22 else "OP"))
    if not h_off.empty and not h_run.empty:
        panels.append((h_run, f"{L['hrun']}  ({h_run.date.nunique()} {L['days']})", lambda h: "H"))
        panels.append((h_off, f"{L['hoff']}  ({h_off.date.nunique()} {L['days']})", lambda h: "H"))
    elif not hd.empty:
        panels.append((hd, L["hd"], lambda h: "H"))

    if not panels:
        raise ValueError("ยังไม่มีข้อมูล AMR จริงสำหรับประเภทธุรกิจนี้เลย")

    peaks = {r: df.loc[df.rate == r, "kw"].max() for r in COLORS if (df.rate == r).any()}
    ymax = (max(peaks.values()) if peaks else df["kw"].max()) * 1.18

    fig, axes = plt.subplots(len(panels), 1, figsize=(12, 4.6 * len(panels)), sharey=True, squeeze=False)
    axes = axes[:, 0]

    for ax, (data, name, rate_of) in zip(axes, panels):
        stats = _box_stats(_values_by_hour(data))
        bp = ax.bxp(stats, positions=np.arange(24) + 0.5, widths=0.6, showfliers=True,
                    patch_artist=True, manage_ticks=False)
        for h in range(24):
            c = COLORS[rate_of(h)]
            bp["boxes"][h].set(facecolor=c, alpha=0.35, edgecolor=c)
            bp["medians"][h].set(color=c, linewidth=2.5)
            for k in (2 * h, 2 * h + 1):
                bp["whiskers"][k].set(color=c)
                bp["caps"][k].set(color=c)
            bp["fliers"][h].set(marker="o", markersize=3.5, markerfacecolor="black", markeredgecolor="black")
        ax.set_title(name, loc="left", fontsize=12)
        ax.set_xlim(0, 24)
        ax.set_ylim(0, ymax if ymax > 0 else 1)
        ax.set_xticks(np.arange(0, 24, 3) + 0.5)
        ax.set_xticklabels(range(0, 24, 3))
        ax.set_ylabel("kW")
        ax.grid(axis="y", alpha=0.25)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    axes[-1].set_xlabel(L["hour"])
    fig.suptitle(title, fontsize=14, weight="bold")
    fig.text(0.01, 0.005,
              "Box = Q1-Q3, bold line = median, whiskers = P5-P95, dot = max 15-min value. Real AMR data.",
              fontsize=8, color="gray")
    fig.tight_layout(rect=(0, 0.02, 1, 0.97))

    buf = io.BytesIO()
    try:
        fig.savefig(buf, format="png", dpi=140)
    finally:
        plt.close(fig)
    return buf.getvalue()
