// หน้าเดียว: ค้นหา/เลือกประเภทธุรกิจ (TSIC) ของบริษัท จากชื่อหรือเลขทะเบียนนิติบุคคล ผ่าน DBD
// DataWarehouse (หรือแหล่งสำรอง: Wikipedia ตอน DBD DataWarehouse บล็อก) — ไม่มีผลพยากรณ์ตัวเลข
// kWh/kW ใดๆ อีกต่อไป (ตัดฟีเจอร์นั้นออกจากทั้งระบบแล้ว) เหลือแค่จับคู่ประเภทธุรกิจเท่านั้น
//
// ⚠️ ชื่อบริษัท/เลขทะเบียนที่พิมพ์ในช่องด้านบน "ถูกส่งไป server" ทันทีที่กดปุ่มค้นหา (แล้ว server
// ส่งต่อไปค้นหาที่เว็บ DBD จริง) เพราะไม่มีทางค้นหาบริษัทจากชื่อ/เลขทะเบียนได้โดยไม่ส่งไปที่แหล่ง
// ข้อมูลนั้น — มีคำเตือนนี้แสดงในหน้าเว็บชัดเจนแล้ว ปุ่มค้นหาไม่บังคับกด (เลือกประเภทธุรกิจเองได้เลย
// จากกล่องด้านล่างโดยไม่ต้องค้นหา)

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ค่าจริงเก็บใน hidden input ตัวนี้ (.value อ่าน/เขียนได้แบบเดิม) — ส่วน UI ที่มองเห็น/คลิกได้คือ
// section-combobox + biz-type-combobox ด้านล่าง (ดู setupBusinessTypeCombobox) แยกออกจาก native
// <select> เพราะ dropdown ของ native select เปิดขึ้นด้านบนเองเวลาพื้นที่ด้านล่างจอไม่พอ (ผู้ใช้
// แจ้งว่าเปิดขึ้นบนแล้วเห็นตัวเลือกไม่ครบ) ซึ่งเป็นพฤติกรรมเบราว์เซอร์ล้วนๆ บังคับทิศทางไม่ได้เลย
const businessTypeSelect = document.getElementById("f-business-type");

let BUSINESS_TYPE_GROUPS = new Map(); // section_code (หรือ "UNVERIFIED") -> [{code, bt}, ...]

function sectionGroupLabel(key, items) {
  if (key === "UNVERIFIED") return "ยังไม่ตรวจสอบ TSIC";
  const name = items[0] && items[0].bt ? items[0].bt.section_name_th : "";
  return `${key} · ${name}`;
}

// ใช้ /api/business-types-full (มี section_code/section_name_th) เพื่อจัดกลุ่มตัวเลือกตาม TSIC
// Section (A, B, C, ...) — แสดงทุกประเภทธุรกิจที่มีในระบบ (business_types.csv) ไม่กรองตาม "มี
// โปรไฟล์อ้างอิงจริงรองรับไหม" อีกต่อไป (ไม่มีแนวคิดนั้นแล้วหลังตัดฟีเจอร์พยากรณ์ตัวเลขออก)
async function loadBusinessTypes() {
  try {
    const res = await fetch("/api/business-types-full");
    const types = await res.json();

    const groups = new Map();
    for (const bt of types) {
      const key = bt.section_code || "UNVERIFIED";
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push({ code: bt.code, bt });
    }
    for (const items of groups.values()) {
      items.sort((a, b) => (a.bt ? a.bt.name_th : a.code).localeCompare(b.bt ? b.bt.name_th : b.code, "th"));
    }
    BUSINESS_TYPE_GROUPS = groups;

    setupBusinessTypeCombobox();
  } catch (err) {
    console.warn("โหลดประเภทธุรกิจไม่สำเร็จ", err);
  }
}

// ── Section-first 2-ขั้น combobox สำหรับเลือกประเภทธุรกิจ (เหมือนหน้า Admin) ──

