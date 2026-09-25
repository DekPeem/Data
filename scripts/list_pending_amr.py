"""แสดงรายการทั้งหมดที่ค้างอยู่ในคิว "รอทราบอัตรา" (pending_amr_local.csv) เป็น text ในเทอร์มินัล
โดยตรง — เหมือนหน้า /pending-amr แต่ดูได้เร็วโดยไม่ต้องเปิดเว็บ

ใช้:
    python scripts/list_pending_amr.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amr_mapping.loader import DEFAULT_DATA_DIR, load_pending_amr_local


def main() -> None:
    entries = load_pending_amr_local(DEFAULT_DATA_DIR / "pending_amr_local.csv")

    if not entries:
        print('คิว "รอทราบอัตรา" ว่างเปล่าครับ')
        return

    print(f'รวม {len(entries)} รายการในคิว "รอทราบอัตรา":\n')
    for e in entries:
        name = e.get("company_name") or "(ไม่ทราบชื่อ)"
        account_no = e.get("account_no") or "-"
        file_count = len([p for p in (e.get("file_paths") or "").split("|") if p])
        created_at = e.get("created_at") or "-"
        print(f"  {name} — บัญชี {account_no} — {file_count} ไฟล์ — บันทึกเมื่อ {created_at} — pending_id={e.get('pending_id')}")


if __name__ == "__main__":
    main()
