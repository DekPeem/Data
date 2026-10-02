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
const amrBoxplotBizSearch = document.getElementById("amr-boxplot-biz-search");
const amrBoxplotBizCombobox = document.getElementById("amr-boxplot-biz-combobox");
const amrBoxplotBizDropdown = amrBoxplotBizCombobox.querySelector(".biz-type-dropdown");
const amrBoxplotFiles = document.getElementById("amr-boxplot-files");
const amrBoxplotAccountNo = document.getElementById("amr-boxplot-account-no");
const amrBoxplotCompanyName = document.getElementById("amr-boxplot-company-name");
const amrBoxplotRegistrationNo = document.getElementById("amr-boxplot-registration-no");
const amrBoxplotUploadBtn = document.getElementById("amr-boxplot-upload-btn");
const amrBoxplotUploadStatus = document.getElementById("amr-boxplot-upload-status");

const AMR_BIZ_SELECT_UNCLASSIFIED_KEY = "__unclassified__";

// จัดกลุ่มประเภทธุรกิจตาม TSIC Section (A-U) — ใช้ร่วมกันทั้งช่องอัปโหลด (biz-type-combobox พิมพ์
// ค้นหาได้ทั้งชื่อ/รหัส TSIC — ผู้ใช้ฟีดแบ็กว่า <select>/<optgroup> เดิมพิมพ์หาไม่ได้เลย) และ
// <select> เดิมของโหมด "ดึงจากเว็บ PEA อัตโนมัติ" (ยังไม่แปลงเป็น combobox เพราะมีตัวเลือกพิเศษ
// "ตรวจจับอัตโนมัติ" ปนอยู่ด้วย)
function groupBizTypesBySection(types) {
  const groups = new Map(); // section_code (หรือ UNCLASSIFIED) -> { label, items: [] }
  for (const t of types) {
    const key = t.section_code || AMR_BIZ_SELECT_UNCLASSIFIED_KEY;
    if (!groups.has(key)) {
      groups.set(key, {
        label: t.section_code ? `${t.section_code} · ${t.section_name_th || ""}` : "ยังไม่ระบุหมวด",
        items: [],
      });
    }
    groups.get(key).items.push(t);
  }
  const sortedKeys = Array.from(groups.keys()).sort((a, b) => {
    if (a === AMR_BIZ_SELECT_UNCLASSIFIED_KEY) return 1;
    if (b === AMR_BIZ_SELECT_UNCLASSIFIED_KEY) return -1;
    return a.localeCompare(b);
  });
  for (const key of sortedKeys) {
    groups.get(key).items.sort((a, b) => (a.name_th || "").localeCompare(b.name_th || "", "th"));
  }
  return sortedKeys.map((key) => groups.get(key));
}

function buildBizSelectOptionsHtml(types) {
  return groupBizTypesBySection(types)
    .map((group) => {
      const optionsHtml = group.items.map((t) => `<option value="${t.code}">${t.name_th} · ${t.code}</option>`).join("");
      return `<optgroup label="${escapeHtml(group.label)}">${optionsHtml}</optgroup>`;
    })
    .join("");
}

// ช่องอัปโหลด: พิมพ์ค้นหาได้ (ชื่อหรือรหัส TSIC) แทน <select>/<optgroup> เดิมที่พิมพ์หาไม่ได้เลย
// (เลือกได้แค่เลื่อนดู/กดตัวอักษรแรกแบบเบราว์เซอร์เดิม) ค่าจริงเก็บใน hidden input
// #amr-boxplot-biz-select (โค้ดส่วนอื่นที่อ่าน .value ไม่ต้องแก้อะไรเลย)
function buildBizDropdownItemsHtml(types) {
  return (
    groupBizTypesBySection(types)
      .map(
        (group) =>
          `<div class="biz-type-dropdown-group">${escapeHtml(group.label)}</div>` +
          group.items.map((t) => `<button type="button" class="biz-type-dropdown-item" data-code="${t.code}" data-label="${escapeHtml(t.name_th)} · ${t.code}">${escapeHtml(t.name_th)} · ${t.code}</button>`).join("")
      )
      .join("") + `<div class="biz-type-dropdown-empty" style="display:none;">ไม่พบประเภทธุรกิจที่ตรงกับคำค้นหา</div>`
  );
}

// กรองรายการในดรอปดาวน์ตามคำค้นหา เหมือน filterComboboxDropdown แต่ต้องซ่อน/แสดงหัวข้อกลุ่ม
// (.biz-type-dropdown-group) ตามด้วยว่ากลุ่มนั้นเหลือรายการที่ตรงคำค้นหาบ้างไหม — เขียนแยกจาก
// filterComboboxDropdown ที่ใช้ร่วมกันที่อื่น (ไม่มีแนวคิดหัวข้อกลุ่มปนอยู่ในดรอปดาวน์) กันกระทบกัน
function filterAmrBoxplotBizDropdown() {
  const query = amrBoxplotBizSearch.value.trim().toLowerCase();
  let anyVisible = false;
  let currentGroup = null;
  let currentGroupHasMatch = false;
  for (const el of amrBoxplotBizDropdown.children) {
    if (el.classList.contains("biz-type-dropdown-group")) {
      if (currentGroup) currentGroup.style.display = currentGroupHasMatch ? "" : "none";
      currentGroup = el;
      currentGroupHasMatch = false;
    } else if (el.classList.contains("biz-type-dropdown-item")) {
      const match = !query || el.textContent.toLowerCase().includes(query);
      el.style.display = match ? "" : "none";
      if (match) {
        anyVisible = true;
        currentGroupHasMatch = true;
      }
    }
  }
  if (currentGroup) currentGroup.style.display = currentGroupHasMatch ? "" : "none";
  const emptyMsg = amrBoxplotBizDropdown.querySelector(".biz-type-dropdown-empty");
  if (emptyMsg) emptyMsg.style.display = anyVisible ? "none" : "block";
}

function selectAmrBoxplotBiz(code, label) {
  amrBoxplotBizSelect.value = code;
  amrBoxplotBizSearch.value = label;
  amrBoxplotBizCombobox.classList.remove("open");
  amrBoxplotBizDropdown.querySelectorAll(".biz-type-dropdown-item").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.code === code);
  });
}

let amrBoxplotBizComboboxReady = false;

function setupAmrBoxplotBizCombobox() {
  amrBoxplotBizDropdown.querySelectorAll(".biz-type-dropdown-item").forEach((btn) => {
    btn.addEventListener("click", () => selectAmrBoxplotBiz(btn.dataset.code, btn.dataset.label));
  });

  if (amrBoxplotBizComboboxReady) return; // ผูก event listener ของช่อง search ครั้งเดียวพอ
  amrBoxplotBizComboboxReady = true;
  amrBoxplotBizSearch.addEventListener("focus", () => amrBoxplotBizCombobox.classList.add("open"));
  amrBoxplotBizSearch.addEventListener("input", filterAmrBoxplotBizDropdown);
}

