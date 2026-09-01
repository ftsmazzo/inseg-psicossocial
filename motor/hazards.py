from __future__ import annotations

from dataclasses import dataclass

from motor.models import QuestionScore
from motor.textutil import normalize


@dataclass(frozen=True)
class HazardTemplate:
    id: str
    # Fragmentos curtos no estilo APRHO Inseg (listas, não prosa)
    agente_frag: str
    causa_frag: str
    trajetoria_frag: str
    danos_frag: str
    controle_frag: str
    dimensao: str
    question_hints: tuple[str, ...]
    codigo_mte: str = ""
    # Só entra com pergunta explícita (assédio/violência) — nunca por soft-dimension
    requires_explicit_evidence: bool = False
    critical_pct_positiva_below: float = 50.0
    critical_pct_negativa_above: float = 60.0
    role_hints: tuple[str, ...] = ()


# Catálogo alinhado ao Guia MTE (PSICO-*) — exemplificativo; só com evidência.
HAZARDS: list[HazardTemplate] = [
    HazardTemplate(
        id="baixa_autonomia",
        codigo_mte="PSICO-006",
        agente_frag="Baixa Autonomia e Baixa Influência Sobre o Trabalho",
        causa_frag="Baixa Participação nas Decisões Operacionais, Pouca Influência Sobre Conteúdo e Sequência das Tarefas",
        trajetoria_frag="Organização do Trabalho, Autonomia Decisória",
        danos_frag="Estresse Ocupacional, Fadiga Mental, Desmotivação",
        controle_frag="Participação nas Decisões Operacionais, Clareza de Prioridades",
        dimensao="CONTROLE",
        question_hints=(
            "escolher o que",
            "escolher como",
            "possibilidade de aprender",
            "tomar iniciativas",
        ),
        role_hints=("auxiliar", "operador", "administrativ", "limpeza"),
    ),
    HazardTemplate(
        id="demandas_pressao_temporal",
        codigo_mte="PSICO-010",
        agente_frag="Demandas Quantitativas Elevadas e Pressão Temporal",
        causa_frag="Volume de Atividades, Prazos Reduzidos, Cumprimento Simultâneo de Demandas",
        trajetoria_frag="Organização do Trabalho, Ritmo Produtivo, Gestão de Prazos",
        danos_frag="Fadiga, Estresse Ocupacional, Redução da Concentração",
        controle_frag="Balanceamento de Demandas, Revisão de Metas e Prazos, Dimensionamento de Equipe, Pausas",
        dimensao="DEMANDA",
        question_hints=(
            "muita rapidez",
            "trabalhar intensamente",
            "exige demais",
            "tempo suficiente",
            "exigencias contraditorias",
            "exigências contraditórias",
        ),
        critical_pct_negativa_above=55.0,
        role_hints=("producao", "linha", "vendedor", "atendimento", "operador"),
    ),
    HazardTemplate(
        id="esforco_sobrecarga",
        codigo_mte="PSICO-010",
        agente_frag="Exigências de Esforço Elevadas e Sobrecarga de Responsabilidades",
        causa_frag="Concentração de Responsabilidades, Intensificação das Demandas, Carga de Trabalho",
        trajetoria_frag="Organização do Trabalho, Distribuição de Tarefas, Gestão de Pessoas",
        danos_frag="Fadiga, Desgaste Psicofisiológico, Estresse Ocupacional, Redução da Concentração",
        controle_frag="Distribuição das Responsabilidades, Gestão de Jornada, Apoio da Liderança, Pausas",
        dimensao="ESFORÇO",
        question_hints=(
            "muita responsabilidade",
            "exige cada vez mais",
            "pressionado pelo tempo",
            "carga pesada",
            "interrompido",
            "depois da hora",
            "esforco fisico",
            "esforço físico",
        ),
        critical_pct_negativa_above=55.0,
        role_hints=("encarregado", "lider", "supervisor", "motorista", "carreteiro"),
    ),
    HazardTemplate(
        id="reconhecimento_insuficiente",
        codigo_mte="PSICO-004",
        agente_frag="Reconhecimento e Recompensa Insuficientes",
        causa_frag="Desequilíbrio Esforço-Recompensa, Baixa Perspectiva de Progressão, Remuneração Percebida Inadequada",
        trajetoria_frag="Gestão de Pessoas, Reconhecimento, Desenvolvimento Profissional",
        danos_frag="Estresse Ocupacional, Desmotivação, Desgaste Emocional",
        controle_frag="Critérios Claros de Reconhecimento, Feedback da Liderança, Comunicação Sobre Progressão",
        dimensao="RECOMPENSA",
        question_hints=(
            "salario",
            "salário",
            "renda e adequado",
            "reconhecimento que mereco",
            "respeito e o reconhecimento",
            "promovido",
            "estabilidade no emprego",
            "mudancas nao desejadas",
            "mudanças não desejadas",
            "tratado injustamente",
        ),
        critical_pct_positiva_below=55.0,
    ),
    HazardTemplate(
        id="suporte_lideranca",
        codigo_mte="PSICO-005",
        agente_frag="Suporte Insuficiente da Liderança",
        causa_frag="Comunicação Gerencial Insuficiente, Baixo Apoio em Situações Difíceis",
        trajetoria_frag="Gestão de Pessoas, Relacionamento Hierárquico, Comunicação Organizacional",
        danos_frag="Estresse Ocupacional, Insegurança Quanto a Prioridades, Desgaste Emocional",
        controle_frag="Reuniões de Alinhamento, Canais de Suporte, Apoio da Liderança",
        dimensao="RECOMPENSA",
        question_hints=(
            "respeito que mereco dos meus chefes",
            "apoi o em situacoes dificeis",
            "apoio em situações difíceis",
            "contar com apoio",
        ),
        critical_pct_positiva_below=55.0,
    ),
    HazardTemplate(
        id="clareza_papel",
        codigo_mte="PSICO-003",
        agente_frag="Baixa Clareza de Papel ou Função",
        causa_frag="Atribuições Ambíguas, Sobreposição de Responsabilidades, Prioridades Não Definidas",
        trajetoria_frag="Organização do Trabalho, Gestão de Papéis",
        danos_frag="Insegurança Quanto a Prioridades, Tensão por Ambiguidade de Função, Fadiga Mental",
        controle_frag="Descrição Formal de Papéis, Matriz de Responsabilidades, Alinhamento de Prioridades",
        dimensao="CONTROLE",
        question_hints=(
            "sei o que esperam",
            "objetivos claros",
            "clareza",
            "papel",
            "função definida",
            "contradit",
        ),
        critical_pct_positiva_below=55.0,
        role_hints=("administrativ", "assistente", "analista"),
    ),
    HazardTemplate(
        id="justica_organizacional",
        codigo_mte="PSICO-007",
        agente_frag="Baixa Justiça Organizacional",
        causa_frag="Percepção de Tratamento Desigual, Critérios Opacos de Avaliação ou Progressão",
        trajetoria_frag="Gestão de Pessoas, Justiça Organizacional",
        danos_frag="Desmotivação, Desgaste Emocional, Queda de Engajamento",
        controle_frag="Critérios Escritos e Comunicados, Transparência de Processos, Canal Formal de Contestação",
        dimensao="RECOMPENSA",
        question_hints=(
            "tratado injustamente",
            "injust",
            "favoritism",
            "igualdade",
            "criterio justo",
        ),
        critical_pct_positiva_below=55.0,
    ),
    HazardTemplate(
        id="relacoes_trabalho",
        codigo_mte="PSICO-011",
        agente_frag="Más Relações Socioprofissionais no Trabalho",
        causa_frag="Conflitos Recorrentes, Baixa Cooperação, Clima de Tensão na Equipe",
        trajetoria_frag="Relações Socioprofissionais, Clima de Equipe",
        danos_frag="Tensão Relacional, Desgaste Emocional, Redução da Cooperação",
        controle_frag="Mediação Formal de Conflitos, Regras de Convivência, Mediação da Liderança",
        dimensao="RECOMPENSA",
        question_hints=(
            "colegas",
            "conflito",
            "relacionamento",
            "cooper",
            "respeito dos colegas",
            "ambiente de trabalho",
        ),
        critical_pct_positiva_below=55.0,
    ),
    HazardTemplate(
        id="mudanca_organizacional",
        codigo_mte="PSICO-002",
        agente_frag="Má Gestão de Mudanças Organizacionais",
        causa_frag="Mudanças sem Comunicação Adequada, Insegurança Quanto a Papéis e Processos",
        trajetoria_frag="Gestão de Mudanças, Comunicação Organizacional",
        danos_frag="Insegurança Organizacional, Tensão por Mudança, Desmotivação",
        controle_frag="Plano de Comunicação da Mudança, Participação dos Afetados, Acompanhamento Pós-Mudança",
        dimensao="RECOMPENSA",
        question_hints=(
            "mudancas nao desejadas",
            "mudanças não desejadas",
            "mudanca",
            "mudança",
            "reestrutura",
        ),
        critical_pct_positiva_below=55.0,
    ),
    HazardTemplate(
        id="comunicacao_dificil",
        codigo_mte="PSICO-012",
        agente_frag="Trabalho em Condições de Difícil Comunicação",
        causa_frag="Fluxo de Informação Insuficiente, Canais Ineficazes entre Áreas ou Turnos",
        trajetoria_frag="Comunicação Organizacional, Organização do Trabalho",
        danos_frag="Insegurança Quanto a Prioridades, Retrabalho, Fadiga Mental",
        controle_frag="Canais Formais de Passagem de Turno, Rituais de Alinhamento, Registros Compartilhados",
        dimensao="CONTROLE",
        question_hints=(
            "informado",
            "comunicacao",
            "comunicação",
            "nao sei o que acontece",
            "falta de informacao",
        ),
        critical_pct_positiva_below=55.0,
        role_hints=("turno", "plantao", "remoto"),
    ),
    HazardTemplate(
        id="trabalho_remoto_isolado",
        codigo_mte="PSICO-013",
        agente_frag="Trabalho Remoto ou Isolado com Baixo Suporte",
        causa_frag="Isolamento, Dificuldade de Acesso à Liderança, Sobrecarga sem Visibilidade",
        trajetoria_frag="Organização do Trabalho Remoto, Suporte Organizacional",
        danos_frag="Fadiga por Isolamento, Insegurança Quanto a Prioridades, Desgaste Emocional",
        controle_frag="Rotina de Check-in, Definição de Jornada e Disponibilidade, Canais de Suporte Remoto",
        dimensao="CONTROLE",
        question_hints=(
            "home office",
            "remoto",
            "teletrabalho",
            "isolado",
            "trabalho em casa",
        ),
        role_hints=("remoto", "home office", "teletrabalho"),
    ),
    HazardTemplate(
        id="subcarga",
        codigo_mte="PSICO-009",
        agente_frag="Baixa Demanda e Subcarga de Trabalho",
        causa_frag="Subutilização, Monotonia, Escassez de Tarefas Significativas",
        trajetoria_frag="Organização do Trabalho, Conteúdo da Tarefa",
        danos_frag="Desmotivação, Monotonia Ocupacional, Queda de Engajamento",
        controle_frag="Revisão de Atribuições, Enriquecimento de Tarefas, Redistribuição",
        dimensao="DEMANDA",
        question_hints=(
            "pouco trabalho",
            "monoton",
            "subutiliz",
            "tempo ocioso",
            "tarefas insuficientes",
        ),
        # Demanda baixa = pct baixa é risco (inverso do excesso)
        critical_pct_negativa_above=101.0,  # desliga regra "alta"
        requires_explicit_evidence=True,
    ),
    HazardTemplate(
        id="assedio_trabalho",
        codigo_mte="PSICO-001",
        agente_frag="Assédio Relacionado ao Trabalho",
        causa_frag="Condutas Abusivas Identificadas no Contexto Laboral",
        trajetoria_frag="Relações Socioprofissionais, Gestão de Pessoas",
        danos_frag="Desgaste Emocional, Insegurança no Ambiente de Trabalho, Queda de Engajamento",
        controle_frag="Canal Confidencial, Investigação Formal, Medidas de Proteção, Treinamento de Liderança",
        dimensao="RECOMPENSA",
        question_hints=(
            "assedio",
            "assédio",
            "humilha",
            "constrang",
            "ameac",
            "hostil",
        ),
        requires_explicit_evidence=True,
        critical_pct_positiva_below=60.0,
    ),
    HazardTemplate(
        id="violencia_trabalho",
        codigo_mte="PSICO-008",
        agente_frag="Exposição a Eventos Violentos ou Traumáticos no Trabalho",
        causa_frag="Situações de Violência ou Trauma Ocupacional Identificadas",
        trajetoria_frag="Segurança no Trabalho, Relações Socioprofissionais",
        danos_frag="Desgaste Emocional, Insegurança no Ambiente de Trabalho, Fadiga Mental",
        controle_frag="Protocolo de Resposta a Violência, Suporte Organizacional Pós-Evento, Prevenção Situacional",
        dimensao="ESFORÇO",
        question_hints=(
            "violencia",
            "violência",
            "agressao",
            "agressão",
            "ameaca fisica",
            "trauma",
        ),
        requires_explicit_evidence=True,
        critical_pct_negativa_above=50.0,
    ),
]


