const PERIOD_TH = { P: "Peak (P)", OP: "Off-Peak (OP)", H: "Holiday (H)" };

const businessTypeSelect = document.getElementById("f-business-type");
const fileBusinessTypeSelect = document.getElementById("f-file-business-type");
const submitBtn = document.getElementById("submit-btn");
const submitFileBtn = document.getElementById("submit-file-btn");
const formHint = document.getElementById("form-hint");
const jobArea = document.getElementById("job-area");
const jobStatusPill = document.getElementById("job-status-pill");
const jobLog = document.getElementById("job-log");
const jobResult = document.getElementById("job-result");
const usernameInput = document.getElementById("f-username");
const accountsInput = document.getElementById("f-accounts");

// ── สลับโหมดนำเข้า: ดึงจากเว็บ PEA (username/password) vs แนบไฟล์ที่มีอยู่แล้ว ──

const importModeWebEl = document.getElementById("import-mode-web");
const importModeFileEl = document.getElementById("import-mode-file");

document.querySelectorAll(".import-mode-tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".import-mode-tab-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    const isFileMode = btn.dataset.mode === "file";
    importModeWebEl.style.display = isFileMode ? "none" : "block";
    importModeFileEl.style.display = isFileMode ? "block" : "none";
    formHint.textContent = "";
  });
});

// username ที่ใช้ login เข้าเว็บ AMR ของ PEA ส่วนใหญ่คือเลขบัญชีผู้ใช้ไฟนั้นเอง (login
// แบบลูกค้ารายบุคคล 1 login = 1 บัญชี) — เติมช่องเลขบัญชีให้อัตโนมัติเมื่อพิมพ์ username
// เสร็จ (ออกจากช่อง) ถ้าช่องเลขบัญชียังว่างอยู่ หรือผู้ใช้ยังไม่เคยแก้เอง
let accountsEditedByUser = false;
accountsInput.addEventListener("input", () => {
  accountsEditedByUser = true;
});
usernameInput.addEventListener("blur", () => {
  const username = usernameInput.value.trim();
  if (username && !accountsEditedByUser) {
    accountsInput.value = username;
  }
});

async function loadBusinessTypes() {
  try {
    const res = await fetch("/api/business-types");
    const types = await res.json();
    const optionsHtml = types.map((t) => `<option value="${t.code}">${t.name_th} (${t.code})</option>`).join("");
    // โหมดดึงจากเว็บ: ปล่อยว่างได้ (ให้ระบบตรวจจับอัตโนมัติ) — โหมดแนบไฟล์ไม่มีการตรวจจับ
    // อัตโนมัติเลย (ไม่ได้เข้าหน้าข้อมูลผู้ใช้ไฟของ PEA) จึงบังคับต้องเลือกเอง
    businessTypeSelect.innerHTML = `<option value="">-- ให้ระบบตรวจจับอัตโนมัติ --</option>` + optionsHtml;
    fileBusinessTypeSelect.innerHTML = `<option value="">-- เลือกประเภทธุรกิจ --</option>` + optionsHtml;
  } catch (err) {
    console.error("โหลดประเภทธุรกิจไม่สำเร็จ", err);
  }
}

// ── ตาราง "ประวัติการนำเข้า AMR ในเครื่องนี้" (import_log_local.csv — ชื่อจริง ไม่ commit) ──

const importLogRefreshBtn = document.getElementById("import-log-refresh-btn");
const importLogGroupsEl = document.getElementById("import-log-groups");

// เก็บ log ล่าสุดไว้ใช้เดา "ชื่อบริษัทที่น่าจะตรงกับหมวดธุรกิจนี้" ตอนเปิดแผงตรวจสอบ TSIC ด้านล่าง
let importLogEntries = [];

function formatImportedDate(iso) {
  try {
    return new Date(iso).toLocaleDateString("th-TH", { dateStyle: "medium" });
  } catch (err) {
    return iso || "";
  }
}

function formatImportedTime(iso) {
  try {
    return new Date(iso).toLocaleTimeString("th-TH", { timeStyle: "short" });
  } catch (err) {
    return "";
  }
}

// จัดกลุ่มประวัติการนำเข้าตามวัน (ใช้วันที่แสดงผลเป็น key) — entries เข้ามาเรียงใหม่สุดก่อนอยู่แล้ว
// (จาก backend) จึงได้กลุ่มเรียงวันใหม่สุดก่อนไปโดยไม่ต้อง sort เพิ่ม
function groupImportLogByDate(entries) {
  const groups = [];
  const indexByLabel = {};
  entries.forEach((e) => {
    const label = formatImportedDate(e.imported_at);
    if (!(label in indexByLabel)) {
      indexByLabel[label] = groups.length;
      groups.push({ label, entries: [] });
    }
    groups[indexByLabel[label]].entries.push(e);
  });
  return groups;
}