async function loadAmrBoxplotBizOptions() {
  try {
    const res = await fetch("/api/business-types-full");
    const types = await res.json();
    amrBoxplotBizDropdown.innerHTML = buildBizDropdownItemsHtml(types);
    setupAmrBoxplotBizCombobox();

    const optionsHtml = buildBizSelectOptionsHtml(types);
    // ช่องเดียวกันในโหมด "ดึงจากเว็บ PEA อัตโนมัติ" มีตัวเลือกแรกเป็น "ตรวจจับอัตโนมัติ" (value ว่าง)
    // เสมอ ต้องคงไว้ ไม่ใช่เขียนทับด้วย optionsHtml ตรงๆ
    amrFetchBizSelect.innerHTML = amrFetchBizSelect.options[0].outerHTML + optionsHtml;
  } catch (err) {
    console.error(err);
  }
}

// ── log ข้อมูล AMR จริงที่มีอยู่แล้วในระบบ แยกตาม TSIC + เลขบัญชี (ดู
// GET /api/admin/amr-boxplot/status-by-account — amr_boxplot.summarize_available_by_account)
// ให้เห็นชัดๆ ว่าอัปโหลด/ดึงบัญชีไหนไปแล้วบ้าง กี่จุด/กี่วัน (ผู้ใช้ยืนยันอยากได้แบบแยกทีละบัญชี
// ไม่อยากเห็นแค่ยอดรวมต่อ TSIC) แทนที่จะต้องเดา/ลองอัปโหลดซ้ำ — รีเฟรชอัตโนมัติทุกครั้งที่อัปโหลด/
// ดึงข้อมูลสำเร็จ (ดู amrBoxplotUploadBtn/pollAmrFetchJob/pollAmrFetchBulkJob) และกดรีเฟรชเองได้ด้วย
//
// จัดกลุ่มตาม TSIC Section (A-U) พร้อมแถบปุ่มกรองด่วน — เลียนแบบ overview.js ทุกประการ (หน้า
// "ภาพรวมลูกค้าทั้งหมด" มีอยู่แล้ว) เพื่อให้ UX สอดคล้องกันทั้งระบบ ไม่ fix รายชื่อ section ตายตัว
// คำนวณจาก section ที่เจอจริงในข้อมูลปัจจุบันเท่านั้น
const AMR_LOG_UNCLASSIFIED_SECTION_KEY = "__unclassified__";
const AMR_LOG_COLUMN_COUNT = 6;

const amrBoxplotLogStatus = document.getElementById("amr-boxplot-log-status");
const amrBoxplotLogTable = document.getElementById("amr-boxplot-log-table");
const amrBoxplotLogFilterBar = document.getElementById("amr-boxplot-log-filter-bar");
const amrBoxplotLogRefreshBtn = document.getElementById("amr-boxplot-log-refresh-btn");

let amrBoxplotLogRows = []; // ผลดิบจาก status-by-account รอบล่าสุด
let amrBoxplotLogTypeByCode = new Map(); // business_type_code -> {name_th, section_code, section_name_th}
let amrBoxplotLogActiveSection = null; // null = ทั้งหมด

function amrBoxplotLogSectionKeyOf(r) {
  const t = amrBoxplotLogTypeByCode.get(r.business_type_code);
  return t && t.section_code ? t.section_code : AMR_LOG_UNCLASSIFIED_SECTION_KEY;
}

function amrBoxplotLogSectionLabelOf(r) {
  const t = amrBoxplotLogTypeByCode.get(r.business_type_code);
  return t && t.section_code ? `${t.section_code} · ${t.section_name_th}` : "ยังไม่ระบุหมวด";
}

function renderAmrBoxplotLogFilterBar() {
  const seen = new Map(); // section_code -> section_name_th
  let hasUnclassified = false;
  for (const r of amrBoxplotLogRows) {
    const t = amrBoxplotLogTypeByCode.get(r.business_type_code);
    if (t && t.section_code) seen.set(t.section_code, t.section_name_th);
    else hasUnclassified = true;
  }
  const sectionCodes = Array.from(seen.keys()).sort();

  const chips = [
    `<button type="button" class="amr-log-filter-chip ${amrBoxplotLogActiveSection === null ? "active" : ""}" data-section="">ทั้งหมด</button>`,
  ];
  for (const code of sectionCodes) {
    chips.push(
      `<button type="button" class="amr-log-filter-chip ${amrBoxplotLogActiveSection === code ? "active" : ""}" data-section="${escapeHtml(code)}" title="${escapeHtml(seen.get(code) || "")}">${escapeHtml(code)}</button>`
    );
  }
  if (hasUnclassified) {
    chips.push(
      `<button type="button" class="amr-log-filter-chip ${amrBoxplotLogActiveSection === AMR_LOG_UNCLASSIFIED_SECTION_KEY ? "active" : ""}" data-section="${AMR_LOG_UNCLASSIFIED_SECTION_KEY}">ยังไม่ระบุหมวด</button>`
    );
  }
  amrBoxplotLogFilterBar.innerHTML = chips.join("");
}

