// --- Element refs ---
const uploadForm = document.getElementById("uploadForm");
const jobInfo = document.getElementById("jobInfo");

const jobIdInput = document.getElementById("jobIdInput");
const statusLine = document.getElementById("statusLine");
const savingsLine = document.getElementById("savingsLine");

const logBox = document.getElementById("logBox");
const checkBtn = document.getElementById("checkBtn");
const downloadBtn = document.getElementById("downloadBtn");
const deleteBtn = document.getElementById("deleteBtn");

const statePill = document.getElementById("statePill");
const progressBar = document.getElementById("progressBar");
const copyLog = document.getElementById("copyLog");

const themeToggle = document.getElementById("themeToggle");

const dropZone = document.getElementById("dropZone");
const fileInput = document.getElementById("fileInput");
const fileName = document.getElementById("fileName");

const historyList = document.getElementById("historyList");
const clearHistoryBtn = document.getElementById("clearHistory");

let pollTimer = null;

// --- Theme ---
const THEME_KEY = "clearscan_theme";

function updateThemeToggleLabel(theme) {
  if (!themeToggle) return;
  themeToggle.textContent = theme === "light" ? "Switch to dark" : "Switch to light";
}

function applyTheme(theme) {
  const body = document.body;
  const isLight = theme === "light";

  body.classList.toggle("theme-light", isLight);
  body.classList.toggle("theme-dark", !isLight);
  body.classList.toggle("bg-slate-50", isLight);
  body.classList.toggle("text-slate-900", isLight);
  body.classList.toggle("bg-slate-950", !isLight);
  body.classList.toggle("text-slate-100", !isLight);

  document.documentElement.style.colorScheme = isLight ? "light" : "dark";
  updateThemeToggleLabel(theme);
}

function getTheme() {
  const stored = localStorage.getItem(THEME_KEY);
  return stored === "light" ? "light" : "dark";
}

function setTheme(theme) {
  localStorage.setItem(THEME_KEY, theme);
  applyTheme(theme);
}

applyTheme(getTheme());
// --- Build/version info ---
const buildInfo = document.getElementById("buildInfo");
async function loadVersion() {
  try {
    const res = await fetch("/api/version");
    if (!res.ok) return;
    const v = await res.json();
    if (buildInfo) {
      const sha = v.git_sha ? ` (${String(v.git_sha).slice(0,7)})` : "";
      buildInfo.textContent = `${v.version || "v0.6.2"}${sha}`;
    }
  } catch {}
}
loadVersion();

themeToggle?.addEventListener("click", () => setTheme(getTheme() === "dark" ? "light" : "dark"));

// --- File picker + drag/drop ---
dropZone?.addEventListener("click", () => fileInput?.click());

function updateSelectedFileLabel(files) {
  const selected = files || fileInput?.files;
  if (!selected || !selected.length) {
    fileName.textContent = "";
    return;
  }
  if (selected.length === 1) {
    fileName.textContent = `Selected: ${selected[0].name}`;
    return;
  }
  fileName.textContent = `Selected: ${selected.length} files`;
}

fileInput?.addEventListener("change", () => {
  updateSelectedFileLabel(fileInput.files);
});

["dragenter", "dragover"].forEach((evt) =>
  dropZone?.addEventListener(evt, (e) => {
    e.preventDefault();
    e.stopPropagation();
    dropZone.classList.add("border-indigo-500/70");
  })
);
["dragleave"].forEach((evt) =>
  dropZone?.addEventListener(evt, (e) => {
    e.preventDefault();
    e.stopPropagation();
    dropZone.classList.remove("border-indigo-500/70");
  })
);

dropZone?.addEventListener("drop", (e) => {
  e.preventDefault();
  e.stopPropagation();
  dropZone.classList.remove("border-indigo-500/70");

  const droppedFiles = e.dataTransfer?.files;
  if (!droppedFiles || !droppedFiles.length) return;

  try {
    fileInput.files = droppedFiles;
  } catch {}
  updateSelectedFileLabel(droppedFiles);
});

