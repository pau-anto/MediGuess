"""Fonctions réservées aux admins : joueurs, classement, statistiques.

Le droit admin est vérifié par l'API (api.py, require_admin) avant tout
appel à ces méthodes.
"""

import json

from backend.src.auth import public_profile


class Forbidden(Exception):
    """Action refusée (ex. un admin qui supprime son propre compte)."""


class AdminService:
    def __init__(self, store):
        self.store = store

    # ------------------------------------------------------------------
    # Joueurs
    # ------------------------------------------------------------------
    def players(self):
        """Tous les comptes avec leurs statistiques, du plus actif au moins actif."""
        rows = [public_profile(user) for user in self.store.query("users")]
        return sorted(rows, key=lambda r: (-r["games_played"], r["username"].lower()))

    def delete_player(self, username, by_admin):
        if username.lower() == by_admin.lower():
            raise Forbidden("Un admin ne peut pas supprimer son propre compte.")
        if self.store.pop("users", username.lower()) is None:
            return False
        # Ses scores sortent du classement. Ses anciennes parties restent
        # dans les statistiques des maladies (elles sont anonymes).
        for row in self.store.query("scores"):
            if row["username"].lower() == username.lower():
                self.store.pop("scores", row["_key"])
        return True

    # ------------------------------------------------------------------
    # Classement
    # ------------------------------------------------------------------
    def scores(self):
        """Toutes les parties classées (pas seulement le meilleur score)."""
        rows = self.store.query("scores")
        rows.sort(key=lambda r: (-r["score"], r["finished_at"]))
        return [
            {
                "game_id": r["_key"],
                "username": r["username"],
                "score": r["score"],
                "cases": r["cases"],
                "correct": r["correct"],
                "finished_at": r["finished_at"],
            }
            for r in rows
        ]

    def delete_score(self, game_id):
        return self.store.pop("scores", game_id) is not None

    def reset_scores(self):
        """Vide le classement. Les statistiques des profils (record, nombre
        de parties) ne sont pas modifiées."""
        rows = self.store.query("scores")
        for row in rows:
            self.store.pop("scores", row["_key"])
        return len(rows)

    # ------------------------------------------------------------------
    # Statistiques du modèle / des maladies
    # ------------------------------------------------------------------
    def stats(self, min_shown=1):
        diseases = []
        total_shown = total_correct = 0
        for row in self.store.query("diseases"):
            total_shown += row["shown"]
            total_correct += row["correct"]
            if row["shown"] < min_shown:
                continue
            confusions = json.loads(row["confusions"])
            top = max(confusions.items(), key=lambda kv: kv[1]) if confusions else None
            diseases.append(
                {
                    "disease": row["disease"],
                    "shown": row["shown"],
                    "correct": row["correct"],
                    "error_rate": round(1 - row["correct"] / row["shown"], 3),
                    "top_confusion": top[0] if top else None,
                    "top_confusion_count": top[1] if top else 0,
                }
            )
        diseases.sort(key=lambda d: (-d["error_rate"], -d["shown"]))
        games = self.store.query("games")
        return {
            "players": len(self.store.query("users")),
            "games": sum(1 for g in games if not g.get("admin_mode")),
            "answers": total_shown,
            "accuracy": round(total_correct / total_shown, 3) if total_shown else 0,
            "diseases": diseases,
        }

    def reset_stats(self):
        """Remet à zéro les statistiques des maladies."""
        rows = self.store.query("diseases")
        for row in rows:
            self.store.pop("diseases", row["_key"])
        return len(rows)
