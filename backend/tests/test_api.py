"""Tests HTTP de l'API : comptes, parties, classement. Lancer : pytest backend"""

import pytest
from fastapi.testclient import TestClient

from backend.src import api
from backend.src.game import MAX_LIVES


@pytest.fixture(name="client")
def fixture_client(bank_path, monkeypatch):
    monkeypatch.setenv("CASE_BANK_PATH", str(bank_path))
    monkeypatch.setenv("JWT_SECRET", "secret-de-test")
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    with TestClient(api.app) as client:
        yield client


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def register(client, username="Nina", password="motdepasse"):
    response = client.post(
        "/auth/register", json={"username": username, "password": password}
    )
    return response


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_register_login_and_profile(client):
    response = register(client)
    assert response.status_code == 201
    token = response.json()["token"]
    assert client.get("/me", headers=auth(token)).json()["username"] == "Nina"

    # Pseudo déjà pris (insensible à la casse)
    assert register(client, "nina").status_code == 409

    login = client.post(
        "/auth/login", json={"username": "NINA", "password": "motdepasse"}
    )
    assert login.status_code == 200 and login.json()["username"] == "Nina"
    bad = client.post("/auth/login", json={"username": "Nina", "password": "mauvais!!"})
    assert bad.status_code == 401


@pytest.mark.parametrize(
    "username,password",
    [("ab", "motdepasse"), ("nom avec espace", "motdepasse"), ("Nina", "court")],
)
def test_register_validation(client, username, password):
    assert register(client, username, password).status_code == 422


def test_protected_routes(client):
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers=auth("faux.jeton.jwt")).status_code == 401


def play_until_game_over(client, headers):
    game = client.post("/games", headers=headers).json()
    result = None
    for _ in range(50):
        case = client.get("/case", params={"game_id": game["game_id"]}, headers=headers)
        body = {"case_id": case.json()["case_id"], "answer": "mauvaise réponse"}
        result = client.post("/answer", json=body, headers=headers).json()
        if result["game"]["game_over"]:
            break
    return game, result


def test_full_game_with_account(client):
    headers = auth(register(client).json()["token"])
    game, result = play_until_game_over(client, headers)
    assert result["game"]["lives"] == 0 and result["game"]["cases"] == MAX_LIVES
    assert (
        client.get("/case", params={"game_id": game["game_id"]}, headers=headers)
    ).status_code == 409

    board = client.get("/leaderboard").json()
    assert board[0]["username"] == "Nina" and board[0]["rank"] == 1
    assert len(client.get("/me/games", headers=headers).json()) == 1
    assert client.get("/me", headers=headers).json()["games_played"] == 1


def test_guest_game_is_not_ranked(client):
    game, result = play_until_game_over(client, {})
    assert game["username"] is None and result["game"]["game_over"]
    assert client.get("/leaderboard").json() == []


def test_other_player_cannot_use_my_game(client):
    mine = auth(register(client, "Nina").json()["token"])
    other = auth(register(client, "Pirate").json()["token"])
    game = client.post("/games", headers=mine).json()
    response = client.get("/case", params={"game_id": game["game_id"]}, headers=other)
    assert response.status_code == 403


def test_case_without_game_still_works(client):
    case = client.get("/case").json()
    body = {"case_id": case["case_id"], "answer": case["choices"][0]}
    result = client.post("/answer", json=body)
    assert result.status_code == 200 and "game" not in result.json()
    assert client.post("/answer", json=body).status_code == 404
