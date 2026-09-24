"""Prédiction + explication SHAP d'un cas clinique MediGuess (tâche #10).

Pourquoi ne pas appeler directement shap.TreeExplainer(model) ?
Avec 721 maladies, SHAP recopie les probabilités des 721 classes pour chaque
noeud de chaque arbre : plusieurs Go de RAM -> crash sur un laptop et
impossible sur Lambda. Or le jeu n'a besoin d'expliquer qu'UNE maladie à la
fois (la bonne réponse, ou celle choisie par le joueur).

On construit donc, à la demande, un explainer "mono-classe" : on extrait des
arbres la seule probabilité de la maladie visée. Le résultat est
mathématiquement identique aux valeurs SHAP de cette classe, pour une
fraction de la mémoire. Les explainers déjà construits sont mis en cache.

Usage :
    from ml.src.explain import CaseExplainer
    explainer = CaseExplainer()                      # charge l'artefact
    explainer.predict_top_k(["fever", "cough"])     # 4 choix du jeu
    explainer.explain(["fever", "cough"], "flu")    # top 3 facteurs
"""

from collections import OrderedDict

import numpy as np
import pandas as pd
import shap

from ml.src.train import load_artifact

TOP_K = 4
TOP_FACTORS = 3
CACHE_SIZE = 32  # nombre d'explainers mono-classe gardés en mémoire


class CaseExplainer:
    def __init__(self, artifact=None):
        artifact = artifact if artifact is not None else load_artifact()
        self.model = artifact["model"]
        self.symptom_columns = artifact["symptom_columns"]
        self.classes = list(self.model.classes_)
        self._class_index = {c: i for i, c in enumerate(self.classes)}
        self._symptom_set = set(self.symptom_columns)
        self._cache = OrderedDict()

    # ------------------------------------------------------------------
    # Entrée
    # ------------------------------------------------------------------
    def to_vector(self, symptoms):
        """Liste de noms de symptômes présents -> DataFrame 1 ligne (0/1)."""
        unknown = [s for s in symptoms if s not in self._symptom_set]
        if unknown:
            raise ValueError(f"Symptômes inconnus du modèle : {unknown}")
        row = pd.DataFrame(
            np.zeros((1, len(self.symptom_columns)), dtype=np.uint8),
            columns=self.symptom_columns,
        )
        row.loc[0, list(symptoms)] = 1
        return row

    # ------------------------------------------------------------------
    # Prédiction
    # ------------------------------------------------------------------
    def predict_top_k(self, symptoms, k=TOP_K):
        """Les k maladies les plus probables, triées, avec leur proba."""
        proba = self.model.predict_proba(self.to_vector(symptoms))[0]
        best = np.argsort(proba)[::-1][:k]
        return [
            {"disease": self.classes[i], "probability": round(float(proba[i]), 4)}
            for i in best
        ]

    # ------------------------------------------------------------------
    # Explication
    # ------------------------------------------------------------------
    def _explainer_for(self, disease):
        """Explainer SHAP limité à une seule maladie (mis en cache)."""
        if disease in self._cache:
            self._cache.move_to_end(disease)
            return self._cache[disease]
        if disease not in self._class_index:
            raise ValueError(f"Maladie inconnue du modèle : {disease}")
        idx = self._class_index[disease]
        n_trees = len(self.model.estimators_)

        trees = []
        for estimator in self.model.estimators_:
            tree = estimator.tree_
            # value[:, 0, idx] = proba de la maladie dans chaque noeud.
            # predict_proba d'une forêt = moyenne des arbres -> on divise
            # par n_trees pour que la somme des arbres redonne la proba.
            values = tree.value[:, 0, idx].astype(np.float64) / n_trees
            trees.append(
                {
                    "children_left": tree.children_left.copy(),
                    "children_right": tree.children_right.copy(),
                    "children_default": tree.children_left.copy(),
                    "features": tree.feature.copy(),
                    "thresholds": tree.threshold.astype(np.float64),
                    "values": values.reshape(-1, 1),
                    "node_sample_weight": tree.weighted_n_node_samples.astype(
                        np.float64
                    ),
                }
            )
        explainer = shap.TreeExplainer({"trees": trees})

        self._cache[disease] = explainer
        if len(self._cache) > CACHE_SIZE:
            self._cache.popitem(last=False)
        return explainer

    def explain(self, symptoms, disease, n_factors=TOP_FACTORS):
        """Top n facteurs qui poussent le modèle vers (ou contre) `disease`.

        Chaque facteur indique si le symptôme est présent ou absent du cas :
        l'absence d'un symptôme attendu est aussi une information clinique.
        """
        vector = self.to_vector(symptoms)
        explainer = self._explainer_for(disease)
        contributions = np.asarray(explainer.shap_values(vector.values)).reshape(-1)

        order = np.argsort(np.abs(contributions))[::-1][:n_factors]
        factors = [
            {
                "symptom": self.symptom_columns[i],
                "present": bool(vector.iat[0, i]),
                "contribution": round(float(contributions[i]), 4),
                "direction": "pour" if contributions[i] > 0 else "contre",
            }
            for i in order
            if contributions[i] != 0
        ]
        base_value = float(np.ravel(explainer.expected_value)[0])
        return {
            "disease": disease,
            # base_value + somme des contributions = proba donnée par le modèle
            "probability": round(base_value + float(contributions.sum()), 4),
            "base_value": round(base_value, 4),
            "factors": factors,
        }


def demo():
    """Tire un cas au hasard dans le dataset et affiche ce que verrait le jeu."""
    # Import local : la démo seule a besoin du dataset, pas l'API.
    from ml.src.train import DATA_PATH, TARGET_COLUMN  # pylint: disable=C0415

    explainer = CaseExplainer()
    row = pd.read_csv(DATA_PATH).sample(1).iloc[0]
    symptoms = [s for s in explainer.symptom_columns if row[s] == 1]

    print(f"\nSymptômes du cas : {', '.join(symptoms)}")
    print(f"Bonne réponse     : {row[TARGET_COLUMN]}\n")
    print("4 choix proposés par le modèle :")
    for choice in explainer.predict_top_k(symptoms):
        print(f"  - {choice['disease']} ({choice['probability']:.1%})")

    result = explainer.explain(symptoms, row[TARGET_COLUMN])
    print(f"\nPourquoi '{result['disease']}' ? (proba {result['probability']:.1%})")
    for factor in result["factors"]:
        state = "présent" if factor["present"] else "absent"
        print(
            f"  - {factor['symptom']} ({state}) : "
            f"{factor['contribution']:+.3f} {factor['direction']}"
        )


if __name__ == "__main__":
    demo()
