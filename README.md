# Inseg Psicossocial — Campanha CST → PGR Inseg

Sistema web da Inseg: sobe a campanha (PDF CST) + PGR (DOCX Inseg), propõe **uma linha Ergonômico (Psicossocial) por GHE**, permite revisão técnica e gera o PGR atualizado.

**Dor que resolve:** evitar colar o PGR inteiro no ChatGPT (cota, texto genérico, “Agente” virando cargo). O motor fatia evidência → decide o preenchimento → grava o Word.

---

## Stack (hoje)

| Camada | Onde | Papel |
|---|---|---|
| **Motor** | `motor/` | Parse CST/PGR, dossiê por GHE, hazards, proposta, escrita DOCX |
| **Knowledge** | `knowledge/` | Skills NR-01 / Inseg APRH / perigos→controles + corpus + gold (RAG leve) |
| **API** | `backend/` | FastAPI + SQLAlchemy + JWT |
| **UI** | `frontend/` | React (Vite) — Jobs → Upload → Processar (barra) → Revisão → Chat → Download |
| **DB local** | SQLite | `DATABASE_URL=sqlite:///./psicossocial.db` (Windows) |
| **DB prod** | Postgres 16 | via `docker-compose.yml` / EasyPanel |

Arquivos de job ficam em `backend/data/jobs/{id}/` (uploads, `progress.json`, `proposal.json`, DOCX).

---

## Login bootstrap

- E-mail: `admin@inseg.local`
- Senha: `inseg123`

Troque em produção (`BOOTSTRAP_ADMIN_*`, `SECRET_KEY`).

---

## Arquitetura do preenchimento (como funciona hoje)

```
PDF campanha + DOCX PGR
        │
        ▼
 parse_campanha + parse_pgr → build_dossiers (1 dossiê / GHE)
        │
        ▼
 MOTOR MECÂNICO (compose_deterministic)
   • Agente = perigo(s) do catálogo (nunca cargo/função)
   • Trajetória / Exposição (Habitual e Intermitente)
   • Danos SST por perfil de função (linha ≠ encarregado ≠ motorista…)
   • Rascunho de causa + controles amarrados ao posto
        │
        ▼
 LLM (OpenRouter) — só refina causa_fonte, controles e danos
   • System = skills + dossiê compacto + RAG (`knowledge/`)
   • NÃO manda no Agente/trajetória
   • Sem chave / falha / saída genérica → fica o motor
        │
        ▼
 Validação (anti-genérico, anti-cargo no Agente, anti-diagnóstico clínico)
        │
        ▼
 Checkpoint linha a linha → revisão UI → write DOCX
```

### Regras de conteúdo (SST, não consultório)

- **Agente** = fator/perigo psicossocial (ex.: Demandas Quantitativas e Pressão Temporal). Proibido lista de cargos.
- **Causa/Fonte** = origem operacional **deste** GHE (ritmo, metas, jornada, autonomia…).
- **Danos** = agravos **ocupacionais** amarrados ao posto. **Proibido** Burnout, Depressão, CID, transtorno de consultório. **Proibido** repetir o mesmo trio genérico em todo GHE/PGR.
- **Controles** = medidas **diretivas** citando o posto (Revisar / Redistribuir / Definir…). Proibido prosa vaga (“Manter adequada distribuição…”, “garantir comunicação…”).
- **GE/GES**: preserva do PGR quando existem; Potencial pela matriz Inseg.
- **Insert**: se o GHE não tem linha psicossocial, a proposta cria (não só atualiza).
- Anonimato técnico: `n < 5` → status Preliminar.

### Modelo LLM (OpenRouter)

Padrão atual (custo/benefício vs `gpt-4o-mini`):

```env
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_MODEL=google/gemini-2.5-flash
OPENROUTER_ORCHESTRATOR_MODEL=google/gemini-2.5-flash
OPENROUTER_CHAT_MODEL=google/gemini-2.5-flash
```

Sem chave → só motor determinístico.

O **chat do job** usa o mesmo modelo + tools (`list_ghes`, `get_ghe_dossier`, `search_knowledge`, `validate_line`, `propose_line`, …).

### Knowledge / RAG

| Arquivo | Uso |
|---|---|
| `skill_nr01_regras.md` | Proibições NR-01, anonimato, GE/GES |
| `skill_guia_mte_nr01.md` | Guia MTE FRPRT operacional (catálogo PSICO, anti-inventar, hierarquia de controles) |
| `skill_inseg_aprh.md` | Contrato de colunas e anti-genérico Inseg |
| `skill_perigos_controles.md` | Catálogo hazard → causa/controle (PSICO-001…013) |
| `gold_examples.md` | Exemplos de especificidade (inspiração, não eco) |
| `corpus_mte_frprt.md` / `corpus_sesi_frprt.md` | Grounding |
| `inseg_aprh_style.md` | Estilo telegráfico |

Especificação completa de domínio (GRO): `modelos/ESPECIFICACAO_SISTEMA_NR01_RISCOS_PSICOSSOCIAIS_CURSOR.md` — usada como regra de domínio; o produto atual implementa o **recorte CST→PGR**, não o SaaS GRO inteiro.

Índice local: `motor/knowledge_index.py` (busca por tokens, sem vector DB).

