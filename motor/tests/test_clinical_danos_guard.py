"""Testes de defesa: danos clínicos/robóticos não podem passar."""

from __future__ import annotations

import logging
from types import SimpleNamespace

from motor.hazards import has_clinical_danos
from motor.llm import is_robotic_danos
from motor.write_pgr import _SAFE_DANOS_FALLBACK, _write_row


def test_burnout_leak_string_is_caught():
    """Caso real que vazou para produção — não pode voltar a passar."""
    text = "Síndrome de Burnout, Ansiedade, Diminuição da produtividade"
    assert has_clinical_danos(text) is True
    assert is_robotic_danos(text) is True


def test_ok_occupational_danos_pass():
    text = "Fadiga por Ritmo de Linha, Redução da Atenção em Tarefa Repetitiva"
    assert has_clinical_danos(text) is False
    assert is_robotic_danos(text) is False


def test_write_row_safety_net_replaces_clinical(caplog):
    class _Cell:
        def __init__(self):
            self._tc = object()
            self.paragraphs = []
            self.text = ""

    class _Row:
        def __init__(self):
            self.cells = [_Cell() for _ in range(10)]

    ln = SimpleNamespace(
        ghe_numero="07",
        categoria="Ergonômico (Psicossocial)",
        agente="Demandas Quantitativas Elevadas e Pressão Temporal",
        exposicao="Habitual e Intermitente",
        causa_fonte="Ritmo de Linha",
        trajetoria="Organização do Trabalho",
        danos="Síndrome de Burnout, Ansiedade, Diminuição da produtividade",
        grau_exposicao=2,
        grau_efeito=2,
        potencial="Baixo",
        controles="Revisão de Metas do Posto",
    )
    row = _Row()
    with caplog.at_level(logging.WARNING, logger="motor.write_pgr"):
        _write_row(row, ln)
    assert row.cells[5].text == _SAFE_DANOS_FALLBACK
    assert "safety-net" in caplog.text.lower() or "bloqueado" in caplog.text.lower()
