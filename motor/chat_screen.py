"""Contexto da tela + respostas rápidas só para perguntas diretas de validação."""

from __future__ import annotations

import re
from typing import Any

from motor.agent_tools import validate_line_fields

# Perguntas diretas sim/não sobre qualidade do campo
VALIDATION_HINTS = (
    "genéric",
    "generico",
    "genérica",
    "generica",
    "vago",
    "vaga",
    "robót",
    "robot",
    "clínic",
    "clinic",
    "essa causa",
    "esse agente",
    "esses controles",
    "esses danos",
    "está ok",
    "esta ok",
    "valida",
    "validar",
)

# Pedidos conversacionais — NÃO usar resposta rápida programada
CONVERSATION_HINTS = (
    "objetiv",
    "filtr",
    "principal",
    "melhor",
    "melhore",
    "sugir",
    "sugest",
    "como fic",
    "o que ach",
    "explique",
    "por que",
    "porque",
    "ajuda",
    "analisa",
    "analise",
    "resum",
    "enxug",
    "prioriz",
    "aplica",
    "grava",
    "salva",
    "edita",
    "atualiz",
)


def build_screen_context(line: Any) -> dict[str, Any]:
    fields = {
        "agente": (line.agente or "").strip(),
        "exposicao": (line.exposicao or "Habitual e Intermitente").strip(),
        "causa_fonte": (line.causa_fonte or "").strip(),
        "trajetoria": (line.trajetoria or "").strip(),
        "danos": (line.danos or "").strip(),
        "controles": (line.controles or "").strip(),
        "ghe_numero": line.ghe_numero,
    }
    return {
        "ghe_numero": line.ghe_numero,
        "ghe_nome": line.ghe_nome,
        "status": line.status,
        "accepted": bool(line.accepted),
        "discarded": bool(line.discarded),
        "fields": fields,
        "validation": validate_line_fields(fields),
    }


def is_direct_validation_question(message: str) -> bool:
    """Só perguntas fechadas (está genérico? / valida?) — não consultoria."""
    msg = (message or "").lower().strip()
    if not msg:
        return False
    if any(h in msg for h in CONVERSATION_HINTS):
        return False
    if not any(h in msg for h in VALIDATION_HINTS):
        return False
    if "?" in msg:
        return True
    return any(
        p in msg
        for p in (
            "está genéric",
            "esta generic",
            "é genéric",
            "e generic",
            "está ok",
            "esta ok",
            "valida ess",
            "validar ess",
        )
    )


def _focus_field(message: str) -> str | None:
    msg = message.lower()
    if re.search(r"\bcausa\b", msg):
        return "causa_fonte"
    if "controle" in msg:
        return "controles"
    if "dano" in msg:
        return "danos"
    if "agente" in msg or "perigo" in msg:
        return "agente"
    if "trajet" in msg:
        return "trajetoria"
    return None


def _causa_looks_generic(text: str) -> bool:
    from motor.llm import is_generic_field
    from motor.textutil import normalize

    if is_generic_field(text, "causa"):
        return True
    n = normalize(text)
    if (text or "").count(",") >= 4 and len(text) > 120:
        return True
    if (text or "").count(",") >= 3 and "ritmo" in n and "repetitiv" in n:
        return True
    return False


def _field_looks_generic(field: str, text: str) -> bool:
    from motor.llm import is_generic_field

    if field == "causa_fonte":
        return _causa_looks_generic(text)
    if field == "controles":
        return is_generic_field(text, "controle")
    if field == "agente":
        from motor.hazards import is_generic_agente, is_job_title_agente

        t = (text or "").strip()
        return not t or is_generic_agente(t) or is_job_title_agente(t)
    if field == "danos":
        from motor.llm import is_robotic_danos

        return is_robotic_danos(text or "")
    return False


def _field_label(key: str) -> str:
    return {
        "causa_fonte": "Causa/Fonte",
        "controles": "Controles",
        "danos": "Danos",
        "agente": "Agente/Perigo",
        "trajetoria": "Trajetória",
    }.get(key, key)


def _errors_for_field(errors: list[str], field: str) -> list[str]:
    field_l = _field_label(field).lower()
    out: list[str] = []
    for err in errors:
        el = err.lower()
        if field in el or field_l.split("/")[0] in el:
            out.append(err)
    return out


def try_fast_screen_reply(message: str, screen: dict[str, Any]) -> str | None:
    """Resposta determinística só para pergunta fechada de validação."""
    if not is_direct_validation_question(message):
        return None

    v = screen.get("validation") or {}
    errors = list(v.get("errors") or [])
    warnings = list(v.get("warnings") or [])
    ghe = screen.get("ghe_numero", "")
    nome = screen.get("ghe_nome", "")
    fields = screen.get("fields") or {}
    focus = _focus_field(message)

    if focus:
        field_errors = _errors_for_field(errors, focus)
        text = (fields.get(focus) or "").strip()
        label = _field_label(focus)
        generic = bool(field_errors) or _field_looks_generic(focus, text)
        short = text if len(text) <= 280 else text[:277] + "…"
        if generic:
            reason = field_errors[0] if field_errors else (
                "texto em lista vaga — APRHO pede origem operacional do posto"
            )
            return (
                f"Sim — a {label.lower()} do GHE {ghe} parece genérica ou insuficiente: {reason}.\n\n"
                f"«{short}»\n\n"
                "Posso sugerir uma versão mais objetiva no chat; diga se quer que eu **aplique** na linha."
            )
        return (
            f"Não — a {label.lower()} do GHE {ghe} não acionou alerta de genérico.\n\n"
            f"«{short}»"
        )

    if errors:
        return (
            f"GHE {ghe} ({nome}): problemas — {'; '.join(errors)}.\n\n"
            "Posso sugerir ajustes no chat; peça para **aplicar** quando quiser gravar."
        )
    if warnings:
        return (
            f"GHE {ghe} ({nome}): atenção — {'; '.join(warnings)}."
        )
    return f"GHE {ghe} ({nome}): linha OK no validador Inseg."


def format_screen_system_block(screen: dict[str, Any]) -> str:
    fields = screen.get("fields") or {}
    v = screen.get("validation") or {}
    return (
        "\n\n=== CONTEXTO DA TELA (linha que o usuário está vendo) ===\n"
        f"GHE {screen.get('ghe_numero')} — {screen.get('ghe_nome')}\n"
        f"Status: {screen.get('status')} | aceita={screen.get('accepted')}\n"
        f"Agente: {fields.get('agente', '')}\n"
        f"Causa/Fonte: {fields.get('causa_fonte', '')}\n"
        f"Trajetória: {fields.get('trajetoria', '')}\n"
        f"Danos: {fields.get('danos', '')}\n"
        f"Controles: {fields.get('controles', '')}\n"
        f"Validação automática: ok={v.get('ok')} errors={v.get('errors')}\n"
    )
