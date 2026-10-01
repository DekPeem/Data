# Project: No AMR

เครื่องมือ**ค้นหาประเภทธุรกิจ (TSIC)** ของผู้ใช้ไฟ PEA/MEA จากชื่อบริษัทหรือเลขทะเบียน
นิติบุคคล แล้วแสดง**กราฟ Boxplot การใช้ไฟจริง** (AMR — Automatic Meter Reading) ของ
ผู้ใช้ไฟรายอื่นที่อยู่ประเภทธุรกิจเดียวกัน ให้ลูกค้าที่ยังไม่มี AMR ของตัวเองดูเป็นข้อมูล
อ้างอิง — **ไม่มีการพยากรณ์ตัวเลข kWh/kW เชิงปริมาณแล้ว** (ฟีเจอร์รหัสอัตรา/KVA/Solar
และโมดูลพยากรณ์เดิม `mapping.py`/`estimate_customer_load` ถูกตัดออกจากระบบไปแล้วตามที่
ผู้ใช้ยืนยัน — ดู git history ถ้าอยากย้อนดูของเก่า) เหลือเพียง 2 อย่าง:

1. **จับคู่ TSIC** — ค้นหาประเภทธุรกิจที่ถูกต้อง
2. **ดูข้อมูล AMR จริง** — กราฟ Boxplot ของกลุ่มธุรกิจเดียวกัน (ข้อมูลวัดจริง ไม่ใช่ค่า
   ประมาณการ) บวกตัวช่วยประเมิน "รูปทรง" เส้นโค้งคร่าวๆ จากตัวเลขบนบิลสำหรับกรณีที่ยัง
   ไม่มีข้อมูลกลุ่มธุรกิจเดียวกันเลย (ดูหัวข้อ "พยากรณ์รูปทรงจากบิล" ด้านล่าง)

หน้าแรกของเว็บ (`/`) เป็นเมนูเลือกเครื่องมือ — มีลิงก์ไปเครื่องมือนี้ (`/tsic`) และไปแอป
**Solar Predict** (พยากรณ์พลังงานแสงอาทิตย์ — รันแยกเป็นแอป Streamlit อีกตัว คนละ repo/
process/port) ไว้ด้วยแล้ว เผื่อจะรวม 2 ระบบเข้าด้วยกันในอนาคต — ดู `web/static/menu.html`

## โครงสร้างโปรเจกต์

```
data/reference/
  business_types.csv          ตารางประเภทธุรกิจ (TSIC code, ชื่อ, section/division)
  tsic_code_mapping.csv       ตารางแปลงรหัส TSIC เก่าของ PEA -> รหัส TSIC 2552/DBD มาตรฐาน
  customers.csv                ทะเบียนผู้ใช้ไฟตัวอย่าง (สมมติ) สำหรับสาธิต — ห้ามใส่ข้อมูลจริง
  customers_local.csv.example  ตัวอย่างไฟล์ทะเบียนลูกค้าจริง (ดูหัวข้อ "ข้อมูลลูกค้าจริง" ด้านล่าง)

src/amr_mapping/
  models.py           dataclass หลัก: BusinessType, Customer
  loader.py            โหลด/บันทึก business_types.csv + customers.csv/customers_local.csv
  dbd_lookup.py         ค้นหา TSIC จากเลขทะเบียนนิติบุคคล/ชื่อบริษัท ผ่าน DBD DataWarehouse
  dbd_scraper/           Playwright scraper เบื้องหลัง dbd_lookup (ต้องมี Chrome จริง)
  wikipedia_lookup.py   fallback ค้นหาชื่อบริษัท/ประเภทธุรกิจผ่าน Wikipedia เมื่อ DBD ไม่เจอ
  keyword_classify.py  เดาหมวด TSIC คร่าวๆ จากคำในชื่อบริษัท (ใช้ตอนแหล่งอื่นหาไม่เจอเลย)
  tsic_normalize.py     แปลงรหัส TSIC เก่าของ PEA ให้เป็นรหัสมาตรฐานปัจจุบัน
  amr_boxplot.py        หัวใจของฝั่ง AMR จริง — parser รองรับไฟล์ AMR หลายรูปแบบจาก PEA/MEA,
                        เก็บ/สรุปข้อมูลสะสม, วาดกราฟ Boxplot (matplotlib) เป็น PNG
  amr_downloader.py    ดาวน์โหลดรายงาน AMR จากเว็บ PEA อัตโนมัติด้วย Selenium
  forecast_shape.py    สร้าง "รูปทรง" เส้นโค้งคร่าวๆ จากตัวเลขบนบิล (Peak/หน่วยไฟ) ล้วนๆ
                        ไม่ได้อิงข้อมูลจริงของบริษัทอื่น — ดูหัวข้อด้านล่าง

scripts/
  lookup_tsic.py                           ทดสอบค้นหา TSIC ผ่าน dbd_scraper แบบ standalone (debug)
  list_known_companies.py                  แสดงรายชื่อลูกค้าทั้งหมดในทะเบียนของเครื่องนี้
  check_amr_tsic_consistency.py            เช็คว่า TSIC ในทะเบียนลูกค้า vs ที่ผูกไว้ตอนอัปโหลด AMR ตรงกันไหม
  fix_amr_tsic_mismatches.py               แก้ TSIC ในทะเบียนลูกค้าให้ตรงกับที่ผูกไว้ตอนอัปโหลด AMR
  add_missing_amr_customers_to_registry.py เพิ่มลูกค้าที่มี AMR แล้วแต่ยังไม่มีในทะเบียนเข้าไปให้อัตโนมัติ

web/
  app.py    เว็บแอป Flask — ค้นหา TSIC + อัปโหลด/ดู AMR จริง + พยากรณ์รูปทรงจากบิล
  static/   หน้าเว็บ (HTML/CSS/JS ธรรมดา ไม่มี build step)
    menu.html         เมนูเลือกเครื่องมือ (TSIC / Solar Predict)
    index.html        ค้นหา TSIC + ดูกราฟ Boxplot
    admin.html        อัปโหลด/ดึง AMR จริง, ดูกราฟใหม่, แก้ไข/ลบข้อมูล, เช็คบัญชีซ้ำ
    overview.html     ภาพรวมทะเบียนลูกค้าทั้งหมด
    methodology.html  อธิบายหลักการจับคู่ TSIC แบบละเอียด
    manual.html        คู่มือการใช้งาน

tests/   unit tests (pytest) ครอบคลุม dbd_lookup, amr_boxplot, forecast_shape, web app ฯลฯ
```

