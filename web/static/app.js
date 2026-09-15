// หน้าเดียว มี 2 โหมดสลับด้วยแท็บ:
//   "adhoc"  (ค่าเริ่มต้น) พิมพ์ชื่อบริษัท + เลือกธุรกิจ/อัตรา ดูผลทันที ไม่บันทึกอะไรลงไฟล์เลย —
//            ชื่อบริษัทที่พิมพ์ "ไม่เคย" ถูกส่งไปที่เซิร์ฟเวอร์ (ดู runForecast(): body ที่ fetch
//            ไปยัง /api/forecast-adhoc มีแค่ business_type_code/rate_code/contract_kva เท่านั้น)
//   "search" ค้นหาผู้ใช้ไฟที่บันทึกไว้แล้วในทะเบียน (customers.csv/customers_local.csv) ด้วยเลขบัญชี

const PERIOD_COLOR = { P: "#2a78d6", OP: "#eb6834", H: "#1baf7a" };
const PERIOD_TH = { P: "Peak (P)", OP: "Off-Peak (OP)", H: "Holiday (H)" };

const resultArea = document.getElementById("result");
const emptyState = document.getElementById("empty-state");
const emptyStateText = document.getElementById("empty-state-text");

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

// ── สลับโหมดด้วยแท็บ (ไม่เปลี่ยนหน้า/URL) ──

const modeTabs = document.querySelectorAll(".mode-tab");
const adhocPanel = document.getElementById("adhoc-panel");
const searchPanel = document.getElementById("search-panel");

let currentMode = "adhoc";

function clearResult() {
  resultArea.innerHTML = "";
  resultArea.style.display = "none";
  emptyState.style.display = "flex";
}

function setMode(mode) {
  currentMode = mode;
  modeTabs.forEach((btn) => btn.classList.toggle("active", btn.dataset.mode === mode));
  adhocPanel.hidden = mode !== "adhoc";
  searchPanel.hidden = mode !== "search";
  emptyStateText.textContent =
    mode === "adhoc"
      ? 'กรอกข้อมูลด้านบนแล้วกด "พยากรณ์" เพื่อดูผลพยากรณ์'
      : 'พิมพ์เลขบัญชีผู้ใช้ไฟแล้วกด "ค้นหา" เพื่อดูผลพยากรณ์';
  clearResult();
}

modeTabs.forEach((btn) => btn.addEventListener("click", () => setMode(btn.dataset.mode)));

// ── โหมดค้นหาในทะเบียนลูกค้า ──

const searchInput = document.getElementById("search-input");
const searchBtn = document.getElementById("search-btn");
const searchHint = document.getElementById("search-hint");
const customerList = document.getElementById("customer-list");

async function loadCustomerList() {
  try {
    const res = await fetch("/api/customers");
    const customers = await res.json();
    customerList.innerHTML = customers.map((c) => `<option value="${c.account_no}">${c.name}</option>`).join("");
  } catch (err) {
    // ถ้าโหลดรายชื่อไม่สำเร็จ ยังพิมพ์เลขบัญชีค้นหาเองได้ตามปกติ ไม่ต้องบล็อกอะไร
    console.warn("โหลดรายชื่อผู้ใช้ไฟไม่สำเร็จ", err);
  }
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
      clearResult();
      searchHint.textContent = data.message || "เกิดข้อผิดพลาด";
      return;
    }

    const c = data.customer;
    renderResult(data, {
      name: c.name,
      subLabel: `บัญชีผู้ใช้ไฟ ${c.account_no}`,
      businessTypeCode: c.business_type_code,
      fields: [
        { label: "เลขบัญชีผู้ใช้ไฟ", value: c.account_no },
        { label: "ประเภทอัตรา", value: c.rate_code || "ไม่ทราบ" },
        { label: "KVA ตามสัญญา", value: c.contract_kva ? formatNumber(c.contract_kva) + " kVA" : "ไม่ทราบ" },
      ],
      extraField: null,
      disclaimerExtra: "",
    });
  } catch (err) {
    searchHint.textContent = "เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ";
    console.error(err);
  }
}

searchBtn.addEventListener("click", runSearch);
searchInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") runSearch();
});

