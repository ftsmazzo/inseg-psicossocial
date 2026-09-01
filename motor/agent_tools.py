"""Tools do agente sobre dossiês já parseados (+ knowledge + snippets aprovados)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from motor.hazards import has_clinical_danos, is_generic_agente, is_job_title_agente
from motor.llm import is_generic_field, is_robotic_danos
from motor.dossier import JobDossiers, list_ghe_summaries
from motor.knowledge_index import search_knowledge


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_ghes",
            "description": "Lista GHEs do job com resumo (n, hazards, anonimato).",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_ghe_dossier",
            "description": "Retorna o dossiê mastigado completo de um GHE.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ghe_numero": {"type": "string", "description": "Número do GHE, ex: 01"},
                },
                "required": ["ghe_numero"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_critical_questions",
            "description": "Perguntas críticas da campanha para um GHE.",
            "parameters": {
                "type": "object",
                "properties": {"ghe_numero": {"type": "string"}},
                "required": ["ghe_numero"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_aprho_line",
            "description": "Linha psicossocial atual no PGR (se existir) e/ou proposta em edição.",
            "parameters": {
                "type": "object",
                "properties": {"ghe_numero": {"type": "string"}},
                "required": ["ghe_numero"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_hazards",
            "description": "Hazards candidatos já detectados pelo motor para o GHE.",
            "parameters": {
                "type": "object",
                "properties": {"ghe_numero": {"type": "string"}},
                "required": ["ghe_numero"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "Busca nas skills NR-01/Inseg, corpus MTE/SESI e exemplos gold.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "validate_line",
            "description": "Valida campos APRHO (anti-genérico, exposição fixa, etc).",
            "parameters": {
                "type": "object",
                "properties": {
                    "agente": {"type": "string"},
                    "exposicao": {"type": "string"},
                    "causa_fonte": {"type": "string"},
                    "trajetoria": {"type": "string"},
                    "danos": {"type": "string"},
                    "controles": {"type": "string"},
                    "ghe_numero": {"type": "string"},
                },
                "required": ["agente", "causa_fonte", "controles"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_line",
            "description": (
                "Grava campos APRHO no GHE — use SOMENTE quando o usuário pedir explicitamente "
                "para aplicar/gravar/salvar/atualizar a linha, ou confirmar uma sugestão sua."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ghe_numero": {"type": "string"},
                    "agente": {"type": "string"},
                    "exposicao": {"type": "string"},
                    "causa_fonte": {"type": "string"},
                    "trajetoria": {"type": "string"},
                    "danos": {"type": "string"},
                    "controles": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": [
                    "ghe_numero",
                    "agente",
                    "causa_fonte",
                    "trajetoria",
                    "danos",
                    "controles",
                ],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explain_line",
            "description": "Explica a proposta atual de um GHE com base no dossiê.",
            "parameters": {
                "type": "object",
                "properties": {"ghe_numero": {"type": "string"}},
                "required": ["ghe_numero"],
            },
        },
    },
]


def validate_line_fields(payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    agente = (payload.get("agente") or "").strip()
    causa = (payload.get("causa_fonte") or "").strip()
    controles = (payload.get("controles") or "").strip()
    exposicao = (payload.get("exposicao") or "Habitual e Intermitente").strip()
    trajetoria = (payload.get("trajetoria") or "").strip()
    danos = (payload.get("danos") or "").strip()

    if not agente or is_generic_agente(agente):
        errors.append("agente genérico ou vazio")
    if is_job_title_agente(agente):
        errors.append(
            "agente parece cargo/função — use perigo psicossocial (ex.: Demandas Quantitativas e Pressão Temporal)"
        )
    if is_generic_field(causa, "causa"):
        errors.append("causa_fonte genérica ou insuficiente")
    if is_generic_field(controles, "controle"):
        errors.append("controles genéricos ou insuficientes")
    if is_robotic_danos(danos) or has_clinical_danos(danos):
        errors.append("danos genéricos/robóticos ou clínicos (use agravos SST amarrados ao posto)")
    if exposicao and exposicao != "Habitual e Intermitente":
        warnings.append("exposicao deve ser 'Habitual e Intermitente' (será forçada)")
    if len(trajetoria) < 8:
        warnings.append("trajetoria curta")
    if len(danos) < 8:
        warnings.append("danos curtos")

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "normalized": {
            "agente": agente,
            "exposicao": "Habitual e Intermitente",
            "causa_fonte": causa,
            "trajetoria": trajetoria,
            "danos": danos,
            "controles": controles,
        },
    }


@dataclass
class AgentJobContext:
    dossiers: JobDossiers
    proposals: dict[str, dict[str, Any]] = field(default_factory=dict)
    approved_snippets: list[dict[str, Any]] = field(default_factory=list)
    line_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)

    def get_dossier(self, ghe_numero: str):
        return self.dossiers.by_numero(ghe_numero)

    def dispatch(self, name: str, args: dict[str, Any]) -> Any:
        handlers: dict[str, Callable[[dict[str, Any]], Any]] = {
            "list_ghes": lambda _a: list_ghe_summaries(self.dossiers),
            "get_ghe_dossier": self._get_ghe_dossier,
            "get_critical_questions": self._get_critical_questions,
            "get_current_aprho_line": self._get_current_aprho_line,
            "suggest_hazards": self._suggest_hazards,
            "search_knowledge": self._search_knowledge,
            "validate_line": lambda a: validate_line_fields(a),
            "propose_line": self._propose_line,
            "explain_line": self._explain_line,
        }
        if name not in handlers:
            return {"error": f"tool desconhecida: {name}"}
        try:
            return handlers[name](args or {})
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    def _get_ghe_dossier(self, args: dict[str, Any]) -> Any:
        d = self.get_dossier(str(args.get("ghe_numero", "")))
        if not d:
            return {"error": "GHE não encontrado"}
        return d.to_dict()

    def _get_critical_questions(self, args: dict[str, Any]) -> Any:
        d = self.get_dossier(str(args.get("ghe_numero", "")))
        if not d:
            return {"error": "GHE não encontrado"}
        return d.perguntas_criticas

    def _get_current_aprho_line(self, args: dict[str, Any]) -> Any:
        num = str(args.get("ghe_numero", ""))
        d = self.get_dossier(num)
        if not d:
            return {"error": "GHE não encontrado"}
        return {
            "pgr_atual": d.linha_psico_atual,
            "proposta": self.proposals.get(d.ghe_numero) or self.line_overrides.get(d.ghe_numero),
            "ge_preservar": d.ge_preservar,
            "ges_preservar": d.ges_preservar,
        }

    def _suggest_hazards(self, args: dict[str, Any]) -> Any:
        d = self.get_dossier(str(args.get("ghe_numero", "")))
        if not d:
            return {"error": "GHE não encontrado"}
        return d.hazards_candidatos

    def _search_knowledge(self, args: dict[str, Any]) -> Any:
        extra: list[tuple[str, str]] = []
        if self.approved_snippets:
            blob = "\n\n".join(
                f"## {s.get('role_hint', 'snippet')}\n"
                f"Causa: {s.get('causa_fonte', '')}\n"
                f"Controles: {s.get('controles', '')}\n"
                f"Agente: {s.get('agente', '')}"
                for s in self.approved_snippets[:40]
            )
            extra.append(("approved_snippets", blob))
        return search_knowledge(
            str(args.get("query", "")),
            limit=int(args.get("limit") or 5),
            extra_texts=extra or None,
        )

    def _propose_line(self, args: dict[str, Any]) -> Any:
        num = str(args.get("ghe_numero", ""))
        d = self.get_dossier(num)
        if not d:
            return {"error": "GHE não encontrado"}
        payload = {
            "agente": args.get("agente", ""),
            "exposicao": args.get("exposicao") or "Habitual e Intermitente",
            "causa_fonte": args.get("causa_fonte", ""),
            "trajetoria": args.get("trajetoria", ""),
            "danos": args.get("danos", ""),
            "controles": args.get("controles", ""),
        }
        check = validate_line_fields(payload)
        if not check["ok"]:
            return {"accepted": False, "validation": check}
        self.proposals[d.ghe_numero] = {
            **check["normalized"],
            "rationale": (args.get("rationale") or "")[:400],
        }
        return {"accepted": True, "ghe_numero": d.ghe_numero, "fields": self.proposals[d.ghe_numero]}

    def _explain_line(self, args: dict[str, Any]) -> Any:
        num = str(args.get("ghe_numero", ""))
        d = self.get_dossier(num)
        if not d:
            return {"error": "GHE não encontrado"}
        prop = self.proposals.get(d.ghe_numero) or self.line_overrides.get(d.ghe_numero)
        return {
            "ghe": {"numero": d.ghe_nome, "nome": d.ghe_nome, "setor": d.setor},
            "n": d.n_respondentes,
            "anonimato_ok": d.anonimato_ok,
            "hazards": d.hazards_candidatos,
            "perguntas_criticas": d.perguntas_criticas[:5],
            "proposta": prop,
            "pgr_atual": d.linha_psico_atual,
        }


def tool_result_message(tool_call_id: str, result: Any) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": json.dumps(result, ensure_ascii=False)[:12000],
    }