function filterComboboxList(input, wrap) {
  const query = input.value.trim().toLowerCase();
  const items = wrap.querySelectorAll(".biz-type-dropdown-item");
  let anyVisible = false;
  items.forEach((item) => {
    const match = !query || item.textContent.toLowerCase().includes(query);
    item.style.display = match ? "" : "none";
    if (match) anyVisible = true;
  });
  const emptyMsg = wrap.querySelector(".biz-type-dropdown-empty");
  if (emptyMsg) emptyMsg.style.display = anyVisible ? "none" : "block";
}

// ชื่อบริษัทที่จับคู่ล่าสุดจากผล DBD (ไม่ใช่การพิมพ์เอง — อ่านมาจาก candidate.juristic_name
// ตอนค้นหาด้วยเลขทะเบียนสำเร็จเท่านั้น) เก็บไว้ใช้โชว์คู่กับ Boxplot ด้านล่างด้วยว่ากำลังดูของ
// ธุรกิจประเภทไหนที่จับคู่กับบริษัทไหน (เคลียร์ทิ้งทุกครั้งที่เปลี่ยนประเภทธุรกิจเองแบบไม่ผ่านการ
// ค้นหา กันโชว์ชื่อบริษัทเก่าค้างคู่กับประเภทธุรกิจใหม่ที่ไม่เกี่ยวกัน)
let matchedCompanyName = null;

// ตั้งค่าประเภทธุรกิจที่เลือก (ทั้ง hidden input และข้อความที่แสดงในกล่องค้นหาทั้ง 2 ขั้น) —
// companyName (ไม่บังคับ) ใส่เฉพาะตอนมาจากผลค้นหา DBD จริงเท่านั้น ไม่งั้นเว้นว่างไว้ (เคลียร์)
function setBusinessType(code, companyName) {
  businessTypeSelect.value = code || "";

  matchedCompanyName = companyName || null;
  const matchedNameEl = document.getElementById("matched-company-name");
  if (matchedNameEl) {
    matchedNameEl.textContent = matchedCompanyName ? `🏢 บริษัทที่จับคู่: ${matchedCompanyName}` : "";
    matchedNameEl.style.display = matchedCompanyName ? "" : "none";
  }
  const sectionInput = document.querySelector("#f-business-type-section .biz-type-search-input");
  const bizInput = document.querySelector("#f-business-type-biz .biz-type-search-input");
  const clearBtn = document.getElementById("f-business-type-clear");

  const bt = code ? [...BUSINESS_TYPE_GROUPS.values()].flat().find((t) => t.code === code) : null;
  if (bt) {
    const key = bt.bt && bt.bt.section_code ? bt.bt.section_code : "UNVERIFIED";
    sectionInput.value = sectionGroupLabel(key, [bt]);
    bizInput.disabled = false;
    bizInput.value = `${bt.bt ? bt.bt.name_th : bt.code} · ${bt.code}`;
    clearBtn.style.display = "";
  } else {
    sectionInput.value = "";
    bizInput.value = "";
    bizInput.disabled = true;
    bizInput.placeholder = "เลือก Section ก่อน...";
    clearBtn.style.display = "none";
  }

  // ปุ่ม "ดู Boxplot ธุรกิจนี้" โผล่ขึ้นมาเฉพาะตอนเลือกประเภทธุรกิจไว้แล้วเท่านั้น (ต้องรู้ว่า
  // จะขอ boxplot ของ TSIC ไหน) — ซ่อนกราฟ/สถานะเก่าทิ้งทุกครั้งที่เปลี่ยนประเภทธุรกิจ กันโชว์
  // ผลของธุรกิจก่อนหน้าค้างอยู่
  const boxplotBtnEl = document.getElementById("boxplot-btn");
  const boxplotImgEl = document.getElementById("boxplot-img");
  const boxplotStatusEl = document.getElementById("boxplot-status");
  boxplotBtnEl.style.display = code ? "" : "none";
  boxplotImgEl.style.display = "none";
  boxplotStatusEl.textContent = "";
}

let businessTypeComboboxReady = false;