// --- Helpers ---
function humanBytes(n) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return "";
  const units = ["B", "KB", "MB", "GB"];
  let x = Number(n),
    u = 0;
  while (x >= 1024 && u < units.length - 1) {
    x /= 1024;
    u++;
  }
  return `${x.toFixed(u === 0 ? 0 : 2)} ${units[u]}`;
}

// --- History storage (v2) ---
// --- History storage (v3): server-first, local fallback ---
const HISTORY_KEY = "clearscan_job_history_v2"; // fallback only

async function fetchJobs() {
  try {
    const res = await fetch("/api/jobs");
    if (!res.ok) return null;
    const data = await res.json();
    return Array.isArray(data.jobs) ? data.jobs : [];
  } catch {
    return null;
  }
}

async function clearJobsOnServer() {
  const jobs = await fetchJobs();
  if (!jobs) return false;

  for (const j of jobs) {
    try { await fetch(`/api/delete/${j.job_id}`, { method: "POST" }); } catch {}
  }
  return true;
}

// Fallback local history (kept for resilience)
function loadLocalHistory() {
  try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]"); }
  catch { return []; }
}
function saveLocalHistory(items) {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(items.slice(0, 30)));
}
function upsertLocalHistory(entry) {
  const items = loadLocalHistory();
  const idx = items.findIndex((x) => x.jobId === entry.jobId);
  if (idx >= 0) items[idx] = { ...items[idx], ...entry };
  else items.unshift(entry);
  saveLocalHistory(items);
}

function renderHistoryFromJobs(jobs) {
  historyList.innerHTML = "";

  if (!jobs || !jobs.length) {
    historyList.innerHTML = `<li class="text-xs text-slate-400">No jobs yet.</li>`;
    return;
  }

  for (const item of jobs) {
    const li = document.createElement("li");
    li.className = "rounded-lg bg-slate-950/60 border border-slate-800 px-3 py-2";

    const when = item.created ? new Date(item.created).toLocaleString() : "";
    const sizesKnown =
      typeof item.input_bytes === "number" &&
      typeof item.output_bytes === "number" &&
      typeof item.savings_pct === "number";

    const sizesText = sizesKnown
      ? `${humanBytes(item.input_bytes)} → ${humanBytes(item.output_bytes)} (-${Math.abs(item.savings_pct).toFixed(2)}%)`
      : "Sizes: pending…";

    li.innerHTML = `
      <div class="flex items-center justify-between gap-3">
        <div class="min-w-0">
          <div class="text-sm font-semibold truncate">${item.filename || "(unknown.pdf)"}</div>
          <div class="text-[11px] text-slate-400 font-mono truncate">${item.job_id}</div>
          <div class="text-[11px] text-slate-400">${when}</div>
          <div class="text-[11px] text-slate-400 mt-1">${sizesText}</div>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          <button class="useJob text-xs px-3 py-2 rounded-lg bg-slate-900 border border-slate-800 hover:bg-slate-800">Use</button>
          <button class="dlJob text-xs px-3 py-2 rounded-lg bg-emerald-600 text-white hover:bg-emerald-500">DL</button>
        </div>
      </div>
    `;

    li.querySelector(".useJob").addEventListener("click", async () => {
      jobIdInput.value = item.job_id;
      await refresh(item.job_id, true);
      if (pollTimer) clearInterval(pollTimer);
      pollTimer = setInterval(() => refresh(item.job_id, true), 1500);
    });

    li.querySelector(".dlJob").addEventListener("click", () => {
      window.location.href = `/api/download/${item.job_id}`;
    });

    historyList.appendChild(li);
  }
}

async function renderHistory() {
  const serverJobs = await fetchJobs();
  if (serverJobs) {
    renderHistoryFromJobs(serverJobs);
    return;
  }

  // fallback (offline / endpoint missing)
  const local = loadLocalHistory();
  renderHistoryFromJobs(local.map(x => ({
    job_id: x.jobId,
    filename: x.filename,
    created: x.ts,
    input_bytes: x.inputBytes,
    output_bytes: x.outputBytes,
    savings_pct: x.savingsPct,
  })));
}

