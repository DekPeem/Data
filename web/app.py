"""เว็บแอป No AMR — ค้นหาผู้ใช้ไฟ + ดูผลพยากรณ์โปรไฟล์ P/OP/H

รันด้วย:
    python web/app.py
แล้วเปิดเบราว์เซอร์ที่ http://localhost:5000

⚠️ ข้อมูลลูกค้าในเว็บนี้ (data/reference/customers.csv) เป็นข้อมูล "สมมติ" เพื่อสาธิต
การทำงานเท่านั้น ห้ามใส่ข้อมูลลูกค้าจริงลงไฟล์นี้ เพราะ repo เป็น public — ถ้าจะต่อกับ
ข้อมูลลูกค้าจริง ให้เปลี่ยน data_dir ไปชี้ฐานข้อมูลจริงที่แยกเก็บไว้นอก repo แทน
"""

from __future__ import annotations

import dataclasses
import os
import sys
import threading
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from flask import Flask, jsonify, redirect, request

from amr_mapping import estimate_customer_load, load_reference_data
from amr_mapping.amr_import import import_amr_auto, import_amr_for_business
from amr_mapping.dbd_lookup import find_exact_match, lookup_business_type_for_company
from amr_mapping.loader import (
    DEFAULT_DATA_DIR,
    load_import_log_local,
    save_business_types,
    upsert_business_type,
)
from amr_mapping.mapping import MatchLevel, find_load_curve
from amr_mapping.models import Customer

app = Flask(__name__, static_folder="static", static_url_path="")


def get_reference():
    """โหลดข้อมูลอ้างอิงใหม่ทุกครั้ง (ไฟล์ CSV เล็กมาก โหลดซ้ำไม่แพง) เพื่อให้เห็นข้อมูล
    ล่าสุดทันทีหลังจาก job นำเข้า AMR อัปเดต load_profiles.csv เสร็จ โดยไม่ต้อง restart แอป"""

    return load_reference_data()


# ── Job store สำหรับงานนำเข้า AMR แบบ background (เก็บใน memory พอ เพราะเป็นเครื่องมือ
#    ใช้คนเดียวในเครื่อง ไม่ใช่ multi-user service) ──
_JOBS: dict = {}
_JOBS_LOCK = threading.Lock()

MATCH_LEVEL_LABEL_TH = {
    MatchLevel.EXACT: "ตรงตามธุรกิจและอัตรา (Exact Match)",
    MatchLevel.BUSINESS_ONLY: "ตรงตามประเภทธุรกิจ (ไม่ทราบ/ไม่ตรงอัตรา)",
    MatchLevel.DIVISION_ONLY: "ไม่มีข้อมูลธุรกิจนี้ตรงๆ แต่อยู่ในกลุ่มอุตสาหกรรม (TSIC) เดียวกับที่มีข้อมูล",
    MatchLevel.RATE_ONLY: "ตรงตามประเภทอัตรา (ยังไม่จัดประเภทธุรกิจ)",
    MatchLevel.DEFAULT: "ไม่พบข้อมูลที่ตรงกัน (ใช้ค่ากลาง)",
}


def _customer_to_dict(customer) -> dict:
    return {
        "account_no": customer.account_no,
        "name": customer.name,
        "business_type_code": customer.business_type_code,
        "rate_code": customer.rate_code,
        "contract_kva": customer.contract_kva,
        "has_amr": customer.has_amr,
    }


_NO_CURVE = {"available": False, "day_types": {}, "sample_size": 0}