function setupBusinessTypeCombobox() {
  const sectionWrap = document.getElementById("f-business-type-section");
  const sectionInput = sectionWrap.querySelector(".biz-type-search-input");
  const sectionDropdown = sectionWrap.querySelector(".biz-type-dropdown");
  const bizWrap = document.getElementById("f-business-type-biz");
  const bizInput = bizWrap.querySelector(".biz-type-search-input");
  const bizDropdown = bizWrap.querySelector(".biz-type-dropdown");
  const clearBtn = document.getElementById("f-business-type-clear");

  const sortedKeys = [...BUSINESS_TYPE_GROUPS.keys()].sort((a, b) => {
    if (a === "UNVERIFIED") return 1;
    if (b === "UNVERIFIED") return -1;
    return a.localeCompare(b);
  });

  sectionDropdown.innerHTML =
    sortedKeys
      .map((key) => {
        const items = BUSINESS_TYPE_GROUPS.get(key);
        return `<button type="button" class="biz-type-dropdown-item" data-section="${escapeHtml(key)}">${escapeHtml(sectionGroupLabel(key, items))} (${items.length})</button>`;
      })
      .join("") + `<div class="biz-type-dropdown-empty" style="display:none;">ไม่พบ Section ที่ตรงกับคำค้นหา</div>`;

  sectionDropdown.querySelectorAll(".biz-type-dropdown-item").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation(); // กัน biz-type-combobox ที่เพิ่งเปิดต่อโดนปิดทันทีจาก click-outside ด้านล่าง
      const key = btn.dataset.section;
      const items = BUSINESS_TYPE_GROUPS.get(key) || [];
      sectionInput.value = sectionGroupLabel(key, items);
      sectionWrap.classList.remove("open");

      businessTypeSelect.value = "";
      clearBtn.style.display = "";
      bizInput.disabled = false;
      bizInput.value = "";
      bizInput.placeholder = `🔍 ค้นหาประเภทธุรกิจ (${items.length} รายการ)...`;
      bizDropdown.innerHTML =
        items.map(({ code, bt }) => `<button type="button" class="biz-type-dropdown-item" data-code="${escapeHtml(code)}">${escapeHtml(bt ? bt.name_th : code)} · ${escapeHtml(code)}</button>`).join("") +
        `<div class="biz-type-dropdown-empty" style="display:none;">ไม่พบประเภทธุรกิจที่ตรงกับคำค้นหา</div>`;
      bizDropdown.querySelectorAll(".biz-type-dropdown-item").forEach((itemBtn) => {
        itemBtn.addEventListener("click", () => {
          setBusinessType(itemBtn.dataset.code);
          bizWrap.classList.remove("open");
        });
      });
      bizWrap.classList.add("open");
      bizInput.focus();
    });
  });

  clearBtn.addEventListener("click", () => {
    setBusinessType("");
  });

  if (businessTypeComboboxReady) return; // event listener ต่อไปนี้ผูกครั้งเดียวพอ ไม่งั้นซ้ำซ้อนทุกครั้งที่โหลดข้อมูลใหม่
  businessTypeComboboxReady = true;

  sectionInput.addEventListener("focus", () => sectionWrap.classList.add("open"));
  sectionInput.addEventListener("input", () => filterComboboxList(sectionInput, sectionWrap));
  bizInput.addEventListener("focus", () => {
    if (!bizInput.disabled) bizWrap.classList.add("open");
  });
  bizInput.addEventListener("input", () => filterComboboxList(bizInput, bizWrap));

  document.addEventListener("click", (e) => {
    document.querySelectorAll(".section-combobox.open, .biz-type-combobox.open").forEach((box) => {
      if (!box.contains(e.target)) box.classList.remove("open");
    });
  });
}

// ── ค้นหาประเภทธุรกิจอัตโนมัติจากชื่อบริษัท (ผ่าน DBD DataWarehouse) ──

const lookupBtn = document.getElementById("lookup-business-type-btn");
const lookupStatus = document.getElementById("business-type-lookup-status");
const registrationNoInput = document.getElementById("f-registration-no");

