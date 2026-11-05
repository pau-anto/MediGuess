"""API HTTP de MediGuess (FastAPI), conforme à docs/api-contract.md.

En local, depuis la racine du repo :
    uvicorn backend.src.api:app --reload --port 8080

Configuration par variables d'environnement :
- AZURE_STORAGE_CONNECTION_STRING : Table Storage (sinon : en mémoire)
- JWT_SECRET : clé de signature des jetons de connexion
- CASE_BANK_PATH : chemin de la banque de cas (défaut : backend/data/)
- ALLOWED_ORIGINS : origines CORS autorisées, séparées par des virgules
"""

import os
from contextlib import asynccontextmanager
from typing import Annotated, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from backend.src import admin as admin_mod
from backend.src.admin import AdminService
from backend.src.auth import AccountService, AuthError
from backend.src.game import (
    DEFAULT_BANK_PATH,
    Forbidden,
    GameEngine,
    GameFinished,
    NotFound,
    load_bank,
)
from backend.src.storage import Conflict, make_store

state = {}


@asynccontextmanager
async def lifespan(_app):
    store = make_store()
    cases = load_bank(os.environ.get("CASE_BANK_PATH", DEFAULT_BANK_PATH))
    state["accounts"] = AccountService(store)
    state["engine"] = GameEngine(cases, store, state["accounts"])
    state["admin"] = AdminService(store)
    yield
    state.clear()


app = FastAPI(title="MediGuess API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("ALLOWED_ORIGINS", "*").split(","),
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)

# ----------------------------------------------------------------------
# Joueur connecté (en-tête « Authorization: Bearer <jeton> »)
# ----------------------------------------------------------------------
bearer = HTTPBearer(auto_error=False)
Credentials = Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer)]


def optional_user(credentials: Credentials) -> Optional[str]:
    """Pseudo du joueur connecté, ou None pour un invité."""
    if credentials is None:
        return None
    try:
        return state["accounts"].username_from_token(credentials.credentials)
    except AuthError as err:
        raise HTTPException(status_code=401, detail=err.args[0]) from err


def required_user(username: Annotated[Optional[str], Depends(optional_user)]) -> str:
    if username is None:
        raise HTTPException(status_code=401, detail="Connexion requise.")
    return username


def required_admin(username: Annotated[str, Depends(required_user)]) -> str:
    # Relu dans la base à chaque requête : retirer le droit admin dans le
    # portail prend effet immédiatement, même avec un jeton encore valide.
    if not state["accounts"].is_admin(username):
        raise HTTPException(status_code=403, detail="Réservé aux administrateurs.")
    return username


OptionalUser = Annotated[Optional[str], Depends(optional_user)]
RequiredUser = Annotated[str, Depends(required_user)]
AdminUser = Annotated[str, Depends(required_admin)]


def game_errors(func, *args, **kwargs):
    """Traduit les erreurs du moteur de jeu en codes HTTP."""
    try:
        return func(*args, **kwargs)
    except NotFound as err:
        raise HTTPException(status_code=404, detail=err.args[0]) from err
    except Forbidden as err:
        raise HTTPException(status_code=403, detail=err.args[0]) from err
    except GameFinished as err:
        raise HTTPException(status_code=409, detail=err.args[0]) from err


# ----------------------------------------------------------------------
# Modèles des requêtes
# ----------------------------------------------------------------------
class RegisterRequest(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9_-]{3,20}$")
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(max_length=20)
    password: str = Field(max_length=128)


class GameRequest(BaseModel):
    admin_mode: bool = False


class AnswerRequest(BaseModel):
    case_id: str
    answer: str


# ----------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok", "cases": len(state["engine"].cases)}


@app.post("/auth/register", status_code=201)
def register(body: RegisterRequest):
    try:
        token = state["accounts"].register(body.username, body.password)
    except Conflict as err:
        raise HTTPException(status_code=409, detail=err.args[0]) from err
    return {"token": token, "username": body.username}


@app.post("/auth/login")
def login(body: LoginRequest):
    try:
        username, token = state["accounts"].login(body.username, body.password)
    except AuthError as err:
        raise HTTPException(status_code=401, detail=err.args[0]) from err
    return {"token": token, "username": username}


@app.get("/me")
def me(username: RequiredUser):
    try:
        return state["accounts"].profile(username)
    except AuthError as err:
        raise HTTPException(status_code=401, detail=err.args[0]) from err


@app.get("/me/games")
def my_games(username: RequiredUser):
    return state["engine"].history(username)


@app.post("/games", status_code=201)
def start_game(username: OptionalUser, body: Optional[GameRequest] = None):
    admin_mode = bool(body and body.admin_mode)
    if admin_mode and not state["accounts"].is_admin(username):
        raise HTTPException(status_code=403, detail="Mode admin réservé aux admins.")
    return state["engine"].start_game(username, admin_mode)


@app.get("/games/current")
def current_game(username: RequiredUser):
    """Partie sauvegardée (non terminée) du joueur connecté."""
    game = state["engine"].current_game(username)
    if game is None:
        raise HTTPException(status_code=404, detail="Aucune partie en cours.")
    return game


@app.get("/games/{game_id}")
def get_game(game_id: str, username: OptionalUser):
    return game_errors(state["engine"].get_game, game_id, username)


@app.post("/games/{game_id}/finish")
def finish_game(game_id: str, username: OptionalUser):
    """Terminer maintenant : le score est enregistré au classement."""
    return game_errors(state["engine"].finish_game, game_id, username)


@app.get("/case")
def get_case(username: OptionalUser, game_id: Optional[str] = None):
    return game_errors(state["engine"].new_case, game_id, username)


@app.post("/answer")
def post_answer(body: AnswerRequest, username: OptionalUser):
    return game_errors(state["engine"].answer, body.case_id, body.answer, username)


@app.get("/leaderboard")
def leaderboard(limit: int = Query(10, ge=1, le=50)):
    return state["engine"].leaderboard(limit)


# ----------------------------------------------------------------------
# Administration (champ is_admin = true dans la table users)
# ----------------------------------------------------------------------
@app.get("/admin/players")
def admin_players(_admin: AdminUser):
    return state["admin"].players()


@app.delete("/admin/players/{username}")
def admin_delete_player(username: str, admin: AdminUser):
    try:
        deleted = state["admin"].delete_player(username, admin)
    except admin_mod.Forbidden as err:
        raise HTTPException(status_code=403, detail=err.args[0]) from err
    if not deleted:
        raise HTTPException(status_code=404, detail="Joueur introuvable.")
    return {"deleted": username}


@app.get("/admin/scores")
def admin_scores(_admin: AdminUser):
    return state["admin"].scores()


@app.delete("/admin/scores/{game_id}")
def admin_delete_score(game_id: str, _admin: AdminUser):
    if not state["admin"].delete_score(game_id):
        raise HTTPException(status_code=404, detail="Score introuvable.")
    return {"deleted": game_id}


@app.post("/admin/scores/reset")
def admin_reset_scores(_admin: AdminUser):
    return {"deleted": state["admin"].reset_scores()}


@app.get("/admin/stats")
def admin_stats(_admin: AdminUser, min_shown: int = Query(1, ge=1)):
    return state["admin"].stats(min_shown)


@app.post("/admin/stats/reset")
def admin_reset_stats(_admin: AdminUser):
    return {"deleted": state["admin"].reset_stats()}
