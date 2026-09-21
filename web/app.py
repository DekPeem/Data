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
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from flask import Flask, jsonify, redirect, request
from werkzeug.utils import secure_filename

from amr_mapping import estimate_customer_load, load_reference_data
from amr_mapping.amr_import import (
    DEFAULT_DOWNLOAD_DIR,
    import_amr_auto,
    import_amr_for_business,
    import_amr_from_files,
)
from amr_mapping.clustering import cluster_business_types, nearest_business_type_by_tsic, rank_business_types_by_tsic
from amr_mapping.dataforthai_lookup import lookup_business_category, suggest_companies_with_fallback
from amr_mapping.dataforthai_lookup import setup_driver as setup_dataforthai_driver
from amr_mapping.dbd_lookup import BlockedByAntiBot, find_exact_match, lookup_business_type_for_company
from amr_mapping.dbd_opendata import fetch_all as fetch_dbd_opendata
from amr_mapping.dbd_opendata import is_db_available as dbd_opendata_is_available
from amr_mapping.dbd_opendata import search_juristic_person
from amr_mapping.keyword_classify import guess_tsic_division
from amr_mapping.loader import (
    DEFAULT_DATA_DIR,
    append_pending_amr_local,
    load_import_log_local,
    load_pending_amr_local,
    load_site_curves_local,
    remove_import_log_local_entry,
    remove_load_curve,
    remove_load_profile,
    remove_pending_amr_local,
    save_business_types,
    save_load_curves,
    save_load_profiles,
    upsert_business_type,
)
from amr_mapping.mapping import UNKNOWN_RATE_CODE, MatchLevel, find_load_curve
from amr_mapping.models import Customer
from amr_mapping.wikipedia_lookup import search_wikipedia_company

app = Flask(__name__, static_folder="static", static_url_path="")

# ไฟล์เก็บรายการ AMR ที่นำเข้าไม่สำเร็จเพราะไม่ทราบประเภทธุรกิจ/รหัสอัตรา — local-only เหมือน
# import_log_local.csv (ดู .gitignore/loader.py)
PENDING_AMR_LOCAL_PATH = DEFAULT_DATA_DIR / "pending_amr_local.csv"

# ข้อความ error ส่วนที่คงที่จาก import_amr_from_files ตอนไม่รู้ประเภทธุรกิจ/รหัสอัตราของบัญชี —
# ใช้แยกแยะว่า error นี้ "รอกรอกภายหลังได้" (ควรบันทึกเป็นรายการ pending) กับ error อื่นๆ ที่ควร
# แจ้งผู้ใช้ตรงๆ (เช่นไฟล์เสียหาย อ่านไม่ได้) ซึ่งบันทึกเป็น pending ไปก็ resolve ไม่ได้อยู่ดี
_UNKNOWN_BUSINESS_TYPE_OR_RATE_ERROR = "ไม่ทราบประเภทธุรกิจ/รหัสอัตราของบัญชีนี้"


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
    MatchLevel.SOLAR_MISMATCH: "ตรงตามธุรกิจและอัตรา แต่ไม่มีข้อมูลของสถานะ Solar ที่ตรงกัน",
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
        "has_solar": customer.has_solar,
    }


_NO_CURVE = {"available": False, "day_types": {}, "sample_size": 0}


def _parse_tri_state_bool(value) -> Optional[bool]:
    """แปลงค่า has_solar ที่รับมาจาก client (JSON body หรือ query string) เป็น tri-state:
    None (ไม่ทราบ/ไม่ระบุ), True, False — รองรับทั้ง JSON boolean จริงและสตริง "true"/"false" """

    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes")


def _curve_response(
    reference, business_type_code: str, rate_code: str, scale_factor: float, has_solar: Optional[bool] = None
) -> dict:
    """หาเส้นโค้งรายชั่วโมง (คู่ business_type_code/rate_code/has_solar ที่จับคู่ได้แล้วจาก
    find_load_profile) แล้วปรับสเกลด้วย scale_factor เดียวกับที่ใช้กับ P/OP/H
    คืน {"available": False, ...} เฉยๆ ถ้ายังไม่มีข้อมูลเส้นโค้งของคู่นี้เลย (เช่น ยังไม่เคย
    นำเข้า AMR จริงที่มีข้อมูลราย 15 นาทีมาก่อน — ไม่ใช่ error)"""

    curve = find_load_curve(reference.load_curves, business_type_code, rate_code, has_solar=has_solar)
    if curve is None:
        return _NO_CURVE

    def scale(v):
        return None if v is None else round(v * scale_factor, 2)

    return {
        "available": True,
        "day_types": {day_type: [scale(v) for v in hours] for day_type, hours in curve.hours.items()},
        "sample_size": curve.sample_size,
    }


