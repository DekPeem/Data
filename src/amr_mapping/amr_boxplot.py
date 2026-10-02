"""รวบรวมข้อมูล AMR จริง (รายงาน 15 นาทีจาก PEA/กฟภ. หรือ MEA/กฟน. — ดู _is_mea_csv) ที่แอดมินอัปโหลดเข้ามา จัดเก็บแยกตามประเภทธุรกิจ
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

import csv
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


def _read_one_interval_kwh_single_rate(tables: List[pd.DataFrame]) -> pd.DataFrame:
    """แกะตารางข้อมูลจากไฟล์รายงาน "ข้อมูลกิโลวัตต์ชั่วโมงแบบช่วงเวลา" ของ PEA (รูปแบบไฟล์ AMR จริง
    แบบที่ 9 ที่เจอ — .xlsx จริง 3 ชีตเหมือนรายงาน "ข้อมูลกิโลวัตต์แบบช่วงเวลา" เดิมที่รองรับอยู่แล้ว
    แต่ต่างกันตรงที่ตารางข้อมูลจริง (ชีตกลาง) มีแค่ 5 คอลัมน์ (ts, RATE A, RATE B, RATE C, ผลรวม —
    ค่าเดียวต่อ rate ไม่ใช่คู่ a1/a2/b1/b2/c1/c2 แบบเดิมที่มี 7 คอลัมน์) และหน่วยข้อมูลเป็น kWh
    (พลังงานสะสมของช่วง 15 นาทีนั้น — ยืนยันจากชื่อรายงานที่มีคำว่า "กิโลวัตต์ชั่วโมง" ต่างจาก
    "กิโลวัตต์" เฉยๆ หลักการเดียวกับ _read_one_monthly_kwh) ต้องแปลงเป็น kW เฉลี่ยก่อน (คูณ 4) คืน
    DataFrame คอลัมน์ ts,a1,a2,b1,b2,c1,c2 มาตรฐานเดียวกับรายงานอื่นๆ (duplicate ค่าลงคู่คอลัมน์เอง
    ให้โครงสร้างผลลัพธ์ตรงกัน เหมือน _read_one_monthly_kwh ทุกประการ แค่อ่านจาก tables[1] แทนชีต
    เดียวรวมกัน)"""

    d = tables[1].iloc[1:].copy()  # table 0 = ข้อมูลหัวรายงาน, 1 = ข้อมูลจริง, 2 = ท้ายรายงาน
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
    _read_one_monthly_kw) — ไฟล์ที่มี 3 ชีต (header/ข้อมูล/ท้ายรายงาน) แยกอีกชั้นจากจำนวนคอลัมน์ของ
    ชีตข้อมูลจริง (tables[1]): 5 คอลัมน์ (ts + RATE A/B/C + ผลรวม) คือรายงาน "กิโลวัตต์ชั่วโมงแบบ
    ช่วงเวลา" หน่วย kWh ต้องแปลง (ดู _read_one_interval_kwh_single_rate) ส่วน 7 คอลัมน์ (ts +
    a1/a2/b1/b2/c1/c2) คือรายงาน "กิโลวัตต์แบบช่วงเวลา" แบบเดิม หน่วย kW ตรงอยู่แล้ว ไม่ต้องแปลง —
    เหมือน load_boxplot.py ต้นฉบับทุกประการ"""

    if len(tables) == 1:
        if _sheet_contains_text(tables[0], "Custom kW Report"):
            return _read_one_custom_kw(tables[0])
        if _sheet_contains_text(tables[0], "กิโลวัตต์ชั่วโมงรายเดือน"):
            return _read_one_monthly_kwh(tables[0])
        return _read_one_monthly_kw(tables[0])

    if tables[1].shape[1] == 5:
        return _read_one_interval_kwh_single_rate(tables)

    d = tables[1].iloc[1:].copy()  # table 0 = ข้อมูลหัวรายงาน, 1 = ข้อมูลจริง, 2 = ท้ายรายงาน
    d.columns = ["ts", "a1", "a2", "b1", "b2", "c1", "c2"]
    d = d[d["ts"].astype(str).str.match(r"\d\d/\d\d/\d{4} \d\d\.\d\d")]
    for c in d.columns[1:]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d


def _is_mea_csv(path: Union[str, Path]) -> bool:
    """เช็คว่าไฟล์เป็นรายงาน AMR ของ กฟน. (MEA) รูปแบบ CSV ธรรมดา — ต่างจากรายงานของ กฟภ./PEA ทุก
    แบบที่รองรับอยู่ก่อนหน้านี้โดยสิ้นเชิง (มาเป็น HTML-in-.xls หรือ .xlsx จริงเสมอ ไม่เคยเป็น
    plain CSV เลย) เช็คจากบรรทัดหัวตาราง (header) ตรงๆ — "MEA No.,UI ID.,Rate Category,
    Measuring Compoenent,TOU/TOD,Date Time,Value" (สะกด "Compoenent" ผิดตามไฟล์จริงจาก กฟน. เอง
    ไม่ใช่ตัวพิมพ์ผิดของเราเอง) อ่านแค่บรรทัดแรกพอ ไม่ต้องโหลดทั้งไฟล์"""

    try:
        with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
            first_line = f.readline()
    except OSError:
        return False
    return "MEA No." in first_line and "Measuring Compoenent" in first_line


def _parse_mea_csv(path: Union[str, Path]) -> List[ParsedInterval]:
    """แกะรายงาน AMR ของ กฟน. (MEA) รูปแบบ CSV ธรรมดา — 1 ไฟล์มี 2 ชนิดข้อมูลปนกัน (Measuring
    Compoenent = "E-MAX-KW-IMP" กำลังไฟฟ้าจริง กับ "E-MAX-KVAR-IMP" กำลังไฟฟ้ารีแอกทีฟ) ต้องกรอง
    เอาเฉพาะ kW เท่านั้น (เหมือนรายงานของ PEA ทุกแบบที่เก็บแค่ kW ไม่สนใจ kVAR) วันที่เป็นรูปแบบ
    สากล M/D/YYYY H:MM (เดือนขึ้นก่อนวัน ต่างจากรายงานของ PEA ที่เป็น DD/MM/YYYY เสมอ — ยืนยันจาก
    ไฟล์ตัวอย่างจริงที่ค่าคอลัมน์แรกไม่เคยเกิน 12 เลย)

    คอลัมน์ TOU/TOD ของ กฟน. มีแค่ 2 ค่า (ON/OFF) ต่างจาก P/OP/H 3 ระดับที่ระบบนี้ใช้ — ยืนยันจากไฟล์
    ตัวอย่างจริงแล้วว่า ON ปรากฏเฉพาะวันทำการ (จันทร์-ศุกร์) ช่วง 9:00-22:00 เท่านั้น ใช้ ON บอกช่วง
    Peak (P) ได้ตรงๆ ส่วน OFF ต้องแยกต่ออีกชั้นว่าเป็นวันทำการ (Off-Peak — OP) หรือวันหยุดสุดสัปดาห์
    (Holiday — H) จากวันในสัปดาห์ของ timestamp เอง (เสาร์-อาทิตย์เสมอในไฟล์ตัวอย่าง — ไม่รองรับ
    วันหยุดนักขัตฤกษ์ระหว่างสัปดาห์ ข้อจำกัดเดียวกับ _classify_tou_rate ที่ใช้เดาให้รายงาน
    "Custom kW Report" ของ PEA) — timestamp ในไฟล์บอกเวลา "สิ้นสุด" ของช่วง 15 นาทีนั้น เหมือน
    รายงานของ PEA ทุกแบบ ต้องลบ 15 นาทีก่อนหาว่าอยู่วัน/ชั่วโมงไหน (ยืนยันจากไฟล์ตัวอย่างจริง:
    timestamp ลงท้าย 9:00 ยังเป็น OFF แต่ 9:15 เป็น ON แล้ว แปลว่าช่วง [9:00-9:15) ที่ลงท้ายด้วย 9:15
    คือช่วง Peak แรกของวัน ไม่ใช่ช่วงที่ลงท้ายด้วย 9:00 เอง)"""

    df = pd.read_csv(path, encoding="utf-8-sig", dtype=str)
    df = df[df["Measuring Compoenent"].str.strip() == "E-MAX-KW-IMP"].copy()
    if df.empty:
        return []

    end = pd.to_datetime(df["Date Time"], format="%m/%d/%Y %H:%M", errors="coerce")
    start = end - pd.Timedelta(minutes=15)
    kw = pd.to_numeric(df["Value"], errors="coerce")
    tou = df["TOU/TOD"].str.strip().str.upper()
    is_weekday = start.dt.weekday < 5
    rate = np.select([tou == "ON", is_weekday], ["P", "OP"], "H")

    out: List[ParsedInterval] = []
    for s, r, k in zip(start, rate, kw):
        if pd.isna(s) or pd.isna(k):
            continue
        out.append(ParsedInterval(date=s.strftime("%Y-%m-%d"), hour=int(s.hour), minute=int(s.minute), rate=str(r), kw=float(k)))
    return out


def _extract_mea_csv_customer_info(path: Union[str, Path]) -> Tuple[str, str]:
    """หาเลขบัญชี (คอลัมน์ "MEA No.") จากรายงาน CSV ของ กฟน. — ไม่มีชื่อบริษัทให้เลยในไฟล์รูปแบบนี้
    (ต่างจากรายงานส่วนใหญ่ของ PEA) company_name จะว่างเสมอ ต้องกรอกเองในฟอร์ม"""

    try:
        df = pd.read_csv(path, encoding="utf-8-sig", dtype=str, nrows=1)
    except Exception:  # noqa: BLE001 — ไฟล์เสีย/รูปแบบไม่ตรง ถือว่าหาไม่เจอ
        return "", ""
    if df.empty or "MEA No." not in df.columns:
        return "", ""
    return str(df["MEA No."].iloc[0]).strip(), ""


def _is_mea_wide_excel(path: Union[str, Path]) -> bool:
    """เช็คว่าไฟล์เป็นรายงาน AMR ของ กฟน. (MEA) รูปแบบ .xlsx จริง "ตารางแสดงผลข้อมูลแบบสรุปแนวขวาง"
    — คนละรูปแบบไฟล์กับ MEA CSV ที่รองรับอยู่ก่อนหน้า (ไฟล์นี้เป็น Excel 2007+ จริง มี "PK" magic
    bytes เหมือนไฟล์ .xlsx จริงของ PEA แต่หัวตารางต่างกันโดยสิ้นเชิง) เป็น 1 ชีต มีหัวตาราง 4 แถวก่อน
    ถึงแถวข้อมูลจริง: แถว 0 ชื่อรายงาน, แถว 1 ว่าง, แถว 2 "Value" (หัวกลุ่มคอลัมน์ตัวเลข), แถว 3 คือ
    หัวตารางจริง — เช็คจากข้อความ "MEA No." ใน 10 แถวบนสุดพอ กันสับสนกับไฟล์ .xlsx จริงของ PEA ที่ไม่
    เคยมีข้อความนี้เลย (อ่านแค่ sheet 0, 10 แถวแรกพอ ไม่ต้องโหลดทั้งไฟล์)"""

    try:
        raw = Path(path).read_bytes()
    except OSError:
        return False
    if raw[:2] != b"PK":
        return False
    try:
        df = pd.read_excel(io.BytesIO(raw), sheet_name=0, header=None, nrows=10, dtype=str)
    except Exception:  # noqa: BLE001 — ไฟล์เสีย/อ่านไม่ได้/ไม่ใช่ .xlsx จริง ถือว่าไม่ใช่รูปแบบนี้
        return False
    return _sheet_contains_text(df, "MEA No.")


def _find_mea_wide_excel_header_row(df: pd.DataFrame) -> Optional[int]:
    """หาตำแหน่งแถวหัวตารางจริง (มีคำว่า "MEA No." อยู่) ใน DataFrame ที่โหลดมาแบบ header=None —
    ใช้ร่วมกันทั้ง _parse_mea_wide_excel และ _extract_mea_wide_excel_customer_info"""

    for i in range(len(df)):
        if "MEA No." in df.iloc[i].astype(str).tolist():
            return i
    return None


def _parse_mea_wide_excel(path: Union[str, Path]) -> List[ParsedInterval]:
    """แกะรายงาน AMR ของ กฟน. (MEA) รูปแบบ .xlsx "ตารางแสดงผลข้อมูลแบบสรุปแนวขวาง" — ต่างจาก MEA CSV
    (ดู _parse_mea_csv) ตรงที่ 1 แถวมีค่า kW/kVAR/kWh/kVARh ของช่วง 15 นาทีเดียวกันครบอยู่ในแถว
    เดียวกันแล้ว (ไม่ต้องกรองแถวตามชนิดข้อมูลเหมือน CSV) อ่านแค่คอลัมน์ "E-MAX-KW-IMP" (กำลังไฟฟ้า
    จริงสูงสุดของช่วง — ชื่อคอลัมน์เดียวกับที่ MEA CSV ใช้) ไม่สนใจคอลัมน์พลังงานสะสม (E-KWH-TOTAL-IMP/
    E-KVARH-TOTAL-IMP) หรือ kVAR (E-MAX-KVAR-IMP) เลย — Date Time เป็นรูปแบบ ISO
    "YYYY-MM-DD HH:MM:SS" ตรงๆ (ต่างจาก MEA CSV ที่เป็น M/D/YYYY H:MM ไม่เติมเลข 0 นำหน้า) ตรรกะ
    แปลงคอลัมน์ TOU/TOD (ON/OFF) เป็น P/OP/H เหมือนกันเป๊ะกับ _parse_mea_csv (ดูคำอธิบายที่นั่น รวม
    ข้อจำกัดเรื่องวันหยุดนักขัตฤกษ์ระหว่างสัปดาห์ด้วย — ยืนยันจากไฟล์ตัวอย่างจริงว่าวันหยุดนักขัตฤกษ์
    ที่ตรงกับวันธรรมดา เช่น วันจักรี/สงกรานต์ คอลัมน์ TOU/TOD เป็น OFF ทั้งวันถูกต้องอยู่แล้ว แต่ด้วย
    ข้อจำกัดเดียวกันนี้ ระบบจะจัดเป็น OP ไม่ใช่ H เพราะแยกจากวันในสัปดาห์เท่านั้น ไม่มีปฏิทินวันหยุด
    นักขัตฤกษ์ให้เทียบ — ไม่กระทบค่า P เลย เพราะ ON ไม่เคยเกิดขึ้นในวันหยุดนักขัตฤกษ์เหล่านี้)"""

    raw = Path(path).read_bytes()
    df = pd.read_excel(io.BytesIO(raw), sheet_name=0, header=None, dtype=str)
    header_row_idx = _find_mea_wide_excel_header_row(df)
    if header_row_idx is None:
        return []
    df.columns = df.iloc[header_row_idx]
    df = df.iloc[header_row_idx + 1 :].reset_index(drop=True)
    if "Date Time" not in df.columns or "E-MAX-KW-IMP" not in df.columns or "TOU/TOD" not in df.columns:
        return []

    end = pd.to_datetime(df["Date Time"], errors="coerce")
    start = end - pd.Timedelta(minutes=15)
    kw = pd.to_numeric(df["E-MAX-KW-IMP"], errors="coerce")
    tou = df["TOU/TOD"].astype(str).str.strip().str.upper()
    is_weekday = start.dt.weekday < 5
    rate = np.select([tou == "ON", is_weekday], ["P", "OP"], "H")

    out: List[ParsedInterval] = []
    for s, r, k in zip(start, rate, kw):
        if pd.isna(s) or pd.isna(k):
            continue
        out.append(ParsedInterval(date=s.strftime("%Y-%m-%d"), hour=int(s.hour), minute=int(s.minute), rate=str(r), kw=float(k)))
    return out


def _extract_mea_wide_excel_customer_info(path: Union[str, Path]) -> Tuple[str, str]:
    """หาเลขบัญชี (คอลัมน์ "MEA No.") จากรายงาน .xlsx แบบสรุปแนวขวางของ กฟน. — ไม่มีชื่อบริษัทให้เลย
    ในไฟล์รูปแบบนี้เหมือนกัน (เหมือน MEA CSV — ดู _extract_mea_csv_customer_info) company_name
    จะว่างเสมอ ต้องกรอกเองในฟอร์ม"""

    try:
        raw = Path(path).read_bytes()
        df = pd.read_excel(io.BytesIO(raw), sheet_name=0, header=None, nrows=10, dtype=str)
    except Exception:  # noqa: BLE001 — ไฟล์เสีย/อ่านไม่ได้ ถือว่าหาไม่เจอ
        return "", ""
    header_row_idx = _find_mea_wide_excel_header_row(df)
    if header_row_idx is None:
        return "", ""
    header = df.iloc[header_row_idx].tolist()
    if "MEA No." not in header or header_row_idx + 1 >= len(df):
        return "", ""
    mea_col = header.index("MEA No.")
    return str(df.iloc[header_row_idx + 1, mea_col]).strip(), ""


def _is_load_profile_detail_xlsx(path: Union[str, Path]) -> bool:
    """เช็คว่าไฟล์เป็นรายงาน "Load Profile" รูปแบบ .xlsx จริง 1 ชีต หัวตารางแถวเดียว (แถว 0) ที่มี
    คอลัมน์ "DateTime" + แยกกำลังไฟฟ้าเป็น 3 ช่วงเวลา (TOD rate — Time of Day): "kW (On-Peak)",
    "kW (Off-Peak)", "kW (Partial-Peak)" — รูปแบบไฟล์ AMR จริงแบบที่ 8 ที่เจอ ต่างจากทุกแบบก่อนหน้า
    ตรงที่เป็นไฟล์ "สรุปแล้ว" (ไม่ใช่ export ดิบจาก PEA/MEA ตรงๆ — ไม่มีคอลัมน์เลขบัญชี/ชื่อบริษัท
    เลย ต้องกรอกเองเสมอ) น่าจะมาจากเครื่องมือ/ที่ปรึกษาพลังงานที่ประมวลผลไฟล์ดิบของผู้ใช้ไฟรายที่ถือ
    สัญญาอัตรา TOD (3 ช่วงราคาต่อวัน ใช้เหมือนกันทุกวันในสัปดาห์ ไม่แยกวันหยุดสุดสัปดาห์แบบ TOU) มา
    อีกที — เช็คจากชื่อคอลัมน์ตรงๆ ใน 1 แถวบนสุดพอ (ไม่ต้องสนใจชื่อไฟล์ ไฟล์ของลูกค้าคนอื่นที่ใช้
    เครื่องมือเดียวกันก็ควรจะมีโครงสร้างคอลัมน์แบบนี้เหมือนกัน)"""

    try:
        raw = Path(path).read_bytes()
    except OSError:
        return False
    if raw[:2] != b"PK":
        return False
    try:
        df = pd.read_excel(io.BytesIO(raw), sheet_name=0, header=0, nrows=1)
    except Exception:  # noqa: BLE001 — ไฟล์เสีย/อ่านไม่ได้/ไม่ใช่ .xlsx จริง ถือว่าไม่ใช่รูปแบบนี้
        return False
    cols = set(str(c) for c in df.columns)
    return {"DateTime", "kW (On-Peak)", "kW (Off-Peak)"}.issubset(cols)


def _parse_load_profile_detail_xlsx(path: Union[str, Path]) -> List[ParsedInterval]:
    """แกะรายงาน "Load Profile" รูปแบบ .xlsx ที่มีคอลัมน์ "DateTime" + "kW" ตรงๆ (ดู
    _is_load_profile_detail_xlsx) — ไฟล์นี้ให้กำลังไฟฟ้ารวม (คอลัมน์ "kW") ของแต่ละช่วง 15 นาที
    มาตรงๆ อยู่แล้ว (เท่ากับผลรวมของ 3 คอลัมน์ On-Peak/Off-Peak/Partial-Peak เป๊ะ — ยืนยันจากไฟล์
    ตัวอย่างจริง) จึงไม่ต้องรวมเอง อ่านคอลัมน์ "kW" ตรงๆ พอ ไม่สนใจคอลัมน์แยกตาม TOD rate
    (On-Peak/Off-Peak/Partial-Peak/RATE_A/B/C) เลย เพราะ 3 ช่วงราคานี้เป็นสัญญาอัตรา TOD เฉพาะ
    (ใช้เหมือนกันทุกวันในสัปดาห์ ไม่สนใจวันหยุดสุดสัปดาห์) ซึ่ง "ไม่ตรง" กับแนวคิด P/OP/H ของระบบนี้
    ที่อิงวันหยุดสุดสัปดาห์เป็นหลัก (ดู COLORS/ParsedInterval.rate) — เลือกเดารหัส P/OP/H จากวัน/
    เวลาเองแทนด้วย _classify_tou_rate (เหมือนที่ใช้กับรายงาน "Custom kW Report" ของ PEA ที่ไม่มี
    rate ให้เหมือนกัน) ซึ่งหมายความว่าขอบเขตเวลา Peak (9:00-22:00 วันทำการ) อาจไม่ตรงกับขอบเขต TOD
    rate จริงของสัญญานี้เป๊ะ แต่ก็ยังให้ผลลัพธ์ H (วันหยุดสุดสัปดาห์) ถูกต้องเสมอ ซึ่งเป็นสิ่งที่
    Boxplot ใช้แยกกลุ่มจริงๆ (ดู render_boxplot_png — แยกแค่ H กับไม่ใช่ H เท่านั้น ส่วน P/OP ภายใน
    panel วันทำการ Boxplot จะคำนวณจากชั่วโมงเองอยู่แล้วไม่ได้อิงค่า rate ที่เก็บไว้) "DateTime" บอก
    เวลา "สิ้นสุด" ของช่วง 15 นาทีนั้น (เหมือนรายงานของ PEA/MEA ทุกแบบ) ต้องลบ 15 นาทีก่อน — ไฟล์นี้
    ไม่มีเลขบัญชี/ชื่อบริษัทให้เลย (ดู _is_load_profile_detail_xlsx) ต้องกรอกเองในฟอร์มเสมอ"""

    raw = Path(path).read_bytes()
    df = pd.read_excel(io.BytesIO(raw), sheet_name=0, header=0)
    if "DateTime" not in df.columns or "kW" not in df.columns:
        return []

    end = pd.to_datetime(df["DateTime"], errors="coerce")
    start = end - pd.Timedelta(minutes=15)
    kw = pd.to_numeric(df["kW"], errors="coerce")
    rate = _classify_tou_rate(start)

    out: List[ParsedInterval] = []
    for s, r, k in zip(start, rate, kw):
        if pd.isna(s) or pd.isna(k):
            continue
        out.append(ParsedInterval(date=s.strftime("%Y-%m-%d"), hour=int(s.hour), minute=int(s.minute), rate=str(r), kw=float(k)))
    return out


def _is_power_logger_csv(path: Union[str, Path]) -> bool:
    """เช็คว่าไฟล์เป็น log จากเครื่องวัดไฟฟ้า (power logger — เช่นรุ่น DW-680) โดยตรง — คนละประเภท
    ไฟล์โดยสิ้นเชิงจากรายงาน AMR ของ PEA/MEA ทุกแบบที่รองรับอยู่ก่อนหน้านี้ (ไม่ใช่รายงานสรุปราย 15
    นาทีจากการไฟฟ้า แต่เป็นข้อมูลวัดจริงต่อเนื่องทุกๆ ไม่กี่วินาทีจากเครื่องมือวัดของผู้ใช้เอง มีหัว
    ตารางยาวมาก (Voltage/Current/Power Factor/Active-Reactive-Apparent Power/THD/ฯลฯ) นำหน้าด้วย
    ข้อมูลตั้งค่าเครื่อง "Model"/"Serial Number"/"Wire Mode") เช็คจากข้อความ "Model" และ
    "Wire Mode" ใน 10 บรรทัดบนสุดพอ (ไม่ต้องโหลดทั้งไฟล์ — ไฟล์พวกนี้มักใหญ่มาก เป็นหลักสิบ MB)"""

    try:
        with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
            head_lines = [f.readline() for _ in range(10)]
    except OSError:
        return False
    head = "".join(head_lines)
    return "Model" in head and "Wire Mode" in head


def _parse_power_logger_csv(path: Union[str, Path]) -> List[ParsedInterval]:
    """แกะไฟล์ log จากเครื่องวัดไฟฟ้า (power logger) — วัดต่อเนื่องทุกไม่กี่วินาที (ต่างจากรายงาน AMR
    ของ PEA/MEA ที่เป็นค่าเฉลี่ย/สะสมต่อช่วง 15 นาทีอยู่แล้ว) ความถี่สูงกว่ารายงานทั่วไปหลายสิบเท่า —
    ถ้านำเข้าทุกจุดตรงๆ โดยไม่เฉลี่ยก่อน บัญชีนี้จะมีจุดข้อมูลมากกว่าบัญชีอื่นในกลุ่ม TSIC เดียวกัน
    มหาศาล ถ่วงน้ำหนักสถิติ Boxplot ผิดเพี้ยนไปเลย จึงต้องเฉลี่ยรวมเป็นช่วง 15 นาทีเอง (floor ลงช่วง
    15 นาที แล้วหาค่าเฉลี่ยของกำลังไฟฟ้าในช่วงนั้น) ก่อนเก็บเป็น interval เดียวต่อช่วง เหมือนรายงาน
    อื่นๆ ทุกแบบ

    หาแถวหัวตาราง (คอลัมน์แรกคือ "Date" คอลัมน์ที่สองคือ "Time") และคอลัมน์ "PSum" (กำลังไฟฟ้าจริง
    รวม 3 เฟส หน่วย kW — อยู่แถวถัดจากแถวหัวตาราง) เองจากเนื้อหาไฟล์ตรงๆ แทนตำแหน่งแถวตายตัว กันพัง
    ถ้า preamble ของรุ่นเครื่อง/เฟิร์มแวร์อื่นยาวไม่เท่ากัน — ชื่อคอลัมน์ "PSum" ปรากฏซ้ำอีกครั้งท้าย
    ไฟล์ในกลุ่ม "Active Power Demand" (ไม่ใช่กำลังไฟฟ้าจริง ณ ขณะนั้น) ใช้ .index() หาตัวแรกที่เจอพอ
    ไม่ใช่ตัวหลัง

    รูปแบบวันที่เป็น YYYY/MM/DD (ปีขึ้นก่อน มีเลข 0 นำหน้าเดือน/วันเสมอ — ยืนยันจากไฟล์ตัวอย่างจริง
    ตรงๆ "2026/09/05" ตรงกับชื่อไฟล์ที่มีวันที่กำกับไว้เอง "..._20260905_122233_..." และตรงกับ
    คอลัมน์ Time แถวแรกเป๊ะ "12:22:33" ด้วย — ⚠️ ระวังสับสนกับตอนก็อปข้อมูลจากไฟล์ไปแปะใน Excel/
    แชทแล้วเปิดดู Excel อาจแสดงผลวันที่ให้ใหม่ตามภาษา/รูปแบบที่ตั้งไว้ในเครื่อง เช่น "5/9/2026" ซึ่ง
    ไม่ใช่รูปแบบดิบจริงในไฟล์ ต้องยึดค่าดิบจากไฟล์ .csv ตรงๆ เท่านั้น) แต่ละแถวเป็นค่าที่วัด ณ ขณะนั้น
    จริง (point-in-time) ไม่ใช่ค่าเฉลี่ย/สะสมของช่วงเวลาแบบรายงาน AMR จึงไม่ต้องลบ 15 นาทีแบบรูปแบบ
    อื่นที่ timestamp บอกจุดสิ้นสุดของช่วง — ไม่มีข้อมูล rate (P/OP/H) ให้เลย ต้องเดาจากวัน/เวลาเองด้วย
    _classify_tou_rate
    (เหมือนรายงาน "Custom kW Report" ของ PEA) โดยใช้จุดเริ่มต้นของแต่ละช่วง 15 นาที (ผลลัพธ์จาก
    .dt.floor("15min")) เป็นตัวเดา ไม่ใช่เวลาที่วัดแต่ละจุดดิบ — ไม่มีเลขบัญชี/ชื่อบริษัทที่เชื่อถือ
    ได้ในไฟล์เลย ("User Name"/"Location" เป็นแค่ label ตั้งค่าเครื่องวัด ไม่ใช่ชื่อลูกค้าเสมอไป) ต้อง
    กรอกเองในฟอร์มเสมอ (ดู extract_customer_info)"""

    # อ่านด้วย csv.reader ตรงๆ (ไม่ใช่ pd.read_csv) เพราะ preamble ตั้งค่าเครื่องช่วงบนของไฟล์มี
    # จำนวนคอลัมน์ต่อแถวไม่เท่ากันเลย (บางแถวมีแค่ 2 คอลัมน์ "Model\tDW-680" บางแถวว่างเปล่า บางแถว
    # (หัวตารางกลุ่ม) มีหลายสิบคอลัมน์) ทำให้ pd.read_csv ที่ validate จำนวนคอลัมน์ต่อแถวให้เท่ากันทั้ง
    # ไฟล์ raise ParserError ทันทีตั้งแต่แถวที่จำนวนคอลัมน์เปลี่ยน — csv.reader ไม่ validate อะไรแบบนี้
    # เลย อ่านแถวแบบไหนก็ได้ผ่านหมด ตรงตามโครงสร้างไฟล์จริงพอดี
    try:
        with open(path, "r", encoding="utf-8-sig", errors="ignore", newline="") as f:
            sample = f.read(4096)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",\t")
            except csv.Error:
                dialect = csv.excel_tab if "\t" in sample else csv.excel
            rows = list(csv.reader(f, dialect))
    except OSError:
        return []

    header_row_idx = None
    for i, row in enumerate(rows[:30]):
        if len(row) > 1 and row[0].strip() == "Date" and row[1].strip() == "Time":
            header_row_idx = i
            break
    if header_row_idx is None or header_row_idx + 2 >= len(rows):
        return []

    field_row = [c.strip() for c in rows[header_row_idx + 1]]
    try:
        psum_col = field_row.index("PSum")
    except ValueError:
        return []

    dates: List[str] = []
    times: List[str] = []
    kws: List[str] = []
    for row in rows[header_row_idx + 2 :]:
        if len(row) <= psum_col:
            continue
        dates.append(row[0].strip())
        times.append(row[1].strip())
        kws.append(row[psum_col])

    ts = pd.to_datetime(pd.Series(dates) + " " + pd.Series(times), format="%Y/%m/%d %H:%M:%S", errors="coerce")
    kw_raw = pd.to_numeric(pd.Series(kws), errors="coerce")

    valid = ts.notna() & kw_raw.notna()
    ts, kw_raw = ts[valid], kw_raw[valid]
    if ts.empty:
        return []

    bucket_start = ts.dt.floor("15min")
    kw_avg = kw_raw.groupby(bucket_start).mean()
    rate = _classify_tou_rate(pd.Series(kw_avg.index))

    out: List[ParsedInterval] = []
    for t, k, r in zip(kw_avg.index, kw_avg.values, rate):
        out.append(ParsedInterval(date=t.strftime("%Y-%m-%d"), hour=int(t.hour), minute=int(t.minute), rate=str(r), kw=float(k)))
    return out