def _curve_response(reference, business_type_code: str, rate_code: str, scale_factor: float) -> dict:
    """หาเส้นโค้งรายชั่วโมง (exact match กับคู่ business_type_code/rate_code ที่จับคู่ได้
    แล้วจาก find_load_profile) แล้วปรับสเกลด้วย scale_factor เดียวกับที่ใช้กับ P/OP/H
    คืน {"available": False, ...} เฉยๆ ถ้ายังไม่มีข้อมูลเส้นโค้งของคู่นี้เลย (เช่น ยังไม่เคย
    นำเข้า AMR จริงที่มีข้อมูลราย 15 นาทีมาก่อน — ไม่ใช่ error)"""

    curve = find_load_curve(reference.load_curves, business_type_code, rate_code)
    if curve is None:
        return _NO_CURVE

    def scale(v):
        return None if v is None else round(v * scale_factor, 2)

    return {
        "available": True,
        "day_types": {day_type: [scale(v) for v in hours] for day_type, hours in curve.hours.items()},
        "sample_size": curve.sample_size,
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


@app.route("/api/business-types-full")
def api_list_business_types_full():
    """รายชื่อประเภทธุรกิจทั้งหมดแบบละเอียด (รวม TSIC section/division + ว่ามีโปรไฟล์อ้างอิง
    จริงรองรับอยู่แล้วกี่อัตรา) — ใช้โดยตาราง "หมวดหมู่ธุรกิจทั้งหมดในระบบ" ในหน้า Admin เพื่อดูภาพ
    รวมของข้อมูลอ้างอิงทั้งหมดในเครื่องนี้ในที่เดียว ไม่ต้องเปิดไฟล์ CSV ดูเอง"""

    reference = get_reference()
    profiles_by_business: dict = {}
    for p in reference.load_profiles:
        profiles_by_business.setdefault(p.business_type_code, []).append(
            {"rate_code": p.rate_code, "sample_size": p.sample_size}
        )

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
                "profiles": profiles_by_business.get(bt.code, []),
            }
            for bt in reference.business_types.values()
        ]
    )


@app.route("/api/import-log-local")
def api_list_import_log_local():
    """ประวัติการนำเข้า AMR จริงในเครื่องนี้ (ชื่อบริษัท/เลขบัญชีจริง) — อ่านจาก
    import_log_local.csv ซึ่งอยู่ใน .gitignore แล้ว (หลักการเดียวกับ customers_local.csv)
    ไฟล์นี้ไม่บังคับต้องมี คืน list ว่างถ้ายังไม่เคย import แบบ auto มาก่อนเลย"""

    entries = load_import_log_local(DEFAULT_DATA_DIR / "import_log_local.csv")
    return jsonify(list(reversed(entries)))  # ใหม่ล่าสุดขึ้นก่อน


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


@app.route("/api/rate-schedules")
def api_list_rate_schedules():
    """รายชื่อประเภทอัตราทั้งหมด (สำหรับ dropdown ในหน้าพยากรณ์แบบไม่บันทึก)"""

    return jsonify(
        [
            {"code": rs.code, "billing_method": rs.billing_method, "voltage_level": rs.voltage_level, "description": rs.description}
            for rs in get_reference().rate_schedules.values()
        ]
    )


@app.route("/api/load-profile-keys")
def api_list_load_profile_keys():
    """รายการคู่ (ประเภทธุรกิจ, รหัสอัตรา) ที่ "มีโปรไฟล์อ้างอิงจริง" อยู่ใน load_profiles.csv
    เท่านั้น (ไม่รวมแถว DEFAULT/DEFAULT ซึ่งเป็นแค่ค่ากลาง fallback ไม่ใช่ธุรกิจจริง)

    ใช้โดยหน้าพยากรณ์แบบไม่บันทึกข้อมูล เพื่อจำกัดตัวเลือกประเภทธุรกิจ/รหัสอัตราให้เลือกได้
    เฉพาะคู่ที่ "มีข้อมูลจริงรองรับ" เท่านั้น (ตรงตาม exact match เสมอ) แทนที่จะให้พิมพ์/เลือก
    ค่าที่ไม่มีข้อมูลจริงมาคู่กัน แล้วได้ผลลัพธ์แบบ fallback (BUSINESS_ONLY/RATE_ONLY) ซึ่งอาจดู
    เหมือนระบบจับคู่ผิดทั้งที่จริงๆ คือไม่มีข้อมูลของคู่นั้นให้จับคู่แบบตรงเป๊ะได้ตั้งแต่แรก
    """

    return jsonify(
        [
            {"business_type_code": p.business_type_code, "rate_code": p.rate_code, "sample_size": p.sample_size}
            for p in get_reference().load_profiles
            if not (p.business_type_code == "DEFAULT" and p.rate_code == "DEFAULT")
        ]
    )


