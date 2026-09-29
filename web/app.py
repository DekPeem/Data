"""เว็บแอป No AMR — ค้นหาประเภทธุรกิจ (TSIC) ของผู้ใช้ไฟจากชื่อบริษัทหรือเลขทะเบียนนิติบุคคล

รันด้วย:
    python web/app.py
แล้วเปิดเบราว์เซอร์ที่ http://localhost:5000

⚠️ ข้อมูลลูกค้าในเว็บนี้ (data/reference/customers.csv) เป็นข้อมูล "สมมติ" เพื่อสาธิต
การทำงานเท่านั้น ห้ามใส่ข้อมูลลูกค้าจริงลงไฟล์นี้ เพราะ repo เป็น public — ถ้าจะต่อกับ
ข้อมูลลูกค้าจริง ให้เปลี่ยน data_dir ไปชี้ฐานข้อมูลจริงที่แยกเก็บไว้นอก repo แทน
"""

from __future__ import annotations

import dataclasses
import hmac
import io
import os
import sys
import threading
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from flask import Flask, jsonify, request, send_file
from werkzeug.utils import secure_filename

from amr_mapping import load_reference_data
from amr_mapping.dbd_lookup import BlockedByAntiBot, find_exact_match, lookup_business_type_for_company
from amr_mapping.keyword_classify import guess_tsic_division
from amr_mapping.loader import (
    DEFAULT_DATA_DIR,
    load_tsic_code_mapping,
    save_business_types,
    upsert_business_type,
    upsert_customer_local,
)
from amr_mapping.models import BusinessType, Customer
from amr_mapping.tsic_normalize import normalize_tsic_code_with_audit
from amr_mapping.wikipedia_lookup import search_wikipedia_company

app = Flask(__name__, static_folder="static", static_url_path="")


def get_reference():
    """โหลดข้อมูลอ้างอิงใหม่ทุกครั้ง (ไฟล์ CSV เล็กมาก โหลดซ้ำไม่แพง) เพื่อให้เห็นข้อมูลล่าสุด
    ทันทีหลังแก้ทะเบียนลูกค้า/ประเภทธุรกิจ โดยไม่ต้อง restart แอป"""

    return load_reference_data()


# ── Job store สำหรับงานค้นหาประเภทธุรกิจแบบ background (เก็บใน memory พอ เพราะเป็นเครื่องมือ
#    ใช้คนเดียวในเครื่อง ไม่ใช่ multi-user service) ──
_JOBS: dict = {}
_JOBS_LOCK = threading.Lock()


def _customer_to_dict(customer) -> dict:
    return {
        "account_no": customer.account_no,
        "name": customer.name,
        "business_type_code": customer.business_type_code,
        "business_type_code_raw": customer.business_type_code_raw,
        "has_amr": customer.has_amr,
        "registration_no": customer.registration_no,
    }


@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/api/customers")
def api_list_customers():
    """รายชื่อผู้ใช้ไฟทั้งหมด (สำหรับ dropdown/autocomplete ในหน้าค้นหา)"""

    return jsonify([_customer_to_dict(c) for c in get_reference().customers])


@app.route("/api/business-types")
def api_list_business_types():
    """รายชื่อประเภทธุรกิจทั้งหมด (สำหรับ dropdown ในหน้านำเข้า AMR / หน้าพยากรณ์แบบไม่บันทึก)"""

    return jsonify(
        [
            {"code": bt.code, "name_th": bt.name_th, "category": bt.category}
            for bt in get_reference().business_types.values()
        ]
    )


@app.route("/api/business-types", methods=["POST"])
def api_create_business_type():
    """เพิ่มประเภทธุรกิจใหม่เอง (self-service) — ให้ผู้ใช้เพิ่มรหัส TSIC ที่ค้นเจอเองได้ทันทีตอน
    เจอบริษัทที่ยังไม่มีในระบบ ไม่ต้องรอให้แก้ business_types.csv ให้ทุกครั้ง

    code ต้องไม่ซ้ำกับที่มีอยู่แล้ว (ใช้ /api/business-types/<code>/hierarchy ถ้าจะแก้ Section/
    Division ของรหัสที่มีอยู่แล้วแทน) — เป็นแค่รหัส/ชื่อหมวดธุรกิจสาธารณะ commit เข้า repo ได้
    ไม่มีชื่อบริษัทเกี่ยวข้องเลย เหมือน /api/business-types/<code>/hierarchy"""

    body = request.get_json(force=True, silent=True) or {}
    code = (body.get("code") or "").strip()
    name_th = (body.get("name_th") or "").strip()
    if not code or not name_th:
        return jsonify({"error": "invalid_request", "message": "กรุณากรอกรหัสและชื่อประเภทธุรกิจให้ครบ"}), 400

    reference = get_reference()
    if code in reference.business_types:
        return jsonify({"error": "duplicate", "message": f"มีรหัส {code} อยู่แล้วในระบบ — ถ้าต้องการแก้ Section/Division ใช้ช่องแก้ไขของรหัสเดิมแทน"}), 409

    alias_of = (body.get("alias_of") or "").strip() or None
    if alias_of and alias_of not in reference.business_types:
        return jsonify({"error": "invalid_request", "message": f"ไม่พบรหัส {alias_of} ที่จะตั้งเป็น alias เป้าหมาย"}), 400

    new_bt = BusinessType(
        code=code,
        name_th=name_th,
        category=(body.get("category") or "manual").strip(),
        notes=(body.get("notes") or "").strip(),
        section_code=(body.get("section_code") or "").strip() or None,
        section_name_th=(body.get("section_name_th") or "").strip(),
        division_code=(body.get("division_code") or "").strip() or None,
        division_name_th=(body.get("division_name_th") or "").strip(),
        alias_of=alias_of,
    )
    updated_bts = upsert_business_type(reference.business_types, new_bt)
    save_business_types(updated_bts, DEFAULT_DATA_DIR / "business_types.csv")

    return jsonify({"code": new_bt.code, "name_th": new_bt.name_th}), 201


