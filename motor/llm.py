from __future__ import annotations

import os

from motor.hazards import HazardTemplate, join_frags
from motor.models import QuestionScore
from motor.textutil import normalize


GENERIC_CAUSA_MARKERS = (
    "lideranca de equipe controle da producao cumprimento de metas",
    "organizacao do trabalho",
    "fatores psicossociais",
    "gestao de pessoas ritmo produtivo e relacionamento",
    # prosa vaga vista em PGR ruim / saída LLM frouxa
    "organizacao e ritmo das atividades produtivas",
    "necessidade de atendimento as demandas",
    "atencao a qualidade e acabamento",
    "relacionamento socioprofissional",
    "distribuicao de tarefas e relacionamento",
)

GENERIC_CONTROLE_MARKERS = (
    "planejamento e balanceamento da producao distribuicao das responsabilidades",
    "organizacao das atividades distribuicao equilibrada das tarefas",
    "monitoramento periodico dos fatores psi",
    "apoio da gestao pausas reunioes de alinhamento",
    # bloco "Manter adequada..." não diretivo
    "manter adequada distribuicao",
    "garantir pausas",
    "manter comunicacao clara",
    "canais para comunicacao de dificuldades",
    "acompanhamento periodico dos fatores psicossociais",
    "preservar ao baixo nivel",
    # Guia MTE §22 — não substituem organização do trabalho
    "palestra",
    "resiliencia",
    "meditacao",
    "yoga",
    "mindfulness",
    "controlar o estresse",
    "gerenciar o estresse",
    "psicoterapia",
)


def openrouter_enabled() -> bool:
    return bool(os.getenv("OPENROUTER_API_KEY", "").strip())


def is_generic_field(text: str, kind: str = "causa") -> bool:
    n = normalize(text or "")
    if not n or len(n) < 8:
        return True
    markers = GENERIC_CAUSA_MARKERS if kind == "causa" else GENERIC_CONTROLE_MARKERS
    if any(m in n for m in markers):
        return True
    # frases-modelo Inseg muito repetidas
    if kind == "causa" and n.count(",") >= 3 and "cumprimento de metas" in n:
        return True
    if kind == "controle" and "monitoramento periodico" in n and "distribuicao" in n:
        return True
    return False


def _role_causa_bits(ghe_nome: str, setor: str, atividade: str) -> list[str]:
    blob = normalize(f"{ghe_nome} {setor} {atividade}")
    bits: list[str] = []
    if any(k in blob for k in ("encarregado", "lider", "supervisor", "gerente")):
        bits += [
            "Liderança de Equipe com Responsabilidade por Resultados",
            "Cobrança de Metas e Ritmo Produtivo",
        ]
    if any(k in blob for k in ("auxiliar de producao", "assistente de producao", "operador", "torref")):
        bits += [
            "Ritmo de Linha Produtiva",
            "Tarefas Repetitivas com Baixa Influência sobre o Método",
        ]
    if "esforco fisico" in blob or "peso" in blob or "amendoim" in blob or "torref" in blob:
        bits.append("Exigência Física Associada à Demanda Operacional")
    if any(k in blob for k in ("administrativ", "escritorio", "auxiliar administrativ")):
        bits += [
            "Baixa Autonomia sobre Conteúdo e Sequência das Tarefas",
            "Demandas Administrativas Simultâneas",
        ]
    if any(k in blob for k in ("motorista", "carreteiro", "vendedor externo", "transporte")):
        bits += [
            "Jornada Externa com Pressão de Prazos",
            "Baixa Previsibilidade da Rotina",
        ]
    if "limpeza" in blob:
        bits += [
            "Tarefas Rotineiras com Baixa Autonomia",
            "Exigências Físicas e Temporais da Rotina",
        ]
    if not bits and setor:
        bits.append(f"Organização das Atividades no Setor {setor.title()}")
    return bits


