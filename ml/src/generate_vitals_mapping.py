"""
Catégorise les 773 maladies du dataset (dhivyeshrk/diseases-and-symptoms-dataset)
en grandes familles cliniques, puis leur associe une plage de signes vitaux
plausible (ou "non discriminant" quand les vitaux n'apportent rien).

Approche en deux passes :
1. Classification par mots-clés dans le nom de la maladie (rapide, fiable
   pour les cas évidents : "bronchite" -> respiratoire, "arthrite" -> ostéo-articulaire...)
2. Repli par score de symptômes : pour les maladies non reconnues par mot-clé,
   on regarde la fréquence des symptômes caractéristiques de chaque catégorie
   dans les lignes du dataset associées à cette maladie, et on prend la
   catégorie la mieux corrélée.

Sortie : un CSV disease -> category -> vitals (une ligne par maladie),
utilisable directement comme table de lookup côté jeu.
"""

import re
import pandas as pd

SRC = "../../data/cleaned_dataset.csv"
OUT = "../../data/disease_vitals_mapping.csv"

# ---------------------------------------------------------------------------
# 1. Catégories cliniques + mots-clés de nom de maladie
# ---------------------------------------------------------------------------
CATEGORY_KEYWORDS = {
    "infectieux_febrile": [
        "infection", "abscess", "sepsis", "flu", "influenza", "fever",
        "cellulitis", "meningitis", "mononucleosis", "tuberculosis",
        "malaria", "hepatitis", "hiv", "measles", "mumps", "rubella",
        "chickenpox", "shingles", "impetigo",
    ],
    "cardiovasculaire": [
        "heart", "cardiac", "cardio", "coronary", "myocard", "artery",
        "arrhythmia", "hypertension", "aneurysm", "vascular", "thrombosis",
        "embolism", "atrial", "ventricular", "pericard",
    ],
    "respiratoire": [
        "bronch", "asthma", "pneumonia", "lung", "pulmonary", "respiratory",
        "copd", "sinusitis", "pleuris", "emphysema", "apnea", "laryngitis",
        "pharyngitis", "tracheitis",
    ],
    "digestif": [
        "gastri", "intestin", "bowel", "colitis", "colon", "esophag",
        "stomach", "liver", "hepat", "pancreat", "gallbladder", "bile",
        "diarrhea", "constipation", "hernia", "appendicitis", "ulcer",
        "reflux",
    ],
    "dermatologique": [
        "skin", "derma", "eczema", "psoriasis", "acne", "rash", "wart",
        "melanoma", "mole", "urticaria", "dermatitis", "fungal", "ringworm",
    ],
    "osteo_articulaire": [
        "arthrit", "joint", "bone", "fracture", "osteo", "muscle",
        "tendon", "ligament", "spine", "spinal", "disc", "bursitis",
        "sprain", "strain", "scoliosis",
    ],
    "neurologique": [
        "brain", "neuro", "seizure", "epilep", "stroke", "migraine",
        "headache", "parkinson", "alzheimer", "sclerosis", "nerve",
        "paralysis", "neuropathy", "dementia",
    ],
    "psychiatrique": [
        "anxiety", "depress", "bipolar", "schizophren", "psychotic",
        "personality disorder", "stress reaction", "phobia", "panic",
        "eating disorder", "insomnia", "adjustment reaction",
    ],
    "renal_urinaire": [
        "kidney", "renal", "bladder", "urinary", "urethr", "cystitis",
        "nephro", "prostat",
    ],
    "endocrine_metabolique": [
        "diabetes", "thyroid", "hormone", "obesity", "metabolic",
        "adrenal", "pituitary", "cholesterol",
    ],
    "orl_ophtalmo": [
        "ear", "eye", "vision", "hearing", "nose", "nasal", "throat",
        "sinus", "conjunctiv", "cataract", "glaucoma", "otitis",
    ],
    "gyneco_obstetrique": [
        "pregnan", "menstru", "vaginal", "uterine", "ovary", "ovarian",
        "cervix", "cervical", "menopause", "labor", "postpartum",
    ],
    "hemato_oncologique": [
        "cancer", "tumor", "leukemia", "lymphoma", "anemia", "carcinoma",
        "sarcoma", "malignant",
    ],
}