// วันไหนเคยกดเปิดดูไว้ - เก็บไว้ให้ยังเปิดค้างอยู่ต่อ แม้จะกดรีเฟรชใหม่ก็ตาม
const openImportLogDates = new Set();

function toggleImportLogDate(label, index) {
  const panel = document.getElementById(`import-log-panel-${index}`);
  if (!panel) return;
  if (openImportLogDates.has(label)) {
    openImportLogDates.delete(label);
    panel.classList.remove("open");
  } else {
    openImportLogDates.add(label);
    panel.classList.add("open");
  }
}

function renderImportLogGroups(entries) {
  const groups = groupImportLogByDate(entries);

  importLogGroupsEl.innerHTML = groups.length
    ? groups
        .map((g, i) => {
          const isOpen = openImportLogDates.has(g.label);
          const rows = g.entries
            .map(
              (e) => `
            <tr style="border-bottom:1px solid rgba(15,23,42,0.06);">
              <td style="padding:8px 10px;">${formatImportedTime(e.imported_at)}</td>
              <td style="padding:8px 10px;font-weight:600;">${e.company_name || "-"}</td>
              <td style="padding:8px 10px;">${e.account_no || "-"}</td>
              <td style="padding:8px 10px;">${e.business_type_code}</td>
              <td style="padding:8px 10px;">${e.rate_code}</td>
            </tr>`
            )
            .join("");
          return `
            <div class="section-block">
              <button type="button" class="section-pill-btn import-log-date-btn" data-label="${g.label}" data-index="${i}">
                <span>${g.label}</span>
                <span class="section-count">${g.entries.length} รายการ</span>
              </button>
              <div class="section-panel${isOpen ? " open" : ""}" id="import-log-panel-${i}" style="padding:0 18px 16px;">
                <div style="overflow-x:auto;">
                  <table style="width:100%;border-collapse:collapse;font-size:13px;">
                    <thead>
                      <tr style="text-align:left;border-bottom:2px solid rgba(15,23,42,0.1);">
                        <th style="padding:8px 10px;">เวลา</th>
                        <th style="padding:8px 10px;">ชื่อบริษัท/นิติบุคคล</th>
                        <th style="padding:8px 10px;">เลขบัญชี</th>
                        <th style="padding:8px 10px;">ประเภทธุรกิจ</th>
                        <th style="padding:8px 10px;">รหัสอัตรา</th>
                      </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                  </table>
                </div>
              </div>
            </div>`;
        })
        .join("")
    : `<div class="hint" style="padding:12px 10px;">ยังไม่เคยนำเข้าแบบอัตโนมัติจากเครื่องนี้เลย</div>`;

  importLogGroupsEl.querySelectorAll(".import-log-date-btn").forEach((btn) => {
    btn.addEventListener("click", () => toggleImportLogDate(btn.dataset.label, btn.dataset.index));
  });
}

async function loadImportLogLocal() {
  importLogGroupsEl.innerHTML = `<div class="hint" style="padding:12px 10px;">กำลังโหลด...</div>`;
  try {
    const res = await fetch("/api/import-log-local");
    importLogEntries = await res.json();
    renderImportLogGroups(importLogEntries);
  } catch (err) {
    importLogGroupsEl.innerHTML = `<div class="hint" style="padding:12px 10px;color:#d03b3b;">โหลดไม่สำเร็จ</div>`;
    console.error("โหลดประวัติการนำเข้าไม่สำเร็จ", err);
  }
}

importLogRefreshBtn.addEventListener("click", loadImportLogLocal);

// หาชื่อบริษัทล่าสุดในประวัติการนำเข้าที่ตรงกับรหัสประเภทธุรกิจนี้ (ไว้เติมช่องค้นหาให้อัตโนมัติ)
function guessCompanyNameForBusinessType(businessTypeCode) {
  const match = importLogEntries.find((e) => e.business_type_code === businessTypeCode && e.company_name);
  return match ? match.company_name : "";
}

// ── "หมวดหมู่ธุรกิจทั้งหมดในระบบ" จัดกลุ่มตาม Section (TSIC) ก่อน แล้วค่อยแยก Division/
//    ประเภทธุรกิจย่อยด้านใน — แต่ละประเภทธุรกิจแสดงรายชื่อบริษัทที่เคยนำเข้า (จาก import log)
//    และปุ่มดูกราฟการใช้ไฟจริงจาก AMR (ยังไม่ใช่ส่วนพยากรณ์ — แค่สำรวจรูปแบบก่อนนำไปใช้) ──

const businessTypesRefreshBtn = document.getElementById("business-types-refresh-btn");
const businessTypesBySectionEl = document.getElementById("business-types-by-section");