@app.route("/api/business-types-full")
def api_list_business_types_full():
    """รายชื่อประเภทธุรกิจทั้งหมดแบบละเอียด (รวม TSIC section/division) — ใช้โดยตาราง "หมวดหมู่
    ธุรกิจทั้งหมดในระบบ" ในหน้า Admin เพื่อดูภาพรวมของข้อมูลอ้างอิงทั้งหมดในเครื่องนี้ในที่เดียว
    ไม่ต้องเปิดไฟล์ CSV ดูเอง"""

    reference = get_reference()
    return jsonify(
        [
            {
                "code": bt.code,
                "name_th": bt.name_th,
                "category": bt.category,
                "notes": bt.notes,
                "section_code": bt.section_code,
                "section_name_th": bt.section_name_th,
                "division_code": bt.division_code,
                "division_name_th": bt.division_name_th,
                "alias_of": bt.alias_of,
            }
            for bt in reference.business_types.values()
        ]
    )


@app.route("/api/admin/overview-entry", methods=["PATCH"])
def api_update_overview_entry():
    """แก้ไขประเภทธุรกิจของบัญชีหนึ่งจากหน้า "ภาพรวมลูกค้าทั้งหมด" (/overview) โดยตรง — เขียนลง
    customers_local.csv (upsert ตาม account_no) ซึ่งเป็นไฟล์ที่
    get_reference()/load_reference_data() ใช้ override ทะเบียนลูกค้าเสมอ (ดู
    load_reference_data ใน loader.py) จึงมีผลกับทั้งระบบทันที (หน้าค้นหา/พยากรณ์ที่อ่านทะเบียน
    นี้จะเห็นค่าใหม่โดยไม่ต้อง restart เซิร์ฟเวอร์)

    ถ้าตั้งค่า environment variable ADMIN_EDIT_PASSWORD ไว้ (ดู .env.example) จะต้องกรอกรหัสผ่าน
    ให้ตรงถึงจะแก้ไขได้ (เทียบด้วย hmac.compare_digest กัน timing attack) — แต่ถ้า "ไม่ได้ตั้งค่า
    นี้เลย" (ค่าเริ่มต้น) จะแก้ไขได้อิสระโดยไม่ต้องใส่รหัสผ่าน (ยังตั้งค่าเปิดใช้งานทีหลังได้เสมอ
    เมื่อพร้อม) เพราะเครื่องมือนี้ใช้ในเครื่องตัวเอง (127.0.0.1) คนเดียวเป็นหลัก ไม่ได้เปิดออก
    เครือข่ายสาธารณะ — ความสะดวกสำคัญกว่าความปลอดภัยเข้มงวดสำหรับ use case นี้"""

    # .strip() กันปัญหาที่เจอจริง: Windows cmd.exe เก็บช่องว่างท้ายค่าไว้ตรงๆ ถ้าพิมพ์
    # `set ADMIN_EDIT_PASSWORD=123456 ` (มีเว้นวรรคเกินก่อน Enter) — ตัวแปรจะเป็น "123456 " ทำให้
    # เทียบกับรหัสผ่านที่พิมพ์ในกล่อง prompt ("123456" ไม่มีเว้นวรรค) ไม่ตรงกันทั้งที่ผู้ใช้มองว่า
    # เป็นรหัสเดียวกัน ไม่มีใครตั้งใจใช้ช่องว่างนำ/ตามหลังเป็นส่วนหนึ่งของรหัสผ่านจริงๆ อยู่แล้ว
    configured_password = (os.environ.get("ADMIN_EDIT_PASSWORD") or "").strip()

    body = request.get_json(silent=True) or {}
    if configured_password:
        password = (body.get("password") or "").strip()
        # hmac.compare_digest แบบ str ต้องเป็น ASCII ล้วนทั้งคู่เท่านั้น (raise TypeError ถ้ามี
        # อักขระนอก ASCII แม้แต่ตัวเดียวในฝั่งไหนก็ตาม) — เข้ารหัสเป็น UTF-8 bytes ก่อนเทียบเสมอ
        # กันพังกรณีตั้งรหัสผ่าน/พิมพ์รหัสผ่านเป็นภาษาไทยหรือมีอักขระพิเศษปน
        if not hmac.compare_digest(password.encode("utf-8"), configured_password.encode("utf-8")):
            return jsonify({"error": "wrong_password", "message": "รหัสผ่านไม่ถูกต้อง"}), 403

    account_no = (body.get("account_no") or "").strip()
    if not account_no:
        return jsonify({"error": "invalid_request", "message": "ต้องระบุเลขบัญชี"}), 400

    # เอาค่าปัจจุบัน (จากทะเบียนที่ merge แล้ว) มาเป็นฐาน — ฟิลด์ไหนไม่ได้ส่งมาแก้ ให้คงค่าเดิมไว้
    current = next((c for c in get_reference().customers if c.account_no == account_no), None)

    name = body.get("name", current.name if current else "") or (current.name if current else account_no)

    # TSIC Code Normalization — business_type_code ที่ผู้ใช้กรอก/เลือกเองในหน้า /overview (User
    # Input) อาจเป็นรหัสเก่าตามระบบเดิมของ กฟภ. ก็ได้ แปลงเป็นรหัสมาตรฐานใหม่ทันทีก่อนบันทึกลง
    # customers_local.csv (ฟิลด์ business_type_code ใช้จับคู่จริงทั้งระบบ) เก็บรหัสดิบไว้ที่
    # business_type_code_raw เป็น audit trail (ดู tsic_normalize.py) — คำนวณใหม่เฉพาะตอนที่ body
    # ส่ง business_type_code มาแก้จริงๆ เท่านั้น ไม่งั้นจะคำนวณจากค่าที่แปลงแล้วเดิมซ้ำ (idempotent
    # ไม่มีผลต่อ business_type_code เอง แต่จะเขียนทับ audit trail เดิมทิ้งอย่างผิดๆ ทุกครั้งที่แก้
    # ฟิลด์อื่นที่ไม่เกี่ยวเลย เช่น registration_no)
    if "business_type_code" in body:
        tsic_mapping = load_tsic_code_mapping(DEFAULT_DATA_DIR / "tsic_code_mapping.csv")
        business_type_code, business_type_code_raw = normalize_tsic_code_with_audit(
            body.get("business_type_code"), tsic_mapping
        )
    else:
        business_type_code = current.business_type_code if current else None
        business_type_code_raw = current.business_type_code_raw if current else None

    registration_no = body.get("registration_no", current.registration_no if current else None)
    has_amr = current.has_amr if current else False

    updated = Customer(
        account_no=account_no,
        name=(name or account_no).strip(),
        business_type_code=(business_type_code or "").strip() or None,
        business_type_code_raw=business_type_code_raw,
        has_amr=has_amr,
        registration_no=(registration_no or "").strip() or None,
    )

    upsert_customer_local(DEFAULT_DATA_DIR / "customers_local.csv", updated)
    return jsonify(_customer_to_dict(updated))


