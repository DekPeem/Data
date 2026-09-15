const PERIOD_TH = { P: "Peak (P)", OP: "Off-Peak (OP)", H: "Holiday (H)" };

const businessTypeSelect = document.getElementById("f-business-type");
const submitBtn = document.getElementById("submit-btn");
const formHint = document.getElementById("form-hint");
const jobArea = document.getElementById("job-area");
const jobStatusPill = document.getElementById("job-status-pill");
const jobLog = document.getElementById("job-log");
const jobResult = document.getElementById("job-result");
const usernameInput = document.getElementById("f-username");
const accountsInput = document.getElementById("f-accounts");

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
    const autoOption = `<option value="">-- ให้ระบบตรวจจับอัตโนมัติ --</option>`;
    businessTypeSelect.innerHTML =
      autoOption + types.map((t) => `<option value="${t.code}">${t.name_th} (${t.code})</option>`).join("");
  } catch (err) {
    console.error("โหลดประเภทธุรกิจไม่สำเร็จ", err);
  }
}

function setStatusPill(status) {
  const map = {
    running: { text: "⏳ กำลังทำงาน...", bg: "#eef3fa", color: "#184f95" },
    success: { text: "✅ สำเร็จ", bg: "#e8f7ec", color: "#006300" },
    error: { text: "❌ ไม่สำเร็จ", bg: "#fdecea", color: "#a01818" },
  };
  const s = map[status] || map.running;
  jobStatusPill.textContent = s.text;
  jobStatusPill.style.background = s.bg;
  jobStatusPill.style.color = s.color;
}

function renderResult(result) {
  jobResult.innerHTML = `
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
    <div class="field-label" style="margin-top:12px;">บันทึกแล้วสำหรับ: ${result.business_type_code} / อัตรา ${result.rate_code} (เฉลี่ยจาก ${result.sample_size} ไฟล์)</div>
  `;
}

async function pollJob(jobId) {
  const res = await fetch(`/api/admin/import/${jobId}`);
  const data = await res.json();

  setStatusPill(data.status);
  jobLog.textContent = (data.logs || []).join("\n");
  jobLog.scrollTop = jobLog.scrollHeight;

  if (data.status === "running") {
    setTimeout(() => pollJob(jobId), 1000);
    return;
  }

  submitBtn.disabled = false;

  if (data.status === "success") {
    renderResult(data.result);
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

    pollJob(data.job_id);
  } catch (err) {
    submitBtn.disabled = false;
    formHint.textContent = "เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ";
    console.error(err);
  }
}

submitBtn.addEventListener("click", startImport);
loadBusinessTypes();
