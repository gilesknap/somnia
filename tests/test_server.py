import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from anthropic import Anthropic
from starlette.testclient import TestClient

from conftest import ToneBook
from fakes import FakeEmbedder, RecordingAbs
from mp4 import duration_ms, payload
from somnia import server
from somnia.agent import OFFER_SENTENCE, Turn, open_library
from somnia.catalog import update_catalog
from somnia.config import Config
from somnia.db import connect
from somnia.queue import claim, finish
from somnia.tools import Library, Moved, Offer
from tone_book import CHAPTERS, GID, TOTAL_MS

TOKEN = "tab-1"


class FakeConversation:
    """Answers with its own turn count, so tests can tell conversations apart."""

    # Class-level, because `create_app` keeps its Conversations to itself and
    # there is no handle on the instance from outside. What is being proved is
    # that a value crossed the wire, and that is the same proof either way.
    seen_gids: list[int | None] = []

    def __init__(
        self, cfg: Config, library: Library, client: Anthropic | None = None
    ) -> None:
        self.turns: list[str] = []

    def ask(self, question: str, gid: int | None = None) -> Turn:
        self.turns.append(question)
        FakeConversation.seen_gids.append(gid)
        return Turn(reply=f"{len(self.turns)}: {question}")


class MovingConversation:
    """A turn that moves the book, without a model deciding to.

    It moves through the real tool layer rather than writing the row itself, so
    what the page is told comes from the same place a real move would put it.
    """

    def __init__(
        self, cfg: Config, library: Library, client: Anthropic | None = None
    ) -> None:
        self._library = library

    def ask(self, question: str, gid: int | None = None) -> Turn:
        moved = self._library.move_to(GID, 12_000)
        return Turn(reply="You're back at the fair.", move=moved)


class OfferingConversation:
    """A turn that asks which place they meant, without a model deciding to.

    The list is built through the real tool layer, so the body the page is
    handed is filled in by the same dataclasses a real turn fills in — there is
    exactly one definition of this shape and this is it going over the wire.

    ``places`` comes from the test because only it knows what the fixture book
    indexed. ``move`` is for the one case the tools already make impossible: a
    turn carrying both, which the serialiser has to refuse anyway.
    """

    places: list[int] = []
    move: Moved | None = None

    def __init__(
        self, cfg: Config, library: Library, client: Anthropic | None = None
    ) -> None:
        self._library = library

    def ask(self, question: str, gid: int | None = None) -> Turn:
        offer = self._library.offer_positions(GID, self.places)
        assert isinstance(offer, Offer), offer
        return Turn(reply=OFFER_SENTENCE, move=self.move, candidates=offer)


def chunks_at(tone_book: ToneBook, *starts: int) -> list[int]:
    """The ids of the passages beginning there, the way a search names them."""
    ids: list[int] = []
    for start_ms in starts:
        row = tone_book.conn.execute(
            "SELECT id FROM chunks WHERE book_gid = ? AND start_ms = ?", (GID, start_ms)
        ).fetchone()
        assert row is not None, f"no passage at {start_ms}"
        ids.append(int(row["id"]))
    return ids


def listening_at(tone_book: ToneBook, position_ms: int, heard_to_ms: int) -> None:
    """Put the listener somewhere, with a high-water mark behind them.

    The fixture book is heard end to end, which is the one state in which
    nothing on a list can be ahead of them.
    """
    with tone_book.conn:
        tone_book.conn.execute(
            "UPDATE books SET position_ms = ?, heard_to_ms = ? WHERE gid = ?",
            (position_ms, heard_to_ms, GID),
        )


def book_row(tone_book: ToneBook) -> dict[str, Any]:
    """Everything about the book a listener could tell had changed."""
    row = tone_book.conn.execute(
        "SELECT position_ms, position_seq, position_at, heard_to_ms FROM books"
        " WHERE gid = ?",
        (GID,),
    ).fetchone()
    return dict(row)


def no_warm_up(self: server.Conversations) -> None:
    """Startup's one slow step, stood down.

    It asks the API whether this model takes an effort level and builds the
    embedder — a live call and a torch import, neither of which belongs in a
    test suite. What it actually does has its own test below.
    """
    return None


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(server, "Conversation", FakeConversation)
    monkeypatch.setattr(server.Conversations, "warm", no_warm_up)
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
    monkeypatch.setattr(server.Conversations, "warm", no_warm_up)
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


def test_the_book_the_page_has_open_reaches_the_turn(client: TestClient) -> None:
    """Without this the agent could see the whole shelf and nothing saying
    which book was making the sound, so it asked "which book?" every turn.
    """
    FakeConversation.seen_gids.clear()
    ask_with(client, "where was I?", gid=271)
    assert FakeConversation.seen_gids == [271]


def test_a_page_that_sends_no_book_is_still_answered(client: TestClient) -> None:
    """Optional on purpose, and in two directions. A page that has opened
    nothing has questions worth asking, and a cached app.js from before this
    change must keep working rather than meet a 400 in the dark.

    Anything that is not a positive integer is no book at all: a gid that
    arrived as a string, a bool or a null is a page saying it does not know, and
    a guess would answer about a book nobody is listening to.
    """
    FakeConversation.seen_gids.clear()
    for sent in ({}, {"gid": None}, {"gid": "271"}, {"gid": True}, {"gid": 0}):
        status, _ = ask_with(client, "where was I?", **sent)
        assert status == 200
    assert FakeConversation.seen_gids == [None] * 5


def ask_with(client: TestClient, question: str, **rest: Any) -> Any:
    response = client.post(
        "/api/ask", json={"token": TOKEN, "question": question, **rest}
    )
    return response.status_code, response.json()


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


def test_the_page_is_asked_about_before_it_is_reused(client: TestClient) -> None:
    """A deploy has to be on the phone at the next launch, and without this it
    was not.

    Served with an ETag and no cache policy, the browser invents one: Chrome
    keeps a file for a tenth of its age, so a day-old ``app.js`` was good for
    another two hours and the page never asked. The units restart, the bytes on
    disk change, every request in the log is answered, and the phone runs last
    week's page — which reads as a deploy that silently did not happen.

    Every file in the shell, not just the ones that change often: the two that
    made this hard to see were ``app.js`` and ``style.css``, and the one anybody
    would have checked by hand is ``/``.
    """
    for path in ("/", "/app.js", "/style.css", "/sw.js", "/manifest.webmanifest"):
        page = client.get(path)
        assert page.status_code == 200, path
        assert page.headers["cache-control"] == "no-cache", path
        # And the ETag is still what answers the asking, so the cost of this is
        # a 304 and not the file again.
        again = client.get(path, headers={"if-none-match": page.headers["etag"]})
        assert again.status_code == 304, path
        assert again.headers["cache-control"] == "no-cache", path


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