// โครงสร้าง Section/Division ของ TSIC (อิง ISIC Rev.4 ที่ TSIC ใช้เป็นฐาน) — ใช้แค่เดา Section
// จาก Division ให้อัตโนมัติตอนตรวจสอบ (แก้ไขเองได้เสมอถ้าไม่ตรง)
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

// กรองรายการในกล่อง dropdown ค้นหา (ใช้ร่วมกันทั้งกล่องค้นหาบริษัท/ไซต์ และกล่องค้นหาประเภทธุรกิจ)
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

function filterCompanyDropdown(input) {
  filterComboboxDropdown(input, ".company-combobox", ".company-dropdown-item", ".company-dropdown-empty");
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
  document.querySelectorAll(".company-combobox.open, .biz-type-combobox.open, .section-combobox.open").forEach((box) => {
    if (!box.contains(e.target)) box.classList.remove("open");
  });
});

// รายชื่อบริษัท (ไม่ซ้ำ) ที่เคยนำเข้าไว้สำหรับประเภทธุรกิจรหัสนี้ — มาจาก import log ในเครื่องนี้
function companiesForBusinessType(code) {
  const seen = new Set();
  const result = [];
  importLogEntries
    .filter((e) => e.business_type_code === code)
    .forEach((e) => {
      const key = `${e.company_name}|${e.account_no}`;
      if (!seen.has(key)) {
        seen.add(key);
        result.push(e);
      }
    });
  return result;
}

