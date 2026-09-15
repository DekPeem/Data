// กราฟเส้นโค้งการใช้ไฟฟ้ารายชั่วโมง (SVG) — ใช้ร่วมกันทั้งหน้าเว็บหลัก (app.js, ตอนแสดงผลพยากรณ์)
// และหน้า Admin (admin.js, ตอนดูรูปแบบกราฟดิบของแต่ละประเภทธุรกิจ ก่อนจะเอาไปพยากรณ์)

function formatNumber(n, digits = 0) {
  return n.toLocaleString("th-TH", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

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