// ── โหมดพยากรณ์แบบไม่บันทึกข้อมูล ──
// ประเภทธุรกิจ/รหัสอัตราที่เลือกได้ในโหมดนี้ ต้อง "มีโปรไฟล์อ้างอิงจริงรองรับ" เท่านั้น (มาจาก
// /api/load-profile-keys ซึ่งอ่านตรงจาก load_profiles.csv) — กันไม่ให้เลือกคู่ที่ไม่มีข้อมูลจริง
// มาจับกัน แล้วได้ผลแบบ fallback (BUSINESS_ONLY/RATE_ONLY) ที่ดูเหมือนจับคู่ผิดพลาดทั้งที่จริงๆ
// คือยังไม่มีข้อมูลของคู่นั้นให้จับแบบตรงเป๊ะได้ตั้งแต่แรก

const nameInput = document.getElementById("f-name");
const businessTypeSelect = document.getElementById("f-business-type");
const rateCodeSelect = document.getElementById("f-rate-code");
const kvaInput = document.getElementById("f-kva");
const adhocSubmitBtn = document.getElementById("adhoc-submit-btn");
const adhocFormHint = document.getElementById("adhoc-form-hint");

let PROFILE_KEYS = []; // [{business_type_code, rate_code, sample_size}, ...]
let BUSINESS_TYPE_NAMES = {}; // code -> name_th

async function loadBusinessTypesAndKeys() {
  try {
    const [typesRes, keysRes] = await Promise.all([fetch("/api/business-types"), fetch("/api/load-profile-keys")]);
    const types = await typesRes.json();
    PROFILE_KEYS = await keysRes.json();
    BUSINESS_TYPE_NAMES = Object.fromEntries(types.map((t) => [t.code, t.name_th]));

    const businessCodesWithData = [...new Set(PROFILE_KEYS.map((k) => k.business_type_code))];
    businessTypeSelect.innerHTML =
      `<option value="">-- ไม่ระบุ (จับคู่จากอัตราอย่างเดียว) --</option>` +
      businessCodesWithData
        .map((code) => `<option value="${code}">${BUSINESS_TYPE_NAMES[code] || code} · ${code}</option>`)
        .join("");

    updateRateCodeOptions();
  } catch (err) {
    console.warn("โหลดประเภทธุรกิจ/รหัสอัตราที่มีข้อมูลจริงไม่สำเร็จ", err);
  }
}

function updateRateCodeOptions() {
  const businessTypeCode = businessTypeSelect.value;
  const relevant = businessTypeCode ? PROFILE_KEYS.filter((k) => k.business_type_code === businessTypeCode) : PROFILE_KEYS;
  const rateCodes = [...new Set(relevant.map((k) => k.rate_code))];

  const previousValue = rateCodeSelect.value;
  rateCodeSelect.innerHTML = rateCodes.map((code) => `<option value="${code}">${code}</option>`).join("");
  if (rateCodes.includes(previousValue)) {
    rateCodeSelect.value = previousValue;
  }
}

businessTypeSelect.addEventListener("change", updateRateCodeOptions);

async function runForecast() {
  adhocFormHint.textContent = "";
  const displayName = nameInput.value.trim(); // ใช้แสดงผลเท่านั้น — ไม่ส่งไป server
  const businessTypeCode = businessTypeSelect.value.trim();
  const rateCode = rateCodeSelect.value.trim();
  const kvaRaw = kvaInput.value.trim();

  if (!businessTypeCode && !rateCode) {
    adhocFormHint.textContent = "กรุณาเลือกประเภทธุรกิจ หรือ กรอกรหัสอัตรา อย่างน้อยหนึ่งอย่าง";
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
      clearResult();
      adhocFormHint.textContent = data.message || "เกิดข้อผิดพลาด";
      return;
    }

    const kva = kvaRaw ? Number(kvaRaw) : null;
    renderResult(data, {
      name: displayName || "(ไม่ได้ระบุชื่อ)",
      subLabel: "พยากรณ์แบบไม่บันทึกข้อมูล — ไม่มีเลขบัญชีผู้ใช้ไฟ",
      businessTypeCode,
      fields: [
        { label: "ประเภทอัตราที่กรอก", value: rateCode || "ไม่ทราบ" },
        { label: "KVA ตามสัญญาที่กรอก", value: kva ? formatNumber(kva) + " kVA" : "ไม่ทราบ" },
      ],
      extraField: { label: "จำนวนตัวอย่างในโปรไฟล์", getValue: (p) => p.sample_size || "-" },
      disclaimerExtra: " และ<b>ไม่มีการบันทึกชื่อบริษัท/ข้อมูลที่กรอกในหน้านี้ลงไฟล์หรือฐานข้อมูลใดๆ ทั้งสิ้น</b>",
    });
  } catch (err) {
    adhocFormHint.textContent = "เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ";
    console.error(err);
  }
}