### Classificação (Guia MTE no motor)

- Catálogo ampliado com códigos **PSICO-***; assédio/violência **só com evidência explícita**.
- Hazards **reordenados por GHE** (papel + dimensões do recorte), não o mesmo top-3 cego da empresa.
- `evidencia_nivel`: forte / moderada / fraca / insuficiente → Preliminar + “INFORMAÇÃO INSUFICIENTE…” quando fraco; sem LLM inventando.
- Controles tipo resiliência/palestra/meditação rejeitados.

---

## Fluxo do usuário (UI)

1. Login  
2. Novo job  
3. Upload PDF campanha + DOCX PGR  
4. **Processar** (background) — barra de progresso (`GET /api/jobs/{id}/progress`), checkpoint por GHE (dá para retomar se interromper)  
5. Revisar linhas (Aceitar / Editar / Descartar); Aceitar todas; Potencial recalcula com a matriz  
6. Chat opcional no job (agente com tools)  
7. Gerar PGR → Baixar DOCX  

Rotas UI: `/login`, `/`, `/jobs/:id`.

---

## API (resumo)

| Método | Rota | Função |
|---|---|---|
| POST | `/api/auth/login` | JWT |
| GET | `/api/auth/me` | Usuário |
| GET/POST | `/api/jobs` | Listar / criar |
| GET | `/api/jobs/{id}` | Detalhe + linhas |
| POST | `/api/jobs/{id}/upload` | Campanha + PGR |
| POST | `/api/jobs/{id}/process` | Processar (async + progresso) |
| GET | `/api/jobs/{id}/progress` | `%`, GHE atual, mensagem |
| PATCH | `/api/jobs/{id}/lines/{line_id}` | Editar / status da linha |
| POST | `/api/jobs/{id}/accept-all` | Aceitar todas |
| POST | `/api/jobs/{id}/chat` | Agente do job |
| POST | `/api/jobs/{id}/generate` | Escrever DOCX |
| GET | `/api/jobs/{id}/download` | Baixar |
| GET | `/api/health` | Healthcheck |

Docs interativas: `http://127.0.0.1:8000/docs`.

---

## Desenvolvimento local

### 1) Motor só (CLI, sem UI)

```bash
python -m motor.cli --campanha modelos/Campanha-Amendo.pdf --pgr modelos/PGR-Amendo.docx --out out/amendo
```

### 2) API

> Windows / Python local: **SQLite** por padrão. Docker/EasyPanel: **PostgreSQL**.

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\activate   # Windows
pip install -r requirements.txt
copy .env.example .env
# preencha OPENROUTER_API_KEY se for usar LLM
uvicorn app.main:app --reload --app-dir .
```

API: `http://127.0.0.1:8000`

### 3) Frontend

```bash
cd frontend
npm install
npm run dev
```

UI: `http://127.0.0.1:5173` (proxy `/api` → backend).

### 4) Postgres opcional (Compose)

```bash
docker compose up -d db
```

Ajuste `DATABASE_URL` no `.env` se for usar o Postgres do Compose em vez do SQLite.

---

## EasyPanel / produção

1. Serviço Compose apontando para este repositório (`docker-compose.yml`: `db` + `api`).  
2. Porta **8000** (ou domínio no EasyPanel).  
3. Secrets: `SECRET_KEY`, `BOOTSTRAP_ADMIN_PASSWORD`, `OPENROUTER_API_KEY`, `DATABASE_URL` se Postgres for externo.  
4. Volume `appdata` → uploads e DOCX.  
5. Build da imagem inclui a UI estática em `backend/static`.

---

## Mapa rápido do código

```
motor/
  parse_campanha.py   # PDF CST → CampaignData
  parse_pgr.py        # DOCX Inseg → GHEs / APRHO / matriz
  dossier.py          # dossiê por GHE + hazards da campanha
  hazards.py          # catálogo + anti-cargo / anti-clínico no Agente/Danos
  llm.py              # motor mecânico por perfil + anti-genérico
  orchestrator.py     # fill (Gemini) + chat model helpers
  propose.py          # 1 ProposedLine / GHE + checkpoint callback
  write_pgr.py        # aplica linhas no DOCX
  chat_agent.py       # tool-loop do chat
  knowledge_index.py  # RAG leve
  pipeline.py         # orquestra parse → propose → artifacts

backend/app/
  routers/jobs.py     # process async, progress, chat, generate
  services.py         # chama o motor, persiste linhas
  config.py           # Settings + export OPENROUTER_* para o motor

frontend/src/pages/
  Jobs.jsx            # lista
  JobWorkspace.jsx    # upload, progresso, revisão, chat, download
```

---

## Observações operacionais

- **Não reinicie a API** no meio de um `process` longo: mata o job. Há checkpoint, mas tokens já gastos não voltam.  
- Processamento é **por GHE**; PGR grande = muitas chamadas LLM (custo escala com nº de GHEs).  
- Modelo caro (`gpt-4o` etc.) sem teto de custo já queimou saldo em jobs grandes — o default atual é Flash de propósito.  
- Zerar jobs de teste: apagar registros `Job` / `JobLine` / `ApprovedSnippet` e pastas `backend/data/jobs/*` (não há botão “wipe” na UI hoje).
