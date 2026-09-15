"""รวมขั้นตอน ดาวน์โหลด AMR จริง (Selenium) → parse → เฉลี่ยหลายเดือน → บันทึกลง
load_profiles.csv แบบ anonymized ในคำสั่งเดียว — ใช้โดย web/app.py (endpoint นำเข้า AMR)

หลักการความปลอดภัยเดิมยังคงอยู่สำหรับสิ่งที่ commit เข้า repo public ได้: มีแต่ตัวเลข P/OP/H
ที่เฉลี่ยแล้ว (anonymized) เท่านั้นที่ถูกเขียนลง load_profiles.csv/business_types.csv

⚠️ เปลี่ยนจากเดิม: ไฟล์ AMR ดิบที่ดาวน์โหลดมา (มีเลขบัญชี/เลขมิเตอร์) เดิมจะถูกลบทิ้งทันที
หลังประมวลผลเสร็จเสมอ — ตอนนี้เก็บไว้ที่ amr_downloads/ แทน (ไม่ลบอัตโนมัติแล้ว) เพื่อให้
รันซ้ำ/ดึงเดือนเพิ่มไม่ต้องดาวน์โหลดของเดิมใหม่ (ดู _cache_key ใน amr_downloader.py) โฟลเดอร์
นี้อยู่ใน .gitignore แล้ว (ไม่มีทาง commit/push ขึ้น GitHub ได้) เหมือนหลักการเดียวกับ
customers_local.csv — ข้อมูลระบุตัวตนลูกค้าจริงเก็บไว้ในเครื่องตัวเองได้ปลอดภัย แค่ต้องไม่ให้
มันเข้า repo public เท่านั้น
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, List, Optional

from .amr_downloader import ProgressCallback, download_amr_kw_reports, download_amr_with_profile
from .loader import (
    DEFAULT_DATA_DIR,
    ReferenceData,
    load_reference_data,
    save_business_types,
    save_load_curves,
    save_load_profiles,
    upsert_business_type,
    upsert_load_curve,
    upsert_load_profile,
)
from .models import BusinessType, LoadCurve, LoadProfile
from .pea_ingest import (
    aggregate_interval_readings,
    average_profiles,
    compute_hourly_curve,
    parse_interval_report,
)

# โฟลเดอร์เก็บไฟล์ AMR ดิบที่ดาวน์โหลดมาแบบถาวร (ไม่ใช่ temp dir ที่ลบทิ้งหลังเสร็จเหมือนเดิม)
# อยู่ที่ root ของ repo นี้ — มี .gitignore คุ้มครองแล้ว (amr_downloads/) ไม่มีทางหลุดเข้า
# repo public ได้ ใช้เป็นค่า default เมื่อไม่ได้ระบุ download_dir เอง
DEFAULT_DOWNLOAD_DIR = Path(__file__).resolve().parents[2] / "amr_downloads"


def _noop(_: str) -> None:
    pass


def _build_profile_from_downloads(
    downloaded_files: List[str],
    business_type_code: str,
    rate_code: str,
    billing_method: str,
    contract_kva: Optional[float],
    notes: str,
    data_dir: Path,
    log: ProgressCallback,
) -> LoadProfile:
    """แปลงไฟล์ AMR ที่ดาวน์โหลดมาแล้วเป็น LoadProfile เฉลี่ยหลายเดือน แล้ว upsert ลง
    load_profiles.csv — ใช้ร่วมกันทั้ง import_amr_for_business และ import_amr_auto"""

    log(f"📊 ประมวลผล {len(downloaded_files)} ไฟล์ ...")
    monthly_profiles = []
    all_readings = []  # รวม interval readings ของทุกไฟล์ ไว้คำนวณเส้นโค้งรายชั่วโมงด้วย (ดูด้านล่าง)
    for path in downloaded_files:
        try:
            readings = parse_interval_report(path)
            if not readings:
                log(f"⚠️ ไม่มีข้อมูลใน {Path(path).name}")
                continue
            monthly_profiles.append(aggregate_interval_readings(readings, label=Path(path).name))
            all_readings.extend(readings)
        except Exception as e:  # noqa: BLE001
            log(f"⚠️ อ่านไฟล์ {Path(path).name} ไม่สำเร็จ: {e}")

    if not monthly_profiles:
        raise RuntimeError("ไม่สามารถอ่านข้อมูลจากไฟล์ที่ดาวน์โหลดมาได้เลย")

    agg = average_profiles(monthly_profiles)
    log(f"✅ เฉลี่ยจาก {agg['n_months']} ไฟล์: demand_kw={agg['demand_kw']} energy_kwh={agg['energy_kwh']}")

    new_profile = LoadProfile(
        business_type_code=business_type_code,
        rate_code=rate_code,
        billing_method=billing_method,
        demand_kw=agg["demand_kw"],
        energy_kwh=agg["energy_kwh"],
        contract_kva_ref=contract_kva,
        sample_size=agg["n_months"],
        notes=notes,
    )

    reference: ReferenceData = load_reference_data(data_dir)
    updated_profiles = upsert_load_profile(reference.load_profiles, new_profile)
    save_load_profiles(updated_profiles, data_dir / "load_profiles.csv")
    log(f"💾 บันทึกลง {data_dir / 'load_profiles.csv'} แล้ว (key: {business_type_code}, {rate_code})")

    # เส้นโค้งกำลังไฟฟ้าเฉลี่ยรายชั่วโมง (ใช้ raw interval readings ทั้งหมดที่รวมมาจากทุกไฟล์
    # โดยตรง ไม่ใช่ค่าเฉลี่ยรายเดือน — ละเอียดกว่า P/OP/H ที่เป็นแค่ยอดรวม/พีค ใช้แสดงกราฟว่า
    # ช่วงเวลาไหนของวันใช้ไฟเยอะ/น้อย แยกตามวันในสัปดาห์ได้)
    hourly = compute_hourly_curve(all_readings)
    new_curve = LoadCurve(
        business_type_code=business_type_code,
        rate_code=rate_code,
        hours=hourly,
        contract_kva_ref=contract_kva,
        sample_size=agg["n_months"],
        notes=notes,
    )
    updated_curves = upsert_load_curve(reference.load_curves, new_curve)
    save_load_curves(updated_curves, data_dir / "load_curves.csv")
    log(f"💾 บันทึกเส้นโค้งรายชั่วโมงลง {data_dir / 'load_curves.csv'} แล้ว")

    return new_profile


def import_amr_for_business(
    username: str,
    password: str,
    accounts: List[str],
    start_date: str,
    end_date: str,
    business_type_code: str,
    rate_code: str,
    contract_kva: Optional[float],
    source_label: str,
    billing_method: str = "TOU",
    data_dir: Optional[Path] = None,
    download_dir: Optional[Path] = None,
    log: ProgressCallback = _noop,
    headless: bool = True,
) -> LoadProfile:
    """ดาวน์โหลด + ประมวลผล AMR จริงของบัญชีที่ระบุ แล้วอัปเดตโปรไฟล์อ้างอิงของ
    (business_type_code, rate_code) ใน load_profiles.csv ด้วยค่าเฉลี่ยที่ได้

    ไฟล์ดิบที่ดาวน์โหลดมาจะถูกเก็บไว้ที่ download_dir (ค่า default: DEFAULT_DOWNLOAD_DIR =
    amr_downloads/ ที่ root ของ repo — gitignored) ไม่ลบทิ้งอัตโนมัติแล้ว เพื่อให้รันซ้ำ/นำเข้า
    เพิ่มไม่ต้องดาวน์โหลดของเดิมใหม่ (ใช้ cache ตามบัญชี+มิเตอร์+ช่วงวันที่ ดู amr_downloader.py)

    คืนค่า LoadProfile ที่บันทึกไปแล้ว
    """

    data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    download_dir = str(Path(download_dir) if download_dir else DEFAULT_DOWNLOAD_DIR)
    os.makedirs(download_dir, exist_ok=True)

    log(
        f"📂 โฟลเดอร์เก็บไฟล์ AMR (เก็บไว้ใช้ซ้ำ ไม่ลบอัตโนมัติ อยู่ใน .gitignore แล้ว "
        f"ไม่มีทางหลุดเข้า repo public): {download_dir}"
    )
    results = download_amr_kw_reports(
        username=username,
        password=password,
        accounts=accounts,
        start_date=start_date,
        end_date=end_date,
        download_dir=download_dir,
        log=log,
        headless=headless,
    )

    downloaded_files = [r.file_path for r in results if r.success and r.file_path]
    if not downloaded_files:
        raise RuntimeError("ดาวน์โหลดไม่สำเร็จเลยแม้แต่ไฟล์เดียว — ตรวจสอบ log ด้านบน")

    notes = "ค่าเฉลี่ยจาก AMR จริง (นำเข้าอัตโนมัติผ่านเว็บ, anonymized)"
    if source_label:
        notes += f" - {source_label}"

    return _build_profile_from_downloads(
        downloaded_files, business_type_code, rate_code, billing_method, contract_kva, notes, data_dir, log,
    )


def import_amr_auto(
    username: str,
    password: str,
    start_date: str,
    end_date: str,
    source_label: str = "",
    data_dir: Optional[Path] = None,
    download_dir: Optional[Path] = None,
    on_profile: Optional[Callable[[dict], None]] = None,
    log: ProgressCallback = _noop,
    headless: bool = True,
) -> LoadProfile:
    """เวอร์ชัน "ใส่แค่ Username/Password" — ดึงประเภทอัตรา/ประเภทธุรกิจ/KVA จากหน้า
    ข้อมูลผู้ใช้ไฟของ PEA เองอัตโนมัติ (ไม่ต้องเลือก/กรอกเอง) แล้วดาวน์โหลด + ประมวลผล
    AMR ของบัญชีนั้น (username = เลขบัญชี, 1 login = 1 บัญชี) เหมือน import_amr_for_business

    ถ้าเจอรหัสประเภทธุรกิจ (TSIC) ที่ยังไม่มีใน business_types.csv จะเพิ่มแถวใหม่ให้อัตโนมัติ
    ด้วย (ชื่อธุรกิจตามที่สแกนได้จากหน้า PEA) คืนค่า LoadProfile ที่บันทึกไปแล้ว

    ไฟล์ดิบที่ดาวน์โหลดมาจะถูกเก็บไว้ที่ download_dir (ค่า default: DEFAULT_DOWNLOAD_DIR =
    amr_downloads/ ที่ root ของ repo — gitignored) ไม่ลบทิ้งอัตโนมัติแล้ว เหมือน
    import_amr_for_business

    on_profile (ถ้าระบุ) จะถูกเรียกทันทีหลังดึงข้อมูลผู้ใช้ไฟจากหน้า CustProfile.aspx สำเร็จ
    พร้อมส่ง dict ข้อมูลดิบทั้งหมด (รวมชื่อจริง/เลขบัญชี/เลขมิเตอร์) ไปให้ — ใช้สำหรับให้ผู้เรียก
    (เช่น web/app.py) เก็บไว้แสดงผลในเครื่องตัวเองเท่านั้น (เช่นแสดงชื่อบริษัทจริงในหน้า Admin)
    ไม่ใช่สำหรับเขียนลงไฟล์ที่ commit เข้า repo ได้ — ฟังก์ชันนี้เองไม่เขียนข้อมูลจาก dict นี้
    ลงไฟล์ใดๆ ทั้งสิ้น (ยกเว้น business_type_code/name ที่เป็นสาธารณะอยู่แล้ว ดูด้านล่าง)
    """

    data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    download_dir = str(Path(download_dir) if download_dir else DEFAULT_DOWNLOAD_DIR)
    os.makedirs(download_dir, exist_ok=True)

    log(
        f"📂 โฟลเดอร์เก็บไฟล์ AMR (เก็บไว้ใช้ซ้ำ ไม่ลบอัตโนมัติ อยู่ใน .gitignore แล้ว "
        f"ไม่มีทางหลุดเข้า repo public): {download_dir}"
    )
    profile_info, results = download_amr_with_profile(
        username=username,
        password=password,
        start_date=start_date,
        end_date=end_date,
        download_dir=download_dir,
        log=log,
        headless=headless,
    )

    if on_profile:
        try:
            on_profile(profile_info)
        except Exception as e:  # noqa: BLE001 — callback error ต้องไม่ทำให้ job หลักพังไปด้วย
            log(f"⚠️ on_profile callback error (ไม่กระทบผลการนำเข้าหลัก): {e}")

    downloaded_files = [r.file_path for r in results if r.success and r.file_path]
    if not downloaded_files:
        raise RuntimeError("ดาวน์โหลดไม่สำเร็จเลยแม้แต่ไฟล์เดียว — ตรวจสอบ log ด้านบน")

    business_type_code = profile_info.get("business_type_code") or ""
    business_type_name = profile_info.get("business_type_name") or ""
    rate_code = profile_info.get("rate_code") or ""
    billing_method = profile_info.get("billing_method") or "TOU"

    if not business_type_code or not rate_code:
        raise RuntimeError(
            "ไม่สามารถตรวจจับประเภทธุรกิจ/ประเภทอัตราจากหน้าข้อมูลผู้ใช้ไฟได้ "
            "(business_type_code หรือ rate_code ว่างเปล่า) — ลองกรอกเองแทน"
        )

    kva_raw = (profile_info.get("kva") or "").replace(",", "").strip()
    try:
        contract_kva = float(kva_raw) if kva_raw else None
    except ValueError:
        contract_kva = None

    # เพิ่มประเภทธุรกิจใหม่อัตโนมัติ ถ้าเป็นรหัสที่ยังไม่เคยมีใน business_types.csv
    reference: ReferenceData = load_reference_data(data_dir)
    if business_type_code not in reference.business_types:
        new_bt = BusinessType(
            code=business_type_code,
            name_th=business_type_name or f"ธุรกิจรหัส {business_type_code}",
            category="auto",
            notes="เพิ่มอัตโนมัติจากการนำเข้า AMR (สแกนจากหน้าข้อมูลผู้ใช้ไฟของ PEA)",
        )
        updated_bts = upsert_business_type(reference.business_types, new_bt)
        save_business_types(updated_bts, data_dir / "business_types.csv")
        log(f"🆕 เพิ่มประเภทธุรกิจใหม่: {business_type_code} - {business_type_name}")

    notes = (
        "ค่าเฉลี่ยจาก AMR จริง (นำเข้าอัตโนมัติผ่านเว็บ ตรวจจับธุรกิจ/อัตรา/KVA "
        "อัตโนมัติจากหน้าข้อมูลผู้ใช้ไฟของ PEA, anonymized)"
    )
    if source_label:
        notes += f" - {source_label}"

    return _build_profile_from_downloads(
        downloaded_files, business_type_code, rate_code, billing_method, contract_kva, notes, data_dir, log,
    )
