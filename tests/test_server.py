from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from conftest import ToneBook
from fakes import RecordingAbs
from somnia import server
from somnia.agent import Turn
from somnia.config import Config
from somnia.db import connect
from somnia.tools import Library
from tone_book import CHAPTERS, GID

TOKEN = "tab-1"


class FakeConversation:
    """Answers with its own turn count, so tests can tell conversations apart."""

    def __init__(self, cfg: Config, library: Library) -> None:
        self.turns: list[str] = []

    def ask(self, question: str) -> Turn:
        self.turns.append(question)
        return Turn(reply=f"{len(self.turns)}: {question}")


class MovingConversation:
    """A turn that moves the book, without a model deciding to.

    It moves through the real tool layer rather than writing the row itself, so
    what the page is told comes from the same place a real move would put it.
    """

    def __init__(self, cfg: Config, library: Library) -> None:
        self._library = library

    def ask(self, question: str) -> Turn:
        moved = self._library.move_to(GID, 12_000)
        return Turn(reply="You're back at the fair.", move=moved)


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


def test_a_turn_that_moved_the_book_tells_the_page_where_to_go(
    tone_book: ToneBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The head start. Without it the page waits for its next report to be
    refused, which is up to fifteen seconds of nothing happening after being
    told it had.

    The count travels with the position because a page that took one without the
    other would have its very next report refused, and the refusal would drag it
    back here after it had already played on.
    """
    monkeypatch.setattr(server, "Conversation", MovingConversation)
    with TestClient(server.create_app(tone_book.cfg, tone_book.conn)) as client:
        status, body = ask(client, "take me back to the fair")

    assert status == 200
    assert body == {
        "reply": "You're back at the fair.",
        "move": {"gid": GID, "position_ms": 12_000, "seq": 1},
    }


def test_a_turn_that_moved_nothing_says_nothing_about_moving(
    client: TestClient,
) -> None:
    """The page reads the key's presence, so an empty one would be a move."""
    status, body = ask(client, "how far am I?")
    assert (status, body) == (200, {"reply": "1: how far am I?"})


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


# ------------------------------------------------------ where they have got to


def report(client: TestClient, **body: Any) -> Any:
    payload = {"token": TOKEN, "gid": GID, "seq": 0, "playing": True, "reason": "tick"}
    payload.update(body)
    response = client.post("/api/position", json=payload)
    return response.status_code, response.json()


def test_the_page_can_say_where_it_has_got_to(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    status, body = report(tone_client, position_ms=12_500)
    assert (status, body["accepted"], body["position_ms"]) == (200, True, 12_500)
    assert tone_client.get(f"/api/book/{GID}").json()["position_ms"] == 12_500


def test_a_position_report_is_answered_two_hundred_even_when_refused(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """A refusal is the protocol working, not an error.

    A 409 would put a red line in the console at 2am for something behaving
    exactly as designed, invite a throw in the fetch wrapper that skipped the
    one line that mattered, and be unreadable to a beacon, which is how the
    last position of the night is sent.
    """
    with tone_book.conn:
        tone_book.conn.execute(
            "UPDATE books SET position_seq = 4, position_ms = 20000 WHERE gid = ?",
            (GID,),
        )
    status, body = report(tone_client, position_ms=1_000, seq=0)
    assert status == 200
    assert body == {
        "accepted": False,
        "gid": GID,
        "position_ms": 20_000,
        "seq": 4,
        "heard_to_ms": 24_000,
        "reason": "moved",
    }


def test_a_report_about_a_book_that_is_gone_is_not_an_error_either(
    tone_client: TestClient,
) -> None:
    status, body = report(tone_client, gid=404_404, position_ms=1_000)
    assert status == 200
    assert body == {"accepted": False, "gid": 404_404, "reason": "gone"}


def test_a_report_with_nothing_in_it_is_refused_outright(
    tone_client: TestClient,
) -> None:
    """The one case worth a 400: there is nothing here to write."""
    assert tone_client.post("/api/position", json={"token": TOKEN}).status_code == 400
    assert (
        tone_client.post(
            "/api/position", json={"gid": GID, "position_ms": "somewhere"}
        ).status_code
        == 400
    )


def test_a_report_of_an_unknown_kind_is_taken_as_a_tick(
    tone_client: TestClient,
) -> None:
    """A garbled 2am request is not news, and dropping the position would be."""
    status, body = report(tone_client, position_ms=3_000, reason="sleepwalking")
    assert (status, body["accepted"]) == (200, True)


def test_stopping_tells_audiobookshelf_and_a_tick_does_not(
    tone_book: ToneBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ABS is right whenever someone next opens it, for a few writes a night.

    Telling it every fifteen seconds would be hundreds of requests to a server
    nothing is reading, on a link that may not be there.
    """
    recorder = RecordingAbs()

    def one_abs_client(base_url: str, token: str) -> RecordingAbs:
        """create_app builds its own, so this is how a test gets a look at it."""
        return recorder

    monkeypatch.setattr(server, "Conversation", FakeConversation)
    monkeypatch.setattr(server, "AbsClient", one_abs_client)
    tone_book.cfg.abs_token = "a-token"
    with tone_book.conn:
        tone_book.conn.execute(
            "UPDATE books SET abs_item_id = 'abs-item-1' WHERE gid = ?", (GID,)
        )

    with TestClient(server.create_app(tone_book.cfg, tone_book.conn)) as client:
        report(client, position_ms=1_000, reason="tick")
        assert recorder.moves == []
        report(client, position_ms=2_000, reason="pause")
        report(client, position_ms=3_000, reason="unload")
    assert recorder.moves == [("abs-item-1", 2.0), ("abs-item-1", 3.0)]
