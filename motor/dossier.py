"""Dossiê mastigado por GHE — contexto assertivo para o orquestrador."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from motor.hazards import (
    detect_hazards,
    rank_hazards_for_ghe,
    soft_hazards_from_dimensions,
)
from motor.dossier_insights import (
    compute_missing_information,
    compute_pattern_alerts,
    compute_protective_signals,
)
from motor.match_ghe import aggregate_n, slices_for_ghe
from motor.models import CampaignData, PgrModel, QuestionScore
from motor.textutil import normalize

MIN_ANONIMATO = 5


@dataclass
class GheDossier:
    ghe_numero: str
    ghe_nome: str
    setor: str
    funcoes: list[str]
    atividade_resumo: str
    ambiente: str
    n_respondentes: int
    anonimato_ok: bool
    ssos_slices: list[dict[str, Any]]
    dimensoes_campanha: list[dict[str, Any]]
    perguntas_criticas: list[dict[str, Any]]
    hazards_candidatos: list[dict[str, Any]]
    linha_psico_atual: dict[str, Any] | None
    ge_preservar: int | None
    ges_preservar: int | None
    match_info: str
    match_score: float
    campanha_meta: dict[str, Any]
    # forte | moderada | fraca | insuficiente — Guia MTE: não inventar sem evidência
    evidencia_nivel: str = "moderada"
    pattern_alerts: list[dict[str, Any]] = field(default_factory=list)
    protective_signals: list[dict[str, Any]] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class JobDossiers:
    campaign_meta: dict[str, Any]
    dossiers: list[GheDossier] = field(default_factory=list)

    def by_numero(self, numero: str) -> GheDossier | None:
        key = str(numero).strip().zfill(2) if str(numero).isdigit() else str(numero)
        for d in self.dossiers:
            if d.ghe_numero == str(numero) or d.ghe_numero == key:
                return d
            if d.ghe_numero.lstrip("0") == str(numero).lstrip("0"):
                return d
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaign_meta": self.campaign_meta,
            "dossiers": [d.to_dict() for d in self.dossiers],
        }


def _atividade_resumo(atividade: str, limit: int = 320) -> str:
    t = (atividade or "").strip().replace("\n", " ")
    t = " ".join(t.split())
    return t[:limit]


def _parse_ge_ges(existing) -> tuple[int | None, int | None]:
    if not existing:
        return None, None
    try:
        ge = int(str(existing.grau_exposicao).strip()[0])
        ges = int(str(existing.grau_efeito).strip()[0])
        if 1 <= ge <= 5 and 1 <= ges <= 5:
            return ge, ges
    except (ValueError, IndexError, TypeError, AttributeError):
        pass
    return None, None


def _token_setor_match(a: str, b: str) -> bool:
    from motor.textutil import token_overlap

    return token_overlap(a, b) >= 0.5


def _critical_questions(
    campaign: CampaignData, hazards_found: list
) -> list[QuestionScore]:
    qs: list[QuestionScore] = []
    seen: set[str] = set()
    for _h, matched, _sev in hazards_found:
        for q in matched:
            key = normalize(q.text)
            if key not in seen:
                seen.add(key)
                qs.append(q)
    if not qs:
        scored = sorted(
            campaign.perguntas,
            key=lambda q: (
                q.pct if q.dimensao.upper() in {"CONTROLE", "RECOMPENSA"} else -q.pct
            ),
        )
        qs = scored[:8]
    return qs[:8]


def _evidencia_nivel(
    *,
    n: int,
    has_slice: bool,
    from_questions: bool,
    soft_only: bool,
) -> str:
    if soft_only or not from_questions:
        return "insuficiente" if soft_only else "fraca"
    if n >= MIN_ANONIMATO and has_slice:
        return "forte"
    if n >= MIN_ANONIMATO or has_slice:
        return "moderada"
    return "fraca"


def build_dossiers(campaign: CampaignData, pgr: PgrModel) -> JobDossiers:
    company_hazards = detect_hazards(campaign.perguntas)
    dimensoes = [
        {"nome": d.name, "tipo": d.tipo, "pct": d.pct, "media": d.media}
        for d in campaign.dimensoes
    ]
    soft = soft_hazards_from_dimensions(dimensoes) if not company_hazards else []

    meta = {
        "empresa": campaign.empresa,
        "cnpj": campaign.cnpj,
        "campanha": campaign.campanha,
        "periodo": campaign.periodo,
        "ssos_pct": campaign.ssos_pct,
        "ssos_classificacao": campaign.ssos_classificacao,
        "n_participantes": campaign.n_participantes,
        "metodologia": "Campanha CST (questionário) — evidência, não grau PGR",
        "fonte_normativa": "Guia MTE FRPRT / NR-1",
    }

    out: list[GheDossier] = []
    for ghe in pgr.ghes:
        hits = slices_for_ghe(ghe, campaign)
        slice_list = [h[0] for h in hits]
        n = aggregate_n(slice_list) if slice_list else 0
        if not slice_list:
            for s in campaign.por_setor:
                if _token_setor_match(s.setor, ghe.setor) or _token_setor_match(
                    s.setor, ghe.nome
                ):
                    slice_list.append(s)
                    n += s.n

        slice_dims = [
            {
                "demanda_pct": getattr(s, "demanda_pct", None),
                "esforco_pct": getattr(s, "esforco_pct", None),
                "controle_pct": getattr(s, "controle_pct", None),
                "recompensa_pct": getattr(s, "recompensa_pct", None),
            }
            for s in slice_list[:5]
        ]

        soft_only = False
        if company_hazards:
            selected = rank_hazards_for_ghe(
                company_hazards,
                ghe_nome=ghe.nome,
                setor=ghe.setor,
                atividade=ghe.atividade or "",
                funcoes=list(ghe.funcoes or []),
                slice_dims=slice_dims,
                limit=3,
            )
            from_questions = True
        elif soft:
            selected = rank_hazards_for_ghe(
                soft,
                ghe_nome=ghe.nome,
                setor=ghe.setor,
                atividade=ghe.atividade or "",
                funcoes=list(ghe.funcoes or []),
                slice_dims=slice_dims,
                limit=2,
            )
            from_questions = False
            soft_only = True
        else:
            selected = []
            from_questions = False
            soft_only = True

        evid_nivel = _evidencia_nivel(
            n=n,
            has_slice=bool(slice_list),
            from_questions=from_questions and bool(selected),
            soft_only=soft_only or not selected,
        )

        hazards_payload = [
            {
                "id": h.id,
                "codigo_mte": h.codigo_mte,
                "agente_frag": h.agente_frag,
                "causa_frag": h.causa_frag,
                "controle_frag": h.controle_frag,
                "severity": round(sev, 1),
                "perguntas": [
                    {"dimensao": q.dimensao, "pct": q.pct, "text": q.text} for q in qs[:4]
                ],
            }
            for h, qs, sev in selected
        ]
        crit = _critical_questions(campaign, selected or company_hazards[:1] or soft[:1])
        ge, ges = _parse_ge_ges(ghe.psico_row)
        existing = None
        if ghe.psico_row:
            r = ghe.psico_row
            existing = {
                "agente": r.agente,
                "exposicao": r.exposicao,
                "causa_fonte": r.causa_fonte,
                "trajetoria": r.trajetoria,
                "danos": r.danos,
                "controles": r.controles,
                "grau_exposicao": r.grau_exposicao,
                "grau_efeito": r.grau_efeito,
                "potencial": r.potencial,
            }

        match_info = hits[0][2] if hits else "agregado_campanha"
        if evid_nivel in {"fraca", "insuficiente"}:
            match_info = f"{match_info}|evidencia_{evid_nivel}"

        pattern_alerts = compute_pattern_alerts(slice_dims)
        protective_signals = compute_protective_signals(slice_dims)
        missing_information = compute_missing_information(
            n_respondentes=n,
            anonimato_ok=n >= MIN_ANONIMATO,
            atividade_resumo=_atividade_resumo(ghe.atividade),
            has_slice=bool(slice_list),
            hazards_candidatos=hazards_payload,
            evidencia_nivel=evid_nivel,
            soft_only=soft_only or not selected,
        )

        out.append(
            GheDossier(
                ghe_numero=ghe.numero,
                ghe_nome=ghe.nome,
                setor=ghe.setor,
                funcoes=list(ghe.funcoes or []),
                atividade_resumo=_atividade_resumo(ghe.atividade),
                ambiente=(ghe.ambiente or "")[:200],
                n_respondentes=n,
                anonimato_ok=n >= MIN_ANONIMATO,
                ssos_slices=[
                    {
                        "setor": s.setor,
                        "cargo": s.cargo,
                        "n": s.n,
                        "ssos": s.ssos,
                        "classificacao": s.classificacao,
                        "controle_pct": s.controle_pct,
                        "demanda_pct": s.demanda_pct,
                        "esforco_pct": s.esforco_pct,
                        "recompensa_pct": s.recompensa_pct,
                    }
                    for s in slice_list[:5]
                ],
                dimensoes_campanha=dimensoes,
                perguntas_criticas=[
                    {"dimensao": q.dimensao, "pct": q.pct, "text": q.text} for q in crit
                ],
                hazards_candidatos=hazards_payload,
                linha_psico_atual=existing,
                ge_preservar=ge,
                ges_preservar=ges,
                match_info=match_info,
                match_score=hits[0][1] if hits else 0.0,
                campanha_meta=meta,
                evidencia_nivel=evid_nivel,
                pattern_alerts=pattern_alerts,
                protective_signals=protective_signals,
                missing_information=missing_information,
            )
        )

    return JobDossiers(campaign_meta=meta, dossiers=out)


def list_ghe_summaries(job: JobDossiers) -> list[dict[str, Any]]:
    return [
        {
            "ghe_numero": d.ghe_numero,
            "ghe_nome": d.ghe_nome,
            "setor": d.setor,
            "n": d.n_respondentes,
            "anonimato_ok": d.anonimato_ok,
            "evidencia_nivel": d.evidencia_nivel,
            "hazards": [h["id"] for h in d.hazards_candidatos],
            "codigos_mte": [h.get("codigo_mte") for h in d.hazards_candidatos if h.get("codigo_mte")],
            "pattern_alerts": [a.get("type") for a in d.pattern_alerts],
            "missing": d.missing_information[:3],
        }
        for d in job.dossiers
    ]
