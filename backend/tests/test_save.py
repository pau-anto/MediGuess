"""Sauvegarde / reprise / arrêt d'une partie. Lancer : pytest backend"""

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


def login(client, username="Nina"):
    token = client.post(
        "/auth/register", json={"username": username, "password": "motdepasse"}
    ).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def good_answer(case_id):
    engine = api.state["engine"]
    return engine.cases[engine.store.get("cases", case_id)["bank_index"]]["answer"]


def test_quit_and_resume_keeps_score_and_same_case(client):
    headers = login(client)
    game = client.post("/games", headers=headers).json()
    params = {"game_id": game["game_id"]}

    case = client.get("/case", params=params, headers=headers).json()
    body = {"case_id": case["case_id"], "answer": good_answer(case["case_id"])}
    client.post("/answer", json=body, headers=headers)
    pending = client.get("/case", params=params, headers=headers).json()

    # Le joueur quitte puis revient (autre appareil : il ne connaît que son compte)
    saved = client.get("/games/current", headers=headers).json()
    assert saved["game_id"] == game["game_id"] and saved["score"] == 10
    assert not saved["game_over"] and saved["cases"] == 1

    # Le cas non répondu revient à l'identique : impossible de le « passer »
    again = client.get("/case", params=params, headers=headers).json()
    assert again == pending


def test_guest_can_resume_with_game_id(client):
    game = client.post("/games").json()
    resumed = client.get(f"/games/{game['game_id']}").json()
    assert resumed["lives"] == MAX_LIVES and resumed["username"] is None


def test_finish_now_records_score(client):
    headers = login(client)
    game = client.post("/games", headers=headers).json()
    case = client.get(
        "/case", params={"game_id": game["game_id"]}, headers=headers
    ).json()
    body = {"case_id": case["case_id"], "answer": good_answer(case["case_id"])}
    client.post("/answer", json=body, headers=headers)
    client.get("/case", params={"game_id": game["game_id"]}, headers=headers)

    finished = client.post(f"/games/{game['game_id']}/finish", headers=headers).json()
    assert finished["game_over"] and finished["score"] == 10
    assert client.get("/leaderboard").json()[0]["score"] == 10
    assert client.get("/games/current", headers=headers).status_code == 404
    # le cas en attente est supprimé avec la partie
    assert not api.state["engine"].store.query("cases", game_id=game["game_id"])


def answer_one(client, headers, game_id):
    case = client.get("/case", params={"game_id": game_id}, headers=headers).json()
    body = {"case_id": case["case_id"], "answer": good_answer(case["case_id"])}
    client.post("/answer", json=body, headers=headers)


def test_new_game_closes_the_saved_one(client):
    headers = login(client)
    first = client.post("/games", headers=headers).json()
    answer_one(client, headers, first["game_id"])
    second = client.post("/games", headers=headers).json()
    answer_one(client, headers, second["game_id"])
    assert client.get(f"/games/{first['game_id']}", headers=headers).json()["game_over"]
    assert client.get("/games/current", headers=headers).json()["game_id"] == (
        second["game_id"]
    )
    # l'ancienne partie (1 bonne réponse) est entrée au classement
    assert client.get("/leaderboard").json()[0]["score"] == 10


def test_game_without_answer_is_not_a_save(client):
    headers = login(client)
    game = client.post("/games", headers=headers).json()
    client.get("/case", params={"game_id": game["game_id"]}, headers=headers)
    # quitte avant de répondre : rien à reprendre
    assert client.get("/games/current", headers=headers).status_code == 404
    # et une nouvelle partie ne met pas de 0 au classement
    client.post("/games", headers=headers)
    assert client.get("/leaderboard").json() == []


def test_cannot_resume_someone_elses_game(client):
    game = client.post("/games", headers=login(client, "Nina")).json()
    other = login(client, "Pirate")
    assert client.get(f"/games/{game['game_id']}", headers=other).status_code == 403
    url = f"/games/{game['game_id']}/finish"
    assert client.post(url, headers=other).status_code == 403


def test_new_accounts_have_visible_admin_flag(client):
    login(client, "Nina")
    user = api.state["accounts"].store.get("users", "nina")
    assert user["is_admin"] is False


@pytest.mark.parametrize("value", [True, "true", "True", "1"])
def test_admin_flag_typed_by_hand_is_accepted(client, value):
    headers = login(client, "Chef")
    store = api.state["accounts"].store
    user = store.get("users", "chef")
    user["is_admin"] = value
    store.upsert("users", "chef", user)
    assert client.get("/me", headers=headers).json()["is_admin"] is True
