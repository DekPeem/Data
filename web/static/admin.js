// หน้า Admin — ดูแล/แก้ไข "หมวดหมู่ธุรกิจทั้งหมดในระบบ" (business_types.csv) — ไม่มีการนำเข้า
// AMR/พยากรณ์ตัวเลขใดๆ อีกต่อไป (ตัดฟีเจอร์นั้นออกจากทั้งระบบแล้ว)

// ── โครงสร้าง Section/Division ของ TSIC (อิง ISIC Rev.4 ที่ TSIC ใช้เป็นฐาน) — ใช้แค่เดา Section
//    จาก Division ให้อัตโนมัติตอนตรวจสอบ (แก้ไขเองได้เสมอถ้าไม่ตรง) ──
const TSIC_SECTIONS = [
  { code: "A", from: 1, to: 3, name_th: "เกษตรกรรม การป่าไม้ และการประมง" },
  { code: "B", from: 5, to: 9, name_th: "การทำเหมืองแร่และเหมืองหิน" },
  { code: "C", from: 10, to: 33, name_th: "การผลิต" },
  { code: "D", from: 35, to: 35, name_th: "ไฟฟ้า ก๊าซ ไอน้ำ และระบบปรับอากาศ" },
  { code: "E", from: 36, to: 39, name_th: "การจัดหาน้ำ การจัดการน้ำเสียและของเสีย" },
  { code: "F", from: 41, to: 43, name_th: "การก่อสร้าง" },
  { code: "G", from: 45, to: 47, name_th: "การขายส่งและการขายปลีก การซ่อมยานยนต์และจักรยานยนต์" },
  { code: "H", from: 49, to: 53, name_th: "การขนส่งและสถานที่เก็บสินค้า" },
  { code: "I", from: 55, to: 56, name_th: "ที่พักแรมและบริการด้านอาหาร" },
  { code: "J", from: 58, to: 63, name_th: "ข้อมูลข่าวสารและการสื่อสาร" },
  { code: "K", from: 64, to: 66, name_th: "กิจกรรมทางการเงินและการประกันภัย" },
  { code: "L", from: 68, to: 68, name_th: "กิจกรรมเกี่ยวกับอสังหาริมทรัพย์" },
  { code: "M", from: 69, to: 75, name_th: "กิจกรรมทางวิชาชีพ วิทยาศาสตร์ และเทคนิค" },
  { code: "N", from: 77, to: 82, name_th: "กิจกรรมการบริหารและบริการสนับสนุน" },
  { code: "O", from: 84, to: 84, name_th: "การบริหารราชการ การป้องกันประเทศ และการประกันสังคมภาคบังคับ" },
  { code: "P", from: 85, to: 85, name_th: "การศึกษา" },
  { code: "Q", from: 86, to: 88, name_th: "กิจกรรมด้านสุขภาพและงานสังคมสงเคราะห์" },
  { code: "R", from: 90, to: 93, name_th: "ศิลปะ ความบันเทิง และนันทนาการ" },
  { code: "S", from: 94, to: 96, name_th: "กิจกรรมการบริการอื่นๆ" },
  { code: "T", from: 97, to: 98, name_th: "กิจกรรมการจ้างงานในครัวเรือน" },
  { code: "U", from: 99, to: 99, name_th: "กิจกรรมขององค์การระหว่างประเทศ" },
];

function sectionForDivision(divisionCode) {
  const n = Number(divisionCode);
  if (Number.isNaN(n)) return null;
  return TSIC_SECTIONS.find((s) => n >= s.from && n <= s.to) || null;
}

// จัดกลุ่ม business types ตาม section_code — ตัวที่ยังไม่มี section_code เลยจัดไว้ในกลุ่ม
// "UNVERIFIED" (แสดงเป็น "ยังไม่ตรวจสอบ TSIC") ท้ายสุดเสมอ
function groupBySection(types) {
  const groups = {};
  types.forEach((t) => {
    const key = t.section_code || "UNVERIFIED";
    if (!groups[key]) {
      groups[key] = { section_code: t.section_code, section_name_th: t.section_name_th, types: [] };
    }
    groups[key].types.push(t);
  });
  return groups;
}

// กรองรายการในกล่อง dropdown ค้นหา (ใช้ร่วมกันทั้งกล่องค้นหา Section และกล่องค้นหาประเภทธุรกิจ)
// ตามคำที่พิมพ์ — จับคู่แบบ "มีคำนี้อยู่ตรงไหนก็ได้" ในข้อความของแต่ละรายการ (ไม่ต้องพิมพ์ตรงตั้งแต่
// ตัวแรก) ไม่สนตัวพิมพ์เล็ก-ใหญ่
function filterComboboxDropdown(input, comboboxSelector, itemSelector, emptySelector) {
  const wrap = input.closest(comboboxSelector);
  const query = input.value.trim().toLowerCase();
  const items = wrap.querySelectorAll(itemSelector);
  let anyVisible = false;
  items.forEach((item) => {
    const match = !query || item.textContent.toLowerCase().includes(query);
    item.style.display = match ? "" : "none";
    if (match) anyVisible = true;
  });
  const emptyMsg = wrap.querySelector(emptySelector);
  if (emptyMsg) emptyMsg.style.display = anyVisible ? "none" : "block";
}

