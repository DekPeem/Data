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
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional

from .amr_downloader import ProgressCallback, download_amr_kw_reports, download_amr_with_profile
from .loader import (
    DEFAULT_DATA_DIR,
    ReferenceData,
    append_import_log_local,
    append_site_curve_local,
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
    parse_report_header,
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
    has_solar: bool = False,
    site_info: Optional[dict] = None,
) -> LoadProfile:
    """แปลงไฟล์ AMR ที่ดาวน์โหลดมาแล้วเป็น LoadProfile เฉลี่ยหลายเดือน แล้ว upsert ลง
    load_profiles.csv — ใช้ร่วมกันทั้ง import_amr_for_business และ import_amr_auto

    site_info (ถ้าระบุ — {"company_name": ..., "account_no": ...}) จะทำให้บันทึกเส้นโค้งของ
    ไซต์นี้แยกต่างหากไว้ที่ site_curves_local.csv ด้วย (ไฟล์ local-only มีชื่อบริษัทจริง — ดู
    loader.append_site_curve_local) เพื่อให้กดดูกราฟของไซต์นี้แยกจากค่าเฉลี่ยรวมได้ทีหลังในหน้า
    Admin — ใช้เฉพาะโหมด auto (import_amr_auto) เพราะเป็นโหมดเดียวที่ทราบชื่อบริษัทจริง"""

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
        has_solar=has_solar,
    )

    reference: ReferenceData = load_reference_data(data_dir)
    updated_profiles = upsert_load_profile(reference.load_profiles, new_profile)
    save_load_profiles(updated_profiles, data_dir / "load_profiles.csv")
    log(
        f"💾 บันทึกลง {data_dir / 'load_profiles.csv'} แล้ว "
        f"(key: {business_type_code}, {rate_code}, ติด Solar: {'ใช่' if has_solar else 'ไม่'})"
    )

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
        has_solar=has_solar,
    )
    updated_curves = upsert_load_curve(reference.load_curves, new_curve)
    save_load_curves(updated_curves, data_dir / "load_curves.csv")
    log(f"💾 บันทึกเส้นโค้งรายชั่วโมงลง {data_dir / 'load_curves.csv'} แล้ว")

    if site_info and site_info.get("account_no"):
        try:
            append_site_curve_local(
                site_info.get("company_name") or "",
                site_info["account_no"],
                new_curve,
                data_dir / "site_curves_local.csv",
            )
            log("💾 บันทึกกราฟแยกของไซต์นี้ไว้ในเครื่อง (site_curves_local.csv — ไม่ commit เข้า repo)")
        except OSError as e:  # noqa: BLE001 — บันทึกกราฟแยกของไซต์ไม่สำเร็จ ต้องไม่ทำให้ผลหลักพังไปด้วย
            log(f"⚠️ บันทึกกราฟแยกของไซต์ไม่สำเร็จ (ไม่กระทบผลลัพธ์หลัก): {e}")

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
    has_solar: bool = False,
    data_dir: Optional[Path] = None,
    download_dir: Optional[Path] = None,
    log: ProgressCallback = _noop,
    headless: bool = True,
) -> LoadProfile:
    """ดาวน์โหลด + ประมวลผล AMR จริงของบัญชีที่ระบุ แล้วอัปเดตโปรไฟล์อ้างอิงของ
    (business_type_code, rate_code, has_solar) ใน load_profiles.csv ด้วยค่าเฉลี่ยที่ได้

    has_solar ต้องกรอกเอง (ไม่มีการตรวจจับอัตโนมัติ) เพราะหน้าข้อมูลผู้ใช้ไฟของ PEA ไม่มีฟิลด์
    บอกสถานะ Solar/Net Metering ให้ตรวจจับได้ — แยกเป็นโปรไฟล์อ้างอิงคนละชุดจากคู่ธุรกิจ+อัตรา
    เดียวกันที่ไม่ติด Solar เพราะรูปแบบการใช้ไฟช่วงกลางวันต่างกันมาก (ดู models.LoadProfile)

    ไฟล์ดิบที่ดาวน์โหลดมาจะถูกเก็บไว้ที่ download_dir (ค่า default: DEFAULT_DOWNLOAD_DIR =
    amr_downloads/ ที่ root ของ repo — gitignored) ไม่ลบทิ้งอัตโนมัติแล้ว เพื่อให้รันซ้ำ/นำเข้า
    เพิ่มไม่ต้องดาวน์โหลดของเดิมใหม่ (ใช้ cache ตามบัญชี+มิเตอร์+ช่วงวันที่ ดู amr_downloader.py)

    บันทึกประวัติ (import_log_local.csv — ไฟล์ local-only เหมือนโหมดอื่นๆ) แยกทีละบัญชีที่ระบุมา
    ด้วย (อ่านชื่อบริษัทจากหัวรายงานของไฟล์ที่ดาวน์โหลดมาได้ของบัญชีนั้น) เพื่อให้ตามดูย้อนหลังได้
    ว่าโปรไฟล์นี้เฉลี่ยมาจากบัญชีจริงไหนบ้าง — ไม่ได้บันทึกเส้นโค้งแยกของแต่ละไซต์ (ต่างจาก
    import_amr_from_files) เพราะฟังก์ชันนี้เฉลี่ยรวมได้หลายบัญชีเข้าด้วยกันในคำสั่งเดียว ไม่มีเส้น
    โค้งของบัญชีใดบัญชีหนึ่งแยกเดี่ยวๆ ให้บันทึก

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

    profile = _build_profile_from_downloads(
        downloaded_files, business_type_code, rate_code, billing_method, contract_kva, notes, data_dir, log,
        has_solar=has_solar,
    )

    # บันทึกประวัติการนำเข้าในเครื่อง (import_log_local.csv) เหมือน import_amr_from_files —
    # ฟังก์ชันนี้ (โหมดกรอกประเภทธุรกิจเอง) เดิมไม่เคยบันทึกเลย ทำให้ลิสต์ "ค้นหาบริษัท/ไซต์" ใน
    # หน้า Admin หาชื่อบริษัทที่นำเข้าผ่านโหมดนี้ไม่เจอ — อ่านหัวรายงานของแต่ละไฟล์ที่ดาวน์โหลด
    # สำเร็จ (อาจมีหลายบัญชีถ้า accounts ระบุมาหลายเลข) เพื่อเอาชื่อบริษัทจริงมาบันทึกแยกทีละบัญชี
    # ให้ตรงกับ business_type_code/rate_code ที่ job นี้ resolve ออกมา (ไม่ใช่ตัวโปรไฟล์ที่เฉลี่ย
    # รวมกันแล้ว ซึ่งไม่มีข้อมูลรายบัญชีเหลืออยู่)
    logged_accounts = set()
    for r in results:
        if not (r.success and r.file_path) or r.account_no in logged_accounts:
            continue
        logged_accounts.add(r.account_no)
        try:
            header_info = parse_report_header(r.file_path)
        except Exception as e:  # noqa: BLE001 — อ่านหัวรายงานไม่สำเร็จต้องไม่ทำให้ผลการนำเข้าหลักพัง
            log(f"⚠️ อ่านหัวรายงานของบัญชี {r.account_no} เพื่อบันทึกประวัติไม่สำเร็จ (ไม่กระทบผลลัพธ์หลัก): {e}")
            continue
        company_name = (header_info.get("ชื่อผู้ใช้ไฟ") or "").strip()
        try:
            append_import_log_local(
                {
                    "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "business_type_code": business_type_code,
                    "rate_code": rate_code,
                    "company_name": company_name,
                    "account_no": r.account_no,
                    "has_solar": "true" if has_solar else "false",
                },
                data_dir / "import_log_local.csv",
            )
        except OSError as e:  # noqa: BLE001 — บันทึก log ไม่สำเร็จ ต้องไม่ทำให้ผลการนำเข้าหลักพังไปด้วย
            log(f"⚠️ บันทึกประวัติการนำเข้าในเครื่องไม่สำเร็จ (ไม่กระทบผลลัพธ์หลัก): {e}")

    return profile


def import_amr_from_files(
    file_paths: List[str],
    business_type_code: str = "",
    rate_code: str = "",
    contract_kva: Optional[float] = None,
    source_label: str = "",
    billing_method: str = "",
    has_solar: bool = False,
    data_dir: Optional[Path] = None,
    on_profile: Optional[Callable[[dict], None]] = None,
    log: ProgressCallback = _noop,
    site_label: str = "",
) -> LoadProfile:
    """เหมือน import_amr_for_business ทุกอย่าง ยกเว้นไม่ต้อง login/ดาวน์โหลดจากเว็บ PEA เลย —
    ใช้ตอนมีไฟล์ "รายงานข้อมูลกิโลวัตต์ชั่วโมงแบบช่วงเวลา" (รูปแบบเดียวกับที่
    download_amr_kw_reports ดาวน์โหลดมาให้เอง — ดู pea_ingest.parse_interval_report) อยู่แล้ว
    ในเครื่อง (เช่น ได้รับมาจากที่อื่น ไม่มี username/password ของบัญชีนั้นเอง)

    business_type_code/rate_code/contract_kva/billing_method ไม่ต้องกรอกก็ได้ (ปล่อยว่าง) —
    จะพยายามหาให้อัตโนมัติก่อนเสมอ:
      1. อ่านเลขบัญชี/ชื่อผู้ใช้ไฟ/Tariff จาก "หัวรายงาน" ในไฟล์แรกที่แนบมา (ดู
         pea_ingest.parse_report_header — ไฟล์ export ของ PEA มีข้อมูลนี้อยู่ในตัวไฟล์เองอยู่แล้ว)
      2. เอาเลขบัญชีที่อ่านได้ไปค้นในทะเบียนลูกค้า (customers.csv/customers_local.csv) ถ้าเจอ
         จะได้ business_type_code/rate_code/contract_kva ของบัญชีนั้นมาใช้ต่อ (ค่าที่ผู้ใช้กรอก
         มาเองในพารามิเตอร์ยังมีความสำคัญกว่าเสมอ ถ้าระบุมาจะไม่ถูกเขียนทับด้วยค่าจากทะเบียน)
    ประเภทธุรกิจ/TSIC ไม่มีทางหาได้จากไฟล์นี้เอง (ไม่มีข้อมูลนี้อยู่ในไฟล์ export เลย ต่างจาก
    บัญชี/ชื่อ/Tariff) จึงต้องพึ่งทะเบียนลูกค้าเท่านั้น — ถ้าหา business_type_code หรือ rate_code
    ไม่ได้เลยทั้งจากที่ระบุมาเองและจากทะเบียน จะ raise RuntimeError บอกชัดเจนว่าต้องกรอกเอง

    ถ้าอ่านเจอเลขบัญชี/ชื่อบริษัทจากไฟล์ จะบันทึกประวัติ + กราฟแยกของไซต์นี้ไว้ในเครื่องเองด้วย
    (import_log_local.csv/site_curves_local.csv — ไฟล์ local-only เหมือนโหมดอัตโนมัติจากเว็บ)

    site_label (ไม่บังคับ): ต่อท้ายชื่อบริษัทที่อ่านได้จากไฟล์เป็น "ชื่อบริษัท (site_label)" ก่อน
    บันทึกลงไฟล์ local-only ด้านบน — ใช้แยกแยะกรณีบริษัทเดียวกันมีหลายมิเตอร์/หลายไซต์ (เช่น
    คลังสินค้าคนละแห่ง) ที่ใช้ชื่อผู้ใช้ไฟตัวเดียวกันในไฟล์ export ทุกไฟล์ ไม่กระทบ notes/
    source_label ที่ไปอยู่ใน load_profiles.csv/load_curves.csv (คนละคอลัมน์กัน — คอลัมน์นั้น
    commit เข้า repo ได้ ห้ามมีข้อมูลระบุตัวตน)
    """

    data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR

    header_info: dict = {}
    if file_paths:
        try:
            header_info = parse_report_header(file_paths[0])
        except Exception as e:  # noqa: BLE001 — อ่านหัวรายงานไม่สำเร็จต้องไม่ทำให้ทั้ง job พังไปด้วย
            log(f"⚠️ อ่านหัวรายงานจากไฟล์ไม่สำเร็จ (ไม่กระทบการประมวลผลหลัก): {e}")

    account_no = (header_info.get("บัญชีผู้ใช้ไฟ") or "").strip()
    company_name = (header_info.get("ชื่อผู้ใช้ไฟ") or "").strip()
    if site_label.strip() and company_name:
        company_name = f"{company_name} ({site_label.strip()})"
    if account_no:
        log(f"📋 พบข้อมูลในไฟล์: บัญชี {account_no}" + (f" ({company_name})" if company_name else ""))

    if on_profile:
        try:
            on_profile({"name": company_name, "account_no": account_no, "meter_no": header_info.get("หมายเลขมิเตอร์") or ""})
        except Exception as e:  # noqa: BLE001 — callback error ต้องไม่ทำให้ job หลักพังไปด้วย
            log(f"⚠️ on_profile callback error (ไม่กระทบผลการนำเข้าหลัก): {e}")

    if not billing_method:
        billing_method = (header_info.get("Tariff") or "").strip() or "TOU"

    if (not business_type_code or not rate_code or contract_kva is None) and account_no:
        reference: ReferenceData = load_reference_data(data_dir)
        matched = next((c for c in reference.customers if c.account_no == account_no), None)
        if matched:
            log(f"✅ พบบัญชี {account_no} ในทะเบียนลูกค้า — ใช้ประเภทธุรกิจ/อัตรา/KVA จากทะเบียนอัตโนมัติ")
            business_type_code = business_type_code or (matched.business_type_code or "")
            rate_code = rate_code or (matched.rate_code or "")
            if contract_kva is None:
                contract_kva = matched.contract_kva

    if not business_type_code or not rate_code:
        hint = ""
        if account_no:
            hint = (
                f" (พบบัญชี {account_no}" + (f" - {company_name}" if company_name else "")
                + " ในไฟล์ แต่ไม่พบในทะเบียนลูกค้า หรือทะเบียนยังไม่ได้ระบุประเภทธุรกิจ/อัตราไว้)"
            )
        raise RuntimeError(f"ไม่ทราบประเภทธุรกิจ/รหัสอัตราของบัญชีนี้{hint} — กรุณากรอกประเภทธุรกิจและรหัสอัตราเอง")

    notes = "ค่าเฉลี่ยจาก AMR จริง (นำเข้าจากไฟล์ที่แนบเอง, anonymized)"
    if source_label:
        notes += f" - {source_label}"

    result_profile = _build_profile_from_downloads(
        file_paths, business_type_code, rate_code, billing_method, contract_kva, notes, data_dir, log,
        has_solar=has_solar,
        site_info={"company_name": company_name, "account_no": account_no} if account_no else None,
    )

    if account_no:
        try:
            append_import_log_local(
                {
                    "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "business_type_code": business_type_code,
                    "rate_code": rate_code,
                    "company_name": company_name,
                    "account_no": account_no,
                    "has_solar": "true" if has_solar else "false",
                },
                data_dir / "import_log_local.csv",
            )
        except OSError as e:  # noqa: BLE001 — บันทึก log ไม่สำเร็จ ต้องไม่ทำให้ผลการนำเข้าหลักพังไปด้วย
            log(f"⚠️ บันทึกประวัติการนำเข้าในเครื่องไม่สำเร็จ (ไม่กระทบผลลัพธ์หลัก): {e}")

    return result_profile


def import_amr_auto(
    username: str,
    password: str,
    start_date: str,
    end_date: str,
    source_label: str = "",
    has_solar: bool = False,
    data_dir: Optional[Path] = None,
    download_dir: Optional[Path] = None,
    on_profile: Optional[Callable[[dict], None]] = None,
    log: ProgressCallback = _noop,
    headless: bool = True,
) -> LoadProfile:
    """เวอร์ชัน "ใส่แค่ Username/Password" — ดึงประเภทอัตรา/ประเภทธุรกิจ/KVA จากหน้า
    ข้อมูลผู้ใช้ไฟของ PEA เองอัตโนมัติ (ไม่ต้องเลือก/กรอกเอง) แล้วดาวน์โหลด + ประมวลผล
    AMR ของบัญชีนั้น (username = เลขบัญชี, 1 login = 1 บัญชี) เหมือน import_amr_for_business

    has_solar ต้องกรอกเอง (ไม่ตรวจจับอัตโนมัติ — ดู import_amr_for_business) เพราะหน้าข้อมูล
    ผู้ใช้ไฟของ PEA ไม่มีฟิลด์บอกสถานะ Solar/Net Metering ให้ตรวจจับได้

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

    result_profile = _build_profile_from_downloads(
        downloaded_files, business_type_code, rate_code, billing_method, contract_kva, notes, data_dir, log,
        has_solar=has_solar,
        site_info={"company_name": profile_info.get("name") or "", "account_no": profile_info.get("account_no") or ""},
    )

    # บันทึกประวัติ "ทำอะไรไปแล้วบ้าง มีข้อมูลของใครบ้าง" ไว้ในเครื่องตัวเองเท่านั้น (ชื่อบริษัท/
    # เลขบัญชีจริง) — import_log_local.csv อยู่ใน .gitignore แล้ว หลักการเดียวกับ
    # customers_local.csv ไม่เคยถูกเขียนไปที่ไฟล์อื่นที่ commit เข้า repo ได้เลย (โหมด auto
    # เท่านั้นที่มีชื่อบริษัทจริงจากการ scrape — โหมด manual (import_amr_for_business) ไม่มี
    # ชื่อบริษัทให้บันทึก จึงไม่ต้องมี log แบบนี้)
    try:
        append_import_log_local(
            {
                "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "business_type_code": business_type_code,
                "rate_code": rate_code,
                "company_name": profile_info.get("name") or "",
                "account_no": profile_info.get("account_no") or "",
                "has_solar": "true" if has_solar else "false",
            },
            data_dir / "import_log_local.csv",
        )
    except OSError as e:  # noqa: BLE001 — บันทึก log ไม่สำเร็จ ต้องไม่ทำให้ผลการนำเข้าหลักพังไปด้วย
        log(f"⚠️ บันทึกประวัติการนำเข้าในเครื่องไม่สำเร็จ (ไม่กระทบผลลัพธ์หลัก): {e}")

    return result_profile
