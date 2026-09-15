"""เว็บแอป No AMR — ค้นหาผู้ใช้ไฟ + ดูผลพยากรณ์โปรไฟล์ P/OP/H

รันด้วย:
    python web/app.py
แล้วเปิดเบราว์เซอร์ที่ http://localhost:5000

⚠️ ข้อมูลลูกค้าในเว็บนี้ (data/reference/customers.csv) เป็นข้อมูล "สมมติ" เพื่อสาธิต
การทำงานเท่านั้น ห้ามใส่ข้อมูลลูกค้าจริงลงไฟล์นี้ เพราะ repo เป็น public — ถ้าจะต่อกับ
ข้อมูลลูกค้าจริง ให้เปลี่ยน data_dir ไปชี้ฐานข้อมูลจริงที่แยกเก็บไว้นอก repo แทน
"""

from __future__ import annotations

import os
import sys
import threading
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from flask import Flask, jsonify, request

from amr_mapping import estimate_customer_load, load_reference_data
from amr_mapping.amr_import import import_amr_for_business
from amr_mapping.mapping import MatchLevel

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


@app.route("/")
def index():
    return app.send_static_file("index.html")


@app.route("/api/customers")
def api_list_customers():
    """รายชื่อผู้ใช้ไฟทั้งหมด (สำหรับ dropdown/autocomplete ในหน้าค้นหา)"""

    return jsonify([_customer_to_dict(c) for c in get_reference().customers])


@app.route("/api/business-types")
def api_list_business_types():
    """รายชื่อประเภทธุรกิจทั้งหมด (สำหรับ dropdown ในหน้านำเข้า AMR)"""

    return jsonify(
        [
            {"code": bt.code, "name_th": bt.name_th, "category": bt.category}
            for bt in get_reference().business_types.values()
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
        }
    )


@app.route("/admin")
def admin_page():
    return app.send_static_file("admin.html")


def _run_import_job(job_id: str, username: str, password: str, params: dict) -> None:
    def log(msg: str) -> None:
        with _JOBS_LOCK:
            _JOBS[job_id]["logs"].append(msg)

    try:
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

    อ่าน username/password จากตัวแปรสภาพแวดล้อม PEA_AMR_USERNAME / PEA_AMR_PASSWORD
    เท่านั้น (ไม่รับจาก request body) — ตั้งค่าที่เครื่องที่รันเซิร์ฟเวอร์นี้ ดู README
    """

    username = os.environ.get("PEA_AMR_USERNAME")
    password = os.environ.get("PEA_AMR_PASSWORD")
    if not username or not password:
        return jsonify(
            {
                "error": "missing_credentials",
                "message": "ยังไม่ได้ตั้งค่า PEA_AMR_USERNAME / PEA_AMR_PASSWORD ในเครื่องนี้ "
                "(ดูวิธีตั้งค่าในไฟล์ README หัวข้อ 'นำเข้า AMR อัตโนมัติผ่านเว็บ')",
            }
        ), 400

    body = request.get_json(force=True, silent=True) or {}
    accounts_raw = body.get("accounts") or body.get("account_no") or ""
    accounts = [a.strip() for a in str(accounts_raw).split(",") if a.strip()]
    business_type_code = (body.get("business_type_code") or "").strip()
    rate_code = (body.get("rate_code") or "").strip()
    start_date = (body.get("start_date") or "").strip()
    end_date = (body.get("end_date") or "").strip()

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
        _JOBS[job_id] = {"status": "running", "logs": [], "result": None, "error": None}

    params = {
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
    app.run(debug=True, port=5000)
