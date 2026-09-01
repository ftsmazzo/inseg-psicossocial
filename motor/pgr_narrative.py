"""Trechos descritivos psicossociais fixos nos PGR Inseg (mecânico, idempotente)."""

from __future__ import annotations

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


def _find_paragraph(doc: Document, *anchor_substrings: str) -> Paragraph | None:
    """Primeiro parágrafo cujo texto contém todos os substrings (normalizados)."""
    if not anchor_substrings:
        return None
    needles = [_norm(s) for s in anchor_substrings]
    for para in doc.paragraphs:
        hay = _norm(para.text)
        if all(n in hay for n in needles):
            return para
    return None


def _append_to_paragraph(paragraph: Paragraph, suffix: str) -> None:
    """Acrescenta texto ao fim do parágrafo, removendo ponto final se houver."""
    base = paragraph.text.rstrip()
    if base.endswith("."):
        base = base[:-1].rstrip()
    paragraph.text = f"{base}{suffix}"


def _insert_after(paragraph: Paragraph, lines: list[str]) -> None:
    """Insere parágrafos após o âncora, copiando o estilo dele."""
    from docx.oxml import OxmlElement

    style = paragraph.style
    anchor = paragraph
    for line in lines:
        new_p = OxmlElement("w:p")
        anchor._p.addnext(new_p)
        new_para = Paragraph(new_p, paragraph._parent)
        new_para.style = style
        new_para.text = line
        anchor = new_para


def _find_last_references_anchor(doc: Document) -> Paragraph | None:
    """Último item da seção DOCUMENTOS DE REFERÊNCIA (final do documento)."""
    last_heading: int | None = None
    for i, para in enumerate(doc.paragraphs):
        if _norm(para.text) == _norm("DOCUMENTOS DE REFERÊNCIA"):
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


@dataclass(frozen=True)
class _Patch:
    patch_id: str
    mode: Mode
    anchors: tuple[str, ...]
    marker: str
    append_suffix: str = ""
    insert_lines: tuple[str, ...] = ()
    insert_style_from: str | None = None  # substring para copiar estilo de outro parágrafo


# Textos fixos — iguais para todos os PGR com psicossocial Inseg.
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
        insert_style_from="acidente de trabalho de origem elétrica",
    ),
    _Patch(
        patch_id="documentos_referencia_psico",
        mode="insert_after",
        anchors=(),  # tratado à parte
        marker="Relatório de Avaliação Psicossocial (SSOS)",
        insert_lines=(
            "Relatório de Avaliação Psicossocial (SSOS);",
            "Resultados consolidados da pesquisa de fatores psicossociais aplicada aos trabalhadores.",
        ),
        insert_style_from="Norma Regulamentadora nº 9",
    ),
)


def apply_psicossocial_narratives(doc: Document) -> dict[str, str | bool]:
    """
    Insere trechos descritivos psicossociais padrão Inseg.
    Idempotente: não duplica se o marcador já existir no documento.
    Retorna status por patch_id.
    """
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
            style = anchor.style
            from docx.oxml import OxmlElement

            insert_after = anchor
            for line in patch.insert_lines:
                new_p = OxmlElement("w:p")
                insert_after._p.addnext(new_p)
                new_para = Paragraph(new_p, anchor._parent)
                new_para.style = style
                new_para.text = line
                insert_after = new_para
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

        style = anchor.style
        if patch.insert_style_from:
            src = _find_paragraph(doc, patch.insert_style_from)
            if src is not None:
                style = src.style

        from docx.oxml import OxmlElement

        insert_after = anchor
        for line in patch.insert_lines:
            new_p = OxmlElement("w:p")
            insert_after._p.addnext(new_p)
            new_para = Paragraph(new_p, anchor._parent)
            new_para.style = style
            new_para.text = line
            insert_after = new_para
        results[patch.patch_id] = "applied"

    return results
