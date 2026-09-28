// หน้า "ภาพรวมลูกค้าทั้งหมด" — แสดงทะเบียนลูกค้าทั้งหมด (/api/customers: customers.csv ของ repo
// มีแต่แถว DEMO สมมติ + customers_local.csv ถ้ามี) จัดกลุ่มตาม TSIC Section พร้อมแก้ไขประเภทธุรกิจ
// ได้ในตาราง (บันทึกผ่าน PATCH /api/admin/overview-entry ซึ่งเขียนลง customers_local.csv มีผลกับ
// ทั้งระบบทันที)
//
// แถว DEMO (customers.csv สาธิต — account_no ขึ้นต้นด้วย "DEMO-" เสมอตามธรรมเนียมของ repo นี้)
// ถูกกรองทิ้งไม่ให้ขึ้นในตารางนี้ เพราะเป็นข้อมูลสมมติ ไม่ใช่ลูกค้าจริง
//
// จัดกลุ่มแถวตาม Section (TSIC A-U) พร้อมแถบปุ่มกรองด่วน — คำนวณจากรายชื่อ section ที่เจอจริง
// ในข้อมูลปัจจุบันเท่านั้น (ไม่ fix รายชื่อ 21 หมวดไว้ตายตัว กันปุ่มเยอะเกินจำเป็นตอนข้อมูลน้อย)

const tbody = document.getElementById("overview-tbody");
const emptyState = document.getElementById("overview-empty");
const countEl = document.getElementById("overview-count");
const searchBox = document.getElementById("search-box");
const sectionFilterBar = document.getElementById("section-filter-bar");

const SESSION_PASSWORD_KEY = "overviewEditPassword";
const UNCLASSIFIED_SECTION_KEY = "__unclassified__";

let customers = [];
let businessTypeByCode = {};
let editingAccountNo = null;
let activeSectionFilter = null; // null = ทั้งหมด

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
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