def _is_pea_monthly_combined_datetime_xls(path: Union[str, Path]) -> bool:
    """เช็คว่าไฟล์เป็นรายงาน "รายงานใช้ไฟ - รายเดือน" ของ PEA รูปแบบ .xls ไบนารีเก่าจริง (BIFF/OLE2
    Compound File — เปิดด้วย Excel 97-2003 ได้ตรงๆ) — คนละไบนารีฟอร์แมตโดยสิ้นเชิงจากทั้ง .xlsx จริง
    (PK magic bytes) และ HTML-in-.xls แบบเดิมที่ตั้งนามสกุล .xls เฉยๆ แต่เนื้อหาจริงเป็น HTML table
    (รองรับอยู่แล้วใน _load_report_tables — ไฟล์นี้ decode เป็น HTML ไม่ได้เลย ต้องใช้ library xlrd
    อ่านเท่านั้น) เช็คจาก magic bytes ของ OLE2 Compound File (D0 CF 11 E0 A1 B1 1A E1 — ไฟล์ไบนารี
    .xls เก่าทุกไฟล์ขึ้นต้นด้วยเสมอ) ร่วมกับข้อความ "วันที่/เวลา" (ชื่อคอลัมน์ที่รวมวันที่+เวลาไว้ด้วย
    กัน — ต่างจากรายงานอื่นของ PEA ที่แยกคอลัมน์ ts ปกติ) ในชีตแรก กันไปชนกับไฟล์ไบนารี .xls เก่า
    รูปแบบอื่นที่อาจเจอในอนาคต"""

    try:
        with open(path, "rb") as f:
            magic = f.read(8)
        if magic != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
            return False
        df = pd.read_excel(path, sheet_name=0, header=None, nrows=10, dtype=str, engine="xlrd")
    except Exception:  # noqa: BLE001 — ไฟล์เสีย/อ่านไม่ได้/ไม่ใช่ .xls ไบนารีจริง ถือว่าไม่ใช่รูปแบบนี้
        return False
    return _sheet_contains_text(df, "วันที่/เวลา")