function renderAmrBoxplotLogTable() {
  if (!amrBoxplotLogRows.length) {
    amrBoxplotLogFilterBar.innerHTML = "";
    amrBoxplotLogTable.innerHTML = `<div class="hint">ยังไม่มีข้อมูล AMR จริงในระบบเลย — อัปโหลด/ดึงจากเว็บ PEA ได้จากด้านบน</div>`;
    return;
  }

  renderAmrBoxplotLogFilterBar();

  const visible =
    amrBoxplotLogActiveSection === null
      ? amrBoxplotLogRows
      : amrBoxplotLogRows.filter((r) => amrBoxplotLogSectionKeyOf(r) === amrBoxplotLogActiveSection);

  // จัดกลุ่มตาม section ก่อน (เรียง A-U ส่วนที่ยังไม่ระบุหมวดไว้ท้ายสุด) แล้วในแต่ละ section จัด
  // กลุ่มย่อยตาม TSIC อีกชั้น (เรียงตามรหัส) และเรียงตามจุดข้อมูลมากไปน้อยภายในกลุ่มเดียวกัน — ให้
  // บัญชีของ TSIC เดียวกันอยู่ติดกันเสมอ อ่านง่ายกว่าเรียงจุดข้อมูลล้วนๆ แบบปนกันทุก TSIC/section
  const bySection = new Map();
  for (const r of visible) {
    const key = amrBoxplotLogSectionKeyOf(r);
    if (!bySection.has(key)) bySection.set(key, []);
    bySection.get(key).push(r);
  }
  const sectionKeys = Array.from(bySection.keys()).sort((a, b) => {
    if (a === AMR_LOG_UNCLASSIFIED_SECTION_KEY) return 1;
    if (b === AMR_LOG_UNCLASSIFIED_SECTION_KEY) return -1;
    return a.localeCompare(b);
  });

  const rowsHtml = [];
  let amrBoxplotLogRowIndex = 0; // นับเฉพาะแถวข้อมูลจริง (ไม่รวมแถวหัว section/TSIC) ไว้ทำแถบสีสลับ
  for (const key of sectionKeys) {
    const group = [...bySection.get(key)].sort((a, b) => {
      if (a.business_type_code !== b.business_type_code) return a.business_type_code.localeCompare(b.business_type_code);
      return b.intervals - a.intervals;
    });
    rowsHtml.push(
      `<tr class="amr-log-section-header"><td colspan="${AMR_LOG_COLUMN_COUNT}">${escapeHtml(amrBoxplotLogSectionLabelOf(group[0]))} (${group.length} รายการ)</td></tr>`
    );
    // จัดกลุ่มย่อยตาม TSIC ภายใน section อีกชั้น — แสดงชื่อ/รหัส TSIC แค่ครั้งเดียวต่อกลุ่มในแถวหัว
    // กลุ่มย่อย (ไม่ต้องพิมพ์ซ้ำทุกแถวเหมือนเดิมซึ่งทำให้ตารางรกและลิงก์ "ดู Boxplot" ถูกบีบจนตัดคำ)
    // พร้อมลิงก์ดู Boxplot รวมทุกบัญชีไว้ในแถวหัวกลุ่มเดียวกัน (เฉพาะตอนมีมากกว่า 1 บัญชี)
    const byTsic = new Map();
    for (const r of group) {
      if (!byTsic.has(r.business_type_code)) byTsic.set(r.business_type_code, []);
      byTsic.get(r.business_type_code).push(r);
    }

    for (const [tsicCode, rows] of byTsic) {
      const name = (amrBoxplotLogTypeByCode.get(tsicCode) || {}).name_th || "";
      const tsicNameHtml = name
        ? `${escapeHtml(name)} · ${escapeHtml(tsicCode)}`
        : `${escapeHtml(tsicCode)} <span style="color:#d03b3b;">(ไม่พบชื่อในระบบ)</span>`;
      const combinedLinkHtml =
        rows.length > 1
          ? `<button type="button" class="amr-boxplot-log-view-combined-btn" data-code="${escapeHtml(tsicCode)}" style="border:none;background:none;color:#184f95;cursor:pointer;font-size:13px;padding:0;">📊 ดู Boxplot รวมทุกบัญชี →</button>`
          : "";
      // ค่าเริ่มต้นพับเก็บ (collapsed) ทุกกลุ่ม TSIC ไว้ก่อนเสมอ — ผู้ใช้ฟีดแบ็กว่าตารางแสดงทุกบัญชี
      // ของทุก TSIC พร้อมกันหมดลานตาเกินไป กดที่หัวกลุ่มเพื่อกางดูบัญชีของ TSIC นั้นทีละอันแทน (ไม่
      // เก็บ state ข้ามการ render ใหม่ — พับกลับเป็นค่าเริ่มต้นทุกครั้งที่ข้อมูล/ตัวกรองเปลี่ยน ซึ่งเป็น
      // พฤติกรรมที่ต้องการอยู่แล้ว ไม่ใช่บั๊ก)
      const tsicGroupId = `${key}::${tsicCode}`;
      rowsHtml.push(`<tr class="amr-log-tsic-header" data-tsic-group-toggle="${escapeHtml(tsicGroupId)}" style="cursor:pointer;"><td colspan="${AMR_LOG_COLUMN_COUNT}">
        <div class="amr-log-tsic-header-row">
          <span class="amr-log-tsic-name"><span class="amr-log-tsic-caret">▶</span> ${tsicNameHtml}<span class="amr-log-tsic-count">(${rows.length} บัญชี)</span></span>
          ${combinedLinkHtml}
        </div>
      </td></tr>`);

      // เรียงให้บัญชีของบริษัทเดียวกัน (เจอบ่อยมาก — ลูกค้ารายเดียวมีหลายเลขบัญชี PEA) อยู่ติดกัน
      // เสมอ (เดิมเรียงแค่ตามจุดข้อมูลมากไปน้อย บางทีบัญชีของบริษัทเดียวกันเลยไม่ติดกัน) แล้ว rowspan
      // เซลล์ "บริษัท"/"เลขนิติบุคคล" รวมเป็นแถวเดียวแทนที่จะพิมพ์ชื่อบริษัทซ้ำทุกบัญชี — ลดความรก
      // ลงมาก (ผู้ใช้ขอ "อ่านง่ายกว่านี้") บริษัทที่ไม่มีชื่อ (ว่าง) ไม่ merge กันเองเด็ดขาด กันเข้าใจ
      // ผิดว่าเป็นบริษัทเดียวกันทั้งที่จริงๆ แค่ไม่มีใครกรอกชื่อไว้
      const sortedRows = [...rows].sort((a, b) => {
        const an = a.company_name || "";
        const bn = b.company_name || "";
        if (an !== bn) {
          if (!an) return 1;
          if (!bn) return -1;
          return an.localeCompare(bn, "th");
        }
        return b.intervals - a.intervals;
      });

      let idx = 0;
      while (idx < sortedRows.length) {
        const r = sortedRows[idx];
        const companyName = r.company_name;
        let span = 1;
        if (companyName) {
          while (idx + span < sortedRows.length && sortedRows[idx + span].company_name === companyName) span++;
        }
        const spanRows = sortedRows.slice(idx, idx + span);
        const companyLabel = companyName ? escapeHtml(companyName) : `<span style="color:#8996ab;">—</span>`;
        const regValue = spanRows.map((x) => x.registration_no).find(Boolean) || "";
        const regLabel = regValue ? escapeHtml(regValue) : `<span style="color:#8996ab;">—</span>`;
        const rowspanAttr = span > 1 ? ` rowspan="${span}"` : "";

        spanRows.forEach((row, i) => {
          amrBoxplotLogRowIndex += 1;
          const zebraClass = amrBoxplotLogRowIndex % 2 === 0 ? "amr-log-row-even" : "";
          const accountLabel = row.account_no ? escapeHtml(row.account_no) : `<span style="color:#8996ab;">ไม่ระบุบัญชี</span>`;
          const companyCellHtml = i === 0 ? `<td${rowspanAttr}>${companyLabel}</td>` : "";
          const regCellHtml = i === 0 ? `<td${rowspanAttr}>${regLabel}</td>` : "";
          rowsHtml.push(`<tr class="${zebraClass}" data-tsic-group="${escapeHtml(tsicGroupId)}" style="display:none;">
            ${companyCellHtml}
            <td>${accountLabel}</td>
            ${regCellHtml}
            <td class="num">${row.intervals.toLocaleString("th-TH")}</td>
            <td class="num">${row.days.toLocaleString("th-TH")}</td>
            <td class="amr-log-action-cell">
              <button type="button" class="amr-boxplot-log-view-btn" data-code="${escapeHtml(row.business_type_code)}" data-account="${escapeHtml(row.account_no || "")}" style="border:none;background:none;color:#184f95;cursor:pointer;font-size:13px;padding:0;">📊 ดู Boxplot →</button>
              &nbsp;·&nbsp;
              <button type="button" class="amr-boxplot-log-quick-upload-btn" data-code="${escapeHtml(row.business_type_code)}" data-account="${escapeHtml(row.account_no || "")}" data-company="${escapeHtml(row.company_name || "")}" data-reg="${escapeHtml(row.registration_no || "")}" style="border:none;background:none;color:#184f95;cursor:pointer;font-size:13px;padding:0;">📤 อัปโหลดเพิ่ม</button>
              &nbsp;·&nbsp;
              <button type="button" class="amr-boxplot-log-edit-btn" data-code="${escapeHtml(row.business_type_code)}" data-account="${escapeHtml(row.account_no || "")}" data-company="${escapeHtml(row.company_name || "")}" data-reg="${escapeHtml(row.registration_no || "")}" style="border:none;background:none;color:#184f95;cursor:pointer;font-size:13px;padding:0;">✏️ แก้ไข</button>
              &nbsp;·&nbsp;
              <button type="button" class="amr-boxplot-log-delete-btn" data-code="${escapeHtml(row.business_type_code)}" data-account="${escapeHtml(row.account_no || "")}" data-intervals="${row.intervals}" style="border:none;background:none;color:#d03b3b;cursor:pointer;font-size:13px;padding:0;">🗑️ ลบ</button>
            </td>
          </tr>`);
        });
        idx += span;
      }
    }
  }

  amrBoxplotLogTable.innerHTML = `
    <table class="amr-log-table">
      <thead><tr><th>บริษัท</th><th>เลขบัญชี</th><th>เลขนิติบุคคล</th><th class="num">จำนวนจุดข้อมูล</th><th class="num">จำนวนวัน</th><th></th></tr></thead>
      <tbody>${rowsHtml.join("")}</tbody>
    </table>`;

  // กดที่หัวกลุ่ม TSIC เพื่อกาง/พับดูรายชื่อบัญชีของ TSIC นั้น (ค่าเริ่มต้นพับเก็บไว้หมดทุกกลุ่ม —
  // ดูคอมเมนต์ตอนสร้างแถวหัวกลุ่มด้านบน) ไม่ใช้ event delegation ที่ tbody เพราะต้อง stopPropagation
  // กันลิงก์ "ดู Boxplot รวมทุกบัญชี" ในแถวหัวกลุ่มเดียวกันโดนกดพับ/กางไปด้วยเวลาคลิกลิงก์นั้น
  amrBoxplotLogTable.querySelectorAll("tr.amr-log-tsic-header").forEach((headerRow) => {
    headerRow.addEventListener("click", (e) => {
      if (e.target.closest("button")) return; // คลิกปุ่ม "ดู Boxplot รวมทุกบัญชี" ไม่ต้องพับ/กาง
      const groupId = headerRow.dataset.tsicGroupToggle;
      const expanding = headerRow.classList.toggle("expanded");
      const caret = headerRow.querySelector(".amr-log-tsic-caret");
      if (caret) caret.textContent = expanding ? "▼" : "▶";
      amrBoxplotLogTable.querySelectorAll(`tr[data-tsic-group="${CSS.escape(groupId)}"]`).forEach((row) => {
        row.style.display = expanding ? "" : "none";
      });
    });
  });

  // ปุ่ม "ดู Boxplot รวมทุกบัญชี" ในแถวหัวกลุ่ม TSIC — วาดกราฟใหม่ทันทีในพื้นที่แสดงผลเดียวกับปุ่ม
  // "ดูกราฟ Boxplot ของประเภทธุรกิจนี้" ด้านบนสุดของการ์ด (ดู renderAmrBoxplotPreview) ไม่ต้องเลือก
  // TSIC จากช่องค้นหาเองอีกรอบ — ผู้ใช้ยืนยันอยากได้ปุ่มกดแล้ว "ทำกราฟใหม่ได้เลย" จากประวัติที่มีอยู่แล้ว
  amrBoxplotLogTable.querySelectorAll(".amr-boxplot-log-view-combined-btn").forEach((btn) => {
    btn.addEventListener("click", () => renderAmrBoxplotPreview(btn.dataset.code));
  });

  // ปุ่ม "ดู Boxplot" ต่อแถวบัญชี — เหมือนกันแต่กรองเหลือบัญชีเดียว (เดิมเป็นลิงก์ <a target="_blank">
  // เปิดแท็บใหม่ เปลี่ยนเป็นปุ่มวาดในหน้าเดิมแทน อ่านง่ายกว่า ไม่ต้องสลับแท็บไปมา)
  amrBoxplotLogTable.querySelectorAll(".amr-boxplot-log-view-btn").forEach((btn) => {
    btn.addEventListener("click", () => renderAmrBoxplotPreview(btn.dataset.code, btn.dataset.account));
  });

  // ปุ่ม "อัปโหลดเพิ่ม" ต่อแถวบัญชี — เติม TSIC/เลขบัญชี/ชื่อบริษัท/เลขทะเบียนนิติบุคคลของแถวนั้นลง
  // ในฟอร์มอัปโหลดด้านบนให้อัตโนมัติ (ดู prefillAmrBoxplotUploadForm) ผู้ใช้แค่เลือกไฟล์ใหม่แล้วกด
  // อัปโหลด ไม่ต้องพิมพ์ TSIC/เลขบัญชี/ชื่อบริษัทซ้ำเองเหมือนอัปโหลดครั้งแรก
  amrBoxplotLogTable.querySelectorAll(".amr-boxplot-log-quick-upload-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      prefillAmrBoxplotUploadForm(btn.dataset.code, btn.dataset.account, btn.dataset.company, btn.dataset.reg);
    });
  });

  // ปุ่มแก้ไขต่อแถว — แก้ชื่อบริษัท/เลขทะเบียนนิติบุคคลของบัญชีที่อัปโหลดไปแล้วโดยตรง ใช้ตอนไฟล์
  // ต้นทางไม่มีชื่อบริษัทให้เลย (เช่นรายงาน "Custom kW Report") หรือกรอกผิดตอนอัปโหลดครั้งแรก — ไม่
  // ต้องลบแล้วอัปโหลดใหม่ทั้งก้อน (append_intervals_local ไม่มี dedup ข้ามการอัปโหลด เสี่ยงข้อมูลซ้ำ)
  amrBoxplotLogTable.querySelectorAll(".amr-boxplot-log-edit-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const code = btn.dataset.code;
      const accountNo = btn.dataset.account;
      const companyName = prompt("ชื่อบริษัท (เว้นว่างไว้ได้ถ้าไม่ทราบ):", btn.dataset.company || "");
      if (companyName === null) return; // กดยกเลิก
      const registrationNo = prompt("เลขทะเบียนนิติบุคคล (DBD) — ไม่บังคับ เว้นว่างได้:", btn.dataset.reg || "");
      if (registrationNo === null) return;

      btn.disabled = true;
      try {
        const res = await fetch("/api/admin/amr-boxplot/data", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            business_type_code: code,
            account_no: accountNo,
            company_name: companyName.trim(),
            registration_no: registrationNo.trim(),
          }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          alert(data.message || "แก้ไขไม่สำเร็จ");
          btn.disabled = false;
          return;
        }
        loadAmrBoxplotLog();
      } catch (err) {
        alert("เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ");
        console.error(err);
        btn.disabled = false;
      }
    });
  });

  // ปุ่มลบต่อแถว — ลบข้อมูลจริงถาวร (เขียนทับไฟล์ CSV ตรงๆ ไม่มีทาง undo) ต้อง confirm() กับ
  // ผู้ใช้ก่อนเสมอ บอกให้ชัดว่ากำลังจะลบอะไร (TSIC + บัญชี + จำนวนจุดข้อมูล) กันกดพลาด
  amrBoxplotLogTable.querySelectorAll(".amr-boxplot-log-delete-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const code = btn.dataset.code;
      const accountNo = btn.dataset.account;
      const accountDesc = accountNo ? `บัญชี ${accountNo}` : 'กลุ่ม "ไม่ระบุบัญชี"';
      const confirmed = confirm(
        `ลบข้อมูล AMR จริงของ TSIC ${code} (${accountDesc}) ทั้งหมด ${Number(btn.dataset.intervals).toLocaleString("th-TH")} จุด ถาวรเลยหรือไม่?\n\nกู้คืนไม่ได้`
      );
      if (!confirmed) return;

      btn.disabled = true;
      try {
        const params = new URLSearchParams({ business_type_code: code, account_no: accountNo });
        const res = await fetch(`/api/admin/amr-boxplot/data?${params.toString()}`, { method: "DELETE" });
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          alert(data.message || "ลบไม่สำเร็จ");
          btn.disabled = false;
          return;
        }
        loadAmrBoxplotLog();
      } catch (err) {
        alert("เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ");
        console.error(err);
        btn.disabled = false;
      }
    });
  });
}

