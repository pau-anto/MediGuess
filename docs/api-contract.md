# Contrat d'API MediGuess

Format des échanges entre le front (`frontend/api.js`) et le backend (`backend/src/api.py`).
Les erreurs renvoient `{ "detail": "message" }` (ou une liste d'erreurs de validation en `422`).

## Authentification

Comptes : pseudo + mot de passe. L'API renvoie un **jeton JWT** valable 7 jours, que le
front envoie ensuite dans l'en-tête `Authorization: Bearer <jeton>`.
Sans jeton, on joue en **invité** : la partie fonctionne mais le score n'est pas enregistré.

| Route | Jeton | Rôle |
|---|---|---|
| `POST /auth/register` | — | Créer un compte |
| `POST /auth/login` | — | Se connecter |
| `GET /me` | obligatoire | Statistiques du joueur |
| `GET /me/games` | obligatoire | 20 dernières parties |
| `POST /games` | optionnel | Commencer une partie |
| `GET /games/current` | obligatoire | Partie sauvegardée du joueur (`404` si aucune) |
| `GET /games/{game_id}` | optionnel | État d'une partie (reprise d'un invité) |
| `POST /games/{game_id}/finish` | optionnel | Terminer maintenant (score enregistré, non utilisé par le front) |
| `GET /case?game_id=…` | optionnel | Tirer un cas |
| `POST /answer` | optionnel | Répondre |
| `GET /leaderboard?limit=10` | — | Classement |
| `GET /health` | — | État de l'API |
| `/admin/...` | admin | Voir [Administration](#administration) |

### `POST /auth/register` → `201`
Corps : `{ "username": "Nina", "password": "motdepasse" }`
- `username` : 3 à 20 caractères `A-Z a-z 0-9 _ -`, unique sans tenir compte de la casse.
- `password` : 8 à 128 caractères. Stocké uniquement sous forme de hash scrypt salé.

Réponse : `{ "token": "eyJ...", "username": "Nina" }`. Erreurs : `409` pseudo pris, `422` format.

### `POST /auth/login` → `200`
Même corps et même réponse. `401` si pseudo ou mot de passe incorrect.

### `GET /me` → `200`
```json
{ "username": "Nina", "is_admin": false, "created": 1793900186.2, "games_played": 4,
  "best_score": 60, "total_cases": 21, "total_correct": 15, "accuracy": 0.714 }
```

### `GET /me/games` → `200`
```json
[{ "score": 60, "cases": 9, "correct": 6, "finished_at": "2026-11-05T18:16:59+00:00" }]
```

## Partie

Le **score et les vies sont tenus par le serveur** (3 vies, 10 points par bon diagnostic) :
le front ne fait qu'afficher, il ne peut pas envoyer un faux score.

### `POST /games` → `201`
Corps optionnel : `{ "admin_mode": true }` (admins uniquement, sinon `403`).
```json
{ "game_id": "e99b…", "username": "Nina", "score": 0, "lives": 3,
  "cases": 0, "correct": 0, "game_over": false, "admin_mode": false }
```
`username` vaut `null` pour un invité.

### Sauvegarde et reprise
- La partie est **sauvegardée en continu** côté serveur (table `games`) : le joueur peut
  quitter à tout moment et reprendre plus tard, y compris sur un autre appareil s'il est connecté.
- Invité : le front garde le `game_id` dans le navigateur et reprend avec `GET /games/{game_id}`.
- Un cas affiché mais pas encore répondu reste attaché à la partie : à la reprise,
  `GET /case` renvoie **le même cas** (impossible de « passer » un cas difficile en quittant).
- Un joueur connecté n'a qu'une partie en cours : `POST /games` termine l'ancienne et enregistre son score.
- Une partie **sans aucune réponse** n'est pas une sauvegarde (`/games/current` l'ignore)
  et n'entre jamais au classement.