## หลักการจับคู่ TSIC (matching priority)

ดูรายละเอียดเต็มในหน้า `/methodology` ของเว็บแอป สรุปสั้นๆ:

1. **EXACT** — เจอรหัส TSIC ตรงเป๊ะในระบบ (จาก DBD หรือ Wikipedia ที่ให้รหัสมาตรงๆ)
2. **DIVISION_ONLY** — ไม่ตรงเป๊ะ แต่มีธุรกิจในระบบอยู่ division (TSIC 2 หลักแรก) เดียวกัน
   — เป็นการประมาณการ (`suggested_is_approximate=True`)
3. **SECTION_ONLY** — ไม่มีธุรกิจไหนอยู่ division เดียวกันเลย ถอยไปหา section (หมวดใหญ่
   A-U) เดียวกันแทน — หยาบกว่า DIVISION_ONLY ควรให้ผู้ใช้ตรวจสอบซ้ำเสมอ
4. **NONE** — ไม่พบข้อมูลที่เกี่ยวข้องเลย ต้องเลือกประเภทธุรกิจเอง

ตอน DIVISION_ONLY/SECTION_ONLY มีตัวเลือกมากกว่า 1 ตัว ระบบจะ**เลือกตัวที่มีข้อมูล AMR
จริงอัปโหลดไว้แล้วก่อนเสมอ** (ดีกว่าได้ TSIC ที่ยังไม่มีกราฟ Boxplot ให้ดู)

## ข้อมูล AMR จริง (ฝั่ง `amr_boxplot.py`)

รองรับการอัปโหลดไฟล์รายงาน AMR หลายรูปแบบที่เจอจริงจาก PEA และ MEA (HTML-in-.xls,
.xlsx ปกติ, .xls ไบนารีเก่า BIFF/OLE2, CSV ของ MEA ทั้งแบบปกติและแบบ "สรุปแนวขวาง",
ไฟล์ log จากเครื่องวัดไฟฟ้า/power logger ฯลฯ — ดู `_is_*`/`_parse_*` function pair แต่ละ
คู่ใน `amr_boxplot.py` และเทสใน `tests/test_amr_boxplot.py`) อ่านเฉพาะตัวเลขกำลังไฟฟ้า
รายช่วง 15 นาที จัดเป็น P (วันทำการ 09:00-22:00) / OP (วันทำการนอกเวลานั้น) / H (เสาร์-
อาทิตย์) แล้วเก็บสะสมลงไฟล์ local-only (`amr_boxplot_intervals_local.csv` — อยู่ใน
`.gitignore` ไม่มีทาง commit ขึ้น repo public) แยกตาม (ประเภทธุรกิจ, เลขบัญชี)

กราฟ Boxplot ที่วาดออกมา (`render_boxplot_png`) แยก panel วันทำการ/วันหยุด พร้อมตัวเลข
สรุป Peak/เฉลี่ยของแต่ละ rate (P/OP/H) กำกับไว้ใต้หัวเรื่องกราฟด้วย

หน้า `/admin` ให้:
- อัปโหลดไฟล์ AMR เอง หรือดึงอัตโนมัติจากเว็บ PEA ผ่าน Selenium (บัญชีเดียวหรือหลายบัญชี
  พร้อมกัน — ดูข้อกำหนดเรื่อง Chrome/credential ด้านล่าง)