# ---------------------------------------------------------------------------
# 2. Symptômes caractéristiques par catégorie (repli quand le nom ne suffit pas)
#    -> doivent correspondre exactement aux colonnes du CSV
# ---------------------------------------------------------------------------
SYMPTOM_CLUSTERS = {
    "infectieux_febrile": ["fever", "chills", "sweating", "flu-like syndrome", "feeling ill"],
    "cardiovasculaire": ["sharp chest pain", "palpitations", "irregular heartbeat",
                          "increased heart rate", "decreased heart rate", "chest tightness"],
    "respiratoire": ["shortness of breath", "cough", "wheezing", "breathing fast",
                      "difficulty breathing", "coughing up sputum"],
    "digestif": ["nausea", "vomiting", "diarrhea", "sharp abdominal pain",
                 "upper abdominal pain", "constipation", "heartburn"],
    "dermatologique": ["skin rash", "itching of skin", "abnormal appearing skin",
                        "skin lesion", "skin dryness, peeling, scaliness, or roughness"],
    "osteo_articulaire": ["joint pain", "back pain", "muscle pain", "muscle stiffness or tightness",
                           "joint stiffness or tightness"],
    "neurologique": ["headache", "dizziness", "seizures", "loss of sensation",
                      "disturbance of memory", "paresthesia"],
    "psychiatrique": ["anxiety and nervousness", "depression", "insomnia",
                       "depressive or psychotic symptoms", "fears and phobias"],
    "renal_urinaire": ["painful urination", "frequent urination", "blood in urine",
                        "low urine output", "retention of urine"],
    "endocrine_metabolique": ["excessive urination at night", "weight gain",
                               "recent weight loss", "thirst", "excessive appetite"],
    "orl_ophtalmo": ["sore throat", "nasal congestion", "ear pain", "diminished vision",
                      "diminished hearing", "eye redness"],
    "gyneco_obstetrique": ["vaginal discharge", "painful menstruation",
                            "problems during pregnancy", "pelvic pain"],
    "hemato_oncologique": ["fatigue", "pallor", "swollen lymph nodes", "recent weight loss"],
}

# ---------------------------------------------------------------------------
# 3. Profils de signes vitaux par catégorie
#    has_meaningful_vitals=False -> vitaux non discriminants, on affiche
#    des valeurs de population générale plutôt qu'un signal diagnostique.
# ---------------------------------------------------------------------------
NORMAL = dict(heart_rate="60-90 bpm", systolic_bp="110-130 mmHg", diastolic_bp="70-85 mmHg",
              resp_rate="12-18 /min", temperature="36.5-37.2 °C", spo2="97-100 %")