# ไฟล์ local-only ที่มีชื่อบริษัท/เลขบัญชีลูกค้าจริง (อยู่ใน .gitignore แล้ว ไม่เคยถูก commit
# เข้า repo) — เป็นข้อมูลชุดเดียวที่ "ไม่มีสำเนาสำรองที่ไหนเลย" ถ้าเครื่องที่รันเว็บนี้พัง/ไฟล์
# เสียหาย ข้อมูลที่กรอกไว้ทั้งหมดจะหายถาวร กู้คืนไม่ได้ (ต่างจาก business_types.csv ที่ commit
# เข้า git repo อยู่แล้ว จึงไม่รวมในนี้)
_BACKUP_LOCAL_FILENAMES = ["customers_local.csv"]


@app.route("/api/admin/backup")
def api_admin_backup():
    """สร้างไฟล์ .zip รวมข้อมูล local-only ทั้งหมดที่มีอยู่จริงตอนนี้ (ข้ามไฟล์ที่ยังไม่เคยสร้าง)
    ให้ดาวน์โหลดทันที — ใช้สำรองข้อมูลลูกค้าจริงไว้นอกเครื่องเป็นระยะ (เช่น ก็อปไปไดรฟ์อื่น/
    คลาวด์ส่วนตัว) เพราะไฟล์เหล่านี้อยู่ในเครื่องอย่างเดียว ไม่เคย commit เข้า git เลย"""

    buffer = io.BytesIO()
    included = []
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename in _BACKUP_LOCAL_FILENAMES:
            path = DEFAULT_DATA_DIR / filename
            if path.exists():
                zf.write(path, arcname=filename)
                included.append(filename)
    buffer.seek(0)

    if not included:
        return jsonify({"error": "no_data", "message": "ยังไม่มีข้อมูล local ให้สำรองเลย"}), 404

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return send_file(
        buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"no-amr-backup-{timestamp}.zip",
    )


@app.route("/api/business-types/<code>/hierarchy", methods=["POST"])
def api_update_business_type_hierarchy(code: str):
    """บันทึก TSIC section/division ที่ตรวจสอบแล้วของประเภทธุรกิจตัวหนึ่ง (แก้ business_types.csv
    ที่ commit เข้า repo ได้ — เป็นแค่รหัส/ชื่อหมวดธุรกิจสาธารณะ ไม่มีชื่อบริษัทเกี่ยวข้องเลย)"""

    body = request.get_json(force=True, silent=True) or {}
    section_code = (body.get("section_code") or "").strip() or None
    section_name_th = (body.get("section_name_th") or "").strip()
    division_code = (body.get("division_code") or "").strip() or None
    division_name_th = (body.get("division_name_th") or "").strip()

    reference = get_reference()
    existing = reference.business_types.get(code)
    if existing is None:
        return jsonify({"error": "not_found", "message": f"ไม่พบประเภทธุรกิจรหัส {code}"}), 404

    updated = dataclasses.replace(
        existing,
        section_code=section_code,
        section_name_th=section_name_th,
        division_code=division_code,
        division_name_th=division_name_th,
    )
    updated_bts = upsert_business_type(reference.business_types, updated)
    save_business_types(updated_bts, DEFAULT_DATA_DIR / "business_types.csv")

    return jsonify({"code": code, "section_code": section_code, "division_code": division_code})


