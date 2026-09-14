"""ตัวอย่างการใช้งาน amr_mapping

รันด้วย:
    python examples/demo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amr_mapping import Customer, estimate_customer_load, load_reference_data


def print_forecast(title: str, customer: Customer, reference) -> None:
    print(f"\n=== {title} ===")
    print(f"ลูกค้า: {customer.name} (บัญชี {customer.account_no})")
    print(f"ประเภทธุรกิจ: {customer.business_type_code or 'ไม่ทราบ'} | อัตรา: {customer.rate_code or 'ไม่ทราบ'} | KVA: {customer.contract_kva or 'ไม่ทราบ'}")

    result = estimate_customer_load(customer, reference)

    bt = reference.business_types.get(result.matched_profile.business_type_code)
    bt_name = bt.name_th if bt else result.matched_profile.business_type_code

    print(f"จับคู่กับโปรไฟล์: ธุรกิจ={bt_name} ({result.matched_profile.business_type_code}), อัตรา={result.matched_profile.rate_code}")
    print(f"ระดับการจับคู่: {result.match_level.value}")
    print(f"ตัวคูณสเกล (customer_kva / reference_kva): {result.scale_factor}")
    print("กำลังไฟฟ้าสูงสุด (kW):", result.demand_kw)
    print("พลังงานไฟฟ้า (kWh):  ", result.energy_kwh)
    if result.warnings:
        print("คำเตือน:")
        for w in result.warnings:
            print(f"  - {w}")


def main() -> None:
    reference = load_reference_data()

    # กรณีที่ 1: ทราบทั้งประเภทธุรกิจและอัตรา และ KVA (คล้ายผู้ใช้ไฟในภาพที่ 1: โรงแรม รหัสอัตรา 50, KVA 2000)
    # แต่สมมติว่าผู้ใช้ไฟรายนี้ "ไม่มี AMR" ของตัวเอง จึงต้องพยากรณ์จากโปรไฟล์กลุ่มโรงแรม
    hotel_customer = Customer(
        account_no="020024424275",
        name="บจก. พิพัฒน์ ดีเวลลอปเมนท์ (โนโวเทล ฟิวเจอร์พาร์ค รังสิต)",
        business_type_code="63201",
        rate_code="50",
        contract_kva=2000,
        has_amr=False,
    )
    print_forecast("กรณี 1: ทราบธุรกิจ+อัตรา+KVA ครบ (EXACT match)", hotel_customer, reference)

    # กรณีที่ 2: ทราบอัตรา (3224) แต่ยังไม่ได้จัดประเภทธุรกิจ -> fallback เป็น RATE_ONLY
    unclassified_customer = Customer(
        account_no="9029 020029174637",
        name="ห้างหุ้นส่วนบริษัท ศรีนเฟิล เฮลท์แคร์-กำแพงเพชร จำกัด",
        business_type_code=None,
        rate_code="3224",
        contract_kva=None,
        has_amr=False,
    )
    print_forecast("กรณี 2: ทราบเฉพาะอัตรา ยังไม่จัดประเภทธุรกิจ (RATE_ONLY match)", unclassified_customer, reference)

    # กรณีที่ 3: ทราบประเภทธุรกิจ (โรงพยาบาล) แต่ไม่ทราบอัตรา และไม่มีอัตราที่ตรงกันในตารางอ้างอิง
    hospital_customer = Customer(
        account_no="TEST-HOSP-001",
        name="ลูกค้าโรงพยาบาลตัวอย่าง",
        business_type_code="86101",
        rate_code=None,
        contract_kva=900,
        has_amr=False,
    )
    print_forecast("กรณี 3: ทราบเฉพาะประเภทธุรกิจ (BUSINESS_ONLY match)", hospital_customer, reference)

    # กรณีที่ 4: ไม่ทราบทั้งธุรกิจและอัตราเลย -> DEFAULT fallback
    unknown_customer = Customer(
        account_no="TEST-UNKNOWN-001",
        name="ลูกค้าที่ไม่มีข้อมูลจัดประเภทเลย",
        business_type_code=None,
        rate_code=None,
        contract_kva=None,
        has_amr=False,
    )
    print_forecast("กรณี 4: ไม่ทราบข้อมูลใดๆ เลย (DEFAULT fallback)", unknown_customer, reference)


if __name__ == "__main__":
    main()
