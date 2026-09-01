from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str
    name: str
    is_admin: bool

    class Config:
        from_attributes = True


class LoginForm(BaseModel):
    email: str
    password: str


class JobCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)


class JobOut(BaseModel):
    id: int
    title: str
    status: str
    empresa: str | None
    cnpj: str | None
    error_message: str | None
    notes_json: list | None
    created_at: datetime
    updated_at: datetime
    lines_count: int = 0
    accepted_count: int = 0
    progress: dict | None = None

    class Config:
        from_attributes = True


class JobLineOut(BaseModel):
    id: int
    ghe_numero: str
    ghe_nome: str
    setor_pgr: str | None
    categoria: str
    agente: str
    exposicao: str
    causa_fonte: str
    trajetoria: str
    danos: str
    grau_exposicao: int
    grau_efeito: int
    potencial: str
    controles: str
    evidencias_json: list | None
    status: str
    hazard_id: str
    match_score: float
    matched_from: str | None
    n_respondentes: int
    action: str
    plano_acao: str | None
    motor_rationale: str | None = None
    prioridade_acao: str | None = None
    accepted: bool
    discarded: bool
    needs_review: bool = False

    class Config:
        from_attributes = True


class JobLineUpdate(BaseModel):
    agente: str | None = None
    exposicao: str | None = None
    causa_fonte: str | None = None
    trajetoria: str | None = None
    danos: str | None = None
    grau_exposicao: int | None = None
    grau_efeito: int | None = None
    controles: str | None = None
    status: str | None = None
    accepted: bool | None = None
    discarded: bool | None = None
    plano_acao: str | None = None


class JobDetailOut(JobOut):
    lines: list[JobLineOut] = []


class ChatMessageIn(BaseModel):
    role: str
    content: str


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[ChatMessageIn] = []
    ghe_numero: str | None = Field(
        default=None,
        description="GHE selecionado na UI — o agente recebe contexto dessa linha",
    )


class ChatOut(BaseModel):
    reply: str
    status: str
    tool_trace: list[str] = []
    lines_applied: list[str] = []
    proposals_updated: list[str] = []
