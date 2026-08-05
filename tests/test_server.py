from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from somnia import server
from somnia.config import Config
from somnia.db import connect
from somnia.tools import Library

TOKEN = "tab-1"


class FakeConversation:
    """Answers with its own turn count, so tests can tell conversations apart."""

    def __init__(self, cfg: Config, library: Library) -> None:
        self.turns: list[str] = []

    def ask(self, question: str) -> str:
        self.turns.append(question)
        return f"{len(self.turns)}: {question}"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(server, "Conversation", FakeConversation)
    cfg = Config(data_dir=tmp_path)
    conn = connect(cfg.db_path, cross_thread=True)
    try:
        yield TestClient(server.create_app(cfg, conn))
    finally:
        # An unclosed connection surfaces as a ResourceWarning whenever the
        # garbage collector gets to it, which pytest raises as an error in
        # whichever test happened to be running at the time.
        conn.close()


def ask(client: TestClient, question: str, token: str = TOKEN) -> Any:
    response = client.post("/api/ask", json={"token": token, "question": question})
    return response.status_code, response.json()


def test_the_same_page_keeps_talking_to_the_same_conversation(
    client: TestClient,
) -> None:
    assert ask(client, "what am I part-way through?") == (
        200,
        {"reply": "1: what am I part-way through?"},
    )
    status, body = ask(client, "the horse one")
    assert (status, body) == (200, {"reply": "2: the horse one"})


def test_a_second_page_gets_its_own_conversation(client: TestClient) -> None:
    ask(client, "first")
    status, body = ask(client, "second", token="tab-2")
    assert (status, body) == (200, {"reply": "1: second"})


def test_starting_over_forgets_what_was_said(client: TestClient) -> None:
    ask(client, "first")
    assert client.post("/api/forget", json={"token": TOKEN}).status_code == 200
    status, body = ask(client, "again")
    assert (status, body) == (200, {"reply": "1: again"})


def test_a_blank_question_is_not_put_to_the_agent(client: TestClient) -> None:
    status, body = ask(client, "   ")
    assert status == 400
    assert "error" in body


def test_a_failed_turn_answers_instead_of_hanging(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Half asleep, an unanswered request is indistinguishable from a broken app."""

    def explode(self: FakeConversation, question: str) -> str:
        raise RuntimeError("the API is down")

    monkeypatch.setattr(FakeConversation, "ask", explode)
    status, body = ask(client, "where am I?")
    assert status == 500
    assert "error" in body


def test_the_chat_page_is_served_from_the_package(client: TestClient) -> None:
    """The PWA ships inside the wheel; a missing web/ would only show up here."""
    page = client.get("/")
    assert page.status_code == 200
    assert "somnia" in page.text
    assert client.get("/manifest.webmanifest").status_code == 200
    assert client.get("/sw.js").status_code == 200


def test_old_conversations_are_dropped_rather_than_kept_for_ever(
    client: TestClient,
) -> None:
    ask(client, "first", token="oldest")
    for n in range(server.MAX_CONVERSATIONS):
        ask(client, "hello", token=f"tab-{n}")
    status, body = ask(client, "still there?", token="oldest")
    assert (status, body) == (200, {"reply": "1: still there?"})
