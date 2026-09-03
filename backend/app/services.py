from __future__ import annotations

import json
import logging
import shutil
import sys
import threading
from pathlib import Path

from sqlalchemy.orm import Session

log = logging.getLogger("inseg.process")

# Evita duas threads processando o mesmo job (travava no GHE 39).
_job_processing: set[int] = set()
_job_processing_guard = threading.Lock()

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from motor.parse_pgr import lookup_potencial  # noqa: E402
from motor.pipeline import run_pipeline  # noqa: E402

from app.config import get_settings
from app.models_db import ApprovedSnippet, Job, JobLine, JobStatus

settings = get_settings()


def job_dir(job_id: int) -> Path:
    d = Path(settings.data_dir) / "jobs" / str(job_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def delete_job(db: Session, job: Job) -> None:
    """Remove job, linhas (cascade) e pasta de arquivos."""
    job_id = job.id
    db.delete(job)
    db.commit()
    folder = Path(settings.data_dir) / "jobs" / str(job_id)
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)


def list_approved_snippets(db: Session, limit: int = 40) -> list[dict]:
    rows = (
        db.query(ApprovedSnippet)
        .order_by(ApprovedSnippet.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "role_hint": r.role_hint,
            "setor_hint": r.setor_hint,
            "agente": r.agente,
            "causa_fonte": r.causa_fonte,
            "controles": r.controles,
            "trajetoria": r.trajetoria,
            "danos": r.danos,
            "hazard_id": r.hazard_id,
        }
        for r in rows
    ]


