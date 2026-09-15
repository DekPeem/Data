const PERIOD_COLOR = { P: "#2a78d6", OP: "#eb6834", H: "#1baf7a" };
const PERIOD_TH = { P: "Peak (P)", OP: "Off-Peak (OP)", H: "Holiday (H)" };

const searchInput = document.getElementById("search-input");
const searchBtn = document.getElementById("search-btn");
const searchHint = document.getElementById("search-hint");
const resultArea = document.getElementById("result");
const emptyState = document.getElementById("empty-state");
const customerList = document.getElementById("customer-list");

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

async function loadCustomerList() {
  try {
    const res = await fetch("/api/customers");
    const customers = await res.json();
    customerList.innerHTML = customers
      .map((c) => `<option value="${c.account_no}">${c.name}</option>`)
      .join("");
  } catch (err) {
    // ถ้าโหลดรายชื่อไม่สำเร็จ ยังพิมพ์เลขบัญชีค้นหาเองได้ตามปกติ ไม่ต้องบล็อกอะไร
    console.warn("โหลดรายชื่อผู้ใช้ไฟไม่สำเร็จ", err);
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

// ── กราฟเส้น "การใช้ไฟฟ้ารายชั่วโมงใน 1 วัน" แยกดูตามวันในสัปดาห์ได้ (จันทร์-อาทิตย์ หรือ
//    เฉลี่ยทั้งเดือน) พร้อมชี้ช่วง Peak (09:00-22:00 วันทำการ) บนกราฟ ──

const DAY_TYPE_TH = {
  all: "เฉลี่ยทั้งเดือน",
  mon: "จันทร์",
  tue: "อังคาร",
  wed: "พุธ",
  thu: "พฤหัสบดี",
  fri: "ศุกร์",
  sat: "เสาร์",
  sun: "อาทิตย์",
};
const DAY_TYPE_ORDER = ["all", "mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const WEEKDAY_DAY_TYPES = new Set(["all", "mon", "tue", "wed", "thu", "fri"]);

function renderDailyCurveSVG(hours, dayType) {
  const width = 640;
  const height = 220;
  const padX = 40;
  const padY = 30;
  const chartW = width - padX * 2;
  const chartH = height - padY * 2 - 16;
  const hourW = chartW / 24;
  const hourX = (h) => padX + hourW * h;

  const known = hours.filter((v) => v !== null && v !== undefined);
  if (!known.length) {
    return `<div style="padding:36px 0;text-align:center;color:#8996ab;font-size:13px;">ไม่มีข้อมูลสำหรับวันนี้ในช่วงที่นำเข้า AMR ไว้</div>`;
  }
  const max = Math.max(...known, 1);

  const peakRect = WEEKDAY_DAY_TYPES.has(dayType)
    ? `<rect x="${hourX(9).toFixed(1)}" y="${padY}" width="${(hourX(22) - hourX(9)).toFixed(1)}" height="${chartH.toFixed(1)}" fill="#2a78d6" opacity="0.08"/>
       <text x="${((hourX(9) + hourX(22)) / 2).toFixed(1)}" y="${padY - 10}" text-anchor="middle" font-size="11" font-weight="700" fill="#184f95">ช่วง Peak (09:00-22:00)</text>`
    : "";

  const points = hours
    .map((v, h) => (v === null || v === undefined ? null : { x: hourX(h) + hourW / 2, y: padY + (1 - v / max) * chartH, v }))
    .filter(Boolean);

  const polyline =
    points.length > 1
      ? `<polyline points="${points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ")}" fill="none" stroke="#2a78d6" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>`
      : "";
  const dots = points.map((p) => `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="3" fill="#2a78d6"/>`).join("");

  const hourLabels = [0, 3, 6, 9, 12, 15, 18, 21]
    .map(
      (h) =>
        `<text x="${(hourX(h) + hourW / 2).toFixed(1)}" y="${height - 4}" text-anchor="middle" font-size="11" fill="#8996ab">${String(h).padStart(2, "0")}:00</text>`
    )
    .join("");
  const baseline = `<line x1="${padX}" y1="${(padY + chartH).toFixed(1)}" x2="${width - padX}" y2="${(padY + chartH).toFixed(1)}" stroke="#e1e0d9" stroke-width="1"/>`;

  return `
    <svg viewBox="0 0 ${width} ${height}" style="width:100%;height:auto;" preserveAspectRatio="xMidYMid meet">
      ${peakRect}${baseline}${polyline}${dots}${hourLabels}
    </svg>`;
}

function initDailyCurveSection(container, curveData) {
  if (!curveData || !curveData.available) {
    container.innerHTML = `
      <div class="card" style="padding:24px;color:#8996ab;font-size:13px;">
        ยังไม่มีข้อมูลกราฟการใช้ไฟฟ้ารายชั่วโมงสำหรับกลุ่มนี้ — ต้องนำเข้า AMR จริงที่มีข้อมูลราย 15 นาทีก่อน (ผ่านหน้า <a href="/admin">นำเข้า AMR (Admin)</a>)
      </div>`;
    return;
  }

  const availableDayTypes = DAY_TYPE_ORDER.filter((d) => curveData.day_types[d]);
  let selected = availableDayTypes.includes("all") ? "all" : availableDayTypes[0];

  function render() {
    const buttons = availableDayTypes
      .map((d) => `<button type="button" data-day="${d}" class="day-type-btn${d === selected ? " active" : ""}">${DAY_TYPE_TH[d]}</button>`)
      .join("");
    const caption = WEEKDAY_DAY_TYPES.has(selected)
      ? `<div class="chart-caption">แถบสีฟ้าอ่อนคือช่วง Peak (วันทำการ 09:00-22:00) — นอกแถบเป็น Off-Peak</div>`
      : `<div class="chart-caption">วันหยุดสุดสัปดาห์ — ทั้งวันเป็นอัตรา Holiday (H) ไม่มีช่วง Peak</div>`;

    container.innerHTML = `
      <div class="card chart-card">
        <div class="chart-title">การใช้ไฟฟ้าเฉลี่ยรายชั่วโมงใน 1 วัน (kW)</div>
        <div class="day-type-row">${buttons}</div>
        ${renderDailyCurveSVG(curveData.day_types[selected] || [], selected)}
        ${caption}
      </div>`;

    container.querySelectorAll(".day-type-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        selected = btn.dataset.day;
        render();
      });
    });
  }

  render();
}

