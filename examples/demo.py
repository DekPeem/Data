"""ตัวอย่างการใช้งาน amr_mapping

รันด้วย:
    python examples/demo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amr_mapping import load_reference_data, normalize_tsic_code_with_audit


def print_match(title: str, tsic_code: str, reference) -> None:
    print(f"\n=== {title} ===")
    print(f"รหัส TSIC ที่ได้มา: {tsic_code}")

    if tsic_code in reference.business_types:
        bt = reference.business_types[tsic_code]
        print(f"จับคู่ตรงเป๊ะ (EXACT): {bt.name_th} ({bt.code})")
        return

    division_code = tsic_code[:2] if len(tsic_code) >= 2 else None
    same_division = [bt for bt in reference.business_types.values() if bt.division_code == division_code]
    if same_division:
        print(f"ไม่มีรหัส {tsic_code} ตรงเป๊ะในระบบ — ธุรกิจที่อยู่ TSIC division {division_code} เดียวกัน (ประมาณการ):")
        for bt in same_division[:3]:
            print(f"  - {bt.name_th} ({bt.code})")
    else:
        print(f"ไม่พบธุรกิจใดในระบบที่ตรงทั้งรหัสและ division {division_code} เลย")


def main() -> None:
    reference = load_reference_data()

    # กรณีที่ 1: รหัส TSIC ตรงกับธุรกิจที่มีอยู่ในระบบเป๊ะๆ (EXACT match)
    print_match("กรณี 1: รหัส TSIC ตรงเป๊ะกับธุรกิจที่มีในระบบ", "55101", reference)

    # กรณีที่ 2: รหัส TSIC ไม่ตรงเป๊ะ แต่ division เดียวกันมีธุรกิจอื่นอยู่ในระบบ (ประมาณการ)
    print_match("กรณี 2: ไม่ตรงรหัสเป๊ะ แต่ตรง TSIC division", "46999", reference)

    # กรณีที่ 3: รหัส TSIC เก่า (ก่อนแปลงมาตรฐาน) — ต้องแปลงผ่าน tsic_code_mapping ก่อน
    from amr_mapping.loader import DEFAULT_DATA_DIR, load_tsic_code_mapping

    tsic_mapping = load_tsic_code_mapping(DEFAULT_DATA_DIR / "tsic_code_mapping.csv")
    normalized_code, raw_code = normalize_tsic_code_with_audit("93311", tsic_mapping)
    print("\n=== กรณี 3: รหัส TSIC เก่าถูกแปลงเป็นรหัสมาตรฐานใหม่ก่อนจับคู่ ===")
    print(f"รหัสดิบที่ได้มา: {raw_code} -> รหัสมาตรฐานใหม่: {normalized_code}")
    print_match("จับคู่ด้วยรหัสที่แปลงแล้ว", normalized_code, reference)


if __name__ == "__main__":
    main()
