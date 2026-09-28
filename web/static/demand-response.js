// โหมด "dr" — จำลองผลของการหยุดผลิตชั่วคราว (เช่น พักเที่ยง) ต่อกำลังไฟฟ้า/พลังงานที่ใช้
// ใช้รูปทรงกราฟรายชั่วโมงจริงของประเภทธุรกิจที่เลือก (ต้องมีข้อมูล AMR จริงนำเข้าไว้แล้วเท่านั้น
// — has_curve) เป็นฐาน แล้วส่งไปคำนวณที่ POST /api/demand-response-simulate (ดู
// src/amr_mapping/demand_response.py ฝั่ง backend)

const drBusinessTypeSelect = document.getElementById("dr-business-type");
const drDemandP = document.getElementById("dr-demand-p");
const drDemandOp = document.getElementById("dr-demand-op");
const drDemandH = document.getElementById("dr-demand-h");
const drEnergyP = document.getElementById("dr-energy-p");
const drEnergyOp = document.getElementById("dr-energy-op");
const drEnergyH = document.getElementById("dr-energy-h");
const drStopStart = document.getElementById("dr-stop-start");
const drStopEnd = document.getElementById("dr-stop-end");
const drDropPercent = document.getElementById("dr-drop-percent");
const drSubmitBtn = document.getElementById("dr-submit-btn");
const drFormHint = document.getElementById("dr-form-hint");
const drResult = document.getElementById("dr-result");

// โหลดเฉพาะประเภทธุรกิจที่มีข้อมูลกราฟรายชั่วโมงจริง (has_curve) — ต่างจาก dropdown ในโหมด
// adhoc ที่แสดงทุกประเภทที่มีโปรไฟล์ (อาจเป็นแค่ค่าเฉลี่ย P/OP/H ไม่มีกราฟราย ชม. เลย)
async function loadDrBusinessTypes() {
  try {
    const res = await fetch("/api/business-types-full");
    const types = await res.json();
    const withCurve = types.filter((t) => (t.profiles || []).some((p) => p.has_curve));
    withCurve.sort((a, b) => a.name_th.localeCompare(b.name_th, "th"));

    if (!withCurve.length) {
      drBusinessTypeSelect.innerHTML = `<option value="">-- ยังไม่มีประเภทธุรกิจที่มีข้อมูลกราฟรายชั่วโมงจริงในระบบ --</option>`;
      return;
    }
    drBusinessTypeSelect.innerHTML = withCurve.map((t) => `<option value="${escapeHtml(t.code)}">${escapeHtml(t.name_th)} · ${escapeHtml(t.code)}</option>`).join("");
  } catch (err) {
    drFormHint.textContent = "โหลดรายชื่อประเภทธุรกิจไม่สำเร็จ";
    console.error(err);
  }
}

function timeStringToHour(value) {
  const m = /^(\d{1,2}):(\d{2})$/.exec(value || "");
  if (!m) return null;
  return Number(m[1]) + Number(m[2]) / 60;
}

function formatHour(h) {
  const hh = Math.floor(h);
  const mm = Math.round((h - hh) * 60);
  return `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
}

function drStatTiles(label, demand, energy) {
  const ordered = [
    ...["P", "OP", "H"].map((p) => ({ period: p, value: demand[p], unit: "kW", digits: 2 })),
    ...["P", "OP", "H"].map((p) => ({ period: p, value: energy[p], unit: "kWh", digits: 0 })),
  ];
  return `
    <div class="chart-title">${label}</div>
    <div class="stats-grid">
      ${ordered
        .map(
          (t) => `
        <div class="stat-tile">
          <div class="stat-head"><span class="dot" style="background:${PERIOD_COLOR[t.period]};"></span><span class="stat-label">${PERIOD_TH[t.period]}</span></div>
          <div><span class="stat-value">${formatNumber(t.value, t.digits)}</span> <span class="stat-unit">${t.unit}</span></div>
        </div>`
        )
        .join("")}
    </div>`;
}

async function runDemandResponseSimulation() {
  drFormHint.textContent = "";
  const businessTypeCode = drBusinessTypeSelect.value;
  if (!businessTypeCode) {
    drFormHint.textContent = "กรุณาเลือกประเภทธุรกิจ";
    return;
  }

  const demandKw = { P: Number(drDemandP.value || 0), OP: Number(drDemandOp.value || 0), H: Number(drDemandH.value || 0) };
  const energyKwh = { P: Number(drEnergyP.value || 0), OP: Number(drEnergyOp.value || 0), H: Number(drEnergyH.value || 0) };

  const stopStartHour = timeStringToHour(drStopStart.value);
  const stopEndHour = timeStringToHour(drStopEnd.value);
  if (stopStartHour === null || stopEndHour === null) {
    drFormHint.textContent = "กรุณากรอกช่วงเวลาที่หยุดให้ครบ";
    return;
  }
  const dropPercent = Number(drDropPercent.value);

  drResult.innerHTML = "";
  drSubmitBtn.disabled = true;
  try {
    const res = await fetch("/api/demand-response-simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        business_type_code: businessTypeCode,
        demand_kw: demandKw,
        energy_kwh: energyKwh,
        stop_start_hour: stopStartHour,
        stop_end_hour: stopEndHour,
        drop_percent: dropPercent,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      drFormHint.textContent = data.message || "คำนวณไม่สำเร็จ";
      return;
    }

    const savedTotal = data.energy_saved_kwh.P + data.energy_saved_kwh.OP + data.energy_saved_kwh.H;
    drResult.innerHTML = `
      <div class="card" style="padding:16px 28px;background:#f7f9fc;">
        หยุดผลิต <b>${escapeHtml(data.business_type_name)}</b> ช่วง ${formatHour(stopStartHour)}-${formatHour(stopEndHour)} น. ลดลง ${formatNumber(dropPercent, 0)}%
        → พลังงานไฟฟ้าประหยัดรวม <b>${formatNumber(savedTotal, 0)} kWh/เดือน</b>
        (สัดส่วนที่ลดจากคาบ Peak แล้วนำไปใช้กับ OP/H เท่ากันหมด = ${formatNumber(data.reduction_ratio * 100, 1)}% ของค่าเดิม)
      </div>

      <div class="card chart-card">
        ${drStatTiles("ก่อนหยุดผลิต (ค่าที่กรอก)", demandKw, energyKwh)}
      </div>
      <div class="card chart-card">
        ${drStatTiles("หลังหยุดผลิต (คำนวณใหม่)", data.demand_kw, data.energy_kwh)}
      </div>

      <div class="card chart-card">
        <div class="chart-title">กราฟรายชั่วโมงก่อนหยุดผลิต (kW)</div>
        ${renderDailyCurveSVG(data.baseline_curve, "all")}
      </div>
      <div class="card chart-card">
        <div class="chart-title">กราฟรายชั่วโมงหลังหยุดผลิต (kW)</div>
        ${renderDailyCurveSVG(data.adjusted_curve, "all")}
      </div>`;
  } catch (err) {
    drFormHint.textContent = "เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ";
    console.error(err);
  } finally {
    drSubmitBtn.disabled = false;
  }
}

drSubmitBtn.addEventListener("click", runDemandResponseSimulation);
loadDrBusinessTypes();
