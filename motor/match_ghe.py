from __future__ import annotations

from motor.models import CampaignData, GheBlock, SliceScore
from motor.textutil import best_overlap, normalize, token_overlap


def match_cargo_to_ghe(
    cargo: str, ghes: list[GheBlock], setor: str = ""
) -> tuple[GheBlock | None, float, str]:
    best: GheBlock | None = None
    best_score = 0.0
    best_why = ""

    for g in ghes:
        candidates = [g.nome, *g.funcoes]
        score, hit = best_overlap(cargo, candidates)
        # small boost if setor overlaps
        if setor and g.setor:
            score = min(1.0, score + 0.1 * token_overlap(setor, g.setor))
        if score > best_score:
            best_score = score
            best = g
            best_why = f"cargo→{hit}" if hit else "cargo"
    if best_score < 0.35:
        return None, best_score, "sem_match"
    return best, best_score, best_why


def slices_for_ghe(
    ghe: GheBlock, campaign: CampaignData
) -> list[tuple[SliceScore, float, str]]:
    hits: list[tuple[SliceScore, float, str]] = []
    for sl in campaign.por_cargo:
        if not sl.cargo:
            continue
        g, score, why = match_cargo_to_ghe(sl.cargo, [ghe], sl.setor)
        if g and score >= 0.35:
            hits.append((sl, score, why))
    hits.sort(key=lambda x: (x[0].n, x[1]), reverse=True)
    return hits


def aggregate_n(slices: list[SliceScore]) -> int:
    return sum(s.n for s in slices)


def worst_ssos_class(slices: list[SliceScore]) -> str:
    order = {
        "muito alta": 5,
        "alta": 4,
        "média": 3,
        "media": 3,
        "baixa": 2,
        "muito baixa": 1,
    }
    if not slices:
        return ""
    return max(slices, key=lambda s: order.get(normalize(s.classificacao), 0)).classificacao
