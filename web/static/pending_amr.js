// หน้า "รอทราบอัตรา" — แสดงรายการ AMR ที่นำเข้าไม่สำเร็จเพราะไม่ทราบประเภทธุรกิจ/รหัสอัตรา
// (บันทึกไว้ใน pending_amr_local.csv โดย web/app.py ตอนโหมดแนบไฟล์เจอ error แบบนี้) ให้กรอก
// ประเภทธุรกิจ/รหัสอัตราย้อนหลังได้ทีหลังเมื่อทราบแล้ว โดยไม่ต้องอัปโหลดไฟล์ใหม่ (ไฟล์เดิมยังอยู่
// ที่เครื่องเสิร์ฟเวอร์อยู่แล้ว)

const pendingListEl = document.getElementById("pending-list");

// รายการยาวขึ้นเรื่อยๆ ตามจำนวนประเภทธุรกิจที่เพิ่มเข้าระบบ — เรียงตามชื่อ (ไม่ใช่ตามลำดับที่เพิ่ม
// เข้าไฟล์) ให้หาง่ายขึ้นตอนเลื่อนดูทั้งรายการก่อนพิมพ์ค้นหา
let businessTypes = [];

async function loadBusinessTypeOptions() {
  try {
    const res = await fetch("/api/business-types");
    businessTypes = (await res.json()).sort((a, b) => a.name_th.localeCompare(b.name_th, "th"));
  } catch (err) {
    console.error("โหลดประเภทธุรกิจไม่สำเร็จ", err);
  }
}

function businessTypeDropdownHtml() {
  return `
    <div class="biz-type-combobox">
      <input type="hidden" class="p-business-type">
      <input type="text" class="biz-type-search-input" placeholder="🔍 ค้นหาประเภทธุรกิจ (${businessTypes.length} รายการ)..." autocomplete="off">
      <div class="biz-type-dropdown">
        ${businessTypes.map((t) => `<button type="button" class="biz-type-dropdown-item" data-code="${t.code}">${t.name_th} (${t.code})</button>`).join("")}
        <div class="biz-type-dropdown-empty" style="display:none;">ไม่พบประเภทธุรกิจที่ตรงกับคำค้นหา</div>
      </div>
    </div>`;
}

// กรองรายการใน dropdown ตามคำที่พิมพ์ — จับคู่แบบ "มีคำนี้อยู่ตรงไหนก็ได้" ไม่สนตัวพิมพ์เล็ก-ใหญ่
// (เหมือน filterComboboxDropdown ในหน้า Admin แต่ทำแยกเองเพราะหน้านี้ไม่ได้โหลด admin.js ร่วมด้วย)
function filterBizTypeDropdown(input) {
  const wrap = input.closest(".biz-type-combobox");
  const query = input.value.trim().toLowerCase();
  const items = wrap.querySelectorAll(".biz-type-dropdown-item");
  let anyVisible = false;
  items.forEach((item) => {
    const match = !query || item.textContent.toLowerCase().includes(query);
    item.style.display = match ? "" : "none";
    if (match) anyVisible = true;
  });
  wrap.querySelector(".biz-type-dropdown-empty").style.display = anyVisible ? "none" : "block";
}

// ปิด dropdown ที่เปิดค้างไว้เมื่อคลิกข้างนอกกล่องค้นหา (ผูกครั้งเดียว ใช้ event delegation เพราะ
// การ์ดแต่ละใบถูกสร้าง/ลบทิ้งไปเรื่อยๆ ตามรายการที่ resolve/delete)
document.addEventListener("click", (e) => {
  document.querySelectorAll(".biz-type-combobox.open").forEach((box) => {
    if (!box.contains(e.target)) box.classList.remove("open");
  });
});

