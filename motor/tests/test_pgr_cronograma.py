"""Testes do cronograma psicossocial no PGR."""

from __future__ import annotations

import tempfile
from pathlib import Path

from docx import Document

from motor.models import LineStatus, ProposedLine
from motor.pgr_cronograma import apply_psicossocial_cronogram
from motor.write_pgr import apply_lines_to_pgr

MODEL = Path(__file__).resolve().parents[2] / "modelos" / "PGR-Maestralle.docx"


def _line(
    *,
    ghe: str,
    setor: str,
    agente: str,
    potencial: str,
    controles: str,
    prioridade: str = "2",
) -> ProposedLine:
    return ProposedLine(
        ghe_numero=ghe,
        ghe_nome=f"GHE {ghe}",
        setor_pgr=setor,
        funcoes=[],
        categoria="Ergonômico (Psicossocial)",
        agente=agente,
        exposicao="Habitual",
        causa_fonte="Organização do trabalho",
        trajetoria="Demanda",
        danos="Fadiga mental",
        grau_exposicao=3,
        grau_efeito=3,
        potencial=potencial,
        controles=controles,
        evidencias=[],
        status=LineStatus.PROPOSTA,
        hazard_id="h1",
        match_score=1.0,
        matched_from="test",
        n_respondentes=5,
        action="insert_after_psico",
        aprho_table_index=0,
        psico_row_index=None,
        prioridade_acao=prioridade,
    )


def test_cronogram_groups_moderado_plus():
    if not MODEL.exists():
        return

    lines = [
        _line(ghe="01", setor="ACM", agente="Demandas Elevadas", potencial="Moderado", controles="Revisar metas"),
        _line(ghe="03", setor="ACM", agente="Demandas Elevadas", potencial="Alto", controles="Revisar metas e pausas"),
        _line(ghe="07", setor="Montagem", agente="Baixa Autonomia", potencial="Moderado", controles="Ampliar autonomia"),
        _line(ghe="09", setor="Montagem", agente="Baixa Autonomia", potencial="Baixo", controles="Não entra"),
    ]
    doc = Document(str(MODEL))
    result = apply_psicossocial_cronogram(doc, lines)
    assert result["status"] == "applied"
    assert result["rows_added"] == 2

    flat = " ".join(c.text for t in doc.tables for r in t.rows for c in r.cells)
    assert "organização do trabalho e gestão de demandas" in flat
    assert "comunicação, reconhecimento e apoio" in flat

    result2 = apply_psicossocial_cronogram(doc, lines)
    assert result2["status"] == "skipped"


def test_write_pgr_includes_cronogram():
    if not MODEL.exists():
        return

    lines = [
        _line(
            ghe="01",
            setor="ACM",
            agente="Demandas Elevadas",
            potencial="Moderado",
            controles="Revisão de metas e pausas programadas",
        )
    ]
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out.docx"
        stats = apply_lines_to_pgr(MODEL, out, lines, only_accepted=False)
        assert stats["cronogram"]["status"] in {"applied", "skipped", "no_eligible_lines"}
        assert stats["narrative"]["5.2"] in {"applied", "skipped"}


if __name__ == "__main__":
    test_cronogram_groups_moderado_plus()
    test_write_pgr_includes_cronogram()
    print("ok")
