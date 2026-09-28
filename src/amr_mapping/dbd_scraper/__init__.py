"""Playwright-based scraper for DBD DataWarehouse (datawarehouse.dbd.go.th).

ต่างจาก amr_mapping.dbd_lookup (Selenium, ค้นด้วย "ชื่อบริษัท" ผ่านช่องค้นหาแบบ keyword search
ตรงๆ) — แพ็กเกจนี้ขับเบราว์เซอร์เหมือนผู้ใช้งานจริงกว่า (เปิดหน้าแรก พิมพ์ในกล่องค้นหา เลือกจาก
autocomplete) ซึ่งจำเป็นสำหรับการค้นหาด้วย "เลขทะเบียนนิติบุคคล" เพราะยืนยันจากการทดสอบจริงว่า
วิธีเดาที่มาก่อนหน้านี้ (เดา URL หน้าโปรไฟล์ตรงๆ, ค้นด้วยเลขทะเบียนผ่าน endpoint keyword search
ของ dbd_lookup) ไม่น่าเชื่อถือ/โดนบล็อกบ่อย

lookup_tsic_by_registration_no (ใน tsic_lookup.py) คือ entry point ที่ web/app.py เรียกใช้
"""

from .tsic_lookup import lookup_tsic_by_registration_no  # noqa: F401