# Hazards que podem vir de dimensão fraca sem pergunta literal (núcleo CST clássico)
_SOFT_CORE_IDS = frozenset(
    {
        "baixa_autonomia",
        "demandas_pressao_temporal",
        "esforco_sobrecarga",
        "reconhecimento_insuficiente",
        "suporte_lideranca",
    }
)


def question_risk_score(q: QuestionScore) -> float:
    dim = q.dimensao.upper()
    if dim in {"CONTROLE", "RECOMPENSA"}:
        return max(0.0, 100.0 - q.pct)
    return q.pct


def is_question_critical(q: QuestionScore, hazard: HazardTemplate) -> bool:
    nq = normalize(q.text)
    if not any(normalize(h) in nq for h in hazard.question_hints):
        return False
    # Subcarga: demanda muito baixa
    if hazard.id == "subcarga":
        return q.dimensao.upper() == "DEMANDA" and q.pct <= 35.0
    if q.dimensao.upper() in {"CONTROLE", "RECOMPENSA"}:
        return q.pct <= hazard.critical_pct_positiva_below
    return q.pct >= hazard.critical_pct_negativa_above


def detect_hazards(
    perguntas: list[QuestionScore],
) -> list[tuple[HazardTemplate, list[QuestionScore], float]]:
    found: list[tuple[HazardTemplate, list[QuestionScore], float]] = []
    for hz in HAZARDS:
        matched = [q for q in perguntas if is_question_critical(q, hz)]
        if not matched:
            continue
        severity = sum(question_risk_score(q) for q in matched) / len(matched)
        found.append((hz, matched, severity))
    found.sort(key=lambda x: x[2], reverse=True)
    return found