function filterBizTypeDropdown(input) {
  filterComboboxDropdown(input, ".biz-type-combobox", ".biz-type-dropdown-item", ".biz-type-dropdown-empty");
}

function filterSectionDropdown(input) {
  filterComboboxDropdown(input, ".section-combobox", ".section-dropdown-item", ".section-dropdown-empty");
}

// ปิด dropdown ที่เปิดค้างไว้เมื่อคลิกข้างนอกกล่องค้นหา (ผูกครั้งเดียวตอนโหลดสคริปต์ ไม่ใช่ทุกครั้ง
// ที่ render การ์ดใหม่ เพราะ element การ์ดถูกสร้างใหม่ทุกครั้งอยู่แล้วแต่ document ตัวเดียวกันเสมอ)
document.addEventListener("click", (e) => {
  document.querySelectorAll(".biz-type-combobox.open, .section-combobox.open").forEach((box) => {
    if (!box.contains(e.target)) box.classList.remove("open");
  });
});

function renderBizCard(t) {
  const divisionBadge = t.division_code
    ? `<span class="biz-division-badge">Division ${t.division_code}${t.division_name_th ? ` · ${t.division_name_th}` : ""}</span>`
    : `<span class="biz-division-badge">ยังไม่ทราบ Division</span>`;

  return `
    <div class="biz-card" data-code="${t.code}">
      <div class="biz-card-header">
        <div><span class="biz-code">${t.code}</span>${t.name_th}${divisionBadge}</div>
        <button type="button" class="day-type-btn verify-toggle-btn" data-code="${t.code}">🔍 ตรวจสอบ TSIC</button>
      </div>
      <div id="verify-panel-${t.code}" style="display:none;"></div>
    </div>`;
}

// รหัสประเภทธุรกิจที่ถูกเลือกไว้ (กดค้นหาแล้วเลือกจาก dropdown ของ section) ให้แสดงการ์ดอยู่ —
// เก็บข้าม section ไว้ในตัวแปรเดียวกันได้เพราะรหัสไม่ซ้ำข้าม section (1 รหัส = 1 section เสมอ)
const openBizTypeCards = new Set();

// เนื้อหาในแต่ละ section: กล่องค้นหา/dropdown เลือกประเภทธุรกิจ (กันไม่ให้การ์ดทุกอันโชว์พร้อมกัน
// หมดจนรก โดยเฉพาะ section ที่มีประเภทธุรกิจเยอะ) ตามด้วยการ์ดของแต่ละประเภทที่เลือกไว้ (ซ่อนโดย
// default จนกว่าจะเลือกจาก dropdown)
function renderSectionBody(types) {
  const combobox = `
    <div class="biz-type-combobox">
      <input type="text" class="biz-type-search-input" placeholder="🔍 ค้นหาประเภทธุรกิจ (${types.length} รายการ)..." autocomplete="off">
      <div class="biz-type-dropdown">
        ${types
          .map(
            (t) =>
              `<button type="button" class="biz-type-dropdown-item${openBizTypeCards.has(t.code) ? " active" : ""}" data-code="${t.code}">${t.code} · ${t.name_th}</button>`
          )
          .join("")}
        <div class="biz-type-dropdown-empty" style="display:none;">ไม่พบประเภทธุรกิจที่ตรงกับคำค้นหา</div>
      </div>
    </div>`;
  const cards = types
    .map(
      (t) =>
        `<div class="biz-card-wrap" data-code="${t.code}" style="${openBizTypeCards.has(t.code) ? "" : "display:none;"}">${renderBizCard(t)}</div>`
    )
    .join("");
  return combobox + cards;
}

function toggleBizTypeCard(code, btn) {
  const wrap = businessTypesBySectionEl.querySelector(`.biz-card-wrap[data-code="${code}"]`);
  if (!wrap) return;
  if (openBizTypeCards.has(code)) {
    openBizTypeCards.delete(code);
    wrap.style.display = "none";
    btn.classList.remove("active");
  } else {
    openBizTypeCards.add(code);
    wrap.style.display = "";
    btn.classList.add("active");
  }
}

// Section (TSIC) ที่เลือกดูอยู่ตอนนี้ในหน้า "หมวดหมู่ธุรกิจทั้งหมดในระบบ" — เลือกได้ทีละ 1 อันจาก
// dropdown เดียว
let selectedSectionKey = null;

// รายการประเภทธุรกิจล่าสุดที่ fetch มา (เก็บไว้ใช้ re-render ได้โดยไม่ต้องยิง request ซ้ำ)
let lastBusinessTypes = [];

const businessTypesRefreshBtn = document.getElementById("business-types-refresh-btn");
const businessTypesBySectionEl = document.getElementById("business-types-by-section");

async function loadBusinessTypesTable() {
  businessTypesBySectionEl.innerHTML = `<div style="padding:12px 10px;color:#8996ab;">กำลังโหลด...</div>`;
  try {
    const res = await fetch("/api/business-types-full");
    lastBusinessTypes = await res.json();
    renderBusinessTypesSections(lastBusinessTypes);
  } catch (err) {
    businessTypesBySectionEl.innerHTML = `<div style="padding:12px 10px;color:#d03b3b;">โหลดไม่สำเร็จ</div>`;
    console.error("โหลดหมวดหมู่ธุรกิจไม่สำเร็จ", err);
  }
}

