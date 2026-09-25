"""Boucle de jeu MediGuess (tâche #12) : cas -> 4 choix -> réponse -> score.

Logique pure, sans dépendance web : l'API (api.py) et plus tard la Lambda
ne font qu'appeler GameEngine. Ça permet de la tester sans serveur.
"""

import random
import time
import uuid

from ml.src.explain import CaseExplainer
from ml.src.train import load_data

N_CHOICES = 4
MIN_SYMPTOMS = 2  # un cas avec un seul symptôme est injouable
CASE_TTL_SECONDS = 30 * 60  # un cas non répondu expire après 30 min
POINTS_CORRECT = 10  # scoring provisoire, à remplacer par la tâche #13


class GameEngine:
    def __init__(self, explainer=None, features=None, target=None, seed=None):
        self.explainer = explainer if explainer is not None else CaseExplainer()
        if features is None or target is None:
            features, target = load_data()
        self.features = features
        self.target = target.reset_index(drop=True)
        self.features = self.features.reset_index(drop=True)
        self.symptom_columns = list(self.features.columns)
        self.rng = random.Random(seed)
        # case_id -> {answer, symptoms, created}. En mémoire pour le local ;
        # sur Lambda (sans état) il faudra DynamoDB, cf. docs/api-contract.md
        self._cases = {}

    # ------------------------------------------------------------------
    # Tirage d'un cas
    # ------------------------------------------------------------------
    def _draw_symptoms(self):
        """Tire une ligne du dataset jusqu'à obtenir un cas jouable."""
        for _ in range(50):
            idx = self.rng.randrange(len(self.target))
            disease = self.target.iat[idx]
            row = self.features.iloc[idx].to_numpy()
            # On masque les symptômes qui portent le nom de la maladie
            # (ex. symptôme "depression" pour la maladie "depression"),
            # sinon la réponse est donnée au joueur.
            symptoms = [
                name
                for name, present in zip(self.symptom_columns, row)
                if present and name.lower() != disease.lower()
            ]
            if len(symptoms) >= MIN_SYMPTOMS:
                return disease, symptoms
        raise RuntimeError("Aucun cas jouable trouvé après 50 tirages.")

    def _build_choices(self, disease, symptoms):
        """Les 4 maladies les plus probables selon le modèle = distracteurs
        crédibles. Si la bonne réponse n'y est pas, elle remplace la 4e."""
        top = [c["disease"] for c in self.explainer.predict_top_k(symptoms)]
        choices = top[:N_CHOICES]
        if disease not in choices:
            choices[-1] = disease
        self.rng.shuffle(choices)
        return choices

    def new_case(self):
        self._purge_expired()
        disease, symptoms = self._draw_symptoms()
        choices = self._build_choices(disease, symptoms)
        self.rng.shuffle(symptoms)  # l'ordre du dataset donnerait des indices
        case_id = uuid.uuid4().hex
        self._cases[case_id] = {
            "answer": disease,
            "symptoms": symptoms,
            "created": time.time(),
        }
        # La bonne réponse ne quitte JAMAIS le serveur à cette étape.
        return {"case_id": case_id, "symptoms": symptoms, "choices": choices}

    # ------------------------------------------------------------------
    # Réponse du joueur
    # ------------------------------------------------------------------
    def answer(self, case_id, answer):
        case = self._cases.pop(case_id, None)  # un cas ne se joue qu'une fois
        if case is None:
            raise KeyError("Cas inconnu, déjà joué ou expiré.")

        correct = answer == case["answer"]
        explanation = self.explainer.explain(case["symptoms"], case["answer"])
        return {
            "correct": correct,
            "correct_answer": case["answer"],
            "points": POINTS_CORRECT if correct else 0,
            "feedback": build_feedback(correct, explanation),
            "explanation": explanation,
        }

    def _purge_expired(self):
        limit = time.time() - CASE_TTL_SECONDS
        for case_id in [k for k, v in self._cases.items() if v["created"] < limit]:
            del self._cases[case_id]


def build_feedback(correct, explanation):
    """Feedback provisoire à partir du top facteur (template complet : #14)."""
    supporting = [
        f["symptom"]
        for f in explanation["factors"]
        if f["present"] and f["direction"] == "pour"
    ]
    if not supporting:
        return "Aucun symptôme ne se détachait nettement sur ce cas."
    clue = supporting[0]
    if correct:
        return f"Bien vu : {clue} était l'indice le plus parlant."
    return f"L'indice le plus parlant était : {clue}."
