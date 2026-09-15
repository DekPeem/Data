// หน้าพยากรณ์แบบไม่บันทึกข้อมูล — ชื่อบริษัทที่พิมพ์ในฟอร์มนี้ "ไม่เคย" ถูกส่งไปที่เซิร์ฟเวอร์
// เลย (ดู runForecast() ด้านล่าง: body ที่ fetch ไปยัง /api/forecast-adhoc มีแค่
// business_type_code / rate_code / contract_kva เท่านั้น) ใช้แสดงผลฝั่ง browser ล้วนๆ

const PERIOD_COLOR = { P: "#2a78d6", OP: "#eb6834", H: "#1baf7a" };
const PERIOD_TH = { P: "Peak (P)", OP: "Off-Peak (OP)", H: "Holiday (H)" };

const nameInput = document.getElementById("f-name");
const businessTypeSelect = document.getElementById("f-business-type");
const rateCodeInput = document.getElementById("f-rate-code");
const rateCodeList = document.getElementById("rate-code-list");
const kvaInput = document.getElementById("f-kva");
const submitBtn = document.getElementById("submit-btn");
const formHint = document.getElementById("form-hint");
const resultArea = document.getElementById("result");

function formatNumber(n, digits = 0) {
  return n.toLocaleString("th-TH", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function iconCheck(color) {
  return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>`;
}

function iconInfo(color) {
  return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><path d="M12 8h.01"/></svg>`;
}

function iconBuilding(color) {
  return `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
    <rect x="4" y="3" width="10" height="18" rx="1"/>
    <rect x="14" y="9" width="6" height="12" rx="1"/>
    <path d="M7 7h.01M10.5 7h.01M7 11h.01M10.5 11h.01M7 15h.01M10.5 15h.01M16.5 12h.01M16.5 16h.01"/>
  </svg>`;
}

async function loadBusinessTypes() {
  try {
    const res = await fetch("/api/business-types");
    const types = await res.json();
    businessTypeSelect.innerHTML =
      `<option value="">-- ไม่ระบุ (จับคู่จากอัตราอย่างเดียว) --</option>` +
      types.map((t) => `<option value="${t.code}">${t.name_th} · ${t.code}</option>`).join("");
  } catch (err) {
    console.warn("โหลดรายชื่อประเภทธุรกิจไม่สำเร็จ", err);
  }
}

async function loadRateSchedules() {
  try {
    const res = await fetch("/api/rate-schedules");
    const rates = await res.json();
    rateCodeList.innerHTML = rates.map((r) => `<option value="${r.code}">${r.description || ""}</option>`).join("");
  } catch (err) {
    console.warn("โหลดรายชื่อประเภทอัตราไม่สำเร็จ", err);
  }
}

function renderBarChart(title, values, unit) {
  const max = Math.max(...Object.values(values), 1);
  const bars = ["P", "OP", "H"]
    .map((period) => {
      const height = Math.round((values[period] / max) * 160);
      return `
        <div class="bar-col">
          <div class="bar-value">${formatNumber(values[period], unit === "kWh" ? 0 : 2)}</div>
          <div class="bar" style="height:${height}px;background:${PERIOD_COLOR[period]};"></div>
          <div class="bar-label">${period}</div>
        </div>`;
    })
    .join("");
  return `
    <div class="card chart-card">
      <div class="chart-title">${title}</div>
      <div class="chart-bars">${bars}</div>
    </div>`;
}

function renderLineChart(title, values, unit) {
  const periods = ["P", "OP", "H"];
  const max = Math.max(...periods.map((p) => values[p]), 1);
  const width = 280;
  const height = 170;
  const padX = 34;
  const padY = 28;
  const stepX = (width - padX * 2) / (periods.length - 1);

  const points = periods.map((period, i) => {
    const x = padX + stepX * i;
    const y = padY + (1 - values[period] / max) * (height - padY * 2 - 12);
    return { x, y, period, value: values[period] };
  });
  const pointsAttr = points.map((pt) => `${pt.x.toFixed(1)},${pt.y.toFixed(1)}`).join(" ");

  const dots = points
    .map(
      (pt) => `
      <text x="${pt.x.toFixed(1)}" y="${(pt.y - 10).toFixed(1)}" text-anchor="middle" font-size="11" font-weight="700" fill="#0f1b2d">${formatNumber(pt.value, unit === "kWh" ? 0 : 2)}</text>
      <circle cx="${pt.x.toFixed(1)}" cy="${pt.y.toFixed(1)}" r="4.5" fill="${PERIOD_COLOR[pt.period]}" stroke="#ffffff" stroke-width="2"/>
      <text x="${pt.x.toFixed(1)}" y="${height - 6}" text-anchor="middle" font-size="12" fill="#8996ab">${pt.period}</text>`
    )
    .join("");

  return `
    <div class="card chart-card">
      <div class="chart-title">${title}</div>
      <svg viewBox="0 0 ${width} ${height}" style="width:100%;height:auto;" preserveAspectRatio="xMidYMid meet">
        <line x1="${padX}" y1="${height - 18}" x2="${width - padX}" y2="${height - 18}" stroke="#e1e0d9" stroke-width="1"/>
        <polyline points="${pointsAttr}" fill="none" stroke="#2a78d6" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>
        ${dots}
      </svg>
    </div>`;
}

function renderStatTiles(demand, energy) {
  const ordered = [
    ...["P", "OP", "H"].map((p) => ({ period: p, value: demand[p], unit: "kW", label: "กำลังไฟฟ้าสูงสุด", digits: 2 })),
    ...["P", "OP", "H"].map((p) => ({ period: p, value: energy[p], unit: "kWh", label: "พลังงานไฟฟ้า / เดือน", digits: 0 })),
  ];
  return ordered
    .map(
      (t) => `
      <div class="stat-tile">
        <div class="stat-head"><span class="dot" style="background:${PERIOD_COLOR[t.period]};"></span><span class="stat-label">${PERIOD_TH[t.period]}</span></div>
        <div><span class="stat-value">${formatNumber(t.value, t.digits)}</span> <span class="stat-unit">${t.unit}</span></div>
        <div class="stat-label">${t.label}</div>
      </div>`
    )
    .join("");
}

function renderResult(data, displayName, typedBusinessTypeCode, typedRateCode, typedKva) {
  const m = data.match;
  const p = data.matched_profile;
  const f = data.forecast;

  const matchColor = m.is_exact ? "#0ca30c" : "#fab219";
  const matchBg = m.is_exact ? "#e8f7ec" : "#fff7e6";

  const businessBadge = typedBusinessTypeCode
    ? `<span class="badge" style="background:#eef3fa;color:#184f95;">${p.business_type_name || typedBusinessTypeCode} · ${typedBusinessTypeCode}</span>`
    : `<span class="badge" style="background:rgba(15,23,42,0.05);color:#55647a;">ยังไม่จัดประเภทธุรกิจ</span>`;

  resultArea.innerHTML = `
    <div class="card customer-card">
      <div class="customer-head">
        <div class="customer-head-left">
          <div class="customer-icon">${iconBuilding("#2a78d6")}</div>
          <div>
            <div class="customer-name">${displayName || "(ไม่ได้ระบุชื่อ)"}</div>
            <div class="customer-sub">พยากรณ์แบบไม่บันทึกข้อมูล — ไม่มีเลขบัญชีผู้ใช้ไฟ</div>
          </div>
        </div>
        <div class="customer-badges">
          ${businessBadge}
          <span class="badge" style="background:rgba(15,23,42,0.05);color:#55647a;">ไม่มี AMR ของตัวเอง</span>
        </div>
      </div>
      <div class="divider"></div>
      <div class="field-grid">
        <div class="field-item"><div class="field-label">ประเภทอัตราที่กรอก</div><div class="field-value">${typedRateCode || "ไม่ทราบ"}</div></div>
        <div class="field-item"><div class="field-label">KVA ตามสัญญาที่กรอก</div><div class="field-value">${typedKva ? formatNumber(typedKva) + " kVA" : "ไม่ทราบ"}</div></div>
        <div class="field-item"><div class="field-label">โปรไฟล์ที่ใช้อ้างอิง</div><div class="field-value">${p.business_type_name || p.business_type_code || "-"} / อัตรา ${p.rate_code}</div></div>
        <div class="field-item"><div class="field-label">จำนวนตัวอย่างในโปรไฟล์</div><div class="field-value">${p.sample_size || "-"}</div></div>
      </div>
    </div>

    <div class="card match-card">
      <div class="match-left">
        <div class="match-icon" style="background:${matchBg};">${iconCheck(matchColor)}</div>
        <div>
          <div class="match-title">${m.level_label_th}</div>
          <div class="match-sub">${p.notes || ""}</div>
        </div>
      </div>
      <div class="match-right">
        <div class="match-right-label">ตัวคูณปรับสเกลตาม KVA</div>
        <div class="match-right-value">${m.scale_factor.toFixed(2)}×</div>
      </div>
    </div>

    ${
      m.warnings.length
        ? `<div class="card warnings" style="padding:16px 28px;">${m.warnings.map((w) => `<div class="warning-item">⚠️ ${w}</div>`).join("")}</div>`
        : ""
    }

    <div>
      <div class="stats-title" style="margin-bottom:12px;">ผลพยากรณ์โปรไฟล์การใช้ไฟฟ้า</div>
      <div class="stats-grid">${renderStatTiles(f.demand_kw, f.energy_kwh)}</div>
    </div>

    <div>
      <div class="legend-row" style="margin-bottom:12px;">
        <div class="legend-item"><span class="dot" style="background:${PERIOD_COLOR.P};"></span>Peak — วันทำการ 09:00-22:00</div>
        <div class="legend-item"><span class="dot" style="background:${PERIOD_COLOR.OP};"></span>Off-Peak — วันทำการ นอกช่วง Peak</div>
        <div class="legend-item"><span class="dot" style="background:${PERIOD_COLOR.H};"></span>Holiday — วันหยุด/เสาร์-อาทิตย์</div>
      </div>
      <div class="charts-grid">
        ${renderBarChart("กำลังไฟฟ้าสูงสุด (kW)", f.demand_kw, "kW")}
        ${renderBarChart("พลังงานไฟฟ้า (kWh / เดือน)", f.energy_kwh, "kWh")}
      </div>
      <div class="charts-grid" style="margin-top:16px;">
        ${renderLineChart("แนวโน้มกำลังไฟฟ้าสูงสุด (kW)", f.demand_kw, "kW")}
        ${renderLineChart("แนวโน้มพลังงานไฟฟ้า (kWh / เดือน)", f.energy_kwh, "kWh")}
      </div>
    </div>

    <div class="disclaimer">
      ${iconInfo("#55647a")}
      <div class="disclaimer-text">ค่าที่แสดงเป็นค่าพยากรณ์ คำนวณจากค่าเฉลี่ยของผู้ใช้ไฟกลุ่มธุรกิจและอัตราเดียวกัน ไม่ใช่ข้อมูลจากมิเตอร์ AMR ของบริษัทนี้โดยตรง และ<b>ไม่มีการบันทึกชื่อบริษัท/ข้อมูลที่กรอกในหน้านี้ลงไฟล์หรือฐานข้อมูลใดๆ ทั้งสิ้น</b></div>
    </div>
  `;

  resultArea.style.display = "flex";
}

async function runForecast() {
  formHint.textContent = "";
  const displayName = nameInput.value.trim(); // ใช้แสดงผลเท่านั้น — ไม่ส่งไป server
  const businessTypeCode = businessTypeSelect.value.trim();
  const rateCode = rateCodeInput.value.trim();
  const kvaRaw = kvaInput.value.trim();

  if (!businessTypeCode && !rateCode) {
    formHint.textContent = "กรุณาเลือกประเภทธุรกิจ หรือ กรอกรหัสอัตรา อย่างน้อยหนึ่งอย่าง";
    return;
  }

  const body = {
    business_type_code: businessTypeCode || undefined,
    rate_code: rateCode || undefined,
    contract_kva: kvaRaw || undefined,
  };

  try {
    const res = await fetch("/api/forecast-adhoc", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();

    if (!res.ok) {
      resultArea.style.display = "none";
      formHint.textContent = data.message || "เกิดข้อผิดพลาด";
      return;
    }

    renderResult(data, displayName, businessTypeCode, rateCode, kvaRaw ? Number(kvaRaw) : null);
  } catch (err) {
    formHint.textContent = "เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ";
    console.error(err);
  }
}

submitBtn.addEventListener("click", runForecast);

loadBusinessTypes();
loadRateSchedules();
