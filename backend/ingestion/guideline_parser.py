"""
Layer 1 — Knowledge Ingestion: public clinical guideline PDFs (CDC/WHO/NIH).

Uses pdfplumber for text extraction. Guideline PDFs are generally
public-domain, well-structured government/institutional documents, so a
straightforward text extraction + page-level metadata approach is enough —
no OCR fallback needed for the prototype scope.

Usage:
    python -m backend.ingestion.guideline_parser --pdf data/guidelines/cdc_chest_pain.pdf --source CDC
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import pdfplumber

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "guidelines"
DATA_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class GuidelinePage:
    source: str          # e.g. "CDC", "WHO", "NIH"
    document_title: str
    page_number: int
    text: str

    def to_dict(self) -> dict:
        return asdict(self)


def parse_guideline_pdf(pdf_path: str, source: str, document_title: str | None = None) -> list[GuidelinePage]:
    pdf_path = Path(pdf_path)
    document_title = document_title or pdf_path.stem.replace("_", " ")

    pages: list[GuidelinePage] = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            text = text.strip()
            if not text:
                continue
            pages.append(
                GuidelinePage(
                    source=source,
                    document_title=document_title,
                    page_number=i,
                    text=text,
                )
            )
    return pages


def ingest(pdf_path: str, source: str, document_title: str | None = None) -> Path:
    pages = parse_guideline_pdf(pdf_path, source, document_title)
    out_path = DATA_DIR / f"{Path(pdf_path).stem}.jsonl"
    with out_path.open("w") as f:
        for p in pages:
            f.write(json.dumps(p.to_dict()) + "\n")
    print(f"Parsed {len(pages)} pages from {pdf_path} ({source}) -> {out_path}")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parse a public guideline PDF into structured text.")
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--source", required=True, choices=["CDC", "WHO", "NIH"])
    parser.add_argument("--title", default=None)
    args = parser.parse_args()
    ingest(args.pdf, args.source, args.title)
