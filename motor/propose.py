from __future__ import annotations

import gc
import logging
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

from motor.agent_tools import AgentJobContext
from motor.dossier import JobDossiers, build_dossiers
from motor.hazards import (
    is_generic_agente,
    is_job_title_agente,
    join_frags,
    HAZARDS,
)
from motor.llm import is_generic_field, is_robotic_danos, openrouter_enabled
from motor.match_ghe import match_cargo_to_ghe
from motor.models import (
    CampaignData,
    LineStatus,
    PgrModel,
    ProposedLine,
    ProposalBundle,
)
from motor.orchestrator import draft_from_dossier, orchestrate_ghe, orchestrator_model
from motor.parse_pgr import lookup_potencial
from motor.dossier_insights import build_motor_rationale, compute_prioridade_acao


MIN_ANONIMATO = 5
GHE_ORCHESTRATE_TIMEOUT = 130

logger = logging.getLogger(__name__)

OnLineCb = Callable[[ProposedLine, int, int], None]
OnProgressCb = Callable[[str, str, int, int], None]


def _orchestrate_with_timeout(
    ctx: AgentJobContext,
    dossier,
    *,
    draft: dict[str, str],
    timeout: int = GHE_ORCHESTRATE_TIMEOUT,
) -> tuple[dict[str, str], str]:
    """Evita travar o job inteiro se o LLM não responder."""
    pool = ThreadPoolExecutor(max_workers=1)
    fut = pool.submit(orchestrate_ghe, ctx, dossier, draft=draft)
    try:
        return fut.result(timeout=timeout)
    except FuturesTimeout:
        logger.warning("GHE %s: timeout LLM (%ss)", dossier.ghe_numero, timeout)
        return draft, "orchestrator:timeout"
    except Exception as exc:  # noqa: BLE001
        logger.exception("GHE %s: erro no orquestrador", dossier.ghe_numero)
        return draft, f"orchestrator:error ({str(exc)[:80]})"
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def propose(
    campaign: CampaignData,
    pgr: PgrModel,
    *,
    approved_snippets: list[dict] | None = None,
    skip_ghe_numeros: set[str] | None = None,
    on_line: OnLineCb | None = None,
    on_progress: OnProgressCb | None = None,
) -> tuple[ProposalBundle, JobDossiers]:
    """Uma linha por GHE. on_line após cada GHE (checkpoint). skip = resume."""
    notes: list[str] = []
    unmatched: list[dict] = []
    lines: list[ProposedLine] = []
    skip = {str(x) for x in (skip_ghe_numeros or set())}

    dossiers = build_dossiers(campaign, pgr)
    ctx = AgentJobContext(
        dossiers=dossiers,
        approved_snippets=list(approved_snippets or []),
    )

    orch_ok = orch_retry = orch_fail = skipped_resume = 0
    if openrouter_enabled():
        notes.append(
            f"Motor mecânico (Agente/danos) + LLM {orchestrator_model()} só em causa/controles (skill+RAG)."
        )
    else:
        notes.append("OpenRouter ausente — só motor determinístico.")

    os.environ.pop("OPENROUTER_LAST_ERROR", None)
    matched_cargo_keys: set[str] = set()
    ghe_by_num = {g.numero: g for g in pgr.ghes}
    total = len(dossiers.dossiers)
    processed = 0

    for d in dossiers.dossiers:
        ghe = ghe_by_num.get(d.ghe_numero)
        if not ghe:
            for g in pgr.ghes:
                if g.numero.lstrip("0") == d.ghe_numero.lstrip("0"):
                    ghe = g
                    break
        if not ghe:
            continue

        if ghe.numero in skip or d.ghe_numero in skip:
            skipped_resume += 1
            continue

        processed += 1
        if on_progress is not None:
            on_progress(
                ghe.numero,
                ghe.nome,
                len(lines) + skipped_resume,
                total,
            )

        for sl in d.ssos_slices:
            if sl.get("cargo"):
                matched_cargo_keys.add(f"{sl.get('setor')}|{sl.get('cargo')}")

        evidencias = [
            f"Campanha {campaign.campanha} ({campaign.periodo})",
            f"SSOS geral {campaign.ssos_pct}% ({campaign.ssos_classificacao})",
        ]
        if d.ssos_slices:
            evidencias.append(
                "Recortes: "
                + "; ".join(
                    f"{(s.get('cargo') or s.get('setor'))} n={s.get('n')} "
                    f"SSOS {s.get('ssos')}% ({s.get('classificacao')})"
                    for s in d.ssos_slices[:4]
                )
            )
        for q in d.perguntas_criticas[:5]:
            evidencias.append(f"[{q.get('dimensao')} {q.get('pct')}%] {q.get('text')}")

        try:
            draft = draft_from_dossier(d)
            texts, llm_status = _orchestrate_with_timeout(ctx, d, draft=draft)
        except Exception as exc:  # noqa: BLE001
            logger.exception("GHE %s: falha inesperada — motor local", ghe.numero)
            draft = draft_from_dossier(d)
            texts = draft
            llm_status = f"orchestrator:exception ({str(exc)[:80]})"
            notes.append(f"GHE {ghe.numero}: exceção — {exc}")

        if llm_status == "orchestrator:ok":
            orch_ok += 1
            evidencias.append("Redação: orquestrador OK")
        elif llm_status == "orchestrator:retry_ok":
            orch_retry += 1
            evidencias.append("Redação: orquestrador OK (após retry)")
        elif llm_status == "skipped":
            evidencias.append("Redação: determinística (sem OpenRouter)")
        else:
            orch_fail += 1
            evidencias.append(f"Redação: fallback local ({llm_status[:100]})")

        n = d.n_respondentes
        existing = ghe.psico_row
        severity = 0.0
        if d.hazards_candidatos:
            severity = max(float(h.get("severity") or 0) for h in d.hazards_candidatos)
        ge, ges, ge_source = _resolve_degrees(
            existing, severity, n, d.ge_preservar, d.ges_preservar
        )
        if existing and ge_source.startswith("mantido"):
            potencial = (existing.potencial or "").strip() or lookup_potencial(
                ge, ges, pgr.matriz
            )
        else:
            potencial = lookup_potencial(ge, ges, pgr.matriz)

        if n > 0 and n < MIN_ANONIMATO:
            status = LineStatus.PRELIMINAR
            evidencias.append(f"n={n} < {MIN_ANONIMATO} (anonimato). Linha preliminar.")
        elif n >= MIN_ANONIMATO:
            status = LineStatus.DEFINITIVO
        else:
            status = LineStatus.PROPOSTA
            evidencias.append("Sem recorte cargo/setor casado; baseado no agregado.")

        evid_nivel = getattr(d, "evidencia_nivel", "moderada")
        evidencias.append(
            f"Evidência GHE: {evid_nivel} (Guia MTE — score CST ≠ grau PGR)"
        )
        for h in d.hazards_candidatos[:3]:
            cod = h.get("codigo_mte") or ""
            evidencias.append(f"Fator: {h.get('id')} {f'({cod})' if cod else ''}".strip())
        for alert in getattr(d, "pattern_alerts", [])[:2]:
            evidencias.append(f"Alerta: {alert.get('type')} — {alert.get('message', '')[:120]}")
        for sig in getattr(d, "protective_signals", [])[:1]:
            evidencias.append(f"Proteção: {sig.get('type')} — {sig.get('message', '')[:100]}")
        if getattr(d, "missing_information", None):
            evidencias.append(
                "Lacunas: " + "; ".join(d.missing_information[:4])
            )
        if evid_nivel in {"fraca", "insuficiente"} or not d.hazards_candidatos:
            status = LineStatus.PRELIMINAR
            evidencias.append(
                "INFORMAÇÃO INSUFICIENTE — REQUER VALIDAÇÃO TÉCNICA "
                "(não inventar fator sem evidência)"
            )
        if llm_status == "orchestrator:evidencia_insuficiente":
            evidencias.append("Redação: motor cauteloso (sem LLM — evidência insuficiente)")

        evidencias.append(f"GE/GES origem: {ge_source}")

        if existing and is_generic_agente(existing.agente):
            notes.append(f"GHE {ghe.numero}: Agente genérico substituido.")
        if existing and is_job_title_agente(existing.agente):
            notes.append(f"GHE {ghe.numero}: Agente do PGR era cargo/função — regenerado como perigo.")

        hazard_ids = "+".join(h["id"] for h in d.hazards_candidatos) or "agregado"

        # Travamento final: Agente NUNCA cargo; Danos NUNCA clínico de consultório
        by_id = {h.id: h for h in HAZARDS}
        hz = [by_id[i] for i in hazard_ids.split("+") if i in by_id]
        agente_final = texts["agente"]
        if (
            is_job_title_agente(agente_final)
            or is_generic_agente(agente_final)
            or not (agente_final or "").strip()
        ):
            if hz:
                agente_final = join_frags([h.agente_frag for h in hz], limit=3)
            else:
                agente_final = draft["agente"]
            evidencias.append("Agente corrigido: era cargo/função → perigo psicossocial")

        danos_final = texts["danos"]
        if is_robotic_danos(danos_final) or not (danos_final or "").strip():
            danos_final = draft["danos"]
            evidencias.append("Danos: corrigidos para agravos SST amarrados ao posto")

        trajetoria_final = texts["trajetoria"] or (
            join_frags([h.trajetoria_frag for h in hz], limit=4) if hz else draft["trajetoria"]
        )

        causa_final = texts["causa_fonte"]
        if is_generic_field(causa_final, "causa"):
            causa_final = draft["causa_fonte"]
            evidencias.append("ALERTA: Causa genérica — usada versão do motor por função")

        controles_final = texts["controles"]
        if is_generic_field(controles_final, "controle"):
            controles_final = draft["controles"]
            evidencias.append("ALERTA: Controles genéricos — usada versão do motor por função")

        if existing:
            action = "update_existing"
            psico_idx = existing.row_index
        else:
            action = "insert_after_psico"
            psico_idx = None
            notes.append(f"GHE {ghe.numero}: sem linha psicossocial — será criada (insert).")

        prioridade = compute_prioridade_acao(
            severity=severity,
            evidencia_nivel=evid_nivel,
            pattern_alerts=getattr(d, "pattern_alerts", []),
            anonimato_ok=d.anonimato_ok,
        )
        rationale = build_motor_rationale(
            ghe_numero=ghe.numero,
            evidencia_nivel=evid_nivel,
            hazards_candidatos=d.hazards_candidatos,
            pattern_alerts=getattr(d, "pattern_alerts", []),
            protective_signals=getattr(d, "protective_signals", []),
            missing_information=getattr(d, "missing_information", []),
            severity=severity,
            ge=ge,
            ges=ges,
            potencial=potencial,
            prioridade_acao=prioridade,
            match_info=d.match_info,
            n_respondentes=n,
        )
        evidencias.append(f"Prioridade de ação: {prioridade} (separada do potencial {potencial})")

        line = ProposedLine(
            ghe_numero=ghe.numero,
            ghe_nome=ghe.nome,
            setor_pgr=ghe.setor,
            funcoes=ghe.funcoes,
            categoria="Ergonômico (Psicossocial)",
            agente=agente_final,
            exposicao=texts["exposicao"],
            causa_fonte=causa_final,
            trajetoria=trajetoria_final,
            danos=danos_final,
            grau_exposicao=ge,
            grau_efeito=ges,
            potencial=potencial,
            controles=controles_final,
            evidencias=evidencias,
            status=status,
            hazard_id=hazard_ids,
            match_score=d.match_score,
            matched_from=d.match_info,
            n_respondentes=n,
            action=action,
            aprho_table_index=ghe.aprho_table_index,
            psico_row_index=psico_idx,
            plano_acao=_plano_acao_curto(agente_final, controles_final),
            motor_rationale=rationale,
            prioridade_acao=prioridade,
        )
        lines.append(line)
        if on_line is not None:
            on_line(line, len(lines) + skipped_resume, total)

        if processed % 10 == 0:
            gc.collect()

    for sl in campaign.por_cargo:
        key = f"{sl.setor}|{sl.cargo}"
        if key not in matched_cargo_keys and sl.cargo:
            g, score, _why = match_cargo_to_ghe(sl.cargo, pgr.ghes, sl.setor)
            if not g:
                unmatched.append(
                    {
                        "setor": sl.setor,
                        "cargo": sl.cargo,
                        "n": sl.n,
                        "ssos": sl.ssos,
                        "classificacao": sl.classificacao,
                        "best_score": score,
                    }
                )

    notes.append(f"Linhas novas nesta rodada: {len(lines)}.")
    notes.append(f"Dossiês: {len(dossiers.dossiers)}.")
    if skipped_resume:
        notes.append(f"Resume: {skipped_resume} GHE(s) já salvos, pulados.")
    if openrouter_enabled():
        notes.append(
            f"Orquestrador: {orch_ok} OK, {orch_retry} retry OK, {orch_fail} fallback(s)."
        )
    return (
        ProposalBundle(
            campaign=campaign,
            pgr=pgr,
            lines=lines,
            unmatched_cargos=unmatched,
            notes=notes,
        ),
        dossiers,
    )


def _resolve_degrees(existing, severity: float, n: int, ge_d, ges_d) -> tuple[int, int, str]:
    if ge_d is not None and ges_d is not None:
        return ge_d, ges_d, "mantido do PGR Inseg (linha psicossocial existente)"
    if existing:
        try:
            ge = int(str(existing.grau_exposicao).strip()[0])
            ges = int(str(existing.grau_efeito).strip()[0])
            if 1 <= ge <= 5 and 1 <= ges <= 5:
                return ge, ges, "mantido do PGR Inseg (linha psicossocial existente)"
        except (ValueError, IndexError, TypeError, AttributeError):
            pass

    ge = 2
    if severity >= 70:
        ge = 4
    elif severity >= 50:
        ge = 3
    if n < MIN_ANONIMATO:
        ge = min(ge, 3)
    return ge, 3, "proposta preliminar (sem GE/GES prévio no PGR)"


def _plano_acao_curto(agente: str, controles: str) -> str:
    return f"Ação: adequar organização do trabalho ({agente}). Medidas: {controles}."
