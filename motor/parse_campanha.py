from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader

from motor.models import CampaignData, DimensionScore, QuestionScore, SliceScore
from motor.textutil import parse_float_br


def _pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    # normalize weird spacing from PDF extract
    text = "\n".join(parts)
    text = text.replace("\xa0", " ")
    return text


def _field_after(label: str, text: str, until: tuple[str, ...] | None = None) -> str:
    pattern = rf"{re.escape(label)}\s*\n+(.+?)(?:\n|$)"
    m = re.search(pattern, text, re.IGNORECASE)
    if not m:
        return ""
    val = m.group(1).strip()
    if until:
        for u in until:
            if val.upper().startswith(u.upper()):
                return ""
    return val


def parse_campanha_cst(path: str | Path) -> CampaignData:
    path = Path(path)
    text = _pdf_text(path)

    empresa = _field_after("Empresa", text)
    # sometimes empresa is on next non-empty after Empresa label block
    if not empresa or empresa.upper() in {"CNPJ", "CAMPANHA"}:
        m = re.search(r"Empresa\s*\n+\s*([^\n]+)", text, re.I)
        empresa = m.group(1).strip() if m else ""

    cnpj_m = re.search(r"(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})", text)
    cnpj = cnpj_m.group(1) if cnpj_m else ""

    campanha = ""
    m = re.search(
        r"Campanha\s*\n+\s*((?:Avalia[cç][aã]o|[A-Za-zÀ-ú0-9].*?)\s*\d*)\s*(?:\n|$)",
        text,
        re.I,
    )
    if m:
        campanha = m.group(1).strip()
        if campanha.lower() in {"empresa", "cnpj", "período da campanha", "periodo da campanha"}:
            campanha = ""
    if not campanha:
        m = re.search(r"(Avalia[cç][aã]o\s*\d+)", text, re.I)
        if m:
            campanha = m.group(1).strip()

    periodo = ""
    m = re.search(r"Per[ií]odo da campanha\s*\n+\s*([^\n]+)", text, re.I)
    if m:
        periodo = m.group(1).strip()

    ssos_pct = 0.0
    ssos_class = ""
    ssos_texto = ""
    m = re.search(
        r"SSOS\s*\n+\s*(-?\d+(?:[.,]\d+)?)\s*%\s*\(([^)]+)\)\s*-\s*(.+?)(?:\n\s*Participantes|\n\s*DIMENS)",
        text,
        re.I | re.S,
    )
    if m:
        ssos_pct = parse_float_br(m.group(1)) or 0.0
        ssos_class = m.group(2).strip()
        ssos_texto = re.sub(r"\s+", " ", m.group(3)).strip()

    n_part = 0
    m = re.search(r"(\d+)\s*Participantes?", text, re.I)
    if m:
        n_part = int(m.group(1))

    dimensoes = _parse_dimensoes(text)
    perguntas = _parse_perguntas(text)
    por_setor = _parse_ssos_setor(text)
    por_cargo = _parse_ssos_cargo(text)
    _enrich_matrix_pct(text, por_setor, por_cargo)

    return CampaignData(
        empresa=empresa,
        cnpj=cnpj,
        campanha=campanha,
        periodo=periodo,
        ssos_pct=ssos_pct,
        ssos_classificacao=ssos_class,
        ssos_texto=ssos_texto,
        n_participantes=n_part,
        dimensoes=dimensoes,
        perguntas=perguntas,
        por_setor=por_setor,
        por_cargo=por_cargo,
        source_file=path.name,
    )


def _parse_dimensoes(text: str) -> list[DimensionScore]:
    out: list[DimensionScore] = []
    # RECOMPENSA Positiva 31,8 44 72,35%
    for m in re.finditer(
        r"(RECOMPENSA|CONTROLE|ESFOR[CÇ]O|DEMANDA)\s+(Positiva|Negativa)\s+"
        r"(\d+(?:[.,]\d+)?)\s+(\d+(?:[.,]\d+)?)\s+(\d+(?:[.,]\d+)?)\s*%",
        text,
        re.I,
    ):
        out.append(
            DimensionScore(
                name=m.group(1).upper().replace("Ç", "C").replace("ESFORCO", "ESFORÇO"),
                tipo=m.group(2).capitalize(),
                media=parse_float_br(m.group(3)) or 0.0,
                maxima=parse_float_br(m.group(4)) or 0.0,
                pct=parse_float_br(m.group(5)) or 0.0,
            )
        )
    # normalize names
    for d in out:
        if "ESFOR" in d.name.upper():
            d.name = "ESFORÇO"
        elif d.name.upper().startswith("RECOMP"):
            d.name = "RECOMPENSA"
        elif d.name.upper().startswith("CONTROL"):
            d.name = "CONTROLE"
        elif d.name.upper().startswith("DEMAND"):
            d.name = "DEMANDA"
    return out


