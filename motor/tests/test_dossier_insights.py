"""Testes da camada de insights do dossiê."""

from __future__ import annotations

import unittest

from motor.dossier_insights import (
    build_motor_rationale,
    compute_missing_information,
    compute_pattern_alerts,
    compute_prioridade_acao,
    compute_protective_signals,
)


class DossierInsightsTests(unittest.TestCase):
    def test_high_demand_low_control_low_support(self):
        slices = [
            {
                "demanda_pct": 70,
                "controle_pct": 40,
                "recompensa_pct": 35,
                "esforco_pct": 50,
            }
        ]
        alerts = compute_pattern_alerts(slices)
        types = {a["type"] for a in alerts}
        self.assertIn("HIGH_DEMAND_LOW_CONTROL_LOW_SUPPORT", types)

    def test_protective_control(self):
        slices = [{"controle_pct": 65, "recompensa_pct": 50}]
        signals = compute_protective_signals(slices)
        self.assertTrue(any(s["type"] == "FAVORABLE_CONTROL" for s in signals))

    def test_missing_information_lists_gaps(self):
        missing = compute_missing_information(
            n_respondentes=3,
            anonimato_ok=False,
            atividade_resumo="curto",
            has_slice=False,
            hazards_candidatos=[],
            evidencia_nivel="insuficiente",
            soft_only=True,
        )
        self.assertGreaterEqual(len(missing), 3)

    def test_prioridade_separate_from_potencial(self):
        p = compute_prioridade_acao(
            severity=70,
            evidencia_nivel="forte",
            pattern_alerts=[{"type": "HIGH_DEMAND_LOW_CONTROL_LOW_SUPPORT"}],
            anonimato_ok=True,
        )
        self.assertEqual(p, "1")

    def test_motor_rationale_includes_priority(self):
        text = build_motor_rationale(
            ghe_numero="01",
            evidencia_nivel="moderada",
            hazards_candidatos=[{"id": "demandas_pressao_temporal", "codigo_mte": "PSICO-010", "severity": 62}],
            pattern_alerts=[],
            protective_signals=[],
            missing_information=[],
            severity=62,
            ge=3,
            ges=3,
            potencial="Médio",
            prioridade_acao="2",
            match_info="cargo_match",
            n_respondentes=12,
        )
        self.assertIn("Prioridade de ação: 2", text)
        self.assertIn("potencial Médio", text)


if __name__ == "__main__":
    unittest.main()
