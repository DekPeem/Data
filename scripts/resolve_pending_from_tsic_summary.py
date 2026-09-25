"""จัดประเภทธุรกิจ (TSIC) ให้รายการ "รอทราบอัตรา" ตามรายชื่อ/รหัสจากไฟล์สรุป tsic_summary.md ที่
ผู้ใช้จัดทำส่งมา แล้วนำเข้าจริงให้อัตโนมัติ (สคริปต์นี้เฉพาะเจาะจงกับชุดรายชื่อ 23 บอ ชุดนั้นชุดเดียว
ไม่ใช่เครื่องมือทั่วไปที่ใช้ซ้ำได้กับรายการอื่น — ถ้ามีรายการ pending ชุดใหม่ ให้ใช้หน้า /pending-amr
กรอกเองตามปกติ หรือขอให้ช่วยเขียนสคริปต์ใหม่)

ไฟล์สรุปไม่มีรหัสอัตรา (rate_code) ให้เลย จึงใช้ "UNKNOWN" เป็นค่า placeholder (ตามธรรมเนียมเดียวกับ
บัญชีอื่นๆ จำนวนมากในระบบที่ยังไม่ทราบรหัสอัตราจริง — ไปแก้ไขเป็นรหัสจริงทีหลังได้ที่หน้า /overview)

รายการที่ไฟล์สรุปให้ TSIC มาให้เลือก 2 ตัวเลือก (เช่น ธุรกิจหลัก vs. solar) ถือว่า "ไม่ชัดเจนพอจะเดา
เอง" — สคริปต์นี้จะไม่นำเข้าอัตโนมัติให้ แค่แสดงให้ดูว่าต้องไปเลือกเองที่หน้า /pending-amr

ใช้:
    python scripts/resolve_pending_from_tsic_summary.py            # แสดงให้ดูก่อน (ไม่ทำอะไรจริง)
    python scripts/resolve_pending_from_tsic_summary.py --apply    # นำเข้าจริงเฉพาะรายการที่ชัดเจน
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amr_mapping.amr_import import import_amr_from_files
from amr_mapping.loader import (
    DEFAULT_DATA_DIR,
    load_pending_amr_local,
    normalize_company_name,
    remove_pending_amr_local,
)
from amr_mapping.mapping import UNKNOWN_RATE_CODE

# (ชื่อ/label ตามไฟล์สรุปที่ผู้ใช้ส่งมา, business_type_code, has_solar) — เฉพาะรายการที่ไฟล์สรุปให้
# รหัส TSIC มาตัวเดียวชัดเจน (ไม่นับ N/A ที่เป็นจุดมิเตอร์/ชื่อบุคคล ซึ่งไม่มีทางจัดประเภทธุรกิจได้)
RESOLVED: List[Tuple[str, str, bool]] = [
    ("บ.เน็ท โต้ แมนูแฟคเชอริ่ง จก.", "22209", False),
    ("บริษัท อันดามัน อินเตอร์ โฮลดิ้ง จำกัด", "64200", False),
    ("บริษัท ตะวันแดง 1999 จำกัด", "11011", False),
    ("บ.โรงพยาบาลเอกชล จก. (มหาชน)", "86101", False),
    ("บริษัท สยามซานิทารี่แวร์ อินดัสทรี(หนองแค) จำกัด", "23912", False),
    ("บริษัท เอส เค บี ครีเอทีฟ จำกัด", "73101", False),
    ("29_PMDH พริ้นมุกดาหาร PPA Solar", "86101", True),
    ("บริษัท ภาคใต้อุตสาหกรรมท่อน้ำไทย จำกัด", "22201", False),
    ("42_รพ.ปริ้นพิจิตร", "86101", False),
    ("บริษัท เอเชียโมดิไฟด์สตาร์ช จำกัด (2)", "10622", False),
    ("67_Utopian เทพารักษ์", "20119", True),
]

# ชื่อ/label ที่ไฟล์สรุปให้ TSIC มาหลายตัวเลือก (ไม่ชัดเจนพอจะเดาเอง) พร้อมตัวเลือกทั้งหมด — แค่
# "แสดงให้ดู" เตือนว่าต้องไปเลือกเองที่หน้า /pending-amr
AMBIGUOUS: List[Tuple[str, List[str]]] = [
    ("บริษัท เมืองกำแพง จำกัด", ["68102", "01111"]),
    ("บจก.พานาโซนิค แมนูแฟคเจอริ่ง (ประเทศไทย)", ["27500", "27100"]),
    ("01_Thaibengun", ["25999", "13990"]),
    ("36_บริษัท พีพีจี วูด จำกัด", ["16101", "16210"]),
    ("บริษัท ช้างคลานเวย์ จำกัด", ["55101", "68101"]),
    ("บ.พรเทพอินเตอร์กรุ๊ป จก.", ["46900", "46310"]),
    ("48_Eastern Energy Plus", ["38210", "35101"]),
    ("17_Utopian02 (เลขผู้ใช้ไฟฟ้า_ 020020353826)", ["20119", "35101"]),
]


def resolve_one(entry: dict, business_type_code: str, has_solar: bool, data_dir: Path, log=print) -> bool:
    """นำเข้าไฟล์ AMR ของรายการ pending 1 รายการจริงๆ (เหมือน resolve_entry ใน
    dedupe_pending_amr.py) แล้วลบออกจากคิวรอเมื่อสำเร็จ — คืน True ถ้าสำเร็จ"""

    file_paths = [p for p in (entry.get("file_paths") or "").split("|") if p]
    missing = [p for p in file_paths if not Path(p).exists()]
    if not file_paths or missing:
        log(f"  ⚠️ ข้าม (ไม่พบไฟล์ที่เก็บไว้ตอนนำเข้าครั้งแรกแล้ว): {entry.get('company_name') or entry.get('account_no')}")
        return False

    contract_kva: Optional[float] = None
    if entry.get("contract_kva"):
        try:
            contract_kva = float(entry["contract_kva"])
        except ValueError:
            contract_kva = None

    try:
        import_amr_from_files(
            file_paths=file_paths,
            business_type_code=business_type_code,
            rate_code=UNKNOWN_RATE_CODE,
            contract_kva=contract_kva,
            source_label=entry.get("source_label", ""),
            has_solar=has_solar,
            data_dir=data_dir,
            site_label="",
            log=log,
        )
    except Exception as e:  # noqa: BLE001 — รายการหนึ่งพังต้องไม่ทำให้รายการอื่นหยุดนำเข้าไปด้วย
        log(f"  ❌ นำเข้าไม่สำเร็จ: {entry.get('company_name') or entry.get('account_no')} — {e}")
        return False

    remove_pending_amr_local(entry["pending_id"], data_dir / "pending_amr_local.csv")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="นำเข้าจริง (ไม่ใส่ = แสดงให้ดูเฉยๆ)")
    args = parser.parse_args()

    data_dir = DEFAULT_DATA_DIR
    pending_entries = load_pending_amr_local(data_dir / "pending_amr_local.csv")

    by_name: Dict[str, List[dict]] = {}
    for e in pending_entries:
        by_name.setdefault(normalize_company_name(e.get("company_name") or ""), []).append(e)

    print(f"จับคู่ได้ชัดเจน (business_type_code เดียว): {len(RESOLVED)} รายการ\n")
    matched: List[Tuple[dict, str, bool]] = []
    for name, code, has_solar in RESOLVED:
        candidates = by_name.get(normalize_company_name(name), [])
        if not candidates:
            print(f"  ⚠️ ไม่พบในคิว (อาจถูกจัดการไปแล้ว หรือชื่อไม่ตรงเป๊ะ): {name}")
            continue
        for entry in candidates:
            matched.append((entry, code, has_solar))
            solar_label = " (ติด Solar)" if has_solar else ""
            print(f"  - {name} -> {code}{solar_label}")

    print(f"\nต้องเลือกเอง (ไฟล์สรุปให้รหัส TSIC มากกว่า 1 ตัวเลือก): {len(AMBIGUOUS)} รายการ")
    for name, codes in AMBIGUOUS:
        candidates = by_name.get(normalize_company_name(name), [])
        found = "พบในคิว" if candidates else "ไม่พบในคิว"
        print(f"  - {name} -> เลือกเองจาก {'/'.join(codes)} ({found}) — ไปที่หน้า /pending-amr")

    if not args.apply:
        print(
            "\n(นี่แค่แสดงให้ดูก่อนเฉยๆ ยังไม่ได้นำเข้าจริง — ใส่ --apply เพื่อนำเข้ารายการที่จับคู่ชัดเจนแล้วจริง "
            "รายการที่ต้องเลือกเองยังต้องไปทำที่หน้า /pending-amr เสมอ ไม่มีทางอัตโนมัติให้)"
        )
        return

    print("\nกำลังนำเข้า...")
    succeeded = 0
    for entry, code, has_solar in matched:
        if resolve_one(entry, code, has_solar, data_dir, log=lambda m: print(f"  {m}")):
            succeeded += 1
    print(f"\n✅ นำเข้าสำเร็จ {succeeded}/{len(matched)} รายการ")


if __name__ == "__main__":
    main()