function renderBusinessTypesSections(allTypes) {
  try {
    const groups = groupBySection(allTypes);

    const keys = Object.keys(groups)
      .filter((k) => k !== "UNVERIFIED")
      .sort();
    if (groups.UNVERIFIED) keys.push("UNVERIFIED");

    if (!keys.includes(selectedSectionKey)) selectedSectionKey = null;

    const sectionLabel = (key) => {
      const g = groups[key];
      return key === "UNVERIFIED" ? "ยังไม่ตรวจสอบ TSIC" : `${g.section_code} · ${g.section_name_th}`;
    };

    // กล่องค้นหาแบบกำหนดเอง (ไม่ใช่ <select> ของเบราว์เซอร์) เพราะ <select> เปิดลิสต์ขึ้นบน/ลง
    // ล่างเองอัตโนมัติตามพื้นที่ว่างบนจอ ควบคุมทิศทางไม่ได้เลย — แบบนี้เขียนเอง เปิดลงล่างเสมอ
    businessTypesBySectionEl.innerHTML = `
      <div class="form-field">
        <label>เลือก Section (TSIC) เพื่อดูประเภทธุรกิจในกลุ่มนั้น</label>
        ${selectedSectionKey ? `<div class="hint" style="margin-bottom:2px;">กำลังดูอยู่: <b>${sectionLabel(selectedSectionKey)}</b> (${groups[selectedSectionKey].types.length} ประเภทธุรกิจ)</div>` : ""}
        <div class="section-combobox">
          <input type="text" class="section-search-input" placeholder="🔍 พิมพ์เพื่อค้นหา Section (${keys.length} รายการ)..." autocomplete="off">
          <div class="section-dropdown">
            ${keys
              .map(
                (key) =>
                  `<button type="button" class="section-dropdown-item${key === selectedSectionKey ? " active" : ""}" data-section="${key}">${sectionLabel(key)} (${groups[key].types.length} ประเภทธุรกิจ)</button>`
              )
              .join("")}
            <div class="section-dropdown-empty" style="display:none;">ไม่พบ Section ที่ตรงกับคำค้นหา</div>
          </div>
        </div>
      </div>
      <div id="section-picker-body" style="margin-top:14px;">
        ${selectedSectionKey ? renderSectionBody(groups[selectedSectionKey].types) : ""}
      </div>`;

    const sectionInput = businessTypesBySectionEl.querySelector(".section-search-input");
    sectionInput.addEventListener("focus", () => {
      sectionInput.closest(".section-combobox").classList.add("open");
      filterSectionDropdown(sectionInput);
    });
    sectionInput.addEventListener("input", () => filterSectionDropdown(sectionInput));
    businessTypesBySectionEl.querySelectorAll(".section-dropdown-item").forEach((btn) => {
      btn.addEventListener("click", () => {
        selectedSectionKey = btn.dataset.section;
        renderBusinessTypesSections(lastBusinessTypes);
      });
    });

    businessTypesBySectionEl.querySelectorAll(".verify-toggle-btn").forEach((btn) => {
      btn.addEventListener("click", () => toggleVerifyPanel(btn.dataset.code));
    });
    businessTypesBySectionEl.querySelectorAll(".biz-type-dropdown-item").forEach((btn) => {
      btn.addEventListener("click", () => toggleBizTypeCard(btn.dataset.code, btn));
    });
    businessTypesBySectionEl.querySelectorAll(".biz-type-search-input").forEach((input) => {
      input.addEventListener("focus", () => {
        input.closest(".biz-type-combobox").classList.add("open");
        filterBizTypeDropdown(input);
      });
      input.addEventListener("input", () => filterBizTypeDropdown(input));
    });
  } catch (err) {
    businessTypesBySectionEl.innerHTML = `<div style="padding:12px 10px;color:#d03b3b;">แสดงผลไม่สำเร็จ</div>`;
    console.error("แสดงผลหมวดหมู่ธุรกิจไม่สำเร็จ", err);
  }
}

businessTypesRefreshBtn.addEventListener("click", loadBusinessTypesTable);

// ── เพิ่มประเภทธุรกิจใหม่เอง (self-service) — แทนที่ต้องขอให้แก้ business_types.csv ให้ทุกครั้ง
//    ที่เจอบริษัทที่ยังไม่มีรหัส TSIC ในระบบ ──

const addBtToggleBtn = document.getElementById("add-business-type-toggle-btn");
const addBtPanel = document.getElementById("add-business-type-panel");
const addBtCodeInput = document.getElementById("new-bt-code");
const addBtNameInput = document.getElementById("new-bt-name");
const addBtSectionSelect = document.getElementById("new-bt-section");
const addBtDivisionCodeInput = document.getElementById("new-bt-division-code");
const addBtDivisionNameInput = document.getElementById("new-bt-division-name");
const addBtNotesInput = document.getElementById("new-bt-notes");
const addBtSubmitBtn = document.getElementById("add-business-type-submit-btn");
const addBtCancelBtn = document.getElementById("add-business-type-cancel-btn");
const addBtHint = document.getElementById("add-business-type-hint");

addBtSectionSelect.innerHTML =
  `<option value="">-- ไม่ระบุ --</option>` +
  TSIC_SECTIONS.map((s) => `<option value="${s.code}">${s.code} · ${s.name_th}</option>`).join("");