function formatCreatedAt(iso) {
  try {
    return new Date(iso).toLocaleString("th-TH", { dateStyle: "medium", timeStyle: "short" });
  } catch (err) {
    return iso || "";
  }
}

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function renderPendingCard(entry) {
  const fileCount = (entry.file_paths || "").split("|").filter(Boolean).length;
  const name = entry.company_name ? escapeHtml(entry.company_name) : "(ไม่ทราบชื่อผู้ใช้ไฟ)";
  const sourceLabel = entry.source_label ? ` · ${escapeHtml(entry.source_label)}` : "";

  const wrap = document.createElement("div");
  wrap.className = "pending-card";
  wrap.dataset.pendingId = entry.pending_id;
  wrap.innerHTML = `
    <div class="pending-head">
      <div>
        <div class="pending-name">${name}</div>
        <div class="pending-sub">
          เลขบัญชี ${escapeHtml(entry.account_no) || "-"}
          ${entry.meter_no ? ` · มิเตอร์ ${escapeHtml(entry.meter_no)}` : ""}
          · ${fileCount} ไฟล์ · บันทึกเมื่อ ${formatCreatedAt(entry.created_at)}${sourceLabel}
        </div>
      </div>
    </div>
    <div class="pending-form-grid">
      <div class="form-field">
        <label>ประเภทธุรกิจ</label>
        ${businessTypeDropdownHtml()}
      </div>
      <div class="form-field">
        <label>รหัสอัตรา</label>
        <input class="p-rate-code" type="text" placeholder="เช่น 50">
        <label style="display:flex;align-items:center;gap:6px;font-size:12px;font-weight:500;color:#55647a;margin-top:2px;">
          <input type="checkbox" class="p-rate-unknown"> ไม่ทราบรหัสอัตรา
        </label>
      </div>
      <div class="form-field">
        <label>KVA ตามสัญญา</label>
        <input class="p-kva" type="number" min="0" step="any" value="${entry.contract_kva || ""}" placeholder="ไม่บังคับ">
      </div>
      <div class="form-field">
        <label>&nbsp;</label>
        <label style="display:flex;align-items:center;gap:6px;height:40px;font-size:13px;font-weight:500;color:#0f1b2d;">
          <input type="checkbox" class="p-has-solar" ${entry.has_solar === "true" ? "checked" : ""}> ติด Solar
        </label>
      </div>
      <div class="form-field" style="grid-column: 1 / -1;">
        <label>ป้ายกำกับไซต์ (ไม่บังคับ — ใช้แยกกรณีบริษัทเดียวกันมีหลายมิเตอร์ เช่น YMLC4)</label>
        <input class="p-site-label" type="text" placeholder="เช่น YMLC4">
      </div>
    </div>
    <div class="pending-hint"></div>
    <div class="pending-actions">
      <button class="btn-outline-danger p-delete-btn">ลบรายการนี้</button>
      <button class="btn-primary p-resolve-btn">ยืนยันนำเข้า</button>
    </div>
  `;

  const hintEl = wrap.querySelector(".pending-hint");
  const resolveBtn = wrap.querySelector(".p-resolve-btn");
  const deleteBtn = wrap.querySelector(".p-delete-btn");
  const rateCodeInput = wrap.querySelector(".p-rate-code");
  const rateUnknownCheckbox = wrap.querySelector(".p-rate-unknown");

  const bizCombobox = wrap.querySelector(".biz-type-combobox");
  const bizSearchInput = wrap.querySelector(".biz-type-search-input");
  const bizHiddenInput = wrap.querySelector(".p-business-type");
  bizSearchInput.addEventListener("focus", () => bizCombobox.classList.add("open"));
  bizSearchInput.addEventListener("input", () => filterBizTypeDropdown(bizSearchInput));
  bizCombobox.querySelectorAll(".biz-type-dropdown-item").forEach((btn) => {
    btn.addEventListener("click", () => {
      bizHiddenInput.value = btn.dataset.code;
      bizSearchInput.value = btn.textContent;
      bizCombobox.classList.remove("open");
    });
  });

  // ติ๊ก "ไม่ทราบรหัสอัตรา" แล้ว ไม่ต้องกรอกช่องรหัสอัตราอีก (ปิดไว้กันสับสนว่าต้องกรอกไหม) —
  // จะบันทึกด้วยรหัสอัตรา sentinel พิเศษแทน ยังเอาไปใช้จับคู่ระดับ "ประเภทธุรกิจ" ได้อยู่
  // (ดู UNKNOWN_RATE_CODE ใน web/app.py) แค่ไม่มีวันตรงเป๊ะ (EXACT) ให้ใครได้อีก
  rateUnknownCheckbox.addEventListener("change", () => {
    rateCodeInput.disabled = rateUnknownCheckbox.checked;
    if (rateUnknownCheckbox.checked) rateCodeInput.value = "";
  });

  resolveBtn.addEventListener("click", async () => {
    hintEl.textContent = "";
    const business_type_code = wrap.querySelector(".p-business-type").value;
    const rate_code = rateCodeInput.value.trim();
    const rate_code_unknown = rateUnknownCheckbox.checked;
    const kvaRaw = wrap.querySelector(".p-kva").value;
    const has_solar = wrap.querySelector(".p-has-solar").checked;
    const site_label = wrap.querySelector(".p-site-label").value.trim();

    if (!business_type_code || (!rate_code && !rate_code_unknown)) {
      hintEl.textContent = 'กรุณาเลือกประเภทธุรกิจและกรอกรหัสอัตราให้ครบ (หรือติ๊ก "ไม่ทราบรหัสอัตรา")';
      return;
    }

    resolveBtn.disabled = true;
    try {
      const res = await fetch(`/api/admin/pending-amr/${entry.pending_id}/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          business_type_code,
          rate_code,
          rate_code_unknown,
          contract_kva: kvaRaw ? Number(kvaRaw) : null,
          has_solar,
          site_label,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        hintEl.textContent = data.message || "นำเข้าไม่สำเร็จ";
        resolveBtn.disabled = false;
        return;
      }
      const r = data.result;
      const rateLabel = r.rate_code === "UNKNOWN" ? "ไม่ทราบ (ใช้ได้แค่ระดับประเภทธุรกิจ)" : r.rate_code;
      wrap.innerHTML = `
        <div class="pending-name">✅ นำเข้าสำเร็จ: ${name}</div>
        <div class="pending-sub">
          บันทึกแล้วสำหรับ ${r.business_type_code} / อัตรา ${rateLabel}
          ${r.has_solar ? " · ☀️ ติด Solar" : ""} (เฉลี่ยจาก ${r.sample_size} ไฟล์)
        </div>`;
      setTimeout(() => wrap.remove(), 1600);
    } catch (err) {
      hintEl.textContent = "เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ";
      resolveBtn.disabled = false;
      console.error(err);
    }
  });

  deleteBtn.addEventListener("click", async () => {
    if (!confirm(`ลบรายการ "${entry.company_name || entry.account_no}" ออกจากรายการรอทราบอัตราหรือไม่? (ไฟล์ AMR ที่แนบไว้จะไม่ถูกลบ)`)) {
      return;
    }
    deleteBtn.disabled = true;
    try {
      const res = await fetch(`/api/admin/pending-amr/${entry.pending_id}`, { method: "DELETE" });
      if (!res.ok) {
        const data = await res.json();
        hintEl.textContent = data.message || "ลบไม่สำเร็จ";
        deleteBtn.disabled = false;
        return;
      }
      wrap.remove();
      if (!pendingListEl.children.length) renderEmptyState();
    } catch (err) {
      hintEl.textContent = "เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ";
      deleteBtn.disabled = false;
      console.error(err);
    }
  });

  return wrap;
}

function renderEmptyState() {
  pendingListEl.innerHTML = `<div class="pending-empty">🎉 ไม่มีรายการรอทราบอัตราตอนนี้</div>`;
}

async function loadPendingList() {
  pendingListEl.innerHTML = `<div class="pending-empty">กำลังโหลด...</div>`;
  try {
    const res = await fetch("/api/admin/pending-amr");
    const data = await res.json();
    const entries = data.entries || [];
    if (!entries.length) {
      renderEmptyState();
      return;
    }
    pendingListEl.innerHTML = "";
    entries.forEach((entry) => pendingListEl.appendChild(renderPendingCard(entry)));
  } catch (err) {
    pendingListEl.innerHTML = `<div class="pending-empty">โหลดรายการไม่สำเร็จ</div>`;
    console.error(err);
  }
}

(async function init() {
  await loadBusinessTypeOptions();
  await loadPendingList();
})();
