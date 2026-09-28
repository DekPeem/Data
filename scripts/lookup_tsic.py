#!/usr/bin/env python
"""ทดสอบค้นหา TSIC จากเลขนิติบุคคล ผ่าน dbd_scraper (Playwright) แบบ standalone — ไม่ผ่านเว็บ
No AMR Forecast เลย ใช้ตอน debug เพราะ:
  1. ค่าเริ่มต้นเป็น headed (เห็นหน้าต่างเบราว์เซอร์จริง) ต่างจากตอนเรียกผ่านเว็บที่บังคับ
     headless=True เสมอ — เห็นด้วยตาเองว่าไปติดตรงไหน (หน้าเว็บไม่ขึ้น, หา popup ปิดไม่ได้,
     หากล่องค้นหาไม่เจอ ฯลฯ)
  2. เห็น log/print ทุกบรรทัดตรงๆ ใน terminal ทันที ไม่ต้องกดขยาย "ดู log การค้นหาจริง" ในเว็บ
  3. ถ้าพัง จะมี screenshot + HTML ของหน้าที่พังไว้ให้ดูใน src/amr_mapping/dbd_scraper/debug/
     (เฉพาะบางจุดที่ error handling เรียก bu.dump_debug ไว้ — ไม่ใช่ทุกจุด)

ใช้:
    python scripts/lookup_tsic.py 0245540000631
    python scripts/lookup_tsic.py 0245540000631 --headless   (ลองแบบไม่เห็นหน้าต่าง เหมือนตอนเรียกผ่านเว็บ)
    python scripts/lookup_tsic.py 0245540000631 --no-interactive   (ปิดการถามให้คลิก reload เอง)

ถ้าเจอหน้าบล็อกของ Incapsula แล้วลองอัตโนมัติ (รอ/ขยับเมาส์/กด F5) หมดโควตาแล้วยังไม่ผ่าน — สคริปต์
จะหยุดรอให้กด Enter ใน terminal (ค่าเริ่มต้นตอนไม่ได้ใส่ --headless) ให้คลิกปุ่ม reload เองในหน้าต่าง
Chrome ที่เปิดอยู่ด้วยมือก่อน (ยืนยันแล้วว่าผ่านได้ทุกครั้ง) แล้วค่อยกด Enter เพื่อไปต่อ
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from amr_mapping.dbd_scraper import lookup_tsic_by_registration_no


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("registration_no", help="เลขทะเบียนนิติบุคคล 13 หลัก")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="รันแบบไม่เห็นหน้าต่างเบราว์เซอร์ (ค่าเริ่มต้น: เห็นหน้าต่าง — เหมือนตอนเรียกผ่านเว็บ)",
    )
    parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="ปิดการหยุดรอให้คลิก reload เอง (ค่าเริ่มต้น: เปิดไว้ตอนไม่ได้ใส่ --headless)",
    )
    args = parser.parse_args()

    interactive = (not args.headless) and (not args.no_interactive)
    print(f"ค้นหาเลขทะเบียน {args.registration_no} (headless={args.headless}, interactive={interactive}) ...\n")
    results = lookup_tsic_by_registration_no(
        args.registration_no, log=print, headless=args.headless, interactive=interactive
    )

    print(f"\n=== ผลลัพธ์: พบ {len(results)} รายการ ===")
    for r in results:
        print(f"- TSIC {r.tsic_code}: {r.tsic_name_th}")
        print(f"  ชื่อ: {r.juristic_name} ({r.juristic_type}) สถานะ: {r.status}")

    if not results:
        print("ไม่พบเลย — ดู log ด้านบนว่าไปติดตรงไหน (หรือดูไฟล์ใน src/amr_mapping/dbd_scraper/debug/ ถ้ามี)")


if __name__ == "__main__":
    main()