function resetAddBusinessTypeForm() {
  addBtCodeInput.value = "";
  addBtNameInput.value = "";
  addBtSectionSelect.value = "";
  addBtDivisionCodeInput.value = "";
  addBtDivisionNameInput.value = "";
  addBtNotesInput.value = "";
  addBtHint.textContent = "";
}

addBtToggleBtn.addEventListener("click", () => {
  const showing = addBtPanel.style.display === "flex";
  addBtPanel.style.display = showing ? "none" : "flex";
  if (!showing) addBtCodeInput.focus();
});

addBtCancelBtn.addEventListener("click", () => {
  addBtPanel.style.display = "none";
  resetAddBusinessTypeForm();
});

addBtSubmitBtn.addEventListener("click", async () => {
  addBtHint.textContent = "";
  const code = addBtCodeInput.value.trim();
  const name_th = addBtNameInput.value.trim();
  if (!code || !name_th) {
    addBtHint.textContent = "กรุณากรอกรหัสและชื่อประเภทธุรกิจ";
    return;
  }

  const sectionCode = addBtSectionSelect.value;
  const section = TSIC_SECTIONS.find((s) => s.code === sectionCode);

  addBtSubmitBtn.disabled = true;
  try {
    const res = await fetch("/api/business-types", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        code,
        name_th,
        section_code: sectionCode || "",
        section_name_th: section ? section.name_th : "",
        division_code: addBtDivisionCodeInput.value.trim(),
        division_name_th: addBtDivisionNameInput.value.trim(),
        notes: addBtNotesInput.value.trim(),
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      addBtHint.textContent = data.message || "บันทึกไม่สำเร็จ";
      addBtSubmitBtn.disabled = false;
      return;
    }
    addBtPanel.style.display = "none";
    resetAddBusinessTypeForm();
    loadBusinessTypesTable();
  } catch (err) {
    addBtHint.textContent = "เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ";
    console.error(err);
  } finally {
    addBtSubmitBtn.disabled = false;
  }
});

// ── ตรวจสอบ/บันทึก TSIC Section-Division ของประเภทธุรกิจหนึ่งรายการ (ค้นหาจาก DBD DataWarehouse
//    ด้วยชื่อบริษัทตัวอย่าง แล้วเติม Section/Division ให้อัตโนมัติ — ตรวจสอบ/แก้ไขเองได้เสมอก่อน
//    บันทึก) ──

const openVerifyPanels = new Set();

function toggleVerifyPanel(code) {
  const panel = document.getElementById(`verify-panel-${code}`);
  if (openVerifyPanels.has(code)) {
    openVerifyPanels.delete(code);
    panel.style.display = "none";
    return;
  }
  openVerifyPanels.add(code);
  panel.style.display = "block";
  if (!panel.dataset.built) {
    panel.dataset.built = "1";
    renderVerifyPanel(code);
  }
}

function renderVerifyPanel(code) {
  const panel = document.getElementById(`verify-panel-${code}`);
  panel.innerHTML = `
    <div class="verify-panel">
      <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end;">
        <div class="form-field" style="flex:1;min-width:220px;">
          <label for="verify-name-input-${code}">ชื่อบริษัท/นิติบุคคล (ค้นหาจาก DBD DataWarehouse — ไม่บังคับ)</label>
          <input id="verify-name-input-${code}" type="text" placeholder="เช่น บริษัท ตัวอย่าง จำกัด">
        </div>
        <button type="button" class="day-type-btn verify-search-btn" data-code="${code}">ค้นหา TSIC</button>
      </div>
      <div id="verify-status-${code}" class="hint"></div>

      <div class="hint" style="margin-top:10px;">
        ℹ️ ช่อง Section / Division ด้านล่างคืออะไร ใช้ทำไม —
        <a href="/manual#tsic-explained" target="_blank" rel="noopener">อ่านรายละเอียดในคู่มือ →</a>
      </div>

      <div class="hint" style="margin-top:10px;">
        กรอกเอง หรือเลือกจากผลค้นหาด้านบนเพื่อเติมให้อัตโนมัติ — พิมพ์ Division code แล้ว Section
        จะเดาให้เองจากโครงสร้าง TSIC (แก้ไขเองได้เสมอถ้าไม่ตรง):
      </div>
      <div class="verify-row-fields">
        <div class="form-field" style="grid-column: span 2;">
          <label>Section (TSIC)</label>
          <select id="verify-section-select-${code}">
            <option value="">-- ยังไม่ระบุ --</option>
            ${TSIC_SECTIONS.map((s) => `<option value="${s.code}">${s.code} · ${s.name_th} (Division ${s.from}-${s.to})</option>`).join("")}
          </select>
        </div>
        <div class="form-field">
          <label>Division code</label>
          <input id="verify-division-code-${code}" type="text" maxlength="2">
        </div>
        <div class="form-field">
          <label>ชื่อ Division (TH)</label>
          <input id="verify-division-name-${code}" type="text">
        </div>
      </div>
      <div class="submit-row" style="margin-top:10px;">
        <button type="button" class="search-button" id="verify-save-btn-${code}">บันทึกเป็นของรหัส ${code} นี้</button>
      </div>
      <div id="verify-save-status-${code}" class="hint" style="margin-top:6px;"></div>
    </div>`;

  panel.querySelector(".verify-search-btn").addEventListener("click", () => runVerifyLookup(code));
  document.getElementById(`verify-section-select-${code}`).addEventListener("change", () => {
    document.getElementById(`verify-section-select-${code}`).dataset.userEdited = "1";
  });
  document.getElementById(`verify-division-code-${code}`).addEventListener("input", () => {
    autofillSectionFromDivision(code);
  });
  document.getElementById(`verify-save-btn-${code}`).addEventListener("click", () => saveHierarchy(code));
}