def _estimate_result_to_dict(result, reference) -> dict:
    """แปลง ForecastResult เป็น dict สำหรับตอบกลับ JSON — โครงสร้างเดียวกับที่เดิมเขียนซ้ำอยู่ 2
    จุด (/api/forecast/<account_no> และ /api/forecast-adhoc) ดึงมารวมไว้ที่เดียว เพื่อให้จุดที่ 3
    (พยากรณ์อัตโนมัติหลังค้นหาประเภทธุรกิจใน _run_business_type_lookup_job) เรียกใช้ซ้ำได้โดยไม่
    ต้อง copy โครงสร้าง JSON มาเขียนใหม่อีกรอบ"""

    business_type = reference.business_types.get(result.matched_profile.business_type_code)
    rate_schedule = reference.rate_schedules.get(result.matched_profile.rate_code)

    return {
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
            "has_solar": result.matched_profile.has_solar,
        },
        "forecast": {
            "demand_kw": result.demand_kw,
            "energy_kwh": result.energy_kwh,
        },
        "curve": _curve_response(
            reference,
            result.matched_profile.business_type_code,
            result.matched_profile.rate_code,
            result.scale_factor,
            has_solar=result.matched_profile.has_solar,
        ),
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
    รวมของข้อมูลอ้างอิงทั้งหมดในเครื่องนี้ในที่เดียว ไม่ต้องเปิดไฟล์ CSV ดูเอง

    profiles[].has_curve บอกว่าคู่ธุรกิจ+อัตรา+has_solar นั้นมีข้อมูลกราฟรายชั่วโมงจริง
    (load_curves.csv — มาจาก AMR ที่นำเข้าจริงเท่านั้น) หรือเป็นแค่แถว placeholder ใน
    load_profiles.csv ที่มีแค่ตัวเลขเฉลี่ย P/OP/H แต่ไม่มีกราฟให้ดู — ใช้กรองในหน้า Admin

    ธุรกิจ+อัตราคู่เดียวกันอาจมีโปรไฟล์แยกกัน 2 แถว (ติด Solar / ไม่ติด Solar) เพราะ has_solar
    เป็นส่วนหนึ่งของ key อ้างอิง — profiles[].has_solar บอกว่าแถวนั้นเป็นแบบไหน"""

    reference = get_reference()
    profiles_by_business: dict = {}
    for p in reference.load_profiles:
        has_curve = (
            find_load_curve(reference.load_curves, p.business_type_code, p.rate_code, has_solar=p.has_solar)
            is not None
        )
        profiles_by_business.setdefault(p.business_type_code, []).append(
            {
                "rate_code": p.rate_code,
                "sample_size": p.sample_size,
                "has_curve": has_curve,
                "has_solar": p.has_solar,
            }
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


@app.route("/api/admin/import-log-local", methods=["DELETE"])
def api_delete_import_log_local_entry():
    """ลบ 1 แถวในประวัติการนำเข้า (import_log_local.csv) ทิ้ง — ใช้ล้างประวัติที่นำเข้าผิดบัญชี/
    ผิดประเภทธุรกิจไปแล้ว ไฟล์นี้เป็นแค่ log สำหรับดูย้อนหลังเท่านั้น ไม่กระทบ load_profiles.csv/
    load_curves.csv ที่ใช้พยากรณ์จริงเลย (ถ้าต้องการลบตัวที่ใช้พยากรณ์จริงด้วย ใช้
    /api/admin/load-profile/<code>/<rate_code> แยกต่างหาก)"""

    body = request.get_json(silent=True) or {}
    imported_at = (body.get("imported_at") or "").strip()
    account_no = (body.get("account_no") or "").strip()
    if not imported_at or not account_no:
        return jsonify({"error": "invalid_request", "message": "ต้องระบุ imported_at และ account_no"}), 400

    removed = remove_import_log_local_entry(imported_at, account_no, DEFAULT_DATA_DIR / "import_log_local.csv")
    if not removed:
        return jsonify({"error": "not_found", "message": "ไม่พบรายการนี้ในประวัติ"}), 404
    return jsonify({"ok": True})


@app.route("/api/admin/site-curve/<account_no>")
def api_get_site_curve(account_no: str):
    """เส้นโค้งรายชั่วโมงดิบของไซต์ (บัญชี) หนึ่งรายโดยเฉพาะ — อ่านจาก site_curves_local.csv
    (ไฟล์ local-only มีชื่อบริษัท/เลขบัญชีจริง อยู่ใน .gitignore แล้ว) ต่างจาก
    /api/admin/curve/<code>/<rate_code> ซึ่งเป็นค่าเฉลี่ยรวมของทุกไซต์แบบ anonymized —
    endpoint นี้ให้กราฟของไซต์นี้ไซต์เดียวเท่านั้น ใช้กดดูแยกแต่ละบริษัท/ไซต์ในหน้า Admin

    คืน {"available": False, ...} เฉยๆ ถ้ายังไม่มีกราฟแยกของไซต์นี้เลย (เช่น นำเข้าไว้ก่อนฟีเจอร์
    นี้จะมี หรือนำเข้าด้วยโหมดกรอกเองซึ่งไม่ทราบชื่อบริษัทจริง) ไม่ใช่ error"""

    entries = load_site_curves_local(DEFAULT_DATA_DIR / "site_curves_local.csv")
    entry = next((e for e in entries if e["account_no"] == account_no), None)
    if entry is None:
        return jsonify(_NO_CURVE)
    return jsonify({"available": True, "day_types": entry["hours"], "sample_size": entry["sample_size"]})


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


@app.route("/api/admin/curve/<code>/<rate_code>")
def api_admin_curve(code: str, rate_code: str):
    """เส้นโค้งรายชั่วโมงดิบ (ไม่สเกลตาม KVA ของลูกค้ารายใดรายหนึ่ง — scale_factor=1.0) ของคู่
    ประเภทธุรกิจ+รหัสอัตรา(+has_solar) หนึ่งคู่ ใช้ในหน้า Admin เพื่อดูว่ากลุ่มนี้มีรูปแบบการใช้ไฟ
    เป็นแบบไหนก่อนจะเอาไปใช้พยากรณ์จริง (ไม่ใช่ส่วนพยากรณ์ - แค่ดูข้อมูลที่นำเข้าไว้)

    ?has_solar=true|false (ไม่บังคับ) เลือกเส้นโค้งที่ติด/ไม่ติด Solar ของคู่นี้โดยเฉพาะ — ไม่ใส่
    เลยจะได้เส้นที่ไม่ติด Solar ก่อนถ้ามี (พฤติกรรมเดิมก่อนมีมิตินี้)"""

    reference = get_reference()
    has_solar = _parse_tri_state_bool(request.args.get("has_solar"))
    return jsonify(_curve_response(reference, code, rate_code, scale_factor=1.0, has_solar=has_solar))


@app.route("/api/admin/load-profile/<code>/<rate_code>", methods=["DELETE"])
def api_delete_load_profile(code: str, rate_code: str):
    """ลบโปรไฟล์ + เส้นโค้งอ้างอิงของคู่ (business_type_code, rate_code, has_solar) ทิ้งจาก
    load_profiles.csv/load_curves.csv — ใช้ตอนนำเข้าผิดบัญชี/ผิดประเภทธุรกิจไปแล้ว (เช่นเลือก
    ประเภทธุรกิจผิดตอน resolve รายการรอทราบอัตรา) ต้องการล้างข้อมูลที่ผิดออกก่อน ไฟล์ AMR ดิบที่
    เคยนำเข้าไม่ได้ถูกลบไปด้วย (ยังอยู่ใน amr_downloads/) นำเข้าใหม่ให้ถูกต้องได้โดยไม่ต้องอัปโหลด
    ไฟล์ซ้ำถ้ายังหา path เดิมเจอ

    ?has_solar=true|false (ไม่บังคับ) ระบุว่าจะลบคู่ที่ติด/ไม่ติด Solar — ไม่ใส่เลยถือว่าไม่ติด Solar
    (พฤติกรรมเดิมเหมือน /api/admin/curve)"""

    has_solar = bool(_parse_tri_state_bool(request.args.get("has_solar")))
    reference = get_reference()
    updated_profiles, profile_removed = remove_load_profile(reference.load_profiles, code, rate_code, has_solar)
    updated_curves, curve_removed = remove_load_curve(reference.load_curves, code, rate_code, has_solar)
    if not profile_removed and not curve_removed:
        return jsonify({"error": "not_found", "message": "ไม่พบโปรไฟล์/เส้นโค้งของคู่ประเภทธุรกิจ+อัตรานี้"}), 404

    save_load_profiles(updated_profiles, DEFAULT_DATA_DIR / "load_profiles.csv")
    save_load_curves(updated_curves, DEFAULT_DATA_DIR / "load_curves.csv")
    return jsonify({"ok": True})


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
            {
                "business_type_code": p.business_type_code,
                "rate_code": p.rate_code,
                "sample_size": p.sample_size,
                "has_solar": p.has_solar,
            }
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
    return jsonify({"customer": _customer_to_dict(customer), **_estimate_result_to_dict(result, reference)})


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
    has_solar = _parse_tri_state_bool(body.get("has_solar"))
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
        has_solar=has_solar,
    )

    result = estimate_customer_load(transient_customer, reference)
    return jsonify(_estimate_result_to_dict(result, reference))


def _run_dataforthai_fallback(company_name: str, log) -> Optional[dict]:
    """เว็บ DBD โดนบล็อกการเข้าถึงอัตโนมัติ (ดู dbd_lookup.BlockedByAntiBot — ยืนยันจากผู้ใช้จริง
    ว่าเจอหน้า "Request unsuccessful. Incapsula incident ID: ...") — ลอง fallback ไปที่
    dataforthai.com แทน (เว็บบุคคลที่สามที่นำข้อมูลจดทะเบียนธุรกิจสาธารณะมาแสดงต่ออีกที ไม่ใช่
    แหล่งข้อมูลทางการของ DBD เอง) ดู dataforthai_lookup.py

    ⚠️ ผลลัพธ์จากเว็บนี้เป็น "หมวดธุรกิจ" แบบข้อความอิสระ (เช่น "ร้านสะดวกซื้อ/มินิมาร์ท") ไม่ใช่
    รหัส TSIC มาตรฐานแบบที่ DBD ให้มา จึงจับคู่กับ business_type_code ของเราในระบบโดยอัตโนมัติ
    ไม่ได้ (ไม่มีรหัสให้เทียบ) — ให้แค่ข้อความประกอบการตัดสินใจเลือกประเภทธุรกิจเองเท่านั้น

    ⚠️ ขั้นตอนคลิกเลือก suggestion + อ่านหน้าโปรไฟล์ยังไม่เคยทดสอบกับเว็บจริง (ดู docstring ของ
    dataforthai_lookup.lookup_business_category) คืน None ได้ถ้าล้มเหลว ไม่ raise ทำให้ job หลัก
    ล้มไปด้วย เพราะเป็นแค่ทางเลือกเสริมตอน DBD ใช้ไม่ได้อยู่แล้ว

    ยืนยันจากผู้ใช้จริง: เรียก /api/suggest ตรงๆ ด้วย HTTP GET ธรรมดา (ไม่ผ่านเบราว์เซอร์จริง)
    ไม่เจอผลลัพธ์เลยแม้แต่คำค้นหาสั้นๆ ที่เคยเห็นเองในเบราว์เซอร์จริงว่ามี suggestion จริง — จึง
    "ไม่ใช้ผลจาก HTTP request ตรงๆ เป็นเงื่อนไขตัดสินใจว่าจะลอง Selenium ต่อหรือไม่" อีกต่อไป (เดิม
    เคยเขียนไว้แบบนั้น กลายเป็นบล็อกไม่ให้ไปถึงขั้น Selenium เลยทั้งที่ Selenium อาจจะเจอก็ได้ เพราะ
    เป็นการพิมพ์ผ่านเบราว์เซอร์จริงเหมือนที่ผู้ใช้ทำเอง) — ไปลอง lookup_business_category (Selenium
    เปิดเว็บจริง พิมพ์ค้นหา คลิกเลือก อ่านหน้า) ตรงๆ เลย ส่วนผล suggest_companies_with_fallback
    เก็บไว้แค่เป็นข้อมูลประกอบ (รายชื่อใกล้เคียง) เท่านั้น ไม่ใช้ตัดสินใจว่าจะหยุดหรือไปต่อ"""

    log("🔁 ลอง fallback ไปที่ dataforthai.com (เว็บบุคคลที่สาม ไม่ใช่แหล่งข้อมูลทางการของ DBD) ด้วยเบราว์เซอร์จริง")

    category = None
    try:
        driver = setup_dataforthai_driver()
        try:
            category = lookup_business_category(driver, company_name, log=log)
        finally:
            driver.quit()
    except Exception as e:  # noqa: BLE001 — fallback เสริม ล้มแล้วต้องไม่ทำให้ job หลักพังไปด้วย
        log(f"⚠️ ดึงหมวดธุรกิจจาก dataforthai.com ไม่สำเร็จ: {e}")

    # suggest_companies เป็นแค่ HTTP request ธรรมดา (ไม่ผ่านเบราว์เซอร์จริง) เก็บไว้แค่เป็นข้อมูล
    # ประกอบเพิ่มเติมเฉยๆ (รายชื่อใกล้เคียง) — ล้มเหลวได้โดยไม่กระทบผลหลักจาก Selenium ข้างบน
    suggestions = suggest_companies_with_fallback(company_name, log=log)

    if not category and not suggestions:
        log("⚠️ ไม่พบข้อมูลใดๆ จาก dataforthai.com เลยทั้งสองทาง")
        return None

    return {
        "source": "dataforthai",
        "candidates": [{"label": s.label, "value": s.value} for s in suggestions],
        "business_category": category,
    }


def _build_division_to_business(reference) -> dict:
    """หา business_type_code ของเราที่ "อยู่ TSIC division เดียวกัน" กับ division ที่เจอจาก DBD
    (ถ้ามีและเคยตรวจสอบ/บันทึก division_code ไว้แล้วใน business_types.csv)"""

    division_to_business: dict = {}
    for p in reference.load_profiles:
        bt = reference.business_types.get(p.business_type_code)
        if bt and bt.division_code and bt.division_code not in division_to_business:
            division_to_business[bt.division_code] = p.business_type_code
    return division_to_business


def _suggest_business_type_for_division(
    division_code: Optional[str], division_to_business: dict, reference, clusters
) -> tuple:
    """คืน (suggested_code, suggested_name, is_approximate, explanation) จาก TSIC division_code
    — ใช้ร่วมกันทั้งผลจาก DBD DataWarehouse โดยตรง และผลจากฐานข้อมูล DBD Open Data ในเครื่อง
    (ทั้งคู่มี division code ติดมาด้วยเหมือนกัน) ดู clustering.nearest_business_type_by_tsic
    เหตุผลละเอียดของการจับคู่แบบผ่อนลง (section เดียวกัน / ตัวแทนกลุ่มรูปแบบการใช้ไฟ)"""

    suggested_code = division_to_business.get(division_code) if division_code else None
    approximate_match = None
    if not suggested_code and division_code:
        approximate_match = nearest_business_type_by_tsic(None, division_code, reference, clusters=clusters)
        if approximate_match:
            suggested_code = approximate_match.business_type_code
    suggested_bt = reference.business_types.get(suggested_code) if suggested_code else None
    return (
        suggested_code,
        suggested_bt.name_th if suggested_bt else None,
        approximate_match is not None,
        approximate_match.explanation_th if approximate_match else None,
    )


def _run_business_type_lookup_job(
    job_id: str,
    company_name: str,
    rate_code: Optional[str] = None,
    contract_kva: Optional[float] = None,
    has_solar: Optional[bool] = None,
) -> None:
    """ค้นหาประเภทธุรกิจ (TSIC) ของบริษัทจากชื่อ ผ่าน DBD DataWarehouse (ดู dbd_lookup.py) —
    รันเป็น background job แบบเดียวกับ AMR import เพราะเปิดเบราว์เซอร์จริงใช้เวลาหลายวินาที

    ⚠️ ชื่อบริษัทที่พิมพ์ในหน้านี้ "ถูกส่งออกไปค้นหาที่เว็บ DBD จริง" (ต่างจาก /api/forecast-adhoc
    ที่ไม่ส่งชื่อไปไหนเลย) เพราะไม่มีทางค้นหาบริษัทจากชื่อได้โดยไม่ส่งชื่อไปที่แหล่งข้อมูลนั้น —
    หน้าเว็บต้องแจ้งผู้ใช้ให้ชัดเจนก่อนกดใช้ฟีเจอร์นี้ (ดู index.html)

    rate_code/contract_kva/has_solar (ถ้าผู้ใช้กรอกมาพร้อมชื่อบริษัทในฟอร์มเดียวกัน) ใช้พยากรณ์
    ต่อให้อัตโนมัติทันทีหลังจับคู่ประเภทธุรกิจได้ (ดูส่วน primary_index ด้านล่าง) — ผู้ใช้จึงได้ผล
    พยากรณ์ทันทีโดยไม่ต้องกดยืนยัน/เลือกประเภทธุรกิจเองอีกขั้นตอนหนึ่ง ถ้าจับคู่ได้แบบไม่กำกวม
    """

    def log(msg: str) -> None:
        with _JOBS_LOCK:
            _JOBS[job_id]["logs"].append(msg)

    reference = get_reference()
    division_to_business = _build_division_to_business(reference)
    # ถ้าไม่มี division ตรงเป๊ะเลย ลองใช้การจับคู่แบบผ่อนลง (section เดียวกัน หรือถ้าไม่มีเลย
    # ใช้ตัวแทนของกลุ่มรูปแบบการใช้ไฟที่พบบ่อยที่สุด) แทนที่จะปล่อยให้ผู้ใช้เลือกเองทันที — ใช้ร่วมกัน
    # ทั้งผลจาก DBD DataWarehouse โดยตรง (try ข้างล่าง) และผลจากฐานข้อมูล DBD Open Data ในเครื่อง
    # (except BlockedByAntiBot ข้างล่าง) จึงคำนวณไว้ครั้งเดียวตรงนี้ก่อนแยกสองเส้นทาง
    clusters = cluster_business_types(reference)

    try:
        results = lookup_business_type_for_company(company_name, log=log)

        candidates = []
        for r in results:
            suggested_code, suggested_name, is_approximate, explanation = _suggest_business_type_for_division(
                r.tsic_division_code, division_to_business, reference, clusters
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

        exact = find_exact_match(results, company_name)
        exact_index = results.index(exact) if exact is not None else None

        # เลือก "บริษัทหลัก" ที่จะใช้พยากรณ์อัตโนมัติทันที: ถ้าเจอชื่อตรงเป๊ะ (exact) ใช้ตัวนั้น
        # เสมอ — มั่นใจได้ว่าเป็นบริษัทเดียวกับที่พิมพ์มา ถ้าไม่เจอชื่อตรงเป๊ะแต่ค้นหาแล้วได้ผลลัพธ์
        # แค่รายการเดียว ก็ถือว่าเป็นบริษัทเดียวกันได้อย่างมั่นใจพอเช่นกัน (เช่น พิมพ์ชื่อคลาดเคลื่อน
        # จากที่ DBD บันทึกไว้เล็กน้อย) ถ้ามีหลายรายการและไม่มีตัวไหนตรงชื่อเป๊ะเลย ถือว่า "กำกวม"
        # (อาจเป็นคนละบริษัทกับที่ตั้งใจ) — ยังคงพยากรณ์จากตัวแรกให้ดูเป็นตัวอย่างทันที (ผู้ใช้เลือก
        # flow แบบ auto ทุกอย่างไว้แล้ว) แต่ติดธง primary_is_ambiguous ไว้ให้หน้าเว็บเตือนผู้ใช้ให้
        # ตรวจสอบ/เลือกจาก candidates เองแทนถ้าผลที่ auto เลือกมาไม่ใช่บริษัทที่ต้องการจริงๆ
        primary_index: Optional[int] = None
        primary_is_ambiguous = False
        if exact_index is not None:
            primary_index = exact_index
        elif len(results) == 1:
            primary_index = 0
        elif len(results) > 1:
            primary_index = 0
            primary_is_ambiguous = True

        # พยากรณ์อัตโนมัติทันทีถ้าเลือกบริษัทหลักได้แบบไม่กำกวม (หรือกำกวมแต่ยังพอมีตัวอย่างให้ดู)
        # และจับคู่ประเภทธุรกิจได้ (suggested_business_type_code ไม่ใช่ None) — ใช้ rate_code/
        # contract_kva/has_solar ที่ผู้ใช้กรอกมาพร้อมชื่อบริษัท (ถ้ามี) เหมือน /api/forecast-adhoc
        # ทุกอย่าง เพียงแต่ไม่ต้องให้ผู้ใช้กดยืนยัน/เลือกประเภทธุรกิจเองอีกรอบ
        forecast = None
        if primary_index is not None:
            suggested_code = candidates[primary_index]["suggested_business_type_code"]
            if suggested_code:
                transient_customer = Customer(
                    account_no="",
                    name=results[primary_index].juristic_name,
                    business_type_code=suggested_code,
                    rate_code=rate_code,
                    contract_kva=contract_kva,
                    has_amr=False,
                    has_solar=has_solar,
                )
                try:
                    forecast_result = estimate_customer_load(transient_customer, reference)
                    forecast = _estimate_result_to_dict(forecast_result, reference)
                except Exception as forecast_error:  # noqa: BLE001 — พยากรณ์อัตโนมัติล้มไม่ควรทำให้
                    # job หลัก (ที่ได้รายชื่อ/ประเภทธุรกิจมาแล้ว) กลายเป็น error ไปด้วย ผู้ใช้ยังเลือก
                    # ประเภทธุรกิจ/พยากรณ์เองต่อผ่าน /api/forecast-adhoc ได้ตามปกติ
                    log(f"⚠️ พยากรณ์อัตโนมัติไม่สำเร็จ: {forecast_error}")

        with _JOBS_LOCK:
            _JOBS[job_id]["status"] = "success"
            _JOBS[job_id]["result"] = {
                "query": company_name,
                "candidates": candidates,
                "exact_match_index": exact_index,
                "blocked": False,
                "fallback": None,
                "primary_index": primary_index,
                "primary_is_ambiguous": primary_is_ambiguous,
                "forecast": forecast,
            }
    except BlockedByAntiBot as e:
        log(f"🚫 {e}")
        fallback = None
        try:
            fallback = _run_dataforthai_fallback(company_name, log)
        except Exception as fallback_error:  # noqa: BLE001 — fallback ล้มก็ไม่ควรทำให้ job ทั้งหมดกลายเป็น error
            log(f"⚠️ fallback ไป dataforthai.com ก็ไม่สำเร็จเช่นกัน: {fallback_error}")

        # ทางเลือกสุดท้าย: ค้นจากฐานข้อมูล DBD Open Data ที่ดึงมาเก็บไว้ในเครื่องแล้ว (ถ้ามี — ดู
        # dbd_opendata.py) เร็วเพราะไม่ต้องต่อเน็ต แต่ครอบคลุมแค่บริษัทที่ "ตั้งใหม่/เลิกกิจการ" ใน
        # ช่วงที่เคยดึงมาเท่านั้น ไม่ใช่ทะเบียนเต็ม — ต้องบอกข้อจำกัดนี้ในผลลัพธ์เสมอ ไม่ใช่แค่คืนค่า
        # ว่างเงียบๆ ถ้าไม่มีฐานข้อมูลนี้เลย (ยังไม่เคยกดดึงข้อมูล)
        dbd_opendata_matches = []
        dbd_opendata_exact_index = None
        if dbd_opendata_is_available():
            log("🔁 ลองค้นจากฐานข้อมูล DBD Open Data ที่เคยดึงมาเก็บในเครื่องแล้ว (ค้นออฟไลน์)")
            try:
                dbd_opendata_matches = search_juristic_person(company_name, limit=10)
                log(f"✅ พบ {len(dbd_opendata_matches)} รายการในฐานข้อมูล DBD Open Data")

                # ข้อมูล DBD Open Data มี "รหัสวัตถุประสงค์" ติดมาด้วย (เลข 5 หลัก 2 หลักแรกคือ TSIC
                # division ตามมาตรฐานเดียวกับที่ DBD DataWarehouse ใช้) จึงจับคู่ประเภทธุรกิจใน
                # ระบบเราได้แบบเดียวกับผลจาก DBD DataWarehouse โดยตรง (ดู _suggest_business_type_
                # for_division) — ทำให้พยากรณ์อัตโนมัติได้แม้ตอน DBD DataWarehouse บล็อกอยู่ก็ตาม
                normalized_query = company_name.strip().lower()
                for i, m in enumerate(dbd_opendata_matches):
                    purpose_code = (m.get("purpose_code") or "").strip()
                    division_code = purpose_code[:2] if len(purpose_code) >= 2 and purpose_code[:2].isdigit() else None
                    suggested_code, suggested_name, is_approximate, explanation = _suggest_business_type_for_division(
                        division_code, division_to_business, reference, clusters
                    )
                    m["tsic_code"] = purpose_code
                    m["tsic_name_th"] = m.get("purpose") or ""
                    m["suggested_business_type_code"] = suggested_code
                    m["suggested_business_type_name"] = suggested_name
                    m["suggested_is_approximate"] = is_approximate
                    m["suggested_explanation"] = explanation
                    if dbd_opendata_exact_index is None and (m.get("name") or "").strip().lower() == normalized_query:
                        dbd_opendata_exact_index = i
            except Exception as opendata_error:  # noqa: BLE001
                log(f"⚠️ ค้นจากฐานข้อมูล DBD Open Data ไม่สำเร็จ: {opendata_error}")
        else:
            log("ℹ️ ยังไม่เคยดึงฐานข้อมูล DBD Open Data มาเก็บในเครื่องเลย (ดึงได้จากหน้า Admin)")

        # ช่องทางฟรีเพิ่มเติม: Wikipedia ภาษาไทย (ดู wikipedia_lookup.py) — ครอบคลุมเฉพาะบริษัทใหญ่/
        # มีชื่อเสียงเท่านั้น แต่บังเอิญเป็นกลุ่มเดียวกับที่ฐานข้อมูล DBD Open Data ด้านบนมักหาไม่เจอ
        # พอดี (บริษัทเก่า ไม่ใช่ตั้งใหม่) จึงช่วยเติมเต็มจุดที่ยังขาดได้แบบไม่มีค่าใช้จ่าย — คืนแค่
        # ข้อความอิสระเหมือน dataforthai's business_category ไม่ใช่รหัส TSIC จึงจับคู่อัตโนมัติไม่ได้
        wikipedia_result = None
        try:
            wp = search_wikipedia_company(company_name, log=log)
            if wp:
                wikipedia_result = {"title": wp.title, "summary": wp.summary, "url": wp.url}

                # ลองเดาประเภทธุรกิจจากคำสำคัญในข้อความ Wikipedia (ดู keyword_classify.py) —
                # ไม่ใช่รหัส TSIC จริง แค่จับคำตรงตัว จึงต้องบอกผู้ใช้ชัดเจนเสมอว่าเป็นการเดา
                # (ดู guessed_keyword) ไม่ใช่ข้อมูลทางการเหมือนผลจาก DBD DataWarehouse/Open Data
                guess = guess_tsic_division(f"{wp.title} {wp.summary}")
                if guess:
                    guessed_division_code, guessed_keyword = guess
                    log(f"🔤 เดาประเภทธุรกิจจากคำว่า '{guessed_keyword}' ในข้อความ Wikipedia")
                    suggested_code, suggested_name, is_approximate, explanation = _suggest_business_type_for_division(
                        guessed_division_code, division_to_business, reference, clusters
                    )
                    wikipedia_result["guessed_keyword"] = guessed_keyword
                    wikipedia_result["suggested_business_type_name"] = suggested_name
                    wikipedia_result["suggested_is_approximate"] = is_approximate
                    wikipedia_result["suggested_explanation"] = explanation

                    if is_approximate:
                        # ไม่มั่นใจพอ (แค่เดาแบบประมาณการ) — ไม่ตั้งค่า/พยากรณ์ให้อัตโนมัติแบบเงียบๆ
                        # (เคยเจอเคสจริงที่เดาไปโดนธุรกิจคนละแบบเลย เช่น ค้าปลีกไปจับกับการผลิต
                        # กระดาษ) ให้แสดงรายการอันดับ 1/2/3 ที่ใกล้เคียงที่สุดแทน ให้ผู้ใช้เลือกเอง
                        suggested_code = None
                        ranked = rank_business_types_by_tsic(
                            None, guessed_division_code, reference, clusters=clusters, limit=3
                        )
                        wikipedia_result["ranked_candidates"] = [
                            {
                                "business_type_code": m.business_type_code,
                                "business_type_name": (
                                    reference.business_types[m.business_type_code].name_th
                                    if m.business_type_code in reference.business_types
                                    else m.business_type_code
                                ),
                                "match_basis": m.match_basis,
                                "explanation": m.explanation_th,
                            }
                            for m in ranked
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
                "fallback": fallback,
                "dbd_opendata_matches": dbd_opendata_matches,
                "dbd_opendata_available": dbd_opendata_is_available(),
                "dbd_opendata_exact_match_index": dbd_opendata_exact_index,
                "wikipedia_result": wikipedia_result,
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

    # พารามิเตอร์พยากรณ์เสริม (ไม่บังคับ) — ถ้าผู้ใช้กรอกมาพร้อมชื่อบริษัทในฟอร์มเดียวกัน จะถูกใช้
    # พยากรณ์ต่ออัตโนมัติทันทีหลังจับคู่ประเภทธุรกิจได้ (ดู _run_business_type_lookup_job) ไม่กรอก
    # มาก็ยังพยากรณ์ได้ตามปกติ เพียงแต่ scale_factor จะเป็น 1.0 (ไม่ปรับตาม KVA) และไม่กรองตาม Solar
    rate_code = (body.get("rate_code") or "").strip() or None
    has_solar = _parse_tri_state_bool(body.get("has_solar"))
    contract_kva = body.get("contract_kva")
    try:
        contract_kva = float(contract_kva) if contract_kva not in (None, "") else None
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_request", "message": "KVA ตามสัญญาต้องเป็นตัวเลข"}), 400

    job_id = uuid.uuid4().hex
    with _JOBS_LOCK:
        _JOBS[job_id] = {"status": "running", "logs": [], "result": None, "error": None}

    thread = threading.Thread(
        target=_run_business_type_lookup_job,
        args=(job_id, company_name, rate_code, contract_kva, has_solar),
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


def _run_dbd_opendata_fetch_job(job_id: str, start_year: int, start_month: int) -> None:
    """ดึงข้อมูล DBD Open Data (นิติบุคคลตั้งใหม่/เลิกกิจการรายเดือน) มาเก็บเป็นฐานข้อมูลในเครื่อง
    (ดู dbd_opendata.py) — รันเป็น background job เพราะดึงทีละเดือนหลายปีอาจใช้เวลานาน"""

    def log(msg: str) -> None:
        with _JOBS_LOCK:
            _JOBS[job_id]["logs"].append(msg)

    try:
        summary = fetch_dbd_opendata(start_year=start_year, start_month=start_month, log=log)
        with _JOBS_LOCK:
            _JOBS[job_id]["status"] = "success"
            _JOBS[job_id]["result"] = summary
    except Exception as e:  # noqa: BLE001 — ต้อง catch ทุก error เพื่อรายงานสถานะ job ให้ถูกต้อง
        with _JOBS_LOCK:
            _JOBS[job_id]["status"] = "error"
            _JOBS[job_id]["error"] = str(e)


@app.route("/api/admin/dbd-opendata/status")
def api_dbd_opendata_status():
    return jsonify({"available": dbd_opendata_is_available()})


@app.route("/api/admin/dbd-opendata/fetch", methods=["POST"])
def api_start_dbd_opendata_fetch():
    """เริ่ม job ดึงข้อมูล DBD Open Data มาเก็บในเครื่อง (background job — ดู
    _run_dbd_opendata_fetch_job) ค่าเริ่มต้นดึงตั้งแต่ปี 2020 จนถึงเดือนปัจจุบัน"""

    body = request.get_json(force=True, silent=True) or {}
    try:
        start_year = int(body.get("start_year") or 2020)
        start_month = int(body.get("start_month") or 1)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_request", "message": "ปี/เดือนเริ่มต้นต้องเป็นตัวเลข"}), 400

    job_id = uuid.uuid4().hex
    with _JOBS_LOCK:
        _JOBS[job_id] = {"status": "running", "logs": [], "result": None, "error": None}

    thread = threading.Thread(
        target=_run_dbd_opendata_fetch_job, args=(job_id, start_year, start_month), daemon=True
    )
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/api/admin/dbd-opendata/fetch/<job_id>")
def api_get_dbd_opendata_fetch_status(job_id: str):
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return jsonify({"error": "not_found", "message": "ไม่พบ job นี้"}), 404
        return jsonify(dict(job))


@app.route("/admin")
def admin_page():
    return app.send_static_file("admin.html")


@app.route("/manual")
def manual_page():
    return app.send_static_file("manual.html")


@app.route("/methodology")
def methodology_page():
    return app.send_static_file("methodology.html")


@app.route("/pending-amr")
def pending_amr_page():
    return app.send_static_file("pending_amr.html")


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
                has_solar=params.get("has_solar", False),
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
                has_solar=params.get("has_solar", False),
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
                "has_solar": profile.has_solar,
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

    # เช็คความสมเหตุสมผลของช่วงวันที่ก่อนเปิด Selenium session จริง — เคยเจอเคสที่ผู้ใช้พิมพ์ปีใน
    # ช่อง date picker ไม่ครบ 4 หลัก (เช่น "25" แทน "2025") ทำให้ได้ช่วงวันที่ผิดเพี้ยนมาก (เช่น
    # ปี 0025) ส่งไปให้เว็บ PEA แล้วเว็บนั้นตอบกลับมาในรูปแบบที่ทำให้ ChromeDriver ทั้งตัวพัง
    # (native crash) แทนที่จะ error สวยๆ — เช็คตั้งแต่ต้นทางกันไว้ก่อนเลยดีกว่า
    try:
        parsed_start = datetime.strptime(start_date, "%Y-%m-%d").date()
        parsed_end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "invalid_request", "message": "รูปแบบวันที่ไม่ถูกต้อง (ต้องเป็น YYYY-MM-DD)"}), 400

    _MIN_YEAR = 2015
    max_year = date.today().year + 1
    if not (_MIN_YEAR <= parsed_start.year <= max_year) or not (_MIN_YEAR <= parsed_end.year <= max_year):
        return jsonify(
            {
                "error": "invalid_request",
                "message": (
                    f"ปีในวันที่ดูผิดปกติ ({parsed_start.year}-{parsed_end.year}) — ตรวจสอบว่าพิมพ์ปีครบ "
                    "4 หลักในช่องวันที่เริ่มต้น/สิ้นสุด (เช่น 2025 ไม่ใช่ 25)"
                ),
            }
        ), 400
    if parsed_start > parsed_end:
        return jsonify({"error": "invalid_request", "message": "วันที่เริ่มต้นต้องไม่มากกว่าวันที่สิ้นสุด"}), 400

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
        # has_solar ต้องกรอกเอง (checkbox ในฟอร์ม) — หน้าข้อมูลผู้ใช้ไฟของ PEA ไม่มีฟิลด์บอก
        # สถานะ Solar/Net Metering ให้ตรวจจับอัตโนมัติได้ (ดู amr_import.py)
        "has_solar": bool(body.get("has_solar")),
    }

    thread = threading.Thread(target=_run_import_job, args=(job_id, username, password, params), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id})


def _run_import_file_job(job_id: str, file_paths: List[str], params: dict) -> None:
    def log(msg: str) -> None:
        with _JOBS_LOCK:
            _JOBS[job_id]["logs"].append(msg)

    def on_profile(info: dict) -> None:
        # เก็บบัญชี/ชื่อบริษัทจริงที่อ่านได้จากไฟล์ (ถ้ามี) ไว้แสดงในหน้า Admin ของเครื่องนี้
        # เท่านั้น เหมือนโหมดดึงจากเว็บอัตโนมัติ — ไม่เคยถูกเขียนลงไฟล์ใดๆ ทั้งสิ้น
        with _JOBS_LOCK:
            _JOBS[job_id]["customer_profile"] = {
                "name": info.get("name") or "",
                "account_no": info.get("account_no") or "",
                "meter_no": info.get("meter_no") or "",
            }

    try:
        profile = import_amr_from_files(
            file_paths=file_paths,
            business_type_code=params["business_type_code"],
            rate_code=params["rate_code"],
            contract_kva=params.get("contract_kva"),
            source_label=params.get("source_label", ""),
            has_solar=params.get("has_solar", False),
            on_profile=on_profile,
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
                "has_solar": profile.has_solar,
            }
    except Exception as e:  # noqa: BLE001 — ต้อง catch ทุก error เพื่อรายงานสถานะ job ให้ถูกต้อง
        with _JOBS_LOCK:
            customer_profile = dict(_JOBS[job_id].get("customer_profile") or {})
        account_no = (customer_profile.get("account_no") or "").strip()

        # ถ้าอ่านเลขบัญชีจากไฟล์ได้ แต่ยังไม่รู้ประเภทธุรกิจ/รหัสอัตรา — บันทึกไว้เป็นรายการ
        # "รอทราบอัตรา" แทนที่จะทิ้ง error เฉยๆ ไฟล์ AMR ที่แนบไว้ (upload_dir) ยังอยู่ครบ ทำให้
        # กลับมากรอกประเภทธุรกิจ/รหัสอัตราแล้วนำเข้าใหม่ได้เลยโดยไม่ต้องอัปโหลดไฟล์ซ้ำ (ดูหน้า
        # "รอทราบอัตรา" /pending-amr)
        if account_no and _UNKNOWN_BUSINESS_TYPE_OR_RATE_ERROR in str(e):
            pending_id = uuid.uuid4().hex
            try:
                append_pending_amr_local(
                    {
                        "pending_id": pending_id,
                        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "account_no": account_no,
                        "company_name": customer_profile.get("name") or "",
                        "meter_no": customer_profile.get("meter_no") or "",
                        "file_paths": "|".join(file_paths),
                        "contract_kva": "" if params.get("contract_kva") is None else params["contract_kva"],
                        "has_solar": "true" if params.get("has_solar") else "false",
                        "source_label": params.get("source_label", ""),
                    },
                    PENDING_AMR_LOCAL_PATH,
                )
                with _JOBS_LOCK:
                    _JOBS[job_id]["status"] = "pending_rate"
                    _JOBS[job_id]["pending_id"] = pending_id
                    _JOBS[job_id]["error"] = str(e)
                return
            except OSError as save_err:
                log(f"⚠️ บันทึกรายการรอทราบอัตราไม่สำเร็จ: {save_err}")

        with _JOBS_LOCK:
            _JOBS[job_id]["status"] = "error"
            _JOBS[job_id]["error"] = str(e)


# นามสกุลไฟล์ AMR ที่รองรับจริง (รูปแบบเดียวกับที่ pea_ingest.parse_interval_report อ่านได้) — ใช้
# กรองทั้งตอนรับไฟล์แนบตรงๆ และตอนแตกไฟล์ .zip (ข้อ _save_uploaded_amr_files ด้านล่าง) เพื่อข้าม
# ไฟล์แถม/ไฟล์ระบบที่มักติดมาใน .zip (เช่น __MACOSX/, .DS_Store, Thumbs.db) แทนที่จะพยายามอ่านแล้ว
# error ทีหลัง
_AMR_FILE_EXTENSIONS = (".xls", ".xlsx", ".html", ".htm")

# กันไฟล์ .zip ที่แนบมาใหญ่เกินจริงหลังแตกไฟล์ (zip bomb) — รายงาน AMR จริงไม่ควรใหญ่ขนาดนี้เลย
# แม้จะแนบมาหลายสิบเดือนรวมกันก็ตาม ตัวเลขนี้เผื่อไว้กว้างๆ พอสมควร
_MAX_ZIP_EXTRACTED_BYTES = 300 * 1024 * 1024  # 300 MB
_MAX_ZIP_MEMBERS = 1000


def _save_uploaded_amr_files(files, upload_dir: Path) -> List[str]:
    """บันทึกไฟล์ที่แนบมาทุกไฟล์ลง upload_dir — ถ้าเป็นไฟล์ .zip จะแตกไฟล์ข้างในออกมาแทน (เผื่อ
    ผู้ใช้รวมไฟล์ AMR หลายเดือน/หลายบัญชีเป็น .zip เดียวมาแนบ ไม่ต้องแตกเองก่อน) คืน path ของไฟล์
    AMR จริงทั้งหมดที่พร้อมส่งให้ import_amr_from_files (ข้ามไฟล์ที่ไม่ใช่นามสกุลที่รองรับ/ไฟล์ระบบ
    ที่ติดมาใน zip เช่น __MACOSX, .DS_Store โดยอัตโนมัติ)

    ป้องกัน zip slip (path traversal ผ่านชื่อไฟล์ในซิปที่มี "../" ปนอยู่) ด้วยการ resolve path แล้ว
    เช็คว่ายังอยู่ใต้ upload_dir เสมอ ก่อนเขียนไฟล์จริง และจำกัดขนาด/จำนวนไฟล์หลังแตกกัน zip bomb"""

    file_paths: List[str] = []
    for f in files:
        filename = secure_filename(f.filename or "") or f"upload_{len(file_paths) + 1}"

        if filename.lower().endswith(".zip"):
            zip_path = upload_dir / f"_upload_{len(file_paths)}.zip"
            f.save(zip_path)
            try:
                with zipfile.ZipFile(zip_path) as zf:
                    members = [m for m in zf.infolist() if not m.is_dir()]
                    if len(members) > _MAX_ZIP_MEMBERS:
                        raise ValueError(f"ไฟล์ {filename} มีไฟล์ข้างในเยอะเกินไป ({len(members)} ไฟล์)")
                    total_size = sum(m.file_size for m in members)
                    if total_size > _MAX_ZIP_EXTRACTED_BYTES:
                        raise ValueError(f"ไฟล์ {filename} ขนาดหลังแตกไฟล์ใหญ่เกินไป")

                    extracted_count = 0
                    for i, member in enumerate(members):
                        member_name = Path(member.filename).name  # ตัด path ย่อยทิ้ง กัน zip slip
                        # ข้ามไฟล์ระบบที่โปรแกรมซิปมักแถมมาเอง (macOS: __MACOSX/, ไฟล์ resource
                        # fork ที่ขึ้นต้นด้วย "._"; ไฟล์ซ่อนทั่วไปที่ขึ้นต้นด้วย ".") ไม่ใช่ไฟล์ AMR จริง
                        if not member_name or member_name.startswith("."):
                            continue
                        if "__MACOSX" in Path(member.filename).parts:
                            continue
                        if not member_name.lower().endswith(_AMR_FILE_EXTENSIONS):
                            continue
                        safe_name = secure_filename(member_name) or f"zip_entry_{i}"
                        dest = (upload_dir / safe_name).resolve()
                        if upload_dir.resolve() not in dest.parents and dest != upload_dir.resolve():
                            continue  # ป้องกันไว้อีกชั้น แม้ตัด path ย่อยไปแล้วก็ตาม
                        # กันชื่อซ้ำ (ไฟล์ชื่อเดียวกันจากคนละโฟลเดอร์ย่อยในซิป) ด้วยเลขนำหน้า
                        if dest.exists():
                            dest = upload_dir / f"{i}_{safe_name}"
                        with zf.open(member) as src, open(dest, "wb") as out:
                            out.write(src.read())
                        file_paths.append(str(dest))
                        extracted_count += 1
            except zipfile.BadZipFile:
                raise ValueError(f"ไฟล์ {filename} ไม่ใช่ไฟล์ .zip ที่ถูกต้อง หรือไฟล์เสียหาย")
            finally:
                zip_path.unlink(missing_ok=True)
            continue

        dest = upload_dir / filename
        f.save(dest)
        if filename.lower().endswith(_AMR_FILE_EXTENSIONS):
            file_paths.append(str(dest))

    return file_paths


@app.route("/api/admin/import-file", methods=["POST"])
def api_start_import_file():
    """เริ่ม job นำเข้า AMR จากไฟล์ที่แนบมาโดยตรง (ไม่ต้อง login เว็บ PEA เลย) — ใช้เมื่อมีไฟล์
    "รายงานข้อมูลกิโลวัตต์ชั่วโมงแบบช่วงเวลา" (รูปแบบเดียวกับที่โหมดดึงจากเว็บดาวน์โหลดมาให้เอง —
    ดู pea_ingest.parse_interval_report) อยู่แล้วในเครื่อง แต่ไม่มี username/password ของบัญชีนั้น

    business_type_code/rate_code ไม่บังคับต้องกรอก — ถ้าปล่อยว่าง import_amr_from_files จะ
    พยายามอ่านเลขบัญชีจากในไฟล์แล้วค้นในทะเบียนลูกค้าให้อัตโนมัติ (ดู amr_import.py) ถ้าหาไม่ได้
    จริงๆ job จะ error กลับมาบอกให้กรอกเอง (ไฟล์ที่แนบไว้ตอนนั้นจะถูกทิ้งไว้เฉยๆ ไม่ลบอัตโนมัติ)
    """

    files = request.files.getlist("files")
    business_type_code = (request.form.get("business_type_code") or "").strip()
    rate_code = (request.form.get("rate_code") or "").strip()
    contract_kva_raw = (request.form.get("contract_kva") or "").strip()
    source_label = (request.form.get("source_label") or "").strip()
    has_solar = (request.form.get("has_solar") or "").strip().lower() in ("1", "true", "yes", "on")

    if not files:
        return jsonify({"error": "invalid_request", "message": "กรุณาแนบไฟล์ AMR อย่างน้อย 1 ไฟล์"}), 400

    contract_kva: Optional[float] = None
    if contract_kva_raw:
        try:
            contract_kva = float(contract_kva_raw)
        except ValueError:
            return jsonify({"error": "invalid_request", "message": "KVA ตามสัญญาต้องเป็นตัวเลข"}), 400

    job_id = uuid.uuid4().hex

    # เก็บไฟล์ที่แนบไว้ที่ amr_downloads/uploaded/<job_id>/ (โฟลเดอร์เดียวกับไฟล์ที่ดาวน์โหลด
    # จากเว็บ PEA เอง — อยู่ใน .gitignore แล้ว ไม่มีทางหลุดเข้า repo public) sanitize ชื่อไฟล์
    # ด้วย secure_filename เสมอเพราะชื่อไฟล์มาจากผู้ใช้ (กัน path traversal)
    upload_dir = DEFAULT_DOWNLOAD_DIR / "uploaded" / job_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    try:
        file_paths = _save_uploaded_amr_files(files, upload_dir)
    except ValueError as e:
        return jsonify({"error": "invalid_request", "message": str(e)}), 400

    if not file_paths:
        return jsonify(
            {"error": "invalid_request", "message": "ไม่พบไฟล์ AMR ที่รองรับ (.xls/.xlsx/.html/.htm) ในไฟล์ที่แนบมาเลย"}
        ), 400

    with _JOBS_LOCK:
        _JOBS[job_id] = {"status": "running", "logs": [], "result": None, "error": None, "customer_profile": None}

    params = {
        "business_type_code": business_type_code,
        "rate_code": rate_code,
        "contract_kva": contract_kva,
        "source_label": source_label,
        "has_solar": has_solar,
    }

    thread = threading.Thread(target=_run_import_file_job, args=(job_id, file_paths, params), daemon=True)
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


@app.route("/api/admin/pending-amr")
def api_list_pending_amr():
    """รายการ AMR ที่นำเข้าไม่สำเร็จเพราะไม่ทราบประเภทธุรกิจ/รหัสอัตรา (รอกรอกภายหลัง) — ไล่จาก
    รายการล่าสุดไปเก่าสุด"""

    entries = load_pending_amr_local(PENDING_AMR_LOCAL_PATH)
    entries.sort(key=lambda e: e.get("created_at", ""), reverse=True)
    return jsonify({"entries": entries})


@app.route("/api/admin/pending-amr/<pending_id>", methods=["DELETE"])
def api_delete_pending_amr(pending_id: str):
    """ลบรายการรอทราบอัตราทิ้ง (ไม่ต้องการนำเข้าบัญชีนี้แล้ว) — ไฟล์ AMR ที่แนบไว้ตอนนั้นไม่ถูกลบ
    ตามไปด้วย ปล่อยทิ้งไว้ที่ amr_downloads/uploaded/ เฉยๆ"""

    removed = remove_pending_amr_local(pending_id, PENDING_AMR_LOCAL_PATH)
    if not removed:
        return jsonify({"error": "not_found", "message": "ไม่พบรายการนี้ (อาจถูกลบ/resolve ไปแล้ว)"}), 404
    return jsonify({"ok": True})


@app.route("/api/admin/pending-amr/<pending_id>/resolve", methods=["POST"])
def api_resolve_pending_amr(pending_id: str):
    """กรอกประเภทธุรกิจ/รหัสอัตราที่เพิ่งทราบ แล้วนำเข้าไฟล์ AMR ที่เก็บไว้ตอนแรกจริงๆ ทันที (ไม่ต้อง
    อัปโหลดไฟล์ใหม่) — ทำงานแบบ synchronous เพราะไฟล์ถูกเก็บไว้ในเครื่องอยู่แล้ว ไม่ต้องดาวน์โหลด
    ใหม่ จึงเร็วพอที่จะไม่ต้องใช้ job แบบ background เหมือนโหมดอื่น ถ้าสำเร็จจะลบรายการนี้ออกจาก
    รายการรอทราบอัตรา"""

    entries = load_pending_amr_local(PENDING_AMR_LOCAL_PATH)
    entry = next((e for e in entries if e.get("pending_id") == pending_id), None)
    if entry is None:
        return jsonify({"error": "not_found", "message": "ไม่พบรายการนี้ (อาจถูกลบ/resolve ไปแล้ว)"}), 404

    body = request.get_json(silent=True) or {}
    business_type_code = (body.get("business_type_code") or "").strip()
    rate_code = (body.get("rate_code") or "").strip()
    # เลือก "ไม่ทราบรหัสอัตรา" มา — ใช้ค่า sentinel แทนแทนที่จะบังคับกรอกจริง ยังใช้ประโยชน์ได้
    # ที่ชั้นจับคู่ระดับ "ประเภทธุรกิจ" (BUSINESS_ONLY) แม้จะไม่มีวันเป็น EXACT ก็ตาม (ดู
    # mapping.UNKNOWN_RATE_CODE) — ดีกว่าปล่อยค้างไว้ในลิสต์รอทราบอัตราตลอดไปเฉยๆ
    if bool(body.get("rate_code_unknown")):
        rate_code = UNKNOWN_RATE_CODE
    if not business_type_code or not rate_code:
        return jsonify({"error": "invalid_request", "message": "กรุณาเลือกประเภทธุรกิจและกรอกรหัสอัตราให้ครบ (หรือติ๊ก \"ไม่ทราบรหัสอัตรา\")"}), 400

    contract_kva_raw = body.get("contract_kva")
    contract_kva: Optional[float] = None
    if contract_kva_raw not in (None, ""):
        try:
            contract_kva = float(contract_kva_raw)
        except (TypeError, ValueError):
            return jsonify({"error": "invalid_request", "message": "KVA ตามสัญญาต้องเป็นตัวเลข"}), 400
    elif entry.get("contract_kva"):
        try:
            contract_kva = float(entry["contract_kva"])
        except ValueError:
            contract_kva = None

    has_solar_raw = body.get("has_solar")
    has_solar = bool(has_solar_raw) if has_solar_raw is not None else (entry.get("has_solar") == "true")

    file_paths = [p for p in (entry.get("file_paths") or "").split("|") if p]
    missing = [p for p in file_paths if not Path(p).exists()]
    if not file_paths or missing:
        return jsonify(
            {
                "error": "invalid_request",
                "message": "ไม่พบไฟล์ AMR ที่เก็บไว้ตอนนำเข้าครั้งแรกแล้ว (อาจถูกลบออกจากเครื่อง) กรุณาแนบไฟล์ใหม่แทนในโหมดนำเข้าปกติ",
            }
        ), 400

    logs: List[str] = []
    try:
        profile = import_amr_from_files(
            file_paths=file_paths,
            business_type_code=business_type_code,
            rate_code=rate_code,
            contract_kva=contract_kva,
            source_label=entry.get("source_label", ""),
            has_solar=has_solar,
            log=logs.append,
        )
    except Exception as e:  # noqa: BLE001 — รายงาน error กลับไปให้ผู้ใช้แก้ไขแล้วลองใหม่ได้
        return jsonify({"error": "import_failed", "message": str(e), "logs": logs}), 400

    remove_pending_amr_local(pending_id, PENDING_AMR_LOCAL_PATH)

    return jsonify(
        {
            "result": {
                "business_type_code": profile.business_type_code,
                "rate_code": profile.rate_code,
                "demand_kw": profile.demand_kw,
                "energy_kwh": profile.energy_kwh,
                "sample_size": profile.sample_size,
                "contract_kva_ref": profile.contract_kva_ref,
                "notes": profile.notes,
                "has_solar": profile.has_solar,
            },
            "logs": logs,
        }
    )


if __name__ == "__main__":
    # use_reloader=False: ปิด auto-restart เวลาไฟล์เปลี่ยน — งานนำเข้า AMR รันเป็น
    # background thread ที่ใช้เวลานาน (ดาวน์โหลดหลายเดือน) ถ้า reloader restart ตัวเซิร์ฟเวอร์
    # กลางคันจะทำให้ thread ถูกตัดตอน และอาจทำให้ไฟล์ lock ของ webdriver-manager
    # (.wdm-lock-chromedriver-*) ค้างจนรอบถัดไป Selenium ต้องรอ lock จนหมดเวลา (timeout)
    app.run(debug=True, port=5000, use_reloader=False)