function renderBizCard(t) {
  const divisionBadge = t.division_code
    ? `<span class="biz-division-badge">Division ${t.division_code}${t.division_name_th ? ` · ${t.division_name_th}` : ""}</span>`
    : `<span class="biz-division-badge">ยังไม่ทราบ Division</span>`;

  const companies = companiesForBusinessType(t.code);
  const companiesHtml = companies.length
    ? `
      <div class="company-combobox">
        <input type="text" class="company-search-input" placeholder="🔍 ค้นหาบริษัท/ไซต์ (${companies.length} รายการ)..." autocomplete="off">
        <div class="company-dropdown">
          ${companies
            .map(
              (c) =>
                `<button type="button" class="company-dropdown-item company-chip-btn" data-account="${c.account_no}">
                  <span class="delete-import-log-icon" data-account="${c.account_no}" data-imported-at="${c.imported_at}" title="ลบรายการประวัตินี้ทิ้ง (แค่ประวัติ ไม่กระทบข้อมูลที่ใช้พยากรณ์จริง)" style="float:right;color:#a01818;font-weight:400;padding:0 2px;">✕</span>
                  ${c.company_name}${c.account_no ? ` · ${c.account_no}` : ""} 📈
                </button>`
            )
            .join("")}
          <div class="company-dropdown-empty" style="display:none;">ไม่พบบริษัท/ไซต์ที่ตรงกับคำค้นหา</div>
        </div>
      </div>`
    : `<span class="hint">ยังไม่มีประวัติการนำเข้าในเครื่องนี้สำหรับประเภทนี้</span>`;
  const siteCurvePanels = companies
    .filter((c) => c.account_no)
    .map((c) => `<div id="site-curve-panel-${c.account_no}" style="display:none;"></div>`)
    .join("");

  const profileButtons = t.profiles.length
    ? t.profiles
        .map((p) => {
          const solarLabel = p.has_solar ? " · ☀️ ติด Solar" : "";
          return `
            <span style="display:inline-flex;align-items:center;gap:4px;">
              <button type="button" class="day-type-btn curve-toggle-btn" data-code="${t.code}" data-rate="${p.rate_code}" data-solar="${p.has_solar}">📈 ดูกราฟ · อัตรา ${p.rate_code}${solarLabel} (${p.sample_size} ตัวอย่าง)</button>
              <button type="button" class="delete-profile-btn" data-code="${t.code}" data-rate="${p.rate_code}" data-solar="${p.has_solar}" title="ลบโปรไฟล์นี้ทิ้ง (เช่นนำเข้าผิดบัญชี/ผิดประเภทธุรกิจไป)" style="border:1px solid rgba(160,24,24,0.35);background:#fff;color:#a01818;border-radius:8px;width:26px;height:26px;cursor:pointer;font-size:13px;line-height:1;">✕</button>
            </span>`;
        })
        .join("")
    : `<span class="hint">ยังไม่มีโปรไฟล์อ้างอิง</span>`;

  const curvePanels = t.profiles
    .map((p) => {
      const solarTag = p.has_solar ? "solar" : "nosolar";
      return `<div id="curve-panel-${t.code}-${p.rate_code}-${solarTag}" style="display:none;"></div>`;
    })
    .join("");

  return `
    <div class="biz-card" data-code="${t.code}">
      <div class="biz-card-header">
        <div><span class="biz-code">${t.code}</span>${t.name_th}${divisionBadge}</div>
        <button type="button" class="day-type-btn verify-toggle-btn" data-code="${t.code}">🔍 ตรวจสอบ TSIC</button>
      </div>
      <div class="biz-companies">${companiesHtml}</div>
      ${siteCurvePanels}
      <div class="biz-profiles">${profileButtons}</div>
      <div id="verify-panel-${t.code}" style="display:none;"></div>
      ${curvePanels}
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
// dropdown เดียว (เดิมเป็นลิสต์ปุ่มกางออก/หุบเข้าทีละอัน ยาวเกินไปเวลามีหลาย Section)
let selectedSectionKey = null;

// รายการประเภทธุรกิจล่าสุดที่ fetch มา (เก็บไว้ใช้กรองใหม่ตอนติ๊ก/ถอดติ๊ก checkbox โดยไม่ต้อง
// ยิง request ไปเซิร์ฟเวอร์ซ้ำ)
let lastBusinessTypes = [];

const hideNoCurveCheckbox = document.getElementById("hide-no-curve-checkbox");
hideNoCurveCheckbox.addEventListener("change", () => renderBusinessTypesSections(lastBusinessTypes));

// ประเภทธุรกิจหนึ่งตัว "มีกราฟจาก AMR จริง" ถ้ามีโปรไฟล์อย่างน้อย 1 อัตราที่ has_curve เป็น true
// (แถว placeholder ใน load_profiles.csv มีแค่ตัวเลขเฉลี่ย ไม่มีข้อมูลรายชั่วโมงจริง จะไม่ผ่านเงื่อนไขนี้)
function businessTypeHasAnyCurve(t) {
  return t.profiles.some((p) => p.has_curve);
}

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
    const types = hideNoCurveCheckbox.checked ? allTypes.filter(businessTypeHasAnyCurve) : allTypes;
    const groups = groupBySection(types);

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
    // (รูปแบบเดียวกับกล่องค้นหาประเภทธุรกิจ/บริษัท-ไซต์ที่มีอยู่แล้วในหน้านี้)
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
    businessTypesBySectionEl.querySelectorAll(".curve-toggle-btn").forEach((btn) => {
      btn.addEventListener("click", () => toggleCurvePanel(btn.dataset.code, btn.dataset.rate, btn.dataset.solar === "true"));
    });
    businessTypesBySectionEl.querySelectorAll(".delete-profile-btn").forEach((btn) => {
      btn.addEventListener("click", () => deleteLoadProfile(btn.dataset.code, btn.dataset.rate, btn.dataset.solar === "true"));
    });
    businessTypesBySectionEl.querySelectorAll(".company-chip-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        const delIcon = e.target.closest(".delete-import-log-icon");
        if (delIcon) {
          e.stopPropagation();
          deleteImportLogEntry(delIcon.dataset.account, delIcon.dataset.importedAt);
          return;
        }
        toggleSiteCurvePanel(btn.dataset.account);
      });
    });
    businessTypesBySectionEl.querySelectorAll(".company-search-input").forEach((input) => {
      input.addEventListener("focus", () => {
        input.closest(".company-combobox").classList.add("open");
        filterCompanyDropdown(input);
      });
      input.addEventListener("input", () => filterCompanyDropdown(input));
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

// ลบโปรไฟล์+เส้นโค้งอ้างอิงของคู่ประเภทธุรกิจ+อัตราหนึ่งคู่ทิ้ง — ใช้ตอนนำเข้าผิดบัญชี/ผิดประเภท
// ธุรกิจไปแล้ว (เช่นเลือกประเภทธุรกิจผิดตอน resolve รายการรอทราบอัตรา) ไฟล์ AMR ดิบเดิมไม่ได้ถูก
// ลบไปด้วย ยังนำเข้าใหม่ให้ถูกต้องได้ทีหลัง
async function deleteLoadProfile(code, rateCode, hasSolar) {
  if (!confirm(`ลบโปรไฟล์ + เส้นโค้งของ "${code}" อัตรา "${rateCode}"${hasSolar ? " (ติด Solar)" : ""} ทิ้งจริงหรือไม่?\n\n(ข้อมูล AMR ดิบที่เคยนำเข้ายังอยู่ครบ นำเข้าใหม่ให้ถูกต้องได้ทีหลัง)`)) {
    return;
  }
  try {
    const res = await fetch(
      `/api/admin/load-profile/${encodeURIComponent(code)}/${encodeURIComponent(rateCode)}?has_solar=${hasSolar}`,
      { method: "DELETE" }
    );
    if (!res.ok) {
      const data = await res.json();
      alert(data.message || "ลบไม่สำเร็จ");
      return;
    }
    loadBusinessTypesTable();
  } catch (err) {
    alert("เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ");
    console.error(err);
  }
}

// ลบ 1 แถวในประวัติการนำเข้า (import_log_local.csv) ทิ้ง — แค่ความสะอาดของประวัติที่แสดงใน
// dropdown บริษัท/ไซต์ ไม่กระทบข้อมูลที่ใช้พยากรณ์จริงเลย (ดู deleteLoadProfile สำหรับลบตัวที่ใช้
// พยากรณ์จริง)
async function deleteImportLogEntry(accountNo, importedAt) {
  if (!confirm("ลบรายการประวัตินี้ทิ้งหรือไม่? (แค่ลบประวัติที่แสดงตรงนี้ ไม่กระทบข้อมูลที่ใช้พยากรณ์จริงเลย)")) {
    return;
  }
  try {
    const res = await fetch("/api/admin/import-log-local", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ imported_at: importedAt, account_no: accountNo }),
    });
    if (!res.ok) {
      const data = await res.json();
      alert(data.message || "ลบไม่สำเร็จ");
      return;
    }
    await loadImportLogLocal();
    renderBusinessTypesSections(lastBusinessTypes);
  } catch (err) {
    alert("เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ");
    console.error(err);
  }
}

// ── กราฟการใช้ไฟจาก AMR จริงของแต่ละคู่ประเภทธุรกิจ+อัตรา (ข้อมูลดิบ ไม่สเกล — ยังไม่ใช่การ
//    พยากรณ์ แค่ดูว่าประเภทธุรกิจนี้มีรูปแบบการใช้ไฟแบบไหน) ──

const openCurvePanels = new Set();

async function toggleCurvePanel(code, rateCode, hasSolar) {
  const solarTag = hasSolar ? "solar" : "nosolar";
  const key = `${code}|${rateCode}|${solarTag}`;
  const panel = document.getElementById(`curve-panel-${code}-${rateCode}-${solarTag}`);
  if (openCurvePanels.has(key)) {
    openCurvePanels.delete(key);
    panel.style.display = "none";
    return;
  }
  openCurvePanels.add(key);
  panel.style.display = "block";
  if (!panel.dataset.built) {
    panel.dataset.built = "1";
    panel.innerHTML = `<div class="hint" style="padding:12px 0;">⏳ กำลังโหลดกราฟ...</div>`;
    try {
      const res = await fetch(
        `/api/admin/curve/${encodeURIComponent(code)}/${encodeURIComponent(rateCode)}?has_solar=${hasSolar}`
      );
      const curveData = await res.json();
      initDailyCurveSection(panel, curveData);
    } catch (err) {
      panel.innerHTML = `<div class="hint" style="color:#d03b3b;">โหลดกราฟไม่สำเร็จ</div>`;
      console.error("โหลดกราฟไม่สำเร็จ", err);
    }
  }
}

// ── กราฟของแต่ละไซต์/บัญชีแยกต่างหาก (คนละกับ toggleCurvePanel ด้านบนที่เป็นค่าเฉลี่ยรวม) —
//    กดที่ชื่อบริษัทในการ์ดเพื่อดูกราฟของไซต์นั้นไซต์เดียว ไม่ใช่ค่าเฉลี่ยรวมกับไซต์อื่น ──

const openSiteCurvePanels = new Set();

async function toggleSiteCurvePanel(accountNo) {
  const panel = document.getElementById(`site-curve-panel-${accountNo}`);
  if (!panel) return;

  const dropdownItem = businessTypesBySectionEl.querySelector(`.company-dropdown-item[data-account="${accountNo}"]`);

  if (openSiteCurvePanels.has(accountNo)) {
    openSiteCurvePanels.delete(accountNo);
    panel.style.display = "none";
    if (dropdownItem) dropdownItem.classList.remove("active");
    return;
  }
  openSiteCurvePanels.add(accountNo);
  panel.style.display = "block";
  if (dropdownItem) dropdownItem.classList.add("active");
  if (!panel.dataset.built) {
    panel.dataset.built = "1";
    panel.innerHTML = `<div class="hint" style="padding:12px 0;">⏳ กำลังโหลดกราฟ...</div>`;
    try {
      const res = await fetch(`/api/admin/site-curve/${encodeURIComponent(accountNo)}`);
      const curveData = await res.json();
      if (!curveData.available) {
        panel.innerHTML = `<div class="hint" style="padding:12px 0;">ยังไม่มีกราฟแยกของไซต์นี้ (นำเข้าไว้ก่อนฟีเจอร์นี้จะมี หรือใช้โหมดกรอกเองซึ่งไม่ทราบชื่อบริษัท — นำเข้าใหม่อีกครั้งด้วยโหมดอัตโนมัติเพื่อให้มีกราฟแยก)</div>`;
        return;
      }
      initDailyCurveSection(panel, curveData);
    } catch (err) {
      panel.innerHTML = `<div class="hint" style="color:#d03b3b;">โหลดกราฟไม่สำเร็จ</div>`;
      console.error("โหลดกราฟของไซต์ไม่สำเร็จ", err);
    }
  }
}

// ── แผงตรวจสอบ TSIC ในการ์ด (ค้นหาจากชื่อบริษัทที่เคยนำเข้า แล้วบันทึกกลับเข้า business_types.csv) ──

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
  const guessedName = guessCompanyNameForBusinessType(code);
  panel.innerHTML = `
    <div class="verify-panel">
      <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end;">
        <div class="form-field" style="flex:1;min-width:220px;">
          <label for="verify-name-input-${code}">ชื่อบริษัท/นิติบุคคล (ค้นหาจาก DBD DataWarehouse — ไม่บังคับ)</label>
          <input id="verify-name-input-${code}" type="text" value="${guessedName}" placeholder="เช่น บริษัท ตัวอย่าง จำกัด">
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

function setStatusPill(status) {
  const map = {
    running: { text: "⏳ กำลังทำงาน...", bg: "#eef3fa", color: "#184f95" },
    success: { text: "✅ สำเร็จ", bg: "#e8f7ec", color: "#006300" },
    error: { text: "❌ ไม่สำเร็จ", bg: "#fdecea", color: "#a01818" },
    pending_rate: { text: "📋 บันทึกไว้รอทราบอัตรา", bg: "#fff8e6", color: "#8a6100" },
  };
  const s = map[status] || map.running;
  jobStatusPill.textContent = s.text;
  jobStatusPill.style.background = s.bg;
  jobStatusPill.style.color = s.color;
}

function renderResult(result, customerProfile) {
  const nameBlock =
    customerProfile && customerProfile.name
      ? `<div class="field-item" style="margin-bottom:12px;">
          <div class="field-label">ชื่อบริษัทจริงที่ตรวจพบ (แสดงในเครื่องนี้เท่านั้น — ไม่ถูกบันทึกลงไฟล์ใดๆ)</div>
          <div class="field-value" style="font-size:16px;">${customerProfile.name}${customerProfile.account_no ? ` · บัญชี ${customerProfile.account_no}` : ""}</div>
        </div>`
      : "";

  jobResult.innerHTML = `
    ${nameBlock}
    <div class="field-grid" style="grid-template-columns: repeat(3, minmax(0,1fr));">
      ${["P", "OP", "H"]
        .map(
          (p) => `
        <div class="field-item">
          <div class="field-label">${PERIOD_TH[p]}</div>
          <div class="field-value">Demand ${result.demand_kw[p]} kW · Energy ${result.energy_kwh[p].toLocaleString("th-TH")} kWh</div>
        </div>`
        )
        .join("")}
    </div>
    <div class="field-label" style="margin-top:12px;">
      บันทึกแล้วสำหรับ: ${result.business_type_code} / อัตรา ${result.rate_code}
      ${result.has_solar ? " · ☀️ ติด Solar" : ""} (เฉลี่ยจาก ${result.sample_size} ไฟล์)
    </div>
  `;
}

async function pollJob(jobId, activeBtn) {
  const res = await fetch(`/api/admin/import/${jobId}`);
  const data = await res.json();

  setStatusPill(data.status);
  jobLog.textContent = (data.logs || []).join("\n");
  jobLog.scrollTop = jobLog.scrollHeight;

  if (data.status === "running") {
    setTimeout(() => pollJob(jobId, activeBtn), 1000);
    return;
  }

  activeBtn.disabled = false;

  if (data.status === "success") {
    renderResult(data.result, data.customer_profile);
    // นำเข้าเสร็จอาจมีประวัติการนำเข้าแถวใหม่ (โหมดอัตโนมัติ) และประเภทธุรกิจ/โปรไฟล์ใหม่ —
    // ต้องโหลด import log ให้เสร็จก่อน (เติมตัวแปร importLogEntries) แล้วค่อยวาดการ์ดประเภทธุรกิจ
    // ไม่งั้นชื่อบริษัทในการ์ดจะยังว่างเพราะ fetch สองอันแข่งกัน (race condition)
    loadImportLogLocal().then(loadBusinessTypesTable);
  } else if (data.status === "pending_rate") {
    jobResult.innerHTML = `
      <div class="search-hint" style="min-height:auto;">
        ${data.error || "ไม่ทราบประเภทธุรกิจ/รหัสอัตราของบัญชีนี้"}<br>
        📋 ระบบบันทึกไฟล์นี้ไว้ในรายการ <a href="/pending-amr" target="_blank" rel="noopener">"รอทราบอัตรา"</a> แล้ว
        — ไม่ต้องอัปโหลดไฟล์ใหม่ กลับมากรอกประเภทธุรกิจ/รหัสอัตราทีหลังได้เมื่อทราบแล้ว
      </div>`;
  } else if (data.status === "error") {
    jobResult.innerHTML = `<div class="search-hint" style="min-height:auto;">${data.error || "เกิดข้อผิดพลาด"}</div>`;
  }
}

async function startImport() {
  formHint.textContent = "";

  const username = document.getElementById("f-username").value.trim();
  const password = document.getElementById("f-password").value;
  const accounts = document.getElementById("f-accounts").value.trim();
  const business_type_code = businessTypeSelect.value;
  const rate_code = document.getElementById("f-rate-code").value.trim();
  const contract_kva = document.getElementById("f-kva").value;
  const source_label = document.getElementById("f-source-label").value.trim();
  const has_solar = document.getElementById("f-has-solar").checked;
  const start_date = document.getElementById("f-start").value;
  const end_date = document.getElementById("f-end").value;

  if (!start_date || !end_date) {
    formHint.textContent = "กรุณาเลือกวันที่เริ่มต้นและสิ้นสุด";
    return;
  }

  // ระบุประเภทธุรกิจหรืออัตรามาอย่างใดอย่างหนึ่ง (โหมดกรอกเอง) ต้องกรอกให้ครบทั้งคู่ +
  // เลขบัญชี — ถ้าไม่ระบุทั้งคู่เลย ปล่อยให้ backend ใช้โหมดตรวจจับอัตโนมัติแทน
  if (business_type_code || rate_code) {
    if (!accounts || !business_type_code || !rate_code) {
      formHint.textContent = "โหมดกรอกเอง: กรุณากรอกเลขบัญชี, ประเภทธุรกิจ และรหัสอัตราให้ครบทั้งหมด";
      return;
    }
  }

  submitBtn.disabled = true;
  jobArea.style.display = "flex";
  jobLog.textContent = "";
  jobResult.innerHTML = "";
  setStatusPill("running");

  try {
    const res = await fetch("/api/admin/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username,
        password,
        accounts,
        business_type_code,
        rate_code,
        contract_kva: contract_kva ? Number(contract_kva) : null,
        source_label,
        has_solar,
        start_date,
        end_date,
      }),
    });

    // ล้างช่อง password ออกจากหน้าจอทันทีหลังส่งไปแล้ว (ไม่ให้ค้างอยู่บนจอโดยไม่จำเป็น)
    document.getElementById("f-password").value = "";

    const data = await res.json();

    if (!res.ok) {
      submitBtn.disabled = false;
      setStatusPill("error");
      jobLog.textContent = data.message || "เกิดข้อผิดพลาด";
      return;
    }

    pollJob(data.job_id, submitBtn);
  } catch (err) {
    submitBtn.disabled = false;
    formHint.textContent = "เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ";
    console.error(err);
  }
}

