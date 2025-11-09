from pathlib import Path
import re

from docx import Document


def heading_level(paragraph) -> int | None:
    style_name = getattr(paragraph.style, "name", "") or ""
    m = re.match(r"Heading\s+(\d+)$", style_name.strip(), flags=re.IGNORECASE)
    return int(m.group(1)) if m else None


def extract_headings(docx_path: Path) -> list[tuple[int, str]]:
    doc = Document(str(docx_path))
    items: list[tuple[int, str]] = []
    for p in doc.paragraphs:
        text = (p.text or "").strip()
        if not text:
            continue
        lvl = heading_level(p)
        if lvl:
            items.append((lvl, text))
    return items


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    src = root / "[Touseef Asif, Ozair Ilyas] FinalYearProject Documentation.docx"
    out = root / "docs" / "Touseef_headings.txt"

    if not src.exists():
        raise SystemExit(f"File not found: {src}")

    headings = extract_headings(src)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for lvl, text in headings:
            f.write(f"H{lvl}\t{text}\n")
    print(f"Saved: {out} ({len(headings)} headings)")


