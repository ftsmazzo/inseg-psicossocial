from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    Float,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class JobStatus(str, enum.Enum):
    draft = "draft"
    processing = "processing"
    review = "review"
    ready = "ready"
    failed = "failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    jobs: Mapped[list["Job"]] = relationship(back_populates="owner")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.draft)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    empresa: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cnpj: Mapped[str | None] = mapped_column(String(32), nullable=True)
    campanha_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pgr_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    output_docx_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    proposal_json_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    owner: Mapped[User] = relationship(back_populates="jobs")
    lines: Mapped[list["JobLine"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class JobLine(Base):
    __tablename__ = "job_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    ghe_numero: Mapped[str] = mapped_column(String(16))
    ghe_nome: Mapped[str] = mapped_column(String(500))
    setor_pgr: Mapped[str | None] = mapped_column(String(255), nullable=True)
    categoria: Mapped[str] = mapped_column(String(120), default="Ergonômico (Psicossocial)")
    agente: Mapped[str] = mapped_column(Text)
    exposicao: Mapped[str] = mapped_column(Text)
    causa_fonte: Mapped[str] = mapped_column(Text)
    trajetoria: Mapped[str] = mapped_column(Text)
    danos: Mapped[str] = mapped_column(Text)
    grau_exposicao: Mapped[int] = mapped_column(Integer)
    grau_efeito: Mapped[int] = mapped_column(Integer)
    potencial: Mapped[str] = mapped_column(String(64))
    controles: Mapped[str] = mapped_column(Text)
    evidencias_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(64))
    hazard_id: Mapped[str] = mapped_column(String(255))
    match_score: Mapped[float] = mapped_column(Float, default=0)
    matched_from: Mapped[str | None] = mapped_column(String(255), nullable=True)
    n_respondentes: Mapped[int] = mapped_column(Integer, default=0)
    action: Mapped[str] = mapped_column(String(64))
    aprho_table_index: Mapped[int] = mapped_column(Integer)
    psico_row_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    plano_acao: Mapped[str | None] = mapped_column(Text, nullable=True)
    motor_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    prioridade_acao: Mapped[str | None] = mapped_column(String(8), nullable=True)
    accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    discarded: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)

    job: Mapped["Job"] = relationship(back_populates="lines")


class ApprovedSnippet(Base):
    """Memória do dialeto Inseg — linhas aceitas viram exemplos para o agente."""

    __tablename__ = "approved_snippets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_hint: Mapped[str] = mapped_column(String(255), default="")
    setor_hint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    agente: Mapped[str] = mapped_column(Text)
    causa_fonte: Mapped[str] = mapped_column(Text)
    controles: Mapped[str] = mapped_column(Text)
    trajetoria: Mapped[str | None] = mapped_column(Text, nullable=True)
    danos: Mapped[str | None] = mapped_column(Text, nullable=True)
    hazard_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_line_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)