def _suggest_business_type_for_division(
    tsic_code: Optional[str], division_code: Optional[str], reference
) -> tuple:
    """คืน (suggested_code, suggested_name, is_approximate, explanation) — ลองรหัส TSIC ตรงเป๊ะ
    ก่อนเสมอ (ถ้ามีอยู่ในระบบ business_types.csv แล้ว) ก่อนจะลดชั้นไปใช้ business_type อื่นที่อยู่
    TSIC division เดียวกันแทน (ประมาณการ) ถ้ายังไม่มีเลยทั้งสองชั้น คืน (None, None, False, None)
    ให้ผู้ใช้เลือกเอง/เพิ่มประเภทธุรกิจใหม่เอง (ดู POST /api/business-types)

    ใช้ร่วมกันทั้งผลจาก DBD DataWarehouse โดยตรง และคำเดาจาก Wikipedia (ทั้งสองมี division_code
    ติดมาด้วยเหมือนกัน แต่ Wikipedia มักไม่มี tsic_code ที่แน่นอนให้ลองจับคู่แบบตรงเป๊ะ ส่งแค่
    division_code มาแล้วปล่อย tsic_code=None ได้)"""

    if tsic_code and tsic_code in reference.business_types:
        bt = reference.business_types[tsic_code]
        return (bt.code, bt.name_th, False, None)

    if division_code:
        for bt in reference.business_types.values():
            if bt.division_code == division_code:
                explanation = (
                    f"ไม่มีรหัส TSIC {tsic_code or division_code} ตรงๆ ในระบบ ใช้ '{bt.name_th}' "
                    f"({bt.code}) ที่อยู่ TSIC division {division_code} เดียวกันแทน"
                )
                return (bt.code, bt.name_th, True, explanation)

    return (None, None, False, None)


def _rank_businesses_by_division(division_code: Optional[str], reference, limit: int = 3) -> List[BusinessType]:
    """คืน business_type ที่อยู่ TSIC division เดียวกันสูงสุด limit รายการ — ใช้ตอนเดา TSIC จาก
    Wikipedia ได้ไม่มั่นใจพอ (ดู _run_business_type_lookup_job) ให้ผู้ใช้เลือกเองจากตัวเลือก
    ใกล้เคียงแทนที่จะเดาให้อัตโนมัติ"""

    if not division_code:
        return []
    return [bt for bt in reference.business_types.values() if bt.division_code == division_code][:limit]