async function loadAmrBoxplotLog() {
  amrBoxplotLogStatus.textContent = "⏳ กำลังโหลด...";
  amrBoxplotLogTable.innerHTML = "";
  try {
    const [rowsRes, typesRes] = await Promise.all([
      fetch("/api/admin/amr-boxplot/status-by-account"),
      fetch("/api/business-types-full"),
    ]);
    amrBoxplotLogRows = await rowsRes.json();
    const types = await typesRes.json();
    amrBoxplotLogTypeByCode = new Map(types.map((t) => [t.code, t]));

    amrBoxplotLogStatus.textContent = "";
    renderAmrBoxplotLogTable();
  } catch (err) {
    amrBoxplotLogStatus.innerHTML = `<span style="color:#d03b3b;">โหลดไม่สำเร็จ</span>`;
    console.error(err);
  }
}

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

amrBoxplotLogFilterBar.addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-section]");
  if (!btn) return;
  const section = btn.dataset.section;
  amrBoxplotLogActiveSection = section === "" ? null : section;
  renderAmrBoxplotLogTable();
});

amrBoxplotLogRefreshBtn.addEventListener("click", loadAmrBoxplotLog);
loadAmrBoxplotLog();

// ── เช็คว่าบัญชีนี้ (เลขบัญชี PEA หรือ MEA No.) มีข้อมูล AMR จริงอยู่แล้วหรือยัง — ผู้ใช้ยืนยันไม่
// อยากไล่หาเองในตาราง log ด้านล่าง (อาจยาวมาก) แค่พิมพ์เลขบัญชีแล้วรู้ผลทันที ค้นจาก
// amrBoxplotLogRows ที่โหลดไว้แล้ว (ไม่ยิง request ใหม่ — ข้อมูลเดียวกับตาราง log ด้านล่างเป๊ะ รีเฟรช
// พร้อมกันเสมอ) เทียบแบบ "ตรงกันพอดี" ก่อน (ตัดช่องว่างหัวท้าย) ถ้าไม่เจอค่อยลองแบบ "มีคำนี้อยู่ในเลข
// บัญชี" ต่อ (เผื่อพิมพ์/จำเลขบัญชีมาไม่ครบ) — พิมพ์ทันทีเห็นผลทันที ไม่ต้องกดปุ่มแยก (debounce เล็ก
// น้อยกันยิงค้นหาถี่เกินไปตอนพิมพ์เร็ว)
const amrAccountCheckInput = document.getElementById("amr-account-check-input");
const amrAccountCheckResult = document.getElementById("amr-account-check-result");
let amrAccountCheckDebounceTimer = null;

