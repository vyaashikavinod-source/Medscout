"""
Layer 1 — Knowledge Ingestion: PubMed

Pulls abstracts from the PubMed API via Biopython's Bio.Entrez wrapper.
Public, free, no PHI. Stores structured metadata (pub date, source, study
type) alongside the raw text so downstream layers never lose provenance.

Usage:
    python -m backend.ingestion.pubmed_client --query "chest pain differential diagnosis" --max-results 40
"""
from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from Bio import Entrez

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "pubmed"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# NCBI asks that you identify yourself. Set a real contact email via env var
# in production; a placeholder is fine for local prototyping.
Entrez.email = os.environ.get("PUBMED_CONTACT_EMAIL", "medscout-dev@example.com")
Entrez.tool = "MedScout"


@dataclass
class PubMedRecord:
    pmid: str
    title: str
    abstract: str
    journal: str
    pub_date: str
    study_type: str  # heuristically inferred, see _infer_study_type
    source: str = "PubMed"

    def to_dict(self) -> dict:
        return asdict(self)


def _infer_study_type(publication_types: list[str]) -> str:
    """PubMed exposes structured PublicationType tags — use them directly
    instead of guessing from free text, which is far more reliable than
    keyword-sniffing the abstract."""
    priority = [
        "Randomized Controlled Trial",
        "Systematic Review",
        "Meta-Analysis",
        "Practice Guideline",
        "Clinical Trial",
        "Review",
        "Case Reports",
        "Observational Study",
    ]
    for p in priority:
        if p in publication_types:
            return p
    return publication_types[0] if publication_types else "Unspecified"


def search_pubmed(query: str, max_results: int = 40) -> list[str]:
    handle = Entrez.esearch(db="pubmed", term=query, retmax=max_results, sort="relevance")
    record = Entrez.read(handle)
    handle.close()
    return record.get("IdList", [])


def fetch_records(pmids: Iterable[str], batch_size: int = 20) -> list[PubMedRecord]:
    pmids = list(pmids)
    records: list[PubMedRecord] = []

    for i in range(0, len(pmids), batch_size):
        batch = pmids[i : i + batch_size]
        handle = Entrez.efetch(db="pubmed", id=",".join(batch), rettype="abstract", retmode="xml")
        data = Entrez.read(handle)
        handle.close()

        for article in data.get("PubmedArticle", []):
            try:
                medline = article["MedlineCitation"]
                art = medline["Article"]
                pmid = str(medline["PMID"])
                title = str(art.get("ArticleTitle", ""))

                abstract_parts = art.get("Abstract", {}).get("AbstractText", [])
                abstract = " ".join(str(p) for p in abstract_parts)

                journal = str(art.get("Journal", {}).get("Title", ""))

                pub_date_raw = (
                    art.get("Journal", {})
                    .get("JournalIssue", {})
                    .get("PubDate", {})
                )
                pub_date = "-".join(
                    str(pub_date_raw[k]) for k in ("Year", "Month", "Day") if k in pub_date_raw
                ) or "unknown"

                pub_types = [str(t) for t in art.get("PublicationTypeList", [])]
                study_type = _infer_study_type(pub_types)

                if not abstract:
                    continue  # skip records with no usable text

                records.append(
                    PubMedRecord(
                        pmid=pmid,
                        title=title,
                        abstract=abstract,
                        journal=journal,
                        pub_date=pub_date,
                        study_type=study_type,
                    )
                )
            except (KeyError, IndexError):
                # Malformed / incomplete record — skip rather than crash the
                # whole ingestion run.
                continue

        time.sleep(0.34)  # stay under NCBI's 3 req/sec unauthenticated limit

    return records


def ingest(query: str, max_results: int = 40) -> Path:
    pmids = search_pubmed(query, max_results=max_results)
    records = fetch_records(pmids)

    out_path = DATA_DIR / f"{query.replace(' ', '_')[:60]}.jsonl"
    with out_path.open("w") as f:
        for r in records:
            f.write(json.dumps(r.to_dict()) + "\n")

    print(f"Fetched {len(records)} PubMed records for query={query!r} -> {out_path}")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest PubMed abstracts for a query.")
    parser.add_argument("--query", required=True)
    parser.add_argument("--max-results", type=int, default=40)
    args = parser.parse_args()
    ingest(args.query, args.max_results)