def soft_hazards_from_dimensions(
    dimensoes: list[dict],
) -> list[tuple[HazardTemplate, list[QuestionScore], float]]:
    """Fallback fraco: só núcleo CST por dimensão — nunca assédio/violência."""
    by_id = {h.id: h for h in HAZARDS}
    out: list[tuple[HazardTemplate, list[QuestionScore], float]] = []
    for d in dimensoes:
        nome = (d.get("nome") or d.get("tipo") or "").upper()
        pct = float(d.get("pct") or 0)
        hid = None
        sev = 0.0
        if "DEMANDA" in nome and pct >= 55:
            hid, sev = "demandas_pressao_temporal", pct
        elif "ESFOR" in nome and pct >= 55:
            hid, sev = "esforco_sobrecarga", pct
        elif "CONTROLE" in nome and pct <= 50:
            hid, sev = "baixa_autonomia", 100.0 - pct
        elif "RECOMPENSA" in nome and pct <= 50:
            hid, sev = "reconhecimento_insuficiente", 100.0 - pct
        if hid and hid in by_id and hid in _SOFT_CORE_IDS:
            out.append((by_id[hid], [], sev))
    out.sort(key=lambda x: x[2], reverse=True)
    # dedupe
    seen: set[str] = set()
    uniq: list[tuple[HazardTemplate, list[QuestionScore], float]] = []
    for item in out:
        if item[0].id in seen:
            continue
        seen.add(item[0].id)
        uniq.append(item)
    return uniq


