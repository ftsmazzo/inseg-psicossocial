"""Camada de refinamento do dossiê — alertas, proteção, lacunas, prioridade (sem alterar matriz)."""

from __future__ import annotations

from typing import Any


def _avg_pct(slice_dims: list[dict[str, Any]], key: str) -> float | None:
    vals = [float(s[key]) for s in slice_dims if s.get(key) is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)


def compute_pattern_alerts(slice_dims: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Combinações JCQ-style — alerta contextual, não altera classificação."""
    if not slice_dims:
        return []
    dem = _avg_pct(slice_dims, "demanda_pct")
    ctl = _avg_pct(slice_dims, "controle_pct")
    rec = _avg_pct(slice_dims, "recompensa_pct")
    esf = _avg_pct(slice_dims, "esforco_pct")
    alerts: list[dict[str, str]] = []

    if dem is not None and dem >= 55 and ctl is not None and ctl <= 50:
        if rec is not None and rec <= 50:
            alerts.append(
                {
                    "type": "HIGH_DEMAND_LOW_CONTROL_LOW_SUPPORT",
                    "message": (
                        "Combinação desfavorável: demanda elevada + baixo controle + "
                        "baixo suporte/recompensa — merece análise técnica prioritária."
                    ),
                }
            )
        else:
            alerts.append(
                {
                    "type": "HIGH_DEMAND_LOW_CONTROL",
                    "message": (
                        "Demanda elevada com baixo controle — padrão de alta preocupação "
                        "ocupacional (JCQ)."
                    ),
                }
            )

    if esf is not None and esf >= 55 and dem is not None and dem >= 55:
        alerts.append(
            {
                "type": "HIGH_EFFORT_HIGH_DEMAND",
                "message": "Esforço e demanda elevados simultaneamente no recorte do GHE.",
            }
        )

    return alerts


def compute_protective_signals(slice_dims: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Fatores protetores no recorte — contextualizam, não apagam exposição."""
    if not slice_dims:
        return []
    ctl = _avg_pct(slice_dims, "controle_pct")
    rec = _avg_pct(slice_dims, "recompensa_pct")
    signals: list[dict[str, str]] = []
    if ctl is not None and ctl >= 60:
        signals.append(
            {
                "type": "FAVORABLE_CONTROL",
                "message": f"Controle/autonomia favorável no recorte (média {ctl:.0f}%).",
            }
        )
    if rec is not None and rec >= 60:
        signals.append(
            {
                "type": "FAVORABLE_SUPPORT_REWARD",
                "message": f"Suporte/recompensa favorável no recorte (média {rec:.0f}%).",
            }
        )
    return signals


def compute_missing_information(
    *,
    n_respondentes: int,
    anonimato_ok: bool,
    atividade_resumo: str,
    has_slice: bool,
    hazards_candidatos: list[dict[str, Any]],
    evidencia_nivel: str,
    soft_only: bool,
) -> list[str]:
    """Lista objetiva do que falta — apoio à validação, não bloqueio automático."""
    missing: list[str] = []
    if not has_slice:
        missing.append("recorte da campanha por cargo/setor casado a este GHE")
    if n_respondentes <= 0:
        missing.append("n de respondentes no recorte do GHE")
    elif not anonimato_ok:
        missing.append(f"amostra n={n_respondentes} abaixo do mínimo de anonimato (5)")
    if len((atividade_resumo or "").strip()) < 25:
        missing.append("descrição de atividade/função do GHE no PGR (trabalho real)")
    if not hazards_candidatos:
        missing.append("fator psicossocial com evidência de perguntas críticas")
    if soft_only:
        missing.append("evidência direta de perguntas (apenas dimensão agregada)")
    if evidencia_nivel in {"fraca", "insuficiente"}:
        missing.append("evidência consolidada no recorte (nível fraco/insuficiente)")
    return missing


def compute_prioridade_acao(
    *,
    severity: float,
    evidencia_nivel: str,
    pattern_alerts: list[dict[str, str]],
    anonimato_ok: bool,
) -> str:
    """
    Prioridade de intervenção (1=mais urgente). Separada do potencial/matriz.
    Facilidade de solução NÃO reduz prioridade quando severity é alta.
    """
    critical_types = {
        "HIGH_DEMAND_LOW_CONTROL_LOW_SUPPORT",
        "HIGH_DEMAND_LOW_CONTROL",
    }
    has_critical = any(a.get("type") in critical_types for a in pattern_alerts)

    if has_critical and evidencia_nivel in {"forte", "moderada"}:
        return "1"
    if severity >= 65 and evidencia_nivel in {"forte", "moderada"} and anonimato_ok:
        return "1"
    if severity >= 45 or evidencia_nivel == "moderada" or has_critical:
        return "2"
    return "3"


def build_motor_rationale(
    *,
    ghe_numero: str,
    evidencia_nivel: str,
    hazards_candidatos: list[dict[str, Any]],
    pattern_alerts: list[dict[str, str]],
    protective_signals: list[dict[str, str]],
    missing_information: list[str],
    severity: float,
    ge: int,
    ges: int,
    potencial: str,
    prioridade_acao: str,
    match_info: str,
    n_respondentes: int,
) -> str:
    """Trilha auditável compacta para o revisor."""
    hazard_lines = [
        f"{h.get('id')} ({h.get('codigo_mte') or '—'}) sev={h.get('severity')}"
        for h in hazards_candidatos[:3]
    ]
    parts = [
        f"GHE {ghe_numero}: evidência {evidencia_nivel}, n={n_respondentes}.",
        f"Fatores: {'; '.join(hazard_lines) or 'agregado'}.",
        f"GE/GES={ge}/{ges} → potencial {potencial} (matriz Inseg).",
        f"Prioridade de ação: {prioridade_acao} (≠ potencial).",
    ]
    if pattern_alerts:
        parts.append(
            "Alertas: "
            + "; ".join(a.get("type", "") for a in pattern_alerts[:3])
        )
    if protective_signals:
        parts.append(
            "Proteção: "
            + "; ".join(s.get("type", "") for s in protective_signals[:2])
        )
    if missing_information:
        parts.append("Lacunas: " + ", ".join(missing_information[:4]))
    parts.append(f"Match campanha: {match_info}.")
    return " ".join(parts)
