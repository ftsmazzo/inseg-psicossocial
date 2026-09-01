"""Motor mecânico + LLM só amarra causa/controles (skill + RAG)."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

from motor.agent_tools import TOOL_SCHEMAS, AgentJobContext, tool_result_message, validate_line_fields
from motor.dossier import GheDossier
from motor.hazards import HAZARDS, is_generic_agente, is_job_title_agente, join_frags
from motor.knowledge_index import load_system_skills, search_knowledge
from motor.llm import compose_deterministic, is_generic_field, is_robotic_danos, openrouter_enabled
from motor.models import QuestionScore


# LLM amarra causa, controles e danos SST ao GHE. Agente/trajetória ficam no motor.
FILL_SYSTEM = """
Você é redator técnico APRHO Inseg (psicossocial / SST), NÃO psicólogo clínico.
Base: Guia MTE FRPRT / NR-1 — condições de trabalho no GHE, nunca diagnóstico individual.

ARQUITETURA:
- MOTOR já fixou: agente, exposicao, trajetoria (não altere).
- Você reescreve: causa_fonte, controles e danos — específicos DESTE GHE/função.
- NÃO copie o mesmo texto de outro PGR ou de outro cargo.
- NÃO invente fator (assédio, violência etc.) sem evidência no dossiê.

EVIDÊNCIA (campo evidencia_nivel no dossiê):
- forte/moderada: amarre causa/controles às perguntas críticas + atividade.
- fraca/insuficiente: NÃO complete por plausibilidade. Causa e controles CURTOS,
  baseados só no que há. Se faltar base, use tom cauteloso compatível com revisão técnica
  (o status Preliminar será aplicado pelo motor).

DANOS — agravos OCUPACIONAIS SST com âncora do posto.
PROIBIDO: Burnout, Depressão, CID, transtorno, diagnóstico de consultório.
PROIBIDO trio vazio "Estresse Ocupacional, Fadiga Mental, Desmotivação" sem âncora.

CAUSA: origem operacional deste GHE. Proibido "rotina laboral" / "fatores organizacionais" isolados.
CONTROLES: medidas DIRETIVAS na organização do trabalho (Revisar metas, Redistribuir,
Dimensionar, Definir papéis, Pausas…). PROIBIDO como única resposta: palestra de resiliência,
meditação, "orientar a controlar o estresse", "Manter adequada…", "garantir comunicação…".

Se pattern_alerts no dossiê: amarre causa/controles ao padrão (ex.: demanda+controle+suporte).
Se missing_information: seja cauteloso; não invente fonte/circunstância ausente.
Se protective_signals: contextualize sem negar exposição existente.

Tom telegráfico inventário. Sem parágrafo.

