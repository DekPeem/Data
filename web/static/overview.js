// หน้า "ภาพรวมลูกค้าทั้งหมด" — รวม 2 แหล่งข้อมูลเข้าด้วยกัน (key ด้วย account_no):
//   1. /api/customers        — ทะเบียนลูกค้าที่ "ลงทะเบียนไว้ล่วงหน้า" (customers.csv ของ repo
//      มีแต่แถว DEMO สมมติ + customers_local.csv ถ้ามี) อาจยังไม่มี AMR จริงก็ได้
//   2. /api/import-log-local — ประวัติการนำเข้า AMR จริงในเครื่องนี้ (import_log_local.csv มี
//      ชื่อบริษัท/เลขบัญชีจริง) นี่คือแหล่งข้อมูลจริงส่วนใหญ่ที่ผู้ใช้เจอเวลานำเข้าไฟล์ AMR เอง
//      ไม่เคยถูกเขียนลง customers_local.csv เลย ถ้าดึงแค่ /api/customers อย่างเดียวจะไม่เห็น
//      ข้อมูลจริงที่นำเข้าไปแล้วเลย (เจอปัญหานี้จริงตอนทดสอบ — เห็นแต่ DEMO)
// ถ้าบัญชีเดียวกันมีทั้ง 2 แหล่ง ใช้ข้อมูลจาก import log (ใหม่กว่า/เป็นของจริงที่เพิ่งนำเข้า) ทับ
// ทะเบียนลูกค้า — import log อาจมีหลายแถวต่อบัญชี (นำเข้าซ้ำหลายรอบ) เอาแถวล่าสุดต่อบัญชี
// (API คืนใหม่สุดก่อนอยู่แล้ว) ไม่มี endpoint ใหม่ ใช้ของที่มีอยู่แล้วทั้งหมด
//
// "ก่อตั้งเมื่อไหร่" ไม่มีอยู่ในตารางนี้ เพราะไม่มีแหล่งข้อมูลนี้เก็บไว้ที่ไหนในระบบเลย (ดู
// customers.csv/customers_local.csv และ dbd_lookup.py — ไม่มีฟิลด์วันจดทะเบียน/ก่อตั้ง)

const tbody = document.getElementById("overview-tbody");
const emptyState = document.getElementById("overview-empty");
const countEl = document.getElementById("overview-count");
const searchBox = document.getElementById("search-box");

let customers = [];
let businessTypeByCode = {};

function mergeCustomersWithImportLog(registryCustomers, importLogEntries) {
  const byAccount = new Map();
  for (const c of registryCustomers) {
    if (c.account_no) byAccount.set(c.account_no, { ...c });
  }

  // importLogEntries มาจาก /api/import-log-local ซึ่งเรียงใหม่สุดก่อนอยู่แล้ว — ใช้ Set กันไม่ให้
  // แถวเก่ากว่าของบัญชีเดียวกัน (นำเข้าซ้ำหลายรอบ) มาทับแถวล่าสุดที่ประมวลผลไปแล้ว
  const seenFromLog = new Set();
  for (const entry of importLogEntries) {
    const accountNo = entry.account_no;
    if (!accountNo || seenFromLog.has(accountNo)) continue;
    seenFromLog.add(accountNo);

    const existing = byAccount.get(accountNo) || { account_no: accountNo };
    byAccount.set(accountNo, {
      ...existing,
      name: entry.company_name || existing.name,
      business_type_code: entry.business_type_code || existing.business_type_code,
      rate_code: entry.rate_code || existing.rate_code,
      has_solar: entry.has_solar === "true" ? true : entry.has_solar === "false" ? false : existing.has_solar,
      has_amr: true,
    });
  }

  return Array.from(byAccount.values());
}

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function solarCell(hasSolar) {
  if (hasSolar === true) return `<span class="pill-yes">☀️ ติดแล้ว</span>`;
  if (hasSolar === false) return `<span class="pill-no">— ยังไม่ติด</span>`;
  return `<span class="pill-unknown">ไม่ทราบ</span>`;
}

function renderRows(list) {
  tbody.innerHTML = "";
  emptyState.style.display = list.length === 0 ? "flex" : "none";
  countEl.textContent = `ทั้งหมด ${list.length} ราย`;

  for (const c of list) {
    const bt = businessTypeByCode[c.business_type_code];
    const businessLabel = bt ? escapeHtml(bt.name_th) : c.business_type_code ? escapeHtml(c.business_type_code) : "ยังไม่ระบุ";
    const sectionLabel = bt && bt.section_name_th ? `${bt.section_code} · ${escapeHtml(bt.section_name_th)}` : "-";
    const rateCell = c.rate_code
      ? `${escapeHtml(c.rate_code)}`
      : `<span class="pill-muted">ยังไม่มี</span>`;
    const amrCell = c.has_amr ? `<span class="pill-yes">✅ มีแล้ว</span>` : `<span class="pill-muted">ยังไม่มี</span>`;

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>
        ${escapeHtml(c.name) || "(ไม่ทราบชื่อ)"}
        <div class="cell-sub">บัญชี ${escapeHtml(c.account_no) || "-"}</div>
      </td>
      <td>${businessLabel}</td>
      <td>${sectionLabel}</td>
      <td>${rateCell}</td>
      <td><span class="pill-muted" title="ยังไม่มีแหล่งข้อมูลนี้ในระบบ">ไม่มีข้อมูล</span></td>
      <td>${solarCell(c.has_solar)}</td>
      <td>${amrCell}</td>
    `;
    tbody.appendChild(tr);
  }
}

function applyFilter() {
  const q = searchBox.value.trim().toLowerCase();
  if (!q) {
    renderRows(customers);
    return;
  }
  const filtered = customers.filter((c) => {
    const bt = businessTypeByCode[c.business_type_code];
    const haystack = [c.name, c.account_no, c.business_type_code, bt && bt.name_th, bt && bt.section_name_th]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(q);
  });
  renderRows(filtered);
}

async function load() {
  try {
    const [customersRes, importLogRes, businessTypesRes] = await Promise.all([
      fetch("/api/customers"),
      fetch("/api/import-log-local"),
      fetch("/api/business-types-full"),
    ]);
    const registryCustomers = await customersRes.json();
    const importLogEntries = await importLogRes.json();
    const businessTypes = await businessTypesRes.json();
    businessTypeByCode = Object.fromEntries(businessTypes.map((bt) => [bt.code, bt]));

    customers = mergeCustomersWithImportLog(registryCustomers, importLogEntries);
    customers.sort((a, b) => (a.name || "").localeCompare(b.name || "", "th"));
    renderRows(customers);
  } catch (err) {
    console.error("โหลดข้อมูลภาพรวมไม่สำเร็จ", err);
    emptyState.textContent = "โหลดข้อมูลไม่สำเร็จ ลองรีเฟรชหน้าใหม่อีกครั้ง";
    emptyState.style.display = "flex";
  }
}

searchBox.addEventListener("input", applyFilter);
load();
