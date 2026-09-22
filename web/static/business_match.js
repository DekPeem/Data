// หน้า "จับคู่เฉพาะหมวดธุรกิจ" — เวอร์ชันเร็วของหน้า "รอทราบอัตรา" (/pending-amr) สำหรับตอนมีไฟล์
// รอทราบอัตราเยอะๆ แต่ไม่รู้รหัสอัตราเลยสักตัว — ตัดช่องรหัสอัตรา/KVA/Solar/ป้ายกำกับไซต์ออกหมด
// เหลือแค่เลือกประเภทธุรกิจแล้วกดยืนยัน (ส่ง rate_code_unknown=true ให้เสมอ ใช้ endpoint เดียวกับ
// หน้ารอทราบอัตรา — ดู UNKNOWN_RATE_CODE ใน web/app.py)

const tableBody = document.getElementById("match-table-body");
const emptyStateEl = document.getElementById("match-empty-state");

let businessTypeOptionsHtml = "";

async function loadBusinessTypeOptions() {
  try {
    const res = await fetch("/api/business-types");
    const types = await res.json();
    businessTypeOptionsHtml =
      `<option value="">-- เลือกประเภทธุรกิจ --</option>` +
      types.map((t) => `<option value="${t.code}">${t.name_th} (${t.code})</option>`).join("");
  } catch (err) {
    console.error("โหลดประเภทธุรกิจไม่สำเร็จ", err);
  }
}

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function renderRow(entry) {
  const fileCount = (entry.file_paths || "").split("|").filter(Boolean).length;
  const name = entry.company_name ? escapeHtml(entry.company_name) : "(ไม่ทราบชื่อผู้ใช้ไฟ)";

  const row = document.createElement("tr");
  row.dataset.pendingId = entry.pending_id;
  row.innerHTML = `
    <td>
      <div class="match-name">${name}</div>
      <div class="match-sub">เลขบัญชี ${escapeHtml(entry.account_no) || "-"} · ${fileCount} ไฟล์</div>
      <div class="match-hint"></div>
    </td>
    <td><select class="m-business-type">${businessTypeOptionsHtml}</select></td>
    <td><button type="button" class="match-btn">ยืนยัน</button></td>
  `;

  const select = row.querySelector(".m-business-type");
  const btn = row.querySelector(".match-btn");
  const hintEl = row.querySelector(".match-hint");

  btn.addEventListener("click", async () => {
    hintEl.textContent = "";
    const business_type_code = select.value;
    if (!business_type_code) {
      hintEl.textContent = "กรุณาเลือกประเภทธุรกิจก่อน";
      return;
    }

    btn.disabled = true;
    select.disabled = true;
    try {
      const res = await fetch(`/api/admin/pending-amr/${entry.pending_id}/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ business_type_code, rate_code_unknown: true }),
      });
      const data = await res.json();
      if (!res.ok) {
        hintEl.textContent = data.message || "นำเข้าไม่สำเร็จ";
        btn.disabled = false;
        select.disabled = false;
        return;
      }
      row.style.opacity = "0.5";
      row.querySelector(".match-name").textContent = `✅ ${name}`;
      setTimeout(() => {
        row.remove();
        if (!tableBody.children.length) renderEmptyState();
      }, 900);
    } catch (err) {
      hintEl.textContent = "เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ";
      btn.disabled = false;
      select.disabled = false;
      console.error(err);
    }
  });

  return row;
}

function renderEmptyState() {
  emptyStateEl.innerHTML = `<div class="match-empty">🎉 ไม่มีรายการรอจับคู่ตอนนี้</div>`;
}

async function loadPendingList() {
  emptyStateEl.innerHTML = "";
  tableBody.innerHTML = `<tr><td colspan="3" class="match-empty">กำลังโหลด...</td></tr>`;
  try {
    const res = await fetch("/api/admin/pending-amr");
    const data = await res.json();
    const entries = data.entries || [];
    tableBody.innerHTML = "";
    if (!entries.length) {
      renderEmptyState();
      return;
    }
    entries.forEach((entry) => tableBody.appendChild(renderRow(entry)));
  } catch (err) {
    tableBody.innerHTML = "";
    emptyStateEl.innerHTML = `<div class="match-empty">โหลดรายการไม่สำเร็จ</div>`;
    console.error(err);
  }
}

(async function init() {
  await loadBusinessTypeOptions();
  await loadPendingList();
})();