def _run_business_type_lookup_job(
    job_id: str,
    company_name: str,
    registration_no: Optional[str] = None,
) -> None:
    """ค้นหาประเภทธุรกิจ (TSIC) ของบริษัทจากชื่อ (หรือเลขทะเบียนนิติบุคคลถ้ามี) ผ่าน DBD
    DataWarehouse (ดู dbd_lookup.py) — รันเป็น background job เพราะเปิดเบราว์เซอร์จริงใช้เวลา
    หลายวินาที

    ⚠️ คำค้นหาที่พิมพ์ในหน้านี้ "ถูกส่งออกไปค้นหาที่เว็บ DBD จริง" เพราะไม่มีทางค้นหาบริษัทจากชื่อ/
    เลขทะเบียนได้โดยไม่ส่งไปที่แหล่งข้อมูลนั้น — หน้าเว็บต้องแจ้งผู้ใช้ให้ชัดเจนก่อนกดใช้ฟีเจอร์นี้
    (ดู index.html)

    registration_no (ไม่บังคับ — เลขทะเบียนนิติบุคคล 13 หลัก) ถ้ามีจะใช้เป็นคำค้นหาแทนชื่อบริษัท
    ทันที (แม่นยำกว่ามาก ไม่มีปัญหาเรื่องสะกด/คำนำหน้า-ต่อท้ายไม่ตรงกับที่จดทะเบียนไว้เป๊ะเหมือนชื่อ)
    และใช้เทียบหา "exact match" ด้วยเลขทะเบียนแทนชื่อด้วย — company_name ยังต้องส่งมาเสมอ (ใช้เป็น
    ชื่อที่แสดง/log เฉยๆ ถ้ามี registration_no ให้ค้นหาแทน)
    """

    def log(msg: str) -> None:
        with _JOBS_LOCK:
            _JOBS[job_id]["logs"].append(msg)

    reference = get_reference()

    try:
        # มีเลขทะเบียนนิติบุคคล — ใช้ dbd_scraper (Playwright, ขับกล่องค้นหาบนหน้าเว็บจริง) แทน
        # dbd_lookup (Selenium, ค้นด้วยชื่อผ่าน keyword search) เพราะยืนยันจากผู้ใช้จริงว่าการเดา
        # URL หน้าโปรไฟล์ตรงๆ/ค้นด้วยเลขทะเบียนผ่านช่องค้นหาแบบเดิมไม่น่าเชื่อถือ/โดนบล็อกบ่อย
        # (ดู amr_mapping.dbd_scraper.tsic_lookup) — import แบบ lazy ตรงนี้ (ไม่ใช่ top-level ของ
        # ไฟล์) เพราะต้องพึ่ง playwright (dependency ใหม่) เหมือนที่ dbd_lookup.py เอง lazy-import
        # selenium เข้าไปเฉพาะตอนใช้จริง — กัน web/app.py ทั้งไฟล์ boot ไม่ขึ้นถ้าเครื่องนั้นยังไม่ได้
        # ติดตั้ง playwright ไว้ (ฟีเจอร์อื่นๆ ที่ไม่เกี่ยวกับการค้นหาด้วยเลขทะเบียนต้องใช้งานได้ตามปกติ)
        if registration_no:
            from amr_mapping.dbd_scraper import lookup_tsic_by_registration_no

            # headless=True (ไม่เปิดหน้าต่างเบราว์เซอร์ให้เห็นเลย) ตามที่ผู้ใช้ยืนยันไว้ — เคยลองทำ
            # แบบเปิดหน้าต่างจริง (headless=False) แล้วหยุดรอให้คลิก reload เองตอนโดนบล็อก (เหมือน
            # scripts/lookup_tsic.py ตอนรันแบบ interactive) แต่ผู้ใช้ไม่ต้องการให้มีหน้าต่าง popup
            # โผล่ขึ้นมาตอนค้นหาผ่านเว็บ จึงตัดกลไกนั้นออกจากเว็บไปเลย (ไม่ส่ง on_blocked — ไม่มีทาง
            # ให้คนช่วยคลิก reload ได้อยู่แล้วถ้าไม่มีหน้าต่างให้เห็น) แลกกับการที่ถ้าโดนบล็อกจริงจะลอง
            # หาข้อมูลจาก Wikipedia แทน (ดู except BlockedByAntiBot ด้านล่าง) ไม่ได้ TSIC ตรงจาก DBD
            # เป๊ะเหมือนตอนคลิก reload เองได้ — ยังใช้กลไก on_blocked ได้อยู่ถ้าจะรัน
            # scripts/lookup_tsic.py debug ในเครื่องเอง
            results = lookup_tsic_by_registration_no(registration_no, log=log)
        else:
            results = lookup_business_type_for_company(company_name, log=log)

        candidates = []
        for r in results:
            suggested_code, suggested_name, is_approximate, explanation = _suggest_business_type_for_division(
                r.tsic_code, r.tsic_division_code, reference
            )
            candidates.append(
                {
                    "registration_no": r.registration_no,
                    "juristic_name": r.juristic_name,
                    "juristic_type": r.juristic_type,
                    "status": r.status,
                    "tsic_code": r.tsic_code,
                    "tsic_name_th": r.tsic_name_th,
                    "tsic_division_code": r.tsic_division_code,
                    "suggested_business_type_code": suggested_code,
                    "suggested_business_type_name": suggested_name,
                    "suggested_is_approximate": is_approximate,
                    "suggested_explanation": explanation,
                }
            )

        if registration_no:
            normalized_reg_no = registration_no.strip()
            exact = next((r for r in results if r.registration_no.strip() == normalized_reg_no), None)
        else:
            exact = find_exact_match(results, company_name)
        exact_index = results.index(exact) if exact is not None else None

        # เลือก "บริษัทหลัก" ที่จะไฮไลต์ให้ทันที: ถ้าเจอชื่อตรงเป๊ะ (exact) ใช้ตัวนั้นเสมอ — มั่นใจ
        # ได้ว่าเป็นบริษัทเดียวกับที่พิมพ์มา ถ้าไม่เจอชื่อตรงเป๊ะแต่ค้นหาแล้วได้ผลลัพธ์แค่รายการเดียว
        # ก็ถือว่าเป็นบริษัทเดียวกันได้อย่างมั่นใจพอเช่นกัน (เช่น พิมพ์ชื่อคลาดเคลื่อนจากที่ DBD บันทึก
        # ไว้เล็กน้อย) ถ้ามีหลายรายการและไม่มีตัวไหนตรงชื่อเป๊ะเลย ถือว่า "กำกวม" (อาจเป็นคนละบริษัทกับ
        # ที่ตั้งใจ) — ติดธง primary_is_ambiguous ไว้ให้หน้าเว็บเตือนผู้ใช้ให้ตรวจสอบ/เลือกจาก
        # candidates เองแทนถ้าตัวที่ไฮไลต์มาไม่ใช่บริษัทที่ต้องการจริงๆ
        primary_index: Optional[int] = None
        primary_is_ambiguous = False
        if exact_index is not None:
            primary_index = exact_index
        elif len(results) == 1:
            primary_index = 0
        elif len(results) > 1:
            primary_index = 0
            primary_is_ambiguous = True

        with _JOBS_LOCK:
            _JOBS[job_id]["status"] = "success"
            _JOBS[job_id]["result"] = {
                "query": company_name,
                "candidates": candidates,
                "exact_match_index": exact_index,
                "blocked": False,
                "primary_index": primary_index,
                "primary_is_ambiguous": primary_is_ambiguous,
            }
    except BlockedByAntiBot as e:
        log(f"🚫 {e}")

        # ช่องทางฟรีเพิ่มเติม: Wikipedia ภาษาไทย (ดู wikipedia_lookup.py) — ครอบคลุมเฉพาะบริษัทใหญ่/
        # มีชื่อเสียงเท่านั้น คืนแค่ข้อความอิสระ ไม่ใช่รหัส TSIC จึงจับคู่อัตโนมัติไม่ได้แบบมั่นใจเต็มที่
        wikipedia_result = None
        try:
            wp = search_wikipedia_company(company_name, log=log)
            if wp:
                wikipedia_result = {"title": wp.title, "summary": wp.summary, "url": wp.url}

                # ลองเดาประเภทธุรกิจจากคำสำคัญในข้อความ Wikipedia (ดู keyword_classify.py) —
                # ไม่ใช่รหัส TSIC จริง แค่จับคำตรงตัว จึงต้องบอกผู้ใช้ชัดเจนเสมอว่าเป็นการเดา
                # (ดู guessed_keyword) ไม่ใช่ข้อมูลทางการเหมือนผลจาก DBD DataWarehouse โดยตรง
                guess = guess_tsic_division(f"{wp.title} {wp.summary}")
                if guess:
                    guessed_division_code, guessed_keyword = guess
                    log(f"🔤 เดาประเภทธุรกิจจากคำว่า '{guessed_keyword}' ในข้อความ Wikipedia")
                    suggested_code, suggested_name, is_approximate, explanation = _suggest_business_type_for_division(
                        None, guessed_division_code, reference
                    )
                    wikipedia_result["guessed_keyword"] = guessed_keyword
                    wikipedia_result["suggested_business_type_name"] = suggested_name
                    wikipedia_result["suggested_is_approximate"] = is_approximate
                    wikipedia_result["suggested_explanation"] = explanation

                    if is_approximate:
                        # ไม่มั่นใจพอ (แค่เดาแบบประมาณการ) — ไม่ตั้งค่าให้อัตโนมัติแบบเงียบๆ (เคยเจอ
                        # เคสจริงที่เดาไปโดนธุรกิจคนละแบบเลย เช่น ค้าปลีกไปจับกับการผลิตกระดาษ) ให้
                        # แสดงรายการอันดับ 1/2/3 ที่ใกล้เคียงที่สุดแทน ให้ผู้ใช้เลือกเอง
                        suggested_code = None
                        ranked = _rank_businesses_by_division(guessed_division_code, reference, limit=3)
                        wikipedia_result["ranked_candidates"] = [
                            {
                                "business_type_code": bt.code,
                                "business_type_name": bt.name_th,
                                "match_basis": "same_division",
                                "explanation": f"อยู่ TSIC division {guessed_division_code} เดียวกับที่เดาไว้",
                            }
                            for bt in ranked
                        ]
                    wikipedia_result["suggested_business_type_code"] = suggested_code
        except Exception as wikipedia_error:  # noqa: BLE001 — ฟรี/เสริมเฉยๆ ล้มแล้วไม่ควรทำให้ job พัง
            log(f"⚠️ ค้นจาก Wikipedia ไม่สำเร็จ: {wikipedia_error}")

        with _JOBS_LOCK:
            _JOBS[job_id]["status"] = "success"
            _JOBS[job_id]["result"] = {
                "query": company_name,
                "candidates": [],
                "exact_match_index": None,
                "blocked": True,
                "blocked_message": str(e),
                "wikipedia_result": wikipedia_result,
            }
    except Exception as e:  # noqa: BLE001 — ต้อง catch ทุก error เพื่อรายงานสถานะ job ให้ถูกต้อง
        with _JOBS_LOCK:
            _JOBS[job_id]["status"] = "error"
            _JOBS[job_id]["error"] = str(e)