def _parse_perguntas(text: str) -> list[QuestionScore]:
    out: list[QuestionScore] = []
    # Question lines end with DIMENSAO media pct%
    # Multi-line questions: join until we see DIMENSAO float float%
    block_m = re.search(
        r"PERGUNTAS DE DIMENS[AÃ]O POSITIVA(.+?)PERGUNTAS DE DIMENS[AÃ]O NEGATIVA(.+?)(?:SSOS POR SETOR|MATRIZ DE AN[AÁ]LISE)",
        text,
        re.I | re.S,
    )
    chunks: list[tuple[str, str]] = []
    if block_m:
        chunks.append((block_m.group(1), "pos"))
        chunks.append((block_m.group(2), "neg"))
    else:
        chunks.append((text, "all"))

    dim_re = r"(CONTROLE|RECOMPENSA|ESFOR[CÇ]O|DEMANDA)"
    line_re = re.compile(
        rf"(.+?)\s+{dim_re}\s+(\d+(?:[.,]\d+)?)\s+(\d+(?:[.,]\d+)?)\s*%",
        re.I | re.S,
    )

    for chunk, _ in chunks:
        # flatten newlines inside questions carefully: replace newline not after % 
        flat = re.sub(r"\n(?!\s*(?:CONTROLE|RECOMPENSA|ESFOR|DEMANDA|SSOS|MATRIZ|DIMENS))", " ", chunk)
        flat = re.sub(r"\s+", " ", flat)
        for m in line_re.finditer(flat):
            q = m.group(1).strip(" -")
            q = re.sub(r"^CST INFORM[AÁ]TICA LTDA\.?\s*", "", q, flags=re.I).strip()
            # clean headers leaking in
            if "Pergunta" in q or "pontua" in q.lower() or len(q) < 12:
                continue
            dim = m.group(2).upper()
            if "ESFOR" in dim:
                dim = "ESFORÇO"
            out.append(
                QuestionScore(
                    text=q,
                    dimensao=dim,
                    media=parse_float_br(m.group(3)) or 0.0,
                    pct=parse_float_br(m.group(4)) or 0.0,
                )
            )
    return out


def _parse_ssos_setor(text: str) -> list[SliceScore]:
    out: list[SliceScore] = []
    m = re.search(
        r"SSOS POR SETOR\s*(.+?)(?:SSOS POR CARGO|MATRIZ DE AN[AÁ]LISE)",
        text,
        re.I | re.S,
    )
    if not m:
        return out
    block = m.group(1)
    # Setor n ssos Classificacao — class may be Alta/Baixa/Muito baixa
    for row in re.finditer(
        r"([A-Za-zÀ-ú0-9][A-Za-zÀ-ú0-9 /.\-]+?)\s+(\d+)\s+(-?\d+(?:[.,]\d+)?)\s+(Muito\s+baixa|Muito\s+alta|Baixa|Alta|Média|Media)",
        block,
        re.I,
    ):
        setor = row.group(1).strip()
        if setor.lower().startswith("setor") or "respostas" in setor.lower():
            continue
        out.append(
            SliceScore(
                setor=setor,
                cargo=None,
                n=int(row.group(2)),
                ssos=parse_float_br(row.group(3)) or 0.0,
                classificacao=re.sub(r"\s+", " ", row.group(4)).strip().title().replace("Media", "Média"),
            )
        )
    return out


