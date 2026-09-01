from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models_db import Job, JobLine, JobStatus, User
from app.schemas import JobCreate, JobDetailOut, JobLineOut, JobLineUpdate, JobOut, ChatIn, ChatOut
from app.services import (
    chat_job,
    delete_job,
    generate_docx,
    job_dir,
    process_job_background,
    read_progress,
    recalculate_potencial,
    save_approved_snippet,
    save_upload,
    write_progress,
)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _job_out(job: Job, db: Session) -> JobOut:
    lines = db.query(JobLine).filter(JobLine.job_id == job.id).all()
    prog = read_progress(job.id)
    if prog is None and job.status == JobStatus.processing:
        prog = {
            "done": len(lines),
            "total": max(len(lines), 1),
            "pct": 0,
            "message": "Iniciando…",
            "phase": "parse",
            "ghe": "",
        }
    return JobOut(
        id=job.id,
        title=job.title,
        status=job.status.value,
        empresa=job.empresa,
        cnpj=job.cnpj,
        error_message=job.error_message,
        notes_json=job.notes_json,
        created_at=job.created_at,
        updated_at=job.updated_at,
        lines_count=len(lines),
        accepted_count=sum(1 for l in lines if l.accepted and not l.discarded),
        progress=prog,
    )


@router.get("", response_model=list[JobOut])
def list_jobs(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    jobs = (
        db.query(Job)
        .filter(Job.owner_id == user.id)
        .order_by(Job.created_at.desc())
        .all()
    )
    return [_job_out(j, db) for j in jobs]


@router.post("", response_model=JobOut)
def create_job(
    body: JobCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    job = Job(title=body.title, owner_id=user.id, status=JobStatus.draft)
    db.add(job)
    db.commit()
    db.refresh(job)
    job_dir(job.id)
    return _job_out(job, db)


@router.delete("/{job_id}", status_code=204)
def remove_job(
    job_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    job = db.query(Job).filter(Job.id == job_id, Job.owner_id == user.id).first()
    if not job:
        raise HTTPException(404, "Job não encontrado")
    if job.status == JobStatus.processing:
        raise HTTPException(
            409,
            "Job em processamento — aguarde terminar antes de excluir.",
        )
    delete_job(db, job)


@router.get("/{job_id}", response_model=JobDetailOut)
def get_job(
    job_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    job = db.query(Job).filter(Job.id == job_id, Job.owner_id == user.id).first()
    if not job:
        raise HTTPException(404, "Job não encontrado")
    base = _job_out(job, db)
    lines = db.query(JobLine).filter(JobLine.job_id == job.id).order_by(JobLine.ghe_numero).all()
    return JobDetailOut(**base.model_dump(), lines=lines)


@router.post("/{job_id}/upload")
async def upload_files(
    job_id: int,
    campanha: UploadFile | None = File(None),
    pgr: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.query(Job).filter(Job.id == job_id, Job.owner_id == user.id).first()
    if not job:
        raise HTTPException(404, "Job não encontrado")

    if campanha is not None:
        data = await campanha.read()
        path = save_upload(job.id, "campanha", campanha.filename or "campanha.pdf", data)
        job.campanha_path = str(path)
    if pgr is not None:
        data = await pgr.read()
        path = save_upload(job.id, "pgr", pgr.filename or "pgr.docx", data)
        job.pgr_path = str(path)

    db.add(job)
    db.commit()
    return {"ok": True, "campanha": job.campanha_path, "pgr": job.pgr_path}


@router.post("/{job_id}/process", response_model=JobOut)
def run_process(
    job_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.query(Job).filter(Job.id == job_id, Job.owner_id == user.id).first()
    if not job:
        raise HTTPException(404, "Job não encontrado")
    if not job.campanha_path or not job.pgr_path:
        raise HTTPException(400, "Campanha PDF e PGR DOCX são obrigatórios")
    if job.status == JobStatus.processing:
        return _job_out(job, db)

    job.status = JobStatus.processing
    job.error_message = None
    job.notes_json = ["Fila: processamento iniciado…"]
    db.add(job)
    db.commit()
    write_progress(
        job.id,
        done=0,
        total=1,
        message="Na fila — iniciando motor…",
        phase="parse",
    )
    background_tasks.add_task(process_job_background, job.id)
    db.refresh(job)
    return _job_out(job, db)


@router.get("/{job_id}/progress")
def job_progress(
    job_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    job = db.query(Job).filter(Job.id == job_id, Job.owner_id == user.id).first()
    if not job:
        raise HTTPException(404, "Job não encontrado")
    prog = read_progress(job.id) or {
        "done": 0,
        "total": 1,
        "pct": 0,
        "message": "Sem progresso ainda",
        "phase": job.status.value,
        "ghe": "",
    }
    lines = db.query(JobLine).filter(JobLine.job_id == job.id).count()
    return {
        "status": job.status.value,
        "lines_count": lines,
        "error_message": job.error_message,
        **prog,
    }


@router.patch("/{job_id}/lines/{line_id}", response_model=JobLineOut)
def update_line(
    job_id: int,
    line_id: int,
    body: JobLineUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.query(Job).filter(Job.id == job_id, Job.owner_id == user.id).first()
    if not job:
        raise HTTPException(404, "Job não encontrado")
    line = db.query(JobLine).filter(JobLine.id == line_id, JobLine.job_id == job.id).first()
    if not line:
        raise HTTPException(404, "Linha não encontrada")

    data = body.model_dump(exclude_unset=True)

    if "danos" in data and data["danos"] is not None:
        from motor.llm import is_robotic_danos

        if is_robotic_danos(data["danos"]):
            raise HTTPException(
                422,
                "Danos não pode conter diagnóstico clínico (Burnout/Depressão/CID) — "
                "use agravo ocupacional amarrado ao posto",
            )
    if "agente" in data and data["agente"] is not None:
        from motor.hazards import is_generic_agente, is_job_title_agente

        if is_job_title_agente(data["agente"]) or is_generic_agente(data["agente"]):
            raise HTTPException(
                422,
                "Agente não pode ser cargo/função nem genérico — "
                "use perigo psicossocial (ex.: Demandas Quantitativas e Pressão Temporal)",
            )

    for k, v in data.items():
        setattr(line, k, v)
    if "grau_exposicao" in data or "grau_efeito" in data:
        recalculate_potencial(line)
    if data.get("accepted") is True and not data.get("discarded"):
        save_approved_snippet(db, job, line)
    # edição manual válida limpa flag de auditoria
    if "danos" in data or "agente" in data:
        line.needs_review = False
    db.add(line)
    db.commit()
    db.refresh(line)
    return line


@router.post("/{job_id}/revalidate")
def revalidate_lines(
    job_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    from app.services import revalidate_job_lines

    job = db.query(Job).filter(Job.id == job_id, Job.owner_id == user.id).first()
    if not job:
        raise HTTPException(404, "Job não encontrado")
    affected = revalidate_job_lines(db, job)
    return {
        "ok": True,
        "affected_count": len(affected),
        "ghe_numeros": affected,
    }


@router.post("/{job_id}/accept-all")
def accept_all(
    job_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    job = db.query(Job).filter(Job.id == job_id, Job.owner_id == user.id).first()
    if not job:
        raise HTTPException(404, "Job não encontrado")
    lines = db.query(JobLine).filter(JobLine.job_id == job.id, JobLine.discarded.is_(False)).all()
    for ln in lines:
        ln.accepted = True
        db.add(ln)
        save_approved_snippet(db, job, ln)
    db.commit()
    return {"accepted": len(lines)}


@router.post("/{job_id}/chat", response_model=ChatOut)
def job_chat(
    job_id: int,
    body: ChatIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.query(Job).filter(Job.id == job_id, Job.owner_id == user.id).first()
    if not job:
        raise HTTPException(404, "Job não encontrado")
    try:
        result = chat_job(
            db,
            job,
            body.message,
            history=[h.model_dump() for h in body.history],
            ghe_numero=body.ghe_numero,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc
    return ChatOut(
        reply=result.get("reply") or "",
        status=result.get("status") or "ok",
        tool_trace=result.get("tool_trace") or [],
        lines_applied=result.get("lines_applied") or [],
        proposals_updated=result.get("proposals_updated") or [],
    )

@router.post("/{job_id}/generate")
def generate(
    job_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    job = db.query(Job).filter(Job.id == job_id, Job.owner_id == user.id).first()
    if not job:
        raise HTTPException(404, "Job não encontrado")
    try:
        path = generate_docx(db, job)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "path": str(path)}


@router.get("/{job_id}/download")
def download(
    job_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    job = db.query(Job).filter(Job.id == job_id, Job.owner_id == user.id).first()
    if not job or not job.output_docx_path:
        raise HTTPException(404, "Arquivo não gerado")
    path = Path(job.output_docx_path)
    if not path.exists():
        raise HTTPException(404, "Arquivo ausente no disco")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=path.name,
    )
