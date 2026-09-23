"""อัปเดต data/reference/load_profiles.csv ด้วยค่าเฉลี่ยที่คำนวณจากไฟล์ประวัติ
การอ่านหน่วยมิเตอร์ AMR จริง (register history .xls export จากระบบ PEA)

⚠️ สคริปต์นี้อ่าน "ไฟล์ดิบ" ที่อาจมีข้อมูลระบุตัวตนลูกค้า (ชื่อบริษัท, เลขบัญชี,
เลขมิเตอร์) จาก path ที่ระบุ แต่เขียนกลับลง load_profiles.csv เฉพาะ "ค่าเฉลี่ย"
ของกำลังไฟฟ้าสูงสุด/พลังงานไฟฟ้า (P/OP/H) เท่านั้น — ไม่มีข้อมูลระบุตัวตนใดๆ
ถูกเขียนลงไฟล์ผลลัพธ์ จึงปลอดภัยที่จะ commit ไฟล์ผลลัพธ์เข้า repository

ตัวอย่างการใช้งาน:
    python scripts/update_load_profile_from_register.py \\
        --input /path/to/Billing_register_history.xls \\
        --business-type 55101 \\
        --rate-code 50 \\
        --ct-ratio "50:5 A." \\
        --vt-ratio "22000:110 V." \\
        --contract-kva 2000 \\
        --source-label "AMR จริง เฉลี่ย 12 เดือน (ส.ค. 2568 - ส.ค. 2569), กฟภ.รังสิต"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amr_mapping import LoadProfile, load_reference_data, save_load_profiles, upsert_load_profile
from amr_mapping.pea_ingest import (
    average_profiles,
    compute_meter_multiplier,
    compute_monthly_profiles,
    parse_register_history,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", required=True, help="path ไฟล์ประวัติการอ่านหน่วยมิเตอร์ AMR (.xls)")
    parser.add_argument("--business-type", required=True, help="รหัสประเภทธุรกิจ เช่น 55101")
    parser.add_argument("--rate-code", required=True, help="รหัสประเภทอัตรา เช่น 50")
    parser.add_argument("--billing-method", default="TOU")
    parser.add_argument("--ct-ratio", help='เช่น "50:5 A." (ใช้คู่กับ --vt-ratio แทน --multiplier)')
    parser.add_argument("--vt-ratio", help='เช่น "22000:110 V."')
    parser.add_argument("--multiplier", type=float, help="ตัวคูณมิเตอร์โดยตรง (แทนการระบุ ct/vt ratio)")
    parser.add_argument("--contract-kva", type=float, default=None)
    parser.add_argument(
        "--source-label",
        default="",
        help="คำอธิบายที่มาของข้อมูล (ไม่ควรมีชื่อ/เลขบัญชีลูกค้า) จะถูกใส่ในคอลัมน์ notes",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="โฟลเดอร์ data/reference/ (ค่าเริ่มต้น: ที่ root ของ repo นี้)",
    )
    args = parser.parse_args()

    if args.multiplier is not None:
        multiplier = args.multiplier
    elif args.ct_ratio and args.vt_ratio:
        multiplier = compute_meter_multiplier(args.ct_ratio, args.vt_ratio)
    else:
        parser.error("ต้องระบุ --multiplier หรือ (--ct-ratio และ --vt-ratio) อย่างใดอย่างหนึ่ง")

    print(f"ตัวคูณมิเตอร์ที่ใช้: {multiplier}")

    readings = parse_register_history(args.input)
    print(f"อ่านประวัติได้ {len(readings)} แถว (เดือน)")

    monthly = compute_monthly_profiles(readings, multiplier)
    print(f"คำนวณโปรไฟล์รายเดือนได้ {len(monthly)} เดือน:")
    for m in monthly:
        print(f"  {m.month}: demand_kw={m.demand_kw} energy_kwh={m.energy_kwh}")

    agg = average_profiles(monthly)
    print(f"\nค่าเฉลี่ย {agg['n_months']} เดือน:")
    print(f"  demand_kw = {agg['demand_kw']}")
    print(f"  energy_kwh = {agg['energy_kwh']}")

    reference = load_reference_data(args.data_dir)
    notes = f"ค่าเฉลี่ยจาก AMR จริง {agg['n_months']} เดือน (anonymized)"
    if args.source_label:
        notes += f" - {args.source_label}"

    new_profile = LoadProfile(
        business_type_code=args.business_type,
        rate_code=args.rate_code,
        billing_method=args.billing_method,
        demand_kw=agg["demand_kw"],
        energy_kwh=agg["energy_kwh"],
        contract_kva_ref=args.contract_kva,
        sample_size=agg["n_months"],
        notes=notes,
    )

    updated_profiles = upsert_load_profile(reference.load_profiles, new_profile)
    data_dir = Path(args.data_dir) if args.data_dir else (Path(__file__).resolve().parents[1] / "data" / "reference")
    save_load_profiles(updated_profiles, data_dir / "load_profiles.csv")
    print(f"\n✅ อัปเดต {data_dir / 'load_profiles.csv'} แล้ว (key: {args.business_type}, {args.rate_code})")


if __name__ == "__main__":
    main()