adhocSubmitBtn.addEventListener("click", runForecast);

// ── กราฟแท่ง P/OP/H ──

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
//    เฉลี่ยทั้งเดือน) พร้อมชี้จุดที่ใช้ไฟฟ้าสูงสุดจริงของวัน + แถบช่วงอัตรา Peak ตาม TOU ──

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
  const height = 230;
  const padX = 40;
  const padY = 40;
  const chartW = width - padX * 2;
  const chartH = height - padY * 2 - 16;
  const hourW = chartW / 24;
  const hourX = (h) => padX + hourW * h;

  const known = hours.filter((v) => v !== null && v !== undefined);
  if (!known.length) {
    return `<div style="padding:36px 0;text-align:center;color:#8996ab;font-size:13px;">ไม่มีข้อมูลสำหรับวันนี้ในช่วงที่นำเข้า AMR ไว้</div>`;
  }
  const max = Math.max(...known, 1);

  // แถบอัตรา Peak ตามช่วงเวลา TOU ของ กฟภ. (วันทำการ 09:00-22:00 เสมอ ไม่ว่าจริงๆ จะใช้ไฟ
  // เยอะช่วงนั้นหรือไม่) — ป้ายกำกับวางไว้ในแถบเอง ไม่ใช่จุดที่ใช้ไฟสูงสุดจริง (ดู peakPointMarker)
  const peakRect = WEEKDAY_DAY_TYPES.has(dayType)
    ? `<rect x="${hourX(9).toFixed(1)}" y="${padY}" width="${(hourX(22) - hourX(9)).toFixed(1)}" height="${chartH.toFixed(1)}" fill="#2a78d6" opacity="0.07"/>
       <rect x="${(((hourX(9) + hourX(22)) / 2) - 78).toFixed(1)}" y="${padY + 3}" width="156" height="15" rx="3" fill="#eef3fa" opacity="0.9"/>
       <text x="${((hourX(9) + hourX(22)) / 2).toFixed(1)}" y="${(padY + 14).toFixed(1)}" text-anchor="middle" font-size="10.5" font-weight="600" fill="#184f95">ช่วงอัตรา Peak (TOU) 09:00-22:00</text>`
    : "";

  const points = hours
    .map((v, h) => (v === null || v === undefined ? null : { x: hourX(h) + hourW / 2, y: padY + (1 - v / max) * chartH, v, h }))
    .filter(Boolean);

  // จุดที่ใช้ไฟฟ้าสูงสุดจริงของวัน (ไม่ใช่ช่วงอัตรา Peak ข้างบน) — ชี้ด้วยเส้นประ+จุดสีแดง
  const peakPoint = points.reduce((best, p) => (best === null || p.v > best.v ? p : best), null);
  const peakPointMarker = peakPoint
    ? `<line x1="${peakPoint.x.toFixed(1)}" y1="${padY}" x2="${peakPoint.x.toFixed(1)}" y2="${(padY + chartH).toFixed(1)}" stroke="#d03b3b" stroke-width="1.5" stroke-dasharray="4,3"/>
       <text x="${peakPoint.x.toFixed(1)}" y="${(padY - 26).toFixed(1)}" text-anchor="middle" font-size="11.5" font-weight="700" fill="#d03b3b">ใช้ไฟสูงสุด ${String(peakPoint.h).padStart(2, "0")}:00 น. (${formatNumber(peakPoint.v, 1)} kW)</text>
       <circle cx="${peakPoint.x.toFixed(1)}" cy="${peakPoint.y.toFixed(1)}" r="5.5" fill="#d03b3b" stroke="#ffffff" stroke-width="2"/>`
    : "";

  const polyline =
    points.length > 1
      ? `<polyline points="${points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ")}" fill="none" stroke="#2a78d6" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>`
      : "";
  const dots = points
    .filter((p) => p !== peakPoint)
    .map((p) => `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="3" fill="#2a78d6"/>`)
    .join("");

  const hourLabels = [0, 3, 6, 9, 12, 15, 18, 21]
    .map(
      (h) =>
        `<text x="${(hourX(h) + hourW / 2).toFixed(1)}" y="${height - 4}" text-anchor="middle" font-size="11" fill="#8996ab">${String(h).padStart(2, "0")}:00</text>`
    )
    .join("");
  const baseline = `<line x1="${padX}" y1="${(padY + chartH).toFixed(1)}" x2="${width - padX}" y2="${(padY + chartH).toFixed(1)}" stroke="#e1e0d9" stroke-width="1"/>`;

  return `
    <svg viewBox="0 0 ${width} ${height}" style="width:100%;height:auto;" preserveAspectRatio="xMidYMid meet">
      ${peakRect}${baseline}${polyline}${dots}${hourLabels}${peakPointMarker}
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
      ? `<div class="chart-caption"><span style="color:#d03b3b;font-weight:700;">●</span> จุด/เส้นประสีแดง คือช่วงเวลาที่ใช้ไฟฟ้าสูงสุดจริงของวันนี้ &nbsp; <span style="color:#184f95;font-weight:700;">■</span> แถบสีฟ้าอ่อน คือช่วงอัตรา Peak ตาม TOU (วันทำการ 09:00-22:00 — ไม่จำเป็นต้องตรงกับช่วงที่ใช้ไฟสูงสุดจริงเสมอไป)</div>`
      : `<div class="chart-caption"><span style="color:#d03b3b;font-weight:700;">●</span> จุด/เส้นประสีแดง คือช่วงเวลาที่ใช้ไฟฟ้าสูงสุดจริงของวันนี้ &nbsp; วันหยุดสุดสัปดาห์ทั้งวันเป็นอัตรา Holiday (H) ไม่มีช่วงอัตรา Peak</div>`;

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

// ── ผลลัพธ์รวม ใช้ร่วมกันทั้ง 2 โหมด — identity คือข้อมูลที่ต่างกันระหว่างโหมด (ชื่อ/เลขบัญชี
//    ที่มาของธุรกิจ/อัตรา ฯลฯ) ส่วน data (match/matched_profile/forecast/curve) รูปแบบเดียวกัน
//    ทั้งสอง endpoint (/api/forecast/<account_no> และ /api/forecast-adhoc) อยู่แล้ว ──

function renderResult(data, identity) {
  const m = data.match;
  const p = data.matched_profile;
  const f = data.forecast;

  const matchColor = m.is_exact ? "#0ca30c" : "#fab219";
  const matchBg = m.is_exact ? "#e8f7ec" : "#fff7e6";

  const businessBadge = identity.businessTypeCode
    ? `<span class="badge" style="background:#eef3fa;color:#184f95;">${p.business_type_name || identity.businessTypeCode} · ${identity.businessTypeCode}</span>`
    : `<span class="badge" style="background:rgba(15,23,42,0.05);color:#55647a;">ยังไม่จัดประเภทธุรกิจ</span>`;

  const fields = [...identity.fields, { label: "โปรไฟล์ที่ใช้อ้างอิง", value: `${p.business_type_name || p.business_type_code || "-"} / อัตรา ${p.rate_code}` }];
  if (identity.extraField) {
    fields.push({ label: identity.extraField.label, value: identity.extraField.getValue(p) });
  }

  resultArea.innerHTML = `
    <div class="card customer-card">
      <div class="customer-head">
        <div class="customer-head-left">
          <div class="customer-icon">${iconBuilding("#2a78d6")}</div>
          <div>
            <div class="customer-name">${identity.name}</div>
            <div class="customer-sub">${identity.subLabel}</div>
          </div>
        </div>
        <div class="customer-badges">
          ${businessBadge}
          <span class="badge" style="background:rgba(15,23,42,0.05);color:#55647a;">ไม่มี AMR ของตัวเอง</span>
        </div>
      </div>
      <div class="divider"></div>
      <div class="field-grid">
        ${fields.map((fl) => `<div class="field-item"><div class="field-label">${fl.label}</div><div class="field-value">${fl.value}</div></div>`).join("")}
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
      <div class="disclaimer-text">ค่าที่แสดงเป็นค่าพยากรณ์ คำนวณจากค่าเฉลี่ยของผู้ใช้ไฟกลุ่มธุรกิจและอัตราเดียวกัน ไม่ใช่ข้อมูลจากมิเตอร์ AMR ของผู้ใช้ไฟรายนี้โดยตรง เนื่องจากยังไม่มีการติดตั้ง AMR${identity.disclaimerExtra}</div>
    </div>
  `;

  emptyState.style.display = "none";
  resultArea.style.display = "flex";

  initDailyCurveSection(document.getElementById("daily-curve-root"), data.curve);
}

// ── เริ่มต้น ──

setMode("adhoc");
loadBusinessTypesAndKeys();
loadCustomerList();