function renderViewRow(c) {
  const amrCell = c.has_amr ? `<span class="pill-yes">✅ มีแล้ว</span>` : `<span class="pill-muted">ยังไม่มี</span>`;

  return `
    <td>
      ${escapeHtml(c.name) || "(ไม่ทราบชื่อ)"}
      <div class="cell-sub">บัญชี ${escapeHtml(c.account_no) || "-"}</div>
      ${c.registration_no ? `<div class="cell-sub">เลขนิติบุคคล ${escapeHtml(c.registration_no)}</div>` : ""}
    </td>
    <td>${escapeHtml(businessLabelOf(c))}</td>
    <td>${escapeHtml(sectionLabelOf(c))}</td>
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

  return `
    <td>
      <input type="text" class="edit-input" data-field="name" value="${escapeHtml(c.name)}">
      <div class="cell-sub">บัญชี ${escapeHtml(c.account_no) || "-"}</div>
      <input type="text" class="edit-input" data-field="registration_no" value="${escapeHtml(c.registration_no || "")}" placeholder="เลขนิติบุคคล 13 หลัก (ไม่บังคับ)" style="margin-top:4px;">
    </td>
    <td>
      <input type="text" class="edit-input" data-field="business_type_code" value="${escapeHtml(c.business_type_code || "")}" placeholder="เช่น 26109">
      <div class="edit-resolved-label" data-role="resolved-business">${escapeHtml(resolvedLabel)}</div>
      <button type="button" class="btn-tiny" data-action="dbd-lookup" data-account="${escapeHtml(c.account_no)}" style="margin-top:4px;">🔍 ค้นหาจาก DBD</button>
      <div class="edit-resolved-label" data-role="dbd-lookup-status" style="margin-top:4px;"></div>
    </td>
    <td>${escapeHtml(sectionLabelOf(c))}</td>
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

const COLUMN_COUNT = 5;

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

// ไม่ถามรหัสผ่านล่วงหน้าอีกต่อไป — ลองบันทึกเลยด้วยรหัสผ่านที่แคชไว้ (ถ้ามี) หรือค่าว่าง ถ้า
// server ไม่ได้ตั้ง ADMIN_EDIT_PASSWORD ไว้เลยจะบันทึกผ่านทันทีไม่ต้องถามอะไร (ค่าเริ่มต้น) —
// ถามรหัสผ่านก็ต่อเมื่อ server ตอบกลับมาว่ารหัสผ่านไม่ถูกต้อง/ไม่ได้ใส่มา (403) เท่านั้น
async function saveEdit(accountNo, row, passwordOverride) {
  const hintEl = row.querySelector('[data-role="edit-hint"]');
  const setHint = (msg) => {
    if (hintEl) hintEl.textContent = msg || "";
  };

  const password = passwordOverride !== undefined ? passwordOverride : sessionStorage.getItem(SESSION_PASSWORD_KEY) || "";

  const name = row.querySelector('input[data-field="name"]').value.trim();
  const registrationNo = row.querySelector('input[data-field="registration_no"]').value.trim();
  const businessTypeCode = row.querySelector('input[data-field="business_type_code"]').value.trim();

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
        registration_no: registrationNo,
        business_type_code: businessTypeCode,
      }),
    });
    const data = await res.json();

    if (res.status === 403) {
      sessionStorage.removeItem(SESSION_PASSWORD_KEY);
      const retryPassword = window.prompt(data.message ? `${data.message} — ใส่รหัสผ่านที่ถูกต้อง` : "ใส่รหัสผ่านเพื่อยืนยันการแก้ไข") || "";
      saveBtn.disabled = false;
      if (!retryPassword) {
        setHint(data.message || "รหัสผ่านไม่ถูกต้อง");
        return;
      }
      await saveEdit(accountNo, row, retryPassword);
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

    if (password) sessionStorage.setItem(SESSION_PASSWORD_KEY, password);

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
  } else if (action === "dbd-lookup") {
    const row = btn.closest("tr");
    runDbdLookupForRow(accountNo, row);
  }
});

// ── ค้นหา TSIC จาก DBD DataWarehouse ตรงจากแถวที่กำลังแก้ไข — ใช้เลขนิติบุคคล (registration_no)
//    เป็นคำค้นหาถ้ากรอกไว้ (แม่นยำกว่าชื่อมาก ไม่มีปัญหาสะกด/คำนำหน้า-ต่อท้ายไม่ตรงกับที่จดทะเบียน
//    ไว้เป๊ะ) ไม่งั้น fallback ไปค้นด้วยชื่อบริษัทแทน (เหมือนหน้า Admin เดิม) — เลือกผลลัพธ์ที่ใช่
//    แล้วเติม business_type_code ในแถวให้อัตโนมัติ ยังต้องกด "บันทึก" เองอีกทีเสมอ ──

async function runDbdLookupForRow(accountNo, row) {
  const status = row.querySelector('[data-role="dbd-lookup-status"]');
  const name = row.querySelector('input[data-field="name"]').value.trim();
  const registrationNo = row.querySelector('input[data-field="registration_no"]').value.trim();

  if (!name && !registrationNo) {
    status.innerHTML = `<span style="color:#d03b3b;">กรอกชื่อบริษัทหรือเลขนิติบุคคลก่อน</span>`;
    return;
  }

  status.textContent = "⏳ กำลังค้นหา... (เปิดเบราว์เซอร์จริง อาจใช้เวลาสักครู่)";

  try {
    const res = await fetch("/api/business-type-lookup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ company_name: name || registrationNo, registration_no: registrationNo || undefined }),
    });
    const data = await res.json();
    if (!res.ok) {
      status.innerHTML = `<span style="color:#d03b3b;">${data.message || "เกิดข้อผิดพลาด"}</span>`;
      return;
    }
    pollDbdLookupJobForRow(accountNo, data.job_id);
  } catch (err) {
    status.innerHTML = `<span style="color:#d03b3b;">เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ</span>`;
    console.error(err);
  }
}