// สร้างข้อความแจ้งผล + ตั้งค่าประเภทธุรกิจให้อัตโนมัติ (side effect)
function buildBusinessTypeSuggestionMessage(candidate) {
  const companyName = escapeHtml(candidate.juristic_name || "");

  if (!candidate.suggested_business_type_code) {
    return `<div class="lookup-status-text">พบบริษัท "${companyName}" — TSIC ${candidate.tsic_code} - ${candidate.tsic_name_th} แต่ยังไม่มีในระบบ กรุณาเลือกประเภทธุรกิจที่ใกล้เคียงเองด้านบน หรือเพิ่มประเภทธุรกิจใหม่</div>`;
  }
  setBusinessType(candidate.suggested_business_type_code, candidate.juristic_name);

  if (candidate.suggested_is_approximate) {
    return `<div class="lookup-status-text">⚠️ พบบริษัท "${companyName}" — ตรวจพบ TSIC ${candidate.tsic_code} - ${candidate.tsic_name_th} — ไม่มีธุรกิจนี้ตรงๆ ในระบบ จึงตั้งประเภทธุรกิจเป็น "${candidate.suggested_business_type_name}" แทนแบบประมาณการ (ตรวจสอบ/เปลี่ยนเองได้ด้านบน)<br><span style="color:#8996ab;">${candidate.suggested_explanation}</span></div>`;
  }
  return `<div class="lookup-status-text">✅ พบบริษัท "${companyName}" — ตรวจพบ TSIC ${candidate.tsic_code} - ${candidate.tsic_name_th} → ตั้งประเภทธุรกิจเป็น "${candidate.suggested_business_type_name}" ให้อัตโนมัติแล้ว (ตรวจสอบ/เปลี่ยนเองได้ด้านบน)</div>`;
}

// สร้างข้อความแจ้งผลของการเดาจากคำสำคัญใน Wikipedia (ดู keyword_classify.py ฝั่ง backend) — ต่าง
// จาก buildBusinessTypeSuggestionMessage ตรงที่นี่ "ไม่ใช่รหัส TSIC จริง" แค่เจอคำสำคัญตรงตัวใน
// ข้อความอิสระ จึงต้องบอกให้ชัดเจนกว่าว่าเป็นการเดา ไม่ใช่ข้อมูลทางการ ป้องกันผู้ใช้เข้าใจผิดว่า
// แม่นยำเท่าผลจาก DBD
function buildKeywordGuessMessage(wikipediaResult) {
  if (!wikipediaResult.suggested_business_type_code) {
    return "";
  }
  setBusinessType(wikipediaResult.suggested_business_type_code);
  const approxNote = wikipediaResult.suggested_is_approximate
    ? `<br><span style="color:#8996ab;">${wikipediaResult.suggested_explanation}</span>`
    : "";
  return `<div class="lookup-status-text" style="margin-top:4px;">🔤 เดาประเภทธุรกิจจากคำว่า "${wikipediaResult.guessed_keyword}" ที่พบในข้อความ Wikipedia (ไม่ใช่รหัส TSIC ทางการ เดาแบบจับคำสำคัญตรงตัวเท่านั้น) → ตั้งประเภทธุรกิจเป็น "${wikipediaResult.suggested_business_type_name}" ให้ชั่วคราว — ตรวจสอบ/เปลี่ยนเองได้ด้านบนเสมอ${approxNote}</div>`;
}

function applyBusinessTypeSuggestion(candidate) {
  lookupStatus.innerHTML = buildBusinessTypeSuggestionMessage(candidate);
}

