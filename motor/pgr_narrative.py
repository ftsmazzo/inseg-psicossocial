"""Trechos descritivos psicossociais fixos nos PGR Inseg (mecânico, idempotente)."""

from __future__ import annotations

import copy
import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

from docx import Document
from docx.text.paragraph import Paragraph

logger = logging.getLogger(__name__)

Mode = Literal["append", "insert_after"]


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKC", text or "")
    t = t.replace("\xa0", " ")
    return re.sub(r"\s+", " ", t).strip().lower()


def _doc_contains(doc: Document, marker: str) -> bool:
    m = _norm(marker)
    if not m:
        return False
    for para in doc.paragraphs:
        if m in _norm(para.text):
            return True
    return False


def _paragraph_index(doc: Document, para: Paragraph) -> int | None:
    for i, p in enumerate(doc.paragraphs):
        if p._p is para._p:
            return i
    return None


def _find_paragraph(doc: Document, *anchor_substrings: str) -> Paragraph | None:
    if not anchor_substrings:
        return None
    needles = [_norm(s) for s in anchor_substrings]
    for para in doc.paragraphs:
        hay = _norm(para.text)
        if all(n in hay for n in needles):
            return para
    return None


def _clone_paragraph_after(template: Paragraph, text: str, after: Paragraph) -> Paragraph:
    """Insere parágrafo clonando XML do template (fonte, tamanho, estilo Inseg)."""
    new_el = copy.deepcopy(template._p)
    after._p.addnext(new_el)
    new_para = Paragraph(new_el, after._parent)
    if new_para.runs:
        new_para.runs[0].text = text
        for run in new_para.runs[1:]:
            run.text = ""
    else:
        new_para.text = text
    return new_para


def _insert_formatted_after(
    anchor: Paragraph,
    lines: list[str],
    *,
    template: Paragraph | None = None,
) -> None:
    tpl = template or anchor
    current = anchor
    for line in lines:
        current = _clone_paragraph_after(tpl, line, current)


def _append_to_paragraph(paragraph: Paragraph, suffix: str) -> None:
    """Acrescenta ao fim preservando formatação do primeiro run quando possível."""
    base = paragraph.text.rstrip()
    if base.endswith("."):
        base = base[:-1].rstrip()
    new_text = f"{base}{suffix}"
    if paragraph.runs:
        paragraph.runs[0].text = new_text
        for run in paragraph.runs[1:]:
            run.text = ""
    else:
        paragraph.text = new_text


def _find_last_references_anchor(doc: Document) -> Paragraph | None:
    """Último item da seção DOCUMENTOS DE REFERÊNCIA (final do documento)."""
    last_heading: int | None = None
    for i, para in enumerate(doc.paragraphs):
        if _norm(para.text.replace("\t", "")) == _norm("DOCUMENTOS DE REFERÊNCIA"):
            last_heading = i
    if last_heading is None:
        return None

    insert_after = doc.paragraphs[last_heading]
    for i in range(last_heading + 1, len(doc.paragraphs)):
        para = doc.paragraphs[i]
        text = para.text.strip()
        if not text:
            continue
        style = para.style.name if para.style else ""
        if style.startswith("Heading"):
            break
        insert_after = para
    return insert_after


def _find_plano_emergencia_insert_after(doc: Document, anchor: Paragraph) -> Paragraph:
    """
    Último ponto do bloco de acidente elétrico (modelo Amendo/Inseg),
    antes de EVACUAÇÃO / INCÊNDIO ou conteúdo psicossocial já inserido.
    """
    idx = _paragraph_index(doc, anchor)
    if idx is None:
        return anchor

    insert_after = anchor
    for i in range(idx + 1, len(doc.paragraphs)):
        para = doc.paragraphs[i]
        t = _norm(para.text)
        if not t:
            continue
        if any(k in t for k in ("evacua", "incêndio", "incendio", "em caso de inc")):
            break
        if "crise emocional" in t:
            break
        insert_after = para
    return insert_after


def _bullet_template_after_anchor(doc: Document, anchor: Paragraph) -> Paragraph:
    """Primeiro item de procedimento após o parágrafo-âncora (ex.: passo elétrico)."""
    idx = _paragraph_index(doc, anchor)
    if idx is None:
        return anchor
    for i in range(idx + 1, min(idx + 6, len(doc.paragraphs))):
        para = doc.paragraphs[i]
        if len(para.text.strip()) > 20:
            return para
    return anchor


@dataclass(frozen=True)
class _Patch:
    patch_id: str
    mode: Mode
    anchors: tuple[str, ...]
    marker: str
    append_suffix: str = ""
    insert_lines: tuple[str, ...] = ()
    insert_style_from: str | None = None
    plano_emergencia_block: bool = False


