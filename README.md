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
  models.py    dataclass หลัก: BusinessType, RateSchedule, LoadProfile, Customer, ForecastResult
  loader.py    โหลดตาราง CSV ทั้ง 3 ตารางเป็น ReferenceData
  mapping.py   ตรรกะจับคู่ (find_load_profile) และพยากรณ์ (estimate_customer_load)

examples/demo.py   ตัวอย่างการใช้งาน 4 กรณี (exact / business only / rate only / default)
tests/test_mapping.py   unit tests (pytest)
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
    account_no="020024424275",
    name="บจก. พิพัฒน์ ดีเวลลอปเมนท์",
    business_type_code="63201",  # โรงแรม
    rate_code="50",
    contract_kva=2000,
    has_amr=False,
)
result = estimate_customer_load(customer, reference)
print(result.match_level, result.demand_kw, result.energy_kwh)
```

## ⚠️ ข้อควรทราบเกี่ยวกับข้อมูลอ้างอิงชุดปัจจุบัน

ข้อมูลใน `data/reference/load_profiles.csv` ส่วนใหญ่เป็น **ค่าประมาณ (PLACEHOLDER)**
สำหรับสาธิตการทำงานของโค้ดเท่านั้น (ระบุไว้ในคอลัมน์ `notes` ของแต่ละแถว) ยกเว้นแถว
`UNSPECIFIED,3224` ที่นำมาจากใบแจ้งค่าไฟฟ้าจริง (PEA กำแพงเพชร รอบบิล 06/2569)

ก่อนใช้งานจริง ควรแทนที่ค่า demand/energy ด้วยค่าเฉลี่ยที่คำนวณจากข้อมูล AMR จริงของ
ผู้ใช้ไฟแต่ละกลุ่มธุรกิจ (เช่น ค่าเฉลี่ยจากผู้ใช้ไฟหลายรายในกลุ่มเดียวกัน) และตรวจสอบ
รหัสประเภทธุรกิจ (TSIC) ให้ตรงกับที่การไฟฟ้าใช้จริง