// เดา Section ให้อัตโนมัติทุกครั้งที่ Division code เปลี่ยน (ทั้งตอนพิมพ์เองหรือเติมจากผลค้นหา) —
// เว้นแต่ผู้ใช้เคยเลือก Section เองมาก่อนแล้ว (ไม่อยากไปทับค่าที่เลือกไว้ตั้งใจ)
function autofillSectionFromDivision(code) {
  const sectionSelect = document.getElementById(`verify-section-select-${code}`);
  if (sectionSelect.dataset.userEdited) return;

  const divisionCode = document.getElementById(`verify-division-code-${code}`).value.trim();
  const section = sectionForDivision(divisionCode);
  sectionSelect.value = section ? section.code : "";
}

async function runVerifyLookup(code) {
  const nameInput = document.getElementById(`verify-name-input-${code}`);
  const status = document.getElementById(`verify-status-${code}`);
  const companyName = nameInput.value.trim();
  if (!companyName) {
    status.innerHTML = `<span style="color:#d03b3b;">กรุณาพิมพ์ชื่อบริษัทก่อน</span>`;
    return;
  }

  status.innerHTML = `⏳ กำลังค้นหา... (เปิดเบราว์เซอร์จริง อาจใช้เวลาสักครู่)`;

  try {
    const res = await fetch("/api/business-type-lookup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ company_name: companyName }),
    });
    const data = await res.json();
    if (!res.ok) {
      status.innerHTML = `<span style="color:#d03b3b;">${data.message || "เกิดข้อผิดพลาด"}</span>`;
      return;
    }
    pollVerifyLookupJob(code, data.job_id);
  } catch (err) {
    status.innerHTML = `<span style="color:#d03b3b;">เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ</span>`;
    console.error(err);
  }
}

async function pollVerifyLookupJob(code, jobId) {
  const status = document.getElementById(`verify-status-${code}`);
  const res = await fetch(`/api/business-type-lookup/${jobId}`);
  const data = await res.json();

  if (data.status === "running") {
    setTimeout(() => pollVerifyLookupJob(code, jobId), 800);
    return;
  }

  if (data.status === "error") {
    status.innerHTML = `<span style="color:#d03b3b;">ค้นหาไม่สำเร็จ: ${data.error || "เกิดข้อผิดพลาด"} (ต้องรันเว็บนี้ในเครื่องที่มี Google Chrome ติดตั้งอยู่)</span>`;
    return;
  }

  const { candidates } = data.result;
  if (!candidates.length) {
    status.innerHTML = `ไม่พบบริษัทนี้ใน DBD DataWarehouse — กรอก Section/Division เองด้านล่างได้เลย`;
    return;
  }

  status.innerHTML = `<div style="margin-bottom:8px;">เลือกบริษัทที่ใช่ เพื่อดึง TSIC มาเติมด้านล่าง:</div>`;
  const list = document.createElement("div");
  list.style.display = "flex";
  list.style.flexDirection = "column";
  list.style.gap = "8px";
  candidates.forEach((c, i) => {
    const row = document.createElement("div");
    row.className = "verify-candidate";
    row.innerHTML = `
      <div>
        <div style="font-weight:600;">${c.juristic_name} <span style="font-weight:400;color:#8996ab;">(${c.juristic_type})</span></div>
        <div class="hint">TSIC ${c.tsic_code} - ${c.tsic_name_th} · ${c.status}</div>
      </div>
      <button type="button" class="day-type-btn">ใช้อันนี้</button>`;
    row.querySelector("button").addEventListener("click", () => applyCandidateToFields(code, candidates[i]));
    list.appendChild(row);
  });
  status.appendChild(list);
}

// เติมค่าลงในช่อง Section/Division ที่มีอยู่แล้วในแผง (renderVerifyPanel สร้างไว้ตั้งแต่เปิดแผง) —
// ไม่ auto-apply ให้ทันที ผู้ใช้ยังต้องกด "บันทึก" เองเสมอ จะได้ตรวจสอบ/แก้ไขก่อนได้
function applyCandidateToFields(code, candidate) {
  const divisionCode = candidate.tsic_division_code || candidate.tsic_code.slice(0, 2);
  document.getElementById(`verify-division-code-${code}`).value = divisionCode;
  document.getElementById(`verify-division-name-${code}`).value = candidate.tsic_name_th;
  autofillSectionFromDivision(code);
}