- `POST /games/{game_id}/finish` existe pour terminer une partie sans en commencer une autre ;
  le front ne l'utilise pas (« Nouvelle partie » suffit).

### `GET /case?game_id=e99b…` → `200`
```json
{
  "case_id": "a1b2c3",
  "symptoms": ["cough", "fever", "shortness of breath"],
  "choices": ["pneumonia", "acute bronchitis", "asthma", "common cold"]
}
```
- La bonne réponse n'est **jamais** envoyée ici, sauf dans une partie en **mode admin**
  (champ `answer` en plus).
- Erreurs : `404` partie inconnue, `403` partie d'un autre joueur, `409` partie terminée.
- Sans `game_id` : cas isolé, sans score ni vies (compatibilité).

### `POST /answer` → `200`
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
  },
  "game": { "game_id": "e99b…", "username": "Nina", "score": 10, "lives": 3,
            "cases": 1, "correct": 1, "game_over": false }
}
```
- `explanation` : top 3 SHAP pré-calculé pour la bonne réponse.
- `game` : état de la partie après la réponse (absent pour un cas sans `game_id`).
- À 0 vie, `game_over` passe à `true` ; pour un joueur connecté, le score entre au classement.
- Chaque réponse d'une partie normale alimente les statistiques par maladie.
  Une partie en mode admin ne compte ni au classement, ni dans les statistiques, ni dans le profil.
- Erreurs : `404` cas inconnu ou déjà joué (un cas hors partie expire après 30 min),
  `409` partie terminée.

## `GET /leaderboard?limit=10` → `200`
Meilleur score de chaque joueur connecté, du plus haut au plus bas (`limit` : 1 à 50).
```json
[{ "rank": 1, "username": "Nina", "score": 60, "cases": 9,
   "finished_at": "2026-11-05T18:16:59+00:00" }]
```

## Administration

Un admin est un compte dont le champ **`is_admin` vaut `true`** dans la table `users`
(créé à `false` à l'inscription ; le texte `"true"` est aussi accepté).
Ce champ se règle **à la main** dans le portail Azure (aucune route ne permet de devenir admin)
et il est relu à chaque requête : le retirer coupe l'accès immédiatement.
Sans jeton : `401` ; jeton d'un non-admin : `403`.

| Route | Rôle |
|---|---|
| `GET /admin/players` | Comptes + statistiques (jamais le hash du mot de passe) |
| `DELETE /admin/players/{pseudo}` | Supprime le compte et ses scores (`403` sur son propre compte) |
| `GET /admin/scores` | Toutes les parties classées, avec leur `game_id` |
| `DELETE /admin/scores/{game_id}` | Supprime un score |
| `POST /admin/scores/reset` | Vide le classement (profils inchangés) |
| `GET /admin/stats?min_shown=1` | Stats globales + maladies triées de la plus ratée à la moins ratée |
| `POST /admin/stats/reset` | Remet les statistiques des maladies à zéro |

`GET /admin/stats` :
```json
{ "players": 3, "games": 12, "answers": 57, "accuracy": 0.42,
  "diseases": [{ "disease": "panic disorder", "shown": 6, "correct": 1, "error_rate": 0.833,
                 "top_confusion": "anxiety", "top_confusion_count": 4 }] }
```

## Stockage (Azure Table Storage, ou mémoire en local)

| Table | Clé | Contenu |
|---|---|---|
| `users` | pseudo en minuscules | pseudo, sel + hash du mot de passe, statistiques, `is_admin` |
| `games` | `game_id` | joueur, score, vies, nb de cas, terminée ou non |
| `cases` | `case_id` | index dans la banque de cas, partie ; effacé à la réponse |
| `scores` | `game_id` | parties terminées des joueurs connectés (classement) |
| `diseases` | hash du nom | par maladie : fois présentée, trouvée, confusions (JSON) |

`JWT_SECRET` (signature des jetons) est généré par Terraform et passé en secret à la Container App.
