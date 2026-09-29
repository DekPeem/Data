import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))

import app as app_module  # noqa: E402
from app import app as flask_app  # noqa: E402


@pytest.fixture()
def client():
    flask_app.config.update(TESTING=True)
    with flask_app.test_client() as client:
        yield client


def test_index_serves_html(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"<html" in res.data


def test_methodology_page_serves_html(client):
    res = client.get("/methodology")
    assert res.status_code == 200
    assert b"<html" in res.data


def test_list_customers(client):
    res = client.get("/api/customers")
    assert res.status_code == 200
    data = res.get_json()
    assert isinstance(data, list)
    assert any(c["account_no"] == "DEMO-HOTEL-001" for c in data)


def test_admin_page_serves_html(client):
    res = client.get("/admin")
    assert res.status_code == 200
    assert b"<html" in res.data


def test_list_business_types(client):
    res = client.get("/api/business-types")
    assert res.status_code == 200
    data = res.get_json()
    assert any(bt["code"] == "55101" for bt in data)


def test_admin_backup_returns_404_when_no_local_files_exist(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "DEFAULT_DATA_DIR", tmp_path)
    res = client.get("/api/admin/backup")
    assert res.status_code == 404
    assert res.get_json()["error"] == "no_data"


def test_admin_backup_zips_only_existing_local_files(client, monkeypatch, tmp_path):
    import io
    import zipfile

    monkeypatch.setattr(app_module, "DEFAULT_DATA_DIR", tmp_path)
    (tmp_path / "customers_local.csv").write_text("account_no,name\n019900000001,บริษัท เอ จำกัด\n", encoding="utf-8")
    # ไฟล์แคชที่ดึงใหม่ได้เสมอ ไม่ใช่ข้อมูลต้นทาง — ต้องไม่ถูกรวมในไฟล์สำรอง
    (tmp_path / "dbd_juristic_local.db").write_bytes(b"fake sqlite bytes")

    res = client.get("/api/admin/backup")
    assert res.status_code == 200
    assert res.mimetype == "application/zip"
    assert "attachment" in res.headers.get("Content-Disposition", "")

    with zipfile.ZipFile(io.BytesIO(res.data)) as zf:
        names = set(zf.namelist())
        assert names == {"customers_local.csv"}
        assert b"019900000001" in zf.read("customers_local.csv")


def test_business_type_hierarchy_update_success(client, monkeypatch, tmp_path):
    import shutil

    from amr_mapping.loader import DEFAULT_DATA_DIR as REAL_DATA_DIR, _load_business_types

    # คัดลอกไฟล์จริงไปไว้ที่ tmp ก่อน กัน test เขียนทับ business_types.csv จริงในการทดสอบนี้
    tmp_data_dir = tmp_path / "reference"
    tmp_data_dir.mkdir()
    shutil.copy(REAL_DATA_DIR / "business_types.csv", tmp_data_dir / "business_types.csv")
    monkeypatch.setattr(app_module, "DEFAULT_DATA_DIR", tmp_data_dir)

    res = client.post(
        "/api/business-types/68100/hierarchy",
        json={
            "section_code": "L",
            "section_name_th": "กิจกรรมด้านอสังหาริมทรัพย์",
            "division_code": "68",
            "division_name_th": "กิจกรรมด้านอสังหาริมทรัพย์",
        },
    )
    assert res.status_code == 200
    assert res.get_json()["division_code"] == "68"

    updated_bts = _load_business_types(tmp_data_dir / "business_types.csv")
    assert updated_bts["68100"].division_code == "68"
    assert updated_bts["68100"].section_name_th == "กิจกรรมด้านอสังหาริมทรัพย์"
    # ต้องไม่กระทบประเภทธุรกิจอื่นที่มีอยู่แล้ว (34111 ต้องยัง verified เหมือนเดิม)
    assert updated_bts["34111"].division_code == "17"


def test_business_type_hierarchy_update_unknown_code_404(client, monkeypatch, tmp_path):
    import shutil

    from amr_mapping.loader import DEFAULT_DATA_DIR as REAL_DATA_DIR

    tmp_data_dir = tmp_path / "reference"
    tmp_data_dir.mkdir()
    shutil.copy(REAL_DATA_DIR / "business_types.csv", tmp_data_dir / "business_types.csv")
    monkeypatch.setattr(app_module, "DEFAULT_DATA_DIR", tmp_data_dir)

    res = client.post("/api/business-types/NOPE/hierarchy", json={"division_code": "99"})
    assert res.status_code == 404


def test_create_business_type_success(client, monkeypatch, tmp_path):
    import shutil

    from amr_mapping.loader import DEFAULT_DATA_DIR as REAL_DATA_DIR, _load_business_types

    tmp_data_dir = tmp_path / "reference"
    tmp_data_dir.mkdir()
    shutil.copy(REAL_DATA_DIR / "business_types.csv", tmp_data_dir / "business_types.csv")
    monkeypatch.setattr(app_module, "DEFAULT_DATA_DIR", tmp_data_dir)

    res = client.post(
        "/api/business-types",
        json={
            "code": "99999",
            "name_th": "ธุรกิจทดสอบ",
            "section_code": "C",
            "section_name_th": "การผลิต",
            "division_code": "10",
            "division_name_th": "การผลิตอาหาร",
            "notes": "เพิ่มระหว่างทดสอบ",
        },
    )
    assert res.status_code == 201
    assert res.get_json() == {"code": "99999", "name_th": "ธุรกิจทดสอบ"}

    updated_bts = _load_business_types(tmp_data_dir / "business_types.csv")
    assert updated_bts["99999"].name_th == "ธุรกิจทดสอบ"
    assert updated_bts["99999"].section_code == "C"
    assert updated_bts["99999"].division_code == "10"
    # ต้องไม่กระทบประเภทธุรกิจอื่นที่มีอยู่แล้ว
    assert "34111" in updated_bts


def test_create_business_type_missing_fields_returns_400(client, monkeypatch, tmp_path):
    import shutil

    from amr_mapping.loader import DEFAULT_DATA_DIR as REAL_DATA_DIR

    tmp_data_dir = tmp_path / "reference"
    tmp_data_dir.mkdir()
    shutil.copy(REAL_DATA_DIR / "business_types.csv", tmp_data_dir / "business_types.csv")
    monkeypatch.setattr(app_module, "DEFAULT_DATA_DIR", tmp_data_dir)

    res = client.post("/api/business-types", json={"code": "99999"})
    assert res.status_code == 400

    res2 = client.post("/api/business-types", json={"name_th": "ไม่มีรหัส"})
    assert res2.status_code == 400


def test_create_business_type_duplicate_code_returns_409(client, monkeypatch, tmp_path):
    import shutil

    from amr_mapping.loader import DEFAULT_DATA_DIR as REAL_DATA_DIR

    tmp_data_dir = tmp_path / "reference"
    tmp_data_dir.mkdir()
    shutil.copy(REAL_DATA_DIR / "business_types.csv", tmp_data_dir / "business_types.csv")
    monkeypatch.setattr(app_module, "DEFAULT_DATA_DIR", tmp_data_dir)

    res = client.post("/api/business-types", json={"code": "34111", "name_th": "ชื่อใหม่"})
    assert res.status_code == 409


def test_business_type_lookup_missing_company_name(client):
    res = client.post("/api/business-type-lookup", json={})
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_request"


def test_business_type_lookup_success_suggests_matching_business_type(client, monkeypatch):
    """DBD คืนรหัส TSIC "17099" (division "17" เหมือน 34111 ในระบบเรา ที่ยืนยัน division ไว้
    แล้ว) — ต้องแนะนำ suggested_business_type_code เป็น "34111" ให้"""

    from amr_mapping.dbd_lookup import CompanyBusinessInfo

    def fake_lookup(company_name, log=lambda m: None, headless=True):
        log(f"ค้นหา {company_name}")
        return [
            CompanyBusinessInfo(
                registration_no="0105544000157",
                juristic_name="บริษัท ทดสอบกระดาษ จำกัด",
                juristic_type="บริษัทจำกัด",
                status="ยังดำเนินกิจการอยู่",
                tsic_code="17099",
                tsic_name_th="การผลิตผลิตภัณฑ์กระดาษอื่นๆ",
            )
        ]

    monkeypatch.setattr(app_module, "lookup_business_type_for_company", fake_lookup)

    res = client.post("/api/business-type-lookup", json={"company_name": "บริษัท ทดสอบกระดาษ จำกัด"})
    assert res.status_code == 200
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status = client.get(f"/api/business-type-lookup/{job_id}").get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "success"
    candidates = status["result"]["candidates"]
    assert len(candidates) == 1
    assert candidates[0]["tsic_code"] == "17099"
    assert candidates[0]["tsic_division_code"] == "17"
    assert candidates[0]["suggested_business_type_code"] == "34111"
    # ชื่อที่ค้นหาตรงเป๊ะกับผลลัพธ์เดียวที่เจอ -> ต้องรายงาน exact_match_index
    assert status["result"]["exact_match_index"] == 0


def test_business_type_lookup_uses_registration_no_profile_fetch_when_provided(client, monkeypatch):
    """ถ้าส่ง registration_no มาด้วย ต้องเรียก lookup_tsic_by_registration_no (dbd_scraper,
    Playwright — ขับกล่องค้นหาบนหน้าเว็บจริง) แทน lookup_business_type_for_company (dbd_lookup,
    Selenium — ค้นหาผ่านช่องค้นหาด้วยชื่อ) ไปเลย และ exact_match_index ต้องคำนวณจากเลขทะเบียนตรงกัน
    ไม่ใช่ชื่อ — แม้ชื่อที่พิมพ์มา (company_name) จะสะกดคลาดเคลื่อนจากชื่อที่ DBD บันทึกไว้จริงก็ตาม"""

    from amr_mapping.dbd_lookup import CompanyBusinessInfo

    received_registration_nos = []
    name_search_called = []

    def fake_profile_fetch(registration_no, log=lambda m: None, headless=True, on_blocked=None):
        received_registration_nos.append(registration_no)
        return [
            CompanyBusinessInfo(
                registration_no="0105544000157",
                juristic_name="บริษัท ทดสอบกระดาษ (สะกดต่างจากที่พิมพ์) จำกัด",
                juristic_type="บริษัทจำกัด",
                status="ยังดำเนินกิจการอยู่",
                tsic_code="17099",
                tsic_name_th="การผลิตผลิตภัณฑ์กระดาษอื่นๆ",
            )
        ]

    def fake_name_search(company_name, log=lambda m: None, headless=True):
        name_search_called.append(company_name)
        return []

    # lookup_tsic_by_registration_no ถูก import แบบ lazy (ไม่ใช่ top-level ของ web/app.py — กัน
    # boot ไม่ขึ้นถ้าเครื่องไม่มี playwright ติดตั้ง) จึงต้อง patch ที่ต้นทาง (amr_mapping.dbd_scraper)
    # แทน app_module โดยตรง — `from X import Y` ที่เรียกตอนรัน job จะเห็นค่าที่ patch ไว้เสมอ
    import amr_mapping.dbd_scraper as dbd_scraper_module

    monkeypatch.setattr(dbd_scraper_module, "lookup_tsic_by_registration_no", fake_profile_fetch)
    monkeypatch.setattr(app_module, "lookup_business_type_for_company", fake_name_search)

    res = client.post(
        "/api/business-type-lookup",
        json={"company_name": "บริษัท ทดสอบกระดาดถ จก", "registration_no": "0105544000157"},
    )
    assert res.status_code == 200
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status = client.get(f"/api/business-type-lookup/{job_id}").get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "success"
    assert received_registration_nos == ["0105544000157"]
    assert name_search_called == []  # ไม่ใช้ช่องค้นหาด้วยชื่อเลยตอนมีเลขทะเบียนมาให้
    assert status["result"]["exact_match_index"] == 0  # ตรงกันด้วยเลขทะเบียน แม้ชื่อสะกดต่างกัน


def test_business_type_lookup_prefers_latest_financial_statement_tsic_as_primary(client, monkeypatch):
    """DBD คืน TSIC 2 ค่าต่อบริษัทเดียวได้ ("ตอนจดทะเบียน" vs "ตามงบการเงินปีล่าสุด") เป็น 2
    candidates ที่ใช้เลขทะเบียนเดียวกัน — ต้องเลือก "ปีล่าสุด" เป็นตัวหลัก (primary_index) เสมอ
    ไม่ว่า dbd_scraper จะคืนมาเรียงลำดับไหนก็ตาม (จำลองกรณีคืนมาผิดลำดับ — ตอนจดทะเบียนมาก่อน —
    เพื่อยืนยันว่า web/app.py เช็คซ้ำเองอีกชั้น ไม่ได้พึ่งพา sort ของ scraper อย่างเดียว)"""

    from amr_mapping.dbd_lookup import CompanyBusinessInfo

    def fake_profile_fetch(registration_no, log=lambda m: None, headless=True, on_blocked=None):
        return [
            CompanyBusinessInfo(
                registration_no="0105544000999",
                juristic_name="บริษัท ทดสอบยาง จำกัด",
                juristic_type="บริษัทจำกัด",
                status="ยังดำเนินกิจการอยู่",
                tsic_code="22199",
                tsic_name_th="(ตอนจดทะเบียน) การผลิตผลิตภัณฑ์ยางอื่นๆ ซึ่งมิได้จัดประเภทไว้ในที่อื่น",
            ),
            CompanyBusinessInfo(
                registration_no="0105544000999",
                juristic_name="บริษัท ทดสอบยาง จำกัด",
                juristic_type="บริษัทจำกัด",
                status="ยังดำเนินกิจการอยู่",
                tsic_code="32909",
                tsic_name_th="(ตามงบการเงินปีล่าสุด) การผลิตผลิตภัณฑ์อื่นๆ ซึ่งมิได้จัดประเภทไว้ในที่อื่น",
            ),
        ]

    import amr_mapping.dbd_scraper as dbd_scraper_module

    monkeypatch.setattr(dbd_scraper_module, "lookup_tsic_by_registration_no", fake_profile_fetch)

    res = client.post(
        "/api/business-type-lookup",
        json={"company_name": "บริษัท ทดสอบยาง จำกัด", "registration_no": "0105544000999"},
    )
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status = client.get(f"/api/business-type-lookup/{job_id}").get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "success"
    result = status["result"]
    assert result["primary_index"] == 1  # index 1 คือตัว "ปีล่าสุด" แม้จะมาทีหลังในลิสต์
    assert result["candidates"][result["primary_index"]]["tsic_code"] == "32909"


def test_business_type_lookup_suggests_approximate_match_when_no_exact_division(client, monkeypatch):
    """DBD คืนรหัส TSIC 5 หลักที่ไม่มีธุรกิจไหนในระบบเราตรงเป๊ะ แต่ TSIC division เดียวกัน (46 —
    การขายส่งสินค้า) มีธุรกิจอื่นอยู่ในข้อมูลอ้างอิงจริง — ต้อง fallback ไปแนะนำธุรกิจที่อยู่ division
    เดียวกันแทนที่จะปล่อยว่างเฉยๆ และต้องรายงานว่าเป็นการประมาณการ (suggested_is_approximate=True)
    พร้อมคำอธิบาย"""

    from amr_mapping.dbd_lookup import CompanyBusinessInfo

    def fake_lookup(company_name, log=lambda m: None, headless=True):
        return [
            CompanyBusinessInfo(
                registration_no="0105544000999",
                juristic_name="บริษัท ทดสอบค้าส่ง จำกัด",
                juristic_type="บริษัทจำกัด",
                status="ยังดำเนินกิจการอยู่",
                tsic_code="46999",
                tsic_name_th="การขายส่งสินค้าอื่นๆ ซึ่งมิได้จัดประเภทไว้ในที่อื่น",
            )
        ]

    monkeypatch.setattr(app_module, "lookup_business_type_for_company", fake_lookup)

    res = client.post("/api/business-type-lookup", json={"company_name": "บริษัท ทดสอบค้าส่ง จำกัด"})
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status = client.get(f"/api/business-type-lookup/{job_id}").get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "success"
    candidate = status["result"]["candidates"][0]
    assert candidate["tsic_division_code"] == "46"
    assert candidate["suggested_business_type_code"], "ต้องแนะนำธุรกิจที่ใกล้เคียงที่สุดแทนที่จะปล่อยว่าง"
    assert candidate["suggested_is_approximate"] is True
    assert candidate["suggested_explanation"]


def test_business_type_lookup_handles_selenium_error_gracefully(client, monkeypatch):
    def fake_lookup(company_name, log=lambda m: None, headless=True):
        raise RuntimeError("เปิด Chrome ไม่สำเร็จ (จำลอง error)")

    monkeypatch.setattr(app_module, "lookup_business_type_for_company", fake_lookup)

    res = client.post("/api/business-type-lookup", json={"company_name": "บริษัท ทดสอบ จำกัด"})
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status = client.get(f"/api/business-type-lookup/{job_id}").get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "error"
    assert "เปิด Chrome ไม่สำเร็จ" in status["error"]


def test_business_type_lookup_includes_wikipedia_result_when_found(client, monkeypatch):
    """เสริมช่องทางฟรี Wikipedia (ดู wikipedia_lookup.py) — ตอน DBD บล็อก ต้องลองค้น Wikipedia
    ด้วย แล้วใส่ผลลัพธ์ (แค่ข้อความอิสระประกอบการตัดสินใจ ไม่ใช่รหัส TSIC) กลับไปในผล job"""

    from amr_mapping.dbd_lookup import BlockedByAntiBot
    from amr_mapping.wikipedia_lookup import WikipediaCompanyInfo

    def fake_lookup(company_name, log=lambda m: None, headless=True):
        raise BlockedByAntiBot("Incapsula incident ID: 111")

    monkeypatch.setattr(app_module, "lookup_business_type_for_company", fake_lookup)
    monkeypatch.setattr(
        app_module,
        "search_wikipedia_company",
        lambda company_name, log=lambda m: None: WikipediaCompanyInfo(
            title="ซีพี ออลล์", summary="ซีพี ออลล์ เป็นบริษัทค้าส่งสินค้าอุปโภคบริโภครายใหญ่...", url="https://th.wikipedia.org/wiki/ซีพี_ออลล์"
        ),
    )

    res = client.post("/api/business-type-lookup", json={"company_name": "ซีพี ออลล์"})
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status = client.get(f"/api/business-type-lookup/{job_id}").get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "success"
    result = status["result"]
    assert result["wikipedia_result"]["title"] == "ซีพี ออลล์"
    assert result["wikipedia_result"]["summary"] == "ซีพี ออลล์ เป็นบริษัทค้าส่งสินค้าอุปโภคบริโภครายใหญ่..."
    # "ค้าส่ง" เจอ แต่ไม่มีธุรกิจ TSIC 5 หลักไหนตรงเป๊ะในระบบทดสอบ (มีแค่ธุรกิจอื่นใน division
    # เดียวกัน) -> เป็นแค่การประมาณการ (is_approximate) จึงต้อง "ไม่" auto-apply แบบเงียบๆ
    # (suggested_business_type_code เป็น None) และต้องมีรายการอันดับให้เลือกเองแทน
    assert result["wikipedia_result"]["guessed_keyword"] == "ค้าส่ง"
    assert result["wikipedia_result"]["suggested_is_approximate"] is True
    assert result["wikipedia_result"]["suggested_business_type_code"] is None
    assert len(result["wikipedia_result"]["ranked_candidates"]) >= 1
    assert result["wikipedia_result"]["ranked_candidates"][0]["business_type_code"]


def test_business_type_lookup_guesses_business_type_from_wikipedia_keyword(client, monkeypatch):
    """ถ้าข้อความสรุปจาก Wikipedia มีคำสำคัญที่รู้จัก (ดู keyword_classify.py) เช่น "โรงแรม" ต้อง
    เดาประเภทธุรกิจให้ (พร้อมบอกคำที่ใช้เดาชัดเจน) — แต่การเดาจากคำสำคัญไม่มีทางได้รหัส TSIC 5 หลัก
    จริงติดมาด้วยเลย (มีแค่ TSIC division คร่าวๆ) จึงต้องถือเป็นการประมาณการเสมอ
    (suggested_is_approximate=True, suggested_business_type_code=None) พร้อมรายการอันดับให้เลือกเอง
    ไม่ auto-apply แบบเงียบๆ แม้ division นั้นจะมีธุรกิจในระบบแค่ตัวเดียวก็ตาม"""

    from amr_mapping.dbd_lookup import BlockedByAntiBot
    from amr_mapping.wikipedia_lookup import WikipediaCompanyInfo

    def fake_lookup(company_name, log=lambda m: None, headless=True):
        raise BlockedByAntiBot("Incapsula incident ID: 222")

    monkeypatch.setattr(app_module, "lookup_business_type_for_company", fake_lookup)
    monkeypatch.setattr(
        app_module,
        "search_wikipedia_company",
        lambda company_name, log=lambda m: None: WikipediaCompanyInfo(
            title="บริษัท ทดสอบ จำกัด",
            summary="บริษัท ทดสอบ จำกัด เป็นเจ้าของโรงแรมหลายแห่งในประเทศไทย",
            url="https://th.wikipedia.org/wiki/ทดสอบ",
        ),
    )

    res = client.post("/api/business-type-lookup", json={"company_name": "บริษัท ทดสอบ จำกัด"})
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status = client.get(f"/api/business-type-lookup/{job_id}").get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "success"
    wp_result = status["result"]["wikipedia_result"]
    assert wp_result["guessed_keyword"] == "โรงแรม"
    assert wp_result["suggested_is_approximate"] is True
    assert wp_result["suggested_business_type_code"] is None
    assert len(wp_result["ranked_candidates"]) == 1
    assert wp_result["ranked_candidates"][0]["business_type_code"] == "55101"


def test_overview_entry_normalizes_legacy_tsic_code_from_user_input(client, monkeypatch, tmp_path):
    """ผู้ใช้กรอก/เลือกรหัส TSIC เก่าเองในหน้า /overview (User Input) — ต้องถูกแปลงเป็นรหัส
    มาตรฐานใหม่ทันทีก่อนบันทึกลง customers_local.csv (Requirement 1) โดยรหัสดิบที่กรอกมาต้องถูก
    เก็บไว้ที่ business_type_code_raw เป็น audit trail (Requirement 2)"""

    tmp_data_dir = tmp_path / "reference"
    tmp_data_dir.mkdir()
    (tmp_data_dir / "tsic_code_mapping.csv").write_text(
        "old_code,new_code,notes\n93311,86101,โรงพยาบาลทั่วไป\n", encoding="utf-8"
    )
    monkeypatch.setattr(app_module, "DEFAULT_DATA_DIR", tmp_data_dir)

    res = client.patch(
        "/api/admin/overview-entry",
        json={
            "account_no": "TEST-TSIC-NORMALIZE-001",
            "name": "ลูกค้าทดสอบ normalize",
            "business_type_code": "93311",
        },
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["business_type_code"] == "86101"
    assert data["business_type_code_raw"] == "93311"

    from amr_mapping.loader import load_customers_local

    saved = load_customers_local(tmp_data_dir / "customers_local.csv")
    assert len(saved) == 1
    assert saved[0].business_type_code == "86101"
    assert saved[0].business_type_code_raw == "93311"


def test_overview_entry_saves_and_returns_registration_no(client, monkeypatch, tmp_path):
    """แก้ไขเลขนิติบุคคล (registration_no) ผ่านหน้า /overview ได้ — ต้องบันทึกลง
    customers_local.csv และคืนกลับมาใน response ทันที"""

    tmp_data_dir = tmp_path / "reference"
    tmp_data_dir.mkdir()
    monkeypatch.setattr(app_module, "DEFAULT_DATA_DIR", tmp_data_dir)

    res = client.patch(
        "/api/admin/overview-entry",
        json={
            "account_no": "TEST-REGNO-001",
            "name": "ลูกค้าทดสอบเลขนิติบุคคล",
            "registration_no": "0105544000157",
        },
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["registration_no"] == "0105544000157"

    from amr_mapping.loader import load_customers_local

    saved = load_customers_local(tmp_data_dir / "customers_local.csv")
    assert len(saved) == 1
    assert saved[0].registration_no == "0105544000157"


def test_overview_entry_editing_unrelated_field_keeps_existing_registration_no(client, monkeypatch, tmp_path):
    """แก้ไขฟิลด์อื่น (ไม่ใช่ registration_no) ต้องไม่ล้างเลขนิติบุคคลที่เคยบันทึกไว้ทิ้ง —
    ใช้ monkeypatch ที่ get_reference() ตรงๆ เหมือน
    test_overview_entry_editing_unrelated_field_does_not_clobber_existing_raw_audit เพราะ
    get_reference() โหลดจาก loader.DEFAULT_DATA_DIR เสมอ ไม่ใช่ app_module.DEFAULT_DATA_DIR"""

    from amr_mapping.models import Customer

    tmp_data_dir = tmp_path / "reference"
    tmp_data_dir.mkdir()
    monkeypatch.setattr(app_module, "DEFAULT_DATA_DIR", tmp_data_dir)

    existing_customer = Customer(
        account_no="TEST-REGNO-002", name="ลูกค้า", registration_no="0105544000157",
    )
    patched = replace(app_module.get_reference(), customers=[existing_customer])
    monkeypatch.setattr(app_module, "get_reference", lambda: patched)

    res = client.patch(
        "/api/admin/overview-entry",
        json={"account_no": "TEST-REGNO-002", "name": "ลูกค้า (แก้ชื่อ)"},
    )
    assert res.status_code == 200
    assert res.get_json()["registration_no"] == "0105544000157"


def test_overview_entry_fallback_keeps_unknown_code_unchanged(client, monkeypatch, tmp_path):
    """ไม่มีไฟล์ tsic_code_mapping.csv เลย (หรือรหัสไม่อยู่ใน mapping) — ต้องบันทึกรหัสเดิมได้ตาม
    ปกติ ไม่ error (Requirement 3: Fallback Logic)"""

    tmp_data_dir = tmp_path / "reference"
    tmp_data_dir.mkdir()
    monkeypatch.setattr(app_module, "DEFAULT_DATA_DIR", tmp_data_dir)

    res = client.patch(
        "/api/admin/overview-entry",
        json={
            "account_no": "TEST-TSIC-NORMALIZE-002",
            "name": "ลูกค้าทดสอบ fallback",
            "business_type_code": "63201",
        },
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["business_type_code"] == "63201"
    assert data["business_type_code_raw"] == "63201"


def test_overview_entry_editing_unrelated_field_does_not_clobber_existing_raw_audit(client, monkeypatch, tmp_path):
    """แก้ไขแค่ registration_no (ไม่แตะ business_type_code เลย) ต้องไม่เขียนทับ
    business_type_code_raw เดิมทิ้งด้วยค่าที่แปลงแล้ว (ดูคอมเมนต์ใน api_update_overview_entry —
    บั๊กที่ตั้งใจป้องกัน)

    ใช้ monkeypatch ที่ get_reference() ตรงๆ (แทนการพึ่งพา customers_local.csv ที่เขียนไปจริง)
    เพราะ get_reference() ในแอปจริงโหลดจาก loader.DEFAULT_DATA_DIR เสมอ (ไม่ใช่ app_module.
    DEFAULT_DATA_DIR ที่ mock ในเทสต์นี้ — เทสต์อื่นในไฟล์นี้ก็ใช้วิธีเดียวกันเวลาต้องการ current
    customer ที่กำหนดเอง)"""

    from amr_mapping.models import Customer

    tmp_data_dir = tmp_path / "reference"
    tmp_data_dir.mkdir()
    monkeypatch.setattr(app_module, "DEFAULT_DATA_DIR", tmp_data_dir)

    existing_customer = Customer(
        account_no="TEST-TSIC-NORMALIZE-003",
        name="ลูกค้าทดสอบ preserve raw",
        business_type_code="86101",
        business_type_code_raw="93311",
    )
    patched = replace(app_module.get_reference(), customers=[existing_customer])
    monkeypatch.setattr(app_module, "get_reference", lambda: patched)

    res = client.patch(
        "/api/admin/overview-entry",
        json={"account_no": "TEST-TSIC-NORMALIZE-003", "registration_no": "0105544000157"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["business_type_code"] == "86101"
    assert data["business_type_code_raw"] == "93311"
    assert data["registration_no"] == "0105544000157"


def test_forecast_shape_missing_params_returns_400(client):
    res = client.get("/api/forecast-shape")
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_request"


def test_forecast_shape_rejects_non_numeric_peak(client):
    res = client.get("/api/forecast-shape?peak_p=ไม่ใช่ตัวเลข")
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_request"


def test_forecast_shape_returns_png_on_success(client):
    res = client.get(
        "/api/forecast-shape",
        query_string={
            "peak_p": "650", "energy_p": "69500",
            "peak_op": "420", "energy_op": "45000",
            "peak_h": "300", "energy_h": "24000", "days_h": "8",
        },
    )
    assert res.status_code == 200
    assert res.headers["Content-Type"] == "image/png"
    assert res.data[:8] == b"\x89PNG\r\n\x1a\n"


def test_forecast_shape_works_with_only_one_segment(client):
    """ไม่ต้องกรอกครบทั้ง 3 ช่วง (P/OP/H) — แค่ P อย่างเดียวก็พยากรณ์ได้"""

    res = client.get("/api/forecast-shape", query_string={"peak_p": "500", "energy_p": "50000"})
    assert res.status_code == 200
    assert res.data[:8] == b"\x89PNG\r\n\x1a\n"


def _make_amr_report_html(n_days: int = 3) -> str:
    """สร้างไฟล์รายงาน AMR จำลอง (รูปแบบเดียวกับ tests/test_amr_boxplot.py) — ใช้ทดสอบ endpoint
    อัปโหลดโดยไม่ต้องมีไฟล์ AMR จริง"""

    import datetime as dt

    rows = []
    d = dt.datetime(2026, 1, 1)  # วันพฤหัส (วันทำการ) เป็นวันแรก
    for _ in range(n_days):
        for interval_i in range(96):
            minutes = interval_i * 15
            t = d + dt.timedelta(minutes=minutes) + dt.timedelta(minutes=15)
            hour = (minutes // 60) % 24
            if d.weekday() >= 5:
                col, kw = "c1", 100.0
            elif 9 <= hour < 22:
                col, kw = "a1", 400.0
            else:
                col, kw = "b1", 150.0
            row = {"ts": t.strftime("%d/%m/%Y %H.%M"), "a1": "", "a2": "", "b1": "", "b2": "", "c1": "", "c2": ""}
            row[col] = f"{kw:.2f}"
            rows.append(row)
        d += dt.timedelta(days=1)

    header = "<table><tr><td>Header info</td></tr></table>"
    data_rows = "".join(
        "<tr>" + "".join(f"<td>{r[c]}</td>" for c in ["ts", "a1", "a2", "b1", "b2", "c1", "c2"]) + "</tr>"
        for r in rows
    )
    data_table = (
        "<table><tr><td>ts</td><td>a1</td><td>a2</td><td>b1</td><td>b2</td><td>c1</td><td>c2</td></tr>"
        + data_rows
        + "</table>"
    )
    footer = "<table><tr><td>Footer info</td></tr></table>"
    return header + data_table + footer


def test_amr_boxplot_upload_missing_business_type_returns_400(client, monkeypatch, tmp_path):
    import io

    monkeypatch.setattr(app_module, "DEFAULT_DATA_DIR", tmp_path)
    res = client.post(
        "/api/admin/amr-boxplot/upload",
        data={"files": (io.BytesIO(_make_amr_report_html().encode("utf-8")), "report.xls")},
        content_type="multipart/form-data",
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_request"


def test_amr_boxplot_upload_missing_files_returns_400(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "DEFAULT_DATA_DIR", tmp_path)
    res = client.post(
        "/api/admin/amr-boxplot/upload",
        data={"business_type_code": "55101"},
        content_type="multipart/form-data",
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == "invalid_request"


def test_amr_boxplot_upload_success_then_status_and_boxplot(client, monkeypatch, tmp_path):
    import io

    monkeypatch.setattr(app_module, "DEFAULT_DATA_DIR", tmp_path)

    res = client.post(
        "/api/admin/amr-boxplot/upload",
        data={
            "business_type_code": "55101",
            "files": (io.BytesIO(_make_amr_report_html(n_days=3).encode("utf-8")), "report.xls"),
        },
        content_type="multipart/form-data",
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["added_intervals"] == 3 * 96
    assert data["days"] == 3

    status_res = client.get("/api/admin/amr-boxplot/status")
    assert status_res.status_code == 200
    status = status_res.get_json()
    assert status["55101"]["intervals"] == 3 * 96
    assert status["55101"]["days"] == 3

    boxplot_res = client.get("/api/forecast-boxplot", query_string={"business_type_code": "55101"})
    assert boxplot_res.status_code == 200
    assert boxplot_res.headers["Content-Type"] == "image/png"
    assert boxplot_res.data[:8] == b"\x89PNG\r\n\x1a\n"


def test_amr_boxplot_upload_rejects_zip_with_path_traversal(client, monkeypatch, tmp_path):
    """ป้องกัน zip slip — ชื่อไฟล์ในซิปที่มี "../" ปนอยู่ต้องถูกตัด path ย่อยทิ้งก่อนเขียนไฟล์เสมอ
    ไม่ยอมให้เขียนออกไปนอก upload_dir เด็ดขาด (เหมือนเทสต์เดิมของโหมดนำเข้า AMR ก่อนถูกลบไป)"""

    import io
    import zipfile

    monkeypatch.setattr(app_module, "DEFAULT_DATA_DIR", tmp_path)

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        zf.writestr("../../../evil.xls", _make_amr_report_html(n_days=1))
    zip_buf.seek(0)

    res = client.post(
        "/api/admin/amr-boxplot/upload",
        data={"business_type_code": "55101", "files": (zip_buf, "upload.zip")},
        content_type="multipart/form-data",
    )
    assert res.status_code == 200  # ไฟล์ถูก sanitize ชื่อแล้วนำเข้าตามปกติ ไม่ error
    assert not (tmp_path.parent / "evil.xls").exists()
    assert not (Path("/") / "evil.xls").exists()


def test_forecast_boxplot_missing_business_type_returns_400(client):
    res = client.get("/api/forecast-boxplot")
    assert res.status_code == 400


def test_forecast_boxplot_returns_404_without_data(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "DEFAULT_DATA_DIR", tmp_path)
    res = client.get("/api/forecast-boxplot", query_string={"business_type_code": "NOPE"})
    assert res.status_code == 404
    assert res.get_json()["error"] == "not_found"


def test_amr_boxplot_fetch_missing_credentials_returns_400(client):
    res = client.post("/api/admin/amr-boxplot/fetch", json={})
    assert res.status_code == 400
    assert res.get_json()["error"] == "missing_credentials"


def test_amr_boxplot_fetch_manual_mode_without_accounts_returns_400(client):
    res = client.post(
        "/api/admin/amr-boxplot/fetch",
        json={
            "username": "u", "password": "p", "business_type_code": "55101",
            "start_date": "2026-01-01", "end_date": "2026-01-31",
        },
    )
    assert res.status_code == 400
    assert "accounts" in res.get_json()["message"]


def test_amr_boxplot_fetch_invalid_date_format_returns_400(client):
    res = client.post(
        "/api/admin/amr-boxplot/fetch",
        json={"username": "u", "password": "p", "start_date": "25-01-01", "end_date": "2026-01-31"},
    )
    assert res.status_code == 400


def test_amr_boxplot_fetch_start_after_end_returns_400(client):
    res = client.post(
        "/api/admin/amr-boxplot/fetch",
        json={"username": "u", "password": "p", "start_date": "2026-02-01", "end_date": "2026-01-01"},
    )
    assert res.status_code == 400


def test_amr_boxplot_fetch_job_not_found_returns_404(client):
    res = client.get("/api/admin/amr-boxplot/fetch/doesnotexist")
    assert res.status_code == 404


def test_amr_boxplot_fetch_manual_mode_success(client, monkeypatch, tmp_path):
    """ระบุ business_type_code เอง — ต้องเรียก download_amr_kw_reports (หลายบัญชีได้) แล้วป้อนไฟล์
    ที่ดาวน์โหลดสำเร็จเข้า amr_boxplot storage ตรงๆ (mock ตรงต้นทาง amr_mapping.amr_downloader
    เพราะ web/app.py import แบบ lazy — เหมือนที่เทสต์ dbd_scraper ทำ)"""

    import amr_mapping.amr_downloader as amr_downloader_module
    from amr_mapping.amr_downloader import DownloadResult

    monkeypatch.setattr(app_module, "DEFAULT_DATA_DIR", tmp_path)

    report_path = tmp_path / "downloaded_report.xls"
    report_path.write_text(_make_amr_report_html(n_days=3), encoding="utf-8")

    def fake_download(username, password, accounts, start_date, end_date, download_dir, log, headless=True):
        assert accounts == ["0199000001"]
        return [DownloadResult(account_no="0199000001", meter_text="m1", date_from=start_date, date_to=end_date, file_path=str(report_path), success=True)]

    monkeypatch.setattr(amr_downloader_module, "download_amr_kw_reports", fake_download)

    res = client.post(
        "/api/admin/amr-boxplot/fetch",
        json={
            "username": "u", "password": "p", "business_type_code": "55101",
            "accounts": "0199000001", "start_date": "2026-01-01", "end_date": "2026-01-31",
        },
    )
    assert res.status_code == 200
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status = client.get(f"/api/admin/amr-boxplot/fetch/{job_id}").get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "success"
    assert status["result"]["added_intervals"] == 3 * 96
    assert status["result"]["business_type_code"] == "55101"

    coverage = client.get("/api/admin/amr-boxplot/status").get_json()
    assert coverage["55101"]["intervals"] == 3 * 96


def test_amr_boxplot_fetch_auto_detect_mode_success(client, monkeypatch, tmp_path):
    """ไม่ระบุ business_type_code — ต้องเรียก download_amr_with_profile แทน (username เป็นเลขบัญชี
    ตรงๆ) แล้วดึง business_type_code จาก profile มาใช้ (ผ่าน TSIC Code Normalization ตามปกติ)"""

    import amr_mapping.amr_downloader as amr_downloader_module
    from amr_mapping.amr_downloader import DownloadResult

    monkeypatch.setattr(app_module, "DEFAULT_DATA_DIR", tmp_path)
    (tmp_path / "tsic_code_mapping.csv").write_text("old_code,new_code,notes\n93311,86101,โรงพยาบาลทั่วไป\n", encoding="utf-8")

    report_path = tmp_path / "downloaded_report.xls"
    report_path.write_text(_make_amr_report_html(n_days=2), encoding="utf-8")

    def fake_download_with_profile(username, password, start_date, end_date, download_dir, log, headless=True):
        profile = {"business_type_code": "93311", "business_type_name": "กิจกรรมโรงพยาบาล (รหัสเก่า)"}
        results = [DownloadResult(account_no=username, meter_text="m1", date_from=start_date, date_to=end_date, file_path=str(report_path), success=True)]
        return profile, results

    monkeypatch.setattr(amr_downloader_module, "download_amr_with_profile", fake_download_with_profile)

    res = client.post(
        "/api/admin/amr-boxplot/fetch",
        json={"username": "0199000001", "password": "p", "start_date": "2026-01-01", "end_date": "2026-01-31"},
    )
    assert res.status_code == 200
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status = client.get(f"/api/admin/amr-boxplot/fetch/{job_id}").get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "success"
    assert status["result"]["business_type_code"] == "86101"  # แปลงจากรหัสเก่า 93311 แล้ว
    assert status["result"]["added_intervals"] == 2 * 96


def test_amr_boxplot_fetch_reports_download_failure(client, monkeypatch, tmp_path):
    import amr_mapping.amr_downloader as amr_downloader_module

    monkeypatch.setattr(app_module, "DEFAULT_DATA_DIR", tmp_path)

    def fake_download(username, password, accounts, start_date, end_date, download_dir, log, headless=True):
        return []  # ดาวน์โหลดไม่สำเร็จเลยแม้แต่ไฟล์เดียว

    monkeypatch.setattr(amr_downloader_module, "download_amr_kw_reports", fake_download)

    res = client.post(
        "/api/admin/amr-boxplot/fetch",
        json={
            "username": "u", "password": "p", "business_type_code": "55101",
            "accounts": "0199000001", "start_date": "2026-01-01", "end_date": "2026-01-31",
        },
    )
    job_id = res.get_json()["job_id"]

    status = None
    for _ in range(50):
        status = client.get(f"/api/admin/amr-boxplot/fetch/{job_id}").get_json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "error"
    assert "ดาวน์โหลดไม่สำเร็จ" in status["error"]