function renderAmrAccountCheckResult() {
  const query = amrAccountCheckInput.value.trim();
  if (!query) {
    amrAccountCheckResult.innerHTML = "";
    return;
  }

  const exact = amrBoxplotLogRows.filter((r) => (r.account_no || "").trim() === query);
  const partial = exact.length ? [] : amrBoxplotLogRows.filter((r) => (r.account_no || "").includes(query));
  const matches = exact.length ? exact : partial;

  if (!matches.length) {
    amrAccountCheckResult.innerHTML = `❌ ยังไม่มีข้อมูล AMR ของบัญชี "${escapeHtml(query)}" ในระบบเลย — อัปโหลด/ดึงข้อมูลได้จากฟอร์มด้านบน`;
    return;
  }

  const rowsHtml = matches
    .map((r) => {
      const name = (amrBoxplotLogTypeByCode.get(r.business_type_code) || {}).name_th || "";
      const tsicLabel = name ? `${escapeHtml(name)} · ${escapeHtml(r.business_type_code)}` : escapeHtml(r.business_type_code);
      const companyPart = r.company_name ? ` — ${escapeHtml(r.company_name)}` : "";
      return `<div>บัญชี ${escapeHtml(r.account_no)}${companyPart} — ${tsicLabel} (${Number(r.intervals).toLocaleString("th-TH")} จุด / ${r.days} วัน)</div>`;
    })
    .join("");
  const foundLabel = exact.length ? "✅ มีข้อมูลแล้ว" : `✅ ไม่เจอตรงเป๊ะ แต่เจอเลขบัญชีที่มีคำนี้อยู่`;
  amrAccountCheckResult.innerHTML = `<div style="display:flex;flex-direction:column;gap:4px;">${foundLabel}${rowsHtml}</div>`;
}