@app.route("/api/business-type-lookup", methods=["POST"])
def api_start_business_type_lookup():
    """เริ่ม job ค้นหาประเภทธุรกิจ (TSIC) จากชื่อบริษัท ผ่าน DBD DataWarehouse (background job
    เพราะต้องเปิดเบราว์เซอร์จริง ใช้เวลาหลายวินาที)"""

    body = request.get_json(force=True, silent=True) or {}
    company_name = (body.get("company_name") or "").strip()
    registration_no = (body.get("registration_no") or "").strip() or None
    if not company_name:
        return jsonify({"error": "invalid_request", "message": "กรุณาระบุชื่อบริษัท"}), 400

    job_id = uuid.uuid4().hex
    with _JOBS_LOCK:
        _JOBS[job_id] = {"status": "running", "logs": [], "result": None, "error": None}

    thread = threading.Thread(
        target=_run_business_type_lookup_job,
        args=(job_id, company_name, registration_no),
        daemon=True,
    )
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/api/business-type-lookup/<job_id>")
def api_get_business_type_lookup_status(job_id: str):
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return jsonify({"error": "not_found", "message": "ไม่พบ job นี้"}), 404
        return jsonify(dict(job))


def _parse_optional_float(raw: Optional[str], field_name: str) -> Optional[float]:
    if raw is None or raw.strip() == "":
        return None
    try:
        return float(raw)
    except ValueError:
        raise ValueError(f"{field_name} ต้องเป็นตัวเลข")


def _parse_optional_int(raw: Optional[str], field_name: str) -> Optional[int]:
    if raw is None or raw.strip() == "":
        return None
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"{field_name} ต้องเป็นจำนวนเต็ม")