def rank_hazards_for_ghe(
    hazards_found: list[tuple[HazardTemplate, list[QuestionScore], float]],
    *,
    ghe_nome: str,
    setor: str,
    atividade: str,
    funcoes: list[str] | None = None,
    slice_dims: list[dict] | None = None,
    limit: int = 3,
) -> list[tuple[HazardTemplate, list[QuestionScore], float]]:
    """Reordena hazards da campanha pelo GHE (papel + dimensões do recorte)."""
    blob = normalize(
        f"{ghe_nome} {setor} {atividade} {' '.join(funcoes or [])}"
    )
    scored: list[tuple[HazardTemplate, list[QuestionScore], float]] = []
    for h, qs, sev in hazards_found:
        if h.requires_explicit_evidence and not qs:
            continue
        boost = 0.0
        for rh in h.role_hints:
            if normalize(rh) in blob:
                boost += 8.0
        for s in slice_dims or []:
            dem = float(s.get("demanda_pct") or 0)
            esf = float(s.get("esforco_pct") or 0)
            ctl = float(s.get("controle_pct") or 0)
            rec = float(s.get("recompensa_pct") or 0)
            if h.dimensao == "DEMANDA" and dem >= 55:
                boost += 12.0
            if h.dimensao == "ESFORÇO" and esf >= 55:
                boost += 12.0
            if h.dimensao == "CONTROLE" and ctl and ctl <= 50:
                boost += 12.0
            if h.dimensao == "RECOMPENSA" and rec and rec <= 50:
                boost += 12.0
        scored.append((h, qs, sev + boost))
    scored.sort(key=lambda x: x[2], reverse=True)
    return scored[:limit]


