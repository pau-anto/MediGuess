"""Fixtures communes : une petite banque de cas générée à partir d'un modèle
entraîné à la volée (pas besoin du vrai dataset ni du vrai modèle)."""

import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import RandomForestClassifier

from ml.src.build_case_bank import build_bank, save_bank
from ml.src.explain import CaseExplainer

DISEASES = ["flu", "migraine", "asthma", "gastritis", "depression", "angina"]
N_CASES = 60


@pytest.fixture(name="bank_path", scope="session")
def fixture_bank_path(tmp_path_factory):
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
    cases = build_bank(explainer, features, target, n_cases=N_CASES)
    return save_bank(cases, tmp_path_factory.mktemp("bank") / "bank.json", {})