submitBtn.addEventListener("click", startImport);

// ── โหมดแนบไฟล์ที่มีอยู่แล้ว (ไม่ต้อง login เว็บ PEA เลย) ──

async function startFileImport() {
  formHint.textContent = "";

  const filesInput = document.getElementById("f-file-files");
  const files = filesInput.files;
  const business_type_code = fileBusinessTypeSelect.value;
  const rate_code = document.getElementById("f-file-rate-code").value.trim();
  const contract_kva = document.getElementById("f-file-kva").value;
  const source_label = document.getElementById("f-file-source-label").value.trim();
  const site_label = document.getElementById("f-file-site-label").value.trim();
  const has_solar = document.getElementById("f-file-has-solar").checked;

  if (!files || files.length === 0) {
    formHint.textContent = "กรุณาแนบไฟล์ AMR อย่างน้อย 1 ไฟล์";
    return;
  }
  // ไม่บังคับกรอกประเภทธุรกิจ/รหัสอัตราแล้ว — ปล่อยว่างได้ ระบบจะอ่านเลขบัญชีจากในไฟล์แล้วค้น
  // ในทะเบียนลูกค้าให้อัตโนมัติก่อน ถ้าหาไม่เจอจริงๆ job จะ error กลับมาบอกให้กรอกเอง

  const formData = new FormData();
  for (const file of files) formData.append("files", file);
  if (business_type_code) formData.append("business_type_code", business_type_code);
  if (rate_code) formData.append("rate_code", rate_code);
  if (contract_kva) formData.append("contract_kva", contract_kva);
  formData.append("source_label", source_label);
  formData.append("site_label", site_label);
  formData.append("has_solar", has_solar ? "true" : "false");

  submitFileBtn.disabled = true;
  jobArea.style.display = "flex";
  jobLog.textContent = "";
  jobResult.innerHTML = "";
  setStatusPill("running");

  try {
    const res = await fetch("/api/admin/import-file", { method: "POST", body: formData });
    const data = await res.json();

    if (!res.ok) {
      submitFileBtn.disabled = false;
      setStatusPill("error");
      jobLog.textContent = data.message || "เกิดข้อผิดพลาด";
      return;
    }

    pollJob(data.job_id, submitFileBtn);
  } catch (err) {
    submitFileBtn.disabled = false;
    formHint.textContent = "เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ";
    console.error(err);
  }
}