VITAL_PROFILES = {
    "infectieux_febrile": dict(heart_rate="90-120 bpm", systolic_bp="100-120 mmHg",
                                diastolic_bp="65-80 mmHg", resp_rate="18-24 /min",
                                temperature="38.0-40.0 °C", spo2="94-98 %",
                                has_meaningful_vitals=True,
                                note="Fièvre et tachycardie typiques d'un syndrome infectieux"),
    "cardiovasculaire": dict(heart_rate="45-140 bpm (variable, souvent irrégulier)",
                              systolic_bp="130-180 mmHg", diastolic_bp="85-110 mmHg",
                              resp_rate="16-22 /min", temperature="36.5-37.2 °C", spo2="92-97 %",
                              has_meaningful_vitals=True,
                              note="Tension et rythme cardiaque anormaux évocateurs"),
    "respiratoire": dict(heart_rate="85-110 bpm", systolic_bp="110-130 mmHg",
                          diastolic_bp="70-85 mmHg", resp_rate="20-30 /min",
                          temperature="36.8-38.5 °C", spo2="88-95 %",
                          has_meaningful_vitals=True,
                          note="Fréquence respiratoire élevée et SpO2 abaissée"),
    "renal_urinaire": dict(heart_rate="75-100 bpm", systolic_bp="120-150 mmHg",
                            diastolic_bp="80-95 mmHg", resp_rate="14-20 /min",
                            temperature="36.7-38.0 °C", spo2="96-99 %",
                            has_meaningful_vitals=True,
                            note="Tension parfois élevée, fièvre possible si infection associée"),
    "endocrine_metabolique": dict(heart_rate="70-110 bpm", systolic_bp="115-140 mmHg",
                                   diastolic_bp="75-90 mmHg", resp_rate="14-18 /min",
                                   temperature="36.3-37.5 °C", spo2="96-99 %",
                                   has_meaningful_vitals=True,
                                   note="Rythme cardiaque et tension modérément affectés"),
    "hemato_oncologique": dict(heart_rate="80-110 bpm", systolic_bp="100-125 mmHg",
                                diastolic_bp="65-80 mmHg", resp_rate="16-22 /min",
                                temperature="36.5-38.0 °C", spo2="94-98 %",
                                has_meaningful_vitals=True,
                                note="Tachycardie et pâleur liées à l'anémie possible"),
    # Catégories où les vitaux n'apportent pas d'information diagnostique utile
    "digestif": dict(**NORMAL, has_meaningful_vitals=False,
                      note="Vitaux généralement normaux ; le diagnostic repose sur les symptômes"),
    "dermatologique": dict(**NORMAL, has_meaningful_vitals=False,
                            note="Pathologie cutanée : les signes vitaux ne sont pas discriminants"),
    "osteo_articulaire": dict(**NORMAL, has_meaningful_vitals=False,
                               note="Atteinte locale ; vitaux non informatifs"),
    "neurologique": dict(**NORMAL, has_meaningful_vitals=False,
                          note="Vitaux généralement normaux hors urgence vitale"),
    "psychiatrique": dict(**NORMAL, has_meaningful_vitals=False,
                           note="Pas de signature physiologique fiable"),
    "orl_ophtalmo": dict(**NORMAL, has_meaningful_vitals=False,
                          note="Atteinte locale ; vitaux non informatifs"),
    "gyneco_obstetrique": dict(**NORMAL, has_meaningful_vitals=False,
                                note="Vitaux non discriminants hors complication"),
    "other": dict(**NORMAL, has_meaningful_vitals=False,
                  note="Catégorie non déterminée avec confiance"),
}


def classify_by_keyword(name: str):
    name = name.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in name for kw in keywords):
            return category
    return None


def classify_by_symptoms(disease_rows: pd.DataFrame):
    """Score chaque catégorie par la fréquence moyenne de ses symptômes
    caractéristiques dans les lignes de cette maladie, renvoie la meilleure."""
    best_cat, best_score = "other", 0.15  # seuil minimal pour accepter un match
    for category, symptoms in SYMPTOM_CLUSTERS.items():
        cols = [s for s in symptoms if s in disease_rows.columns]
        if not cols:
            continue
        score = disease_rows[cols].mean().mean()
        if score > best_score:
            best_cat, best_score = category, score
    return best_cat


def main():
    df = pd.read_csv(SRC)
    diseases = sorted(df["diseases"].unique())

    rows = []
    for disease in diseases:
        category = classify_by_keyword(disease)
        if category is None:
            category = classify_by_symptoms(df[df["diseases"] == disease])
        profile = VITAL_PROFILES[category]
        rows.append({
            "disease": disease,
            "category": category,
            "heart_rate": profile["heart_rate"],
            "systolic_bp": profile["systolic_bp"],
            "diastolic_bp": profile["diastolic_bp"],
            "resp_rate": profile["resp_rate"],
            "temperature": profile["temperature"],
            "spo2": profile["spo2"],
            "has_meaningful_vitals": profile["has_meaningful_vitals"],
            "note": profile["note"],
        })

    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False)

    print(f"{len(out)} maladies traitées -> {OUT}\n")
    print("Répartition par catégorie :")
    print(out["category"].value_counts().to_string())
    print(f"\nMaladies avec vitaux jugés informatifs : {out['has_meaningful_vitals'].sum()} / {len(out)}")


if __name__ == "__main__":
    main()
