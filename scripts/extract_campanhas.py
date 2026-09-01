from pathlib import Path
import json
from pypdf import PdfReader

BASE = Path(r"c:\Users\anjo_\OneDrive\Projetos-FabriaIA\psicossocial\modelos")
OUT = Path(r"c:\Users\anjo_\OneDrive\Projetos-FabriaIA\psicossocial\scripts\analysis_out")
OUT.mkdir(exist_ok=True)

for pdf in sorted(BASE.glob("Campanha-*.pdf")):
    reader = PdfReader(str(pdf))
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        pages.append({"page": i + 1, "text": text})
    full = "\n\n===== PAGE BREAK =====\n\n".join(p["text"] for p in pages)
    (OUT / f"{pdf.stem}.txt").write_text(full, encoding="utf-8")
    (OUT / f"{pdf.stem}.json").write_text(
        json.dumps(
            {
                "file": pdf.name,
                "n_pages": len(pages),
                "chars": len(full),
                "preview": full[:4000],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"{pdf.name}: {len(pages)} pages, {len(full)} chars")
    print(full[:1500])
    print("\n---\n")