submitFileBtn.addEventListener("click", startFileImport);
loadBusinessTypes();
// ต้องโหลด import log ให้เสร็จก่อน (เติม importLogEntries) แล้วค่อยวาดการ์ดประเภทธุรกิจ ไม่งั้น
// ชื่อบริษัทในการ์ดจะว่างเพราะ fetch สองอันแข่งกัน (race condition)
loadImportLogLocal().then(loadBusinessTypesTable);

// ── ฐานข้อมูล DBD Open Data (ดึงมาเก็บในเครื่องเพื่อค้นชื่อบริษัทแบบออฟไลน์) ──

const dbdOpendataStatusPill = document.getElementById("dbd-opendata-status-pill");
const dbdOpendataFetchBtn = document.getElementById("dbd-opendata-fetch-btn");
const dbdOpendataJobArea = document.getElementById("dbd-opendata-job-area");
const dbdOpendataLog = document.getElementById("dbd-opendata-log");
const dbdOpendataResult = document.getElementById("dbd-opendata-result");

function setDbdOpendataStatusPill(state) {
  const map = {
    checking: { text: "กำลังตรวจสอบ...", bg: "#eef3fa", color: "#55647a" },
    available: { text: "✅ มีข้อมูลแล้วในเครื่อง", bg: "#e8f7ec", color: "#006300" },
    unavailable: { text: "ยังไม่มีข้อมูล", bg: "#fdecea", color: "#a01818" },
    running: { text: "⏳ กำลังดึงข้อมูล...", bg: "#eef3fa", color: "#184f95" },
  };
  const s = map[state] || map.checking;
  dbdOpendataStatusPill.textContent = s.text;
  dbdOpendataStatusPill.style.background = s.bg;
  dbdOpendataStatusPill.style.color = s.color;
}