JSON único:
{"causa_fonte":"...","controles":"...","danos":"..."}
""".strip()

BANNED_ECHO = (
    "supervisao de linha distribuicao de tarefas entre auxiliares",
    "supervisao de linha distribuicao entre auxiliares",
    "ritmo de linha tarefas repetitivas baixa autonomia sobre metodo",
    "planejamento de roteiros definicao de metas realistas",
)


def orchestrator_model() -> str:
    model = (
        os.getenv("OPENROUTER_ORCHESTRATOR_MODEL")
        or os.getenv("OPENROUTER_MODEL")
        or "google/gemini-2.5-flash"
    ).strip()
    if model and "/" not in model:
        model = f"openai/{model}"
    return model


def chat_model() -> str:
    model = (os.getenv("OPENROUTER_CHAT_MODEL") or orchestrator_model()).strip()
    if model and "/" not in model:
        model = f"openai/{model}"
    return model


def _chat_completion(
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict | None = "auto",
    temperature: float = 0.12,
    model: str | None = None,
    response_format: dict | None = None,
    timeout: int = 60,
    max_tokens: int | None = 700,
) -> dict[str, Any]:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY ausente")
    model = model or orchestrator_model()
    payload: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "messages": messages,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if tools:
        payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
    if response_format:
        payload["response_format"] = response_format

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://inseg.local",
            "X-OpenRouter-Title": "Inseg Orquestrador Psicossocial",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _parse_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {}
    return {}


def _questions_from_dossier(d: GheDossier) -> list[QuestionScore]:
    return [
        QuestionScore(
            text=q.get("text", ""),
            dimensao=q.get("dimensao", ""),
            media=0.0,
            pct=float(q.get("pct") or 0),
        )
        for q in d.perguntas_criticas
    ]


def _hazards_from_dossier(d: GheDossier):
    ids = {h["id"] for h in d.hazards_candidatos}
    found = [h for h in HAZARDS if h.id in ids]
    # Guia MTE: não inventar fatores se o dossiê não trouxe evidência
    return found


def draft_from_dossier(d: GheDossier) -> dict[str, str]:
    """Motor mecânico: Agente/trajetória/danos/causa/controles a partir de hazards + GHE."""
    return compose_deterministic(
        _hazards_from_dossier(d),
        ghe_nome=d.ghe_nome,
        setor=d.setor,
        atividade=d.atividade_resumo,
        perguntas=_questions_from_dossier(d),
        existing_causa="",
        existing_controles="",
        evidencia_nivel=getattr(d, "evidencia_nivel", "moderada"),
    )


def _skill_excerpt(limit: int = 3500) -> str:
    skills = load_system_skills()
    if len(skills) > limit:
        return skills[:limit] + "\n\n[skills truncadas]"
    return skills


def _rag_for_ghe(d: GheDossier, limit: int = 4) -> list[dict[str, str]]:
    query = f"{d.ghe_nome} {d.setor} {d.atividade_resumo} causa controles aprho"
    hits = search_knowledge(query, limit=limit)
    return [
        {"source": h["source"], "title": h["title"], "excerpt": h["excerpt"][:500]}
        for h in hits
    ]


def _compact_dossier(d: GheDossier) -> dict[str, Any]:
    return {
        "ghe": d.ghe_numero,
        "nome_ghe": d.ghe_nome,
        "setor": d.setor,
        "atividade": d.atividade_resumo[:280],
        "n_respondentes": d.n_respondentes,
        "evidencia_nivel": getattr(d, "evidencia_nivel", "moderada"),
        "pattern_alerts": getattr(d, "pattern_alerts", [])[:3],
        "protective_signals": getattr(d, "protective_signals", [])[:2],
        "missing_information": getattr(d, "missing_information", [])[:5],
        "recorte_campanha": d.ssos_slices[:3],
        "evidencias_campanha": {
            "hazards": [
                {
                    "id": h.get("id"),
                    "codigo_mte": h.get("codigo_mte"),
                    "agente": h.get("agente_frag"),
                    "causa_seed": next(
                        (x.causa_frag for x in HAZARDS if x.id == h.get("id")), ""
                    ),
                    "controle_seed": next(
                        (x.controle_frag for x in HAZARDS if x.id == h.get("id")), ""
                    ),
                }
                for h in d.hazards_candidatos
            ],
            "perguntas_criticas": [
                f"[{q.get('dimensao')} {q.get('pct')}%] {q.get('text')}"
                for q in d.perguntas_criticas[:5]
            ],
        },
        "pgr_tem_linha_psico": bool(d.linha_psico_atual),
        "lembrete_mte": (
            "Score CST é evidência, não grau PGR. "
            "Não inventar assédio/violência sem pergunta explícita. "
            "Risco coletivo GHE ≠ aptidão individual. "
            "Nunca sugerir encaminhamento obrigatório a psicólogo ou ASO."
        ),
    }


def _echo_banned(texts: dict[str, str]) -> list[str]:
    from motor.textutil import normalize

    blob = normalize(f"{texts.get('causa_fonte','')} {texts.get('controles','')}")
    hits = [b for b in BANNED_ECHO if b in blob]
    if hits:
        return ["eco de frase-modelo (proibido copiar exemplo/teste anterior)"]
    return []


def _parse_json_content(content: str) -> dict[str, Any] | None:
    content = re.sub(r"^```json\s*|\s*```$", "", (content or "").strip(), flags=re.I)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", content or "")
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None


def _lock_motor_fields(motor: dict[str, str], llm_bits: dict[str, Any] | None) -> dict[str, str]:
    """Agente/trajetória/exposição = motor. LLM pode melhorar causa/controles/danos SST."""
    out = {
        "agente": motor["agente"],
        "exposicao": "Habitual e Intermitente",
        "causa_fonte": motor["causa_fonte"],
        "trajetoria": motor["trajetoria"],
        "danos": motor["danos"],
        "controles": motor["controles"],
    }
    if not llm_bits:
        return out
    causa = (llm_bits.get("causa_fonte") or "").strip()
    controles = (llm_bits.get("controles") or "").strip()
    danos = (llm_bits.get("danos") or "").strip()
    if causa and not is_generic_field(causa, "causa"):
        out["causa_fonte"] = causa
    if controles and not is_generic_field(controles, "controle"):
        out["controles"] = controles
    if danos and not is_robotic_danos(danos):
        out["danos"] = danos
    return out


def _specificity_ok(texts: dict[str, str]) -> list[str]:
    errors = _echo_banned(texts)
    if is_robotic_danos(texts.get("danos") or ""):
        errors.append("danos genéricos/robóticos ou clínicos — amarre ao posto sem Burnout/Depressão")
    if is_generic_field(texts.get("causa_fonte") or "", "causa"):
        errors.append("causa ainda genérica")
    if is_generic_field(texts.get("controles") or "", "controle"):
        errors.append("controles ainda genéricos")
    return errors


def _fill_causa_controles(d: GheDossier, motor: dict[str, str], *, feedback: str = "") -> tuple[dict[str, Any] | None, str]:
    """LLM devolve causa_fonte + controles + danos SST amarrados ao GHE."""
    user = {
        "dossie": _compact_dossier(d),
        "motor_fixado": {
            "agente": motor["agente"],
            "exposicao": motor["exposicao"],
            "trajetoria": motor["trajetoria"],
            "danos_rascunho": motor["danos"],
            "causa_rascunho": motor["causa_fonte"],
            "controles_rascunho": motor["controles"],
        },
        "rag": _rag_for_ghe(d),
        "papel": (
            "Reescreva causa_fonte, controles e danos para ESTE GHE. "
            "Danos ocupacionais SST com âncora do posto (sem Burnout/Depressão). "
            "Controles diretivos citando a função/setor. Não copie bloco de outro PGR."
        ),
    }
    if feedback:
        user["correcao"] = feedback
    system = FILL_SYSTEM + "\n\n--- SKILLS ---\n" + _skill_excerpt()
    try:
        body = _chat_completion(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            tools=None,
            tool_choice=None,
            response_format={"type": "json_object"},
            max_tokens=500,
            temperature=0.15,
        )
        content = body["choices"][0]["message"].get("content") or ""
        parsed = _parse_json_content(content)
        if not parsed:
            return None, "error:json"
        return parsed, "ok"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        return None, f"error:HTTP {exc.code} {detail}"
    except Exception as exc:  # noqa: BLE001
        return None, f"error:{exc}"


def _force_hazard_agente(d: GheDossier, texts: dict[str, str]) -> dict[str, str]:
    out = dict(texts)
    hz = _hazards_from_dossier(d)
    if is_job_title_agente(out.get("agente") or "") or is_generic_agente(out.get("agente") or ""):
        if hz:
            out["agente"] = join_frags([h.agente_frag for h in hz], limit=3)
        elif not (out.get("agente") or "").strip():
            out["agente"] = "Exposição Psicossocial a Caracterizar — Validação Técnica"
    out["exposicao"] = "Habitual e Intermitente"
    if is_robotic_danos(out.get("danos") or ""):
        fixed = draft_from_dossier(d)
        out["danos"] = fixed["danos"]
    return out


def orchestrate_ghe(
    ctx: AgentJobContext,
    dossier: GheDossier,
    *,
    draft: dict[str, str] | None = None,
) -> tuple[dict[str, str], str]:
    """
    Motor: Agente/trajetória + rascunho de danos/causa/controles por perfil de função.
    LLM: refina causa, controles e danos SST (skill+RAG). Genérico/clínico → motor.
    Evidência insuficiente (Guia MTE): não chama LLM para inventar — fica o motor cauteloso.
    """
    motor = _force_hazard_agente(dossier, draft or draft_from_dossier(dossier))
    evid = getattr(dossier, "evidencia_nivel", "moderada")
    if evid == "insuficiente" or not dossier.hazards_candidatos:
        ctx.proposals[dossier.ghe_numero] = motor
        return motor, "orchestrator:evidencia_insuficiente"

    if not openrouter_enabled():
        return motor, "skipped"

    parsed, st = _fill_causa_controles(dossier, motor)
    if st.startswith("error"):
        return motor, f"orchestrator:fallback ({st[:120]})"

    texts = _lock_motor_fields(motor, parsed)
    texts = _force_hazard_agente(dossier, texts)
    check = validate_line_fields(texts)
    spec = _specificity_ok(texts)
    if check["ok"] and not spec:
        ctx.proposals[dossier.ghe_numero] = check["normalized"]
        return check["normalized"], "orchestrator:ok"

    feedback = (
        f"Rejeitado: {(check.get('errors') or []) + spec}. "
        "danos SST com âncora do posto (sem Burnout/Depressão); "
        "causa operacional; controles diretivos citando a função."
    )
    parsed2, st2 = _fill_causa_controles(dossier, motor, feedback=feedback)
    if st2.startswith("error"):
        ctx.proposals[dossier.ghe_numero] = motor
        return motor, f"orchestrator:motor ({st2[:80]})"

    texts2 = _force_hazard_agente(dossier, _lock_motor_fields(motor, parsed2))
    check2 = validate_line_fields(texts2)
    spec2 = _specificity_ok(texts2)
    if check2["ok"] and not spec2:
        ctx.proposals[dossier.ghe_numero] = check2["normalized"]
        return check2["normalized"], "orchestrator:retry_ok"

    for candidate, label in ((texts2, "retry"), (texts, "first"), (motor, "motor")):
        c = validate_line_fields(candidate)
        if c["ok"] and not _specificity_ok(candidate):
            ctx.proposals[dossier.ghe_numero] = c["normalized"]
            return c["normalized"], f"orchestrator:{label}_ok"
        if c["ok"] and label == "motor":
            ctx.proposals[dossier.ghe_numero] = c["normalized"]
            return c["normalized"], "orchestrator:motor_ok"

    ctx.proposals[dossier.ghe_numero] = motor
    return motor, "orchestrator:motor"


def _system_prompt_chat() -> str:
    skills = load_system_skills()
    if len(skills) > 9000:
        skills = skills[:9000] + "\n\n[skills truncadas]"
    return (
        "Você é consultor SST conversacional (APRHO Inseg / NR-01). "
        "NÃO é psicólogo clínico: sem Burnout/Depressão/CID em Danos.\n\n"
        "DOIS MODOS — respeite o pedido do usuário:\n"
        "1) CONVERSAR (padrão): opinião, ser objetivo, filtrar principais, explicar, "
        "sugerir melhorias, comparar com evidências.\n"
        "   → Responda no chat com análise clara. Pode sugerir texto revisado entre aspas.\n"
        "   → Use tools (get_ghe_dossier, validate_line, explain_line, search_knowledge) "
        "quando precisar de base.\n"
        "   → NÃO chame propose_line neste modo.\n\n"
        "2) APLICAR (só se pedido explícito): 'aplica', 'grava', 'salva', 'edita assim', "
        "'usa essa versão', 'atualiza a linha', 'pode gravar', 'confirma'.\n"
        "   → Chame propose_line com o texto acordado na conversa (sua sugestão ou pedido do usuário).\n"
        "   → Mantenha Agente/trajetória/exposição salvo se o usuário não pediu mudança.\n\n"
        "Se houver CONTEXTO DA TELA abaixo, use esses campos — nunca peça ao usuário repetir.\n"
        "Exposição: Habitual e Intermitente. Sem genéricos. Sem inventar números.\n\n"
        "LIMITES (Nota Técnica 4655/2024): este módulo é PGR coletivo por GHE. "
        "Nunca concluir aptidão/inaptidão, emitir ASO, exigir psicólogo ou transformar "
        "risco coletivo em diagnóstico individual. Se perguntarem sobre exame/ASO, "
        "explique que isso é competência médica fora deste fluxo.\n\n"
        f"{skills}"
    )
