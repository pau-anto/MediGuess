"""Entraîne le Random Forest MediGuess et le sérialise en un artefact unique.

Reprend la logique de ml/notebooks/train_model.ipynb sous forme de module
réutilisable (lintable, importable par l'API), et ajoute :
- un artefact unique (modèle + colonnes + classes + métadonnées) compressé ;
- un fichier metadata.json lisible (métriques, paramètres, taille) ;
- la mesure de la taille de l'artefact, pour valider le déploiement Lambda.

Usage (depuis la racine du repo) :
    python -m ml.src.train
    python -m ml.src.train --n-estimators 100 --max-depth 25
    python -m ml.src.train --sample-frac 0.1   # test rapide
"""

import argparse
import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, top_k_accuracy_score
from sklearn.model_selection import train_test_split

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = REPO_ROOT / "data" / "cleaned_dataset.csv"
MODEL_DIR = REPO_ROOT / "models"
ARTIFACT_NAME = "mediguess_model.joblib"
METADATA_NAME = "metadata.json"

TARGET_COLUMN = "diseases"
TEST_SIZE = 0.2
RANDOM_STATE = 42
TOP_K = 4  # nombre de choix proposés au joueur


def load_data(path=DATA_PATH, sample_frac=None):
    """Charge le dataset nettoyé. Les symptômes sont en uint8 (0/1)
    pour diviser la RAM par 8 par rapport à l'int64 par défaut."""
    if not Path(path).is_file():
        raise FileNotFoundError(
            f"Fichier introuvable : {path}\n"
            "Lancez d'abord ml/notebooks/clean_data.ipynb."
        )
    header = pd.read_csv(path, nrows=0).columns
    dtypes = {col: np.uint8 for col in header if col != TARGET_COLUMN}
    df = pd.read_csv(path, dtype=dtypes)

    if sample_frac:
        # Échantillon stratifié : chaque maladie garde au moins 2 exemples
        kept = [
            group.sample(
                n=max(2, int(len(group) * sample_frac)), random_state=RANDOM_STATE
            ).index
            for _, group in df.groupby(TARGET_COLUMN)
        ]
        df = df.loc[np.concatenate(kept)]

    features = df.drop(columns=[TARGET_COLUMN])
    target = df[TARGET_COLUMN]
    return features, target


def train(features, target, params):
    """Split stratifié + entraînement. Renvoie le modèle et le jeu de test."""
    x_train, x_test, y_train, y_test = train_test_split(
        features,
        target,
        test_size=TEST_SIZE,
        random_state=RANDOM_STATE,
        stratify=target,
    )
    model = RandomForestClassifier(random_state=RANDOM_STATE, **params)
    start = time.time()
    model.fit(x_train, y_train)
    train_seconds = time.time() - start
    return model, x_test, y_test, train_seconds


def evaluate(model, x_test, y_test):
    """Top-1 et top-K accuracy (top-K = mécanique de jeu à K choix)."""
    proba = model.predict_proba(x_test)
    y_pred = model.classes_[proba.argmax(axis=1)]
    return {
        "top1_accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
        f"top{TOP_K}_accuracy": round(
            float(top_k_accuracy_score(y_test, proba, k=TOP_K, labels=model.classes_)),
            4,
        ),
        "n_test": int(len(y_test)),
    }


def save_artifact(model, symptom_columns, metrics, params, compress=3):
    """Sérialise tout ce dont l'API a besoin dans UN fichier + un JSON lisible.

    Le numéro de version de scikit-learn est enregistré : un modèle joblib
    ne se recharge de façon fiable qu'avec la même version (important pour
    l'image Lambda)."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    artifact_path = MODEL_DIR / ARTIFACT_NAME

    metadata = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model_type": type(model).__name__,
        "params": params,
        "metrics": metrics,
        "n_symptoms": len(symptom_columns),
        "n_classes": len(model.classes_),
        "sklearn_version": sklearn.__version__,
        "python_version": platform.python_version(),
    }
    artifact = {
        "model": model,
        "symptom_columns": list(symptom_columns),
        "classes": list(model.classes_),
        "metadata": metadata,
    }
    joblib.dump(artifact, artifact_path, compress=compress)

    size_mb = artifact_path.stat().st_size / 1024**2
    metadata["artifact_size_mb"] = round(size_mb, 1)
    with open(MODEL_DIR / METADATA_NAME, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    return artifact_path, size_mb


def load_artifact(path=MODEL_DIR / ARTIFACT_NAME):
    """Recharge l'artefact (utilisé par l'API, SHAP et les tests)."""
    return joblib.load(path)


def parse_args():
    parser = argparse.ArgumentParser(description="Entraîne le modèle MediGuess.")
    parser.add_argument("--n-estimators", type=int, default=200)
    parser.add_argument("--max-depth", type=int, default=30)
    parser.add_argument("--min-samples-leaf", type=int, default=2)
    parser.add_argument("--n-jobs", type=int, default=2)
    parser.add_argument(
        "--compress", type=int, default=3, help="Compression joblib (0-9)."
    )
    parser.add_argument(
        "--sample-frac",
        type=float,
        default=None,
        help="Fraction du dataset pour un test rapide (ex: 0.1).",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    params = {
        "n_estimators": args.n_estimators,
        "max_depth": args.max_depth,
        "min_samples_leaf": args.min_samples_leaf,
        "n_jobs": args.n_jobs,
    }

    print("Chargement des données...")
    features, target = load_data(sample_frac=args.sample_frac)
    print(
        f"{len(features)} lignes, {features.shape[1]} symptômes, "
        f"{target.nunique()} maladies"
    )

    print(f"Entraînement : {params}")
    model, x_test, y_test, train_seconds = train(features, target, params)
    print(f"Entraînement terminé en {train_seconds:.0f}s")

    metrics = evaluate(model, x_test, y_test)
    metrics["train_seconds"] = round(train_seconds, 1)
    print(f"Top-1 : {metrics['top1_accuracy']:.3f}")
    print(f"Top-{TOP_K} : {metrics[f'top{TOP_K}_accuracy']:.3f}")

    path, size_mb = save_artifact(
        model, features.columns, metrics, params, compress=args.compress
    )
    print(f"Artefact : {path} ({size_mb:.1f} Mo)")


if __name__ == "__main__":
    main()