@app.route("/api/forecast/<path:account_no>")
def api_forecast(account_no: str):
    """ค้นหาผู้ใช้ไฟตามเลขบัญชี แล้วคืนผลพยากรณ์โปรไฟล์ P/OP/H"""

    reference = get_reference()
    customer = next((c for c in reference.customers if c.account_no == account_no), None)
    if customer is None:
        return jsonify({"error": "not_found", "message": f"ไม่พบผู้ใช้ไฟที่เลขบัญชี {account_no}"}), 404

    if customer.has_amr:
        return jsonify(
            {
                "error": "has_amr",
                "message": "ผู้ใช้ไฟรายนี้มีข้อมูล AMR ของตัวเองอยู่แล้ว ไม่จำเป็นต้องพยากรณ์",
                "customer": _customer_to_dict(customer),
            }
        ), 409

    result = estimate_customer_load(customer, reference)
    business_type = reference.business_types.get(result.matched_profile.business_type_code)
    rate_schedule = reference.rate_schedules.get(result.matched_profile.rate_code)

    return jsonify(
        {
            "customer": _customer_to_dict(customer),
            "match": {
                "level": result.match_level.value,
                "level_label_th": MATCH_LEVEL_LABEL_TH.get(result.match_level, result.match_level.value),
                "is_exact": result.match_level == MatchLevel.EXACT,
                "scale_factor": result.scale_factor,
                "warnings": result.warnings,
            },
            "matched_profile": {
                "business_type_code": result.matched_profile.business_type_code,
                "business_type_name": business_type.name_th if business_type else None,
                "rate_code": result.matched_profile.rate_code,
                "rate_description": rate_schedule.description if rate_schedule else None,
                "sample_size": result.matched_profile.sample_size,
                "notes": result.matched_profile.notes,
            },
            "forecast": {
                "demand_kw": result.demand_kw,
                "energy_kwh": result.energy_kwh,
            },
            "curve": _curve_response(
                reference, result.matched_profile.business_type_code, result.matched_profile.rate_code, result.scale_factor
            ),
        }
    )


@app.route("/new-forecast")
def adhoc_forecast_page_redirect():
    """เดิมเป็นหน้าแยก — ตอนนี้รวมเข้าหน้าแรกเป็นแท็บ "พยากรณ์แบบไม่บันทึกข้อมูล" แล้ว
    (ค่าเริ่มต้นของหน้าแรกอยู่แล้ว) คง route นี้ไว้เผื่อมี bookmark/ลิงก์เก่าอ้างถึง"""

    return redirect("/")


@app.route("/api/forecast-adhoc", methods=["POST"])
def api_forecast_adhoc():
    """พยากรณ์โปรไฟล์แบบ ad-hoc จากประเภทธุรกิจ + อัตราที่เลือก/กรอกเองโดยตรง

    ใช้สำหรับกรณีที่ยังไม่มีผู้ใช้ไฟรายนี้อยู่ใน customers.csv/customers_local.csv เลย (เช่น
    อยากลองพิมพ์ชื่อบริษัทจริงดูผลลัพธ์ทันทีในเครื่องตัวเอง โดยไม่ต้องบันทึกชื่อ/เลขบัญชีลง
    ไฟล์ใดๆ) — endpoint นี้จึงตั้งใจ "ไม่รับ" ชื่อบริษัทเป็นพารามิเตอร์เลยด้วยซ้ำ (ชื่อที่ผู้ใช้
    พิมพ์ในฟอร์มจะอยู่แค่ฝั่ง browser/JavaScript เท่านั้น ไม่ถูกส่งมาที่ server, ไม่ถูก log,
    ไม่ถูกเขียนลงดิสก์ที่ไหนทั้งสิ้น) คำนวณแล้วคืนผลลัพธ์กลับไปทันที ไม่มีการบันทึกสถานะใดๆ
    ในหน่วยความจำของ server ด้วย
    """

    body = request.get_json(force=True, silent=True) or {}

    business_type_code = (body.get("business_type_code") or "").strip() or None
    rate_code = (body.get("rate_code") or "").strip() or None
    contract_kva = body.get("contract_kva")
    try:
        contract_kva = float(contract_kva) if contract_kva not in (None, "") else None
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_request", "message": "KVA ตามสัญญาต้องเป็นตัวเลข"}), 400

    if not business_type_code and not rate_code:
        return jsonify(
            {"error": "invalid_request", "message": "กรุณาเลือก/กรอกประเภทธุรกิจ หรือ ประเภทอัตรา อย่างน้อยหนึ่งอย่าง"}
        ), 400

    reference = get_reference()
    # ไม่มี account_no/name จริง — เป็นแค่ตัวแปรชั่วคราวสำหรับคำนวณเท่านั้น ไม่ถูกเก็บที่ไหน
    transient_customer = Customer(
        account_no="",
        name="",
        business_type_code=business_type_code,
        rate_code=rate_code,
        contract_kva=contract_kva,
        has_amr=False,
    )

    result = estimate_customer_load(transient_customer, reference)
    business_type = reference.business_types.get(result.matched_profile.business_type_code)
    rate_schedule = reference.rate_schedules.get(result.matched_profile.rate_code)

    return jsonify(
        {
            "match": {
                "level": result.match_level.value,
                "level_label_th": MATCH_LEVEL_LABEL_TH.get(result.match_level, result.match_level.value),
                "is_exact": result.match_level == MatchLevel.EXACT,
                "scale_factor": result.scale_factor,
                "warnings": result.warnings,
            },
            "matched_profile": {
                "business_type_code": result.matched_profile.business_type_code,
                "business_type_name": business_type.name_th if business_type else None,
                "rate_code": result.matched_profile.rate_code,
                "rate_description": rate_schedule.description if rate_schedule else None,
                "sample_size": result.matched_profile.sample_size,
                "notes": result.matched_profile.notes,
            },
            "forecast": {
                "demand_kw": result.demand_kw,
                "energy_kwh": result.energy_kwh,
            },
            "curve": _curve_response(
                reference, result.matched_profile.business_type_code, result.matched_profile.rate_code, result.scale_factor
            ),
        }
    )