def save_approved_snippet(db: Session, job: Job, line: JobLine) -> ApprovedSnippet | None:
    from motor.llm import is_generic_field
    from motor.hazards import is_generic_agente

    if is_generic_agente(line.agente) or is_generic_field(line.causa_fonte, "causa"):
        return None
    if is_generic_field(line.controles, "controle"):
        return None

    # avoid near-duplicates
    existing = (
        db.query(ApprovedSnippet)
        .filter(
            ApprovedSnippet.causa_fonte == line.causa_fonte,
            ApprovedSnippet.controles == line.controles,
        )
        .first()
    )
    if existing:
        return existing

    row = ApprovedSnippet(
        role_hint=(line.ghe_nome or "")[:255],
        setor_hint=line.setor_pgr,
        agente=line.agente,
        causa_fonte=line.causa_fonte,
        controles=line.controles,
        trajetoria=line.trajetoria,
        danos=line.danos,
        hazard_id=line.hazard_id,
        source_job_id=job.id,
        source_line_id=line.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def save_upload(job_id: int, kind: str, filename: str, data: bytes) -> Path:
    dest = job_dir(job_id) / f"{kind}_{filename}"
    dest.write_bytes(data)
    return dest


def _upsert_job_line(db: Session, job_id: int, ln: dict) -> JobLine:
    row = (
        db.query(JobLine)
        .filter(JobLine.job_id == job_id, JobLine.ghe_numero == ln["ghe_numero"])
        .first()
    )
    fields = dict(
        ghe_nome=ln["ghe_nome"],
        setor_pgr=ln.get("setor_pgr"),
        categoria=ln.get("categoria") or "Ergonômico (Psicossocial)",
        agente=ln["agente"],
        exposicao=ln["exposicao"],
        causa_fonte=ln["causa_fonte"],
        trajetoria=ln["trajetoria"],
        danos=ln["danos"],
        grau_exposicao=ln["grau_exposicao"],
        grau_efeito=ln["grau_efeito"],
        potencial=ln["potencial"],
        controles=ln["controles"],
        evidencias_json=ln.get("evidencias"),
        status=ln["status"],
        hazard_id=ln["hazard_id"],
        match_score=ln.get("match_score") or 0,
        matched_from=ln.get("matched_from"),
        n_respondentes=ln.get("n_respondentes") or 0,
        action=ln.get("action") or "update_existing",
        aprho_table_index=ln["aprho_table_index"],
        psico_row_index=ln.get("psico_row_index"),
        plano_acao=ln.get("plano_acao"),
        motor_rationale=ln.get("motor_rationale"),
        prioridade_acao=ln.get("prioridade_acao"),
        accepted=ln.get("status") == "Definitivo",
        discarded=False,
        needs_review=ln.get("status") in ("Preliminar", "Proposta")
        or ln.get("prioridade_acao") == "1",
    )
    if row is None:
        row = JobLine(job_id=job_id, ghe_numero=ln["ghe_numero"], **fields)
        db.add(row)
    else:
        for k, v in fields.items():
            setattr(row, k, v)
        db.add(row)
    return row


def write_progress(
    job_id: int,
    *,
    done: int,
    total: int,
    ghe: str = "",
    message: str = "",
    phase: str = "filling",
) -> dict:
    out = job_dir(job_id) / "out"
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "done": int(done),
        "total": max(int(total), 1),
        "pct": round(100.0 * int(done) / max(int(total), 1), 1),
        "ghe": ghe,
        "message": message,
        "phase": phase,
    }
    (out / "progress.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    return payload


def read_progress(job_id: int) -> dict | None:
    path = job_dir(job_id) / "out" / "progress.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _try_acquire_job_processing(job_id: int) -> bool:
    with _job_processing_guard:
        if job_id in _job_processing:
            return False
        _job_processing.add(job_id)
        return True


def _release_job_processing(job_id: int) -> None:
    with _job_processing_guard:
        _job_processing.discard(job_id)


def process_job_background(job_id: int) -> None:
    """Roda em thread separada — não bloqueia o worker HTTP."""
    from app.db import SessionLocal

    if not _try_acquire_job_processing(job_id):
        log.warning("job_id=%s já em processamento — thread duplicada ignorada", job_id)
        return
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return
        process_job(db, job)
    except Exception as exc:  # noqa: BLE001
        log.exception("process_job_background falhou job_id=%s: %s", job_id, exc)
    finally:
        db.close()
        _release_job_processing(job_id)


def _processing_stale(job: Job, *, minutes: int = 2) -> bool:
    """True se processing parou de atualizar (worker morto ou travado)."""
    from datetime import datetime, timedelta

    if job.status != JobStatus.processing:
        return False
    updated = job.updated_at
    if not updated:
        return True
    if updated.tzinfo is not None:
        updated = updated.replace(tzinfo=None)
    return datetime.utcnow() - updated > timedelta(minutes=minutes)


def process_job(db: Session, job: Job, *, force_full: bool = False) -> Job:
    from app.config import export_llm_env
    from app.db import SessionLocal
    from motor.models import ProposedLine
    from motor.propose import batch_llm_enabled

    export_llm_env()
    if not job.campanha_path or not job.pgr_path:
        raise ValueError("Campanha PDF e PGR DOCX são obrigatórios")

    existing_lines = db.query(JobLine).filter(JobLine.job_id == job.id).all()
    partial_msg = (job.error_message or "")
    prog = read_progress(job.id)
    prog_total = int(prog.get("total") or 0) if prog else 0
    partial_incomplete = (
        job.status == JobStatus.review
        and len(existing_lines) > 0
        and prog_total > len(existing_lines)
    )
    resume = (
        not force_full
        and len(existing_lines) > 0
        and (
            job.status in {JobStatus.processing, JobStatus.failed}
            or partial_incomplete
            or (
                job.status == JobStatus.review
                and (
                    "Parcial salvo" in partial_msg
                    or "Processamento interrompido" in partial_msg
                )
            )
        )
    )
    skip: set[str] = set()
    if resume:
        skip = {ln.ghe_numero for ln in existing_lines}
    else:
        db.query(JobLine).filter(JobLine.job_id == job.id).delete()
        db.commit()

    job.status = JobStatus.processing
    job.error_message = None
    job.notes_json = [
        f"Processando… resume={resume}, já salvos={len(skip)} GHE(s).",
        f"Motor batch_llm={batch_llm_enabled()} (False = rápido, sem OpenRouter).",
    ]
    db.add(job)
    db.commit()

    out = job_dir(job.id) / "out"
    out.mkdir(parents=True, exist_ok=True)
    checkpoint_path = out / "checkpoint.jsonl"
    write_progress(
        job.id,
        done=len(skip),
        total=max(len(skip), 1),
        message="Extraindo campanha e PGR…",
        phase="parse",
    )

    def on_progress(ghe_num: str, ghe_nome: str, done: int, total: int) -> None:
        s = SessionLocal()
        try:
            j = s.query(Job).filter(Job.id == job.id).first()
            if j:
                j.notes_json = [
                    f"Processando GHE {ghe_num} ({done + 1}/{total})…",
                    f"resume_skip={len(skip)}",
                ]
                s.add(j)
                s.commit()
        finally:
            s.close()
        write_progress(
            job.id,
            done=done,
            total=total,
            ghe=f"{ghe_num} · {ghe_nome[:48]}",
            message=f"Processando GHE {ghe_num} ({done + 1}/{total})…",
            phase="filling",
        )

    def on_line(line: ProposedLine, done: int, total: int) -> None:
        payload = line.to_dict()
        s = SessionLocal()
        try:
            _upsert_job_line(s, job.id, payload)
            with checkpoint_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
            j = s.query(Job).filter(Job.id == job.id).first()
            if j:
                j.notes_json = [
                    f"Checkpoint {done}/{total} — GHE {line.ghe_numero} salvo.",
                    f"resume_skip={len(skip)}",
                ]
                s.add(j)
                s.commit()
        finally:
            s.close()
        write_progress(
            job.id,
            done=done,
            total=total,
            ghe=f"{line.ghe_numero} · {line.ghe_nome[:48]}",
            message=f"Redigindo GHE {line.ghe_numero} ({done}/{total})",
            phase="filling",
        )

    try:
        snippets = list_approved_snippets(db)
        if not resume and checkpoint_path.exists():
            checkpoint_path.unlink()

        result = run_pipeline(
            job.campanha_path,
            job.pgr_path,
            out,
            write_docx=False,
            approved_snippets=snippets,
            skip_ghe_numeros=skip or None,
            on_line=on_line,
            on_progress=on_progress,
        )
        proposal = json.loads(Path(result["proposal_json"]).read_text(encoding="utf-8"))

        camp = proposal.get("campaign", {})
        job.empresa = camp.get("empresa") or job.empresa
        job.cnpj = camp.get("cnpj") or job.cnpj
        if camp.get("empresa"):
            job.title = job.title or camp["empresa"]
            if str(job.title).startswith("Job "):
                job.title = camp["empresa"][:255]

        total_lines = db.query(JobLine).filter(JobLine.job_id == job.id).count()
        notes = list(proposal.get("notes") or [])
        notes.append(f"Total no banco após processar: {total_lines} linha(s).")
        job.notes_json = notes
        job.proposal_json_path = result["proposal_json"]
        job.status = JobStatus.review
        db.add(job)
        db.commit()
        write_progress(
            job.id,
            done=total_lines,
            total=total_lines or 1,
            message="Concluído — pronto para revisão",
            phase="done",
        )
        db.refresh(job)
        return job
    except BaseException as exc:  # noqa: BLE001
        saved = db.query(JobLine).filter(JobLine.job_id == job.id).count()
        job.status = JobStatus.failed if saved == 0 else JobStatus.review
        job.error_message = (
            f"{exc} | Parcial salvo: {saved} GHE(s). Use Reprocessar para continuar (resume)."
        )
        notes = list(job.notes_json or [])
        notes.append(job.error_message)
        job.notes_json = notes
        db.add(job)
        db.commit()
        prog = read_progress(job.id) or {}
        total = max(int(prog.get("total") or 0), saved, 1)
        write_progress(
            job.id,
            done=saved,
            total=total,
            message=f"Interrompido — {saved}/{total} GHE(s) salvos",
            phase="stopped",
        )
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise


def build_agent_context(db: Session, job: Job):
    from motor.agent_tools import AgentJobContext
    from motor.dossier import JobDossiers, GheDossier

    dossiers_path = job_dir(job.id) / "out" / "dossiers.json"
    if not dossiers_path.exists():
        raise ValueError("Dossiês ausentes — reprocesse o job")

    raw = json.loads(dossiers_path.read_text(encoding="utf-8"))
    dossiers = JobDossiers(
        campaign_meta=raw.get("campaign_meta") or {},
        dossiers=[GheDossier(**d) for d in raw.get("dossiers") or []],
    )
    ctx = AgentJobContext(
        dossiers=dossiers,
        approved_snippets=list_approved_snippets(db),
    )
    for ln in db.query(JobLine).filter(JobLine.job_id == job.id).all():
        ctx.line_overrides[ln.ghe_numero] = {
            "agente": ln.agente,
            "exposicao": ln.exposicao,
            "causa_fonte": ln.causa_fonte,
            "trajetoria": ln.trajetoria,
            "danos": ln.danos,
            "controles": ln.controles,
        }
        ctx.proposals[ln.ghe_numero] = dict(ctx.line_overrides[ln.ghe_numero])
    return ctx


def chat_job(
    db: Session,
    job: Job,
    message: str,
    history: list[dict] | None = None,
    *,
    ghe_numero: str | None = None,
) -> dict:
    from app.config import export_llm_env
    from motor.chat_agent import run_job_chat

    export_llm_env()
    ctx = build_agent_context(db, job)

    line = None
    screen_context = None
    if ghe_numero:
        line = (
            db.query(JobLine)
            .filter(JobLine.job_id == job.id, JobLine.ghe_numero == ghe_numero)
            .first()
        )
        if not line:
            for ln in db.query(JobLine).filter(JobLine.job_id == job.id).all():
                if ln.ghe_numero.lstrip("0") == str(ghe_numero).lstrip("0"):
                    line = ln
                    break
        if line:
            from motor.chat_screen import build_screen_context

            screen_context = build_screen_context(line)

    result = run_job_chat(ctx, message, history=history, screen_context=screen_context)

    # apply propose_line updates to DB lines
    from motor.hazards import is_generic_agente, is_job_title_agente
    from motor.llm import is_robotic_danos

    applied = []
    for ghe_num, fields in (result.get("proposals") or {}).items():
        line = (
            db.query(JobLine)
            .filter(JobLine.job_id == job.id, JobLine.ghe_numero == ghe_num)
            .first()
        )
        if not line:
            # soft match
            for ln in db.query(JobLine).filter(JobLine.job_id == job.id).all():
                if ln.ghe_numero.lstrip("0") == str(ghe_num).lstrip("0"):
                    line = ln
                    break
        if not line:
            continue
        if fields.get("danos") and is_robotic_danos(fields["danos"]):
            fields = dict(fields)
            fields.pop("danos", None)
        if fields.get("agente") and (
            is_job_title_agente(fields["agente"]) or is_generic_agente(fields["agente"])
        ):
            fields = dict(fields)
            fields.pop("agente", None)
        for k in ("agente", "exposicao", "causa_fonte", "trajetoria", "danos", "controles"):
            if fields.get(k):
                setattr(line, k, fields[k])
        line.exposicao = "Habitual e Intermitente"
        line.accepted = False
        line.discarded = False
        line.status = "Proposta"
        line.needs_review = False
        recalculate_potencial(line)
        evid = list(line.evidencias_json or [])
        evid.append("Atualizado via chat do job")
        line.evidencias_json = evid
        db.add(line)
        applied.append(line.ghe_numero)
    if applied:
        db.commit()
    result["lines_applied"] = applied
    return result


def recalculate_potencial(line: JobLine) -> None:
    line.potencial = lookup_potencial(line.grau_exposicao, line.grau_efeito)


def revalidate_job_lines(db: Session, job: Job) -> list[str]:
    """Audita danos clínicos/robóticos sem reprocessar LLM. Marca needs_review."""
    from motor.llm import is_robotic_danos

    affected: list[str] = []
    reason = (
        "AUDITORIA: danos clínico/robótico (Burnout/Depressão/CID ou trio genérico) — "
        "revisar manualmente ou editar a linha"
    )
    for line in db.query(JobLine).filter(JobLine.job_id == job.id).all():
        if not is_robotic_danos(line.danos or ""):
            if line.needs_review:
                line.needs_review = False
                db.add(line)
            continue
        line.needs_review = True
        evid = list(line.evidencias_json or [])
        if reason not in evid:
            evid.append(reason)
        line.evidencias_json = evid
        db.add(line)
        affected.append(line.ghe_numero)
    db.commit()
    return affected


def original_docx_path(job_id: int) -> Path:
    return job_dir(job_id) / "out" / f"PGR-{job_id}-original.docx"


def generate_docx(
    db: Session,
    job: Job,
    *,
    include_narratives: bool = True,
    include_cronogram: bool = True,
    output_suffix: str = "psicossocial",
    update_job_output: bool = True,
) -> Path:
    from motor.models import LineStatus, ProposedLine
    from motor.write_pgr import apply_lines_to_pgr

    if not job.pgr_path:
        raise ValueError("PGR de origem ausente")

    lines_db = (
        db.query(JobLine)
        .filter(JobLine.job_id == job.id, JobLine.discarded.is_(False), JobLine.accepted.is_(True))
        .all()
    )
    if not lines_db:
        lines_db = (
            db.query(JobLine)
            .filter(JobLine.job_id == job.id, JobLine.discarded.is_(False))
            .all()
        )

    proposed: list[ProposedLine] = []
    for ln in lines_db:
        try:
            status = LineStatus(ln.status)
        except ValueError:
            status = LineStatus.PROPOSTA
        proposed.append(
            ProposedLine(
                ghe_numero=ln.ghe_numero,
                ghe_nome=ln.ghe_nome,
                setor_pgr=ln.setor_pgr or "",
                funcoes=[],
                categoria=ln.categoria,
                agente=ln.agente,
                exposicao=ln.exposicao,
                causa_fonte=ln.causa_fonte,
                trajetoria=ln.trajetoria,
                danos=ln.danos,
                grau_exposicao=ln.grau_exposicao,
                grau_efeito=ln.grau_efeito,
                potencial=ln.potencial,
                controles=ln.controles,
                evidencias=ln.evidencias_json or [],
                status=status,
                hazard_id=ln.hazard_id,
                match_score=ln.match_score,
                matched_from=ln.matched_from or "",
                n_respondentes=ln.n_respondentes,
                action=ln.action,
                aprho_table_index=ln.aprho_table_index,
                psico_row_index=ln.psico_row_index,
                plano_acao=ln.plano_acao or "",
                motor_rationale=ln.motor_rationale or "",
                prioridade_acao=ln.prioridade_acao or "",
            )
        )

    out_path = job_dir(job.id) / "out" / f"PGR-{job.id}-{output_suffix}.docx"
    apply_lines_to_pgr(
        job.pgr_path,
        out_path,
        proposed,
        only_accepted=False,
        include_narratives=include_narratives,
        include_cronogram=include_cronogram,
    )
    if update_job_output:
        job.output_docx_path = str(out_path)
        job.status = JobStatus.ready
        db.add(job)
        db.commit()
    return out_path


def generate_docx_original(db: Session, job: Job) -> Path:
    """Só linhas APRHO — sem narrativas nem cronograma (PGR original + tabelas psico)."""
    return generate_docx(
        db,
        job,
        include_narratives=False,
        include_cronogram=False,
        output_suffix="original",
        update_job_output=True,
    )
