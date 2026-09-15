"""เว็บแอป No AMR — ค้นหาผู้ใช้ไฟ + ดูผลพยากรณ์โปรไฟล์ P/OP/H

รันด้วย:
    python web/app.py
แล้วเปิดเบราว์เซอร์ที่ http://localhost:5000

⚠️ ข้อมูลลูกค้าในเว็บนี้ (data/reference/customers.csv) เป็นข้อมูล "สมมติ" เพื่อสาธิต
การทำงานเท่านั้น ห้ามใส่ข้อมูลลูกค้าจริงลงไฟล์นี้ เพราะ repo เป็น public — ถ้าจะต่อกับ
ข้อมูลลูกค้าจริง ให้เปลี่ยน data_dir ไปชี้ฐานข้อมูลจริงที่แยกเก็บไว้นอก repo แทน
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from flask import Flask, jsonify, send_from_directory

from amr_mapping import estimate_customer_load, load_reference_data
from amr_mapping.mapping import MatchLevel

app = Flask(__name__, static_folder="static", static_url_path="")

# โหลดข้อมูลอ้างอิงครั้งเดียวตอนสตาร์ทแอป (ไฟล์ CSV มีขนาดเล็ก ไม่จำเป็นต้องโหลดใหม่ทุก request)
REFERENCE = load_reference_data()

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

    return jsonify([_customer_to_dict(c) for c in REFERENCE.customers])


@app.route("/api/forecast/<path:account_no>")
def api_forecast(account_no: str):
    """ค้นหาผู้ใช้ไฟตามเลขบัญชี แล้วคืนผลพยากรณ์โปรไฟล์ P/OP/H"""

    customer = next((c for c in REFERENCE.customers if c.account_no == account_no), None)
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

    result = estimate_customer_load(customer, REFERENCE)
    business_type = REFERENCE.business_types.get(result.matched_profile.business_type_code)
    rate_schedule = REFERENCE.rate_schedules.get(result.matched_profile.rate_code)

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


if __name__ == "__main__":
    app.run(debug=True, port=5000)
