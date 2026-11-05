"""Tests de la banque de cas et du moteur de jeu (sans HTTP).
Lancer : pytest backend"""

import json

import pytest

from backend.src.auth import AccountService
from backend.src.game import (
    MAX_LIVES,
    Forbidden,
    GameEngine,
    GameFinished,
    NotFound,
    load_bank,
)
from backend.src.storage import MemoryStore
from backend.tests.conftest import N_CASES


@pytest.fixture(name="engine")
def fixture_engine(bank_path):
    store = MemoryStore()
    return GameEngine(
        load_bank(bank_path), store, AccountService(store, "test"), seed=1
    )


def answer_of(engine, case):
    """Bonne réponse d'un cas (lue côté serveur, jamais envoyée au front)."""
    index = engine.store.get("cases", case["case_id"])["bank_index"]
    return engine.cases[index]["answer"]


def wrong_of(engine, case):
    good = answer_of(engine, case)
    return next(c for c in case["choices"] if c != good)


def test_bank_cases_are_playable(bank_path):
    with open(bank_path, encoding="utf-8") as f:
        cases = json.load(f)["cases"]
    assert len(cases) == N_CASES
    for case in cases:
        assert len(case["choices"]) == 4
        assert case["answer"] in case["choices"]
        assert len(case["symptoms"]) >= 2
        assert case["answer"] not in case["symptoms"]  # pas de réponse visible
        assert len(case["explanation"]["factors"]) <= 3


def test_case_format_and_no_answer_leak(engine):
    case = engine.new_case()
    assert set(case) == {"case_id", "symptoms", "choices"}
    assert answer_of(engine, case) in case["choices"]


def test_case_can_only_be_played_once(engine):
    case = engine.new_case()
    engine.answer(case["case_id"], case["choices"][0])
    with pytest.raises(NotFound):
        engine.answer(case["case_id"], case["choices"][0])


def test_score_and_lives_are_kept_by_the_server(engine):
    game = engine.start_game()
    case = engine.new_case(game["game_id"])
    result = engine.answer(case["case_id"], answer_of(engine, case))
    assert result["correct"]
    assert result["game"]["score"] == result["points"] > 0
    assert result["game"]["lives"] == MAX_LIVES

    case = engine.new_case(game["game_id"])
    result = engine.answer(case["case_id"], wrong_of(engine, case))
    assert result["game"]["lives"] == MAX_LIVES - 1


def lose_game(engine, game_id, username=None):
    result = None
    for _ in range(MAX_LIVES):
        case = engine.new_case(game_id, username)
        result = engine.answer(case["case_id"], wrong_of(engine, case), username)
    return result


def test_game_over_after_three_mistakes(engine):
    game = engine.start_game()
    result = lose_game(engine, game["game_id"])
    assert result["game"]["game_over"] and result["game"]["lives"] == 0
    with pytest.raises(GameFinished):
        engine.new_case(game["game_id"])


def test_guest_score_is_not_ranked(engine):
    lose_game(engine, engine.start_game()["game_id"])
    assert not engine.leaderboard()


def test_player_score_is_ranked_and_saved(engine):
    engine.accounts.register("Nina", "motdepasse")
    game = engine.start_game("Nina")
    case = engine.new_case(game["game_id"], "Nina")
    engine.answer(case["case_id"], answer_of(engine, case), "Nina")
    lose_game(engine, game["game_id"], "Nina")

    board = engine.leaderboard()
    assert board[0]["username"] == "Nina" and board[0]["score"] > 0
    assert engine.history("Nina")[0]["cases"] == MAX_LIVES + 1
    profile = engine.accounts.profile("nina")
    assert profile["games_played"] == 1 and profile["best_score"] == board[0]["score"]


def test_leaderboard_keeps_best_score_per_player(engine):
    for name, score in [("a", 10), ("a", 30), ("b", 20)]:
        engine.store.insert(
            "scores",
            f"{name}{score}",
            {"username": name, "score": score, "cases": 1, "correct": 1,
             "finished_at": "2026-11-05T00:00:00+00:00"},
        )  # fmt: skip
    assert [(r["username"], r["score"]) for r in engine.leaderboard()] == [
        ("a", 30),
        ("b", 20),
    ]


def test_cannot_play_someone_elses_game(engine):
    game = engine.start_game("Nina")
    with pytest.raises(Forbidden):
        engine.new_case(game["game_id"], "Pirate")
