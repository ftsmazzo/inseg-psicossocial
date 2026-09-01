"""Índice local (RAG leve) sobre knowledge/ — busca por palavras, sem dependências pesadas."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from motor.textutil import normalize


def knowledge_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "knowledge"


CORPUS_FILES = (
    "skill_nr01_regras.md",
    "skill_guia_mte_nr01.md",
    "skill_inseg_aprh.md",
    "skill_perigos_controles.md",
    "corpus_mte_frprt.md",
    "corpus_sesi_frprt.md",
    "gold_examples.md",
    "inseg_aprh_style.md",
)


@dataclass
class KnowledgeChunk:
    source: str
    title: str
    text: str


_CACHE: list[KnowledgeChunk] | None = None


def _split_chunks(source: str, raw: str) -> list[KnowledgeChunk]:
    parts = re.split(r"\n(?=#{1,3}\s)", raw)
    chunks: list[KnowledgeChunk] = []
    for part in parts:
        part = part.strip()
        if len(part) < 40:
            continue
        first = part.split("\n", 1)[0].strip("# ").strip()
        chunks.append(KnowledgeChunk(source=source, title=first[:120], text=part[:1800]))
    if not chunks and raw.strip():
        chunks.append(KnowledgeChunk(source=source, title=source, text=raw[:1800]))
    return chunks


def load_chunks(extra_texts: list[tuple[str, str]] | None = None) -> list[KnowledgeChunk]:
    global _CACHE
    if _CACHE is None:
        chunks: list[KnowledgeChunk] = []
        base = knowledge_dir()
        for name in CORPUS_FILES:
            path = base / name
            if path.exists():
                chunks.extend(_split_chunks(name, path.read_text(encoding="utf-8")))
        _CACHE = chunks
    out = list(_CACHE)
    if extra_texts:
        for src, text in extra_texts:
            out.extend(_split_chunks(src, text))
    return out


def reload_index() -> None:
    global _CACHE
    _CACHE = None


def search_knowledge(
    query: str,
    *,
    limit: int = 5,
    extra_texts: list[tuple[str, str]] | None = None,
) -> list[dict]:
    q = normalize(query or "")
    if not q:
        return []
    tokens = [t for t in re.split(r"\W+", q) if len(t) > 2]
    if not tokens:
        tokens = [q]
    scored: list[tuple[float, KnowledgeChunk]] = []
    for ch in load_chunks(extra_texts):
        blob = normalize(f"{ch.title} {ch.text}")
        score = 0.0
        for t in tokens:
            if t in blob:
                score += 1.0 + blob.count(t) * 0.1
        if score > 0:
            scored.append((score, ch))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {
            "source": ch.source,
            "title": ch.title,
            "excerpt": ch.text[:700],
            "score": round(sc, 2),
        }
        for sc, ch in scored[:limit]
    ]


def load_system_skills() -> str:
    """Concatena skills principais para o system prompt (NR-01 + Guia MTE + Inseg)."""
    base = knowledge_dir()
    parts: list[str] = []
    for name in (
        "skill_nr01_regras.md",
        "skill_guia_mte_nr01.md",
        "skill_inseg_aprh.md",
        "skill_perigos_controles.md",
    ):
        p = base / name
        if p.exists():
            parts.append(p.read_text(encoding="utf-8"))
    return "\n\n---\n\n".join(parts) if parts else ""
