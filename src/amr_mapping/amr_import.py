"""รวมขั้นตอน ดาวน์โหลด AMR จริง (Selenium) → parse → เฉลี่ยหลายเดือน → บันทึกลง
load_profiles.csv แบบ anonymized ในคำสั่งเดียว — ใช้โดย web/app.py (endpoint นำเข้า AMR)

หลักการความปลอดภัยเดิมยังคงอยู่: ไฟล์ดิบที่ดาวน์โหลดมา (มีเลขบัญชี/เลขมิเตอร์) จะถูกลบทิ้ง
ทันทีหลังประมวลผลเสร็จ มีแต่ตัวเลข P/OP/H ที่เฉลี่ยแล้วเท่านั้นที่ถูกเขียนลง load_profiles.csv
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import List, Optional

from .amr_downloader import ProgressCallback, download_amr_kw_reports
from .loader import DEFAULT_DATA_DIR, ReferenceData, load_reference_data, save_load_profiles, upsert_load_profile
from .models import LoadProfile
from .pea_ingest import aggregate_interval_readings, average_profiles, parse_interval_report


def _noop(_: str) -> None:
    pass


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
    log: ProgressCallback = _noop,
    headless: bool = True,
) -> LoadProfile:
    """ดาวน์โหลด + ประมวลผล AMR จริงของบัญชีที่ระบุ แล้วอัปเดตโปรไฟล์อ้างอิงของ
    (business_type_code, rate_code) ใน load_profiles.csv ด้วยค่าเฉลี่ยที่ได้

    คืนค่า LoadProfile ที่บันทึกไปแล้ว
    """

    data_dir = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    download_dir = tempfile.mkdtemp(prefix="amr_download_")

    try:
        log(f"📂 โฟลเดอร์ดาวน์โหลดชั่วคราว: {download_dir}")
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

        log(f"📊 ประมวลผล {len(downloaded_files)} ไฟล์ ...")
        monthly_profiles = []
        for path in downloaded_files:
            try:
                readings = parse_interval_report(path)
                if not readings:
                    log(f"⚠️ ไม่มีข้อมูลใน {Path(path).name}")
                    continue
                monthly_profiles.append(aggregate_interval_readings(readings, label=Path(path).name))
            except Exception as e:  # noqa: BLE001
                log(f"⚠️ อ่านไฟล์ {Path(path).name} ไม่สำเร็จ: {e}")

        if not monthly_profiles:
            raise RuntimeError("ไม่สามารถอ่านข้อมูลจากไฟล์ที่ดาวน์โหลดมาได้เลย")

        agg = average_profiles(monthly_profiles)
        log(f"✅ เฉลี่ยจาก {agg['n_months']} ไฟล์: demand_kw={agg['demand_kw']} energy_kwh={agg['energy_kwh']}")

        notes = f"ค่าเฉลี่ยจาก AMR จริง {agg['n_months']} ไฟล์ (นำเข้าอัตโนมัติผ่านเว็บ, anonymized)"
        if source_label:
            notes += f" - {source_label}"

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

        return new_profile
    finally:
        # ลบไฟล์ดิบทิ้งทันทีเสมอ (มีเลขบัญชี/เลขมิเตอร์อยู่ในไฟล์) — เก็บไว้แค่ตัวเลข
        # ที่เฉลี่ยแล้วใน load_profiles.csv เท่านั้น
        shutil.rmtree(download_dir, ignore_errors=True)
        log("🧹 ลบไฟล์ดิบที่ดาวน์โหลดมาแล้ว (ไม่เก็บข้อมูลระบุตัวตนลูกค้าไว้)")
