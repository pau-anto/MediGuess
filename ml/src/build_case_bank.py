"""Génère la banque de cas cliniques du jeu (tâche « Générer / structurer
les cas cliniques »).

Pourquoi pré-calculer ?
Le Random Forest complet prend ~5 Go de RAM une fois chargé (721 classes
stockées dans chaque noeud de chaque arbre) et le dataset fait 167 Mo.
Aucun service serverless (Azure Container Apps, Azure Functions, Lambda)
ne peut charger ça à chaque démarrage à froid. On fait donc tout le travail
ML ici, une fois, sur une machine qui a la RAM :
    cas tiré du dataset -> 4 choix (predict_top_k) -> top 3 SHAP (explain)
et le backend n'a plus qu'à servir un fichier JSON de quelques Mo.

Usage (depuis la racine du repo) :
    python -m ml.src.build_case_bank                  # 2000 cas, modèle par défaut
    python -m ml.src.build_case_bank --n-cases 500 --model models/autre.joblib
"""

import argparse
import json
import random
from datetime import datetime, timezone
from pathlib import Path

from ml.src.explain import CaseExplainer
from ml.src.train import MODEL_DIR, ARTIFACT_NAME, REPO_ROOT, load_artifact, load_data

N_CHOICES = 4
MIN_SYMPTOMS = 2  # un cas avec un seul symptôme est injouable
DEFAULT_OUTPUT = REPO_ROOT / "backend" / "data" / "case_bank.json"


def visible_symptoms(row, symptom_columns, disease):
    """Symptômes présents, sauf ceux qui portent le nom de la maladie
    (ex. symptôme "depression" pour la maladie "depression") : sinon la
    réponse serait donnée au joueur."""
    return [
        name
        for name, present in zip(symptom_columns, row)
        if present and name.lower() != disease.lower()
    ]


def build_choices(explainer, disease, symptoms):
    """Les 4 maladies les plus probables = distracteurs crédibles.
    Si la bonne réponse n'y est pas, elle remplace la 4e."""
    choices = [c["disease"] for c in explainer.predict_top_k(symptoms, k=N_CHOICES)]
    if disease not in choices:
        choices[-1] = disease
    return choices


def draw_cases(features, target, n_cases, rng):
    """Tire n cas jouables et distincts (même maladie + mêmes symptômes =
    doublon). Renvoie une liste de (maladie, symptômes)."""
    columns = list(features.columns)
    order = list(range(len(target)))
    rng.shuffle(order)
    seen, drawn = set(), []
    for idx in order:
        disease = target.iat[idx]
        symptoms = visible_symptoms(features.iloc[idx].to_numpy(), columns, disease)
        key = (disease, frozenset(symptoms))
        if len(symptoms) < MIN_SYMPTOMS or key in seen:
            continue
        seen.add(key)
        drawn.append((disease, symptoms))
        if len(drawn) == n_cases:
            break
    return drawn


def build_bank(explainer, features, target, n_cases, seed=42):
    rng = random.Random(seed)
    drawn = draw_cases(
        features.reset_index(drop=True), target.reset_index(drop=True), n_cases, rng
    )
    # Tri par maladie : l'explainer SHAP mono-classe est construit une fois
    # par maladie et mis en cache -> beaucoup plus rapide.
    drawn.sort(key=lambda case: case[0])
    cases = []
    for i, (disease, symptoms) in enumerate(drawn, start=1):
        explanation = explainer.explain(symptoms, disease)
        cases.append(
            {
                "answer": disease,
                "symptoms": symptoms,
                "choices": build_choices(explainer, disease, symptoms),
                "explanation": explanation,
            }
        )
        if i % 200 == 0:
            print(f"  {i}/{len(drawn)} cas")
    rng.shuffle(cases)
    return cases


def save_bank(cases, output, model_metadata):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    bank = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": model_metadata,
        "n_cases": len(cases),
        "cases": cases,
    }
    with open(output, "w", encoding="utf-8") as f:
        json.dump(bank, f, ensure_ascii=False, separators=(",", ":"))
    return output


def parse_args():
    parser = argparse.ArgumentParser(description="Génère la banque de cas.")
    parser.add_argument("--n-cases", type=int, default=2000)
    parser.add_argument("--model", default=str(MODEL_DIR / ARTIFACT_NAME))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main():
    args = parse_args()
    print(f"Chargement du modèle : {args.model}")
    artifact = load_artifact(args.model)
    explainer = CaseExplainer(artifact)
    print("Chargement du dataset...")
    features, target = load_data()
    print(f"Génération de {args.n_cases} cas...")
    cases = build_bank(explainer, features, target, args.n_cases, args.seed)
    metadata = artifact.get("metadata", {})
    path = save_bank(
        cases,
        args.output,
        {k: metadata.get(k) for k in ("model_type", "params", "metrics", "created_at")},
    )
    size_mb = path.stat().st_size / 1024**2
    print(f"{len(cases)} cas écrits dans {path} ({size_mb:.1f} Mo)")


if __name__ == "__main__":
    main()