def _run_business_type_lookup_job(job_id: str, company_name: str) -> None:
    """ค้นหาประเภทธุรกิจ (TSIC) ของบริษัทจากชื่อ ผ่าน DBD DataWarehouse (ดู dbd_lookup.py) —
    รันเป็น background job แบบเดียวกับ AMR import เพราะเปิดเบราว์เซอร์จริงใช้เวลาหลายวินาที

    ⚠️ ชื่อบริษัทที่พิมพ์ในหน้านี้ "ถูกส่งออกไปค้นหาที่เว็บ DBD จริง" (ต่างจาก /api/forecast-adhoc
    ที่ไม่ส่งชื่อไปไหนเลย) เพราะไม่มีทางค้นหาบริษัทจากชื่อได้โดยไม่ส่งชื่อไปที่แหล่งข้อมูลนั้น —
    หน้าเว็บต้องแจ้งผู้ใช้ให้ชัดเจนก่อนกดใช้ฟีเจอร์นี้ (ดู index.html)
    """

    def log(msg: str) -> None:
        with _JOBS_LOCK:
            _JOBS[job_id]["logs"].append(msg)

    try:
        results = lookup_business_type_for_company(company_name, log=log)
        reference = get_reference()

        # หา business_type_code ของเราที่ "อยู่ TSIC division เดียวกัน" กับที่เจอจาก DBD (ถ้ามี
        # และเคยตรวจสอบ/บันทึก division_code ไว้แล้วใน business_types.csv) — แค่แนะนำเฉยๆ
        # ผู้ใช้ยังต้องกดยืนยัน/เลือกเองในหน้าเว็บ ไม่ auto-apply ให้ทันที
        division_to_business: dict = {}
        for p in reference.load_profiles:
            bt = reference.business_types.get(p.business_type_code)
            if bt and bt.division_code and bt.division_code not in division_to_business:
                division_to_business[bt.division_code] = p.business_type_code

        candidates = []
        for r in results:
            suggested_code = division_to_business.get(r.tsic_division_code)
            suggested_bt = reference.business_types.get(suggested_code) if suggested_code else None
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
                    "suggested_business_type_name": suggested_bt.name_th if suggested_bt else None,
                }
            )

        exact = find_exact_match(results, company_name)
        exact_index = results.index(exact) if exact is not None else None

        with _JOBS_LOCK:
            _JOBS[job_id]["status"] = "success"
            _JOBS[job_id]["result"] = {
                "query": company_name,
                "candidates": candidates,
                "exact_match_index": exact_index,
            }
    except Exception as e:  # noqa: BLE001 — ต้อง catch ทุก error เพื่อรายงานสถานะ job ให้ถูกต้อง
        with _JOBS_LOCK:
            _JOBS[job_id]["status"] = "error"
            _JOBS[job_id]["error"] = str(e)


