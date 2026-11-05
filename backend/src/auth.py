"""Comptes joueurs : pseudo + mot de passe, jeton JWT.

- Mot de passe : jamais stocké. On garde un hash scrypt (bibliothèque
  standard Python) avec un sel aléatoire propre à chaque compte.
- Connexion : l'API renvoie un jeton JWT signé (HS256) valable 7 jours.
  Le front l'envoie dans l'en-tête « Authorization: Bearer <jeton> ».
- JWT_SECRET (variable d'environnement) signe les jetons. Sur Azure, il est
  généré par Terraform. En local, s'il manque, un secret aléatoire est créé
  au démarrage (les jetons ne survivent alors pas à un redémarrage).
"""

import hashlib
import hmac
import os
import secrets
import time

import jwt

from backend.src.storage import Conflict

TOKEN_TTL_SECONDS = 7 * 24 * 3600
_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32, "maxmem": 64 * 1024 * 1024}


class AuthError(Exception):
    """Identifiants ou jeton invalides."""


def hash_password(password, salt=None):
    salt = salt if salt is not None else secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, **_SCRYPT)
    return salt.hex(), digest.hex()


def verify_password(password, salt_hex, hash_hex):
    _, digest = hash_password(password, bytes.fromhex(salt_hex))
    return hmac.compare_digest(digest, hash_hex)


class AccountService:
    def __init__(self, store, secret=None):
        self.store = store
        self.secret = secret or os.environ.get("JWT_SECRET") or secrets.token_hex(32)

    # ------------------------------------------------------------------
    # Jetons
    # ------------------------------------------------------------------
    def create_token(self, username):
        now = int(time.time())
        payload = {"sub": username, "iat": now, "exp": now + TOKEN_TTL_SECONDS}
        return jwt.encode(payload, self.secret, algorithm="HS256")

    def username_from_token(self, token):
        try:
            payload = jwt.decode(token, self.secret, algorithms=["HS256"])
        except jwt.PyJWTError as err:
            raise AuthError("Session expirée ou invalide.") from err
        return payload["sub"]

    # ------------------------------------------------------------------
    # Comptes
    # ------------------------------------------------------------------
    def register(self, username, password):
        salt, digest = hash_password(password)
        user = {
            "username": username,
            "salt": salt,
            "password_hash": digest,
            "created": time.time(),
            "is_admin": False,  # à passer à true dans le portail pour un admin
            "games_played": 0,
            "best_score": 0,
            "total_cases": 0,
            "total_correct": 0,
        }
        try:
            # Clé en minuscules : « Nina » et « nina » sont le même compte.
            self.store.insert("users", username.lower(), user)
        except Conflict as err:
            raise Conflict("Ce pseudo est déjà pris.") from err
        return self.create_token(username)

    def login(self, username, password):
        user = self.store.get("users", username.lower())
        if user is None:
            hash_password(password)  # même durée de réponse qu'un vrai compte
            raise AuthError("Pseudo ou mot de passe incorrect.")
        if not verify_password(password, user["salt"], user["password_hash"]):
            raise AuthError("Pseudo ou mot de passe incorrect.")
        return user["username"], self.create_token(user["username"])

    def profile(self, username):
        user = self.store.get("users", username.lower())
        if user is None:
            raise AuthError("Compte introuvable.")
        return public_profile(user)

    def is_admin(self, username):
        """Admin = champ is_admin à true dans la table users. Il se règle à la
        main dans le portail Azure : aucune route de l'API ne permet de
        devenir admin."""
        user = self.store.get("users", username.lower()) if username else None
        return bool(user and as_bool(user.get("is_admin")))

    def record_game(self, username, game):
        """Met à jour les statistiques du joueur à la fin d'une partie."""
        key = username.lower()
        user = self.store.get("users", key)
        if user is None:
            return
        user["games_played"] += 1
        user["best_score"] = max(user["best_score"], game["score"])
        user["total_cases"] += game["cases"]
        user["total_correct"] += game["correct"]
        self.store.upsert("users", key, user)


def public_profile(user):
    """Ce qu'on peut montrer d'un compte (jamais le hash du mot de passe)."""
    accuracy = user["total_correct"] / user["total_cases"] if user["total_cases"] else 0
    return {
        "username": user["username"],
        "is_admin": as_bool(user.get("is_admin")),
        "created": user["created"],
        "games_played": user["games_played"],
        "best_score": user["best_score"],
        "total_cases": user["total_cases"],
        "total_correct": user["total_correct"],
        "accuracy": round(accuracy, 3),
    }


def as_bool(value):
    """is_admin saisi à la main dans le portail : accepte le type Boolean
    mais aussi le texte « true » / « True » / « 1 »."""
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "oui", "yes")
    return bool(value)
