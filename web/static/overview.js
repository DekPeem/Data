// หน้า "ภาพรวมลูกค้าทั้งหมด" — รวม 2 แหล่งข้อมูลเข้าด้วยกัน (key ด้วย account_no):
//   1. /api/customers        — ทะเบียนลูกค้าที่ "ลงทะเบียนไว้ล่วงหน้า" (customers.csv ของ repo
//      มีแต่แถว DEMO สมมติ + customers_local.csv ถ้ามี) อาจยังไม่มี AMR จริงก็ได้
//   2. /api/import-log-local — ประวัติการนำเข้า AMR จริงในเครื่องนี้ (import_log_local.csv มี
//      ชื่อบริษัท/เลขบัญชีจริง) นี่คือแหล่งข้อมูลจริงส่วนใหญ่ที่ผู้ใช้เจอเวลานำเข้าไฟล์ AMR เอง
//      ไม่เคยถูกเขียนลง customers_local.csv เลย ถ้าดึงแค่ /api/customers อย่างเดียวจะไม่เห็น
//      ข้อมูลจริงที่นำเข้าไปแล้วเลย (เจอปัญหานี้จริงตอนทดสอบ — เห็นแต่ DEMO)
// ถ้าบัญชีเดียวกันมีทั้ง 2 แหล่ง ใช้ข้อมูลจาก import log (ใหม่กว่า/เป็นของจริงที่เพิ่งนำเข้า) ทับ
// ทะเบียนลูกค้า — import log อาจมีหลายแถวต่อบัญชี (นำเข้าซ้ำหลายรอบ) เอาแถวล่าสุดต่อบัญชี
// (API คืนใหม่สุดก่อนอยู่แล้ว) ไม่มี endpoint ใหม่สำหรับอ่าน ใช้ของที่มีอยู่แล้วทั้งหมด
//
// แถว DEMO (customers.csv สาธิต — account_no ขึ้นต้นด้วย "DEMO-" เสมอตามธรรมเนียมของ repo นี้)
// ถูกกรองทิ้งไม่ให้ขึ้นในตารางนี้ เพราะเป็นข้อมูลสมมติ ไม่ใช่ลูกค้าจริง
//
// จัดกลุ่มแถวตาม Section (TSIC A-U) พร้อมแถบปุ่มกรองด่วน — คำนวณจากรายชื่อ section ที่เจอจริง
// ในข้อมูลปัจจุบันเท่านั้น (ไม่ fix รายชื่อ 21 หมวดไว้ตายตัว กันปุ่มเยอะเกินจำเป็นตอนข้อมูลน้อย)
//
// "ใช้ไฟเฉลี่ย/เดือน" และ "Peak สูงสุด/วัน" คำนวณจากกราฟรายชั่วโมงจริงของแต่ละไซต์ (ดึงจาก
// /api/admin/site-curve/<account_no> ซึ่งอ่านจาก site_curves_local.csv) — ใช้ค่าเฉลี่ยกำลังไฟฟ้า
// (kW) รายชั่วโมงของ day_type "all" (ค่าเฉลี่ยรวมทุกวันในช่วงที่นำเข้า ไม่แยกวันธรรมดา/วันหยุด):
//   Peak สูงสุด/วัน = max(hours["all"]) หน่วย kW
//   ใช้ไฟเฉลี่ย/เดือน = sum(hours["all"]) หน่วย kWh/วัน (avg kW ต่อชม. x 1 ชม. = kWh ของชม.นั้น)
//                       คูณ 30 วัน โดยประมาณ
// มีเฉพาะบัญชีที่นำเข้า AMR จริงแบบรู้เลขบัญชี (ผ่านโหมด auto/ไฟล์ที่อ่านเลขบัญชีได้) เท่านั้น —
// บัญชีที่ลงทะเบียนไว้ล่วงหน้าอย่างเดียวไม่มีกราฟให้คำนวณ จะแสดง "ไม่มีข้อมูล"
//
// แก้ไขได้ในตาราง (ปุ่ม "แก้ไข" ต่อแถว) — บันทึกผ่าน PATCH /api/admin/overview-entry ซึ่งเขียนลง
// customers_local.csv (upsert ตาม account_no) มีผลกับทั้งระบบทันที ต้องใส่รหัสผ่านก่อนบันทึกได้
// (รหัสผ่านตั้งค่าไว้ที่เครื่อง server ผ่าน env var ADMIN_EDIT_PASSWORD — ดู .env.example) แคช
// รหัสผ่านที่พิมพ์ถูกไว้ใน sessionStorage เพื่อไม่ต้องพิมพ์ซ้ำทุกแถวในเซสชันเดียวกัน

