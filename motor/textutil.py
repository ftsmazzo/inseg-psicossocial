from __future__ import annotations

import re
import unicodedata


def strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize(text: str) -> str:
    t = strip_accents(text or "").lower()
    t = t.replace("/", " ")
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def parse_float_br(text: str) -> float | None:
    if text is None:
        return None
    t = str(text).strip()
    t = t.replace("%", "").replace(" ", "")
    t = t.replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", t)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def tokenize(text: str) -> set[str]:
    stop = {
        "de",
        "da",
        "do",
        "das",
        "dos",
        "e",
        "a",
        "o",
        "as",
        "os",
        "em",
        "no",
        "na",
        "i",
        "ii",
        "iii",
        "junior",
        "pleno",
        "senior",
        "jr",
        "sr",
    }
    return {tok for tok in normalize(text).split() if tok and tok not in stop and len(tok) > 1}


def token_overlap(a: str, b: str) -> float:
    ta, tb = tokenize(a), tokenize(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    return inter / max(len(ta), len(tb))


def best_overlap(query: str, candidates: list[str]) -> tuple[float, str | None]:
    best = 0.0
    best_c = None
    for c in candidates:
        s = token_overlap(query, c)
        # also try substring boost
        nq, nc = normalize(query), normalize(c)
        if nq and nc and (nq in nc or nc in nq):
            s = max(s, 0.85)
        if s > best:
            best = s
            best_c = c
    return best, best_c