def _causa_from_questions(perguntas: list[QuestionScore], limit: int = 3) -> list[str]:
    mapping = [
        (("escolher o que", "escolher como"), "Baixa Autonomia para Definir O Que/Como Executar"),
        (("tempo suficiente", "muita rapidez", "intensamente"), "Tempo Insuficiente / Pressão de Ritmo"),
        (("muita responsabilidade", "exige cada vez mais"), "Sobrecarga de Responsabilidades"),
        (("depois da hora", "pressionado pelo tempo"), "Extensão de Jornada / Pressão Temporal"),
        (("salario", "salário", "renda"), "Desequilíbrio Esforço-Recompensa Remuneratória"),
        (("promovido", "estabilidade"), "Baixa Perspectiva de Progressão/Estabilidade"),
        (("apoi", "chefes"), "Suporte Gerencial Insuficiente"),
        (("interrompido",), "Interrupções Frequentes na Execução"),
        (("contradit",), "Exigências Contraditórias"),
        (("esforco fisico", "esforço físico"), "Elevada Exigência de Esforço Físico"),
    ]
    out: list[str] = []
    for q in sorted(perguntas, key=lambda x: x.pct if x.dimensao in {"CONTROLE", "RECOMPENSA"} else -x.pct):
        nq = normalize(q.text)
        for hints, label in mapping:
            if any(normalize(h) in nq for h in hints) and label not in out:
                # só se a pergunta for crítica
                if q.dimensao in {"CONTROLE", "RECOMPENSA"} and q.pct > 50:
                    continue
                if q.dimensao in {"ESFORÇO", "DEMANDA"} and q.pct < 55:
                    continue
                out.append(label)
                break
        if len(out) >= limit:
            break
    return out


def _role_profile(ghe_nome: str, setor: str, atividade: str) -> str:
    blob = normalize(f"{ghe_nome} {setor} {atividade}")
    if any(k in blob for k in ("encarregado", "lider", "supervisor", "gerente")):
        return "lideranca"
    if any(k in blob for k in ("motorista", "carreteiro", "transporte", "rota")):
        return "externo_rota"
    if any(k in blob for k in ("vendedor", "comercial", "visita")):
        return "externo_venda"
    if any(k in blob for k in ("administrativ", "escritorio", "financeiro", "rh")):
        return "admin"
    if "limpeza" in blob:
        return "limpeza"
    if any(k in blob for k in ("auxiliar", "operador", "assistente", "torref", "producao", "montador", "soldador")):
        return "linha"
    return "geral"


def _posto_label(ghe_nome: str, setor: str) -> str:
    nome = (ghe_nome or "").strip()
    if nome and len(nome) <= 48:
        return nome
    if setor:
        return f"posto do setor {setor.strip().title()}"
    return "posto"


def _danos_for_role(
    hazards: list[HazardTemplate],
    *,
    ghe_nome: str,
    setor: str,
    atividade: str,
) -> list[str]:
    """Agravos ocupacionais SST variados por perfil — sem diagnóstico clínico, sem trio fixo."""
    role = _role_profile(ghe_nome, setor, atividade)
    ids = {h.id for h in hazards}
    bits: list[str] = []

    if role == "lideranca":
        bits += [
            "Tensão por Responsabilidade por Resultados da Equipe",
            "Fadiga Mental Decisória",
            "Irritabilidade Associada à Cobrança de Metas",
        ]
    elif role == "linha":
        bits += [
            "Fadiga por Ritmo de Linha",
            "Redução da Atenção em Tarefa Repetitiva",
            "Tensão Muscular Associada à Pressão Temporal",
        ]
    elif role == "externo_rota":
        bits += [
            "Fadiga por Jornada Prolongada em Rota",
            "Redução da Atenção na Condução",
            "Tensão por Pressão de Prazo de Entrega",
        ]
    elif role == "externo_venda":
        bits += [
            "Tensão por Metas Comerciais",
            "Fadiga por Deslocamentos Frequentes",
            "Redução da Concentração sob Pressão de Resultado",
        ]
    elif role == "admin":
        bits += [
            "Fadiga Mental por Demandas Simultâneas",
            "Tensão por Prazos Documentais",
            "Redução da Concentração",
        ]
    elif role == "limpeza":
        bits += [
            "Fadiga Física e Temporal da Rotina",
            "Tensão por Múltiplas Áreas sob Prazo",
            "Irritabilidade por Baixa Autonomia",
        ]
    else:
        bits += [
            "Estresse Ocupacional Ligado à Organização do Posto",
            "Fadiga Mental",
            "Redução da Concentração",
        ]

    if "reconhecimento_insuficiente" in ids:
        bits.append("Desmotivação por Desequilíbrio Esforço-Recompensa")
    if "suporte_lideranca" in ids:
        bits.append("Insegurança Quanto a Prioridades e Apoio")
    if "baixa_autonomia" in ids and role in {"linha", "admin", "limpeza", "geral"}:
        bits.append("Desgaste por Baixa Influência sobre o Método")
    if "esforco_sobrecarga" in ids:
        bits.append("Desgaste Psicofisiológico por Sobrecarga")

    return bits


