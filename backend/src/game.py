"""Boucle de jeu MediGuess : partie -> cas -> 4 choix -> réponse -> score.

Le backend ne charge PAS le modèle : les cas, leurs 4 choix et le top 3
SHAP sont pré-calculés par ml/src/build_case_bank.py dans un JSON.

Le score et les vies sont tenus côté serveur : le navigateur ne fait
qu'afficher. Sinon n'importe qui pourrait envoyer un faux score au
classement depuis la console du navigateur.

Logique pure, sans dépendance web : api.py ne fait qu'appeler ces classes.
"""

import hashlib
import json
import random
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.src.storage import MemoryStore

DEFAULT_BANK_PATH = Path(__file__).resolve().parents[1] / "data" / "case_bank.json"
MAX_LIVES = 3
POINTS_CORRECT = 10  # scoring provisoire, à remplacer par la tâche #13
CASE_TTL_SECONDS = 30 * 60  # cas hors partie : expire après 30 min


class NotFound(Exception):
    """Partie ou cas inconnu, déjà joué ou expiré."""


class Forbidden(Exception):
    """La partie appartient à un autre joueur."""


class GameFinished(Exception):
    """La partie est terminée (plus de vies)."""


def load_bank(path=DEFAULT_BANK_PATH):
    with open(path, encoding="utf-8") as f:
        bank = json.load(f)
    if not bank["cases"]:
        raise ValueError(f"Banque de cas vide : {path}")
    return bank["cases"]


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _public_game(game):
    return {
        "game_id": game["game_id"],
        "username": game["username"] or None,
        "score": game["score"],
        "lives": game["lives"],
        "cases": game["cases"],
        "correct": game["correct"],
        "game_over": game["finished"],
        "admin_mode": bool(game.get("admin_mode")),
    }


def disease_key(disease):
    """Clé de table pour une maladie (les noms peuvent contenir « / » ou
    « ? », interdits dans une clé Azure Table)."""
    return hashlib.sha1(disease.encode("utf-8")).hexdigest()[:20]