@app.route("/api/forecast-shape")
def api_forecast_shape():
    """พยากรณ์ "รูปทรง" เส้นโค้งการใช้ไฟรายชั่วโมง (P/OP/H) จากตัวเลขบนบิลค่าไฟ (Peak kW + หน่วยไฟ
    kWh) เท่านั้น — ไม่ต้องมี AMR จริงเลย (ดู src/amr_mapping/forecast_shape.py) คืนรูปภาพ PNG ตรงๆ
    (ไม่ใช่ JSON) ให้ฝั่งหน้าเว็บเอาไปแสดงเป็น <img> ได้เลย — ต่างจาก endpoint อื่นๆ ในไฟล์นี้ที่คืน
    JSON ทั้งหมด เพราะเนื้อหาเป็นรูปภาพโดยตรง ไม่มีอะไรต้อง serialize เพิ่ม

    ⚠️ import matplotlib.pyplot/forecast_shape แบบ lazy ในนี้ (ไม่ใช่ top-level ของไฟล์) เพราะเป็น
    dependency หนักที่ใช้แค่ endpoint เดียว เหมือนที่ dbd_scraper (playwright) ถูก lazy-import ไว้ใน
    _run_business_type_lookup_job เช่นกัน — กันไม่ให้ทั้งแอป boot ช้าลงถ้าไม่ได้ใช้ฟีเจอร์นี้เลย"""

    from amr_mapping.forecast_shape import forecast_shape_png

    args = request.args
    try:
        peak_p = _parse_optional_float(args.get("peak_p"), "Peak P")
        energy_p = _parse_optional_float(args.get("energy_p"), "หน่วยไฟ P")
        days_p = _parse_optional_int(args.get("days_p"), "จำนวนวัน P")
        peak_op = _parse_optional_float(args.get("peak_op"), "Peak OP")
        energy_op = _parse_optional_float(args.get("energy_op"), "หน่วยไฟ OP")
        days_op = _parse_optional_int(args.get("days_op"), "จำนวนวัน OP")
        peak_h = _parse_optional_float(args.get("peak_h"), "Peak H")
        energy_h = _parse_optional_float(args.get("energy_h"), "หน่วยไฟ H")
        days_h = _parse_optional_int(args.get("days_h"), "จำนวนวัน H")
        drop_pct = _parse_optional_float(args.get("drop_pct"), "% ลดตอนพักเที่ยง")
    except ValueError as e:
        return jsonify({"error": "invalid_request", "message": str(e)}), 400

    try:
        png_bytes = forecast_shape_png(
            peak_p=peak_p, energy_p=energy_p, days_p=days_p,
            peak_op=peak_op, energy_op=energy_op, days_op=days_op,
            peak_h=peak_h, energy_h=energy_h, days_h=days_h,
            drop_pct=drop_pct if drop_pct is not None else 43.0,
        )
    except ValueError as e:
        return jsonify({"error": "invalid_request", "message": str(e)}), 400

    return app.response_class(png_bytes, mimetype="image/png")


# ── Boxplot จากข้อมูล AMR จริงที่แอดมินอัปโหลด แยกเก็บตามประเภทธุรกิจ (TSIC) — ดู
#    src/amr_mapping/amr_boxplot.py ต่างจาก /api/forecast-shape ด้านบนตรงที่นี่คือข้อมูล "วัดจริง"
#    ของธุรกิจประเภทเดียวกัน ไม่ใช่เส้นโค้งสมมติจากตัวเลขบิล ──

_AMR_BOXPLOT_FILE_EXTENSIONS = (".xls", ".xlsx", ".html", ".htm")
_MAX_AMR_ZIP_EXTRACTED_BYTES = 300 * 1024 * 1024  # 300 MB
_MAX_AMR_ZIP_MEMBERS = 1000


def _save_uploaded_amr_boxplot_files(files, upload_dir: Path) -> List[str]:
    """บันทึกไฟล์ AMR ที่แนบมาลง upload_dir — แตก .zip ให้อัตโนมัติถ้ามี (เผื่อรวมหลายเดือนมาเป็น
    ซิปเดียว) กัน zip slip ด้วยการตัด path ย่อยทิ้งจากชื่อไฟล์ในซิปเสมอ (ดู
    _save_uploaded_amr_files เดิมใน git history — ย้ายมาแบบง่ายลง เพราะที่นี่ไม่ต้องแยกกลุ่มตาม
    บริษัทเหมือนโหมดนำเข้าหลายบริษัทพร้อมกันแบบเดิม อัปโหลดครั้งนึงคือ TSIC เดียวเสมอ)"""

    file_paths: List[str] = []
    for f in files:
        filename = secure_filename(f.filename or "") or f"upload_{len(file_paths) + 1}"

        if filename.lower().endswith(".zip"):
            zip_path = upload_dir / f"_upload_{len(file_paths)}.zip"
            f.save(zip_path)
            try:
                with zipfile.ZipFile(zip_path) as zf:
                    members = [m for m in zf.infolist() if not m.is_dir()]
                    if len(members) > _MAX_AMR_ZIP_MEMBERS:
                        raise ValueError(f"ไฟล์ {filename} มีไฟล์ข้างในเยอะเกินไป ({len(members)} ไฟล์)")
                    total_size = sum(m.file_size for m in members)
                    if total_size > _MAX_AMR_ZIP_EXTRACTED_BYTES:
                        raise ValueError(f"ไฟล์ {filename} ขนาดหลังแตกไฟล์ใหญ่เกินไป")

                    for i, member in enumerate(members):
                        member_name = Path(member.filename).name  # ตัด path ย่อยทิ้ง กัน zip slip
                        if not member_name or member_name.startswith("."):
                            continue
                        if "__MACOSX" in Path(member.filename).parts:
                            continue
                        if not member_name.lower().endswith(_AMR_BOXPLOT_FILE_EXTENSIONS):
                            continue
                        safe_name = secure_filename(member_name) or f"zip_entry_{i}"
                        dest = (upload_dir / safe_name).resolve()
                        if upload_dir.resolve() not in dest.parents and dest != upload_dir.resolve():
                            continue  # ป้องกันไว้อีกชั้น แม้ตัด path ย่อยไปแล้วก็ตาม
                        if dest.exists():
                            dest = upload_dir / f"{i}_{safe_name}"
                        with zf.open(member) as src, open(dest, "wb") as out:
                            out.write(src.read())
                        file_paths.append(str(dest))
            except zipfile.BadZipFile:
                raise ValueError(f"ไฟล์ {filename} ไม่ใช่ไฟล์ .zip ที่ถูกต้อง หรือไฟล์เสียหาย")
            finally:
                zip_path.unlink(missing_ok=True)
            continue

        dest = upload_dir / filename
        f.save(dest)
        if filename.lower().endswith(_AMR_BOXPLOT_FILE_EXTENSIONS):
            file_paths.append(str(dest))

    return file_paths