clearHistoryBtn?.addEventListener("click", async () => {
  const ok = await clearJobsOnServer();
  if (!ok) {
    // fallback: clear local
    saveLocalHistory([]);
  }
  await renderHistory();
});

// Call once on load
renderHistory();


// --- Status logic ---
async function fetchStatus(jobId) {
  const res = await fetch(`/api/status/${jobId}`);
  if (!res.ok) return null;
  return await res.json();
}

function estimateProgress(logTail) {
  if (!logTail) return 0;
  const s = String(logTail).toLowerCase();
  if (s.includes("complete") || s.includes("finished") || s.includes("output")) return 95;
  if (s.includes("optim") || s.includes("optimiz")) return 80;
  if (s.includes("ocr") || s.includes("tesseract")) return 60;
  if (s.includes("page") || s.includes("analy")) return 35;
  return 10;
}

function setPill(state) {
  statePill.textContent = state || "unknown";
  statePill.classList.remove("bg-slate-800", "bg-indigo-700", "bg-emerald-700", "bg-rose-700");
  if (state === "running") statePill.classList.add("bg-indigo-700");
  else if (state === "done") statePill.classList.add("bg-emerald-700");
  else if (state === "error") statePill.classList.add("bg-rose-700");
  else statePill.classList.add("bg-slate-800");
}

function setButtons(hasOutput, exists) {
  downloadBtn.disabled = !hasOutput;
  deleteBtn.disabled = !exists;
}

async function refresh(jobId, updateHistory = false) {
  const data = await fetchStatus(jobId);

  if (!data) {
    statusLine.textContent = "Not found.";
    savingsLine.textContent = "";
    setPill("unknown");
    progressBar.style.width = "0%";
    return;
  }

  const state = data.status?.state || "unknown";
  const ts = data.status?.ts || "";
  setPill(state);

  logBox.textContent = data.log_tail || "";
  progressBar.style.width = `${estimateProgress(data.log_tail)}%`;

  statusLine.textContent = `State: ${state}${ts ? " @ " + ts : ""}`;

  const inB = data.status?.input_bytes ?? data.meta?.input_bytes;
  const outB = data.status?.output_bytes;
  const pct = data.status?.savings_pct;

  if (state === "done" && typeof inB === "number" && typeof outB === "number" && typeof pct === "number") {
    const savedB = inB - outB;
    savingsLine.textContent =
      `Size: ${humanBytes(inB)} → ${humanBytes(outB)} (-${Math.abs(pct).toFixed(2)}%, saved ${humanBytes(Math.abs(savedB))})`;

    if (updateHistory) {
      upsertLocalHistory({
        jobId,
        filename: data.meta?.filename,
        ts: data.meta?.created || new Date().toISOString(),
        inputBytes: inB,
        outputBytes: outB,
        savingsPct: pct,
      });
    }
  } else {
    savingsLine.textContent = "";
    if (updateHistory) {
      upsertLocalHistory({
        jobId,
        filename: data.meta?.filename,
        ts: data.meta?.created || new Date().toISOString(),
        inputBytes: typeof inB === "number" ? inB : undefined,
      });
    }
  }

  setButtons(data.has_output, true);

  if (state === "done" || state === "error") {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = null;
  }
}

