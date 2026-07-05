"""
Layer 3 — Reasoning & Safety: the deterministic red-flag layer.

DESIGN RULE: this file has zero dependency on the LLM, the retriever, or the
vector store. It is pure Python, pure logic, unit-testable in complete
isolation, and its output is allowed to override every other layer in the
system. If you find yourself wanting to make a rule "smarter" by piping it
through the LLM, that's a sign it belongs in the LLM layer instead — keep
this file boring and legible.

Each rule is a plain function of a normalized symptom set -> RedFlagResult.
Symptom matching is deliberately conservative (substring/keyword match on a
normalized synonym-expanded set) rather than fuzzy/embedding-based, because
false negatives here are the single worst failure mode in the whole system.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# --- symptom normalization -------------------------------------------------

# Each canonical symptom maps to one or more regex patterns. Patterns use
# `.*?` / optional linking-verb groups rather than exact phrases, because
# real symptom descriptions vary in word order ("face is drooping" vs
# "drooping face") far more than a plain substring list can capture. This
# is still deliberately conservative — it does NOT try to handle arbitrary
# paraphrase, only the word-order and linking-verb variation that real
# free-text symptom descriptions actually exhibit.
SYMPTOM_PATTERNS: dict[str, list[str]] = {
    # ---------------- Cardiac ----------------
    "chest pain": [
        r"chest (?:is |feels? )?(?:pain|tight\w*|pressure|discomfort)",
        r"crushing chest pain",
        r"chest pressure",
    ],

    "shortness of breath": [
        r"(?:short(?:ness)? of breath|trouble breathing|difficulty breathing|breathless|can't breathe|cant breathe)"
    ],

    "left arm pain": [
        r"(?:left arm|arm).*?(?:pain|ache|radiat\w*)",
        r"(?:pain|ache|radiat\w*).*?left arm",
    ],

    "jaw pain": [
        r"jaw.*?(?:pain|ache)"
    ],

    "tearing back pain": [
        r"tearing.*back",
        r"ripping.*back",
        r"tearing chest pain",
        r"pain.*through.*back",
    ],

    "sweating": [
        r"sweating",
        r"cold sweat",
        r"diaphoresis",
    ],

    "dizziness": [
        r"dizz\w*",
        r"lightheaded",
    ],

    # ---------------- Stroke ----------------

    "facial droop": [
        r"face.*droop",
        r"drooping face",
    ],

    "slurred speech": [
        r"slurr\w* speech",
        r"speech.*slurr",
    ],

    "unilateral weakness": [
        r"one side.*weak",
        r"one-sided weakness",
        r"left side weak",
        r"right side weak",
        r"arm.*weak",
        r"leg.*weak",
    ],

    "vision loss": [
        r"vision loss",
        r"lost vision",
        r"can't see",
        r"blind in one eye",
    ],

    "confusion": [
        r"confus\w*",
        r"disorient\w*",
        r"not making sense",
    ],

    # ---------------- Neuro ----------------

    "thunderclap headache": [
        r"worst headache.*life",
        r"sudden.*headache",
        r"headache.*out of nowhere",
        r"thunderclap",
    ],

    "seizure": [
        r"seizure",
        r"convulsion",
        r"fit",
    ],

    "syncope": [
        r"fainted",
        r"passed out",
        r"lost consciousness",
        r"syncope",
    ],

    # ---------------- Infection ----------------

    "high fever": [
        r"high fever",
        r"fever.*103",
        r"fever.*104",
        r"fever.*105",
    ],

    "neck stiffness": [
        r"stiff neck",
        r"rigid neck",
    ],

    "photophobia": [
        r"sensitive to light",
        r"light hurts",
        r"photophobia",
    ],

    "lethargy": [
        r"very sleepy",
        r"hard to wake",
        r"letharg",
    ],

    # ---------------- Bleeding ----------------

    "hemoptysis": [
        r"cough.*blood",
    ],

    "hematemesis": [
        r"vomit.*blood",
        r"throw.*blood",
    ],

    "melena": [
        r"black.*stool",
        r"tarry stool",
    ],

    # ---------------- GI ----------------

    "severe abdominal pain": [
        r"severe abdominal pain",
        r"worst abdominal pain",
    ],

    "rigid abdomen": [
        r"rigid abdomen",
        r"hard belly",
        r"board.?like abdomen",
    ],

    "vomiting": [
        r"vomiting",
        r"throwing up",
    ],

    # ---------------- Allergy ----------------

    "lip swelling": [
        r"swollen lips",
        r"lip swelling",
    ],

    "tongue swelling": [
        r"tongue swelling",
        r"swollen tongue",
    ],

    "wheezing": [
        r"wheezing",
    ],

    "cyanosis": [
        r"blue lips",
        r"bluish lips",
        r"cyanosis",
    ],

    # ---------------- Pregnancy ----------------

    "pregnancy": [
        r"pregnant",
        r"pregnancy",
    ],

    "vaginal bleeding": [
        r"heavy bleeding",
        r"vaginal bleeding",
    ],

    "swelling": [
        r"swelling",
        r"swollen",
    ],

    # ---------------- Mental Health ----------------

    "suicidal ideation": [
        r"suicid",
        r"want to die",
        r"kill myself",
        r"end my life",
        r"thoughts of dying",
    ],

    # ---------------- Metabolic ----------------

    "dehydration": [
        r"dehydration",
        r"very little urination",
        r"not urinating",
    ],

    "extreme thirst": [
        r"very thirsty",
        r"extreme thirst",
    ],

    "high blood sugar": [
        r"blood sugar.*high",
        r"extremely high blood sugar",
        r"hyperglycemia",
    ],
}

def normalize_symptoms(raw_text: str) -> set[str]:
    text = raw_text.lower()
    text = re.sub(r"[^a-z0-9' ]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    found: set[str] = set()
    for canonical, patterns in SYMPTOM_PATTERNS.items():
        if any(re.search(p, text) for p in patterns):
            found.add(canonical)

    return found


# --- rule definitions -------------------------------------------------------

@dataclass
class RedFlagRule:
    id: str
    description: str
    required_all_of: tuple[str, ...] = field(default_factory=tuple)   # AND
    required_any_of: tuple[str, ...] = field(default_factory=tuple)   # OR (at least one)
    guidance: str = "Seek immediate medical care."

    def matches(self, symptoms: set[str]) -> bool:
        if self.required_all_of and not set(self.required_all_of).issubset(symptoms):
            return False
        if self.required_any_of and not (set(self.required_any_of) & symptoms):
            return False
        return bool(self.required_all_of or self.required_any_of)


RED_FLAG_RULES: list[RedFlagRule] = [
    RedFlagRule(
        id="acs_pattern",
        description="Possible acute coronary syndrome pattern",
        required_all_of=("chest pain",),
        required_any_of=("shortness of breath", "left arm pain", "jaw pain", "sweating", "dizziness"),
        guidance="Chest pain with breathing difficulty, radiation, sweating, dizziness, or jaw/arm symptoms can be urgent. Seek immediate medical care.",
    ),
    RedFlagRule(
        id="aortic_dissection_pattern",
        description="Possible aortic dissection pattern",
        required_all_of=("chest pain", "tearing back pain"),
        guidance="Sudden tearing chest/back pain can be life-threatening. Seek emergency care immediately.",
    ),
    RedFlagRule(
        id="stroke_pattern",
        description="Possible stroke pattern",
        required_any_of=("facial droop", "unilateral weakness", "slurred speech", "vision loss", "confusion"),
        guidance="Stroke symptoms are time-critical. Call emergency services immediately.",
    ),
    RedFlagRule(
        id="thunderclap_headache",
        description="Sudden severe headache pattern",
        required_any_of=("thunderclap headache",),
        guidance="A sudden worst headache can signal a serious emergency. Seek immediate care.",
    ),
    RedFlagRule(
        id="meningitis_pattern",
        description="Possible meningitis pattern",
        required_all_of=("neck stiffness",),
        required_any_of=("high fever", "photophobia", "confusion", "lethargy"),
        guidance="Fever with stiff neck, light sensitivity, confusion, or lethargy can be urgent. Seek emergency care.",
    ),
    RedFlagRule(
        id="bleeding_pattern",
        description="Possible serious bleeding pattern",
        required_any_of=("hematemesis", "melena", "hemoptysis"),
        guidance="Vomiting blood, black/tarry stool, or coughing blood needs urgent medical evaluation.",
    ),
    RedFlagRule(
        id="acute_abdomen_pattern",
        description="Possible acute abdomen pattern",
        required_all_of=("severe abdominal pain",),
        required_any_of=("rigid abdomen", "high fever", "vomiting"),
        guidance="Severe abdominal pain with rigidity, fever, or vomiting may be urgent. Seek medical care immediately.",
    ),
    RedFlagRule(
        id="first_seizure_pattern",
        description="New seizure or seizure with confusion",
        required_any_of=("seizure",),
        guidance="A new seizure or seizure with ongoing confusion needs urgent medical evaluation.",
    ),
    RedFlagRule(
        id="syncope_exertional_pattern",
        description="Fainting with exertion or chest symptoms",
        required_all_of=("syncope",),
        required_any_of=("chest pain", "shortness of breath"),
        guidance="Fainting with chest symptoms or breathing trouble can be serious. Seek urgent care.",
    ),
    RedFlagRule(
        id="anaphylaxis_pattern",
        description="Possible severe allergic reaction",
        required_any_of=("lip swelling", "tongue swelling", "wheezing", "shortness of breath"),
        guidance="Swelling of lips/tongue or breathing trouble can indicate anaphylaxis. Seek emergency care.",
    ),
    RedFlagRule(
        id="respiratory_distress_pattern",
        description="Severe breathing difficulty or cyanosis",
        required_any_of=("cyanosis", "shortness of breath"),
        guidance="Severe breathing trouble or blue lips can be an emergency. Seek immediate care.",
    ),
    RedFlagRule(
        id="dehydration_confusion_pattern",
        description="Possible severe dehydration",
        required_all_of=("dehydration",),
        required_any_of=("confusion", "lethargy"),
        guidance="Dehydration with confusion, lethargy, or very little urination can be serious. Seek medical care.",
    ),
    RedFlagRule(
        id="hyperglycemic_crisis_pattern",
        description="Possible hyperglycemic crisis",
        required_all_of=("high blood sugar",),
        required_any_of=("confusion", "extreme thirst", "dehydration"),
        guidance="Very high blood sugar with confusion, thirst, or dehydration may be urgent. Seek medical care.",
    ),
    RedFlagRule(
        id="pregnancy_bleeding_pattern",
        description="Pregnancy with heavy bleeding or severe abdominal pain",
        required_all_of=("pregnancy",),
        required_any_of=("vaginal bleeding", "severe abdominal pain"),
        guidance="Bleeding or severe abdominal pain during pregnancy needs urgent medical evaluation.",
    ),
    RedFlagRule(
        id="preeclampsia_pattern",
        description="Possible preeclampsia warning symptoms",
        required_all_of=("pregnancy",),
        required_any_of=("thunderclap headache", "vision loss", "swelling"),
        guidance="Pregnancy with severe headache, vision changes, or swelling can be urgent. Seek medical care immediately.",
    ),
    RedFlagRule(
        id="child_lethargy_pattern",
        description="Child with fever/stiff neck/lethargy pattern",
        required_any_of=("lethargy",),
        guidance="Unusual sleepiness or difficulty waking, especially with fever or stiff neck, needs urgent care.",
    ),
    RedFlagRule(
        id="suicidal_ideation",
        description="Expressed suicidal ideation",
        required_any_of=("suicidal ideation",),
        guidance="Seek immediate crisis support or emergency help.",
    ),
]

@dataclass
class RedFlagResult:
    triggered: bool
    matched_rules: list[dict]
    normalized_symptoms: list[str]

    def to_dict(self) -> dict:
        return {
            "triggered": self.triggered,
            "matched_rules": self.matched_rules,
            "normalized_symptoms": self.normalized_symptoms,
        }


def check_red_flags(symptom_text: str) -> RedFlagResult:
    """The single entry point the rest of the system calls. Pure function:
    same input always produces the same output, no network calls, no LLM."""
    symptoms = normalize_symptoms(symptom_text)

    matched = [
        {"id": rule.id, "description": rule.description, "guidance": rule.guidance}
        for rule in RED_FLAG_RULES
        if rule.matches(symptoms)
    ]

    return RedFlagResult(
        triggered=bool(matched),
        matched_rules=matched,
        normalized_symptoms=sorted(symptoms),
    )