const tbody = document.getElementById("overview-tbody");
const emptyState = document.getElementById("overview-empty");
const countEl = document.getElementById("overview-count");
const searchBox = document.getElementById("search-box");
const sectionFilterBar = document.getElementById("section-filter-bar");

const SESSION_PASSWORD_KEY = "overviewEditPassword";
const UNCLASSIFIED_SECTION_KEY = "__unclassified__";

let customers = [];
let businessTypeByCode = {};
let usageStatsByAccount = {};
let editingAccountNo = null;
let activeSectionFilter = null; // null = ทั้งหมด

function mergeCustomersWithImportLog(registryCustomers, importLogEntries) {
  const byAccount = new Map();
  for (const c of registryCustomers) {
    if (c.account_no && !c.account_no.startsWith("DEMO-")) byAccount.set(c.account_no, { ...c });
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

function businessLabelOf(c) {
  const bt = businessTypeByCode[c.business_type_code];
  return bt ? bt.name_th : c.business_type_code ? c.business_type_code : "ยังไม่ระบุ";
}

function sectionOf(c) {
  return businessTypeByCode[c.business_type_code] || null;
}

function sectionKeyOf(c) {
  const bt = sectionOf(c);
  return bt && bt.section_code ? bt.section_code : UNCLASSIFIED_SECTION_KEY;
}

function sectionLabelOf(c) {
  const bt = sectionOf(c);
  return bt && bt.section_name_th ? `${bt.section_code} · ${bt.section_name_th}` : "-";
}

function usageCells(accountNo) {
  const stats = usageStatsByAccount[accountNo];
  if (!stats) {
    return {
      monthlyKwh: `<span class="pill-muted" title="ไม่มีกราฟรายชั่วโมงของบัญชีนี้ (ยังไม่เคยนำเข้า AMR แบบรู้เลขบัญชี)">ไม่มีข้อมูล</span>`,
      peakKw: `<span class="pill-muted">ไม่มีข้อมูล</span>`,
    };
  }
  return {
    monthlyKwh: `${stats.monthlyKwh.toLocaleString("th-TH", { maximumFractionDigits: 0 })} kWh`,
    peakKw: `${stats.peakKw.toLocaleString("th-TH", { maximumFractionDigits: 1 })} kW`,
  };
}

function renderViewRow(c) {
  const rateCell = c.rate_code ? escapeHtml(c.rate_code) : `<span class="pill-muted">ยังไม่มี</span>`;
  const amrCell = c.has_amr ? `<span class="pill-yes">✅ มีแล้ว</span>` : `<span class="pill-muted">ยังไม่มี</span>`;
  const usage = usageCells(c.account_no);

  return `
    <td>
      ${escapeHtml(c.name) || "(ไม่ทราบชื่อ)"}
      <div class="cell-sub">บัญชี ${escapeHtml(c.account_no) || "-"}</div>
    </td>
    <td>${escapeHtml(businessLabelOf(c))}</td>
    <td>${escapeHtml(sectionLabelOf(c))}</td>
    <td>${rateCell}</td>
    <td>${usage.monthlyKwh}</td>
    <td>${usage.peakKw}</td>
    <td>${solarCell(c.has_solar)}</td>
    <td>${amrCell}</td>
    <td>
      <div class="row-actions">
        <button type="button" class="btn-tiny" data-action="edit" data-account="${escapeHtml(c.account_no)}">แก้ไข</button>
      </div>
    </td>
  `;
}

function renderEditRow(c) {
  const resolvedLabel = businessLabelOf(c);
  const solarValue = c.has_solar === true ? "true" : c.has_solar === false ? "false" : "";
  const usage = usageCells(c.account_no);

  return `
    <td>
      <input type="text" class="edit-input" data-field="name" value="${escapeHtml(c.name)}">
      <div class="cell-sub">บัญชี ${escapeHtml(c.account_no) || "-"}</div>
    </td>
    <td>
      <input type="text" class="edit-input" data-field="business_type_code" value="${escapeHtml(c.business_type_code || "")}" placeholder="เช่น 26109">
      <div class="edit-resolved-label" data-role="resolved-business">${escapeHtml(resolvedLabel)}</div>
    </td>
    <td>${escapeHtml(sectionLabelOf(c))}</td>
    <td><input type="text" class="edit-input" data-field="rate_code" value="${escapeHtml(c.rate_code || "")}" placeholder="เช่น 50"></td>
    <td>${usage.monthlyKwh}</td>
    <td>${usage.peakKw}</td>
    <td>
      <select class="edit-input" data-field="has_solar">
        <option value="" ${solarValue === "" ? "selected" : ""}>ไม่ทราบ</option>
        <option value="true" ${solarValue === "true" ? "selected" : ""}>ติดแล้ว</option>
        <option value="false" ${solarValue === "false" ? "selected" : ""}>ยังไม่ติด</option>
      </select>
    </td>
    <td>${c.has_amr ? `<span class="pill-yes">✅ มีแล้ว</span>` : `<span class="pill-muted">ยังไม่มี</span>`}</td>
    <td>
      <div class="row-actions">
        <button type="button" class="btn-tiny btn-tiny-primary" data-action="save" data-account="${escapeHtml(c.account_no)}">บันทึก</button>
        <button type="button" class="btn-tiny" data-action="cancel" data-account="${escapeHtml(c.account_no)}">ยกเลิก</button>
      </div>
      <div class="edit-hint" data-role="edit-hint"></div>
    </td>
  `;
}

const COLUMN_COUNT = 9;

function renderSectionFilterBar() {
  const seen = new Map(); // section_code -> section_name_th
  let hasUnclassified = false;
  for (const c of customers) {
    const bt = sectionOf(c);
    if (bt && bt.section_code) seen.set(bt.section_code, bt.section_name_th);
    else hasUnclassified = true;
  }
  const sectionCodes = Array.from(seen.keys()).sort();

  const chips = [`<button type="button" class="section-chip ${activeSectionFilter === null ? "active" : ""}" data-section="">ทั้งหมด</button>`];
  for (const code of sectionCodes) {
    chips.push(
      `<button type="button" class="section-chip ${activeSectionFilter === code ? "active" : ""}" data-section="${escapeHtml(code)}" title="${escapeHtml(seen.get(code) || "")}">${escapeHtml(code)}</button>`
    );
  }
  if (hasUnclassified) {
    chips.push(
      `<button type="button" class="section-chip ${activeSectionFilter === UNCLASSIFIED_SECTION_KEY ? "active" : ""}" data-section="${UNCLASSIFIED_SECTION_KEY}">ยังไม่ระบุหมวด</button>`
    );
  }
  sectionFilterBar.innerHTML = chips.join("");
}

function renderRows(list) {
  tbody.innerHTML = "";
  emptyState.style.display = list.length === 0 ? "flex" : "none";
  countEl.textContent = `ทั้งหมด ${list.length} ราย`;

  // จัดกลุ่มตาม section แล้วเรียง section ตามรหัส (A, B, C, ...) ส่วนที่ยังไม่ระบุหมวดไว้ท้ายสุด
  const groups = new Map();
  for (const c of list) {
    const key = sectionKeyOf(c);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(c);
  }
  const sortedKeys = Array.from(groups.keys()).sort((a, b) => {
    if (a === UNCLASSIFIED_SECTION_KEY) return 1;
    if (b === UNCLASSIFIED_SECTION_KEY) return -1;
    return a.localeCompare(b);
  });

  for (const key of sortedKeys) {
    const rows = groups.get(key);
    const headerLabel = key === UNCLASSIFIED_SECTION_KEY ? "ยังไม่ระบุหมวด" : sectionLabelOf(rows[0]);
    const headerTr = document.createElement("tr");
    headerTr.className = "section-group-header";
    headerTr.innerHTML = `<td colspan="${COLUMN_COUNT}">${escapeHtml(headerLabel)} (${rows.length} ราย)</td>`;
    tbody.appendChild(headerTr);

    for (const c of rows) {
      const tr = document.createElement("tr");
      tr.dataset.account = c.account_no || "";
      tr.innerHTML = c.account_no && c.account_no === editingAccountNo ? renderEditRow(c) : renderViewRow(c);
      tbody.appendChild(tr);
    }
  }

  if (editingAccountNo) {
    const input = tbody.querySelector(`tr[data-account="${CSS.escape(editingAccountNo)}"] input[data-field="business_type_code"]`);
    if (input) {
      input.addEventListener("input", () => {
        const bt = businessTypeByCode[input.value.trim()];
        const label = tbody.querySelector(`tr[data-account="${CSS.escape(editingAccountNo)}"] [data-role="resolved-business"]`);
        if (label) label.textContent = bt ? bt.name_th : input.value.trim() ? "ไม่พบรหัสนี้ในระบบ" : "ยังไม่ระบุ";
      });
    }
  }
}

function currentFilteredList() {
  const q = searchBox.value.trim().toLowerCase();
  let list = customers;
  if (activeSectionFilter !== null) {
    list = list.filter((c) => sectionKeyOf(c) === activeSectionFilter);
  }
  if (q) {
    list = list.filter((c) => {
      const haystack = [c.name, c.account_no, c.business_type_code, businessLabelOf(c), sectionLabelOf(c)]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }
  return list;
}

function applyFilter() {
  renderSectionFilterBar();
  renderRows(currentFilteredList());
}

sectionFilterBar.addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-section]");
  if (!btn) return;
  const section = btn.dataset.section;
  activeSectionFilter = section === "" ? null : section;
  applyFilter();
});

async function saveEdit(accountNo, row) {
  const hintEl = row.querySelector('[data-role="edit-hint"]');
  const setHint = (msg) => {
    if (hintEl) hintEl.textContent = msg || "";
  };

  let password = sessionStorage.getItem(SESSION_PASSWORD_KEY);
  if (!password) {
    password = window.prompt("ใส่รหัสผ่านเพื่อยืนยันการแก้ไข (ตั้งค่าไว้ที่เครื่อง server ผ่าน ADMIN_EDIT_PASSWORD)") || "";
    if (!password) return;
  }

  const name = row.querySelector('input[data-field="name"]').value.trim();
  const businessTypeCode = row.querySelector('input[data-field="business_type_code"]').value.trim();
  const rateCode = row.querySelector('input[data-field="rate_code"]').value.trim();
  const solarRaw = row.querySelector('select[data-field="has_solar"]').value;
  const hasSolar = solarRaw === "" ? null : solarRaw === "true";

  const saveBtn = row.querySelector('[data-action="save"]');
  saveBtn.disabled = true;
  setHint("กำลังบันทึก...");

  try {
    const res = await fetch("/api/admin/overview-entry", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        account_no: accountNo,
        password,
        name,
        business_type_code: businessTypeCode,
        rate_code: rateCode,
        has_solar: hasSolar,
      }),
    });
    const data = await res.json();

    if (res.status === 403) {
      sessionStorage.removeItem(SESSION_PASSWORD_KEY);
      setHint(data.message || "รหัสผ่านไม่ถูกต้อง");
      saveBtn.disabled = false;
      return;
    }
    if (res.status === 503) {
      setHint(data.message || "ยังไม่เปิดใช้งานการแก้ไข");
      saveBtn.disabled = false;
      return;
    }
    if (!res.ok) {
      setHint(data.message || "บันทึกไม่สำเร็จ");
      saveBtn.disabled = false;
      return;
    }

    sessionStorage.setItem(SESSION_PASSWORD_KEY, password);

    const idx = customers.findIndex((c) => c.account_no === accountNo);
    const updated = { ...(idx >= 0 ? customers[idx] : {}), ...data };
    if (idx >= 0) customers[idx] = updated;
    else customers.push(updated);

    editingAccountNo = null;
    applyFilter();
  } catch (err) {
    console.error("บันทึกไม่สำเร็จ", err);
    setHint("เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ");
    saveBtn.disabled = false;
  }
}