function renderStatTiles(demand, energy) {
  const rows = ["P", "OP", "H"].flatMap((period) => [
    { period, value: demand[period], unit: "kW", label: "กำลังไฟฟ้าสูงสุด", digits: 2 },
    { period, value: energy[period], unit: "kWh", label: "พลังงานไฟฟ้า / เดือน", digits: 0 },
  ]);
  // จัดเป็นแถวกำลังไฟฟ้าก่อน แล้วค่อยพลังงาน (เหมือน mockup)
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

function renderResult(data) {
  const c = data.customer;
  const m = data.match;
  const p = data.matched_profile;
  const f = data.forecast;

  const matchColor = m.is_exact ? "#0ca30c" : "#fab219";
  const matchBg = m.is_exact ? "#e8f7ec" : "#fff7e6";

  const businessBadge = c.business_type_code
    ? `<span class="badge" style="background:#eef3fa;color:#184f95;">${p.business_type_name || c.business_type_code} · ${c.business_type_code}</span>`
    : `<span class="badge" style="background:rgba(15,23,42,0.05);color:#55647a;">ยังไม่จัดประเภทธุรกิจ</span>`;

  resultArea.innerHTML = `
    <div class="card customer-card">
      <div class="customer-head">
        <div class="customer-head-left">
          <div class="customer-icon">${iconBuilding("#2a78d6")}</div>
          <div>
            <div class="customer-name">${c.name}</div>
            <div class="customer-sub">บัญชีผู้ใช้ไฟ ${c.account_no}</div>
          </div>
        </div>
        <div class="customer-badges">
          ${businessBadge}
          <span class="badge" style="background:rgba(15,23,42,0.05);color:#55647a;">ไม่มี AMR ของตัวเอง</span>
        </div>
      </div>
      <div class="divider"></div>
      <div class="field-grid">
        <div class="field-item"><div class="field-label">เลขบัญชีผู้ใช้ไฟ</div><div class="field-value">${c.account_no}</div></div>
        <div class="field-item"><div class="field-label">ประเภทอัตรา</div><div class="field-value">${c.rate_code || "ไม่ทราบ"}</div></div>
        <div class="field-item"><div class="field-label">KVA ตามสัญญา</div><div class="field-value">${c.contract_kva ? formatNumber(c.contract_kva) + " kVA" : "ไม่ทราบ"}</div></div>
        <div class="field-item"><div class="field-label">โปรไฟล์ที่ใช้อ้างอิง</div><div class="field-value">${p.business_type_name || p.business_type_code || "-"} / อัตรา ${p.rate_code}</div></div>
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
    </div>

    <div id="daily-curve-root" style="margin-top:4px;"></div>

    <div class="disclaimer">
      ${iconInfo("#55647a")}
      <div class="disclaimer-text">ค่าที่แสดงเป็นค่าพยากรณ์ คำนวณจากค่าเฉลี่ยของผู้ใช้ไฟกลุ่มธุรกิจและอัตราเดียวกัน ไม่ใช่ข้อมูลจากมิเตอร์ AMR ของผู้ใช้ไฟรายนี้โดยตรง เนื่องจากยังไม่มีการติดตั้ง AMR</div>
    </div>
  `;

  emptyState.style.display = "none";
  resultArea.style.display = "flex";

  initDailyCurveSection(document.getElementById("daily-curve-root"), data.curve);
}

async function runSearch() {
  const q = searchInput.value.trim();
  searchHint.textContent = "";
  if (!q) {
    searchHint.textContent = "กรุณาพิมพ์เลขบัญชีผู้ใช้ไฟ";
    return;
  }

  try {
    const res = await fetch(`/api/forecast/${encodeURIComponent(q)}`);
    const data = await res.json();

    if (!res.ok) {
      resultArea.style.display = "none";
      emptyState.style.display = "flex";
      searchHint.textContent = data.message || "เกิดข้อผิดพลาด";
      return;
    }

    renderResult(data);
  } catch (err) {
    searchHint.textContent = "เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ";
    console.error(err);
  }
}

searchBtn.addEventListener("click", runSearch);
searchInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") runSearch();
});

loadCustomerList();
