import os
import subprocess
import threading
import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services.latex_generator import generate, OUTPUT_DIR

router = APIRouter(prefix="/export", tags=["export"])

# In-memory job tracker (sufficient for single-user desktop app)
_jobs: dict[str, dict] = {}


class LatexRequest(BaseModel):
    book: str
    chapter_start: int
    chapter_end: int
    edition: str = "2013"
    include_commentary: bool = True
    include_media: bool = True


class PdfRequest(BaseModel):
    tex_path: str


@router.post("/latex")
def export_latex(req: LatexRequest):
    try:
        tex_path = generate(
            book=req.book,
            chapter_start=req.chapter_start,
            chapter_end=req.chapter_end,
            edition=req.edition,
            include_commentary=req.include_commentary,
            include_media=req.include_media,
        )
        return {"tex_path": tex_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pdf")
def compile_pdf(req: PdfRequest):
    if not os.path.exists(req.tex_path):
        raise HTTPException(status_code=404, detail="tex_path not found")

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "pending", "pdf_path": None, "error": None}

    def run():
        try:
            result = subprocess.run(
                [
                    "pdflatex",
                    "-interaction=nonstopmode",
                    "-output-directory", OUTPUT_DIR,
                    req.tex_path,
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                pdf_path = os.path.join(OUTPUT_DIR, "export.pdf")
                _jobs[job_id]["status"] = "complete"
                _jobs[job_id]["pdf_path"] = pdf_path
            else:
                _jobs[job_id]["status"] = "error"
                _jobs[job_id]["error"] = result.stdout[-2000:] + result.stderr[-500:]
        except subprocess.TimeoutExpired:
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["error"] = "pdflatex timed out after 60 seconds"
        except FileNotFoundError:
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["error"] = "pdflatex not found — please install MacTeX"

    threading.Thread(target=run, daemon=True).start()
    return {"job_id": job_id}


@router.get("/pdf/status")
def pdf_status(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/health")
def health():
    return {"status": "ok"}