tbody.addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-action]");
  if (!btn) return;
  const accountNo = btn.dataset.account;
  const action = btn.dataset.action;

  if (action === "edit") {
    editingAccountNo = accountNo;
    applyFilter();
  } else if (action === "cancel") {
    editingAccountNo = null;
    applyFilter();
  } else if (action === "save") {
    const row = btn.closest("tr");
    saveEdit(accountNo, row);
  }
});

function computeUsageStatsFromCurve(dayTypes) {
  const hours = (dayTypes && dayTypes.all) || [];
  const values = hours.filter((v) => v !== null && v !== undefined);
  if (values.length === 0) return null;
  const peakKw = Math.max(...values);
  const dailyKwh = values.reduce((sum, v) => sum + v, 0);
  return { peakKw, monthlyKwh: dailyKwh * 30 };
}

async function loadUsageStats(accountNos) {
  const entries = await Promise.all(
    accountNos.map(async (accountNo) => {
      try {
        const res = await fetch(`/api/admin/site-curve/${encodeURIComponent(accountNo)}`);
        const data = await res.json();
        if (!data.available) return [accountNo, null];
        return [accountNo, computeUsageStatsFromCurve(data.day_types)];
      } catch (err) {
        console.error(`โหลดกราฟของบัญชี ${accountNo} ไม่สำเร็จ`, err);
        return [accountNo, null];
      }
    })
  );
  usageStatsByAccount = Object.fromEntries(entries.filter(([, stats]) => stats !== null));
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
    applyFilter();

    // โหลดกราฟรายชั่วโมง (เพื่อคำนวณ ใช้ไฟเฉลี่ย/เดือน + Peak) แยกทีหลัง ไม่บล็อกการแสดงตารางหลัก
    await loadUsageStats(customers.map((c) => c.account_no).filter(Boolean));
    applyFilter();
  } catch (err) {
    console.error("โหลดข้อมูลภาพรวมไม่สำเร็จ", err);
    emptyState.textContent = "โหลดข้อมูลไม่สำเร็จ ลองรีเฟรชหน้าใหม่อีกครั้ง";
    emptyState.style.display = "flex";
  }
}

searchBox.addEventListener("input", applyFilter);
load();