// --- Upload ---
uploadForm.addEventListener("submit", async (e) => {
  e.preventDefault();

  const selectedFiles = fileInput?.files;
  const fileCount = selectedFiles?.length || 0;
  if (!fileCount) {
    jobInfo.textContent = "Please choose at least one PDF.";
    return;
  }

  jobInfo.textContent = fileCount > 1 ? `Uploading ${fileCount} files...` : "Uploading...";
  savingsLine.textContent = "";

  const formData = new FormData(uploadForm);
  let endpoint = "/api/upload";
  let requestBody = formData;

  if (fileCount > 1) {
    endpoint = "/api/upload-batch";
    const batchData = new FormData();
    for (const f of selectedFiles) {
      batchData.append("files", f, f.name);
    }
    batchData.append("lang", String(formData.get("lang") || "eng"));
    batchData.append("mode", String(formData.get("mode") || "best"));
    batchData.append("output_type", String(formData.get("output_type") || "pdf"));
    batchData.append("optimize", String(formData.get("optimize") || "3"));
    batchData.append("force_ocr", formData.has("force_ocr") ? "true" : "false");
    requestBody = batchData;
  }

  const res = await fetch(endpoint, { method: "POST", body: requestBody });
  const data = await res.json();

  if (!res.ok) {
    const failed = Array.isArray(data.errors) ? ` (${data.errors.length} failed)` : "";
    jobInfo.textContent = `${data.error || "Upload failed"}${failed}`;
    return;
  }

  const createdJobs = Array.isArray(data.jobs)
    ? data.jobs
    : (data.job_id ? [data] : []);
  if (!createdJobs.length) {
    jobInfo.textContent = "No jobs were created.";
    return;
  }

  const failedCount = Array.isArray(data.errors) ? data.errors.length : 0;
  jobInfo.textContent = `${createdJobs.length} job${createdJobs.length === 1 ? "" : "s"} created${failedCount ? `, ${failedCount} failed` : ""}.`;

  for (const job of createdJobs) {
    upsertLocalHistory({
      jobId: job.job_id,
      filename: job.filename,
      ts: new Date().toISOString(),
      inputBytes: typeof job.input_bytes === "number" ? job.input_bytes : undefined,
    });
  }
  await renderHistory();

  const jobId = createdJobs[0].job_id;
  jobIdInput.value = jobId;

  await refresh(jobId, true);

  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(() => refresh(jobId, true), 1500);
});

// --- Status buttons ---
checkBtn.addEventListener("click", async () => {
  const jobId = jobIdInput.value.trim();
  if (!jobId) return;

  await refresh(jobId, true);

  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(() => refresh(jobId, true), 1500);
});

downloadBtn.addEventListener("click", () => {
  const jobId = jobIdInput.value.trim();
  if (!jobId) return;
  window.location.href = `/api/download/${jobId}`;
});

deleteBtn.addEventListener("click", async () => {
  const jobId = jobIdInput.value.trim();
  if (!jobId) return;

  await fetch(`/api/delete/${jobId}`, { method: "POST" });

  statusLine.textContent = "Deleted.";
  savingsLine.textContent = "";
  logBox.textContent = "";
  progressBar.style.width = "0%";
  setPill("idle");
  setButtons(false, false);

  const items = loadLocalHistory().filter((x) => x.jobId !== jobId);
  saveLocalHistory(items);
  await renderHistory();

  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;
});

copyLog.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(logBox.textContent || "");
    copyLog.textContent = "Copied!";
    setTimeout(() => (copyLog.textContent = "Copy"), 800);
  } catch {}
});

// --- Footer changelog drawer (slide-up) ---
const openChangelogBtn = document.getElementById("openChangelog");
const closeChangelogBtn = document.getElementById("closeChangelog");
const changelogBackdrop = document.getElementById("changelogBackdrop");
const changelogPanel = document.getElementById("changelogPanel");

function openChangelog() {
  if (!changelogBackdrop || !changelogPanel) return;

  changelogBackdrop.classList.remove("pointer-events-none", "opacity-0");
  changelogBackdrop.classList.add("opacity-100");

  changelogPanel.classList.remove("translate-y-full");
  changelogPanel.style.transform = "translateY(0)";

  // lock background scroll (mobile friendly)
  document.documentElement.style.overflow = "hidden";
  document.body.style.overflow = "hidden";
}

function closeChangelog() {
  if (!changelogBackdrop || !changelogPanel) return;

  changelogBackdrop.classList.add("pointer-events-none", "opacity-0");
  changelogBackdrop.classList.remove("opacity-100");

  changelogPanel.classList.add("translate-y-full");
  changelogPanel.style.transform = "translateY(100%)";

  document.documentElement.style.overflow = "";
  document.body.style.overflow = "";
}

openChangelogBtn?.addEventListener("click", (e) => {
  e.preventDefault();
  openChangelog();
});
closeChangelogBtn?.addEventListener("click", (e) => {
  e.preventDefault();
  closeChangelog();
});
changelogBackdrop?.addEventListener("click", closeChangelog);

// ESC to close (desktop)
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeChangelog();
});