def _parse_pea_monthly_combined_datetime_xls(path: Union[str, Path]) -> List[ParsedInterval]:
    """แกะรายงาน "รายงานใช้ไฟ - รายเดือน" ของ PEA (.xls ไบนารีเก่าจริง — ดู
    _is_pea_monthly_combined_datetime_xls) คอลัมน์ "วันที่/เวลา" รวมวันที่+เวลาไว้คอลัมน์เดียว
    (ต่างจากรายงานอื่นที่แยกคอลัมน์) ปีเป็น พ.ศ. (เช่น 2569) ต้องแปลงเป็น ค.ศ. ก่อน parse เสมอ (แก้
    ที่ตัว string ปีตรงๆ ก่อนแปลงเป็น Timestamp — ห้ามลบ 543 จาก Timestamp ที่ parse ไปแล้วทีหลัง
    เด็ดขาด เหตุผลเดียวกับที่อธิบายไว้ใน parse_amr_file) เวลา "24:00" ของแถวสุดท้ายในแต่ละวันหมายถึง
    เที่ยงคืนของวันถัดไป (pd.Timestamp ไม่รับ hour=24 ตรงๆ) ต้องแปลงเป็น 00:00 ของวันถัดไปเอง

    มี 2 รูปแบบคอลัมน์ข้อมูลที่เจอจริง ขึ้นอยู่กับประเภทสัญญาอัตราค่าไฟของบัญชีนั้น — (1) บัญชีที่ถือ
    สัญญาอัตรา TOU มีคอลัมน์ "kW (On-Peak)"/"kW (Off-Peak)" แยก 2 ช่วงแต่ไม่มีคอลัมน์ Holiday แยกให้
    เลย ต้องเดา H จากวันในสัปดาห์เอง (ยืนยันจากไฟล์ตัวอย่างจริงแล้วว่า On-Peak เป็น 0 ทุกแถวในวัน
    เสาร์-อาทิตย์เสมอ — หลักการเดียวกับ MEA CSV/MEA wide excel ที่มีแค่ ON/OFF 2 สถานะ) (2) บัญชีที่
    ถือสัญญาอัตราปกติ (Non-TOU) ไม่มีการแยกช่วงเวลาเลย มีแค่คอลัมน์ "kW" เดี่ยวๆ (เจอจากไฟล์ตัวอย่าง
    จริงอีกบัญชีหนึ่ง) ต้องเดา P/OP/H ทั้งหมดจากวัน/เวลาเองด้วย _classify_tou_rate (เหมือนรายงาน
    "Custom kW Report" ของ PEA ที่ไม่มีข้อมูล rate ให้เลยเหมือนกัน) — เช็คว่าไฟล์เป็นแบบไหนจากคอลัมน์
    ที่มีอยู่จริงในหัวตาราง ไม่ใช่เดาจากจำนวนคอลัมน์เฉยๆ

    timestamp บอกเวลา "สิ้นสุด" ของช่วง 15 นาทีนั้น เหมือนรายงานของ PEA ทุกแบบ ต้องลบ 15 นาทีก่อนหา
    ว่าอยู่วัน/ชั่วโมงไหน เวลา "24:00" ของแถวสุดท้ายในแต่ละวันหมายถึงเที่ยงคืนของวันถัดไป
    (pd.Timestamp ไม่รับ hour=24 ตรงๆ) ต้องแปลงเป็น 00:00 ของวันถัดไปเอง ปีเป็น พ.ศ. (เช่น 2569)
    ต้องแปลงเป็น ค.ศ. ก่อน parse เสมอ (แก้ที่ตัว string ปีตรงๆ ก่อนแปลงเป็น Timestamp — ห้ามลบ 543
    จาก Timestamp ที่ parse ไปแล้วทีหลังเด็ดขาด เหตุผลเดียวกับที่อธิบายไว้ใน parse_amr_file) — ไม่มี
    ชื่อบริษัทให้เลย มีแค่ "เครื่องวัดฯ" (หมายเลขมิเตอร์ — คนละความหมายกับเลขบัญชีผู้ใช้ไฟ
    "บัญชีผู้ใช้ไฟ"/"Contact Account" ที่รายงานอื่นใช้) จึงไม่ดึงมาใช้เป็น account_no (เหมือนรายงาน
    อื่นๆ ที่ไม่เคยใช้หมายเลขมิเตอร์แทนเลขบัญชีเช่นกัน) ต้องกรอกเองในฟอร์มเสมอ (ดู
    extract_customer_info)"""

    df = pd.read_excel(path, sheet_name=0, header=None, dtype=str, engine="xlrd")
    header_row_idx = None
    for i in range(min(10, len(df))):
        if "วันที่/เวลา" in df.iloc[i].astype(str).tolist():
            header_row_idx = i
            break
    if header_row_idx is None:
        return []

    header = df.iloc[header_row_idx].tolist()
    try:
        ts_col = header.index("วันที่/เวลา")
    except ValueError:
        return []

    data = df.iloc[header_row_idx + 1 :]
    ts_raw = data.iloc[:, ts_col].astype(str).str.strip()

    parts = ts_raw.str.extract(r"^(\d\d)/(\d\d)/(\d{4}) (\d\d):(\d\d)$")
    day, month, year, hour, minute = (parts[i] for i in range(5))
    is_midnight_next_day = hour == "24"
    hour = hour.where(~is_midnight_next_day, "00")
    year_num = pd.to_numeric(year, errors="coerce")
    ce_year = (year_num - 543).where(year_num > 2400, year_num)
    ce_year_str = ce_year.astype("Int64").astype(str).str.zfill(4)

    end = pd.to_datetime(
        day + "/" + month + "/" + ce_year_str + " " + hour + ":" + minute, format="%d/%m/%Y %H:%M", errors="coerce"
    )
    end = end.where(~is_midnight_next_day.fillna(False), end + pd.Timedelta(days=1))
    start = end - pd.Timedelta(minutes=15)

    if "kW (On-Peak)" in header and "kW (Off-Peak)" in header:
        on_peak = pd.to_numeric(data.iloc[:, header.index("kW (On-Peak)")], errors="coerce")
        off_peak = pd.to_numeric(data.iloc[:, header.index("kW (Off-Peak)")], errors="coerce")
        is_weekday = start.dt.weekday < 5
        rate = np.select([on_peak.fillna(0) > 0, is_weekday], ["P", "OP"], "H")
        kw = on_peak.fillna(0) + off_peak.fillna(0)
    elif "kW" in header:
        kw = pd.to_numeric(data.iloc[:, header.index("kW")], errors="coerce")
        rate = _classify_tou_rate(start)
    else:
        return []

    out: List[ParsedInterval] = []
    for s, r, k in zip(start, rate, kw):
        if pd.isna(s):
            continue
        out.append(ParsedInterval(date=s.strftime("%Y-%m-%d"), hour=int(s.hour), minute=int(s.minute), rate=str(r), kw=float(k)))
    return out