function renderLookupCandidates(candidates) {
  lookupStatus.innerHTML = `
    <div class="lookup-status-text" style="margin-bottom:8px;">พบหลายบริษัทที่ตรงกับคำค้นหา — เลือกบริษัทที่ใช่:</div>
    <div style="display:flex;flex-direction:column;gap:8px;">
      ${candidates
        .map(
          (c, i) => `
        <div class="lookup-candidate">
          <div>
            <div class="lookup-candidate-name">${c.juristic_name} <span style="font-weight:400;color:#8996ab;">(${c.juristic_type})</span></div>
            <div class="lookup-candidate-meta">TSIC ${c.tsic_code} - ${c.tsic_name_th} · ${c.status}</div>
          </div>
          <button type="button" class="lookup-pick-btn" data-idx="${i}">เลือกอันนี้</button>
        </div>`
        )
        .join("")}
    </div>`;

  lookupStatus.querySelectorAll(".lookup-pick-btn").forEach((btn) => {
    btn.addEventListener("click", () => applyBusinessTypeSuggestion(candidates[Number(btn.dataset.idx)]));
  });
}

// สร้าง <details> แสดง log การค้นหาจริง (คำค้นหาที่ลองทั้งหมด/จำนวนผลลัพธ์แต่ละรอบ) — เปิด
// (open ตั้งแต่แรก) เฉพาะตอน "ไม่พบ/error" เพราะเป็นตอนที่มีประโยชน์ที่สุด (ช่วยดูว่าระบบลอง
// ค้นหาด้วยคำว่าอะไรบ้างก่อนจะสรุปว่าไม่เจอ แทนที่จะรู้แค่ผลลัพธ์สุดท้ายเฉยๆ)
function renderSearchLogDetails(logs, openByDefault) {
  if (!logs || !logs.length) return "";
  return `
    <details style="margin-top:8px;" ${openByDefault ? "open" : ""}>
      <summary style="cursor:pointer;font-size:12px;color:#8996ab;">ดู log การค้นหาจริง (${logs.length} บรรทัด)</summary>
      <div style="margin-top:6px;background:#0f1b2d;color:#cde2fb;font-family:'Consolas','Courier New',monospace;font-size:11.5px;line-height:1.6;border-radius:8px;padding:10px 12px;max-height:160px;overflow-y:auto;white-space:pre-wrap;">${logs.map((l) => l.replace(/</g, "&lt;")).join("\n")}</div>
    </details>`;
}