def test_a_turn_that_asks_which_place_they_meant_sends_the_whole_list(
    tone_book: ToneBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The body is the contract, and it is asserted whole rather than sampled.

    Every field on a row is something the page draws or obeys, and the two that
    are not here matter as much as the six that are: a passage's surrounding
    context is three times as much of the book as the reveal was scoped to
    show, and its distance encodes a judgement that has already been made. A
    subset check would let either of them arrive unnoticed.

    Whether a row starts covered up is settled in the tool layer, against the
    Black Beauty fixture, which has a timeline long enough for "ahead" to mean
    something. What is settled here is that the answer arrives at the page
    saying so.
    """
    listening_at(tone_book, position_ms=8_000, heard_to_ms=12_000)
    monkeypatch.setattr(server, "Conversation", OfferingConversation)
    monkeypatch.setattr(
        OfferingConversation, "places", chunks_at(tone_book, 4_000, 12_000)
    )
    with TestClient(server.create_app(tone_book.cfg, tone_book.conn)) as client:
        status, body = ask(client, "the bit with the low tone")

    assert status == 200
    assert body == {
        "reply": "There are a few places that could be it.",
        "candidates": {
            "gid": GID,
            "title": "Three Tones",
            "position_ms": 8_000,
            "places": [
                {
                    "chunk_id": OfferingConversation.places[0],
                    "start_ms": 4_000,
                    "chapter_idx": 0,
                    "chapter_title": "The First Tone",
                    "ahead": False,
                    "text": "the low tone holds to the end of the first chapter",
                },
                {
                    "chunk_id": OfferingConversation.places[1],
                    "start_ms": 12_000,
                    "chapter_idx": 1,
                    "chapter_title": "The Second Tone",
                    "ahead": True,
                    # The words of the one they have not reached come down with
                    # the list, and the page keeps them off the screen until
                    # they ask. There is nothing to fetch them with later, and
                    # deliberately so — see the route test below.
                    "text": "the middle tone holds to the end of the second chapter",
                },
            ],
        },
    }


def test_a_list_and_a_seek_never_arrive_in_the_same_answer(
    tone_book: ToneBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The belt to the tool layer's braces, and this is the belt being tested.

    The tools refuse to move a book once a list exists in the turn, so a turn
    carrying both cannot be built by a model at all. If one ever were, the safe
    reading is that nothing has moved and they choose — a move that really
    happened comes back within fifteen seconds as the refusal of the page's
    next report, whereas a seek under somebody still reading a list is a
    listener dragged somewhere nobody chose.
    """
    listening_at(tone_book, position_ms=8_000, heard_to_ms=12_000)
    monkeypatch.setattr(server, "Conversation", OfferingConversation)
    monkeypatch.setattr(
        OfferingConversation, "places", chunks_at(tone_book, 4_000, 12_000)
    )
    monkeypatch.setattr(
        OfferingConversation, "move", Moved(GID, 20_000, 3, "Moved to 0:00:20.")
    )
    with TestClient(server.create_app(tone_book.cfg, tone_book.conn)) as client:
        status, body = ask(client, "the bit with the low tone")

    assert status == 200
    assert "candidates" in body
    assert "move" not in body


def test_asking_which_place_they_meant_writes_nothing_to_the_book(
    tone_book: ToneBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A turn that offers is a question, and a question leaves no mark.

    Not the position, not the count that would have the page's next report
    refused, and above all not ``heard_to_ms``: showing somebody a list of
    places they have not been is not having been there, and a guard that could
    be widened by asking about it would unwind one question at a time.
    """
    listening_at(tone_book, position_ms=8_000, heard_to_ms=12_000)
    monkeypatch.setattr(server, "Conversation", OfferingConversation)
    monkeypatch.setattr(
        OfferingConversation, "places", chunks_at(tone_book, 4_000, 12_000)
    )
    before = book_row(tone_book)
    with TestClient(server.create_app(tone_book.cfg, tone_book.conn)) as client:
        assert ask(client, "the bit with the low tone")[0] == 200
    assert book_row(tone_book) == before


def test_there_is_no_second_way_to_ask_what_is_at_a_place_they_have_not_heard(
    tone_book: ToneBook,
) -> None:
    """The words travel with the list because the alternative is an oracle.

    A route that answered "what does chunk 5233 say?" would be a permanent,
    general-purpose way to read unheard book text, one guessed integer wide,
    sitting on the server for the life of the deployment — and it would be
    asked over a tailnet at 2am on the one press where a spinner does the most
    damage, because they pressed it precisely when they were unsure.

    So every place on the list carries its own words down with the answer that
    named it, the reveal is a string in a closure reaching the DOM, and nothing
    anywhere hands out a passage by id.

    ``/api/passage`` is not that route and this is where the difference is
    written down. Its address is a point on the book's clock, not an identifier:
    there is no id to guess, the row it returns is bounded by ``heard_to_ms``
    inside the same statement that finds it — see
    :meth:`somnia.player.Player.passage_at` — and no way of asking makes it
    return anything the sound has not already said out loud. It exists for the
    one row on that screen the answer carries nothing for, which is the row that
    is by definition behind the mark: where they are now.
    """
    # Only the route table is under test, but the app is still started and
    # stopped properly, because create_app builds a Player that opens its own
    # connection and only the lifespan closes it. An app built and dropped
    # leaks that connection to the garbage collector, which raises
    # ResourceWarning from whichever unrelated test happens to be running when
    # the collection falls due — an error here, since warnings are errors, and
    # one that moves about between interpreter versions.
    app = server.create_app(tone_book.cfg, tone_book.conn)
    with TestClient(app):
        paths = [str(getattr(route, "path", "")) for route in app.routes]

    assert "/api/ask" in paths
    for path in paths:
        assert "chunk" not in path
        assert "reveal" not in path
        assert "candidate" not in path
    # And the one route that does serve the book's own words is addressed by a
    # time and nothing else. A path that took an id would be the oracle whatever
    # its handler did with it.
    text_routes = [path for path in paths if "passage" in path]
    assert text_routes == ["/api/passage/{gid:int}/{ms:int}"]


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


def test_the_manifest_also_names_the_whole_book_as_one_url(
    tone_client: TestClient,
) -> None:
    """The url the element loads once, and how much book it covers.

    Named by the number of chapters, so that a book which grows while somebody
    is listening is offered a *different* url rather than the same one holding
    different audio. ``stream_ms`` is what tells the end of the book from the
    end of what has been read of it: they are the same number here because this
    book is finished.
    """
    body = tone_client.get(f"/api/book/{GID}").json()
    assert body["stream_url"] == f"api/stream/{GID}/3"
    assert not body["stream_url"].startswith("/")
    assert body["stream_ms"] == 24_000
    # And the per-chapter urls are still there beside it. They are what a page
    # falls back to when there is no stream to be had, and keeping them costs
    # nothing but the string.
    assert len(body["chapters"]) == 3


def test_a_book_with_no_audio_yet_is_offered_a_chapter_at_a_time(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """No chapters is nothing to join, and saying so is not an error.

    A book added at eleven has rows before it has audio. Advertising a stream
    for one would be a url that answers 404 at the moment somebody is trying to
    open the book, which is worse than a page that knows to wait.
    """
    with tone_book.conn:
        tone_book.conn.execute("DELETE FROM chapters WHERE book_gid = ?", (GID,))
    body = tone_client.get(f"/api/book/{GID}").json()
    assert body["stream_url"] is None
    assert body["stream_ms"] == 0


def test_a_book_that_grew_is_offered_a_stream_it_did_not_have_before(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """The version moves with the book, and the old one is still a url.

    This is the whole of how a page listening to a book that is still being read
    finds out there is more: the manifest it polls names a longer stream. The
    file the phone has open is never the file that changed.
    """
    with tone_book.conn:
        tone_book.conn.execute(
            "DELETE FROM chapters WHERE book_gid = ? AND idx = 2", (GID,)
        )
    partway = tone_client.get(f"/api/book/{GID}").json()
    assert (partway["stream_url"], partway["stream_ms"]) == (
        f"api/stream/{GID}/2",
        16_000,
    )
    with tone_book.conn:
        tone_book.conn.execute(
            "INSERT INTO chapters (book_gid, idx, title, start_ms, end_ms,"
            " audio_file) VALUES (?, 2, 'The Third Tone', 16000, 24000, ?)",
            (GID, str(tone_book.book_dir / CHAPTERS[2].file_name)),
        )
    grown = tone_client.get(f"/api/book/{GID}").json()
    assert (grown["stream_url"], grown["stream_ms"]) == (
        f"api/stream/{GID}/3",
        24_000,
    )


# ------------------------------------------- the book as one file
#
# Everything below joins real audio, so it needs ffmpeg, and the suite has
# always been runnable without it (tests/tone_book.py). Skipping rather than
# failing keeps that true — at the price that a machine with no ffmpeg proves
# nothing about the stream, which is why the escaping rule these rest on is
# also pinned without ffmpeg, in tests/test_stream.py.
ffmpeg_only = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="joining chapters needs ffmpeg"
)


def stream_file(tone_book: ToneBook, n: int = len(CHAPTERS)) -> Path:
    """Where the stream covering the book's first ``n`` chapters is written."""
    return tone_book.cfg.data_dir / "streams" / str(GID) / f"{n}.m4a"


@ffmpeg_only
def test_the_whole_book_is_served_as_one_file_the_phone_will_play(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """One URL for the book, so a chapter boundary need touch nothing.

    Assigning ``src`` runs the media element load algorithm, which empties the
    element and takes the lock screen panel down with it. Over Bluetooth it
    sometimes never comes back, and the night ends there. A book the element
    loads once has no boundary to survive.

    The duration is what says the whole book is in there: join two of three and
    it reads sixteen seconds. It runs a shade over rather than exactly to the
    book because ``-c copy`` drops the edit list that trims AAC encoder priming,
    which leaves one frame of silence at the join — 42.667 ms, once, however
    many chapters are joined.
    """
    response = tone_client.get(f"/api/stream/{GID}/3")
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mp4"
    # A Content-Disposition would make the book a download instead.
    assert "content-disposition" not in response.headers
    assert response.content == stream_file(tone_book).read_bytes()
    assert TOTAL_MS <= duration_ms(stream_file(tone_book)) < TOTAL_MS + 100


@ffmpeg_only
def test_the_url_the_manifest_names_for_the_whole_book_really_serves_it(
    tone_client: TestClient,
) -> None:
    """The one road the page takes at boot, walked from the manifest end.

    The two halves are written a file apart — ``player.manifest`` builds the
    url out of a chapter count, the route takes one back apart — so nothing but
    following it proves they agree. A page given a url that 404s at 2am has a
    book it cannot open.
    """
    body = tone_client.get(f"/api/book/{GID}").json()
    assert tone_client.get(f"/{body['stream_url']}").status_code == 200


@ffmpeg_only
def test_the_stream_is_the_chapters_themselves_in_the_order_they_are_read(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """``-c copy`` re-wraps the audio; it must not re-encode or reorder it.

    The joined ``mdat`` is the chapters' own ``mdat``s laid end to end, byte for
    byte — measured that way across all forty-nine chapters of Black Beauty, and
    true here of three. It is worth asserting rather than assuming because it is
    what makes the render clock the manifest speaks a position in the stream:
    the page will seek by arithmetic on it, and a book joined out of order would
    land in the wrong chapter with nothing on the server to say it had.
    """
    assert tone_client.get(f"/api/stream/{GID}/3").status_code == 200
    laid_end_to_end = b"".join(
        payload(tone_book.book_dir / chapter.file_name, "mdat") for chapter in CHAPTERS
    )
    assert payload(stream_file(tone_book), "mdat") == laid_end_to_end


@ffmpeg_only
def test_the_stream_is_written_beside_the_database_and_not_in_the_library(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """ADR 3 promises the Audiobookshelf app keeps working on the same files.

    ``library_dir`` is ABS's own layout, and a second copy of every book
    appearing inside it would be somnia scanning as a library of doubles. The
    concatenation is somnia's own cache, so it lives with somnia's own data.
    """
    before = sorted(p.name for p in tone_book.book_dir.iterdir())
    assert tone_client.get(f"/api/stream/{GID}/3").status_code == 200

    assert stream_file(tone_book).is_file()
    assert sorted(p.name for p in tone_book.book_dir.iterdir()) == before
    in_library = {p.name for p in tone_book.cfg.library_dir.rglob("*.m4a")}
    assert in_library == {chapter.file_name for chapter in CHAPTERS}


@ffmpeg_only
def test_a_stream_can_be_fetched_a_piece_at_a_time(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """Seeking is ranged requests: without 206 the scrubber does nothing."""
    assert tone_client.get(f"/api/stream/{GID}/3").status_code == 200
    whole = stream_file(tone_book).read_bytes()
    response = tone_client.get(f"/api/stream/{GID}/3", headers={"Range": "bytes=0-99"})
    assert response.status_code == 206
    assert response.headers["content-range"] == f"bytes 0-99/{len(whole)}"
    assert response.content == whole[:100]


@ffmpeg_only
def test_the_end_of_a_stream_can_be_asked_for_on_its_own(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """A five-hour book is seeked into far more often than it is read whole."""
    assert tone_client.get(f"/api/stream/{GID}/3").status_code == 200
    whole = stream_file(tone_book).read_bytes()
    response = tone_client.get(f"/api/stream/{GID}/3", headers={"Range": "bytes=-64"})
    assert response.status_code == 206
    assert response.headers["content-range"] == (
        f"bytes {len(whole) - 64}-{len(whole) - 1}/{len(whole)}"
    )
    assert response.content == whole[-64:]


@ffmpeg_only
def test_an_unsatisfiable_range_into_a_stream_is_refused_rather_than_answered(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    assert tone_client.get(f"/api/stream/{GID}/3").status_code == 200
    size = stream_file(tone_book).stat().st_size
    response = tone_client.get(
        f"/api/stream/{GID}/3", headers={"Range": f"bytes={size + 10}-"}
    )
    assert response.status_code == 416
    assert response.headers["content-range"] == f"bytes */{size}"


@ffmpeg_only
def test_the_size_of_a_stream_is_known_without_fetching_it(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """A media element HEADs a file to learn its length before ranging it.

    The first thing the page ever asks for is this, so the HEAD has to build
    the stream rather than answer about one that is not there yet.
    """
    response = tone_client.head(f"/api/stream/{GID}/3")
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mp4"
    assert response.headers["content-length"] == str(
        stream_file(tone_book).stat().st_size
    )
    assert response.content == b""


@ffmpeg_only
def test_a_stream_is_built_once_and_never_rewritten_underneath_a_reader(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """The phone holds this file open for eight hours.

    Rebuilding it while a Range request is in flight splices new bytes against
    a header the element parsed twenty minutes ago, which is a corrupt read in
    the middle of a sentence. So a version is written once: the marker planted
    here comes back untouched, which it could not do if the second request had
    rebuilt anything.
    """
    assert tone_client.get(f"/api/stream/{GID}/3").status_code == 200
    stream_file(tone_book).write_bytes(b"a version that is already being read")

    again = tone_client.get(f"/api/stream/{GID}/3")
    assert again.content == b"a version that is already being read"


@ffmpeg_only
def test_a_book_that_grew_gets_a_new_stream_rather_than_a_rewritten_one(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """Which is what makes the version number a chapter count.

    A book is normally listened to while it is still rendering — nuc2 lands a
    chapter every three and a quarter minutes for the best part of three hours.
    Each new chapter makes a new version, and the one already loaded goes on
    existing, so nothing a phone is reading is ever the file being written.
    """
    assert tone_client.get(f"/api/stream/{GID}/2").status_code == 200
    assert duration_ms(stream_file(tone_book, 2)) < TOTAL_MS

    assert tone_client.get(f"/api/stream/{GID}/3").status_code == 200
    assert duration_ms(stream_file(tone_book, 3)) >= TOTAL_MS
    assert stream_file(tone_book, 2).is_file()


@ffmpeg_only
def test_a_chapter_whose_title_has_an_apostrophe_is_still_in_the_stream(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """``_safe_name`` keeps apostrophes, so the library really has these.

    ``008 - 08 Ginger's Story Continued.m4a`` is the file that found this. In a
    naively written concat list the line ends at the apostrophe; ffmpeg looks
    for ``008 - 08 Ginger``, says "Impossible to open", **exits 0**, and writes
    a book that stops there. Without this test that ships as a Black Beauty
    which goes quiet eight chapters in.
    """
    named = tone_book.book_dir / "002 - 08 Ginger's Story Continued.m4a"
    (tone_book.book_dir / CHAPTERS[1].file_name).rename(named)
    with tone_book.conn:
        tone_book.conn.execute(
            "UPDATE chapters SET audio_file = ? WHERE book_gid = ? AND idx = 1",
            (str(named), GID),
        )

    assert tone_client.get(f"/api/stream/{GID}/3").status_code == 200
    assert duration_ms(stream_file(tone_book)) >= TOTAL_MS


@ffmpeg_only
def test_a_chapter_that_will_not_open_stops_the_build_rather_than_the_book(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """The refusal to serve a short book, which is the only honest answer.

    ffmpeg's concat demuxer treats an input it cannot read as a reason to stop
    rather than a reason to fail: it exits 0 and leaves a file covering
    whatever it managed. Served, that is a book that plays eight seconds and
    ends — and ``ended`` is precisely what takes the lock screen panel down.
    Better a 404 the page can fall back from, loudly, into the journal.
    """
    (tone_book.book_dir / CHAPTERS[1].file_name).write_bytes(b"not audio" * 100)

    assert tone_client.get(f"/api/stream/{GID}/3").status_code == 404
    assert not stream_file(tone_book).exists()
    # And nothing half-written left behind to be picked up as a whole book.
    assert list(stream_file(tone_book).parent.glob("*")) == []


@ffmpeg_only
def test_a_stream_is_never_offered_for_audio_that_is_not_all_there(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """404s that are all the same answer: there is no such stream to serve.

    A version longer than the book is a page asking for chapters nobody has
    rendered; a version of nothing is a book with no audio at all; a missing
    file is a chapter the render never finished. None of them can be joined,
    and none of them is a traceback.
    """
    assert tone_client.get(f"/api/stream/{GID}/4").status_code == 404
    assert tone_client.get(f"/api/stream/{GID}/0").status_code == 404
    assert tone_client.get("/api/stream/404404/3").status_code == 404

    (tone_book.book_dir / CHAPTERS[2].file_name).unlink()
    assert tone_client.get(f"/api/stream/{GID}/3").status_code == 404


def test_a_book_still_being_read_says_so_and_grows_between_asks(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """The page fetches the manifest again while it says 'rendering'.

    Ingest writes a chapter row as each one finishes and bumps total_ms with it,
    which is what lets listening start on chapter one of forty-nine. Fetched
    once and never again, the page ends the night at whatever the book happened
    to be an instant after it opened — so ``status`` is not decoration, it is
    the page's only cue to ask again, and a second ask has to show the chapter
    that has landed since.
    """
    with tone_book.conn:
        tone_book.conn.execute(
            "UPDATE books SET status = 'rendering', total_ms = 16000 WHERE gid = ?",
            (GID,),
        )
        tone_book.conn.execute(
            "DELETE FROM chapters WHERE book_gid = ? AND idx = 2", (GID,)
        )
    rendering = tone_client.get(f"/api/book/{GID}").json()
    assert rendering["status"] == "rendering"
    assert (len(rendering["chapters"]), rendering["total_ms"]) == (2, 16_000)

    with tone_book.conn:
        tone_book.conn.execute(
            "INSERT INTO chapters (book_gid, idx, title, start_ms, end_ms,"
            " audio_file) VALUES (?, 2, 'The Third Tone', 16000, 24000, ?)",
            (GID, str(tone_book.book_dir / CHAPTERS[2].file_name)),
        )
        tone_book.conn.execute(
            "UPDATE books SET status = 'done', total_ms = 24000 WHERE gid = ?", (GID,)
        )
    done = tone_client.get(f"/api/book/{GID}").json()
    assert done["status"] == "done"
    assert [c["start_ms"] for c in done["chapters"]] == [0, 8_000, 16_000]
    assert done["total_ms"] == 24_000
    # And the chapter that arrived is really playable, which is the whole of
    # what the page does with it.
    assert tone_client.get(f"/{done['chapters'][2]['url']}").status_code == 200


def test_the_book_list_says_what_there_is_to_play(tone_client: TestClient) -> None:
    body = tone_client.get("/api/books").json()
    assert body["last_gid"] is None
    assert [(b["gid"], b["chapters"]) for b in body["books"]] == [(GID, len(CHAPTERS))]


# ------------------------------------------------------ where they have got to


def report(client: TestClient, **body: Any) -> Any:
    payload = {"token": TOKEN, "gid": GID, "seq": 0, "played_ms": 0, "reason": "tick"}
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


def test_a_report_that_says_nothing_about_playback_claims_none_of_it(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """A body with no playback in it is nothing played, never no limit.

    The mark is raised by what a report says has really come out of the speaker
    since the last one, so a page too old to send that number — or a body with
    a word where the number goes — has to be read as having played nothing.
    Read the other way round, the oldest page on the phone would be the one
    thing that could unlock the whole book.
    """
    with tone_book.conn:
        tone_book.conn.execute(
            "UPDATE books SET heard_to_ms = 4000 WHERE gid = ?", (GID,)
        )
    body = tone_client.post(
        "/api/position",
        json={"token": TOKEN, "gid": GID, "seq": 0, "position_ms": 20_000},
    ).json()
    assert (body["accepted"], body["heard_to_ms"]) == (True, 4_000)

    status, garbled = report(tone_client, position_ms=20_000, played_ms="all of it")
    assert (status, garbled["heard_to_ms"]) == (200, 4_000)


def test_stopping_tells_audiobookshelf_and_a_tick_does_not(
    tone_book: ToneBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ABS is right whenever someone next opens it, for a few writes a night.

    Telling it every fifteen seconds would be hundreds of requests to a server
    nothing is reading, on a link that may not be there.

    A switch is the book left behind when the agent takes them to another one.
    It counts as stopping because for that book it is: the parting report is the
    last thing the page will ever say about it, and if ABS does not hear it then
    nothing does.
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
        report(client, position_ms=4_000, reason="switch")
    assert recorder.moves == [
        ("abs-item-1", 2.0),
        ("abs-item-1", 3.0),
        ("abs-item-1", 4.0),
    ]


# ----------------------------------------------------------- switching books


def a_second_book(tone_book: ToneBook, gid: int, *, rendered: bool = True) -> None:
    """Another book to switch to, with or without a chapter of audio behind it."""
    with tone_book.conn:
        tone_book.conn.execute(
            "INSERT INTO books (gid, title, voice, status, total_ms)"
            " VALUES (?, 'The Other Book', 'af_heart', 'done', 8000)",
            (gid,),
        )
        if rendered:
            tone_book.conn.execute(
                "INSERT INTO chapters (book_gid, idx, title, start_ms, end_ms,"
                " audio_file) VALUES (?, 0, 'Its Only Chapter', 0, 8000, '')",
                (gid,),
            )


def added_first(tone_book: ToneBook, gid: int) -> None:
    """Make this the oldest book on the shelf, whatever order the test added them.

    ``created_at`` breaks a tie on ``position_at`` and is written in whole
    seconds like it is, so two books a test inserts carry the same one and an
    exact tie is decided by nothing anybody wrote down. Saying which is older
    aims the tie-break, so a test about the lead is answered only by the lead.
    """
    with tone_book.conn:
        tone_book.conn.execute(
            "UPDATE books SET created_at = '2000-01-01 00:00:00' WHERE gid = ?",
            (gid,),
        )


def test_the_page_can_choose_which_book_it_is_on(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """One POST, and a cold launch opens somewhere else from now on.

    This is the whole of switching books. The position it answers with is the
    book's own, from before the press — it is where the page is about to
    resume, not something this wrote.
    """
    a_second_book(tone_book, GID + 1)
    report(tone_client, position_ms=5_000)
    assert tone_client.get("/api/books").json()["last_gid"] == GID

    response = tone_client.post(f"/api/book/{GID + 1}/open")
    assert response.status_code == 200
    assert response.json() == {"gid": GID + 1, "position_ms": None, "seq": 0}
    assert tone_client.get("/api/books").json()["last_gid"] == GID + 1


def test_opening_a_book_changes_nothing_a_listener_could_notice(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """Everything about the row except which book is the most recent one.

    In particular not ``position_seq``, which counts agent moves and nothing
    else: a page that came away from this holding a stale count would have its
    next report refused, and the refusal would drag it to wherever the server
    thought the book was.
    """
    listening_at(tone_book, position_ms=11_000, heard_to_ms=9_000)
    before = book_row(tone_book)
    assert tone_client.post(f"/api/book/{GID}/open").status_code == 200
    after = book_row(tone_book)
    assert {k: v for k, v in after.items() if k != "position_at"} == {
        k: v for k, v in before.items() if k != "position_at"
    }
    # And the page carries on saying where it is as though nothing had
    # happened — which, as far as the report protocol goes, nothing has.
    status, body = report(tone_client, position_ms=11_500)
    assert (status, body["accepted"]) == (200, True)


def test_the_book_being_left_does_not_take_the_switch_back(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """The page's last word about the old book lands just after the switch.

    That is the real order of a press: open the new book, then say where the
    old one had got to. Both writes stamp ``position_at``, both are counted in
    whole seconds, and if the parting one won then a reload would open the book
    they had just left — which is the only way the whole feature can look
    broken while every request in it succeeded.

    The book being opened is made the older of the two, so ``created_at`` is on
    the side of the book being left. Otherwise both rows are added inside one
    second, the tie-break has nothing to say, and this passes with or without
    the lead it exists to protect.
    """
    a_second_book(tone_book, GID + 1)
    added_first(tone_book, GID + 1)
    report(tone_client, position_ms=5_000)
    assert tone_client.post(f"/api/book/{GID + 1}/open").status_code == 200

    status, body = report(tone_client, position_ms=5_500, reason="switch")
    assert (status, body["accepted"]) == (200, True)
    assert tone_client.get("/api/books").json()["last_gid"] == GID + 1


def test_a_book_there_is_nothing_to_play_of_cannot_be_opened(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """404 for a book that is not there, and for one still being read.

    Both are the same answer to a press — there is nothing to open — and the
    panel offers a press in neither state. The guard is on the server as well
    because a book with no audio made the most recent one would leave the next
    launch waiting on a render rather than on the book that was playing.
    """
    a_second_book(tone_book, GID + 1, rendered=False)
    report(tone_client, position_ms=5_000)
    assert tone_client.post(f"/api/book/{GID + 1}/open").status_code == 404
    assert tone_client.post("/api/book/404404/open").status_code == 404
    assert tone_client.get("/api/books").json()["last_gid"] == GID


def test_switching_books_is_a_post_and_a_get_does_not_do_it(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """The GET beside this one is the manifest, and it has to stay one.

    A switch a GET could make would be made by anything that fetches ahead of
    somebody, which on this page includes the service worker — the reason every
    route it uses sits under /api/ in the first place.
    """
    a_second_book(tone_book, GID + 1)
    report(tone_client, position_ms=5_000)
    assert tone_client.get(f"/api/book/{GID + 1}/open").status_code != 200
    assert tone_client.get("/api/books").json()["last_gid"] == GID


# ---------------------------------------------------- coming back to the book


def test_the_page_can_ask_where_the_sentence_it_stopped_in_began(
    tone_client: TestClient,
) -> None:
    """Asked at the pause, spent at the resume — see the handler for why."""
    body = tone_client.get(f"/api/sentence/{GID}/5000").json()
    assert body == {"gid": GID, "ms": 5_000, "start_ms": 4_000}


def test_a_book_with_no_sentence_to_offer_is_not_an_error(
    tone_client: TestClient,
) -> None:
    """The page can always resume without this. It is only ever an improvement."""
    response = tone_client.get(f"/api/sentence/{GID + 1}/5000")
    assert response.status_code == 200
    assert response.json()["start_ms"] is None


def test_the_page_can_ask_what_is_being_said_where_they_are(
    tone_client: TestClient,
) -> None:
    """The words for the "you are here" row, which no answer carries down."""
    body = tone_client.get(f"/api/passage/{GID}/5000").json()
    assert body == {
        "gid": GID,
        "ms": 5_000,
        "text": "the low tone holds to the end of the first chapter",
    }


def test_the_only_route_that_serves_book_text_cannot_serve_unheard_text(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """The one thing this route must never do, asked for directly.

    There is no chunk id in the address and no way to put one there: the address
    is a point on the clock, and what comes back is bounded by how far the sound
    has really got — so a caller naming the last millisecond of the book is
    answered from behind the mark like everybody else. See Player.passage_at.
    """
    with tone_book.conn:
        tone_book.conn.execute(
            "UPDATE books SET heard_to_ms = 12000 WHERE gid = ?", (GID,)
        )
    body = tone_client.get(f"/api/passage/{GID}/{TOTAL_MS}").json()
    assert body["text"] == "the second tone, a fifth above the first"


def test_a_book_with_nothing_to_say_where_they_are_is_not_an_error(
    tone_client: TestClient,
) -> None:
    """The row offers no reveal, and that is the whole of what happens."""
    response = tone_client.get(f"/api/passage/{GID + 1}/5000")
    assert response.status_code == 200
    assert response.json()["text"] is None


# ------------------------------------------------------------- adding a book

# Nine books that share a word, so the cap has something to cut, and two real
# ones so a refusal sentence reads as a book rather than as a number.
_ALSO_A_HORSE = '{gid},Text,2006-01-25,A Horse Story {gid},en,"Nobody",Horses,PZ,\n'
CATALOG_CSV = "".join(
    [
        "Text#,Type,Issued,Title,Language,Authors,Subjects,LoCC,Bookshelves\n",
        '271,Text,2006-01-25,Black Beauty,en,"Sewell, Anna",Horses,PZ,\n',
        "120,Text,2006-01-25,Treasure Island,en,"
        '"Stevenson, Robert Louis",Pirates,PZ,\n',
        *(_ALSO_A_HORSE.format(gid=9000 + n) for n in range(9)),
    ]
)


def catalogued(tone_book: ToneBook) -> None:
    """Fill the local catalog, which is the only thing a search ever reads."""
    update_catalog(tone_book.conn, csv_text=CATALOG_CSV)


def queue_items(client: TestClient) -> list[dict[str, Any]]:
    response = client.get("/api/queue")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return list(body["items"])


def add(client: TestClient, gid: Any) -> Any:
    response = client.post("/api/queue", json={"gid": gid})
    return response.status_code, response.json()


def test_the_catalog_can_be_searched_without_leaving_the_box(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """An FTS5 query against the local dump, not a round trip to Gutenberg.

    The search happens while somebody is standing there with a keyboard up, so
    it has to answer in the time a tap takes. Nothing here fetches anything.
    """
    catalogued(tone_book)
    body = tone_client.get("/api/catalog", params={"q": "black beauty"}).json()
    assert body["query"] == "black beauty"
    assert body["entries"][0] == {
        "gid": 271,
        "title": "Black Beauty",
        "authors": "Sewell, Anna",
        "have": None,
        "source": "gutenberg",
    }


def test_a_book_somnia_already_has_is_marked_rather_than_offered(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """So a duplicate press is never offered, rather than refused afterwards.

    Both halves of "already" are here, and they disagree on purpose. Black
    Beauty is a book with audio on disk and no queue row, which a check against
    the queue alone would miss. Treasure Island is a render that died — a
    ``books`` row on 'pending' — and has since been asked for again, so both
    tables have something to say about it and the live queue row is the true
    one: it is coming, whatever last week's row remembers.
    """
    catalogued(tone_book)
    with tone_book.conn:
        tone_book.conn.execute(
            "INSERT INTO books (gid, title, voice, status)"
            " VALUES (271, 'Black Beauty', 'af_heart', 'done')"
        )
        tone_book.conn.execute(
            "INSERT INTO books (gid, title, voice, status)"
            " VALUES (120, 'Treasure Island', 'af_heart', 'pending')"
        )
    assert add(tone_client, 120)[1]["ok"] is True

    # Two searches, because FTS5 puts an implicit AND between the terms and no
    # book is both of these.
    have = {}
    for query in ["black beauty", "treasure island"]:
        for entry in tone_client.get("/api/catalog", params={"q": query}).json()[
            "entries"
        ]:
            have[entry["gid"]] = entry["have"]
    assert have == {271: "done", 120: "queued"}


def test_a_search_full_of_punctuation_is_not_a_five_hundred(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """FTS5 has its own query syntax, and an apostrophe is not it."""
    catalogued(tone_book)
    for query in ["what's the horse's name?", "", "  ", '"', "a"]:
        response = tone_client.get("/api/catalog", params={"q": query})
        assert response.status_code == 200, query
        assert isinstance(response.json()["entries"], list)


def test_a_search_answers_with_what_fits_on_a_phone(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """Eight is what sits above a keyboard. A scroll here is a second screen."""
    catalogued(tone_book)
    body = tone_client.get("/api/catalog", params={"q": "horse"}).json()
    assert len(body["entries"]) == 8


def test_the_queue_says_what_is_rendering_and_what_is_waiting(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """The whole readout in one GET, asserted whole rather than sampled.

    Every field is something the page draws or obeys, so a field arriving or
    leaving unnoticed is a caption that quietly stops being true.
    """
    catalogued(tone_book)
    assert add(tone_client, 271)[1]["ok"] is True
    assert add(tone_client, 120)[1]["ok"] is True
    taken = claim(tone_book.conn, lease="a-lease", pid=1234)
    assert taken is not None

    items = queue_items(tone_client)
    assert [(i["gid"], i["state"], i["place"]) for i in items] == [
        (271, "rendering", 0),
        (120, "queued", 1),
    ]
    assert set(items[0]) == {
        "id",
        "gid",
        "title",
        "authors",
        "voice",
        "state",
        "place",
        "chapters_done",
        "chapters_total",
        "rendered_ms",
        "stopping",
        "responding",
        "error",
        "submitted_at",
        "started_at",
    }
    assert items[0]["title"] == "Black Beauty"
    assert (items[0]["stopping"], items[0]["responding"]) == (False, True)
    assert (items[0]["chapters_done"], items[0]["chapters_total"]) == (0, 0)


def test_the_page_and_the_voice_say_the_same_thing_about_adding_a_book(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """Byte-identical, because both sentences come out of the same function.

    The agent can be asked for a book and so can the panel, and the two must
    not be able to disagree about what just happened — least of all about a
    refusal, which is the answer somebody reads twice.
    """
    catalogued(tone_book)
    status, first = add(tone_client, 271)
    assert (status, first["ok"]) == (200, True)
    assert first["id"] > 0
    assert "Black Beauty" in first["said"]

    status, again = add(tone_client, 271)
    assert (status, again["ok"], again["id"]) == (200, False, 0)
    library = open_library(tone_book.cfg, tone_book.conn)
    assert again["said"] == library.add_book(271)
    # And the refusal really refused: one row, not two.
    assert len(queue_items(tone_client)) == 1


def test_a_refusal_is_answered_two_hundred_with_something_readable(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """Exactly the argument /api/position already makes for its own refusals.

    A 409 would put a red line in the console at 2am for something working
    exactly as designed, and invite a throw in the fetch wrapper that skipped
    the one line that mattered — which here is the sentence saying why.
    """
    catalogued(tone_book)
    with tone_book.conn:
        tone_book.conn.execute(
            "INSERT INTO books (gid, title, voice, status)"
            " VALUES (271, 'Black Beauty', 'af_heart', 'done')"
        )
    status, body = add(tone_client, 271)
    assert status == 200
    assert body["ok"] is False
    assert "already here" in body["said"]


def test_a_body_with_no_number_in_it_is_the_one_four_hundred(
    tone_client: TestClient,
) -> None:
    """There is nothing to submit, so there is nothing to say 200 about."""
    assert tone_client.post("/api/queue", json={}).status_code == 400
    assert add(tone_client, "treasure island")[0] == 400
    assert add(tone_client, -1)[0] == 400
    assert tone_client.post("/api/queue", content=b"not json").status_code == 400


def test_a_book_that_may_not_be_renderable_is_still_taken(
    tone_client: TestClient,
) -> None:
    """Because finding out costs a fetch and a parse, and that is minutes.

    A control that thinks for three seconds reads as broken, so an unknown gid
    is accepted here and fails later in the worker with a sentence.
    """
    status, body = add(tone_client, 999_999)
    assert (status, body["ok"]) == (200, True)
    assert "book 999999" in body["said"]


def test_a_book_can_be_taken_out_of_the_line_from_the_page(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    catalogued(tone_book)
    job_id = add(tone_client, 271)[1]["id"]
    body = tone_client.post(f"/api/queue/{job_id}/stop")
    assert body.status_code == 200
    assert body.json()["ok"] is True
    assert body.json()["state"] == "cancelled"
    assert "Black Beauty" in body.json()["said"]
    assert [(i["id"], i["state"]) for i in queue_items(tone_client)] == [
        (job_id, "cancelled")
    ]


def test_stopping_something_that_has_already_ended_is_an_answer_not_an_error(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """Too late is a sentence. No such job is a 404, which is a different fact.

    They are told apart because a caller does different things with them: one
    is a row on the screen whose button came a second too late, the other is a
    page holding an id from a database that has moved on.
    """
    catalogued(tone_book)
    job_id = add(tone_client, 271)[1]["id"]
    taken = claim(tone_book.conn, lease="a-lease", pid=1234)
    assert taken is not None
    finish(tone_book.conn, job_id, lease="a-lease", state="done")

    response = tone_client.post(f"/api/queue/{job_id}/stop")
    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert "nothing to stop" in response.json()["said"]

    missing = tone_client.post("/api/queue/404404/stop")
    assert missing.status_code == 404
    assert "said" in missing.json()


def test_what_died_yesterday_is_history_rather_than_news(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """The list empties itself, which is why nothing on it has to be dismissed."""
    catalogued(tone_book)
    job_id = add(tone_client, 271)[1]["id"]
    claim(tone_book.conn, lease="a-lease", pid=1234)
    finish(tone_book.conn, job_id, lease="a-lease", state="failed", error="No HTML.")
    assert [i["error"] for i in queue_items(tone_client)] == ["No HTML."]

    with tone_book.conn:
        tone_book.conn.execute(
            "UPDATE queue SET ended_at = datetime('now', '-25 hours') WHERE id = ?",
            (job_id,),
        )
    assert queue_items(tone_client) == []


def test_a_render_that_stopped_beating_is_shown_as_not_responding(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """Told from a slow one by the heartbeat, and by nothing else.

    Nobody writes this down: staleness is worked out when somebody looks, so
    the page says "not responding" honestly even when the worker unit has been
    stopped and there is nobody left to write anything at all.
    """
    catalogued(tone_book)
    add(tone_client, 271)
    claim(tone_book.conn, lease="a-lease", pid=1234)
    with tone_book.conn:
        tone_book.conn.execute(
            "UPDATE queue SET beat_at = datetime('now', '-6 minutes')"
        )
    item = queue_items(tone_client)[0]
    assert (item["state"], item["responding"]) == ("rendering", False)


def test_the_new_routes_are_under_api_like_everything_the_page_fetches(
    tone_book: ToneBook,
) -> None:
    """Not cosmetic: sw.js skips that prefix, and the mount swallows the rest.

    A queue route the service worker cached would draw last night's queue over
    tonight's, and a queue route behind the static mount would never be reached
    at all.
    """
    app = server.create_app(tone_book.cfg, tone_book.conn)
    with TestClient(app) as client:
        paths = [str(getattr(route, "path", "")) for route in app.routes]
        for path in paths:
            if "queue" in path or "catalog" in path:
                assert path.startswith("/api/"), path
        assert "/api/queue" in paths
        assert "/api/catalog" in paths
        # And the bare name really does fall through to the static mount, which
        # is what proves the prefix is doing the work rather than the ordering
        # happening to be lucky.
        fell_through = client.get("/queue")
        assert fell_through.status_code == 404
        assert "json" not in fell_through.headers.get("content-type", "")


def test_the_warm_up_asks_the_api_once_and_builds_the_embedder(
    tone_book: ToneBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one thing startup does, and nothing exercised it.

    Both fixtures above stub it out, which is right — a test suite must not make
    live API calls or load torch — but stubbing it everywhere left the method
    itself unrun. It does two slow things so that the first question of the
    night does not: asks whether this model takes an effort level, and builds
    the embedder. Both are observable, and neither was observed.
    """
    from somnia import tools
    from somnia.agent import forget_model_capabilities

    asked: list[str] = []
    built: list[str] = []

    class RecordingModels:
        @staticmethod
        def retrieve(model: str) -> Any:
            asked.append(model)
            # No dial, which is the shape Haiku answers with and the branch the
            # default configuration takes.
            return SimpleNamespace(capabilities=None)

    # Conversations builds its own client, so the class is what has to be stood
    # in for — which is also the assertion that no real one is ever made here.
    def fake_client(**kwargs: object) -> Anthropic:
        return cast(Anthropic, SimpleNamespace(models=RecordingModels()))

    class RecordingEmbedder(FakeEmbedder):
        """The embedder as `Library` builds it: from a model name, on demand."""

        def __init__(self, model: str) -> None:
            super().__init__()
            built.append(model)

    # In a finally, because a cached answer about one model outlives this test
    # and decides what every later one is told about it — which is what the
    # autouse fixture in test_agent.py exists for and this file has not got.
    forget_model_capabilities()
    try:
        monkeypatch.setattr(server, "Anthropic", fake_client)
        # No embedder handed in. Injecting one made the assertion below vacuous:
        # `library.embedder is not None` was already true before warm() ran, so
        # the half of this test about the slow half of the warm-up proved
        # nothing at all. `Library` builds it lazily from `cfg.embed_model`, so
        # standing that class in is what shows the build really happened here
        # rather than inside the night's first search.
        monkeypatch.setattr(tools, "Embedder", RecordingEmbedder)
        library = Library(tone_book.cfg, tone_book.conn)
        conversations = server.Conversations(tone_book.cfg, library)

        conversations.warm()

        assert asked == [tone_book.cfg.agent_model]
        # Built once, from the configured model — rather than waiting for the
        # first search, which on nuc2 is twelve seconds inside a turn.
        assert built == [tone_book.cfg.embed_model]
    finally:
        forget_model_capabilities()


def test_the_background_audio_spike_is_still_served(
    tone_client: TestClient,
) -> None:
    """It is reachable, and nothing said so.

    `spike-background-audio.html` is 900 lines of the experiment that decided
    how this page keeps sound going with the screen off, and it is served — by
    an implicit StaticFiles mount rather than by a route anybody wrote, which is
    the part worth pinning. It is kept because it is the only place the
    behaviour can be tried in isolation when the real page stops doing it; a
    file that had quietly stopped being served would be found out at exactly the
    wrong moment.
    """
    response = tone_client.get("/spike-background-audio.html")
    assert response.status_code == 200
    assert "audio" in response.text


def test_starting_the_server_starts_nothing_of_its_own(
    tone_book: ToneBook, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No thread, no child, and no torch — the renderer lives in another unit.

    The point of moving renders out of ``somnia serve`` is that a deploy's
    restart costs a render nothing and the page never waits behind Kokoro. It
    is also what keeps the forty-odd tests that build an app inside a
    ``TestClient`` as fast as they are, so it is worth catching here rather
    than in a stopwatch.
    """
    processes: list[Any] = []
    warmed: list[bool] = []

    def spawned(*args: Any, **kwargs: Any) -> None:
        processes.append(args)

    # The renderer's two shapes: a child process, and the model it would load.
    # `threading.Thread.start` used to be stubbed here as well, which is what
    # made the thread half of this test unable to fail — the assertion was that
    # nothing started, against a stub that made starting impossible. It is gone,
    # and what stands in its place is the one thread this app really does start:
    # the warm-up, recorded rather than run, so that the test says what it does
    # instead of pretending it does not happen.
    monkeypatch.setattr(subprocess, "Popen", spawned)

    def record_warm_up(self: server.Conversations) -> None:
        warmed.append(True)

    monkeypatch.setattr(server.Conversations, "warm", record_warm_up)
    monkeypatch.setattr(server, "Conversation", FakeConversation)

    # Through TestClient, which really runs the startup task — the lifespan
    # driven by hand went up and down before the threadpool had scheduled
    # anything, so nothing it started could have been observed either.
    with TestClient(server.create_app(tone_book.cfg, tone_book.conn)) as started:
        # One request, so the loop gets a turn and the startup task it created
        # actually runs. Without it the app goes up and down inside one tick and
        # cancels the warm-up before the threadpool has scheduled it — which is
        # true of the real server too, and is only ever a deploy restarting
        # inside a second.
        assert started.get("/api/health").status_code == 200

    assert processes == []
    assert warmed == [True]
    assert "torch" not in sys.modules


# ------------------------------------------------------------ choosing a voice


def test_the_page_is_told_which_voices_it_may_ask_for(tone_client: TestClient) -> None:
    """Served rather than written into app.js, so the two cannot come apart.

    A picker drawn from a list the route would refuse is a press that does
    nothing, which is the one failure this page is arranged to make impossible.
    """
    response = tone_client.get("/api/voices")
    assert response.status_code == 200
    voices = response.json()["voices"]
    assert {"id", "name", "says"} == set(voices[0])
    assert "af_heart" in [v["id"] for v in voices]


def test_a_book_can_be_asked_for_in_a_particular_voice(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    catalogued(tone_book)
    response = tone_client.post("/api/queue", json={"gid": 271, "voice": "bm_george"})
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert queue_items(tone_client)[0]["voice"] == "bm_george"


def test_a_voice_somnia_does_not_have_is_refused_before_six_hours_are_spent(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """The one thing this route checks that the queue does not.

    A name off the roster is a page left open across a release, or somebody
    with curl. Either way the honest answer is now, in a line, rather than a
    night of rendering in a voice nobody chose.
    """
    catalogued(tone_book)
    response = tone_client.post("/api/queue", json={"gid": 271, "voice": "af_nobody"})
    assert response.status_code == 400
    assert "af_nobody" in response.json()["error"]
    assert queue_items(tone_client) == []


def test_asking_for_no_voice_at_all_is_not_asking_for_a_wrong_one(
    tone_client: TestClient, tone_book: ToneBook
) -> None:
    """What the agent submits, and what every row written before this held."""
    catalogued(tone_book)
    assert add(tone_client, 271)[1]["ok"] is True
    assert queue_items(tone_client)[0]["voice"] == ""
