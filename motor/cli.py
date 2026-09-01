from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from motor.pipeline import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Motor Campanha CST → PGR Inseg")
    parser.add_argument("--campanha", required=True, help="PDF da campanha CST")
    parser.add_argument("--pgr", required=True, help="DOCX do PGR Inseg")
    parser.add_argument("--out", required=True, help="Pasta de saída")
    parser.add_argument("--no-docx", action="store_true", help="Só gera JSON")
    args = parser.parse_args()

    result = run_pipeline(
        args.campanha,
        args.pgr,
        args.out,
        write_docx=not args.no_docx,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
