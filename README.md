# Project: No AMR

โมดูลสำหรับพยากรณ์โปรไฟล์การใช้ไฟฟ้า (P / OP / H) ของผู้ใช้ไฟที่ **ไม่มีข้อมูล AMR**
(Automatic Meter Reading) ของตัวเอง โดยอาศัยข้อมูล AMR ของผู้ใช้ไฟที่มีลักษณะธุรกิจ
และอัตราค่าไฟใกล้เคียงกันเป็นต้นแบบ (proxy) แล้วปรับสเกลตามขนาดสัญญา (KVA)

ที่มาของแนวคิด: เมื่อไม่ทราบข้อมูล AMR ของผู้ใช้ไฟรายหนึ่งโดยตรง ให้จำแนกผู้ใช้ไฟ
ตาม **ประเภทธุรกิจ** (เช่น โรงแรม, โรงพยาบาล, โรงงาน) และ **ประเภทอัตราค่าไฟ**
(rate code) ก่อน แล้วจึงนำโปรไฟล์การใช้ไฟฟ้าเฉลี่ยของกลุ่มธุรกิจนั้น (กำลังไฟฟ้าสูงสุด
และพลังงานไฟฟ้า แยกตามช่วง Peak / Off-Peak / Holiday) มาใช้เป็นค่าพยากรณ์

## โครงสร้างโปรเจกต์

```
data/reference/
  business_types.csv   ตารางประเภทธุรกิจ (code, ชื่อ, หมวดหมู่)
  rate_schedules.csv   ตารางประเภทอัตราค่าไฟ (code, วิธีคิดเงิน, แรงดัน)
  load_profiles.csv    โปรไฟล์ P/OP/H อ้างอิง ต่อคู่ (ประเภทธุรกิจ, อัตรา)

src/amr_mapping/
  models.py       dataclass หลัก: BusinessType, RateSchedule, LoadProfile, Customer, ForecastResult
  loader.py       โหลด/บันทึกตาราง CSV ทั้ง 3 ตารางเป็น ReferenceData
  mapping.py      ตรรกะจับคู่ (find_load_profile) และพยากรณ์ (estimate_customer_load)
  pea_ingest.py   อ่านไฟล์ export จากระบบ PEA (.xls แบบ HTML table) และคำนวณ
                  โปรไฟล์ P/OP/H รายเดือน + ค่าเฉลี่ยหลายเดือน จากข้อมูล AMR จริง

scripts/update_load_profile_from_register.py
  CLI สำหรับนำไฟล์ "ประวัติการอ่านหน่วยมิเตอร์ AMR" จริงมาคำนวณค่าเฉลี่ยแบบ
  anonymized แล้วอัปเดตแถวใน load_profiles.csv (ไม่เขียนข้อมูลระบุตัวตนลูกค้า
  ลงไฟล์ผลลัพธ์ — ดูหัวข้อ "การนำเข้าข้อมูล AMR จริง" ด้านล่าง)

web/
  app.py            เว็บแอป Flask — API ค้นหาผู้ใช้ไฟ + พยากรณ์โปรไฟล์ (ดูหัวข้อ "เว็บแอป" ด้านล่าง)
  static/           หน้าเว็บ (HTML/CSS/JS ธรรมดา ไม่มี build step)

data/reference/customers.csv   ทะเบียนผู้ใช้ไฟตัวอย่าง (สมมติ) สำหรับสาธิตเว็บแอป

examples/demo.py   ตัวอย่างการใช้งาน 4 กรณี (exact / business only / rate only / default)
tests/   unit tests (pytest) ครอบคลุมทั้ง mapping, pea_ingest และเว็บแอป
```

## หลักการจับคู่ (matching priority)

