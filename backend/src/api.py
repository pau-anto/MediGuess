"""API HTTP locale de MediGuess (FastAPI), conforme à docs/api-contract.md.

Lancer depuis la racine du repo :
    uvicorn backend.src.api:app --reload
Puis dans frontend/api.js : USE_MOCK = false et
API_BASE_URL = "http://127.0.0.1:8000".
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.src.game import GameEngine

state = {}


@asynccontextmanager
async def lifespan(_app):
    # Chargé une seule fois au démarrage : modèle + dataset (~20 s)
    state["engine"] = GameEngine()
    yield
    state.clear()


app = FastAPI(title="MediGuess API", lifespan=lifespan)

# En local, le front est ouvert en file:// (origine "null") : on autorise tout.
# À restreindre au domaine CloudFront en production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class AnswerRequest(BaseModel):
    case_id: str
    answer: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/case")
def get_case():
    return state["engine"].new_case()


@app.post("/answer")
def post_answer(request: AnswerRequest):
    try:
        return state["engine"].answer(request.case_id, request.answer)
    except KeyError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