def _parse_ssos_cargo(text: str) -> list[SliceScore]:
    """Parse SSOS POR CARGO — PDF often glues setor onto next line."""
    out: list[SliceScore] = []
    m = re.search(
        r"SSOS POR CARGO\s*(.+?)(?:MATRIZ DE AN[AÁ]LISE|DIMENS[OÕ]ES POSITIVAS)",
        text,
        re.I | re.S,
    )
    if not m:
        return out
    block = m.group(1)
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    current_setor = ""
    class_re = r"(Muito\s+baixa|Muito\s+alta|Baixa|Alta|Média|Media)"
    # Full row ending with: n ssos class — cargo is everything before that
    row_re = re.compile(
        rf"^(?P<head>.+?)\s+(?P<n>\d+)\s+(?P<ssos>-?\d+(?:[.,]\d+)?)\s+(?P<cls>{class_re})$",
        re.I,
    )
    # Known setores that may prefix the cargo on the same line
    setor_prefixes = [
        "Apoio ADM",
        "Produção/ Logística",
        "Producao/ Logistica",
        "Produção",
        "Producao",
    ]

    for ln in lines:
        low = ln.lower()
        if low.startswith("setor") or "classifica" in low or "respostas" in low or "ssos" == low:
            continue
        # sticky setor-only line
        if re.fullmatch(r"[A-Za-zÀ-ú0-9 /.\-]+", ln) and not re.search(r"\d", ln):
            current_setor = ln.strip()
            continue
        rm = row_re.match(ln)
        if not rm:
            continue
        head = rm.group("head").strip()
        setor = current_setor
        cargo = head
        for pref in sorted(setor_prefixes, key=len, reverse=True):
            if head.lower().startswith(pref.lower()):
                setor = pref
                cargo = head[len(pref) :].strip()
                break
        if not cargo:
            cargo = head
        out.append(
            SliceScore(
                setor=setor,
                cargo=cargo,
                n=int(rm.group("n")),
                ssos=parse_float_br(rm.group("ssos")) or 0.0,
                classificacao=re.sub(r"\s+", " ", rm.group("cls"))
                .strip()
                .title()
                .replace("Media", "Média"),
            )
        )
        if setor:
            current_setor = setor
    return out


def _enrich_matrix_pct(
    text: str, por_setor: list[SliceScore], por_cargo: list[SliceScore]
) -> None:
    m = re.search(
        r"MATRIZ DE AN[AÁ]LISE DE PROBABILIDADE POR CARGO\s*(.+?)(?:DIMENS[OÕ]ES POSITIVAS|$)",
        text,
        re.I | re.S,
    )
    if not m:
        return
    block = m.group(1)
    flat_lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    current_setor = ""
    row_re = re.compile(
        r"^(?:(?P<setor>.+?)\s+)?(?P<cargo>.+?)\s+"
        r"(?P<c>\d+(?:[.,]\d+)?)\s*%\s+"
        r"(?P<d>\d+(?:[.,]\d+)?)\s*%\s+"
        r"(?P<e>\d+(?:[.,]\d+)?)\s*%\s+"
        r"(?P<r>\d+(?:[.,]\d+)?)\s*%\s*$",
        re.I,
    )
    idx_by_key = {
        (s.setor.lower(), (s.cargo or "").lower()): s for s in por_cargo if s.cargo
    }
    for ln in flat_lines:
        if re.fullmatch(r"[A-Za-zÀ-ú0-9 /.\-]+", ln) and not re.search(r"%", ln):
            if "setor" in ln.lower() or "controle" in ln.lower() or "recompensa" in ln.lower():
                continue
            current_setor = ln
            continue
        rm = row_re.match(ln)
        if not rm:
            continue
        setor = (rm.group("setor") or current_setor).strip()
        cargo = rm.group("cargo").strip()
        key = (setor.lower(), cargo.lower())
        # fuzzy key: match by cargo only
        target = idx_by_key.get(key)
        if not target:
            for s in por_cargo:
                if s.cargo and s.cargo.lower() == cargo.lower():
                    target = s
                    break
        if target:
            target.controle_pct = parse_float_br(rm.group("c"))
            target.demanda_pct = parse_float_br(rm.group("d"))
            target.esforco_pct = parse_float_br(rm.group("e"))
            target.recompensa_pct = parse_float_br(rm.group("r"))
        if setor:
            current_setor = setor

    # setor matrix
    m2 = re.search(
        r"MATRIZ DE AN[AÁ]LISE DE PROBABILIDADE POR SETOR\s*(.+?)(?:MATRIZ DE AN[AÁ]LISE DE PROBABILIDADE POR CARGO|$)",
        text,
        re.I | re.S,
    )
    if not m2:
        return
    for ln in m2.group(1).splitlines():
        ln = ln.strip()
        rm = re.match(
            r"^(.+?)\s+(\d+(?:[.,]\d+)?)\s*%\s+(\d+(?:[.,]\d+)?)\s*%\s+(\d+(?:[.,]\d+)?)\s*%\s+(\d+(?:[.,]\d+)?)\s*%\s*$",
            ln,
        )
        if not rm:
            continue
        setor = rm.group(1).strip()
        if "setor" in setor.lower() or "controle" in setor.lower():
            continue
        for s in por_setor:
            if s.setor.lower() == setor.lower():
                s.controle_pct = parse_float_br(rm.group(2))
                s.demanda_pct = parse_float_br(rm.group(3))
                s.esforco_pct = parse_float_br(rm.group(4))
                s.recompensa_pct = parse_float_br(rm.group(5))