1. **EXACT** — ตรงทั้งประเภทธุรกิจและประเภทอัตรา
2. **BUSINESS_ONLY** — ตรงประเภทธุรกิจ แต่ไม่ทราบ/ไม่ตรงอัตรา
3. **RATE_ONLY** — ไม่ทราบ/ไม่ตรงประเภทธุรกิจ แต่ตรงอัตรา
4. **DEFAULT** — ไม่พบข้อมูลที่ตรงกันเลย ใช้ค่ากลาง (แถว `DEFAULT`/`DEFAULT` ใน load_profiles.csv)

ผลลัพธ์จะบอก `match_level` เสมอ เพื่อให้รู้ว่าเป็นค่าพยากรณ์ที่แม่นยำระดับใด
และถ้าไม่ใช่ exact match จะมี warning แจ้งไว้ด้วย

## การปรับสเกลตามขนาดสัญญา (KVA)

ถ้าทราบทั้ง `contract_kva` ของลูกค้า และ `contract_kva_ref` ของโปรไฟล์ที่จับคู่ได้
ผลลัพธ์ demand/energy จะถูกคูณด้วย `customer_kva / reference_kva` เพื่อสะท้อนขนาด
ธุรกิจจริง ไม่ใช่ยกค่าดิบจากโปรไฟล์อ้างอิงมาใช้ตรงๆ

## การใช้งาน

```bash
python examples/demo.py     # ดูตัวอย่างการพยากรณ์ 4 กรณี
python -m pytest tests/ -v  # รัน unit tests
```

```python
from amr_mapping import Customer, load_reference_data, estimate_customer_load

reference = load_reference_data()
customer = Customer(
    account_no="DEMO-HOTEL-001",
    name="ลูกค้าโรงแรมตัวอย่าง (สมมติ)",
    business_type_code="63201",  # โรงแรม
    rate_code="50",
    contract_kva=2000,
    has_amr=False,
)
result = estimate_customer_load(customer, reference)
print(result.match_level, result.demand_kw, result.energy_kwh)
```

## การนำเข้าข้อมูล AMR จริง (pea_ingest)

`src/amr_mapping/pea_ingest.py` อ่านไฟล์ export จากระบบ PEA 2 รูปแบบ (ไฟล์นามสกุล
`.xls` แต่เนื้อหาจริงเป็น HTML table):

- **"แบบฟอร์มการอ่านหน่วยมิเตอร์ AMR"** — ตารางประวัติค่าสะสมรายเดือน (Rate A/B/C)
  ใช้คำนวณพลังงาน (ผลต่างระหว่างเดือน) และกำลังไฟฟ้าสูงสุด (อ่านค่าตรงๆ) ต่อเดือน
  โดย RATE A = ช่วง Peak (P), RATE B = Off-Peak (OP), RATE C = Holiday (H)
  (ยืนยันจากรูปแบบข้อมูลจริง: Rate A ใช้เฉพาะวันทำการ 09:00-22:00, Rate B ใช้ช่วง
  นอกเวลานั้นในวันทำการ, Rate C ใช้ทั้งวันในวันหยุด/เสาร์-อาทิตย์)
- **"รายงานข้อมูลกิโลวัตต์ชั่วโมงแบบช่วงเวลา"** — ข้อมูลละเอียดราย 15 นาที ใช้ตรวจสอบ
  ความถูกต้องข้าม-format ได้ (ผลรวม/ค่าสูงสุดต้องตรงกับที่คำนวณจากไฟล์ประวัติรายเดือน)

ค่าที่อ่านได้จากมิเตอร์เป็น "ค่าดิบ" ต้องคูณด้วย**ตัวคูณมิเตอร์** (CT ratio × VT ratio
เช่น `50:5 A.` × `22000:110 V.` = 2000) จึงจะได้ค่ากำลังไฟฟ้า/พลังงานไฟฟ้าจริง —
`compute_meter_multiplier()` คำนวณให้อัตโนมัติจากสตริงอัตราส่วน

### วิธีอัปเดต load_profiles.csv ด้วยข้อมูลจริง