async function pollBusinessTypeLookupJob(jobId) {
  const res = await fetch(`/api/business-type-lookup/${jobId}`);
  const data = await res.json();

  if (data.status === "running") {
    setTimeout(() => pollBusinessTypeLookupJob(jobId), 800);
    return;
  }

  lookupBtn.disabled = false;

  if (data.status === "error") {
    lookupStatus.innerHTML = `<div class="lookup-status-text" style="color:#d03b3b;">ค้นหาไม่สำเร็จ: ${data.error || "เกิดข้อผิดพลาด"} (ต้องรันเว็บนี้ในเครื่องที่มี Google Chrome ติดตั้งอยู่)</div>${renderSearchLogDetails(data.logs, false)}`;
    return;
  }

  const { candidates, exact_match_index, blocked, blocked_message, wikipedia_result } = data.result;

  if (blocked) {
    let html = `<div class="lookup-status-text" style="color:#a5670b;">🚫 เว็บ DBD DataWarehouse บล็อกการเข้าถึงอัตโนมัติ (ไม่ใช่ว่าไม่พบบริษัทนี้จริงๆ) — ${blocked_message || ""}</div>`;

    // Wikipedia (ฟรี ไม่มีค่าใช้จ่าย) — ช่วยเฉพาะบริษัทใหญ่/มีชื่อเสียงที่มีหน้า Wikipedia เท่านั้น —
    // เป็นข้อความอิสระประกอบการตัดสินใจเท่านั้น ไม่ใช่รหัส TSIC จึงเลือกประเภทธุรกิจให้อัตโนมัติไม่ได้
    let rankedCandidatesButtonsHtml = "";
    if (wikipedia_result) {
      // เนื้อหามาจาก Wikipedia (ใครก็แก้ไขได้) — escape ก่อนใส่ลง innerHTML เหมือน log details
      const wpTitle = wikipedia_result.title.replace(/</g, "&lt;");
      const wpSummary = wikipedia_result.summary.replace(/</g, "&lt;");
      html += `<div class="lookup-status-text" style="margin-top:8px;">📖 พบข้อมูลจาก <a href="${wikipedia_result.url}" target="_blank" rel="noopener">Wikipedia: ${wpTitle}</a> (ใช้ประกอบการตัดสินใจเท่านั้น ไม่ใช่แหล่งข้อมูลทางการ):</div>`;
      html += `<div class="lookup-status-text" style="margin-top:4px;color:#8996ab;">${wpSummary}</div>`;

      if (wikipedia_result.suggested_business_type_code) {
        // มั่นใจพอ (ตรง TSIC division เป๊ะ) — auto-apply ไปเลยเหมือนเดิม
        html += buildKeywordGuessMessage(wikipedia_result);
      } else if (wikipedia_result.ranked_candidates && wikipedia_result.ranked_candidates.length) {
        // แค่เดาแบบประมาณการ (ไม่มั่นใจพอ) — ไม่ auto-apply ให้เงียบๆ (เคยเจอเดาผิดแบบไม่รู้ตัว เช่น
        // ค้าปลีกไปจับกับการผลิตกระดาษ) โชว์เป็นรายการอันดับ 1/2/3 ให้เลือกเองแทน
        html += `<div class="lookup-status-text" style="margin-top:4px;">🔤 เดาจากคำว่า "${wikipedia_result.guessed_keyword}" ได้ไม่มั่นใจพอที่จะเลือกให้เอง — นี่คือธุรกิจที่ใกล้เคียงที่สุด ${wikipedia_result.ranked_candidates.length} อันดับ เลือกอันที่ใช่เอง:</div>`;
        rankedCandidatesButtonsHtml = `
            <div style="display:flex;flex-direction:column;gap:8px;margin-top:6px;">
              ${wikipedia_result.ranked_candidates
                .map(
                  (c, i) => `
                <div class="lookup-candidate">
                  <div>
                    <div class="lookup-candidate-name">อันดับ ${i + 1}: ${c.business_type_name}</div>
                    <div class="lookup-candidate-meta">${c.explanation}</div>
                  </div>
                  <button type="button" class="lookup-pick-btn" data-rankidx="${i}">เลือกอันนี้</button>
                </div>`
                )
                .join("")}
            </div>`;
        html += rankedCandidatesButtonsHtml;
      }
    } else {
      html += `<div class="lookup-status-text" style="margin-top:8px;color:#8996ab;">ลองหาข้อมูลจาก Wikipedia แทนก็ไม่พบ — กรุณาเลือกประเภทธุรกิจเองด้านบน</div>`;
    }

    // ข้อความรายละเอียดทั้งหมด (เหตุผลที่โดนบล็อก, Wikipedia) ยาวและรกหน้าจอถ้าโชว์เต็มทุกครั้ง —
    // จึงพับเก็บไว้ใน <details> แทน เหลือแค่ "สรุปผลลัพธ์" บรรทัดเดียวด้านบนเสมอ — กางออกอัตโนมัติ
    // เฉพาะตอนที่ยังต้องให้ผู้ใช้เลือกอะไรบางอย่างเอง (มีปุ่ม "เลือกอันนี้" ให้กด) เท่านั้น
    const hasPendingChoice = Boolean(rankedCandidatesButtonsHtml);
    const autoApplied = wikipedia_result && wikipedia_result.suggested_business_type_code;

    let headline;
    if (hasPendingChoice) {
      headline = `<div class="lookup-status-text">⚠️ เว็บ DBD DataWarehouse บล็อกการเข้าถึงอัตโนมัติ — เลือกประเภทธุรกิจที่ใกล้เคียงที่สุดจากตัวเลือกด้านล่าง</div>`;
    } else if (autoApplied) {
      headline = `<div class="lookup-status-text" style="color:#0ca30c;">✅ เว็บ DBD DataWarehouse บล็อก แต่หาข้อมูลจาก Wikipedia ได้ — ตั้งประเภทธุรกิจให้อัตโนมัติแล้วด้านบน</div>`;
    } else {
      headline = `<div class="lookup-status-text">🚫 เว็บ DBD DataWarehouse บล็อก และหาข้อมูลจากแหล่งอื่นไม่สำเร็จ — กรุณาเลือกประเภทธุรกิจเองด้านบน</div>`;
    }

    lookupStatus.innerHTML =
      headline +
      `<details ${hasPendingChoice ? "open" : ""} style="margin-top:6px;">
        <summary style="cursor:pointer;font-size:12.5px;color:#8996ab;">ดูรายละเอียดการค้นหา (DBD DataWarehouse / Wikipedia)</summary>
        <div style="margin-top:8px;">${html}</div>
      </details>` +
      renderSearchLogDetails(data.logs, false);
    if (rankedCandidatesButtonsHtml) {
      lookupStatus.querySelectorAll(".lookup-pick-btn[data-rankidx]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const candidate = wikipedia_result.ranked_candidates[Number(btn.dataset.rankidx)];
          setBusinessType(candidate.business_type_code);
          const msg = document.createElement("div");
          msg.className = "lookup-status-text";
          msg.style.marginTop = "8px";
          msg.textContent = `✅ ตั้งประเภทธุรกิจเป็น "${candidate.business_type_name}" แล้ว`;
          lookupStatus.appendChild(msg);
        });
      });
    }
    return;
  }

  if (!candidates.length) {
    lookupStatus.innerHTML = `<div class="lookup-status-text">ไม่พบบริษัทนี้ใน DBD DataWarehouse — กรุณาเลือกประเภทธุรกิจเองด้านบน</div>${renderSearchLogDetails(data.logs, false)}`;
  } else if (exact_match_index !== null && exact_match_index !== undefined) {
    applyBusinessTypeSuggestion(candidates[exact_match_index]);
  } else if (candidates.length === 1) {
    applyBusinessTypeSuggestion(candidates[0]);
  } else {
    renderLookupCandidates(candidates);
  }
}

