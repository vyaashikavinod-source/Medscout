"""
Unit tests for the deterministic safety layer, run in complete isolation
from the LLM/retrieval stack — exactly the point of keeping this layer
dependency-free. Run with: pytest backend/tests/test_red_flag_rules.py
"""
from backend.agent.red_flag_rules import check_red_flags


def test_acs_pattern_triggers():
    result = check_red_flags("crushing chest pain radiating down my left arm, short of breath")
    assert result.triggered
    assert any(r["id"] == "acs_pattern" for r in result.matched_rules)


def test_stroke_pattern_triggers():
    result = check_red_flags("my face is drooping and speech is slurred")
    assert result.triggered
    assert any(r["id"] == "stroke_pattern" for r in result.matched_rules)


def test_thunderclap_headache_triggers():
    result = check_red_flags("worst headache of my life, came on suddenly")
    assert result.triggered
    assert any(r["id"] == "thunderclap_headache" for r in result.matched_rules)


def test_suicidal_ideation_triggers():
    result = check_red_flags("I've been having thoughts that I want to die")
    assert result.triggered
    assert any(r["id"] == "suicidal_ideation" for r in result.matched_rules)


def test_mild_symptoms_do_not_trigger():
    result = check_red_flags("mild stuffy nose and slight headache since this morning")
    assert not result.triggered


def test_chest_pain_alone_does_not_trigger_acs_pattern():
    """Chest pain alone, with no accompanying symptom, should NOT fire the
    ACS pattern rule — the rule requires the combination, not a single
    symptom, matching how the spec's example is phrased."""
    result = check_red_flags("I have some chest pain")
    assert not any(r["id"] == "acs_pattern" for r in result.matched_rules)


def test_partial_gi_bleed_symptom_triggers():
    result = check_red_flags("I noticed black tarry stool this morning")
    assert result.triggered
    assert any(r["id"] == "gi_bleed_pattern" for r in result.matched_rules)


def test_normalize_symptoms_handles_synonyms():
    result = check_red_flags("having trouble breathing and chest tightness")
    assert "shortness of breath" in result.normalized_symptoms
    assert "chest pain" in result.normalized_symptoms
