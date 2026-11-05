"""Tests des fonctions admin et du mode admin. Lancer : pytest backend"""

import pytest
from fastapi.testclient import TestClient

from backend.src import api

PASSWORD = "motdepasse"


@pytest.fixture(name="client")
def fixture_client(bank_path, monkeypatch):
    monkeypatch.setenv("CASE_BANK_PATH", str(bank_path))
    monkeypatch.setenv("JWT_SECRET", "secret-de-test")
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    with TestClient(api.app) as client:
        yield client


def account(client, username, admin=False):
    """Crée un compte ; admin=True simule le réglage manuel dans le portail."""
    token = client.post(
        "/auth/register", json={"username": username, "password": PASSWORD}
    ).json()["token"]
    if admin:
        store = api.state["accounts"].store
        user = store.get("users", username.lower())
        user["is_admin"] = True
        store.upsert("users", username.lower(), user)
    return {"Authorization": f"Bearer {token}"}


def correct_answer(case_id):
    engine = api.state["engine"]
    return engine.cases[engine.store.get("cases", case_id)["bank_index"]]["answer"]


def play_game(client, headers, admin_mode=False, wrong=True):
    """Joue une partie jusqu'au game over ; renvoie (partie, cas vus)."""
    body = {"admin_mode": True} if admin_mode else None
    response = client.post("/games", headers=headers, json=body)
    assert response.status_code == 201, response.json()
    game = response.json()
    seen = []
    for _ in range(50):
        case = client.get(
            "/case", params={"game_id": game["game_id"]}, headers=headers
        ).json()
        seen.append(case)
        answer = "mauvaise réponse" if wrong else correct_answer(case["case_id"])
        result = client.post(
            "/answer",
            json={"case_id": case["case_id"], "answer": answer},
            headers=headers,
        ).json()
        if result["game"]["game_over"]:
            break
    return game, seen


ADMIN_ROUTES = [
    ("get", "/admin/players"),
    ("get", "/admin/scores"),
    ("get", "/admin/stats"),
    ("post", "/admin/scores/reset"),
    ("delete", "/admin/players/x"),
]


@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
def test_admin_routes_are_protected(client, method, path):
    assert getattr(client, method)(path).status_code == 401
    player = account(client, "Joueur")
    assert getattr(client, method)(path, headers=player).status_code == 403


def test_profile_shows_admin_flag(client):
    assert (
        client.get("/me", headers=account(client, "Joueur")).json()["is_admin"] is False
    )
    assert client.get("/me", headers=account(client, "Chef", True)).json()["is_admin"]


def test_players_list_never_exposes_password(client):
    admin = account(client, "Chef", True)
    account(client, "Joueur")
    players = client.get("/admin/players", headers=admin).json()
    assert {p["username"] for p in players} == {"Chef", "Joueur"}
    assert all("password_hash" not in p and "salt" not in p for p in players)


def test_delete_player_removes_account_and_scores(client):
    admin = account(client, "Chef", True)
    player = account(client, "Joueur")
    play_game(client, player)
    assert client.get("/leaderboard").json()

    assert client.delete("/admin/players/joueur", headers=admin).status_code == 200
    assert client.get("/leaderboard").json() == []
    assert client.get("/me", headers=player).status_code == 401
    assert client.delete("/admin/players/Joueur", headers=admin).status_code == 404
    assert client.delete("/admin/players/Chef", headers=admin).status_code == 403


def test_delete_one_score_and_reset(client):
    admin = account(client, "Chef", True)
    player = account(client, "Joueur")
    play_game(client, player)
    play_game(client, player)
    scores = client.get("/admin/scores", headers=admin).json()
    assert len(scores) == 2

    url = f"/admin/scores/{scores[0]['game_id']}"
    assert client.delete(url, headers=admin).status_code == 200
    assert len(client.get("/admin/scores", headers=admin).json()) == 1
    assert client.post("/admin/scores/reset", headers=admin).json() == {"deleted": 1}
    assert client.get("/leaderboard").json() == []


def test_disease_stats_count_mistakes(client):
    admin = account(client, "Chef", True)
    _, seen = play_game(client, account(client, "Joueur"))
    stats = client.get("/admin/stats", headers=admin).json()
    assert stats["answers"] == len(seen) and stats["accuracy"] == 0
    worst = stats["diseases"][0]
    assert worst["error_rate"] == 1 and worst["top_confusion"] == "mauvaise réponse"

    assert client.post("/admin/stats/reset", headers=admin).json()["deleted"] >= 1
    assert client.get("/admin/stats", headers=admin).json()["answers"] == 0


def test_admin_mode_shows_answer_and_is_not_counted(client):
    admin = account(client, "Chef", True)
    game, seen = play_game(client, admin, admin_mode=True)
    assert game["admin_mode"]
    assert all(case["answer"] in case["choices"] for case in seen)

    assert client.get("/leaderboard").json() == []  # pas de classement
    stats = client.get("/admin/stats", headers=admin).json()
    assert stats["answers"] == 0 and stats["games"] == 0  # pas de statistiques
    assert client.get("/me", headers=admin).json()["games_played"] == 0


def test_normal_game_never_shows_answer(client):
    _, seen = play_game(client, account(client, "Chef", True))
    assert all("answer" not in case for case in seen)


def test_only_admins_can_use_admin_mode(client):
    for headers in ({}, account(client, "Joueur")):
        response = client.post("/games", headers=headers, json={"admin_mode": True})
        assert response.status_code == 403