async function runBusinessTypeLookup() {
  const registrationNo = registrationNoInput.value.trim();
  if (!registrationNo) {
    lookupStatus.innerHTML = `<div class="lookup-status-text" style="color:#d03b3b;">กรุณากรอกเลขนิติบุคคล 13 หลักก่อน</div>`;
    return;
  }

  lookupBtn.disabled = true;
  lookupStatus.innerHTML = `<div class="lookup-status-text">⏳ กำลังค้นหา... (เปิดเบราว์เซอร์จริง อาจใช้เวลาสักครู่)</div>`;

  try {
    const res = await fetch("/api/business-type-lookup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // ไม่มีช่องกรอกชื่อบริษัทแยกแล้ว — ใช้เลขนิติบุคคลเป็นทั้งคำค้นหาและ company_name (ฝั่ง
      // backend ยังต้องการ company_name แบบไม่ว่างเปล่าเสมอ ดู _run_business_type_lookup_job แต่
      // ตอนมี registration_no จะใช้เลขทะเบียนค้นหาจริงแทนอยู่ดี ไม่ได้เอา company_name ไปค้นหา)
      body: JSON.stringify({ company_name: registrationNo, registration_no: registrationNo }),
    });
    const data = await res.json();

    if (!res.ok) {
      lookupBtn.disabled = false;
      lookupStatus.innerHTML = `<div class="lookup-status-text" style="color:#d03b3b;">${data.message || "เกิดข้อผิดพลาด"}</div>`;
      return;
    }

    pollBusinessTypeLookupJob(data.job_id);
  } catch (err) {
    lookupBtn.disabled = false;
    lookupStatus.innerHTML = `<div class="lookup-status-text" style="color:#d03b3b;">เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ</div>`;
    console.error(err);
  }
}

lookupBtn.addEventListener("click", runBusinessTypeLookup);

loadBusinessTypes();

