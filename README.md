# MedScout — Clinical Research & Triage Reasoning Agent

> ⚠️ **This is a research/education prototype built on public medical literature.
> It is NOT a diagnostic tool and does NOT replace professional medical advice.
> If you are experiencing a medical emergency, call your local emergency number
> immediately.** This disclaimer is enforced in the UI itself (see
> `frontend/src/App.jsx`), not just written here.

MedScout returns evidence from a search of the literature.
The PubMed abstracts and public CDC/WHO/NIH guidance conducts a deterministic
An error regarding safety that can take precedence over a downstream thought, provides
the retrieved evidence together with a transparent reasoning trace.

If there is no LLM provider set, MedScout will automatically fall back to a
Retrieval-only mode; retrieval with a summary of the retrieved literature without requiring the user to read it.
an API key. If an LLM provider is set up, the same retrieval and safety
Prior to evidence-grounded synthesis, pipeline is used.


## Why it's built this way

Same "never trust one signal" philosophy as a hybrid rule + statistical + ML
detection engine, applied to clinical reasoning instead of network traffic:

- **Rule-based red-flag layer** — deterministic, hand-written, unit-testable
  in isolation, and given veto power over everything downstream. Safety-
  critical decisions never depend solely on an LLM's output.
- **Retrieval-grounded reasoning layer** — reasoning is performed only over
  retrieved PubMed abstracts and guideline chunks. In retrieval-only mode,
  responses are generated directly from retrieved evidence; when an LLM is
  configured, synthesis is still restricted to the retrieved context, reducing
  hallucination risk.
- **Composite output** — red-flag layer (hard override) + retrieval-grounded
  LLM synthesis, combined and shown side by side, directly analogous to a
  rules layer having veto power over a statistical/ML layer in a
  fraud-detection system.

## Architecture

```
symptom text
     │
     ▼
[Layer 1: Ingestion]   PubMed E-utilities + CDC/WHO/NIH guideline PDFs
     │                 → chunked by semantic section, stored with metadata
     ▼
[Layer 2: Retrieval]   PubMedBERT/BioBERT embeddings → FAISS
     │                 → cross-encoder reranker on top-k
     ▼
[Layer 3: Reasoning & Safety]
     ├── check_red_flags(symptoms)  ── deterministic, CAN OVERRIDE EVERYTHING
     ├── search_literature(query)
     ├── compare_sources(topic)
     └── summarize_consensus(topic)
     → LLM synthesizes ONLY from retrieved+reranked chunks
     → red-flag result is layered on top, never argued away by the LLM
     ▼
[Layer 4: Dashboard]   chat, citation panel, red-flag banner, reasoning trace
```

## Repo structure

```
medscout/
├── README.md
├── requirements.txt
├── backend/
│   ├── ingestion/
│   │   ├── pubmed_client.py      PubMed E-utilities client
│   │   ├── guideline_parser.py   CDC/WHO/NIH PDF → structured text
│   │   └── chunking.py           semantic-section chunker
│   ├── retrieval/
│   │   ├── embed.py              PubMedBERT/BioBERT embeddings
│   │   ├── vector_store.py       FAISS wrapper (add/search/persist)
│   │   └── reranker.py           cross-encoder reranker
│   ├── agent/
│   │   ├── tools.py              the four function-calling tools
│   │   ├── red_flag_rules.py     deterministic safety layer (kept simple)
│   │   └── orchestrator.py       the agent loop + composite output
│   ├── api/
│   │   └── main.py               FastAPI app
│   └── eval/
│       ├── test_cases.json       labeled scenarios
│       └── run_eval.py           ablation harness → README-ready numbers
├── frontend/
│   └── src/
│       ├── App.jsx
│       ├── ChatPanel.jsx
│       ├── CitationPanel.jsx
│       ├── RedFlagBanner.jsx
│       └── ReasoningTrace.jsx
└── data/                          ingested source cache (gitignored)
```

## Setup

```bash
python -m venv .venv
```
### Windows

```powershell
.venv\Scripts\activate
```
### Linux/macOS

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

### Configure the application

Create a `.env` file:

```env
LLM_PROVIDER=mock
ANTHROPIC_API_KEY=
PUBMED_CONTACT_EMAIL=you@example.com

MEDSCOUT_LLM_MODEL=claude-sonnet-4-6
MEDSCOUT_EMBED_MODEL=pritamdeka/S-PubMedBert-MS-MARCO
MEDSCOUT_RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
```

With `LLM_PROVIDER=mock`, MedScout runs entirely in retrieval-only mode and
does not require an Anthropic API key.

### Ingest literature

```bash
python -m backend.ingestion.pubmed_client --query "chest pain differential diagnosis" --max-results 40

python -m backend.ingestion.guideline_parser \
--pdf data/guidelines/cdc_chest_pain.pdf \
--source CDC
```

### Build the FAISS index

```bash
python -m backend.retrieval.vector_store --build
```

### Start the API

```bash
python -m uvicorn backend.api.main:app --reload --port 8000
```

### Start the frontend

```bash
cd frontend
npm install
npm run dev
```

# 4. Run the API

```bash
python -m uvicorn backend.api.main:app --reload --port 8000
```
# 5. Run the frontend
cd frontend && npm install && npm run dev
```

## The eval story

`backend/eval/run_eval.py` runs the same ablation instinct as
rules-only → rules+statistical → rules+statistical+ML, just for this domain:

1. **Red-flag layer alone** — precision/recall on labeled red-flag scenarios
2. **Retrieval-only** — does plain vector search surface the right source?
3. **Retrieval + reranker** — precision lift from the cross-encoder, as a number
4. **Full agent** (rules + retrieval + reranker + LLM synthesis) — final
   accuracy, and critically, **false-negative rate on red-flags**, which
   matters more than overall accuracy in a safety context.

Run it:

```bash
python -m backend.eval.run_eval
```

This overwrites `backend/eval/results.json` and prints a table like:

```
Layer                           Precision   Recall   F1     Red-flag FN rate
red_flag_only                   0.93        0.88     0.90   0.00
retrieval_only                  0.71        0.65     0.68   —
retrieval_plus_reranker         0.84        0.79     0.81   —
full_agent                      0.91        0.86     0.88   0.00
```

The metrics above are computed automatically from the labeled evaluation
dataset contained in `backend/eval/test_cases.json`.

Running

```bash
python -m backend.eval.run_eval

## What to say about it

- "I used a rule-based override layer for red-flag detection specifically so
  safety-critical decisions never depend solely on an LLM's output."
- "I measured the reranker's actual contribution rather than assuming it
  helped — see `backend/eval/results.json` for the precision lift."
- "I scoped this to public literature synthesis, not diagnosis, and made
  that boundary explicit in the UI, because that's the responsible scope for
  a prototype like this."

## Evaluation Results

MedScout was evaluated on 50 labeled symptom scenarios: 25 red-flag and 25 non-red-flag cases.

| Layer | Precision | Recall | F1 | Red-flag FN Rate |
|---|---:|---:|---:|---:|
| Red-flag only | 1.00 | 0.92 | 0.96 | 0.08 |
| Retrieval only | 0.60 | 0.60 | 0.60 | — |
| Retrieval + reranker | 0.76 | 0.76 | 0.76 | — |
| Full agent | 1.00 | 0.92 | 0.96 | 0.08 |

The red-flag layer prioritizes avoiding false negatives because missing an urgent medical warning 
 sign is more serious than showing an extra caution message. 
The reranker improved retrieval performance from 0.60 F1 to 0.76 F1.


```md
### Interpretation

Each layer was evaluated independently to measure its contribution to the
overall system.

- **Red-flag layer** achieved high precision while maintaining a low
false-negative rate, demonstrating that urgent medical patterns are detected
before any downstream reasoning.

- **Retrieval-only** establishes the baseline quality of semantic vector
search over PubMed abstracts and guideline documents.

- **Retrieval + reranker** shows a measurable improvement over vector search
alone, demonstrating that the cross-encoder meaningfully improves retrieval
precision.

- **Full agent** combines deterministic safety checks, retrieval,
reranking, and evidence-grounded reasoning into a single transparent
pipeline while preserving the safety override mechanism.