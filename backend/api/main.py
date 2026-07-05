"""
Layer 4 — Dashboard backend: FastAPI app.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.agent.orchestrator import run_query
from dotenv import load_dotenv
load_dotenv()
app = FastAPI(
    title="MedScout API",
    description=(
        "Research/education prototype. NOT a diagnostic tool. "
        "Does not replace professional medical advice."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    red_flag: dict
    answer_text: str
    citations: list[dict]
    confidence: str | None
    reasoning_trace: list[dict]
    disclaimer: str = (
        "MedScout is a research/education prototype using public literature. "
        "It is not a diagnostic tool and does not replace professional medical advice."
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest) -> QueryResponse:
    if not req.question or not req.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")

    result = run_query(req.question)
    return QueryResponse(**result.to_dict())