def _controles_for_hazards(
    hazards: list[HazardTemplate],
    ghe_nome: str,
    *,
    setor: str = "",
    atividade: str = "",
) -> list[str]:
    """Medidas diretivas amarradas ao posto — não bloco HR genérico."""
    role = _role_profile(ghe_nome, setor, atividade)
    posto = _posto_label(ghe_nome, setor)
    ids = {h.id for h in hazards}
    out: list[str] = []

    if role == "lideranca":
        if "demandas_pressao_temporal" in ids or "esforco_sobrecarga" in ids:
            out += [
                f"Revisão Formal de Metas e Prazos do {posto}",
                "Redistribuição de Tarefas entre Auxiliares em Caso de Pico",
                "Apoio Operacional à Liderança de Campo no Turno",
            ]
        if "suporte_lideranca" in ids or "reconhecimento_insuficiente" in ids:
            out.append("Alinhamento Registrado Liderança-Equipe com Feedback de Prioridades")
    elif role == "linha":
        if "demandas_pressao_temporal" in ids:
            out.append(f"Balanceamento de Carga/Ritmo na Linha do {posto}")
            out.append("Revisão de Metas de Produção Compatíveis com o Ciclo da Tarefa")
        if "baixa_autonomia" in ids:
            out.append("Participação do Posto na Definição do Método e Sequência")
        if "esforco_sobrecarga" in ids:
            out.append("Pausas Regulamentadas e Rotação de Posto em Tarefa Repetitiva")
    elif role == "externo_rota":
        out += [
            f"Revisão de Prazos e Janelas de Entrega do {posto}",
            "Balanceamento de Carga e Controle de Horas Extras em Rota",
            "Pausas Regulamentadas em Jornada Externa",
        ]
    elif role == "externo_venda":
        out += [
            f"Definição de Metas Realistas e Roteiro do {posto}",
            "Organização da Jornada de Visitas com Margem de Deslocamento",
            "Pausas Programadas entre Visitas",
        ]
    elif role == "admin":
        out += [
            f"Priorização Escrita de Demandas do {posto}",
            "Dimensionamento de Prazos Documentais e Filas de Trabalho",
        ]
        if "baixa_autonomia" in ids:
            out.append("Clareza de Papéis e Autonomia para Sequenciar Tarefas")
    elif role == "limpeza":
        out += [
            f"Dimensionamento de Áreas e Tempo do {posto}",
            "Definição Clara de Roteiro e Prioridades Diárias",
            "Pausas Regulamentadas na Rotina Intensiva",
        ]
    else:
        if "demandas_pressao_temporal" in ids:
            out.append(f"Revisão de Metas e Prazos do {posto}")
        if "esforco_sobrecarga" in ids:
            out.append(f"Redistribuição Formal de Responsabilidades no {posto}")
        if "baixa_autonomia" in ids:
            out.append(f"Clareza Escrita de Prioridades do {posto}")

    if "reconhecimento_insuficiente" in ids and role not in {"lideranca"}:
        out.append(f"Critérios Transparentes de Reconhecimento Aplicados ao {posto}")
    if "suporte_lideranca" in ids and role != "lideranca":
        out.append(f"Canal Formal de Apoio da Liderança ao {posto}")

    if not out:
        out = [f"{h.controle_frag.split(',')[0].strip()} — {posto}" for h in hazards][:3]
    return out


