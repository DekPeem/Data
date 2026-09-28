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

// แถบช่วงอัตรา TOU ของ กฟภ. — ใช้ร่วมกันทั้งกราฟเส้น (renderDailyCurveSVG) และกราฟ Boxplot
// (renderDailyBoxplotSVG) แสดงทั้ง 2 ช่วงชัดเจนเสมอ (ไม่ใช่แค่ Peak แบบเดิม): คาบ Peak (P)
// 09:00-22:00 กับคาบ Off-Peak (OP) 22:00-09:00 (ข้ามเที่ยงคืน จึงต้องวาดเป็น 2 แท่งแยก: 22:00-24:00
// กับ 00:00-09:00) — เฉพาะวันทำการเท่านั้น (WEEKDAY_DAY_TYPES) วันหยุดสุดสัปดาห์ทั้งวันเป็นอัตรา
// Holiday (H) ไม่มีช่วง P/OP ให้แบ่งเลย จึงไม่วาดแถบอะไรเลยสำหรับ dayType นอกกลุ่มนี้
function _touZonesSVG(dayType, hourX, padY, chartH) {
  if (!WEEKDAY_DAY_TYPES.has(dayType)) return "";

  const peakMidX = (hourX(9) + hourX(22)) / 2;
  const opRect = (x0, x1) => `<rect x="${x0.toFixed(1)}" y="${padY}" width="${(x1 - x0).toFixed(1)}" height="${chartH.toFixed(1)}" fill="#8996ab" opacity="0.08"/>`;

  return `
    <rect x="${hourX(9).toFixed(1)}" y="${padY}" width="${(hourX(22) - hourX(9)).toFixed(1)}" height="${chartH.toFixed(1)}" fill="#2a78d6" opacity="0.07"/>
    ${opRect(hourX(22), hourX(24))}
    ${opRect(hourX(0), hourX(9))}
    <rect x="${(peakMidX - 78).toFixed(1)}" y="${padY + 3}" width="156" height="15" rx="3" fill="#eef3fa" opacity="0.9"/>
    <text x="${peakMidX.toFixed(1)}" y="${(padY + 14).toFixed(1)}" text-anchor="middle" font-size="10.5" font-weight="600" fill="#184f95">ช่วงอัตรา Peak (TOU) 09:00-22:00</text>
    <rect x="${(hourX(0) + 4).toFixed(1)}" y="${padY + 3}" width="118" height="15" rx="3" fill="#eef3fa" opacity="0.9"/>
    <text x="${(hourX(0) + 63).toFixed(1)}" y="${(padY + 14).toFixed(1)}" text-anchor="middle" font-size="10.5" font-weight="600" fill="#55647a">Off-Peak 22:00-09:00</text>`;
}

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

  const peakRect = _touZonesSVG(dayType, hourX, padY, chartH);

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

