"""Inserção mecânica de linhas psicossociais no CRONOGRAMA – PLANO DE AÇÃO."""

from __future__ import annotations

import copy
import logging
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass

from docx import Document
from docx.table import Table, _Row

from motor.models import ProposedLine

logger = logging.getLogger(__name__)

_POTENCIAL_EXCLUIDOS = frozenset({"muito baixo", "baixo"})
_CRONOGRAMA_MARKER = "Medidas psicossociais —"
_DATA_ROW_RE = re.compile(r"^\d{1,3}$")

# Coluna única de "P" (previsto) por prioridade de ação
_PRIORIDADE_P_COL = {"1": 6, "2": 10, "3": 16, "": 10}


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKC", text or "")
    t = t.replace("\xa0", " ")
    return re.sub(r"\s+", " ", t).strip().lower()


def _set_cell_text(cell, text: str) -> None:
    text = text or ""
    if cell.paragraphs:
        p0 = cell.paragraphs[0]
        if p0.runs:
            p0.runs[0].text = text
            for run in p0.runs[1:]:
                run.text = ""
        else:
            p0.text = text
        for p in cell.paragraphs[1:]:
            p._element.getparent().remove(p._element)
    else:
        cell.text = text


def _clone_row(table: Table, row_index: int) -> _Row:
    row = table.rows[row_index]
    new_tr = copy.deepcopy(row._tr)
    row._tr.addnext(new_tr)
    return table.rows[row_index + 1]


def _needs_cronograma(potencial: str) -> bool:
    return _norm(potencial) not in _POTENCIAL_EXCLUIDOS


def _find_cronogram_table(doc: Document) -> Table | None:
    for table in doc.tables:
        if len(table.rows) < 6 or len(table.columns) < 10:
            continue
        header = _norm(" ".join(c.text for r in table.rows[:4] for c in r.cells))
        if "cronograma" in header and "plano de a" in header:
            row3 = _norm(" ".join(c.text for c in table.rows[3].cells))
            if "o que" in row3 and "por qu" in row3:
                return table
    return None


def _last_data_row_index(table: Table) -> int | None:
    last: int | None = None
    for i, row in enumerate(table.rows):
        seq = row.cells[0].text.strip()
        if _DATA_ROW_RE.match(seq):
            last = i
    return last


def _next_sequence(table: Table) -> int:
    last = _last_data_row_index(table)
    if last is None:
        return 1
    try:
        return int(table.rows[last].cells[0].text.strip()) + 1
    except ValueError:
        return 1


def _truncate(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


@dataclass
class _CronogramGroup:
    setor: str
    agente: str
    ghe_numeros: list[str]
    controles: str
    prioridade: str


def _build_groups(lines: list[ProposedLine]) -> list[_CronogramGroup]:
    buckets: dict[tuple[str, str], list[ProposedLine]] = defaultdict(list)
    for ln in lines:
        if not _needs_cronograma(ln.potencial):
            continue
        setor = (ln.setor_pgr or "Geral").strip() or "Geral"
        agente = (ln.agente or "Fatores psicossociais").strip()
        buckets[(setor, agente)].append(ln)

    groups: list[_CronogramGroup] = []
    for (setor, agente), items in sorted(buckets.items(), key=lambda x: (x[0][0], x[0][1])):
        ghes = sorted({ln.ghe_numero for ln in items}, key=lambda g: (len(g), g))
        controles = max((ln.controles or "" for ln in items), key=len)
        prios = [ln.prioridade_acao for ln in items if ln.prioridade_acao in {"1", "2", "3"}]
        prioridade = min(prios) if prios else "2"
        groups.append(
            _CronogramGroup(
                setor=setor,
                agente=agente,
                ghe_numeros=ghes,
                controles=controles,
                prioridade=prioridade,
            )
        )
    return groups


def _format_ghe_list(ghes: list[str]) -> str:
    if len(ghes) <= 8:
        return ", ".join(ghes)
    return f"{', '.join(ghes[:8])} (+{len(ghes) - 8} GHEs)"


def _write_cronogram_row(
    row: _Row,
    *,
    seq: int,
    o_que: str,
    por_que: str,
    como: str,
    prioridade: str,
) -> None:
    cells = row.cells
    if len(cells) < 6:
        return

    _set_cell_text(cells[0], f"{seq:02d}")
    _set_cell_text(cells[1], o_que)
    _set_cell_text(cells[2], por_que)
    _set_cell_text(cells[3], "")
    _set_cell_text(cells[4], como)
    _set_cell_text(cells[5], "Sem Custo")

    p_col = _PRIORIDADE_P_COL.get(prioridade, 10)
    written: set[int] = set()
    for i in range(6, len(cells)):
        tc_id = id(cells[i]._tc)
        if tc_id in written:
            continue
        written.add(tc_id)
        _set_cell_text(cells[i], "P" if i == p_col else "")


def _cronogram_already_applied(table: Table) -> bool:
    for row in table.rows:
        for cell in row.cells[:2]:
            if _CRONOGRAMA_MARKER.lower() in _norm(cell.text):
                return True
    return False


def apply_psicossocial_cronogram(doc: Document, lines: list[ProposedLine]) -> dict:
    """
    Modo B: uma linha por (setor, agente) quando potencial > Baixo.
    Idempotente se linhas psicossociais já existirem no cronograma.
    """
    table = _find_cronogram_table(doc)
    if table is None:
        logger.warning("PGR cronograma: tabela CRONOGRAMA – PLANO DE AÇÃO não encontrada")
        return {"status": "table_not_found", "rows_added": 0, "groups": 0}

    if _cronogram_already_applied(table):
        return {"status": "skipped", "rows_added": 0, "groups": 0}

    groups = _build_groups(lines)
    if not groups:
        return {"status": "no_eligible_lines", "rows_added": 0, "groups": 0}

    anchor = _last_data_row_index(table)
    if anchor is None:
        anchor = min(5, len(table.rows) - 1)

    seq = _next_sequence(table)
    added = 0
    for group in groups:
        ghe_txt = _format_ghe_list(group.ghe_numeros)
        o_que = _truncate(
            f"{_CRONOGRAMA_MARKER} {group.setor} — GHEs {ghe_txt}",
            120,
        )
        por_que = _truncate(
            f"Reduzir exposição a {group.agente} conforme avaliação psicossocial (SSOS/PGRO)",
            200,
        )
        como = _truncate(group.controles, 220)

        new_row = _clone_row(table, anchor)
        anchor += 1
        _write_cronogram_row(
            new_row,
            seq=seq,
            o_que=o_que,
            por_que=por_que,
            como=como,
            prioridade=group.prioridade,
        )
        seq += 1
        added += 1

    return {"status": "applied", "rows_added": added, "groups": len(groups)}
