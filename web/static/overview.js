// หน้า "ภาพรวมลูกค้าทั้งหมด" — รวมทะเบียนลูกค้า (/api/customers) เข้ากับรายชื่อประเภทธุรกิจ
// แบบละเอียด (/api/business-types-full) เพื่อโชว์เป็นตารางเดียว: ชื่อ / ธุรกิจ / หมวด TSIC /
// รหัสอัตรา / Solar / มี AMR จริงหรือยัง — ไม่มี endpoint ใหม่ ใช้ข้อมูลที่มีอยู่แล้วทั้งหมด
//
// "ก่อตั้งเมื่อไหร่" ไม่มีอยู่ในตารางนี้ เพราะไม่มีแหล่งข้อมูลนี้เก็บไว้ที่ไหนในระบบเลย (ดู
// customers.csv/customers_local.csv และ dbd_lookup.py — ไม่มีฟิลด์วันจดทะเบียน/ก่อตั้ง)

const tbody = document.getElementById("overview-tbody");
const emptyState = document.getElementById("overview-empty");
const countEl = document.getElementById("overview-count");
const searchBox = document.getElementById("search-box");

let customers = [];
let businessTypeByCode = {};

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
    const [customersRes, businessTypesRes] = await Promise.all([
      fetch("/api/customers"),
      fetch("/api/business-types-full"),
    ]);
    customers = await customersRes.json();
    const businessTypes = await businessTypesRes.json();
    businessTypeByCode = Object.fromEntries(businessTypes.map((bt) => [bt.code, bt]));

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