async function saveHierarchy(code) {
  const saveStatus = document.getElementById(`verify-save-status-${code}`);
  const section_code = document.getElementById(`verify-section-select-${code}`).value.trim();
  const selectedSection = TSIC_SECTIONS.find((s) => s.code === section_code);
  const section_name_th = selectedSection ? selectedSection.name_th : "";
  const division_code = document.getElementById(`verify-division-code-${code}`).value.trim();
  const division_name_th = document.getElementById(`verify-division-name-${code}`).value.trim();

  saveStatus.textContent = "⏳ กำลังบันทึก...";
  try {
    const res = await fetch(`/api/business-types/${encodeURIComponent(code)}/hierarchy`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ section_code, section_name_th, division_code, division_name_th }),
    });
    const data = await res.json();
    if (!res.ok) {
      saveStatus.innerHTML = `<span style="color:#d03b3b;">${data.message || "บันทึกไม่สำเร็จ"}</span>`;
      return;
    }
    saveStatus.innerHTML = `<span style="color:#006300;">✅ บันทึกแล้ว</span>`;
    loadBusinessTypesTable(); // รีเฟรชตารางหลักให้เห็นค่า Section/Division ใหม่ (แผงจะยุบกลับ - เปิดใหม่ได้)
    openVerifyPanels.delete(code);
  } catch (err) {
    saveStatus.innerHTML = `<span style="color:#d03b3b;">เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ</span>`;
    console.error(err);
  }
}

loadBusinessTypesTable();

// ── อัปโหลด AMR จริง สร้างฐานข้อมูล Boxplot ตาม TSIC (ดู src/amr_mapping/amr_boxplot.py) ──

const amrBoxplotBizSelect = document.getElementById("amr-boxplot-biz-select");
const amrBoxplotFiles = document.getElementById("amr-boxplot-files");
const amrBoxplotUploadBtn = document.getElementById("amr-boxplot-upload-btn");
const amrBoxplotUploadStatus = document.getElementById("amr-boxplot-upload-status");

async function loadAmrBoxplotBizOptions() {
  try {
    const res = await fetch("/api/business-types-full");
    const types = await res.json();
    const optionsHtml = [...types]
      .sort((a, b) => (a.name_th || "").localeCompare(b.name_th || "", "th"))
      .map((t) => `<option value="${t.code}">${t.name_th} · ${t.code}</option>`)
      .join("");
    amrBoxplotBizSelect.innerHTML = optionsHtml;
    // ช่องเดียวกันในโหมด "ดึงจากเว็บ PEA อัตโนมัติ" มีตัวเลือกแรกเป็น "ตรวจจับอัตโนมัติ" (value ว่าง)
    // เสมอ ต้องคงไว้ ไม่ใช่เขียนทับด้วย optionsHtml ตรงๆ
    amrFetchBizSelect.innerHTML = amrFetchBizSelect.options[0].outerHTML + optionsHtml;
  } catch (err) {
    console.error(err);
  }
}

amrBoxplotUploadBtn.addEventListener("click", async () => {
  const bizCode = amrBoxplotBizSelect.value;
  const files = amrBoxplotFiles.files;
  if (!bizCode || !files.length) {
    amrBoxplotUploadStatus.innerHTML = `<span style="color:#d03b3b;">กรุณาเลือกประเภทธุรกิจและแนบไฟล์อย่างน้อย 1 ไฟล์</span>`;
    return;
  }

  const formData = new FormData();
  formData.append("business_type_code", bizCode);
  for (const f of files) formData.append("files", f);

  amrBoxplotUploadBtn.disabled = true;
  amrBoxplotUploadStatus.textContent = "⏳ กำลังอัปโหลด...";
  try {
    const res = await fetch("/api/admin/amr-boxplot/upload", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) {
      amrBoxplotUploadStatus.innerHTML = `<span style="color:#d03b3b;">${data.message || "เกิดข้อผิดพลาด"}</span>`;
      return;
    }
    amrBoxplotUploadStatus.innerHTML = `<span style="color:#006300;">✅ เพิ่มข้อมูลแล้ว ${data.added_intervals.toLocaleString("th-TH")} จุด (${data.days} วัน)</span>`;
    amrBoxplotFiles.value = "";
  } catch (err) {
    amrBoxplotUploadStatus.innerHTML = `<span style="color:#d03b3b;">เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ</span>`;
    console.error(err);
  } finally {
    amrBoxplotUploadBtn.disabled = false;
  }
});

// ── สลับโหมด "แนบไฟล์เอง" / "ดึงจากเว็บ PEA อัตโนมัติ" ──

const amrBoxplotModeUploadBtn = document.getElementById("amr-boxplot-mode-upload-btn");
const amrBoxplotModeFetchBtn = document.getElementById("amr-boxplot-mode-fetch-btn");
const amrBoxplotUploadPanel = document.getElementById("amr-boxplot-upload-panel");
const amrBoxplotFetchPanel = document.getElementById("amr-boxplot-fetch-panel");

amrBoxplotModeUploadBtn.addEventListener("click", () => {
  amrBoxplotModeUploadBtn.classList.add("active");
  amrBoxplotModeFetchBtn.classList.remove("active");
  amrBoxplotUploadPanel.style.display = "flex";
  amrBoxplotFetchPanel.style.display = "none";
});
amrBoxplotModeFetchBtn.addEventListener("click", () => {
  amrBoxplotModeFetchBtn.classList.add("active");
  amrBoxplotModeUploadBtn.classList.remove("active");
  amrBoxplotFetchPanel.style.display = "flex";
  amrBoxplotUploadPanel.style.display = "none";
});

