"""Inserção mecânica de linhas psicossociais no CRONOGRAMA – PLANO DE AÇÃO."""

from __future__ import annotations

import logging
import re
import unicodedata

from docx import Document
from docx.table import Table, _Row

from motor.models import ProposedLine
from motor.pgr_docx_utils import (
    clone_row,
    force_row_page_break,
    set_cell_fill,
    set_cell_text,
    unique_cells,
)

logger = logging.getLogger(__name__)

_POTENCIAL_EXCLUIDOS = frozenset({"muito baixo", "baixo"})
_CRONOGRAMA_MARKER = "Medidas psicossociais —"
_DATA_ROW_RE = re.compile(r"^\d{1,3}$")
_P_YELLOW = "FFFF00"

_GENERIC_ACTIONS: tuple[tuple[str, str, str, str], ...] = (
    (
        "2",
        "Medidas psicossociais — organização do trabalho e gestão de demandas (SSOS/PGRO)",
        "Atender fatores psicossociais identificados na avaliação (demanda, controle, apoio)",
        "Revisar organização do trabalho, metas, pausas e canais de comunicação conforme PGR",
    ),
    (
        "2",
        "Medidas psicossociais — comunicação, reconhecimento e apoio às equipes (SSOS/PGRO)",
        "Reduzir exposição a fatores psicossociais relacionados ao clima e reconhecimento",
        "Implementar ações de prevenção, acolhimento e acompanhamento conforme SSOS/PGRO",
    ),
)


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKC", text or "")
    t = t.replace("\xa0", " ")
    return re.sub(r"\s+", " ", t).strip().lower()


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


def _find_p_cell_index(row) -> int | None:
    """Índice da célula com 'P' previsto (modelo Inseg — coluna amarela)."""
    for idx, cell in unique_cells(row):
        if cell.text.strip().upper() == "P":
            return idx
    return None


def _write_cronogram_row(
    row: _Row,
    *,
    seq: int,
    o_que: str,
    por_que: str,
    como: str,
    p_cell_index: int | None,
) -> None:
    uniq = unique_cells(row)
    by_idx = {idx: cell for idx, cell in uniq}

    if 0 in by_idx:
        set_cell_text(by_idx[0], f"{seq:02d}")
    if 1 in by_idx:
        set_cell_text(by_idx[1], o_que)
    if 2 in by_idx:
        set_cell_text(by_idx[2], por_que)
    if 4 in by_idx:
        set_cell_text(by_idx[4], como)
    if 5 in by_idx:
        set_cell_text(by_idx[5], "Sem Custo")

    if p_cell_index is not None and p_cell_index in by_idx:
        p_cell = by_idx[p_cell_index]
        set_cell_text(p_cell, "P")
        set_cell_fill(p_cell, _P_YELLOW)


def _cronogram_already_applied(table: Table) -> bool:
    for row in table.rows:
        for cell in row.cells[:2]:
            if _CRONOGRAMA_MARKER.lower() in _norm(cell.text):
                return True
    return False


def _has_eligible_lines(lines: list[ProposedLine]) -> bool:
    return any(_needs_cronograma(ln.potencial) for ln in lines)


def apply_psicossocial_cronogram(doc: Document, lines: list[ProposedLine]) -> dict:
    """
    Duas ações genéricas psicossociais quando houver linha com potencial > Baixo.
    Clona linha-modelo (logo/watermark) e marca P em amarelo.
    """
    table = _find_cronogram_table(doc)
    if table is None:
        logger.warning("PGR cronograma: tabela CRONOGRAMA – PLANO DE AÇÃO não encontrada")
        return {"status": "table_not_found", "rows_added": 0, "groups": 0}

    if _cronogram_already_applied(table):
        return {"status": "skipped", "rows_added": 0, "groups": 0}

    if not _has_eligible_lines(lines):
        return {"status": "no_eligible_lines", "rows_added": 0, "groups": 0}

    anchor = _last_data_row_index(table)
    if anchor is None:
        anchor = min(5, len(table.rows) - 1)

    template_row = table.rows[anchor]
    p_cell_index = _find_p_cell_index(template_row)

    seq = _next_sequence(table)
    added = 0
    for _prioridade, o_que, por_que, como in _GENERIC_ACTIONS:
        new_row = clone_row(table, anchor)
        anchor += 1
        if added == 0:
            force_row_page_break(new_row)
        _write_cronogram_row(
            new_row,
            seq=seq,
            o_que=o_que,
            por_que=por_que,
            como=como,
            p_cell_index=p_cell_index,
        )
        seq += 1
        added += 1

    return {"status": "applied", "rows_added": added, "groups": len(_GENERIC_ACTIONS)}