amrAccountCheckInput.addEventListener("input", () => {
  clearTimeout(amrAccountCheckDebounceTimer);
  amrAccountCheckDebounceTimer = setTimeout(renderAmrAccountCheckResult, 200);
});

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
  if (amrBoxplotAccountNo.value.trim()) formData.append("account_no", amrBoxplotAccountNo.value.trim());
  if (amrBoxplotCompanyName.value.trim()) formData.append("company_name", amrBoxplotCompanyName.value.trim());
  if (amrBoxplotRegistrationNo.value.trim()) formData.append("registration_no", amrBoxplotRegistrationNo.value.trim());

  amrBoxplotUploadBtn.disabled = true;
  amrBoxplotUploadStatus.textContent = "⏳ กำลังอัปโหลด...";
  try {
    const res = await fetch("/api/admin/amr-boxplot/upload", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) {
      amrBoxplotUploadStatus.innerHTML = `<span style="color:#d03b3b;">${data.message || "เกิดข้อผิดพลาด"}</span>`;
      return;
    }
    const detectedParts = [];
    if (data.account_no_detected_from_file) detectedParts.push(`บัญชี ${escapeHtml(data.account_no)}`);
    if (data.company_name_detected_from_file) detectedParts.push(escapeHtml(data.company_name));
    const detectedNote = detectedParts.length ? ` — อ่านจากไฟล์ได้: ${detectedParts.join(" · ")}` : "";
    amrBoxplotUploadStatus.innerHTML = `<span style="color:#006300;">✅ เพิ่มข้อมูลแล้ว ${data.added_intervals.toLocaleString("th-TH")} จุด (${data.days} วัน)${detectedNote}</span>`;
    amrBoxplotFiles.value = "";
    loadAmrBoxplotLog();
    // อัปโหลดสำเร็จ = มีข้อมูลใหม่ของ (TSIC, บัญชี) นี้แล้ว วาดกราฟ Boxplot ใหม่ให้ดูทันทีที่ช่อง
    // แสดงผลด้านบน ไม่ต้องกดปุ่ม "ดูกราฟ Boxplot" เองอีกรอบ (ผู้ใช้ยืนยันอยากได้แบบนี้ — "ถ้ามีข้อมูล
    // ใหม่มา จะเปลี่ยนกราฟเลยโดยไม่ต้องไปกรอกใหม่") ใช้ bizCode/account_no ชุดเดียวกับที่เพิ่งอัปโหลด
    renderAmrBoxplotPreview(bizCode, data.account_no || "");
  } catch (err) {
    amrBoxplotUploadStatus.innerHTML = `<span style="color:#d03b3b;">เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ</span>`;
    console.error(err);
  } finally {
    amrBoxplotUploadBtn.disabled = false;
  }
});

// ── สลับโหมด "แนบไฟล์เอง" / "ดึงจากเว็บ PEA อัตโนมัติ" / "ดึงหลายบัญชีพร้อมกัน" ──

const amrBoxplotModeUploadBtn = document.getElementById("amr-boxplot-mode-upload-btn");
const amrBoxplotModeFetchBtn = document.getElementById("amr-boxplot-mode-fetch-btn");
const amrBoxplotModeBulkBtn = document.getElementById("amr-boxplot-mode-bulk-btn");
const amrBoxplotUploadPanel = document.getElementById("amr-boxplot-upload-panel");
const amrBoxplotFetchPanel = document.getElementById("amr-boxplot-fetch-panel");
const amrBoxplotBulkPanel = document.getElementById("amr-boxplot-bulk-panel");

function showAmrBoxplotMode(activeBtn, activePanel) {
  for (const [btn, panel] of [
    [amrBoxplotModeUploadBtn, amrBoxplotUploadPanel],
    [amrBoxplotModeFetchBtn, amrBoxplotFetchPanel],
    [amrBoxplotModeBulkBtn, amrBoxplotBulkPanel],
  ]) {
    btn.classList.toggle("active", btn === activeBtn);
    panel.style.display = panel === activePanel ? "flex" : "none";
  }
}

amrBoxplotModeUploadBtn.addEventListener("click", () => showAmrBoxplotMode(amrBoxplotModeUploadBtn, amrBoxplotUploadPanel));
amrBoxplotModeFetchBtn.addEventListener("click", () => showAmrBoxplotMode(amrBoxplotModeFetchBtn, amrBoxplotFetchPanel));
amrBoxplotModeBulkBtn.addEventListener("click", () => showAmrBoxplotMode(amrBoxplotModeBulkBtn, amrBoxplotBulkPanel));

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
    loadAmrBoxplotLog();
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

// ── ดึง AMR จริงจากเว็บ PEA อัตโนมัติทีละหลายบัญชีพร้อมกัน (ดู POST /api/admin/amr-boxplot/fetch-bulk
// — วนตรวจจับอัตโนมัติทีละบัญชีต่อเนื่องกันเป็น background job เดียวฝั่ง backend) ต่างจากโหมดบัญชี
// เดียวด้านบนตรงที่รับหลาย username/password พร้อมกัน (คนละบัญชี คนละรหัสผ่าน) ไม่ใช่หลายเลขบัญชี
// ภายใต้ login เดียว — ใช้ /api/admin/amr-boxplot/fetch/<job_id> ตัวเดิมโพลสถานะได้เลย (เป็น job
// generic ไม่ผูกกับ endpoint ที่สร้างมัน)
const amrBulkAccountsInput = document.getElementById("amr-bulk-accounts");
const amrBulkStartDate = document.getElementById("amr-bulk-start-date");
const amrBulkEndDate = document.getElementById("amr-bulk-end-date");
const amrBulkBtn = document.getElementById("amr-bulk-btn");
const amrBulkJobArea = document.getElementById("amr-bulk-job-area");
const amrBulkLog = document.getElementById("amr-bulk-log");
const amrBulkResult = document.getElementById("amr-bulk-result");