@app.route("/api/admin/amr-boxplot/upload", methods=["POST"])
def api_amr_boxplot_upload():
    """อัปโหลดไฟล์ AMR จริง (รายงาน 15 นาทีจาก PEA) ผูกกับประเภทธุรกิจ (TSIC) หนึ่งรายการ — อ่าน
    แล้วเก็บเฉพาะตัวเลขกำลังไฟฟ้ารายชั่วโมง (ไม่เก็บชื่อ/เลขบัญชีลูกค้าเลย) ลงไฟล์ local-only
    (amr_boxplot_intervals_local.csv) สะสมไปเรื่อยๆ ทุกครั้งที่อัปโหลดเพิ่ม (ดู
    src/amr_mapping/amr_boxplot.py)"""

    from amr_mapping.amr_boxplot import append_intervals_local, parse_amr_files

    business_type_code = (request.form.get("business_type_code") or "").strip()
    files = request.files.getlist("files")
    if not business_type_code:
        return jsonify({"error": "invalid_request", "message": "กรุณาเลือกประเภทธุรกิจ (TSIC)"}), 400
    if not files:
        return jsonify({"error": "invalid_request", "message": "กรุณาแนบไฟล์ AMR อย่างน้อย 1 ไฟล์"}), 400

    upload_id = uuid.uuid4().hex
    upload_dir = DEFAULT_DATA_DIR / "_amr_boxplot_uploads" / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    try:
        file_paths = _save_uploaded_amr_boxplot_files(files, upload_dir)
    except ValueError as e:
        return jsonify({"error": "invalid_request", "message": str(e)}), 400

    if not file_paths:
        return jsonify(
            {"error": "invalid_request", "message": "ไม่พบไฟล์ AMR ที่รองรับ (.xls/.xlsx/.html/.htm) ในไฟล์ที่แนบมาเลย"}
        ), 400

    intervals = parse_amr_files(file_paths)
    if not intervals:
        return jsonify(
            {"error": "invalid_request", "message": "อ่านไฟล์ที่แนบมาไม่ได้เลย (รูปแบบอาจไม่ตรงกับรายงาน AMR ของ PEA)"}
        ), 400

    storage_path = DEFAULT_DATA_DIR / "amr_boxplot_intervals_local.csv"
    added = append_intervals_local(business_type_code, intervals, storage_path)

    return jsonify({"added_intervals": added, "days": len({i.date for i in intervals})})


@app.route("/api/admin/amr-boxplot/status")
def api_amr_boxplot_status():
    """สรุปว่าแต่ละประเภทธุรกิจ (TSIC) มีข้อมูล AMR จริงสะสมไว้เท่าไหร่แล้ว — ใช้แสดงในหน้า Admin"""

    from amr_mapping.amr_boxplot import summarize_available

    storage_path = DEFAULT_DATA_DIR / "amr_boxplot_intervals_local.csv"
    return jsonify(summarize_available(storage_path))


@app.route("/api/forecast-boxplot")
def api_forecast_boxplot():
    """คืนกราฟ Boxplot (PNG) จากข้อมูล AMR จริงที่สะสมไว้สำหรับประเภทธุรกิจ (TSIC) หนึ่งรายการ —
    ต่างจาก /api/forecast-shape ตรงที่นี่คือข้อมูลวัดจริง ไม่ใช่เส้นโค้งสมมติ ต้องมีคนอัปโหลด AMR
    จริงของธุรกิจประเภทนี้ไว้ก่อนแล้ว (ผ่าน /api/admin/amr-boxplot/upload) ไม่งั้นคืน 404"""

    from amr_mapping.amr_boxplot import load_intervals_local, render_boxplot_png

    business_type_code = (request.args.get("business_type_code") or "").strip()
    if not business_type_code:
        return jsonify({"error": "invalid_request", "message": "กรุณาระบุประเภทธุรกิจ (TSIC)"}), 400

    storage_path = DEFAULT_DATA_DIR / "amr_boxplot_intervals_local.csv"
    df = load_intervals_local(storage_path, business_type_code)
    if df.empty:
        return jsonify(
            {"error": "not_found", "message": "ยังไม่มีข้อมูล AMR จริงสำหรับประเภทธุรกิจนี้เลย (อัปโหลดได้จากหน้า Admin)"}
        ), 404

    reference = get_reference()
    bt = reference.business_types.get(business_type_code)
    business_type_name = bt.name_th if bt else ""

    try:
        png_bytes = render_boxplot_png(df, business_type_code, business_type_name)
    except ValueError as e:
        return jsonify({"error": "invalid_request", "message": str(e)}), 400

    return app.response_class(png_bytes, mimetype="image/png")


@app.route("/admin")
def admin_page():
    return app.send_static_file("admin.html")


@app.route("/manual")
def manual_page():
    return app.send_static_file("manual.html")


@app.route("/methodology")
def methodology_page():
    return app.send_static_file("methodology.html")


@app.route("/overview")
def overview_page():
    return app.send_static_file("overview.html")


if __name__ == "__main__":
    # use_reloader=False: ปิด auto-restart เวลาไฟล์เปลี่ยน — การค้นหาประเภทธุรกิจ (dbd_lookup.py)
    # รันเป็น background thread ที่เปิด Selenium/Playwright จริง ถ้า reloader restart ตัวเซิร์ฟเวอร์
    # กลางคันจะทำให้ thread ถูกตัดตอน และอาจทำให้ไฟล์ lock ของ webdriver-manager
    # (.wdm-lock-chromedriver-*) ค้างจนรอบถัดไป Selenium ต้องรอ lock จนหมดเวลา (timeout)
    app.run(debug=True, port=5000, use_reloader=False)