// ── ดึง AMR จริงจากเว็บ PEA อัตโนมัติ (Selenium — ดู amr_downloader.py) ──

const amrFetchUsername = document.getElementById("amr-fetch-username");
const amrFetchPassword = document.getElementById("amr-fetch-password");
const amrFetchBizSelect = document.getElementById("amr-fetch-biz-select");
const amrFetchAccounts = document.getElementById("amr-fetch-accounts");
const amrFetchStartDate = document.getElementById("amr-fetch-start-date");
const amrFetchEndDate = document.getElementById("amr-fetch-end-date");
const amrFetchBtn = document.getElementById("amr-fetch-btn");
const amrFetchJobArea = document.getElementById("amr-fetch-job-area");
const amrFetchLog = document.getElementById("amr-fetch-log");
const amrFetchResult = document.getElementById("amr-fetch-result");

async function pollAmrFetchJob(jobId) {
  const res = await fetch(`/api/admin/amr-boxplot/fetch/${jobId}`);
  const data = await res.json();

  amrFetchLog.textContent = (data.logs || []).join("\n");
  amrFetchLog.scrollTop = amrFetchLog.scrollHeight;

  if (data.status === "running") {
    setTimeout(() => pollAmrFetchJob(jobId), 1500);
    return;
  }

  amrFetchBtn.disabled = false;

  if (data.status === "success") {
    const r = data.result || {};
    amrFetchResult.innerHTML =
      `<span style="color:#006300;">✅ เสร็จแล้ว — เพิ่ม ${(r.added_intervals || 0).toLocaleString("th-TH")} จุด ` +
      `(${r.days || 0} วัน, ${r.files_downloaded || 0} ไฟล์) เข้าประเภทธุรกิจ ${r.business_type_code || ""}` +
      (r.business_type_name ? ` — ${r.business_type_name}` : "") + `</span>`;
  } else {
    amrFetchResult.innerHTML = `<span style="color:#d03b3b;">${data.error || "เกิดข้อผิดพลาด"}</span>`;
  }
}

amrFetchBtn.addEventListener("click", async () => {
  const body = {
    username: amrFetchUsername.value.trim(),
    password: amrFetchPassword.value,
    business_type_code: amrFetchBizSelect.value,
    accounts: amrFetchAccounts.value.trim(),
    start_date: amrFetchStartDate.value,
    end_date: amrFetchEndDate.value,
  };

  amrFetchBtn.disabled = true;
  amrFetchJobArea.style.display = "flex";
  amrFetchLog.textContent = "";
  amrFetchResult.textContent = "⏳ กำลังเริ่มงาน...";

  try {
    const res = await fetch("/api/admin/amr-boxplot/fetch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();

    if (!res.ok) {
      amrFetchBtn.disabled = false;
      amrFetchResult.innerHTML = `<span style="color:#d03b3b;">${data.message || "เกิดข้อผิดพลาด"}</span>`;
      return;
    }

    pollAmrFetchJob(data.job_id);
  } catch (err) {
    amrFetchBtn.disabled = false;
    amrFetchResult.innerHTML = `<span style="color:#d03b3b;">เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ</span>`;
    console.error(err);
  }
});

loadAmrBoxplotBizOptions();

// ── ดูกราฟ Boxplot ของประเภทธุรกิจที่เลือกไว้ตรงๆ จากหน้า Admin (ไม่ต้องไปหน้าแรกแล้วจับคู่ TSIC
// ก่อน) — ใช้ TSIC จาก dropdown ของแผงที่กำลังเปิดอยู่ (แนบไฟล์เอง หรือดึงจากเว็บ PEA อัตโนมัติ)
const amrBoxplotViewBtn = document.getElementById("amr-boxplot-view-btn");
const amrBoxplotViewStatus = document.getElementById("amr-boxplot-view-status");
const amrBoxplotViewImg = document.getElementById("amr-boxplot-view-img");
let amrBoxplotViewImgObjectUrl = null;

amrBoxplotViewBtn.addEventListener("click", async () => {
  const activeSelect = amrBoxplotFetchPanel.style.display === "none" ? amrBoxplotBizSelect : amrFetchBizSelect;
  const code = activeSelect.value;
  if (!code) {
    amrBoxplotViewStatus.innerHTML = `<span style="color:#d03b3b;">กรุณาเลือกประเภทธุรกิจ (TSIC) ก่อน</span>`;
    amrBoxplotViewImg.style.display = "none";
    return;
  }

  amrBoxplotViewBtn.disabled = true;
  amrBoxplotViewStatus.textContent = "⏳ กำลังโหลด...";
  amrBoxplotViewImg.style.display = "none";

  try {
    const res = await fetch(`/api/forecast-boxplot?business_type_code=${encodeURIComponent(code)}`);
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      amrBoxplotViewStatus.innerHTML = `<span style="color:#8996ab;">${data.message || "ไม่พบข้อมูล"}</span>`;
      return;
    }

    const blob = await res.blob();
    if (amrBoxplotViewImgObjectUrl) URL.revokeObjectURL(amrBoxplotViewImgObjectUrl);
    amrBoxplotViewImgObjectUrl = URL.createObjectURL(blob);
    amrBoxplotViewImg.src = amrBoxplotViewImgObjectUrl;
    amrBoxplotViewImg.style.display = "block";
    amrBoxplotViewStatus.textContent = "";
  } catch (err) {
    amrBoxplotViewStatus.innerHTML = `<span style="color:#d03b3b;">เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ</span>`;
    console.error(err);
  } finally {
    amrBoxplotViewBtn.disabled = false;
  }
});

