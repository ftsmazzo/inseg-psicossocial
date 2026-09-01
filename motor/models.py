from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class LineStatus(str, Enum):
    DEFINITIVO = "Definitivo"
    PRELIMINAR = "Preliminar"
    PROPOSTA = "Proposta"
    SUPRIMIDO_ANONIMATO = "SUPRIMIDO_ANONIMATO"


@dataclass
class DimensionScore:
    name: str
    tipo: str  # Positiva | Negativa
    media: float
    maxima: float
    pct: float


@dataclass
class QuestionScore:
    text: str
    dimensao: str
    media: float
    pct: float


@dataclass
class SliceScore:
    setor: str
    cargo: str | None
    n: int
    ssos: float
    classificacao: str
    controle_pct: float | None = None
    demanda_pct: float | None = None
    esforco_pct: float | None = None
    recompensa_pct: float | None = None


@dataclass
class CampaignData:
    empresa: str
    cnpj: str
    campanha: str
    periodo: str
    ssos_pct: float
    ssos_classificacao: str
    ssos_texto: str
    n_participantes: int
    dimensoes: list[DimensionScore] = field(default_factory=list)
    perguntas: list[QuestionScore] = field(default_factory=list)
    por_setor: list[SliceScore] = field(default_factory=list)
    por_cargo: list[SliceScore] = field(default_factory=list)
    source_file: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AprhoCell:
    categoria: str
    agente: str
    exposicao: str
    causa_fonte: str
    trajetoria: str
    danos: str
    grau_exposicao: str
    grau_efeito: str
    potencial: str
    controles: str
    row_index: int


@dataclass
class GheBlock:
    numero: str
    nome: str
    setor: str
    funcoes: list[str]
    atividade: str
    ambiente: str
    aprho_table_index: int
    psico_row: AprhoCell | None
    all_categories: list[str] = field(default_factory=list)


@dataclass
class PgrModel:
    source_file: str
    razao_social: str
    cnpj: str
    ghes: list[GheBlock]
    # matriz[ge][ges] -> potencial text; ge/ges are 1..5
    matriz: dict[int, dict[int, str]]
    grau_exposicao_desc: dict[int, str]
    grau_efeito_desc: dict[int, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "razao_social": self.razao_social,
            "cnpj": self.cnpj,
            "n_ghes": len(self.ghes),
            "ghes": [asdict(g) for g in self.ghes],
            "matriz": {str(k): {str(kk): vv for kk, vv in v.items()} for k, v in self.matriz.items()},
        }


@dataclass
class ProposedLine:
    ghe_numero: str
    ghe_nome: str
    setor_pgr: str
    funcoes: list[str]
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
    evidencias: list[str]
    status: LineStatus
    hazard_id: str
    match_score: float
    matched_from: str
    n_respondentes: int
    action: str  # update_existing | insert_after_psico | skip
    aprho_table_index: int
    psico_row_index: int | None
    plano_acao: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class ProposalBundle:
    campaign: CampaignData
    pgr: PgrModel
    lines: list[ProposedLine]
    unmatched_cargos: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaign": self.campaign.to_dict(),
            "pgr_summary": {
                "source_file": self.pgr.source_file,
                "razao_social": self.pgr.razao_social,
                "cnpj": self.pgr.cnpj,
                "n_ghes": len(self.pgr.ghes),
            },
            "lines": [ln.to_dict() for ln in self.lines],
            "unmatched_cargos": self.unmatched_cargos,
            "notes": self.notes,
        }
