# Skill NR-01 — Regras técnicas (psicossocial)

Política versionada para o Agente Orquestrador e o Chat do job.
Fonte: Skill Inseg `gerenciar-riscos-psicossociais-nr1` + Guia MTE FRPRT.

## Objetivo

Transformar evidências da campanha + descrição do GHE em preenchimento técnico utilizável no PGR (APRHO), sem prosa genérica e sem inventar fatos.

## Proibições absolutas

- Preencher só com: "Risco psicossocial", "Fatores psicossociais", "Estresse", "Carga mental", "Organização do trabalho" isolados.
- Diagnóstico clínico ou saúde mental de trabalhador individual (Burnout, Depressão, CID, transtornos). Em Danos use agravos ocupacionais SST.
- Inventar números, scores, GE/GES, n de respondentes.
- Assumir `score alto = grau alto no PGR`. Score CST é **evidência**, não grau (Guia MTE §18).
- Inventar fator (assédio, violência etc.) sem pergunta/evidência explícita.
- Completar lacuna técnica por plausibilidade quando `evidencia_nivel` for fraca/insuficiente.
- Correspondência silenciosa GHE↔cargo sem registrar evidência de match.
- Alterar layout do PGR (isso é papel do motor de escrita).

## Anonimato

- Política técnica: mínimo **5 respondentes** por recorte (não é número literal da NR-1).
- Se `n < 5`: status **Preliminar** (ou SUPRIMIDO_ANONIMATO se o usuário pedir).
- Nunca detalhar de forma que permita identificação individual.

## Unidade de análise (contrato Inseg)

- **1 linha** `Ergonômico (Psicossocial)` por **GHE** (não uma linha por perigo separado no APRHO Inseg).
- Agente pode listar 1–3 perigos específicos separados por vírgula.
- Causa/Fonte e Controles devem amarrar à **função/atividade daquele GHE**.

## Graus (GE / GES)

- Se o PGR já tem GE/GES na linha psicossocial: **preservar**.
- Só propor GE/GES novos se o dossiê indicar ausência.
- Potencial vem da matriz Inseg (motor calcula).

## Checklist antes de fechar a linha

1. Qual o fator psicossocial específico?
2. Onde (GHE/setor/função)?
3. Qual a causa/fonte operacional?
4. Quais danos plausíveis (não clínicos individuais)?
5. Quais controles concretos?
6. Qual evidência da campanha sustenta?

Se faltar evidência: deixar explícito no status Preliminar/Proposta — não inventar.
