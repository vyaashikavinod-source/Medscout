"""Free-host literature retrieval, compact vector ranking and opt-in cited synthesis."""
from pathlib import Path
import json
import os
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from backend.agent.red_flag_rules import check_red_flags
from backend.agent.free_synthesis import synthesize

app = FastAPI(title="MedScout — live retrieval demo")

class Query(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    include_ai: bool = False

def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent":"MedScout-Education-Demo/1.0"}),timeout=12) as response:
        return response.read(2_000_000)

def search_pubmed(question):
    base="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    query=urllib.parse.urlencode({"db":"pubmed","term":question,"retmode":"json","retmax":12,"tool":"MedScout"})
    ids=json.loads(fetch(base+"esearch.fcgi?"+query))["esearchresult"]["idlist"]
    if not ids:return []
    root=ET.fromstring(fetch(base+"efetch.fcgi?"+urllib.parse.urlencode({"db":"pubmed","id":",".join(ids),"retmode":"xml"})))
    citations=[]
    for article in root.findall(".//PubmedArticle"):
        pmid=article.findtext(".//PMID")
        title="".join(article.find(".//ArticleTitle").itertext())
        abstract=" ".join("".join(node.itertext()) for node in article.findall(".//AbstractText"))
        citations.append({"text":abstract or "No abstract supplied by PubMed.","metadata":{"source":"PubMed","title":title,"url":f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/","pmid":pmid},"section":"Abstract"})
    return citations

@app.get("/health")
def health():return {"status":"ok","mode":"live PubMed retrieval + optional ONNX ranking + bounded Gemini synthesis",
                     "embedding_enabled":os.getenv('MEDSCOUT_EMBED_ENABLED') == 'true',
                     "llm_enabled":bool(os.getenv('GEMINI_API_KEY'))}

@app.post("/query")
def query(payload:Query):
    flags=check_red_flags(payload.question).to_dict()
    trace=[{"step_type":"rule_check","detail":flags}]
    findings = None
    synthesis = {'status':'skipped_for_safety'}
    if flags["triggered"]:
        citations=[]
        answer="A deterministic red-flag rule matched. Review the safety notice above. Literature retrieval is skipped; this prototype cannot assess or diagnose symptoms."
        trace.append({"step_type":"safety_gate","detail":{"retrieval_skipped":True}})
    else:
        try:
            citations=search_pubmed(payload.question)
            if os.getenv('MEDSCOUT_EMBED_ENABLED') == 'true':
                try:
                    from backend.retrieval.compact import rerank
                    citations=rerank(payload.question,citations)
                    trace.append({'step_type':'tool_result','detail':{'tool':'ONNX vector ranking','model':'MiniLM-L6-v2 general-purpose int8','excerpts':len(citations)}})
                except (OSError,ValueError,RuntimeError,ImportError):
                    trace.append({'step_type':'tool_error','detail':{'tool':'ONNX vector ranking','status':'unavailable; original PubMed order retained'}})
            answer=f"Retrieved {len(citations)} PubMed excerpts. Read the source abstracts and their limitations in the citation panel. These search results are not a diagnosis, consensus assessment, or personalized recommendation. No language model synthesized this response."
            trace.append({"step_type":"tool_result","detail":{"tool":"PubMed E-utilities","records":len(citations)}})
            if payload.include_ai:
                findings,synthesis=synthesize(payload.question,citations)
            else:
                synthesis={'status':'not_requested'}
            trace.append({'step_type':'model_summary','detail':synthesis})
            if findings:
                answer='Research findings from the retrieved excerpts (AI-generated; verify against the quoted sources):\n\n' + '\n\n'.join(
                    f"[{item['pmid']}] {item['summary']}\nSource quote: {item['quote']}" for item in findings)
            elif payload.include_ai:
                answer += '\n\nAI summary unavailable, limited, or rejected by evidence validation; retrieval remains available.'
        except (OSError,ValueError,KeyError,ET.ParseError):
            citations=[]
            synthesis={'status':'retrieval_unavailable'}
            answer="PubMed retrieval is currently unavailable. No evidence or medical answer has been generated. Please try again later."
            trace.append({"step_type":"tool_error","detail":{"tool":"PubMed E-utilities","status":"unavailable"}})
    return {"red_flag":flags,"answer_text":answer,"citations":citations,"confidence":None,"reasoning_trace":trace,
            "findings":findings,"synthesis":synthesis,
            "disclaimer":"Research/education prototype. Not a diagnostic tool or medical advice. Keyword safety rules can miss emergencies; absence of a flag does not establish safety. AI source references and quotes are checked, but this does not certify the interpretation."}

static=Path(__file__).resolve().parents[2]/"frontend/dist"
if static.exists():app.mount("/",StaticFiles(directory=static,html=True),name="frontend")