class GameEngine:
    def __init__(self, cases, store=None, accounts=None, seed=None):
        self.cases = cases
        self.store = store if store is not None else MemoryStore()
        self.accounts = accounts  # None : pas de statistiques joueur (tests)
        self.rng = random.Random(seed)

    # ------------------------------------------------------------------
    # Parties
    # ------------------------------------------------------------------
    def start_game(self, username=None, admin_mode=False):
        """username None = invité : il joue, mais son score n'est pas classé.

        admin_mode : la bonne réponse est envoyée avec chaque cas (pour tester
        ou présenter le jeu). La partie ne compte ni au classement ni dans les
        statistiques des maladies. Le droit admin est vérifié par l'API.

        Un joueur connecté n'a qu'une partie en cours : en commencer une
        nouvelle termine l'ancienne (son score est enregistré)."""
        if username:
            for old in self.store.query("games", username=username, finished=False):
                self._finish(old)
        game = {
            "game_id": uuid.uuid4().hex,
            "username": username or "",
            "score": 0,
            "lives": MAX_LIVES,
            "cases": 0,
            "correct": 0,
            "finished": False,
            "admin_mode": bool(admin_mode),
            "pending_case": "",  # cas affiché mais pas encore répondu
            "created": time.time(),
        }
        self.store.insert("games", game["game_id"], game)
        return _public_game(game)

    def _owned_game(self, game_id, username):
        game = self.store.get("games", game_id)
        if game is None:
            raise NotFound("Partie inconnue.")
        if game["username"] and game["username"] != username:
            raise Forbidden("Cette partie appartient à un autre joueur.")
        return game

    def get_game(self, game_id, username=None):
        """État d'une partie (pour la reprendre)."""
        return _public_game(self._owned_game(game_id, username))

    def current_game(self, username):
        """Partie en cours (sauvegardée) du joueur connecté, ou None.
        Une partie sans aucune réponse n'est pas proposée : rien à reprendre."""
        games = [
            g
            for g in self.store.query("games", username=username, finished=False)
            if g["cases"] > 0
        ]
        if not games:
            return None
        return _public_game(max(games, key=lambda g: g["created"]))

    def finish_game(self, game_id, username=None):
        """Le joueur arrête : la partie se termine et son score est enregistré."""
        game = self._owned_game(game_id, username)
        if not game["finished"]:
            self._finish(game)
        return _public_game(game)

    def _finish(self, game):
        game["finished"] = True
        game["finished_at"] = _now_iso()
        if game.get("pending_case"):
            self.store.pop("cases", game["pending_case"])
            game["pending_case"] = ""
        self._record_score(game)
        self.store.upsert("games", game["game_id"], game)

    # ------------------------------------------------------------------
    # Cas
    # ------------------------------------------------------------------
    def new_case(self, game_id=None, username=None):
        game = None
        if game_id:
            game = self._owned_game(game_id, username)
            if game["finished"]:
                raise GameFinished("La partie est terminée.")
            # Partie reprise avec un cas non répondu : on renvoie LE MÊME cas.
            # Sinon quitter/reprendre permettrait de passer un cas difficile.
            pending = game.get("pending_case") and self.store.get(
                "cases", game["pending_case"]
            )
            if pending:
                return self._case_view(game["pending_case"], pending, game)

        index = self.rng.randrange(len(self.cases))
        case = self.cases[index]
        case_id = uuid.uuid4().hex
        # Ordres mélangés à chaque tirage : l'ordre du dataset ou du modèle
        # donnerait des indices. La bonne réponse ne quitte JAMAIS le serveur.
        stored = {
            "bank_index": index,
            "game_id": game_id or "",
            "symptoms": json.dumps(
                self.rng.sample(case["symptoms"], len(case["symptoms"]))
            ),
            "choices": json.dumps(
                self.rng.sample(case["choices"], len(case["choices"]))
            ),
            "created": time.time(),
        }
        self.store.insert("cases", case_id, stored)
        if game is not None:
            game["pending_case"] = case_id
            self.store.upsert("games", game["game_id"], game)
        return self._case_view(case_id, stored, game)

    def _case_view(self, case_id, stored, game):
        result = {
            "case_id": case_id,
            "symptoms": json.loads(stored["symptoms"]),
            "choices": json.loads(stored["choices"]),
        }
        if game is not None and game.get("admin_mode"):
            # mode admin uniquement
            result["answer"] = self.cases[stored["bank_index"]]["answer"]
        return result

    def answer(self, case_id, answer, username=None):
        stored = self.store.pop("cases", case_id)  # un cas ne se joue qu'une fois
        expired = stored is not None and (
            not stored["game_id"] and stored["created"] < time.time() - CASE_TTL_SECONDS
        )
        if stored is None or expired:
            raise NotFound("Cas inconnu, déjà joué ou expiré.")
        case = self.cases[stored["bank_index"]]
        correct = answer == case["answer"]
        points = POINTS_CORRECT if correct else 0
        result = {
            "correct": correct,
            "correct_answer": case["answer"],
            "points": points,
            "feedback": build_feedback(correct, case["explanation"]),
            "explanation": case["explanation"],
        }
        if stored["game_id"]:
            game = self._owned_game(stored["game_id"], username)
            if game["finished"]:
                raise GameFinished("La partie est terminée.")
            if not game.get("admin_mode"):
                self._record_disease(case["answer"], answer, correct)
            result["game"] = self._apply_to_game(game, correct, points)
        return result

    def _apply_to_game(self, game, correct, points):
        game["pending_case"] = ""
        game["score"] += points
        game["cases"] += 1
        game["correct"] += int(correct)
        if not correct:
            game["lives"] -= 1
        if game["lives"] <= 0:
            self._finish(game)
        else:
            self.store.upsert("games", game["game_id"], game)
        return _public_game(game)

    def _record_score(self, game):
        if not game["username"] or game.get("admin_mode") or game["cases"] == 0:
            return  # invité, mode admin ou partie sans réponse : pas de classement
        self.store.insert(
            "scores",
            game["game_id"],
            {
                "username": game["username"],
                "score": game["score"],
                "cases": game["cases"],
                "correct": game["correct"],
                "finished_at": game["finished_at"],
            },
        )
        if self.accounts is not None:
            self.accounts.record_game(game["username"], game)

    def _record_disease(self, disease, chosen, correct):
        """Compteurs par maladie : combien de fois présentée, trouvée, et avec
        quelle autre maladie les joueurs la confondent (statistiques admin)."""
        key = disease_key(disease)
        stats = self.store.get("diseases", key) or {
            "disease": disease,
            "shown": 0,
            "correct": 0,
            "confusions": "{}",  # JSON : Table Storage ne stocke pas de dict
        }
        stats["shown"] += 1
        if correct:
            stats["correct"] += 1
        else:
            confusions = json.loads(stats["confusions"])
            confusions[chosen] = confusions.get(chosen, 0) + 1
            stats["confusions"] = json.dumps(confusions, ensure_ascii=False)
        self.store.upsert("diseases", key, stats)

    # ------------------------------------------------------------------
    # Scores
    # ------------------------------------------------------------------
    def leaderboard(self, limit=10):
        """Meilleur score de chaque joueur, du plus haut au plus bas."""
        best = {}
        for row in self.store.query("scores"):
            current = best.get(row["username"])
            if current is None or row["score"] > current["score"]:
                best[row["username"]] = row
        ranking = sorted(best.values(), key=lambda r: (-r["score"], r["finished_at"]))
        return [
            {
                "rank": rank,
                "username": row["username"],
                "score": row["score"],
                "cases": row["cases"],
                "finished_at": row["finished_at"],
            }
            for rank, row in enumerate(ranking[:limit], start=1)
        ]

    def history(self, username, limit=20):
        """Dernières parties d'un joueur, la plus récente en premier."""
        rows = self.store.query("scores", username=username)
        rows.sort(key=lambda r: r["finished_at"], reverse=True)
        return [
            {k: r[k] for k in ("score", "cases", "correct", "finished_at")}
            for r in rows[:limit]
        ]


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
