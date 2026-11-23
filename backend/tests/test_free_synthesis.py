import pytest
from backend.agent import free_synthesis as model


def test_unseen_sources_and_fabricated_quotes_are_rejected():
    sources=[{'metadata':{'pmid':'123'},'text':'An exact study excerpt with a stated limitation.'}]
    valid={'findings':[{'pmid':'123','quote':'An exact study excerpt','summary':'The study reports an association; causal inference is limited.'}]}
    assert model.validate(valid,sources)[0]['pmid']=='123'
    for field,value in [('pmid','999'),('quote','A fabricated source quotation'),('summary','You should take this treatment.')]:
        item={**valid['findings'][0],field:value}
        with pytest.raises(ValueError):model.validate({'findings':[item]},sources)


def test_app_limit_and_cooldown_prevent_extra_calls(monkeypatch):
    monkeypatch.setenv('MEDSCOUT_LLM_DAILY_LIMIT','2')
    monkeypatch.setattr(model,'_day','')
    monkeypatch.setattr(model,'_last',0)
    tick=[100.]
    monkeypatch.setattr(model.time,'monotonic',lambda:tick[0])
    assert model.reserve()
    assert not model.reserve()
    tick[0]+=16
    assert model.reserve()
    tick[0]+=16
    assert not model.reserve()


def test_safety_and_no_opt_in_never_call_model(monkeypatch):
    from backend.api import free_demo
    monkeypatch.setattr(free_demo,'synthesize',lambda *_:(_ for _ in ()).throw(AssertionError('Unexpected model call')))
    monkeypatch.setattr(free_demo,'search_pubmed',lambda _:[{'text':'A public abstract excerpt','metadata':{'pmid':'123','title':'Study'}}])
    result=free_demo.query(free_demo.Query(question='exercise and sleep review'))
    assert result['synthesis']['status']=='not_requested'
    safety=free_demo.query(free_demo.Query(question='crushing chest pain radiating down my left arm, short of breath',include_ai=True))
    assert safety['synthesis']['status']=='skipped_for_safety'