async function pollDbdLookupJobForRow(accountNo, jobId) {
  const row = tbody.querySelector(`tr[data-account="${CSS.escape(accountNo)}"]`);
  if (!row) return; // ผู้ใช้กดยกเลิก/เปลี่ยนแถวที่แก้ไปแล้วระหว่างรอผล
  const status = row.querySelector('[data-role="dbd-lookup-status"]');
  if (!status) return;

  const res = await fetch(`/api/business-type-lookup/${jobId}`);
  const data = await res.json();

  if (data.status === "running") {
    setTimeout(() => pollDbdLookupJobForRow(accountNo, jobId), 800);
    return;
  }
  if (data.status === "error") {
    status.innerHTML = `<span style="color:#d03b3b;">ค้นหาไม่สำเร็จ: ${data.error || "เกิดข้อผิดพลาด"}</span>`;
    return;
  }

  const { candidates } = data.result;
  if (!candidates.length) {
    status.textContent = "ไม่พบบริษัทนี้ใน DBD DataWarehouse — กรอกรหัสธุรกิจเองด้านบนได้เลย";
    return;
  }

  status.innerHTML = "";
  candidates.forEach((c) => {
    const item = document.createElement("div");
    item.style.cssText = "margin-top:4px;padding:4px 6px;border:1px solid rgba(15,23,42,0.1);border-radius:6px;";
    item.innerHTML = `
      <div>${escapeHtml(c.juristic_name)} <span style="color:#8996ab;">(${escapeHtml(c.juristic_type)})</span></div>
      <div class="cell-sub">TSIC ${escapeHtml(c.tsic_code)} · ${escapeHtml(c.tsic_name_th)}</div>
      <button type="button" class="btn-tiny" style="margin-top:2px;">ใช้อันนี้</button>`;
    item.querySelector("button").addEventListener("click", () => applyDbdCandidateToRow(accountNo, c));
    status.appendChild(item);
  });
}

function applyDbdCandidateToRow(accountNo, candidate) {
  const row = tbody.querySelector(`tr[data-account="${CSS.escape(accountNo)}"]`);
  if (!row) return;
  if (candidate.suggested_business_type_code) {
    const input = row.querySelector('input[data-field="business_type_code"]');
    input.value = candidate.suggested_business_type_code;
    input.dispatchEvent(new Event("input")); // ให้ป้าย resolved-business อัปเดตตามทันที
  }
  const regInput = row.querySelector('input[data-field="registration_no"]');
  if (regInput && !regInput.value.trim()) regInput.value = candidate.registration_no;
  const status = row.querySelector('[data-role="dbd-lookup-status"]');
  if (status) status.textContent = `เลือกแล้ว: ${candidate.juristic_name} — กด "บันทึก" เพื่อยืนยัน`;
}

async function load() {
  try {
    const [customersRes, businessTypesRes] = await Promise.all([
      fetch("/api/customers"),
      fetch("/api/business-types-full"),
    ]);
    const registryCustomers = await customersRes.json();
    const businessTypes = await businessTypesRes.json();
    businessTypeByCode = Object.fromEntries(businessTypes.map((bt) => [bt.code, bt]));

    customers = registryCustomers.filter((c) => c.account_no && !c.account_no.startsWith("DEMO-"));
    customers.sort((a, b) => (a.name || "").localeCompare(b.name || "", "th"));
    applyFilter();
  } catch (err) {
    console.error("โหลดข้อมูลภาพรวมไม่สำเร็จ", err);
    emptyState.textContent = "โหลดข้อมูลไม่สำเร็จ ลองรีเฟรชหน้าใหม่อีกครั้ง";
    emptyState.style.display = "flex";
  }
}

searchBox.addEventListener("input", applyFilter);
load();