```bash
python scripts/update_load_profile_from_register.py \
    --input /path/to/ไฟล์ประวัติมิเตอร์.xls \
    --business-type 63201 \
    --rate-code 50 \
    --ct-ratio "50:5 A." \
    --vt-ratio "22000:110 V." \
    --contract-kva 2000 \
    --source-label "คำอธิบายที่มา (ห้ามมีชื่อ/เลขบัญชีลูกค้า)"
```

สคริปต์นี้คำนวณ**ค่าเฉลี่ยหลายเดือน**แล้วเขียนกลับเฉพาะตัวเลข P/OP/H ลง
`load_profiles.csv` เท่านั้น — **ไม่เขียนชื่อ/เลขบัญชี/เลขมิเตอร์ของลูกค้าลงไฟล์ผลลัพธ์**
จึง commit ไฟล์ผลลัพธ์เข้า repository (แม้เป็น public) ได้อย่างปลอดภัย ส่วนไฟล์ดิบที่มี
ข้อมูลระบุตัวตนลูกค้า **ไม่ควร commit เข้า repo นี้เด็ดขาด** ให้เก็บไว้นอก repo เท่านั้น

## เว็บแอป

หน้าเว็บสำหรับค้นหาผู้ใช้ไฟ (ตามเลขบัญชี) แล้วดูผลพยากรณ์โปรไฟล์ P/OP/H — เชื่อมกับ
`amr_mapping` โดยตรง (ไม่ใช่ mockup) รันเองในเครื่องได้ทันที ไม่ต้อง build:

```bash
pip install -r requirements.txt
python web/app.py
# เปิดเบราว์เซอร์ที่ http://localhost:5000
```

โครงสร้าง: `web/app.py` เป็น Flask backend เปิด 2 endpoint (`GET /api/customers` รายชื่อ
ทั้งหมด, `GET /api/forecast/<account_no>` ผลพยากรณ์ของรายนั้น) และเสิร์ฟหน้าเว็บ static
จาก `web/static/` (HTML/CSS/JS ธรรมดา ไม่มี framework/build step)

⚠️ **`data/reference/customers.csv` เป็นข้อมูลลูกค้า "สมมติ" สำหรับสาธิตเท่านั้น**
(ตั้งชื่อขึ้นต้นด้วย `DEMO-`) — ห้ามใส่ข้อมูลลูกค้าจริง (ชื่อ/เลขบัญชี/เลขมิเตอร์จริง)
ลงไฟล์นี้เพราะ repo เป็น public ถ้าจะต่อกับข้อมูลลูกค้าจริง ให้แก้ `web/app.py` ให้อ่าน
จากฐานข้อมูล/ไฟล์ที่เก็บแยกไว้นอก repo แทน (เช่นเดียวกับหลักการที่ใช้กับไฟล์ AMR ดิบ)

## ⚠️ ข้อควรทราบเกี่ยวกับข้อมูลอ้างอิงชุดปัจจุบัน

| business_type_code | rate_code | ที่มา |
|---|---|---|
| `63201` (โรงแรม) | `50` | **ข้อมูลจริง** — ค่าเฉลี่ยจาก AMR จริง 12 เดือน (anonymized ผ่าน `pea_ingest`) |
| `UNSPECIFIED` | `3224` | **ข้อมูลจริง** — จากใบแจ้งค่าไฟฟ้าจริง 1 รอบบิล (PEA กำแพงเพชร มิ.ย. 2569) |
| `86101`, `47190`, `MANU`, `DEFAULT` | ต่างๆ | **PLACEHOLDER** — ค่าประมาณสำหรับสาธิตเท่านั้น (ระบุไว้ในคอลัมน์ `notes`) |

แถวที่เป็น PLACEHOLDER ควรแทนที่ด้วยค่าเฉลี่ยจาก AMR จริงของผู้ใช้ไฟกลุ่มนั้นๆ ผ่าน
สคริปต์ด้านบน เมื่อมีข้อมูลพร้อม และควรตรวจสอบรหัสประเภทธุรกิจ (TSIC) ให้ตรงกับที่
การไฟฟ้าใช้จริงด้วย
