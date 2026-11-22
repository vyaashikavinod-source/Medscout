from backend.api import free_demo

def test_safety_gate_skips_external_retrieval(monkeypatch):
    def forbidden(_): raise AssertionError("Safety gate must skip retrieval")
    monkeypatch.setattr(free_demo,"search_pubmed",forbidden)
    result=free_demo.query(free_demo.Query(question="crushing chest pain radiating down my left arm, short of breath"))
    assert result["red_flag"]["triggered"]
    assert result["citations"] == []
    assert result["confidence"] is None

def test_retrieval_failures_do_not_invent_sources(monkeypatch):
    def failed(_): raise OSError("unavailable")
    monkeypatch.setattr(free_demo,"search_pubmed",failed)
    result=free_demo.query(free_demo.Query(question="exercise and sleep systematic review"))
    assert result["citations"] == []
    assert "unavailable" in result["answer_text"]
    assert result["reasoning_trace"][-1]["step_type"] == "tool_error"

def test_pubmed_xml_is_preserved_with_source_links(monkeypatch):
    results=iter([b'{"esearchresult":{"idlist":["123"]}}',b'<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>123</PMID><Article><ArticleTitle>Public study title</ArticleTitle><Abstract><AbstractText>Original abstract.</AbstractText></Abstract></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>'])
    monkeypatch.setattr(free_demo,"fetch",lambda _:next(results))
    records=free_demo.search_pubmed("public research topic")
    assert records[0]["text"]=="Original abstract."
    assert records[0]["metadata"]["url"]=="https://pubmed.ncbi.nlm.nih.gov/123/"