// กราฟ Boxplot รายชั่วโมง — ใช้แทน renderDailyCurveSVG เมื่อมีข้อมูลการกระจายตัวจริงจากหลายไซต์
// (boxHours มาจาก /api/*/boxplot ผ่าน curve_stats.compute_hourly_boxplot ฝั่ง backend) แต่ละชั่วโมง
// วาดกล่อง Q1-Q3 + เส้น median + เส้นหนวดถึง min/max ชั่วโมงไหนไม่มีข้อมูลพอ (n < 2, ค่าเป็น null)
// จะ fallback ไปวาดแค่จุดค่าเฉลี่ย (meanHours) แทน ไม่ให้กราฟมีช่องว่างเฉยๆ
function renderDailyBoxplotSVG(meanHours, boxHours, dayType) {
  const width = 640;
  const height = 230;
  const padX = 40;
  const padY = 40;
  const chartW = width - padX * 2;
  const chartH = height - padY * 2 - 16;
  const hourW = chartW / 24;
  const hourX = (h) => padX + hourW * h;

  const allValues = [];
  boxHours.forEach((b, h) => {
    if (b) {
      allValues.push(b.min, b.max);
    } else if (meanHours[h] !== null && meanHours[h] !== undefined) {
      allValues.push(meanHours[h]);
    }
  });
  if (!allValues.length) {
    return `<div style="padding:36px 0;text-align:center;color:#8996ab;font-size:13px;">ไม่มีข้อมูลสำหรับวันนี้ในช่วงที่นำเข้า AMR ไว้</div>`;
  }
  const max = Math.max(...allValues, 1);
  const y = (v) => padY + (1 - v / max) * chartH;

  const zones = _touZonesSVG(dayType, hourX, padY, chartH);
  const boxWidth = hourW * 0.55;
  const whiskerCapWidth = boxWidth * 0.5;

  const boxes = boxHours
    .map((b, h) => {
      const cx = hourX(h) + hourW / 2;
      if (!b) {
        const v = meanHours[h];
        if (v === null || v === undefined) return "";
        return `<circle cx="${cx.toFixed(1)}" cy="${y(v).toFixed(1)}" r="3" fill="#8996ab"/>`;
      }
      const x0 = cx - boxWidth / 2;
      const yMin = y(b.min);
      const yMax = y(b.max);
      const yQ1 = y(b.q1);
      const yQ3 = y(b.q3);
      const yMed = y(b.median);
      return `
        <line x1="${cx.toFixed(1)}" y1="${yMin.toFixed(1)}" x2="${cx.toFixed(1)}" y2="${yMax.toFixed(1)}" stroke="#8996ab" stroke-width="1.3"/>
        <line x1="${(cx - whiskerCapWidth / 2).toFixed(1)}" y1="${yMin.toFixed(1)}" x2="${(cx + whiskerCapWidth / 2).toFixed(1)}" y2="${yMin.toFixed(1)}" stroke="#8996ab" stroke-width="1.3"/>
        <line x1="${(cx - whiskerCapWidth / 2).toFixed(1)}" y1="${yMax.toFixed(1)}" x2="${(cx + whiskerCapWidth / 2).toFixed(1)}" y2="${yMax.toFixed(1)}" stroke="#8996ab" stroke-width="1.3"/>
        <rect x="${x0.toFixed(1)}" y="${Math.min(yQ1, yQ3).toFixed(1)}" width="${boxWidth.toFixed(1)}" height="${Math.max(Math.abs(yQ3 - yQ1), 1).toFixed(1)}" fill="#2a78d6" fill-opacity="0.32" stroke="#2a78d6" stroke-width="1.2"/>
        <line x1="${x0.toFixed(1)}" y1="${yMed.toFixed(1)}" x2="${(x0 + boxWidth).toFixed(1)}" y2="${yMed.toFixed(1)}" stroke="#184f95" stroke-width="2"/>`;
    })
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
      ${zones}${baseline}${boxes}${hourLabels}
    </svg>`;
}

function initDailyCurveSection(container, curveData, boxplotData) {
  // มีอย่างน้อยอย่างใดอย่างหนึ่ง (เส้นเฉลี่ย หรือ Boxplot) พอแสดงได้ไหม — บางกรณี (เช่น ไซต์จริง
  // ในเครื่องนี้ >= 2 แห่งของคู่ธุรกิจ+อัตรา+has_solar นี้ แต่ยังไม่เคย commit เส้นค่าเฉลี่ยแบบ
  // anonymized เข้า load_curves.csv) มี Boxplot ได้ทั้งที่เส้นเฉลี่ยยังไม่มีก็ได้ ไม่ควรซ่อนไปเฉยๆ
  const hasCurve = Boolean(curveData && curveData.available);
  const hasBoxplot = Boolean(boxplotData && boxplotData.available);
  if (!hasCurve && !hasBoxplot) {
    container.innerHTML = `
      <div class="card" style="padding:24px;color:#8996ab;font-size:13px;">
        ยังไม่มีข้อมูลกราฟการใช้ไฟฟ้ารายชั่วโมงสำหรับกลุ่มนี้ — ต้องนำเข้า AMR จริงที่มีข้อมูลราย 15 นาทีก่อน (ผ่านหน้า <a href="/admin">นำเข้า AMR (Admin)</a>)
      </div>`;
    return;
  }

  const curveDayTypes = hasCurve ? Object.keys(curveData.day_types) : [];
  const boxplotDayTypes = hasBoxplot ? Object.keys(boxplotData.day_types) : [];
  const availableDayTypes = DAY_TYPE_ORDER.filter((d) => curveDayTypes.includes(d) || boxplotDayTypes.includes(d));
  let selected = availableDayTypes.includes("all") ? "all" : availableDayTypes[0];

  function render() {
    const buttons = availableDayTypes
      .map((d) => `<button type="button" data-day="${d}" class="day-type-btn${d === selected ? " active" : ""}">${DAY_TYPE_TH[d]}</button>`)
      .join("");

    // มีข้อมูล Boxplot จริงของวันที่เลือกอยู่ไหม (อย่างน้อย 1 ชม. ต้องมี n >= 2 ไซต์ ไม่งั้นวาด
    // เป็นกล่องไม่ได้จริง) — ถ้าไม่มีก็วาดกราฟเส้นเฉลี่ยแบบเดิม (fallback)
    const boxDayData = boxplotData && boxplotData.available ? boxplotData.day_types[selected] : null;
    const hasBoxData = Boolean(boxDayData && boxDayData.some((b) => b !== null));
    const maxSampleCount = hasBoxData ? Math.max(...boxDayData.filter(Boolean).map((b) => b.n)) : 0;

    const meanHours = (hasCurve && curveData.day_types[selected]) || [];
    const chartHtml = hasBoxData ? renderDailyBoxplotSVG(meanHours, boxDayData, selected) : renderDailyCurveSVG(meanHours, selected);

    const touCaption = WEEKDAY_DAY_TYPES.has(selected)
      ? `<span style="color:#184f95;font-weight:700;">■</span> แถบสีฟ้า/เทาอ่อน คือคาบ Peak/Off-Peak ตาม TOU (วันทำการ 09:00-22:00 / 22:00-09:00 — ไม่จำเป็นต้องตรงกับช่วงที่ใช้ไฟสูงสุดจริงเสมอไป)`
      : `วันหยุดสุดสัปดาห์ทั้งวันเป็นอัตรา Holiday (H) ไม่มีช่วง Peak/Off-Peak`;
    const caption = hasBoxData
      ? `<div class="chart-caption">📦 กล่อง = ช่วง Q1-Q3, เส้นกลางกล่อง = ค่ากลาง (median), เส้นหนวด = ค่าต่ำสุด-สูงสุด — คำนวณจากไซต์จริงในเครื่องนี้สูงสุด ${maxSampleCount} แห่ง &nbsp; ${touCaption}</div>`
      : `<div class="chart-caption"><span style="color:#d03b3b;font-weight:700;">●</span> จุด/เส้นประสีแดง คือช่วงเวลาที่ใช้ไฟฟ้าสูงสุดจริงของวันนี้ &nbsp; ${touCaption}</div>`;

    container.innerHTML = `
      <div class="card chart-card">
        <div class="chart-title">การใช้ไฟฟ้า${hasBoxData ? "" : "เฉลี่ย"}รายชั่วโมงใน 1 วัน (kW)</div>
        <div class="day-type-row">${buttons}</div>
        ${chartHtml}
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