// ── พยากรณ์เส้นโค้งการใช้ไฟ จากไฟล์ AMR จริงบนบิล (ไม่ต้องพิมพ์ Peak/หน่วยไฟ/จำนวนวันเอง — อ่านจาก
// ไฟล์ที่แนบมาให้อัตโนมัติ เหลือแค่ % ลดตอนพักเที่ยง) — ย้ายมาจากหน้าแรก (เดิมอยู่ index.html/
// app.js เป็นฟอร์มกรอกตัวเลขเอง) เพราะคล้าย Boxplot ด้านบนตรงที่ไม่ต้องผูกกับการค้นหาบริษัท/TSIC
// ใดๆ เลย จึงเหมาะเป็นเครื่องมือของ Admin มากกว่า — ดู POST /api/admin/forecast-shape-from-files
// (web/app.py) ฝั่ง backend อ่านไฟล์ที่แนบมาด้วย amr_boxplot.parse_amr_files + คำนวณ Peak/หน่วยไฟ/
// จำนวนวันของแต่ละช่วง P/OP/H เอง (amr_boxplot.compute_bill_stats_from_intervals) แล้วค่อยยิงเข้า
// forecast_shape.forecast_shape_png ตัวเดิม — คืนรูปภาพ PNG ตรงๆ ไม่ใช่ JSON จึงต้อง fetch เป็น
// blob แล้วสร้าง object URL แทนการตั้ง <img src> ตรงๆ (กันกรณี error ตอบกลับมาเป็น JSON แทน —
// ต้องเช็ค response.ok ก่อนตัดสินใจว่าจะแสดงรูปหรือข้อความ error) ตัวเลขที่ระบบอ่านได้จริงจากไฟล์
// (Peak/หน่วยไฟ/จำนวนวันของแต่ละช่วง) ส่งกลับมาทาง response header X-Forecast-Stats (JSON) เอาไว้
// โชว์ให้แอดมินตรวจสอบว่าอ่านไฟล์ถูกไหม ไม่ใช่กล่องดำ
const forecastFilesInput = document.getElementById("fc-files");
const forecastDropPct = document.getElementById("fc-drop-pct");
const forecastBtn = document.getElementById("forecast-shape-btn");
const forecastStatus = document.getElementById("forecast-shape-status");
const forecastImg = document.getElementById("forecast-shape-img");

let forecastImgObjectUrl = null; // ต้อง revoke ของเก่าทิ้งทุกครั้งก่อนสร้างใหม่ กัน memory leak

const FORECAST_RATE_LABELS = { P: "P (Peak)", OP: "OP (Off-Peak)", H: "H (Holiday)" };

function formatForecastStats(rawHeader) {
  let stats;
  try {
    stats = JSON.parse(rawHeader);
  } catch {
    return "";
  }
  const parts = Object.entries(FORECAST_RATE_LABELS)
    .filter(([code]) => stats[code])
    .map(([code, label]) => {
      const s = stats[code];
      return `${label}: Peak ${s.peak.toLocaleString("th-TH", { maximumFractionDigits: 1 })} kW · ` +
        `${s.energy_kwh.toLocaleString("th-TH", { maximumFractionDigits: 0 })} kWh · ${s.days} วัน`;
    });
  return parts.length ? `อ่านจากไฟล์ได้: ${parts.join(" — ")}` : "";
}

forecastBtn.addEventListener("click", async () => {
  if (!forecastFilesInput.files.length) {
    forecastStatus.innerHTML = `<span style="color:#d03b3b;">กรุณาแนบไฟล์ AMR อย่างน้อย 1 ไฟล์</span>`;
    return;
  }

  const formData = new FormData();
  for (const f of forecastFilesInput.files) formData.append("files", f);
  const dropPct = forecastDropPct.value.trim();
  if (dropPct !== "") formData.append("drop_pct", dropPct);

  forecastBtn.disabled = true;
  forecastStatus.textContent = "⏳ กำลังอ่านไฟล์และพยากรณ์...";
  forecastImg.style.display = "none";

  try {
    const res = await fetch("/api/admin/forecast-shape-from-files", { method: "POST", body: formData });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      forecastStatus.innerHTML = `<span style="color:#d03b3b;">${data.message || "เกิดข้อผิดพลาด"}</span>`;
      return;
    }

    const statsHeader = res.headers.get("X-Forecast-Stats");
    const blob = await res.blob();
    if (forecastImgObjectUrl) URL.revokeObjectURL(forecastImgObjectUrl);
    forecastImgObjectUrl = URL.createObjectURL(blob);
    forecastImg.src = forecastImgObjectUrl;
    forecastImg.style.display = "block";
    forecastStatus.textContent = statsHeader ? formatForecastStats(statsHeader) : "";
  } catch (err) {
    forecastStatus.innerHTML = `<span style="color:#d03b3b;">เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ</span>`;
    console.error(err);
  } finally {
    forecastBtn.disabled = false;
  }
});