// ── ดู Boxplot การใช้ไฟจริงของประเภทธุรกิจที่เลือกไว้ (ข้อมูล AMR จริงที่แอดมินอัปโหลดสะสมไว้ —
// ดู src/amr_mapping/amr_boxplot.py) ต่างจากพยากรณ์เส้นโค้งด้านบนตรงที่นี่คือข้อมูลวัดจริง ไม่ใช่
// เส้นโค้งสมมติจากตัวเลขบิล — ต้องเลือกประเภทธุรกิจไว้ก่อน (ปุ่มถึงจะโผล่ขึ้นมา) และต้องมีคนเคย
// อัปโหลด AMR จริงของธุรกิจประเภทนี้ไว้แล้วจากหน้า Admin ไม่งั้นจะได้ 404 กลับมา
const boxplotBtn = document.getElementById("boxplot-btn");
const boxplotStatus = document.getElementById("boxplot-status");
const boxplotImg = document.getElementById("boxplot-img");
let boxplotImgObjectUrl = null;

async function runBoxplot() {
  const code = businessTypeSelect.value;
  if (!code) return;

  boxplotBtn.disabled = true;
  boxplotStatus.textContent = "⏳ กำลังโหลด...";
  boxplotImg.style.display = "none";

  try {
    const res = await fetch(`/api/forecast-boxplot?business_type_code=${encodeURIComponent(code)}`);
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      boxplotStatus.innerHTML = `<span style="color:#8996ab;">${escapeHtml(data.message || "ไม่พบข้อมูล")}</span>`;
      return;
    }

    const blob = await res.blob();
    if (boxplotImgObjectUrl) URL.revokeObjectURL(boxplotImgObjectUrl);
    boxplotImgObjectUrl = URL.createObjectURL(blob);
    boxplotImg.src = boxplotImgObjectUrl;
    boxplotImg.style.display = "block";
    // ⚠️ ข้อมูล Boxplot นี้เป็นข้อมูล AMR จริงของ "บริษัทอื่นในระบบ" ที่มีประเภทธุรกิจเดียวกัน
    // (TSIC เดียวกัน) ที่แอดมินเคยอัปโหลด/ดึงไว้ ไม่ใช่ข้อมูลของบริษัทที่กำลังค้นหา/จับคู่ไว้ด้านบน
    // เลย (บริษัทนั้นแทบทั้งหมดคือกลุ่มที่ "ยังไม่มี AMR ของตัวเอง" อยู่แล้ว ถึงต้องมาดูอันนี้แทน) —
    // ห้ามโชว์ matchedCompanyName ตรงนี้เด็ดขาด เพราะจะเข้าใจผิดว่าข้อมูลนี้เป็นของบริษัทนั้นเอง
    // (เคยพลาดมาแล้ว) กราฟนี้ (Boxplot รวม) ไม่แสดงชื่อ/เลขบัญชีของบริษัทที่ให้ข้อมูลจริงเลย — ระบบ
    // เก็บไว้แค่ฝั่ง Admin เท่านั้น (ผู้ใช้ยืนยันอยากให้แอดมินแยกดูรายบัญชีได้ ดู amr_boxplot.py)
    // หน้านี้ (สาธารณะ ไม่ใช่ Admin) จึงบอกได้แค่ว่า "เป็นข้อมูลของบริษัทอื่น" เท่านั้น
    boxplotStatus.innerHTML = `<span style="color:#8996ab;">ℹ️ นี่คือข้อมูล AMR จริงของ<strong>บริษัทอื่น</strong>ในระบบที่มีประเภทธุรกิจเดียวกัน (TSIC ${escapeHtml(code)}) ไม่ใช่ข้อมูลของบริษัทที่ค้นหาไว้ด้านบนเอง (กราฟนี้ไม่แสดงชื่อ/เลขบัญชีของบริษัทที่ให้ข้อมูลเลย)</span>`;
  } catch (err) {
    boxplotStatus.innerHTML = `<span style="color:#d03b3b;">เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ</span>`;
    console.error(err);
  } finally {
    boxplotBtn.disabled = false;
  }
}

boxplotBtn.addEventListener("click", runBoxplot);