async function loadDbdOpendataStatus() {
  try {
    const res = await fetch("/api/admin/dbd-opendata/status");
    const data = await res.json();
    setDbdOpendataStatusPill(data.available ? "available" : "unavailable");
  } catch (err) {
    console.error(err);
  }
}

async function pollDbdOpendataJob(jobId) {
  const res = await fetch(`/api/admin/dbd-opendata/fetch/${jobId}`);
  const data = await res.json();

  dbdOpendataLog.textContent = (data.logs || []).join("\n");
  dbdOpendataLog.scrollTop = dbdOpendataLog.scrollHeight;

  if (data.status === "running") {
    setTimeout(() => pollDbdOpendataJob(jobId), 1500);
    return;
  }

  dbdOpendataFetchBtn.disabled = false;

  if (data.status === "success") {
    const r = data.result || {};
    dbdOpendataResult.textContent =
      `เสร็จแล้ว — เก็บได้ ${(r.total_rows || 0).toLocaleString("th-TH")} รายการ ` +
      `จาก ${r.months_with_data || 0}/${r.months_tried || 0} เดือนที่มีข้อมูล`;
    setDbdOpendataStatusPill("available");
    loadDbdOpendataStatus();
  } else {
    dbdOpendataResult.textContent = data.error || "เกิดข้อผิดพลาด";
    loadDbdOpendataStatus();
  }
}

async function startDbdOpendataFetch() {
  dbdOpendataFetchBtn.disabled = true;
  dbdOpendataJobArea.style.display = "flex";
  dbdOpendataLog.textContent = "";
  dbdOpendataResult.textContent = "";
  setDbdOpendataStatusPill("running");

  try {
    const res = await fetch("/api/admin/dbd-opendata/fetch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const data = await res.json();

    if (!res.ok) {
      dbdOpendataFetchBtn.disabled = false;
      dbdOpendataResult.textContent = data.message || "เกิดข้อผิดพลาด";
      loadDbdOpendataStatus();
      return;
    }

    pollDbdOpendataJob(data.job_id);
  } catch (err) {
    dbdOpendataFetchBtn.disabled = false;
    dbdOpendataResult.textContent = "เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ";
    console.error(err);
  }
}

dbdOpendataFetchBtn.addEventListener("click", startDbdOpendataFetch);
loadDbdOpendataStatus();