@app.route("/api/business-type-lookup", methods=["POST"])
def api_start_business_type_lookup():
    """เริ่ม job ค้นหาประเภทธุรกิจ (TSIC) จากชื่อบริษัท ผ่าน DBD DataWarehouse (background job
    เพราะต้องเปิดเบราว์เซอร์จริง ใช้เวลาหลายวินาที — เหมือน /api/admin/import)"""

    body = request.get_json(force=True, silent=True) or {}
    company_name = (body.get("company_name") or "").strip()
    if not company_name:
        return jsonify({"error": "invalid_request", "message": "กรุณาระบุชื่อบริษัท"}), 400

    job_id = uuid.uuid4().hex
    with _JOBS_LOCK:
        _JOBS[job_id] = {"status": "running", "logs": [], "result": None, "error": None}

    thread = threading.Thread(target=_run_business_type_lookup_job, args=(job_id, company_name), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/api/business-type-lookup/<job_id>")
def api_get_business_type_lookup_status(job_id: str):
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return jsonify({"error": "not_found", "message": "ไม่พบ job นี้"}), 404
        return jsonify(dict(job))


@app.route("/admin")
def admin_page():
    return app.send_static_file("admin.html")


def _run_import_job(job_id: str, username: str, password: str, params: dict) -> None:
    def log(msg: str) -> None:
        with _JOBS_LOCK:
            _JOBS[job_id]["logs"].append(msg)

    def on_profile(info: dict) -> None:
        # เก็บข้อมูลลูกค้าจริงที่สแกนมาได้ (ชื่อ/เลขบัญชี/เลขมิเตอร์) ไว้ใน job แสดงผลในหน้า
        # Admin ของเครื่องนี้เท่านั้น — อยู่ใน memory ของ process ชั่วคราว (หาย
        # เมื่อรีสตาร์ทเซิร์ฟเวอร์) ไม่เคยถูกเขียนลงไฟล์ใดๆ ทั้งสิ้น
        with _JOBS_LOCK:
            _JOBS[job_id]["customer_profile"] = {
                "name": info.get("name") or "",
                "account_no": info.get("account_no") or "",
                "meter_no": info.get("meter_no") or "",
            }

    try:
        if params["mode"] == "auto":
            log("🤖 ไม่ได้ระบุประเภทธุรกิจ/อัตรา — ให้ระบบตรวจจับอัตโนมัติจากหน้าข้อมูลผู้ใช้ไฟของ PEA")
            profile = import_amr_auto(
                username=username,
                password=password,
                start_date=params["start_date"],
                end_date=params["end_date"],
                source_label=params.get("source_label", ""),
                on_profile=on_profile,
                log=log,
            )
        else:
            profile = import_amr_for_business(
                username=username,
                password=password,
                accounts=params["accounts"],
                start_date=params["start_date"],
                end_date=params["end_date"],
                business_type_code=params["business_type_code"],
                rate_code=params["rate_code"],
                contract_kva=params.get("contract_kva"),
                source_label=params.get("source_label", ""),
                billing_method=params.get("billing_method", "TOU"),
                log=log,
            )
        with _JOBS_LOCK:
            _JOBS[job_id]["status"] = "success"
            _JOBS[job_id]["result"] = {
                "business_type_code": profile.business_type_code,
                "rate_code": profile.rate_code,
                "demand_kw": profile.demand_kw,
                "energy_kwh": profile.energy_kwh,
                "sample_size": profile.sample_size,
                "contract_kva_ref": profile.contract_kva_ref,
                "notes": profile.notes,
            }
    except Exception as e:  # noqa: BLE001 — ต้อง catch ทุก error เพื่อรายงานสถานะ job ให้ถูกต้อง
        with _JOBS_LOCK:
            _JOBS[job_id]["status"] = "error"
            _JOBS[job_id]["error"] = str(e)


@app.route("/api/admin/import", methods=["POST"])
def api_start_import():
    """เริ่ม job ดาวน์โหลด + นำเข้า AMR จริงจากเว็บ PEA (รันเป็น background thread)

    username/password รับได้ 2 ทาง (ฟอร์มมีความสำคัญกว่า):
      1. กรอกในฟอร์มเว็บโดยตรง (เหมาะเมื่อมีหลายบัญชี คนละ username/password กัน) —
         ใช้แค่ครั้งเดียวสำหรับ job นี้ ไม่ถูกบันทึกลงดิสก์/log ที่ไหนเลย
      2. ตัวแปรสภาพแวดล้อม PEA_AMR_USERNAME / PEA_AMR_PASSWORD (ใช้เป็นค่า default เมื่อ
         ไม่ได้กรอกในฟอร์ม — สะดวกถ้ามีบัญชีหลักบัญชีเดียวที่ใช้บ่อย)
    """

    body = request.get_json(force=True, silent=True) or {}

    username = (body.get("username") or "").strip() or os.environ.get("PEA_AMR_USERNAME")
    password = body.get("password") or os.environ.get("PEA_AMR_PASSWORD")
    if not username or not password:
        return jsonify(
            {
                "error": "missing_credentials",
                "message": "ยังไม่ได้กรอก username/password ในฟอร์ม และยังไม่ได้ตั้งค่า "
                "PEA_AMR_USERNAME / PEA_AMR_PASSWORD ในเครื่องนี้ด้วย "
                "(ดูวิธีตั้งค่าในไฟล์ README หัวข้อ 'นำเข้า AMR อัตโนมัติผ่านเว็บ')",
            }
        ), 400

    accounts_raw = body.get("accounts") or body.get("account_no") or ""
    accounts = [a.strip() for a in str(accounts_raw).split(",") if a.strip()]
    business_type_code = (body.get("business_type_code") or "").strip()
    rate_code = (body.get("rate_code") or "").strip()
    start_date = (body.get("start_date") or "").strip()
    end_date = (body.get("end_date") or "").strip()

    # ไม่ระบุทั้งประเภทธุรกิจและอัตรา -> โหมดอัตโนมัติ (ตรวจจับจากหน้าข้อมูลผู้ใช้ไฟของ PEA
    # เอง ต้องการแค่ username/password + ช่วงวันที่); ระบุมาอย่างน้อยหนึ่งอย่าง -> โหมดกรอกเอง
    # (แบบเดิม ต้องกรอกให้ครบทั้งคู่ และต้องระบุเลขบัญชีด้วย)
    mode = "auto" if not business_type_code and not rate_code else "manual"

    if mode == "auto":
        missing = [name for name, val in [("start_date", start_date), ("end_date", end_date)] if not val]
    else:
        missing = [
            name
            for name, val in [
                ("accounts", accounts),
                ("business_type_code", business_type_code),
                ("rate_code", rate_code),
                ("start_date", start_date),
                ("end_date", end_date),
            ]
            if not val
        ]
    if missing:
        return jsonify({"error": "invalid_request", "message": f"กรอกข้อมูลไม่ครบ: {', '.join(missing)}"}), 400

    job_id = uuid.uuid4().hex
    with _JOBS_LOCK:
        _JOBS[job_id] = {"status": "running", "logs": [], "result": None, "error": None, "customer_profile": None}

    params = {
        "mode": mode,
        "accounts": accounts,
        "business_type_code": business_type_code,
        "rate_code": rate_code,
        "start_date": start_date,
        "end_date": end_date,
        "contract_kva": body.get("contract_kva"),
        "source_label": body.get("source_label", ""),
        "billing_method": body.get("billing_method", "TOU"),
    }

    thread = threading.Thread(target=_run_import_job, args=(job_id, username, password, params), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/api/admin/import/<job_id>")
def api_get_import_status(job_id: str):
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return jsonify({"error": "not_found", "message": "ไม่พบ job นี้"}), 404
        # คืนค่า copy ตื้นๆ พอ (ไม่มี username/password อยู่ใน job dict อยู่แล้ว)
        return jsonify(dict(job))


if __name__ == "__main__":
    # use_reloader=False: ปิด auto-restart เวลาไฟล์เปลี่ยน — งานนำเข้า AMR รันเป็น
    # background thread ที่ใช้เวลานาน (ดาวน์โหลดหลายเดือน) ถ้า reloader restart ตัวเซิร์ฟเวอร์
    # กลางคันจะทำให้ thread ถูกตัดตอน และอาจทำให้ไฟล์ lock ของ webdriver-manager
    # (.wdm-lock-chromedriver-*) ค้างจนรอบถัดไป Selenium ต้องรอ lock จนหมดเวลา (timeout)
    app.run(debug=True, port=5000, use_reloader=False)