_PATCHES: tuple[_Patch, ...] = (
    _Patch(
        patch_id="5.2",
        mode="append",
        anchors=("avaliar os riscos ocupacionais relativos aos perigos identificados",),
        marker="fatores psicossociais relacionados à organização do trabalho, conforme previsto na legislação vigente",
        append_suffix=(
            " e os fatores psicossociais relacionados à organização do trabalho, "
            "conforme previsto na legislação vigente e nas diretrizes de gestão de "
            "Segurança e Saúde no Trabalho adotadas pela organização."
        ),
    ),
    _Patch(
        patch_id="5.3",
        mode="insert_after",
        anchors=("desenvolver ações em saúde ocupacional dos trabalhadores",),
        marker="O acompanhamento da saúde ocupacional deverá considerar também os fatores psicossociais",
        insert_lines=(
            "O acompanhamento da saúde ocupacional deverá considerar também os fatores "
            "psicossociais relacionados ao trabalho, mediante monitoramento periódico e "
            "reavaliações sempre que ocorrerem alterações significativas na organização do trabalho.",
        ),
        insert_style_from="desenvolver ações em saúde ocupacional dos trabalhadores",
    ),
    _Patch(
        patch_id="5.5",
        mode="insert_after",
        anchors=("ferramentas e técnicas de avaliação de riscos", "adequadas ao risco ou circunstância"),
        marker="ferramenta específica de levantamento e análise dos fatores relacionados à organização do trabalho",
        insert_lines=(
            "Para os fatores psicossociais, a avaliação foi realizada por meio de ferramenta "
            "específica de levantamento e análise dos fatores relacionados à organização do "
            "trabalho, contemplando aspectos como demanda, controle, esforço e recompensa, "
            "sendo os resultados utilizados para subsidiar a identificação dos perigos, a "
            "avaliação dos riscos e a definição das medidas de prevenção aplicáveis.",
        ),
        insert_style_from="ferramentas e técnicas de avaliação de riscos",
    ),
    _Patch(
        patch_id="plano_emergencia_psico",
        mode="insert_after",
        anchors=("acidente de trabalho de origem elétrica", "procedimentos especiais"),
        marker="Em casos de crise emocional, mal súbito ou outras ocorrências relacionadas a fatores psicossociais",
        insert_lines=(
            "Em casos de crise emocional, mal súbito ou outras ocorrências relacionadas a "
            "fatores psicossociais que possam comprometer a segurança do trabalhador, "
            "deverão ser adotadas as seguintes medidas:",
            "Manter a calma e afastar o trabalhador de fontes de risco;",
            "Comunicar imediatamente o superior responsável;",
            "Encaminhar o trabalhador para local seguro e tranquilo;",
            "Acionar atendimento médico quando necessário;",
            "Registrar a ocorrência para acompanhamento e adoção das medidas cabíveis.",
        ),
        plano_emergencia_block=True,
    ),
    _Patch(
        patch_id="documentos_referencia_psico",
        mode="insert_after",
        anchors=(),
        marker="Relatório de Avaliação Psicossocial (SSOS)",
        insert_lines=(
            "Relatório de Avaliação Psicossocial (SSOS);",
            "Resultados consolidados da pesquisa de fatores psicossociais aplicada aos trabalhadores.",
        ),
        insert_style_from="Norma Regulamentadora nº 9",
    ),
)


def apply_psicossocial_narratives(doc: Document) -> dict[str, str | bool]:
    results: dict[str, str | bool] = {}

    for patch in _PATCHES:
        if _doc_contains(doc, patch.marker):
            results[patch.patch_id] = "skipped"
            continue

        if patch.patch_id == "documentos_referencia_psico":
            anchor = _find_last_references_anchor(doc)
            if anchor is None:
                results[patch.patch_id] = "anchor_not_found"
                logger.warning("PGR narrative: seção DOCUMENTOS DE REFERÊNCIA não encontrada")
                continue
            tpl = _find_paragraph(doc, patch.insert_style_from or "") or anchor
            _insert_formatted_after(anchor, list(patch.insert_lines), template=tpl)
            results[patch.patch_id] = "applied"
            continue

        anchor = _find_paragraph(doc, *patch.anchors)
        if anchor is None:
            results[patch.patch_id] = "anchor_not_found"
            logger.warning(
                "PGR narrative %s: âncora não encontrada (%s)",
                patch.patch_id,
                patch.anchors,
            )
            continue

        if patch.mode == "append":
            _append_to_paragraph(anchor, patch.append_suffix)
            results[patch.patch_id] = "applied"
            continue

        if patch.plano_emergencia_block:
            insert_after = _find_plano_emergencia_insert_after(doc, anchor)
            bullet_tpl = _bullet_template_after_anchor(doc, anchor)
            _insert_formatted_after(
                insert_after,
                list(patch.insert_lines),
                template=bullet_tpl,
            )
            results[patch.patch_id] = "applied"
            continue

        tpl = anchor
        if patch.insert_style_from:
            src = _find_paragraph(doc, patch.insert_style_from)
            if src is not None:
                tpl = src
        _insert_formatted_after(anchor, list(patch.insert_lines), template=tpl)
        results[patch.patch_id] = "applied"

    return results
