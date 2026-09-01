from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from motor.parse_campanha import parse_campanha_cst
from motor.parse_pgr import parse_pgr_inseg
from motor.propose import propose
from motor.write_pgr import apply_lines_to_pgr


def run_pipeline(
    campanha_pdf: str | Path,
    pgr_docx: str | Path,
    out_dir: str | Path,
    *,
    write_docx: bool = True,
    approved_snippets: list | None = None,
    skip_ghe_numeros: set[str] | None = None,
    on_line: Callable | None = None,
    on_progress: Callable | None = None,
) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    campaign = parse_campanha_cst(campanha_pdf)
    pgr = parse_pgr_inseg(pgr_docx)

    # dossiês cedo — chat/resume não dependem do fim do LLM
    from motor.dossier import build_dossiers

    dossiers_early = build_dossiers(campaign, pgr)
    dossiers_path = out_dir / "dossiers.json"
    dossiers_path.write_text(
        json.dumps(dossiers_early.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    # progresso inicial (total real de GHEs)
    already = len(skip_ghe_numeros or set())
    total_g = len(dossiers_early.dossiers)
    (out_dir / "progress.json").write_text(
        json.dumps(
            {
                "done": already,
                "total": max(total_g, 1),
                "pct": round(100.0 * already / max(total_g, 1), 1),
                "ghe": "",
                "message": f"Campanha e PGR lidos — {total_g} GHE(s)",
                "phase": "filling",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    campanha_json = out_dir / "campanha.json"
    campanha_json.write_text(
        json.dumps(campaign.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    pgr_json = out_dir / "pgr_map.json"
    pgr_json.write_text(
        json.dumps(pgr.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    bundle, dossiers = propose(
        campaign,
        pgr,
        approved_snippets=approved_snippets,
        skip_ghe_numeros=skip_ghe_numeros,
        on_line=on_line,
        on_progress=on_progress,
    )

    proposal_path = out_dir / "proposal.json"
    # merge com linhas já existentes no checkpoint file se houver
    proposal_path.write_text(
        json.dumps(bundle.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    dossiers_path.write_text(
        json.dumps(dossiers.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    result = {
        "campaign_file": str(campanha_pdf),
        "pgr_file": str(pgr_docx),
        "n_ghes": len(pgr.ghes),
        "n_lines": len(bundle.lines),
        "unmatched_cargos": len(bundle.unmatched_cargos),
        "notes": bundle.notes,
        "proposal_json": str(proposal_path),
        "dossiers_json": str(dossiers_path),
    }

    if write_docx:
        out_docx = out_dir / f"{Path(pgr_docx).stem}-psicossocial.docx"
        stats = apply_lines_to_pgr(pgr_docx, out_docx, bundle.lines, only_accepted=True)
        result["output_docx"] = stats["output"]
        result["write_stats"] = stats

    return result
