import os
import re
import uuid
import json
import shutil
import subprocess
import threading
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

APP_DIR = Path(__file__).resolve().parent
ENGINE = Path("/srv/engine/clearscan_engine.py")

JOBS_DIR = Path(os.getenv("JOBS_DIR", "/data/jobs"))
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "500"))

app = FastAPI(title="ClearScan OSS Web")
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

JOBS_DIR.mkdir(parents=True, exist_ok=True)

def job_paths(job_id: str) -> dict:
    base = JOBS_DIR / job_id
    return {
        "base": base,
        "input": base / "input.pdf",
        "output_pdf": base / "out" / "output.pdf",
        "out_dir": base / "out",
        "log": base / "job.log",
        "meta": base / "meta.json",
        "status": base / "status.json",
    }

def safe_filename(name: str) -> str:
    name = (name or "document.pdf").strip()
    name = name.replace("\\", "/").split("/")[-1]
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:180] or "document.pdf"

def optimised_name(original: str) -> str:
    original = safe_filename(original)
    stem = original[:-4] if original.lower().endswith(".pdf") else original
    return f"{stem}-optimised.pdf"

def write_status(p: Path, state: str, **extra):
    payload = {"state": state, "ts": datetime.utcnow().isoformat() + "Z", **extra}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2))

def run_job(job_id: str, lang: str, mode: str, force_ocr: bool, output_type: str, optimize: str):
    paths = job_paths(job_id)
    base = paths["base"]
    log_path = paths["log"]
    out_pdf = paths["output_pdf"]

    write_status(paths["status"], "running")
    paths["out_dir"].mkdir(parents=True, exist_ok=True)

    cmd = [
        "python3", str(ENGINE),
        str(paths["input"]),
        "--out", str(out_pdf),
        "--lang", lang,
        "--mode", mode,
        "--output-type", output_type,
        "--optimize", optimize,
    ]
    if force_ocr:
        cmd.append("--force-ocr")

    base.mkdir(parents=True, exist_ok=True)

    with log_path.open("w", encoding="utf-8") as log:
        log.write("Running:\n" + " ".join(cmd) + "\n\n")
        log.flush()
        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, text=True, cwd=str(base))
        rc = proc.wait()

    if rc == 0 and out_pdf.exists():
        in_size = paths["input"].stat().st_size if paths["input"].exists() else None
        out_size = out_pdf.stat().st_size if out_pdf.exists() else None
        savings_pct = None
        savings_bytes = None
        if isinstance(in_size, int) and isinstance(out_size, int) and in_size > 0:
            savings_bytes = in_size - out_size
            savings_pct = round((savings_bytes / float(in_size)) * 100.0, 2)
        write_status(paths["status"], "done",
                     input_bytes=in_size, output_bytes=out_size,
                     savings_bytes=savings_bytes, savings_pct=savings_pct)
    else:
        write_status(paths["status"], "error", exit_code=rc)

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    lang: str = Form("eng"),
    mode: str = Form("best"),
    force_ocr: bool = Form(False),
    output_type: str = Form("pdf"),
    optimize: str = Form("3"),
):
    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > MAX_UPLOAD_MB:
        return JSONResponse({"error": f"File too large: {size_mb:.1f}MB (max {MAX_UPLOAD_MB}MB)"}, status_code=413)

    job_id = uuid.uuid4().hex
    paths = job_paths(job_id)
    paths["base"].mkdir(parents=True, exist_ok=True)

    paths["input"].write_bytes(contents)
    original_name = safe_filename(file.filename or "document.pdf")

    paths["meta"].write_text(json.dumps({
        "filename": original_name,
        "created": datetime.utcnow().isoformat() + "Z",
        "lang": lang,
        "mode": mode,
        "force_ocr": force_ocr,
        "output_type": output_type,
        "optimize": optimize,
        "input_bytes": len(contents),
    }, indent=2))

    write_status(paths["status"], "queued")

    t = threading.Thread(target=run_job, args=(job_id, lang, mode, force_ocr, output_type, optimize), daemon=True)
    t.start()

    return {"job_id": job_id, "filename": original_name, "input_bytes": len(contents)}

@app.get("/api/status/{job_id}")
def status(job_id: str):
    paths = job_paths(job_id)
    if not paths["base"].exists():
        return JSONResponse({"error": "Not found"}, status_code=404)

    status_obj = json.loads(paths["status"].read_text()) if paths["status"].exists() else {}
    meta_obj = json.loads(paths["meta"].read_text()) if paths["meta"].exists() else {}

    log_tail = ""
    if paths["log"].exists():
        lines = paths["log"].read_text(errors="ignore").splitlines()[-300:]
        log_tail = "\n".join(lines)

    return {"job_id": job_id, "status": status_obj, "meta": meta_obj, "has_output": paths["output_pdf"].exists(), "log_tail": log_tail}

@app.get("/api/download/{job_id}")
def download(job_id: str):
    paths = job_paths(job_id)
    if not paths["output_pdf"].exists():
        return JSONResponse({"error": "Output not ready"}, status_code=404)

    original_name = "document.pdf"
    if paths["meta"].exists():
        try:
            meta = json.loads(paths["meta"].read_text())
            original_name = meta.get("filename") or original_name
        except Exception:
            pass

    return FileResponse(path=str(paths["output_pdf"]), filename=optimised_name(original_name), media_type="application/pdf")

@app.post("/api/delete/{job_id}")
def delete(job_id: str):
    paths = job_paths(job_id)
    if not paths["base"].exists():
        return JSONResponse({"error": "Not found"}, status_code=404)
    shutil.rmtree(paths["base"], ignore_errors=True)
    return {"ok": True}