// แกะ textarea (บรรทัดละ 1 บัญชี รูปแบบ "เลขบัญชี,รหัสผ่าน" — รหัสผ่านเว้นว่างได้ถ้าตั้ง
// PEA_AMR_PASSWORD ไว้แล้วในเครื่อง) เป็น [{username, password}, ...] ข้ามบรรทัดว่างไปเฉยๆ
function parseAmrBulkAccounts(raw) {
  return raw
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((line) => {
      const idx = line.indexOf(",");
      const username = (idx === -1 ? line : line.slice(0, idx)).trim();
      const password = idx === -1 ? "" : line.slice(idx + 1).trim();
      return { username, password };
    });
}

function renderAmrBulkResults(results) {
  amrBulkResult.innerHTML = results
    .map((r) => {
      if (r.success) {
        return `<div class="amr-bulk-account-row"><span>✅ ${escapeHtml(r.username)}</span>` +
          `<span style="color:#55647a;">${(r.added_intervals || 0).toLocaleString("th-TH")} จุด (${r.days || 0} วัน) — ` +
          `${escapeHtml(r.business_type_code || "")}${r.business_type_name ? ` · ${escapeHtml(r.business_type_name)}` : ""}</span></div>`;
      }
      return `<div class="amr-bulk-account-row"><span>❌ ${escapeHtml(r.username)}</span>` +
        `<span style="color:#d03b3b;">${escapeHtml(r.error || "เกิดข้อผิดพลาด")}</span></div>`;
    })
    .join("");
}

async function pollAmrFetchBulkJob(jobId) {
  const res = await fetch(`/api/admin/amr-boxplot/fetch/${jobId}`);
  const data = await res.json();

  amrBulkLog.textContent = (data.logs || []).join("\n");
  amrBulkLog.scrollTop = amrBulkLog.scrollHeight;

  if (data.status === "running") {
    setTimeout(() => pollAmrFetchBulkJob(jobId), 1500);
    return;
  }

  amrBulkBtn.disabled = false;

  if (data.status === "success") {
    renderAmrBulkResults((data.result || {}).results || []);
    loadAmrBoxplotLog();
  } else {
    amrBulkResult.innerHTML = `<span style="color:#d03b3b;">${data.error || "เกิดข้อผิดพลาด"}</span>`;
  }
}

amrBulkBtn.addEventListener("click", async () => {
  const credentials = parseAmrBulkAccounts(amrBulkAccountsInput.value);
  if (!credentials.length) {
    amrBulkResult.innerHTML = `<span style="color:#d03b3b;">กรุณาพิมพ์รายชื่อบัญชีอย่างน้อย 1 บัญชี</span>`;
    return;
  }

  amrBulkBtn.disabled = true;
  amrBulkJobArea.style.display = "flex";
  amrBulkLog.textContent = "";
  amrBulkResult.textContent = "⏳ กำลังเริ่มงาน...";

  try {
    const res = await fetch("/api/admin/amr-boxplot/fetch-bulk", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        credentials,
        start_date: amrBulkStartDate.value,
        end_date: amrBulkEndDate.value,
      }),
    });
    const data = await res.json();

    if (!res.ok) {
      amrBulkBtn.disabled = false;
      amrBulkResult.innerHTML = `<span style="color:#d03b3b;">${data.message || "เกิดข้อผิดพลาด"}</span>`;
      return;
    }

    pollAmrFetchBulkJob(data.job_id);
  } catch (err) {
    amrBulkBtn.disabled = false;
    amrBulkResult.innerHTML = `<span style="color:#d03b3b;">เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ</span>`;
    console.error(err);
  }
});

// ── ดูกราฟ Boxplot ของประเภทธุรกิจที่เลือกไว้ตรงๆ จากหน้า Admin (ไม่ต้องไปหน้าแรกแล้วจับคู่ TSIC
// ก่อน) — ใช้ TSIC จาก dropdown ของแผงที่กำลังเปิดอยู่ (แนบไฟล์เอง หรือดึงจากเว็บ PEA อัตโนมัติ)
const amrBoxplotViewBtn = document.getElementById("amr-boxplot-view-btn");
const amrBoxplotViewStatus = document.getElementById("amr-boxplot-view-status");
const amrBoxplotViewImg = document.getElementById("amr-boxplot-view-img");
let amrBoxplotViewImgObjectUrl = null;