GENERIC_AGENTE_MARKERS = (
    "fatores psicossociais relacionados",
    "risco psicossocial",
    "fatores psicossociais",
)

CLINICAL_DANOS_MARKERS = (
    "burnout",
    "sindrome de burnout",
    "depressao",
    "transtorno de ansiedade",
    "transtorno depressivo",
    "cid-",
    "cid 10",
    "cid-10",
)


def has_clinical_danos(danos: str) -> bool:
    n = normalize(danos or "")
    return any(m in n for m in CLINICAL_DANOS_MARKERS)


JOB_TITLE_AGENTE_MARKERS = (
    "auxiliar de",
    "operador de",
    "assistente de",
    "encarregado",
    "lider de",
    "líder de",
    "soldador",
    "motorista",
    "carreteiro",
    "vendedor",
    "montador",
    "tecnico de",
    "técnico de",
    "analista",
    "supervisor",
    "gerente",
    "junior",
    "júnior",
    "pleno",
    "senior",
    "sênior",
)


def is_generic_agente(agente: str) -> bool:
    n = normalize(agente)
    return any(m in n for m in GENERIC_AGENTE_MARKERS)


def is_job_title_agente(agente: str) -> bool:
    """True se o campo Agente parece lista de cargos em vez de perigo psicossocial."""
    n = normalize(agente or "")
    if not n:
        return False
    hits = sum(1 for m in JOB_TITLE_AGENTE_MARKERS if m in n)
    if hits >= 2:
        return True
    if hits >= 1 and ("/" in (agente or "") or n.count(",") >= 1):
        return True
    if hits >= 1 and not any(
        k in n
        for k in (
            "demanda",
            "pressao",
            "autonomia",
            "esforco",
            "sobrecarga",
            "reconhecimento",
            "suporte",
            "psicossocial",
            "ritmo",
            "jornada",
            "assedio",
            "clareza",
            "justica",
            "relacao",
            "mudanca",
            "comunicacao",
            "remoto",
            "violencia",
            "subcarga",
        )
    ):
        return True
    return False


def join_frags(parts: list[str], limit: int = 4) -> str:
    seen: list[str] = []
    for p in parts:
        for bit in [b.strip() for b in p.split(",")]:
            if bit and bit not in seen:
                seen.append(bit)
            if len(seen) >= limit:
                return ", ".join(seen)
    return ", ".join(seen)