- ดูรายการ TSIC/บัญชีที่มีข้อมูลสะสมแล้วทั้งหมด พร้อมปุ่มดูกราฟใหม่ทันที (ไม่ต้องเลือก TSIC
  เอง), ปุ่มอัปโหลดไฟล์เพิ่มแบบเติมข้อมูลเดิมให้อัตโนมัติ, แก้ไข/ลบข้อมูลรายบัญชี
- เช็คว่าเลขบัญชีหนึ่งมีข้อมูล AMR อยู่แล้วหรือยัง (ไม่ต้องไล่หาเอง)
- อัปโหลดสำเร็จแล้ววาดกราฟ Boxplot ใหม่ให้ดูทันทีโดยอัตโนมัติ

### ข้อกำหนดก่อนใช้โหมดดึงจากเว็บ PEA อัตโนมัติ

1. **ต้องรันในเครื่องที่มี Google Chrome ติดตั้งอยู่และเข้าเว็บ `amr.pea.co.th` ได้จริง**
   (ใช้ไม่ได้ใน CI/sandbox ทั่วไป)
2. **ห้าม hardcode username/password ลงโค้ด** — กรอกในฟอร์มหน้า `/admin` โดยตรง (ไม่ถูก
   บันทึกลงดิสก์/log เลย) หรือตั้งเป็นตัวแปรสภาพแวดล้อม `PEA_AMR_USERNAME`/
   `PEA_AMR_PASSWORD` (ดู `.env.example`) เป็นค่า default ก็ได้
3. ไฟล์ดิบที่ดาวน์โหลดมาเก็บไว้ที่ `amr_downloads/` (อยู่ใน `.gitignore`) เพื่อใช้ซ้ำ กัน
   ดาวน์โหลดเดือน/บัญชีเดิมซ้ำถ้ารันงานเดิมอีกรอบ

## พยากรณ์รูปทรงจากบิล (`forecast_shape.py`)

สำหรับกรณีที่ยัง**ไม่มีข้อมูล AMR จริงของกลุ่มธุรกิจเดียวกันในระบบเลย** — อัปโหลดไฟล์ AMR
บนบิล (อ่าน Peak/หน่วยไฟของแต่ละช่วง P/OP/H อัตโนมัติ) แล้วระบบจะ**สร้างรูปทรงเส้นโค้ง
รายชั่วโมงที่ดูสมเหตุสมผล** จากรูปทรงต้นแบบคงที่ (เรียนรู้จาก AMR จริง 12 เดือนของโรงงาน
TOU รายหนึ่งไว้ตั้งแต่ต้น) สเกลให้ตรง Peak/หน่วยไฟที่อ่านได้เป๊ะ

⚠️ นี่คือ**รูปทรงสมมติที่สร้างให้ดูสมเหตุสมผลเท่านั้น ไม่ใช่การวัดจริงและไม่ได้อิงข้อมูลของ
บริษัทอื่นในระบบ** ต่างจากกราฟ Boxplot ข้างบนที่เป็นข้อมูลวัดจริงล้วนๆ — ใช้ต่อเมื่อไม่มี
ทางเลือกอื่นจริงๆ เท่านั้น

## การใช้งาน

```bash
pip install -r requirements.txt
python web/app.py
# เปิดเบราว์เซอร์ที่ http://localhost:5000
```

```bash
python -m pytest tests/ -v   # รัน unit tests
```

## ข้อมูลลูกค้าจริง (local-only)

⚠️ **`data/reference/customers.csv` เป็นข้อมูลลูกค้า "สมมติ" สำหรับสาธิตเท่านั้น**
(ตั้งชื่อขึ้นต้นด้วย `DEMO-`) — ห้ามใส่ข้อมูลลูกค้าจริงลงไฟล์นี้เพราะ repo เป็น public

ถ้าอยากเห็นชื่อลูกค้าจริงตอนรันในเครื่องตัวเอง ให้สร้างไฟล์
`data/reference/customers_local.csv` (คัดลอกจาก `customers_local.csv.example` แล้วเติม
ข้อมูลจริง) — ไฟล์นี้อยู่ใน `.gitignore` ไม่มีทาง commit/push ขึ้น GitHub ได้ เว็บแอปจะโหลด
รวมกับ `customers.csv` อัตโนมัติ (เลขบัญชีซ้ำกัน ข้อมูลจาก `customers_local.csv` ชนะ)

```bash
cp data/reference/customers_local.csv.example data/reference/customers_local.csv
# แล้วแก้ไฟล์ customers_local.csv ใส่ข้อมูลจริงของคุณ
```

ไฟล์ข้อมูล AMR จริงที่อัปโหลด/ดึงผ่านหน้า Admin (`amr_boxplot_intervals_local.csv`) และ
ไฟล์ดิบที่ดาวน์โหลดมา (`amr_downloads/`) ก็เป็น local-only เช่นกัน อยู่ใน `.gitignore` ทั้งคู่