// วาดกราฟ Boxplot ใหม่จากข้อมูลที่สะสมไว้แล้ว ใช้พื้นที่แสดงผลเดียวกัน (amr-boxplot-view-status/
// -img) ไม่ว่าจะกดมาจากปุ่ม "ดูกราฟ Boxplot ของประเภทธุรกิจนี้" ด้านบน หรือปุ่ม "ดู Boxplot"/"ดู
// Boxplot รวมทุกบัญชี" ในตาราง log ด้านล่าง — เลือก TSIC/บัญชีจากประวัติที่มีอยู่แล้วแล้ววาดกราฟใหม่
// ได้ทันที ไม่ต้องพิมพ์/เลือกอะไรซ้ำเอง (ผู้ใช้ยืนยันอยากได้แบบนี้) accountNo = undefined รวมทุกบัญชี
// ของ TSIC นั้น, "" = เฉพาะกลุ่ม "ไม่ระบุบัญชี", ค่าอื่น = เฉพาะบัญชีนั้น
async function renderAmrBoxplotPreview(code, accountNo) {
  if (!code) {
    amrBoxplotViewStatus.innerHTML = `<span style="color:#d03b3b;">กรุณาเลือกประเภทธุรกิจ (TSIC) ก่อน</span>`;
    amrBoxplotViewImg.style.display = "none";
    return;
  }

  amrBoxplotViewBtn.disabled = true;
  amrBoxplotViewStatus.textContent = "⏳ กำลังโหลด...";
  amrBoxplotViewImg.style.display = "none";
  amrBoxplotViewStatus.scrollIntoView({ behavior: "smooth", block: "center" });

  try {
    const params = new URLSearchParams({ business_type_code: code });
    if (accountNo !== undefined) params.set("account_no", accountNo);
    const res = await fetch(`/api/forecast-boxplot?${params.toString()}`);
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
}

amrBoxplotViewBtn.addEventListener("click", () => {
  const activeSelect = amrBoxplotFetchPanel.style.display === "none" ? amrBoxplotBizSelect : amrFetchBizSelect;
  renderAmrBoxplotPreview(activeSelect.value);
});

// ปุ่ม "อัปโหลดเพิ่ม" ต่อแถวในตาราง log — เติม TSIC/เลขบัญชี/ชื่อบริษัท/เลขทะเบียนนิติบุคคลที่มีอยู่
// แล้วลงฟอร์มอัปโหลดด้านบนให้อัตโนมัติ (ไม่แตะช่องไฟล์ — ให้ผู้ใช้เลือกไฟล์ใหม่เอง) สลับไปโหมด "แนบ
// ไฟล์เอง" ให้ด้วยเผื่อผู้ใช้ค้างอยู่โหมดอื่น แล้วเลื่อนจอไปโฟกัสช่องเลือกไฟล์ทันที — ผู้ใช้ยืนยันอยาก
// อัปโหลดไฟล์ AMR เพิ่มให้ TSIC/บัญชีที่มีอยู่แล้วแบบเร็ว ไม่ต้องพิมพ์ข้อมูลเดิมซ้ำทุกครั้ง
function prefillAmrBoxplotUploadForm(code, accountNo, companyName, registrationNo) {
  const name = (amrBoxplotLogTypeByCode.get(code) || {}).name_th || "";
  const label = name ? `${name} · ${code}` : code;

  showAmrBoxplotMode(amrBoxplotModeUploadBtn, amrBoxplotUploadPanel);
  selectAmrBoxplotBiz(code, label);
  amrBoxplotAccountNo.value = accountNo || "";
  amrBoxplotCompanyName.value = companyName || "";
  amrBoxplotRegistrationNo.value = registrationNo || "";
  amrBoxplotFiles.value = "";
  amrBoxplotUploadStatus.innerHTML = `<span style="color:#184f95;">เติมข้อมูล TSIC/บัญชีนี้ให้แล้ว เลือกไฟล์ AMR ที่จะเพิ่มแล้วกด "อัปโหลด" ได้เลย</span>`;
  amrBoxplotFiles.scrollIntoView({ behavior: "smooth", block: "center" });
  amrBoxplotFiles.focus();
}

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
const forecastManualBtn = document.getElementById("forecast-shape-manual-btn");
const forecastStatus = document.getElementById("forecast-shape-status");
const forecastImg = document.getElementById("forecast-shape-img");

// สลับโหมด "แนบไฟล์ AMR" / "กรอกตัวเลขจากบิลเอง" — เหมือนแพทเทิร์น mode-tab-bar ของการ์ด AMR
// Boxplot ด้านบนทุกประการ ใช้ status/img ช่องเดียวกันทั้งสองโหมด (ผลลัพธ์หน้าตาเหมือนกันเป๊ะ
// ต่างกันแค่ว่าตัวเลข Peak/หน่วยไฟ/จำนวนวันมาจากไหน)
const fcModeUploadBtn = document.getElementById("fc-mode-upload-btn");
const fcModeManualBtn = document.getElementById("fc-mode-manual-btn");
const fcUploadPanel = document.getElementById("fc-upload-panel");
const fcManualPanel = document.getElementById("fc-manual-panel");

function showForecastShapeMode(activeBtn, activePanel) {
  for (const [btn, panel] of [
    [fcModeUploadBtn, fcUploadPanel],
    [fcModeManualBtn, fcManualPanel],
  ]) {
    btn.classList.toggle("active", btn === activeBtn);
    panel.style.display = panel === activePanel ? "flex" : "none";
  }
}

fcModeUploadBtn.addEventListener("click", () => showForecastShapeMode(fcModeUploadBtn, fcUploadPanel));
fcModeManualBtn.addEventListener("click", () => showForecastShapeMode(fcModeManualBtn, fcManualPanel));

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

// โหมด "กรอกตัวเลขจากบิลเอง" — เรียก GET /api/forecast-shape ตรงๆ (รับพารามิเตอร์ peak_*/energy_*/
// days_* ผ่าน query string อยู่แล้วตั้งแต่แรก แค่ไม่เคยมีฟอร์มในหน้าเว็บให้กรอกเท่านั้น) ส่งเฉพาะช่อง
// ที่มีค่า (เว้นว่างไว้ = ไม่ส่ง ให้ backend ใช้ค่ากลางเริ่มต้นของมันเอง — ดู forecast_shape.py
// DEFAULT_DAYS) ต้องกรอก Peak อย่างน้อย 1 ช่วง (P, OP หรือ H) เหมือนโหมดแนบไฟล์
const FC_MANUAL_FIELDS = [
  { rate: "P", peak: "fc-peak-p", energy: "fc-energy-p", days: "fc-days-p" },
  { rate: "OP", peak: "fc-peak-op", energy: "fc-energy-op", days: "fc-days-op" },
  { rate: "H", peak: "fc-peak-h", energy: "fc-energy-h", days: "fc-days-h" },
];

forecastManualBtn.addEventListener("click", async () => {
  const params = new URLSearchParams();
  let hasPeak = false;
  for (const { rate, peak, energy, days } of FC_MANUAL_FIELDS) {
    const peakVal = document.getElementById(peak).value.trim();
    const energyVal = document.getElementById(energy).value.trim();
    const daysVal = document.getElementById(days).value.trim();
    if (peakVal !== "") {
      hasPeak = true;
      params.set(`peak_${rate.toLowerCase()}`, peakVal);
    }
    if (energyVal !== "") params.set(`energy_${rate.toLowerCase()}`, energyVal);
    if (daysVal !== "") params.set(`days_${rate.toLowerCase()}`, daysVal);
  }
  if (!hasPeak) {
    forecastStatus.innerHTML = `<span style="color:#d03b3b;">กรุณากรอก Peak (kW) อย่างน้อย 1 ช่วง (P, OP หรือ H)</span>`;
    return;
  }
  const dropPct = forecastDropPct.value.trim();
  if (dropPct !== "") params.set("drop_pct", dropPct);

  forecastManualBtn.disabled = true;
  forecastStatus.textContent = "⏳ กำลังพยากรณ์...";
  forecastImg.style.display = "none";

  try {
    const res = await fetch(`/api/forecast-shape?${params.toString()}`);
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      forecastStatus.innerHTML = `<span style="color:#d03b3b;">${data.message || "เกิดข้อผิดพลาด"}</span>`;
      return;
    }

    const blob = await res.blob();
    if (forecastImgObjectUrl) URL.revokeObjectURL(forecastImgObjectUrl);
    forecastImgObjectUrl = URL.createObjectURL(blob);
    forecastImg.src = forecastImgObjectUrl;
    forecastImg.style.display = "block";
    forecastStatus.textContent = "";
  } catch (err) {
    forecastStatus.innerHTML = `<span style="color:#d03b3b;">เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ</span>`;
    console.error(err);
  } finally {
    forecastManualBtn.disabled = false;
  }
});