def is_robotic_danos(danos: str) -> bool:
    """True se danos são o trio genérico repetido ou diagnóstico clínico."""
    from motor.hazards import has_clinical_danos

    if has_clinical_danos(danos):
        return True
    n = normalize(danos or "")
    if not n or len(n) < 12:
        return True
    # blocos que o motor antigo/LLM repete em todo PGR
    robotic = (
        "estresse ocupacional fadiga mental desmotivacao",
        "estresse ocupacional fadiga mental irritabilidade",
        "sindrome de burnout ansiedade depressao",
        "burnout ansiedade depressao",
        "estresse ocupacional fadiga mental alteracoes do sono",
    )
    compact = n.replace(",", " ")
    compact = " ".join(compact.split())
    if any(r in compact for r in robotic):
        # só marca robótico se NÃO tiver âncora de posto/função
        anchors = (
            "linha",
            "rota",
            "meta",
            "posto",
            "equipe",
            "jornada",
            "document",
            "visita",
            "conduc",
            "resultado",
            "metodo",
            "turno",
            "entrega",
        )
        if not any(a in n for a in anchors):
            return True
    return False


def compose_deterministic(
    hazards: list[HazardTemplate],
    *,
    ghe_nome: str = "",
    setor: str = "",
    atividade: str = "",
    perguntas: list[QuestionScore] | None = None,
    existing_causa: str = "",
    existing_controles: str = "",
    evidencia_nivel: str = "moderada",
) -> dict[str, str]:
    perguntas = perguntas or []
    if not hazards:
        posto = _posto_label(ghe_nome, setor)
        return {
            "agente": "Exposição Psicossocial a Caracterizar — Validação Técnica",
            "exposicao": "Habitual e Intermitente",
            "causa_fonte": (
                "INFORMAÇÃO INSUFICIENTE — REQUER VALIDAÇÃO TÉCNICA "
                f"({posto})"
            ),
            "trajetoria": "Organização do Trabalho, Gestão de Pessoas",
            "danos": "Agravos Ocupacionais a Definir na Validação Técnica",
            "controles": (
                f"Caracterizar Fonte, Exposição e Controles Organizacionais do {posto} "
                "com Validação Técnica"
            ),
        }

    agente = join_frags([h.agente_frag for h in hazards], limit=3)

    causa_bits = _role_causa_bits(ghe_nome, setor, atividade)
    causa_bits += _causa_from_questions(perguntas, limit=3)
    causa_bits += [h.causa_frag.split(",")[0].strip() for h in hazards[:2]]
    if existing_causa and not is_generic_field(existing_causa, "causa"):
        causa_bits.insert(0, existing_causa)
    if evidencia_nivel in {"fraca", "insuficiente"}:
        causa_bits = causa_bits[:3]
    causa = join_frags(causa_bits, limit=5 if evidencia_nivel == "forte" else 4)

    trajetoria = join_frags([h.trajetoria_frag for h in hazards], limit=4)
    danos = join_frags(
        _danos_for_role(hazards, ghe_nome=ghe_nome, setor=setor, atividade=atividade),
        limit=4,
    )

    controle_bits = _controles_for_hazards(
        hazards, ghe_nome, setor=setor, atividade=atividade
    )
    if existing_controles and not is_generic_field(existing_controles, "controle"):
        controle_bits = [existing_controles] + controle_bits
    controles = join_frags(controle_bits, limit=5)

    return {
        "agente": agente,
        "exposicao": "Habitual e Intermitente",
        "causa_fonte": causa,
        "trajetoria": trajetoria,
        "danos": danos,
        "controles": controles,
    }
