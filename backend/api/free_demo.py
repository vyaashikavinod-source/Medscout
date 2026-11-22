"""Small free-host deployment: deterministic safety + live PubMed retrieval.
No LLM, embeddings, generated medical claims, or simulated citations.
"""
from pathlib import Path
import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from backend.agent.red_flag_rules import check_red_flags

app = FastAPI(title="MedScout — live retrieval demo")

class Query(BaseModel):
    question: str = Field(min_length=1, max_length=1000)

def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent":"MedScout-Education-Demo/1.0"}),timeout=12) as response:
        return response.read(2_000_000)

def search_pubmed(question):
    base="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    query=urllib.parse.urlencode({"db":"pubmed","term":question,"retmode":"json","retmax":3,"tool":"MedScout"})
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
def health():return {"status":"ok","mode":"live PubMed retrieval; no LLM"}

@app.post("/query")
def query(payload:Query):
    flags=check_red_flags(payload.question).to_dict()
    trace=[{"step_type":"rule_check","detail":flags}]
    if flags["triggered"]:
        citations=[]
        answer="A deterministic red-flag rule matched. Review the safety notice above. Literature retrieval is skipped; this prototype cannot assess or diagnose symptoms."
        trace.append({"step_type":"safety_gate","detail":{"retrieval_skipped":True}})
    else:
        try:
            citations=search_pubmed(payload.question)
            answer=f"Retrieved {len(citations)} PubMed records. Read the source abstracts and their limitations in the citation panel. These search results are not a diagnosis, consensus assessment, or personalized recommendation. No language model synthesized this response."
            trace.append({"step_type":"tool_result","detail":{"tool":"PubMed E-utilities","records":len(citations)}})
        except (OSError,ValueError,KeyError,ET.ParseError):
            citations=[]
            answer="PubMed retrieval is currently unavailable. No evidence or medical answer has been generated. Please try again later."
            trace.append({"step_type":"tool_error","detail":{"tool":"PubMed E-utilities","status":"unavailable"}})
    return {"red_flag":flags,"answer_text":answer,"citations":citations,"confidence":None,"reasoning_trace":trace,"disclaimer":"Research/education prototype. Not a diagnostic tool or medical advice. Keyword safety rules can miss emergencies; absence of a flag does not establish safety."}

static=Path(__file__).resolve().parents[2]/"frontend/dist"
if static.exists():app.mount("/",StaticFiles(directory=static,html=True),name="frontend")