def parse_amr_file(path: Union[str, Path]) -> List[ParsedInterval]:
    """อ่านไฟล์ AMR ดิบ 1 ไฟล์ (จาก PEA, MEA หรือไฟล์ "Load Profile" ที่สรุปแล้ว) คืนรายการ interval
    ที่แกะแล้ว (rate=P/OP/H, kw, date, hour) — คืน list ว่างถ้าอ่าน/แปลงไม่สำเร็จ (ไม่ raise ทำให้
    ไฟล์อื่นที่อัปโหลดมาพร้อมกันยังประมวลผลต่อได้)"""

    try:
        if _is_mea_csv(path):
            return _parse_mea_csv(path)
        if _is_mea_wide_excel(path):
            return _parse_mea_wide_excel(path)
        if _is_load_profile_detail_xlsx(path):
            return _parse_load_profile_detail_xlsx(path)
        if _is_power_logger_csv(path):
            return _parse_power_logger_csv(path)
        if _is_pea_monthly_combined_datetime_xls(path):
            return _parse_pea_monthly_combined_datetime_xls(path)
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
    ไปเฉยๆ) ของไฟล์ AMR จริง 1 ไฟล์ (PEA) หรือคอลัมน์ "MEA No." (กฟน. — ดู
    _extract_mea_csv_customer_info) — คืน ("", "") ถ้าอ่าน/หาไม่เจอ (ไม่ raise เหมือน
    parse_amr_file ปล่อยให้ผู้ใช้กรอกเองแทนตอนหาไม่เจอ) โครงสร้างของ PEA ยืนยันจากไฟล์ตัวอย่างจริง
    ของผู้ใช้แล้ว (รายงาน "ข้อมูลกิโลวัตต์แบบช่วงเวลา" จากเว็บ amr.pea.co.th): tables[0] มีแถวหนึ่งที่
    คอลัมน์หนึ่งเป็นข้อความ "บัญชีผู้ใช้ไฟ :" ตามด้วยเลขบัญชีในคอลัมน์ถัดไปทันที และอีกคู่คอลัมน์ใน
    แถวเดียวกันเป็น "ชื่อผู้ใช้ไฟ :" ตามด้วยชื่อบริษัทในคอลัมน์ถัดไป (pandas.read_html แกะ &nbsp;/
    ช่องว่างหัวท้ายให้เรียบร้อยแล้วในตัว ไม่ต้อง strip เพิ่ม แต่ strip ไว้กันเหนียวเผื่อโครงสร้างเปลี่ยน
    เล็กน้อย)"""

    if _is_mea_csv(path):
        return _extract_mea_csv_customer_info(path)
    if _is_mea_wide_excel(path):
        return _extract_mea_wide_excel_customer_info(path)
    if _is_load_profile_detail_xlsx(path):
        # ไฟล์ "Load Profile" รูปแบบนี้ไม่มีคอลัมน์เลขบัญชี/ชื่อบริษัทเลย (ดู
        # _is_load_profile_detail_xlsx) ต้องกรอกเองในฟอร์มเสมอ
        return "", ""
    if _is_power_logger_csv(path):
        # ไฟล์ log จากเครื่องวัดไฟฟ้าไม่มีเลขบัญชี/ชื่อบริษัทที่เชื่อถือได้เลย (ดู
        # _parse_power_logger_csv) ต้องกรอกเองในฟอร์มเสมอ
        return "", ""
    if _is_pea_monthly_combined_datetime_xls(path):
        # ไฟล์รูปแบบนี้มีแค่ "เครื่องวัดฯ" (หมายเลขมิเตอร์ คนละความหมายกับเลขบัญชีผู้ใช้ไฟ) ไม่มี
        # ชื่อบริษัทให้เลย (ดู _parse_pea_monthly_combined_datetime_xls) ต้องกรอกเองในฟอร์มเสมอ
        return "", ""

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


def update_account_metadata(
    path: Path,
    business_type_code: str,
    account_no: str,
    company_name: Optional[str] = None,
    registration_no: Optional[str] = None,
) -> int:
    """แก้ชื่อบริษัท/เลขทะเบียนนิติบุคคลของบัญชีที่อัปโหลดไปแล้วโดยตรง ไม่ต้องลบแล้วอัปโหลดใหม่ทั้งก้อน
    (append_intervals_local ไม่มี dedup ข้ามการอัปโหลด อัปโหลดซ้ำจะนับข้อมูลซ้ำ) — ใช้ตอนไฟล์ AMR
    ต้นทางไม่มีชื่อบริษัทให้เลย (เช่นรายงาน "Custom kW Report") หรืออ่าน/กรอกผิดตอนอัปโหลดครั้งแรก
    company_name/registration_no ไม่ส่งมา (None) คือไม่แก้ฟิลด์นั้น ส่งมาเป็น "" ได้ถ้าตั้งใจล้างค่าทิ้ง
    คืนจำนวนแถวที่แก้ (0 ถ้าไม่มีไฟล์/ไม่มีแถวตรงเงื่อนไขเลย)"""

    import csv

    if not path.exists():
        return 0
    _migrate_intervals_file_header_if_needed(path)

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    updated = 0
    for row in rows:
        if row.get("business_type_code") == business_type_code and (row.get("account_no") or "") == account_no:
            if company_name is not None:
                row["company_name"] = company_name
            if registration_no is not None:
                row["registration_no"] = registration_no
            updated += 1

    if updated:
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_INTERVAL_FIELDNAMES, lineterminator="\n")
            writer.writeheader()
            for row in rows:
                writer.writerow({name: row.get(name, "") for name in _INTERVAL_FIELDNAMES})
    return updated


def load_intervals_local(
    path: Path,
    business_type_code: Optional[str] = None,
    account_no: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """โหลดข้อมูล interval จริงทั้งหมด (หรือกรองเฉพาะ business_type_code/account_no/ช่วงวันที่) คืน
    DataFrame ว่างถ้ายังไม่มีไฟล์เลย/ไม่มีข้อมูลตรงเงื่อนไข — account_no=None (ค่าเริ่มต้น) คือไม่กรอง
    ตามบัญชีเลย (รวมทุกบัญชี) ส่วน account_no="" คือกรองเฉพาะกลุ่ม "ไม่ระบุบัญชี" เท่านั้น (คนละ
    ความหมายกับ None — ดู remove_interval_rows ที่ใช้ธรรมเนียมเดียวกันอยู่แล้ว)

    start_date/end_date (ไม่บังคับ) เป็นสตริง "YYYY-MM-DD" แบบเดียวกับคอลัมน์ date เป๊ะ (เทียบแบบ
    string ตรงๆ ได้เลยเพราะ ISO format เรียงลำดับตัวอักษรตรงกับลำดับเวลาอยู่แล้ว ไม่ต้อง parse เป็น
    datetime) ใช้กรองดูเฉพาะเดือน/วันที่ต้องการแทนการรวมข้อมูลทุกวันที่สะสมไว้เสมอ — ส่งแค่ start_date
    อย่างเดียวก็ได้ (กรองตั้งแต่วันนั้นเป็นต้นไป) หรือ end_date อย่างเดียว (กรองถึงวันนั้น) หรือทั้งคู่
    เท่ากัน (ดูเฉพาะวันเดียว)"""

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
    if start_date:
        df = df[df["date"] >= start_date]
    if end_date:
        df = df[df["date"] <= end_date]
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
    means = {r: df.loc[df.rate == r, "kw"].mean() for r in COLORS if (df.rate == r).any()}
    ymax = (max(peaks.values()) if peaks else df["kw"].max()) * 1.18

    # สรุปตัวเลข Peak/เฉลี่ยของแต่ละ rate (P/OP/H) เป็นข้อความใต้หัวเรื่องกราฟ — ผู้ใช้ยืนยันอยากเห็น
    # ตัวเลขสรุปไปพร้อมกับกราฟเลย ไม่ต้องกะด้วยตาจาก box plot เอง (รูปแบบไหนก็ได้ตามที่ขอมา เลือกวาง
    # เป็นบรรทัดข้อความใต้ชื่อกราฟเพราะทำง่ายสุด ไม่ต้องเปลี่ยน API/หน้าเว็บเพิ่ม)
    rate_label = {
        "P": "P (Peak)",
        "OP": "OP (Off-Peak)",
        "H": "H (วันหยุด)" if thai else "H (Holiday)",
    }
    stats_parts = []
    for r in ("P", "OP", "H"):
        if r in peaks:
            if thai:
                stats_parts.append(f"{rate_label[r]}: สูงสุด {peaks[r]:,.1f} kW · เฉลี่ย {means[r]:,.1f} kW")
            else:
                stats_parts.append(f"{rate_label[r]}: max {peaks[r]:,.1f} kW · avg {means[r]:,.1f} kW")
    stats_line = "    |    ".join(stats_parts)

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
    title_lines = 1 + title.count("\n")
    top_margin = 0.97
    if stats_line:
        # วางบรรทัดสรุปตัวเลขไว้ใต้หัวเรื่อง (ซึ่งอาจมี subtitle บัญชี/บริษัทต่ออยู่แล้ว 1 บรรทัด)
        # จึงต้องขยับตำแหน่ง y ลงตามจำนวนบรรทัดของหัวเรื่อง กันทับกัน
        stats_y = 0.975 - title_lines * 0.045
        fig.text(0.5, stats_y, stats_line, ha="center", fontsize=9.5, color="#333333")
        top_margin -= 0.045
    fig.text(0.01, 0.005,
              "Box = Q1-Q3, bold line = median, whiskers = P5-P95, dot = max 15-min value. Real AMR data.",
              fontsize=8, color="gray")
    fig.tight_layout(rect=(0, 0.02, 1, top_margin))

    buf = io.BytesIO()
    try:
        fig.savefig(buf, format="png", dpi=140)
    finally:
        plt.close(fig)
    return buf.getvalue()
