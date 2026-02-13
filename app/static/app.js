console.log("✅ app.js loaded", new Date().toISOString());

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

// Drawer
const openChangelogBtn = document.getElementById("openChangelog");
const closeChangelogBtn = document.getElementById("closeChangelog");
const changelogBackdrop = document.getElementById("changelogBackdrop");
const changelogPanel = document.getElementById("changelogPanel");

let pollTimer = null;

// ---------------- Theme ----------------
const THEME_KEY = "clearscan_theme";
function applyTheme(theme) {
  const body = document.body;
  if (theme === "light") {
    body.classList.remove("bg-slate-950", "text-slate-100");
    body.classList.add("bg-slate-50", "text-slate-900");
    document.documentElement.style.colorScheme = "light";
  } else {
    body.classList.remove("bg-slate-50", "text-slate-900");
    body.classList.add("bg-slate-950", "text-slate-100");
    document.documentElement.style.colorScheme = "dark";
  }
}
function getTheme() {
  return localStorage.getItem(THEME_KEY) || "dark";
}
function setTheme(theme) {
  localStorage.setItem(THEME_KEY, theme);
  applyTheme(theme);
}
applyTheme(getTheme());
themeToggle?.addEventListener("click", () => setTheme(getTheme() === "dark" ? "light" : "dark"));

// ---------------- File picker + drag/drop (mobile-safe) ----------------
function setSelectedFile(file) {
  if (!file) {
    fileName.textContent = "";
    return;
  }
  if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
    fileName.textContent = "Please select a PDF file.";
    return;
  }
  fileName.textContent = `Selected: ${file.name}`;
}

dropZone?.addEventListener("click", () => fileInput?.click());

fileInput?.addEventListener("change", () => {
  setSelectedFile(fileInput.files?.[0]);
});

// Drag & drop (desktop)
["dragenter", "dragover"].forEach((evt) =>
  dropZone?.addEventListener(evt, (e) => {
    e.preventDefault();
    e.stopPropagation();
    dropZone.classList.add("border-indigo-500/70");
  })
);
["dragleave", "drop"].forEach((evt) =>
  dropZone?.addEventListener(evt, (e) => {
    e.preventDefault();
    e.stopPropagation();
    dropZone.classList.remove("border-indigo-500/70");
  })
);

dropZone?.addEventListener("drop", (e) => {
  const f = e.dataTransfer?.files?.[0];
  if (!f) return;
  try { fileInput.files = e.dataTransfer.files; } catch {}
  setSelectedFile(f);
});

// ---------------- Helpers ----------------
function humanBytes(n) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return "";
  const units = ["B", "KB", "MB", "GB"];
  let x = Number(n), u = 0;
  while (x >= 1024 && u < units.length - 1) { x /= 1024; u++; }
  return `${x.toFixed(u === 0 ? 0 : 2)} ${units[u]}`;
}

function safeNum(x) {
  const n = Number(x);
  return Number.isFinite(n) ? n : null;
}

// ---------------- History (v2) ----------------
const HISTORY_KEY = "clearscan_job_history_v2";

function loadHistory() {
  try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]"); }
  catch { return []; }
}
function saveHistory(items) {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(items.slice(0, 30)));
}
function upsertHistory(entry) {
  const items = loadHistory();
  const idx = items.findIndex((x) => x.jobId === entry.jobId);
  if (idx >= 0) items[idx] = { ...items[idx], ...entry };
  else items.unshift(entry);
  saveHistory(items);
  renderHistory();
}
function renderHistory() {
  const items = loadHistory();
  historyList.innerHTML = "";

  if (!items.length) {
    historyList.innerHTML = `<li class="text-xs text-slate-400">No jobs yet.</li>`;
    return;
  }

  for (const item of items) {
    const li = document.createElement("li");
    li.className = "rounded-lg bg-slate-950/60 border border-slate-800 px-3 py-2";

    const when = item.ts ? new Date(item.ts).toLocaleString() : "";
    const sizesKnown =
      typeof item.inputBytes === "number" &&
      typeof item.outputBytes === "number" &&
      typeof item.savingsPct === "number";

    const sizesText = sizesKnown
      ? `${humanBytes(item.inputBytes)} → ${humanBytes(item.outputBytes)} (-${Math.abs(item.savingsPct).toFixed(2)}%)`
      : "Sizes: pending…";

    li.innerHTML = `
      <div class="flex items-center justify-between gap-3">
        <div class="min-w-0">
          <div class="text-sm font-semibold truncate">${item.filename || "(unknown.pdf)"}</div>
          <div class="text-[11px] text-slate-400 font-mono truncate">${item.jobId}</div>
          <div class="text-[11px] text-slate-400">${when}</div>
          <div class="text-[11px] text-slate-400 mt-1">${sizesText}</div>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          <button class="useJob" type="button"
            class="text-xs px-3 py-2 rounded-lg bg-slate-900 border border-slate-800 hover:bg-slate-800">Use</button>
          <button class="dlJob" type="button"
            class="text-xs px-3 py-2 rounded-lg bg-emerald-600 text-white hover:bg-emerald-500">DL</button>
        </div>
      </div>
    `;

    li.querySelector(".useJob").addEventListener("click", async () => {
      jobIdInput.value = item.jobId;
      await refresh(item.jobId, true);
      if (pollTimer) clearInterval(pollTimer);
      pollTimer = setInterval(() => refresh(item.jobId, true), 1500);
    });

    li.querySelector(".dlJob").addEventListener("click", () => {
      window.location.href = `/api/download/${item.jobId}`;
    });

    historyList.appendChild(li);
  }
}

