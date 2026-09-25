"""Tests de la boucle de jeu sur un petit modèle entraîné à la volée
(pas besoin du vrai dataset ni du vrai modèle). Lancer : pytest backend"""

# Les tests lisent la bonne réponse stockée par le moteur.
# pylint: disable=protected-access

import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import RandomForestClassifier

from backend.src.game import GameEngine
from ml.src.explain import CaseExplainer

DISEASES = ["flu", "migraine", "asthma", "gastritis", "depression", "angina"]


@pytest.fixture(name="engine")
def fixture_engine():
    rng = np.random.default_rng(0)
    columns = [f"s{i}" for i in range(20)] + ["depression"]
    target = pd.Series(rng.choice(DISEASES, 600))
    features = pd.DataFrame(
        (rng.random((600, len(columns))) < 0.3).astype(np.uint8), columns=columns
    )
    # "depression" est à la fois symptôme et maladie : doit être masqué
    features.loc[target == "depression", "depression"] = 1
    model = RandomForestClassifier(20, random_state=0).fit(features, target)
    explainer = CaseExplainer({"model": model, "symptom_columns": columns})
    return GameEngine(explainer, features, target, seed=1)


def test_case_format_and_no_answer_leak(engine):
    case = engine.new_case()
    assert set(case) == {"case_id", "symptoms", "choices"}
    assert len(case["choices"]) == 4
    assert len(case["symptoms"]) >= 2
    assert engine._cases[case["case_id"]]["answer"] in case["choices"]


def test_disease_name_is_never_a_visible_symptom(engine):
    for _ in range(100):
        case = engine.new_case()
        answer = engine._cases[case["case_id"]]["answer"]
        assert answer not in case["symptoms"]


def test_correct_and_wrong_answers(engine):
    case = engine.new_case()
    good = engine._cases[case["case_id"]]["answer"]
    result = engine.answer(case["case_id"], good)
    assert result["correct"] and result["points"] > 0
    assert len(result["explanation"]["factors"]) <= 3

    case = engine.new_case()
    good = engine._cases[case["case_id"]]["answer"]
    wrong = next(c for c in case["choices"] if c != good)
    result = engine.answer(case["case_id"], wrong)
    assert not result["correct"] and result["points"] == 0
    assert result["correct_answer"] == good


def test_case_cannot_be_played_twice(engine):
    case = engine.new_case()
    engine.answer(case["case_id"], case["choices"][0])
    with pytest.raises(KeyError):
        engine.answer(case["case_id"], case["choices"][0])
