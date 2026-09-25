# Contrat d'API MediGuess

Format des échanges entre le front (`frontend/`) et le backend (API Gateway + Lambda).
Tant que le backend n'existe pas, `frontend/api.js` simule ces réponses (`USE_MOCK = true`).

## `GET /case`
Tire un nouveau cas clinique.

```json
{
  "case_id": "a1b2c3",
  "symptoms": ["cough", "fever", "shortness of breath"],
  "choices": ["pneumonia", "acute bronchitis", "asthma", "common cold"]
}
```
- `choices` : 4 maladies mélangées (bonne réponse + 3 distracteurs issus de `predict_top_k`).
- La bonne réponse n'est **jamais** envoyée ici, sinon elle serait visible dans le navigateur.

## `POST /answer`
Corps : `{ "case_id": "a1b2c3", "answer": "pneumonia" }`

```json
{
  "correct": true,
  "correct_answer": "pneumonia",
  "points": 10,
  "feedback": "Bien vu : shortness of breath était l'indice le plus parlant.",
  "explanation": {
    "disease": "pneumonia",
    "factors": [
      { "symptom": "shortness of breath", "present": true, "contribution": 0.021, "direction": "pour" }
    ]
  }
}
```
- `explanation` = sortie de `CaseExplainer.explain()` (ml/src/explain.py), pour la bonne réponse.
- `points` : calculé côté serveur (système de scoring, #13).
- `feedback` : phrase générée par template à partir du top 3 (#14).

## À trancher côté backend
Lambda est sans état : pour retrouver la bonne réponse à partir de `case_id`,
il faut soit stocker le cas (ex. DynamoDB avec expiration), soit renvoyer un
`case_id` signé qui contient la réponse chiffrée.
