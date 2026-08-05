from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from conftest import ToneBook
from somnia import server
from somnia.config import Config
from somnia.db import connect
from somnia.tools import Library
from tone_book import CHAPTERS, GID

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
        # As a context manager, so shutdown runs and the player gives its own
        # connection back.
        with TestClient(server.create_app(cfg, conn)) as started:
            yield started
    finally:
        # An unclosed connection surfaces as a ResourceWarning whenever the
        # garbage collector gets to it, which pytest raises as an error in
        # whichever test happened to be running at the time.
        conn.close()


@pytest.fixture
def tone_client(
    tone_book: ToneBook, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    """A server with a book that is really audio behind it."""
    monkeypatch.setattr(server, "Conversation", FakeConversation)
    with TestClient(server.create_app(tone_book.cfg, tone_book.conn)) as client:
        yield client


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


# ------------------------------------------------------------- the player


def chapter_bytes(tone_book: ToneBook, idx: int) -> bytes:
    return (tone_book.book_dir / CHAPTERS[idx].file_name).read_bytes()


def test_a_chapter_is_served_as_audio_the_phone_will_play(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """An unpinned media type is octet-stream, which Safari will not play."""
    response = tone_client.get(f"/api/audio/{GID}/0")
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mp4"
    # A Content-Disposition would make the book a download instead.
    assert "content-disposition" not in response.headers
    assert response.content == chapter_bytes(tone_book, 0)


def test_a_chapter_can_be_fetched_a_piece_at_a_time(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """Seeking is ranged requests: without 206 the scrubber does nothing."""
    whole = chapter_bytes(tone_book, 0)
    response = tone_client.get(f"/api/audio/{GID}/0", headers={"Range": "bytes=0-99"})
    assert response.status_code == 206
    assert response.headers["content-range"] == f"bytes 0-99/{len(whole)}"
    assert response.content == whole[:100]


def test_the_end_of_a_chapter_can_be_asked_for_on_its_own(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """A player reads the trailing index of an m4a before it plays a note."""
    whole = chapter_bytes(tone_book, 1)
    response = tone_client.get(f"/api/audio/{GID}/1", headers={"Range": "bytes=-64"})
    assert response.status_code == 206
    assert response.headers["content-range"] == (
        f"bytes {len(whole) - 64}-{len(whole) - 1}/{len(whole)}"
    )
    assert response.content == whole[-64:]


def test_an_unsatisfiable_range_is_refused_rather_than_answered(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    size = len(chapter_bytes(tone_book, 0))
    response = tone_client.get(
        f"/api/audio/{GID}/0", headers={"Range": f"bytes={size + 10}-"}
    )
    assert response.status_code == 416
    assert response.headers["content-range"] == f"bytes */{size}"


def test_the_size_of_a_chapter_is_known_without_fetching_it(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """A media element HEADs a file to learn its length before ranging it."""
    response = tone_client.head(f"/api/audio/{GID}/2")
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mp4"
    assert response.headers["content-length"] == str(len(chapter_bytes(tone_book, 2)))
    assert response.content == b""


def test_a_chapter_whose_name_has_spaces_is_still_reachable(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """Chapters are addressed by number, so no name ever has to be encoded."""
    assert " " in CHAPTERS[1].file_name
    response = tone_client.get(f"/api/audio/{GID}/1")
    assert response.status_code == 200
    assert response.content == chapter_bytes(tone_book, 1)


def test_a_chapter_that_is_not_there_is_a_404_not_a_traceback(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    assert tone_client.get(f"/api/audio/{GID}/99").status_code == 404
    (tone_book.book_dir / CHAPTERS[2].file_name).unlink()
    assert tone_client.get(f"/api/audio/{GID}/2").status_code == 404


def test_a_book_that_is_not_there_is_a_404(tone_client: TestClient) -> None:
    assert tone_client.get("/api/audio/404404/0").status_code == 404
    manifest = tone_client.get("/api/book/404404")
    assert manifest.status_code == 404
    assert "error" in manifest.json()


def test_no_request_can_name_a_file_of_its_own(
    tone_client: TestClient, tone_book: ToneBook, tmp_path: Path
) -> None:
    """There is no auth here by design, so the audio route must not read paths.

    A chapter is named by two integers and the path comes from the row, which
    is the whole defence. The row is checked too: a library that has moved, or
    a symlink out of it, resolves outside and is refused.
    """
    assert tone_client.get(f"/api/audio/{GID}/../../etc/passwd").status_code == 404

    outside = tmp_path / "secrets.m4a"
    outside.write_bytes(b"not yours")
    with tone_book.conn:
        tone_book.conn.execute(
            "UPDATE chapters SET audio_file = ? WHERE book_gid = ? AND idx = 0",
            (str(outside), GID),
        )
    assert tone_client.get(f"/api/audio/{GID}/0").status_code == 404


def test_the_manifest_gives_the_page_a_url_for_every_chapter(
    tone_client: TestClient,
) -> None:
    """The manifest is the page's only map, so every road on it must lead somewhere."""
    body = tone_client.get(f"/api/book/{GID}").json()
    assert body["gid"] == GID
    assert body["total_ms"] == 24_000
    assert body["position_ms"] is None
    assert [c["start_ms"] for c in body["chapters"]] == [0, 8_000, 16_000]
    for chapter in body["chapters"]:
        # Relative, because the app may be mounted under a path.
        assert not chapter["url"].startswith("/")
        assert tone_client.get(f"/{chapter['url']}").status_code == 200


def test_the_book_list_says_what_there_is_to_play(tone_client: TestClient) -> None:
    body = tone_client.get("/api/books").json()
    assert body["last_gid"] is None
    assert [(b["gid"], b["chapters"]) for b in body["books"]] == [(GID, len(CHAPTERS))]