clearHistoryBtn?.addEventListener("click", () => {
  saveHistory([]);
  renderHistory();
});

renderHistory();

// ---------------- Status logic ----------------
async function fetchStatus(jobId) {
  const res = await fetch(`/api/status/${jobId}`);
  if (!res.ok) return null;
  return await res.json();
}

function estimateProgress(logTail) {
  if (!logTail) return 0;
  const s = String(logTail).toLowerCase();
  if (s.includes("done") || s.includes("complete") || s.includes("finished")) return 100;
  if (s.includes("optim") || s.includes("optimiz")) return 80;
  if (s.includes("ocr") || s.includes("tesseract")) return 60;
  if (s.includes("preprocess") || s.includes("page") || s.includes("render")) return 35;
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

  // These fields depend on your backend. If present, we show savings.
  const inB = safeNum(data.status?.input_bytes ?? data.meta?.input_bytes);
  const outB = safeNum(data.status?.output_bytes);
  const pct = safeNum(data.status?.savings_pct);

  if (state === "done" && inB !== null && outB !== null && pct !== null) {
    const savedB = inB - outB;
    savingsLine.textContent =
      `Size: ${humanBytes(inB)} → ${humanBytes(outB)} (-${Math.abs(pct).toFixed(2)}%, saved ${humanBytes(Math.abs(savedB))})`;

    if (updateHistory) {
      upsertHistory({
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
      upsertHistory({
        jobId,
        filename: data.meta?.filename,
        ts: data.meta?.created || new Date().toISOString(),
        inputBytes: inB !== null ? inB : undefined,
      });
    }
  }

  setButtons(!!data.has_output, true);

  if (state === "done" || state === "error") {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = null;
  }
}

// ---------------- Upload ----------------
uploadForm?.addEventListener("submit", async (e) => {
  e.preventDefault();

  jobInfo.textContent = "Uploading...";
  savingsLine.textContent = "";

  const formData = new FormData(uploadForm);

  const res = await fetch("/api/upload", { method: "POST", body: formData });
  const data = await res.json().catch(() => ({}));

  if (!res.ok) {
    jobInfo.textContent = data.error || "Upload failed";
    return;
  }

  const jobId = data.job_id;
  jobInfo.textContent = `Job created: ${jobId}`;
  jobIdInput.value = jobId;

  upsertHistory({
    jobId,
    filename: data.filename || fileInput?.files?.[0]?.name,
    ts: new Date().toISOString(),
    inputBytes: safeNum(data.input_bytes) ?? undefined,
  });

  await refresh(jobId, true);

  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(() => refresh(jobId, true), 1500);
});

// ---------------- Buttons ----------------
checkBtn?.addEventListener("click", async () => {
  const jobId = jobIdInput.value.trim();
  if (!jobId) return;

  await refresh(jobId, true);

  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(() => refresh(jobId, true), 1500);
});

downloadBtn?.addEventListener("click", () => {
  const jobId = jobIdInput.value.trim();
  if (!jobId) return;
  window.location.href = `/api/download/${jobId}`;
});

deleteBtn?.addEventListener("click", async () => {
  const jobId = jobIdInput.value.trim();
  if (!jobId) return;

  await fetch(`/api/delete/${jobId}`, { method: "POST" });

  statusLine.textContent = "Deleted.";
  savingsLine.textContent = "";
  logBox.textContent = "";
  progressBar.style.width = "0%";
  setPill("idle");
  setButtons(false, false);

  const items = loadHistory().filter((x) => x.jobId !== jobId);
  saveHistory(items);
  renderHistory();

  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;
});

copyLog?.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(logBox.textContent || "");
    copyLog.textContent = "Copied!";
    setTimeout(() => (copyLog.textContent = "Copy"), 800);
  } catch {}
});

// ---------------- Changelog drawer (slide-up, iOS-safe) ----------------
function initDrawer() {
  if (!changelogBackdrop || !changelogPanel) {
    console.warn("Changelog drawer elements missing");
    return;
  }

  // Ensure initial hidden state
  changelogBackdrop.style.opacity = "0";
  changelogBackdrop.style.pointerEvents = "none";
  changelogPanel.style.transform = "translateY(100%)";

  function openChangelog() {
    changelogBackdrop.style.opacity = "1";
    changelogBackdrop.style.pointerEvents = "auto";
    changelogPanel.style.transform = "translateY(0)";
    document.documentElement.style.overflow = "hidden";
    document.body.style.overflow = "hidden";
  }

  function closeChangelog() {
    changelogBackdrop.style.opacity = "0";
    changelogBackdrop.style.pointerEvents = "none";
    changelogPanel.style.transform = "translateY(100%)";
    document.documentElement.style.overflow = "";
    document.body.style.overflow = "";
  }

  openChangelogBtn?.addEventListener("click", openChangelog);
  closeChangelogBtn?.addEventListener("click", closeChangelog);
  changelogBackdrop.addEventListener("click", closeChangelog);

  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeChangelog();
  });
}

initDrawer();
