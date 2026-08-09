"""The 2am conversation: an Anthropic tool runner over :mod:`somnia.tools`.

The model's job is routing, disambiguation and phrasing, not retrieval — the
tools do the work. What it may say used to be bounded by what a tool had handed
it in this conversation; since ADR 6 it is bounded by how far the listener has
listened instead, which is a line the tools compute and tell it about rather
than one it has to remember. Which model answers is :mod:`somnia.config`'s to
say — it has the measurements that chose the one it names — together with the
two settings that decide how long a turn takes.

Everything sent here is shaped around one number: a question asked in the dark
is answered in a handful of seconds, and every one of them is felt. So the
constant half of the prompt is cached rather than re-read on each hop, and the
model is told how hard to think rather than left to decide.
"""

import logging
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from anthropic import Anthropic, Omit, beta_tool, omit
from anthropic.types.beta import BetaOutputConfigParam, BetaTextBlockParam

from .abs import AbsClient
from .config import Config
from .queue import QueueRow
from .tools import Library, Moved, Offer, Refused, format_timestamp

__all__ = [
    "OFFER_SENTENCE",
    "SYSTEM_PROMPT",
    "Conversation",
    "Turn",
    "build_tools",
    "effort_for",
    "forget_model_capabilities",
    "open_library",
]

logger = logging.getLogger(__name__)

# Whether (model, level) will be accepted, asked of the API once each and
# remembered for the life of the process. Both halves of the key matter: a
# model can have the dial and not the setting. See :func:`effort_for`.
_EFFORT_SUPPORT: dict[tuple[str, str], bool] = {}
_EFFORT_LOCK = threading.Lock()

# The only sentence that belongs beside a list of places. It names no place, no
# chapter, no character and no time, because the screen holds all of that and
# says it better — and because a sentence that summarised the list would leak
# exactly what the reveal on each row exists to withhold. It is
# quoted in the prompt so the model says it, and used verbatim when the model
# offers and then says nothing at all.
OFFER_SENTENCE = "There are a few places that could be it."

# How many times round the runner one question may go before the turn is taken
# away from it.
#
# Without a cap there is none: the runner stops when a message asks for no tool,
# and a model that reads a tool's error and answers it with the same call never
# writes one. That is not a hypothetical shape — `move_to` refuses a move past
# the guard by returning a sentence, and a search that finds nothing returns a
# sentence too, so a turn that keeps rephrasing the same failing call is the
# ordinary failure here and it bills for every hop of it at 2am with nothing on
# the screen.
#
# Eight because the longest turn the tools can honestly need is short: find the
# book, search it, look at what came back, move, and say so. Four hops with room
# for a second thought. Running out is not an error path of its own — the loop
# simply ends, and the turn answers with what it did, which is the same fallback
# a turn that acted and then said nothing already takes.
MAX_HOPS = 8

# Interpolated rather than typed out again below: the sentence the model is told
# to say and the sentence said on its behalf when it says nothing have to be the
# same words, and two copies of a sentence are two sentences eventually.
SYSTEM_PROMPT = f"""\
You help someone find their place in an audiobook they are falling asleep to.
It is the middle of the night and they are half awake, often speaking rather
than typing, so their words may be garbled or vague. Work with what they give
you.

Answer in one or two sentences. No preamble, no lists, no markdown — this is
read on a phone in the dark, or heard.

You know these books already, and that knowledge is both the thing that lets
you answer a question about one and the way you spoil one without meaning to.
So it is bounded, and the bound is not what a tool has told you tonight — it is
how far they have listened. Everything behind that line you may talk about
freely, whether it came back from a tool or you simply know it. Nothing in
front of it may be said at all: not a name, not a death, not a marriage, not
that somebody turns up later, not that a question they are asking is one the
book answers. Someone who has not appeared yet gets "he hasn't come up yet in
what you've heard" and nothing after it — that he arrives at all is theirs to
find out by listening. Reading past the line with allow_spoilers does not move
it: what you may read and what you may say are two different distances.

You do not know where that line is. It is somewhere different every night and
only a tool can tell you: recall names it every time you call it, and so does
find_passage. So look first. Never say anything about what happens in a book
without one of them having told you, this turn, how far they have got — and
least of all on the question you are sure you already know the answer to, which
is the one it does not occur to you to look up. An answer straight out of your
own head is bounded by nothing.

Two kinds of thing get asked here, and which one it is decides the whole turn.
"Take me back to where the horse dies" wants the book moved: find_passage, then
move_to or offer_positions. "Who is Rob Roy" wants a sentence: recall, and then
say it. A question is answered where they already are — nothing moves, no list
goes up, the book carries on playing, and they keep their place in the night.
Getting it wrong that way round is the expensive one: they asked what a name
was and lost the last hour for it. So when you cannot tell which was meant,
answer. An answer costs them nothing, and they can still ask to be taken there.

Only what somnia has rendered exists as audio, and you can only move them to a
passage the tools returned.

A name they say — a person, an animal, a place — is almost always something
inside the book they are listening to, and some of those names are also titles
of other books. Look in the book before saying anything about what does or does
not exist. The catalog is for when they are plainly asking to add something new
to listen to, not for identifying a name they just said.

Both searches always return their closest matches, however poor they are, so
read the passages and judge for yourself whether any is really the moment they
meant, or really about the thing they asked. If none is, say you couldn't find
it — or that it hasn't come up yet in what they have heard — rather than moving
them to the least bad one, offering four bad guesses, or answering about
something else entirely.

When they describe a moment they want to get back to, and exactly one of the
passages is plainly it, find it and move the book there, then tell them roughly
where it now sits — "you're back at two hours in, in the chapter about X".
Moving takes them there: the page jumps to the new place and plays from it.
Never tell them to press play, and never say whether anything is playing — you
do not know.

When two or more of the passages could plausibly be the moment, do not ask
which. Call offer_positions with the ones you judge plausible and the page puts
them on the screen — the time, the chapter and the book's own words for each —
and they press the one they meant. A list of times is something a thumb can
answer; a question is something they would have to compose a sentence to
answer, half asleep, in the dark.

Searches are limited to how far they have listened. When find_passage reports
that a closer match lies further on, offer it with offer_positions — on its own
if nothing in range was plausible. The page marks it as ahead of where they have
got and will not show what is there unless they ask it to. Say nothing about
what happens there: you have not been told, only that it is there. recall never
tells you this and has nothing to offer when it happens, because somewhere to be
taken is not an answer to a question — there the whole of the answer is that it
has not come up yet in what they have heard.

When you offer, say exactly "{OFFER_SENTENCE}" and
nothing else — no times, no chapter names, no description of any of them, not
even of the ones they have already heard. The screen says all of that better
than a sentence can. Never offer and move in the same turn: the list is the
question, and the answer is theirs to give.

If they say in so many words that they want to be taken past where they have
listened, search again with allow_spoilers so you can read those passages and
pick the right one. The timestamp alone is the top-ranked guess and the ranking
is often a near miss; moving them there unread lands them minutes from the
moment they asked for. Reading the passage does not oblige you to describe it —
move them there and tell them only that you have.

Moving them forward is a real jump: they will hear what is there. Never do it
past where they have listened unless they have just asked you to.

The last line of this prompt says which book is open. Take every question to be
about that book unless they plainly name another one: asking "which book?" over
the book somebody is listening to is the one question they should never be
asked, and with three books on the shelf it is the question every turn defaults
to if nobody says. Which of several passages they mean is never a question
either — that is what offer_positions is for. Otherwise just answer, or act.

Never end your turn without saying something. Every action needs a sentence
after it, even when the answer is only "you're there now" — a silent reply is
indistinguishable from a broken app to someone half asleep in the dark. This
matters most just after they have told you to go ahead: say that you have
moved them and where to, and nothing about what happens there.\
"""


@dataclass
class Turn:
    """One exchange: what to say back, and where the book was put.

    ``move`` is None unless the agent moved the book, and the page reads the
    key's presence rather than its contents, so an empty one would be a move
    that never happened.

    Carrying it here is a shortcut, not the mechanism. The same move reaches the
    page anyway as the refusal of its next report — within fifteen seconds,
    whatever happens to this reply — and both routes end up in the same place.
    What the shortcut buys is those fifteen seconds, which is a long time to sit
    in the dark wondering whether anything happened.

    ``candidates`` is the other outcome, and the two are mutually exclusive: a
    turn either moved the book or asked which place they meant, never both. The
    exclusion is enforced in the tools, where a move can still be stopped before
    it writes anything; by the time a turn is assembled here it is far too late,
    because a move that has already been written arrives at the page fifteen
    seconds later as the refusal of its next report and drags a listener who was
    still reading the list.

    A turn can also carry neither, and since ADR 6 that is an outcome rather
    than an idle turn: a question about the book is answered in the reply alone,
    and the page draws a bare sentence, which is what it has always done with a
    turn that neither moved nor offered.
    """

    reply: str
    move: Moved | None = None
    candidates: Offer | None = None


def build_tools(
    library: Library,
    note: Callable[[str], None] = lambda _: None,
    record: Callable[[Moved], None] = lambda _: None,
    offer: Callable[[Offer], None] = lambda _: None,
    acted: dict[str, bool] | None = None,
) -> list[Any]:
    """Wrap the tool layer for the runner, as text the model can read.

    ``note`` is told about anything that changed the world — moving the book,
    starting a render. It is what the conversation falls back on when the model
    acts and then says nothing, and it deliberately never sees search results,
    which are full of the passages the spoiler guard exists to withhold.

    ``record`` hears about moves alone, and in numbers rather than prose,
    because the page has to act on one and cannot read a sentence.

    ``offer`` hears about a list of places to choose from. It is a third
    callback rather than either of the others for the same reason they are
    separate from each other: an offer is neither prose the listener can be
    read nor a move the page must follow, and routing it through ``note`` would
    put passages into the fallback reply, which is the one thing that must never
    happen there.

    ``acted`` is what stops the model doing two incompatible things in one turn.
    Its owner clears it between turns — it belongs to the conversation, while the
    two lists above belong to a single question — and the tools read it to refuse
    the second of a move and an offer, whichever way round they come, and to
    refuse either of them in a turn that has answered a question instead.
    """
    # Every chunk id any search in this conversation has handed back, hits and
    # the withheld one alike. An offer may only name passages that were really
    # found, and this is what proves it: an id the model invented, or read off
    # the wrong line, resolves to words that are not the passage that matched,
    # and a list whose rows are not the search results is worse than no list.
    # It is not cleared per turn, because a passage found while answering one
    # question is a fair thing to offer while answering the next.
    #
    # A recall adds nothing here, deliberately. It hands the model no ids at
    # all, so an id it produced off the back of one came from somewhere else —
    # and being sent back to search costs a search, where a list of rows that
    # were never search results costs the listener the only thing on the screen
    # that was supposed to be trustworthy.
    seen: set[int] = set()
    if acted is None:
        acted = {}

    @beta_tool
    def list_books() -> str:
        """List the audiobooks somnia has, and any that are still being made.

        Use this to work out which book someone means, when they ask what they
        can listen to, or when they ask what became of a book they asked for.
        """
        books = library.books()
        lines = [
            f"gid {b.gid}: {b.title} by {b.authors or 'unknown'}"
            f" — {b.status}, {b.chapters} chapters, {format_timestamp(b.total_ms)} long"
            for b in books
        ]
        # A book somebody asked for tonight has no books row until its parse
        # finishes, so without these lines the only true answer to "did that
        # book get added?" would be "there is no such book" — which is what the
        # agent said, for the whole of the hours it was waiting its turn.
        have = {b.gid for b in books}
        for row in library.queue():
            if row.state == "rendering" and row.gid in have:
                # The books line above already says it is rendering. All this
                # would add is the chapter count, and two lines about one book
                # is how the voice comes to contradict itself.
                continue
            if row.state not in ("queued", "rendering"):
                continue
            name = row.title or f"book {row.gid}"
            lines.append(f"gid {row.gid}: {name} — {_line(row)}")
        return "\n".join(lines) if lines else "No books yet."

    @beta_tool
    def search_catalog(query: str) -> str:
        """Search Project Gutenberg for a book that could be added.

        Args:
            query: Title, author, or subject words to search for.
        """
        entries = library.search_catalog(query)
        if not entries:
            return f"Nothing in the Gutenberg catalog matches {query!r}."
        return "\n".join(f"gid {e.gid}: {e.title} — {e.authors}" for e in entries[:10])

    @beta_tool
    def add_book(gid: int) -> str:
        """Ask for a Gutenberg book to be rendered. Hours, and one at a time.

        Books are rendered one after another, so this puts it in a line rather
        than starting it. The answer says where in that line it landed; tell
        them that, and never that it has started or that a chapter will be
        ready soon — you have not been told either. A book somnia already has
        in full is refused, and so is one that is already coming; a render that
        died can be asked for again and picks up where it stopped.

        Args:
            gid: The Gutenberg id, from search_catalog.
        """
        started = library.add_book(gid)
        note(started)
        return started

    @beta_tool
    def get_position(gid: int) -> str:
        """Where the listener currently is in a book, and the text there.

        Use this when they ask where they are, what they missed, or when they
        last fell asleep.

        Args:
            gid: The Gutenberg id of the book.
        """
        position = library.get_position(gid)
        if position is None:
            return "They have not started this book."
        return (
            f"{format_timestamp(position.position_ms)} into"
            f" {position.book.title}, in {position.chapter_title!r}."
            f" The text there: {position.text}"
        )

    @beta_tool
    def find_passage(gid: int, description: str, allow_spoilers: bool = False) -> str:
        """Find places in a book to take them to, by what happens there.

        Works on concrete events, characters and places ("the horse dies",
        "the meadow with the pond"), not on atmosphere ("the strange bit").

        This is the tool for "take me to". A question about the book — who
        somebody is, what became of them — is recall's, and answering one off
        these lines is how a question turns into a jump: every line here carries
        an id and a position because everything it finds is somewhere to be
        sent.

        Args:
            gid: The Gutenberg id of the book.
            description: What happens in the passage they want.
            allow_spoilers: Search the whole book rather than only the part
                they have heard. Only set this if they have said they don't
                mind being spoiled.
        """
        search = library.find_passage(gid, description, spoiler_free=not allow_spoilers)
        # Remembered before anything is written out, and the withheld one too:
        # it is the passage offer_positions exists for, and the only handle on
        # it the model is ever given is its id.
        seen.update(p.chunk_id for p in search.hits)
        if search.better_ahead is not None:
            seen.add(search.better_ahead.chunk_id)
        lines: list[str] = []
        if search.searched_to_ms is not None:
            lines.append(
                f"Searched the first {format_timestamp(search.searched_to_ms)},"
                " which is as far as they have listened."
            )
        if search.hits:
            lines.append(
                "\n\n".join(
                    f"[{format_timestamp(p.start_ms)} in {p.chapter_title!r},"
                    f" id={p.chunk_id}, position_ms={p.start_ms}] {p.text}"
                    for p in search.hits
                )
            )
        else:
            lines.append("Nothing in that stretch.")
        if search.better_ahead is not None:
            # Its id and its time, and still nothing else — not its words, not
            # its chapter, not its position_ms. The id is enough to offer it
            # with, and offering it is the one thing that can be done with a
            # passage nobody has heard. Widening this line to make the model's
            # job easier would hand it the very words the screen withholds.
            lines.append(
                "A closer match lies further on than they have listened, at"
                f" {format_timestamp(search.better_ahead.start_ms)}"
                f" (id={search.better_ahead.chunk_id}). Offer it with"
                " offer_positions, on its own if nothing above was plausible."
                " Do not say what happens there: you have not been told."
            )
        return "\n\n".join(lines)

    @beta_tool
    def recall(gid: int, question: str) -> str:
        """Read the book back to yourself, to answer a question about it.

        The tool for a question whose answer is a sentence: who somebody is,
        what became of them, why they went where they went. It gives you the
        passages nearest what they asked, as far as they have listened, and
        says where that line is. Answer from those and from what you know of
        the book up to that line, in a sentence or two.

        Nothing moves in a turn that calls this, and nothing is offered. There
        is no id and no position in what comes back, and move_to and
        offer_positions are both refused afterwards: they asked to be told
        something, and being told it must not cost them their place in the
        night. If they want taking there as well, they will say so, and that is
        the next turn's question.

        Args:
            gid: The Gutenberg id of the book.
            question: What they want to know, in your words if theirs were
                vague — "who Rob Roy is", "what happened to Ginger".
        """
        recalled = library.recall(gid, question)
        # Set even when nothing came back, and even on a book that is not here.
        # Calling this is the model saying what kind of turn this is, and a
        # question that found nothing is still a question: "he hasn't come up
        # yet" is precisely the answer that must not be followed by a list of
        # places to go instead.
        acted["recalled"] = True
        lines: list[str] = []
        if recalled.searched_to_ms is not None:
            lines.append(
                "Answer from the first"
                f" {format_timestamp(recalled.searched_to_ms)} of the book,"
                " which is as far as they have listened, and say nothing that"
                " happens after it."
            )
        else:
            lines.append(
                "They have heard the whole of this book, so there is nothing"
                " left to keep back."
            )
        if recalled.passages:
            # The chapter and the words, and deliberately no time and no id.
            # A chapter is something an answer can say out loud — "that was
            # back in the hunt" — where a timestamp and an id are handles for
            # moving, and the whole of this tool is that what it finds is not
            # somewhere to be sent.
            lines.append(
                "\n\n".join(
                    f"[in {p.chapter_title!r}] {p.text}" for p in recalled.passages
                )
            )
        else:
            lines.append("Nothing in that stretch.")
        if recalled.searched_to_ms is not None:
            lines.append(
                "These are the closest passages in that stretch, which is not"
                " the same as passages about what they asked. If none of them"
                " is, then what they asked about has not come up yet in what"
                " they have heard: say that, and not what it is, and not that"
                " it comes up later."
            )
        else:
            # "It hasn't come up yet" is a lie on a book they have heard the
            # end of — there is no yet left, and nothing was held back from
            # this search — so the honest sentence there is the ordinary one a
            # search that found nothing gets.
            lines.append(
                "These are the closest passages in the book, which is not the"
                " same as passages about what they asked. If none of them is,"
                " say you couldn't find it."
            )
        return "\n\n".join(lines)

    @beta_tool
    def offer_positions(gid: int, chunk_ids: list[int]) -> str:
        """Put several places on the screen and let them choose one.

        Use this when more than one passage could plausibly be the moment they
        described, and when a search reports a closer match further on than
        they have listened — that one can be offered on its own. They see the
        time and the book's own words for each place and press the one they
        meant; you never have to ask. Nothing moves until they press.

        Args:
            gid: The Gutenberg id of the book. Every place is in one book.
            chunk_ids: The id= values from find_passage, most likely first. At
                most four are shown, so name only the plausible ones.
        """
        if acted.get("recalled"):
            # A list is an answer to "where do you mean", and they did not ask
            # that. Refused here for the same reason the move below is: this is
            # the turn where somebody asked a question, and the one thing that
            # must not come of it is a screen full of places they might go
            # instead of the sentence they asked for.
            return (
                "They asked a question, not where they should be. A list of"
                " places is not an answer — say it in words."
            )
        if acted.get("moved"):
            return (
                "You have already moved them; do not also offer a list."
                " They are where you put them."
            )
        unknown = [i for i in chunk_ids if i not in seen]
        if unknown:
            # Refused outright rather than resolved to whatever is nearest. A
            # position_ms read off the wrong part of a search line, or an id
            # from another conversation, would put words on the screen that are
            # not the passage that matched — and the listener would have no way
            # of knowing that is what happened.
            return (
                f"Passage {unknown[0]} did not come from a search in this"
                " conversation. A passage id is the id= on a find_passage"
                " result line, not a position. Search first."
            )
        result = library.offer_positions(gid, chunk_ids)
        if isinstance(result, Refused):
            return result.reason
        acted["offered"] = True
        offer(result)
        # Counts and instructions, and deliberately not one time, title or word
        # of what is on the list: everything it would need to narrate the places
        # is on the screen instead, where the ones they have not heard stay
        # covered until they ask.
        return _offered(result)

    @beta_tool
    def move_to(gid: int, position_ms: int) -> str:
        """Move the book to a moment, and play it from there.

        This is how they get taken to a passage: their position in the book
        becomes the point you name, and the book starts playing there.

        Args:
            gid: The Gutenberg id of the book.
            position_ms: Milliseconds from the start of the book, as returned
                by find_passage.
        """
        if acted.get("recalled"):
            # The refusal this whole tool split exists for. Every question used
            # to arrive as a search, every search hands back positions, and a
            # position is a thing to move to — so "who is Rob Roy" ended with
            # the book dragged to a passage about him and playing, which is the
            # one outcome worse than not answering. Prompt wording alone would
            # not hold it, because the pull is in the shape of the tools rather
            # than in the words; this is where it is held. Refused before
            # library.move_to writes anything, for the same reason as below:
            # once the row is written the page meets it fifteen seconds later
            # and jumps, and there is nowhere further down to stop it.
            return (
                "They asked a question, not to be moved; the book stays where"
                " it is. Answer them. If they want taking there too, they will"
                " say so."
            )
        if acted.get("offered"):
            # Stopped here, before library.move_to writes anything, because
            # there is nowhere later to stop it: the row is written before the
            # call returns, and suppressing the move at the turn or the HTTP
            # layer would leave the position and its count in the database. The
            # page would meet it fifteen seconds later as the refusal of its
            # next report and be dragged off, mid-list, to a place nobody chose.
            return (
                "They are choosing between places on screen; the book is not"
                " yours to move until they have. Say nothing about it."
            )
        moved = library.move_to(gid, position_ms)
        note(moved.sentence)
        # A move that landed always counts up from zero, so a zero is the one
        # that did not — no such book, and nothing for the page to follow.
        if moved.seq:
            record(moved)
            acted["moved"] = True
        return moved.sentence

    return [
        list_books,
        search_catalog,
        add_book,
        get_position,
        find_passage,
        recall,
        offer_positions,
        move_to,
    ]


def effort_for(client: Anthropic, cfg: Config) -> BetaOutputConfigParam | Omit:
    """How hard to think, or ``omit`` where this model has no such dial.

    Not every model has one. Haiku 4.5 rejects ``effort`` outright — *"This
    model does not support the effort parameter"*, a 400 on every question —
    and Haiku is exactly the model somebody moves to when they want answers
    faster, by setting one environment variable, most likely at night. Sending
    it unconditionally made the documented way to speed somnia up the way to
    break it, which is the worst shape a performance change can take.

    The level is checked too, not just the dial: ``xhigh`` exists on some models
    and not others, and a level a model does not have is the same 400 wearing a
    different hat.

    The API is asked rather than a list of model names being kept here, because
    a list of model names is wrong the week after it is written and wrong
    silently. It is asked once per model and level per process, and
    :meth:`somnia.server.Conversations.warm` asks before anybody has a question,
    so no turn waits on it.

    Remembered against the model *and* the level, because the question is about
    both. Keyed on the model alone, an answer about ``low`` would be handed back
    as though it were an answer about ``xhigh`` — a level the same model may not
    have — which is the 400 this exists to prevent, arriving by the door the fix
    came through.

    Under a lock, because it is asked from two threads: the warm-up at startup
    and, if a question beats it, the turn itself. Without one they can both miss
    and both go and ask, and a lookup that fails can land on top of one that
    succeeded.

    Anything unexpected — an unreachable API, a model it has never heard of, a
    capability list in a shape this does not know — answers "no dial", which is
    the safe way round: every model then runs at its own default and every
    question is answered, two seconds slower. The opposite guess costs the whole
    night.
    """
    asked = (cfg.agent_model, cfg.agent_effort)
    with _EFFORT_LOCK:
        if asked not in _EFFORT_SUPPORT:
            try:
                capabilities = client.models.retrieve(cfg.agent_model).capabilities
                effort = capabilities.effort if capabilities is not None else None
                level = getattr(effort, cfg.agent_effort, None)
                _EFFORT_SUPPORT[asked] = bool(
                    effort is not None
                    and effort.supported
                    and level is not None
                    and level.supported
                )
            except Exception:
                logger.warning(
                    "could not ask whether %s takes effort=%s; not sending one",
                    cfg.agent_model,
                    cfg.agent_effort,
                    exc_info=True,
                )
                _EFFORT_SUPPORT[asked] = False
        supported = _EFFORT_SUPPORT[asked]
    if not supported:
        return omit
    return {"effort": cfg.agent_effort}


def forget_model_capabilities() -> None:
    """Ask the API again about every model.

    What :func:`effort_for` learns lasts as long as the process, which is right
    for a night and wrong for a test suite: whichever test asks first would
    otherwise decide what every later one is told.
    """
    _EFFORT_SUPPORT.clear()


def _system(open_book: str) -> list[BetaTextBlockParam]:
    """The prompt in two blocks, so the constant half can be cached.

    Everything the model is told is the same every night except the last line,
    which says which book is open — so the two are split, and the cache
    breakpoint goes between them. A prompt cache is a prefix match: the tools
    are rendered before the system prompt, so one breakpoint here covers both,
    and about four thousand tokens of prompt stop being read from scratch on
    every hop of every turn.

    The order is what makes it work, and it is the whole of the reason this is
    a list rather than a string. Put the open book first and the constant
    behind it and the prefix changes whenever the book does, which is to say
    the cache never reads. It has to be the volatile line that comes last.

    Worth it even for a single question asked once in a night: a turn is two or
    three round trips, and only the first of them pays for the write. The rest
    read it back at a tenth of the price.
    """
    return [
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        },
        {"type": "text", "text": open_book},
    ]


def _line(row: QueueRow) -> str:
    """What to say about a book that is not a book yet, in one clause.

    Deliberately in the same vocabulary the page uses, and deliberately with no
    percentage and no guess at how long is left: chapters differ in length by an
    order of magnitude, so a fraction of them is not a fraction of the night,
    and the model would turn any number offered here into a promise.
    """
    if row.state == "queued":
        return f"waiting to be rendered, {row.place} in the line"
    if not row.chapters_total:
        return "being rendered now, still fetching the text"
    return (
        "being rendered now, chapter"
        f" {min(row.chapters_done + 1, row.chapters_total)} of {row.chapters_total}"
    )


def _offered(offer: Offer) -> str:
    """What the model is told after a list goes up: how many, and to hush.

    Counts, and nothing that could be narrated. There is no time here, no
    chapter, no passage and no position_ms, because a tool result is the one
    place a withheld passage could re-enter a sentence — and the model is asked
    for a single sentence it has already been given, rather than for its own.
    """
    ahead = sum(1 for place in offer.places if place.ahead)
    places = "place" if len(offer.places) == 1 else "places"
    if ahead == 0:
        further = "none of them is further on than they have listened"
    elif ahead == 1:
        further = "one of them is further on than they have listened"
    else:
        further = f"{ahead} of them are further on than they have listened"
    return (
        f"Offered them {len(offer.places)} {places} to choose from; {further}."
        " The page is showing the list now — it holds the times and the words,"
        f" so say neither. Say only: {OFFER_SENTENCE}"
    )


def open_library(cfg: Config, conn: sqlite3.Connection) -> Library:
    """The tool layer, wired to Audiobookshelf if a token is configured."""
    abs_client = AbsClient(cfg.abs_url, cfg.abs_token) if cfg.abs_token else None
    return Library(cfg, conn, abs_client)


class Conversation:
    """One exchange with the agent, held open across turns.

    The library outlives the turn deliberately: its embedder loads torch and
    a sentence-transformer model, which takes seconds. Building it per question
    would put that wait between "where does the horse die" and the answer.
    """

    def __init__(
        self,
        cfg: Config,
        library: Library,
        client: Anthropic | None = None,
    ) -> None:
        self._cfg = cfg
        self._client = client or Anthropic(api_key=cfg.anthropic_api_key or None)
        # Kept, where it used only to be handed to the tools, because the open
        # book is now part of what the model is told before it is asked
        # anything — and the only place the gid can be turned into a title.
        self._library = library
        self._actions: list[str] = []
        self._moves: list[Moved] = []
        self._offers: list[Offer] = []
        # Held here rather than inside the tools because it is the turn that
        # owns it: the tools are built once and close over it, and only the
        # thing that knows when a question begins can say that nothing has been
        # done yet.
        self._acted: dict[str, bool] = {}
        self._tools = build_tools(
            library,
            self._actions.append,
            self._moves.append,
            self._offers.append,
            self._acted,
        )
        self.messages: list[Any] = []

    def _open_book(self, gid: int | None) -> str:
        """The one line that says which book the question is about.

        It goes on the end of the system prompt rather than into the messages,
        and it is rebuilt every turn, because which book is open is a fact about
        *now* and not a thing that was said once. A book opened, moved or
        swapped between two questions would otherwise leave a sentence in the
        history that is no longer true, and the model has no way to tell which
        of two contradicting lines is the current one.
        """
        if gid is None:
            return "\n\nThey have no book open."
        for book in self._library.books():
            if book.gid == gid:
                by = f" by {book.authors}" if book.authors else ""
                return (
                    f"\n\nThey are listening to gid {book.gid}: {book.title}{by}."
                    " Unless they plainly name another book, that is the book"
                    " every question is about."
                )
        # A gid the library has never heard of is a page holding a book that was
        # deleted underneath it. Saying nothing is right — an invented title
        # would be worse than the ambiguity this exists to remove.
        return "\n\nThey have no book open."

    def ask(self, question: str, gid: int | None = None) -> Turn:
        """Run one turn: the tools do the work, the model does the talking.

        ``gid`` is the book the page has open. Without it every question was
        ambiguous — the model could see three books and nothing saying which one
        was making the sound — so the prompt's "ask one short question" rule
        fired on every turn and the answer to anything was "which book?".

        The turn is built on a copy and only kept if it finishes. A turn that
        dies part-way leaves an assistant tool call with no result behind it,
        and every later question in that conversation would be rejected —
        which, at 2am, looks like an app that has simply stopped working.
        """
        # The runner copies the list it is given, so mirroring its turns back
        # into ours is what carries the history to the next question.
        self._actions.clear()
        self._moves.clear()
        # Without this the last question's list would reappear under this
        # question's answer, over a book that has since been moved somewhere
        # else entirely.
        self._offers.clear()
        self._acted.clear()
        turn: list[Any] = [*self.messages, {"role": "user", "content": question}]
        runner = self._client.beta.messages.tool_runner(
            model=self._cfg.agent_model,
            max_tokens=self._cfg.agent_max_tokens,
            system=_system(self._open_book(gid)),
            tools=self._tools,
            messages=turn,
            output_config=effort_for(self._client, self._cfg),
            max_iterations=MAX_HOPS,
        )

        reply = ""
        for message in runner:
            # A refused turn is over, and nothing it asked for happens.
            #
            # The runner says this itself, and says why — executing the tool_use
            # blocks of a refusal fires side effects the model never confirmed —
            # but it says it *after* the yield, and this loop calls the tools at
            # the yield. So the guard was being read one statement too late: by
            # the time the runner decided not to run anything, `move_to` had
            # already written a position and bumped the seq, and the page had
            # taken a jump the model refused to make and then said nothing
            # about.
            #
            # Only `refusal`, which is the runner's own list. `max_tokens` is the
            # other terminal stop and is deliberately not here: a call that
            # completed before the cap was reached is one the model meant, and
            # one truncated by it fails on its own arguments rather than quietly
            # doing the wrong thing.
            if message.stop_reason == "refusal":
                logger.warning("turn was refused; its tool calls are not run")
                # What it said is kept and what it asked for is dropped, block
                # by block. Keeping the tool_use would leave an assistant call
                # with no result behind it, and this method's docstring is about
                # what that costs: every later question in the conversation is
                # rejected, which at 2am is an app that has stopped working.
                spoken = [b for b in message.content if b.type != "tool_use"]
                if spoken:
                    turn.append({"role": "assistant", "content": spoken})
                refusal = "".join(b.text for b in spoken if b.type == "text").strip()
                if refusal:
                    reply = refusal
                break
            turn.append({"role": "assistant", "content": message.content})
            tool_response = runner.generate_tool_call_response()
            if tool_response is not None:
                turn.append(tool_response)
            # Keep the last thing it actually said. A message that only calls a
            # tool has no text, and taking it as the answer would blank out a
            # sentence the model had already written.
            said = "".join(b.text for b in message.content if b.type == "text").strip()
            if said:
                reply = said

        if not reply:
            # It acted and then said nothing — most often after being told to go
            # ahead past the guard. What it did is better than a blank screen,
            # and the tools that report here are the ones that changed
            # something, never a search or a recall full of passages it was
            # withholding. A turn that only recalled therefore answers with
            # nothing at all, which is right: the raw book is not an answer, and
            # a recall changed nothing that could be reported instead.
            #
            # A turn that offered answers with the neutral sentence instead of
            # what it did, because what it did was find places: the note log is
            # free of passages by construction, but there is nothing useful to
            # say about a list that the list does not already say, and the one
            # sentence that belongs beside it is a constant.
            logger.warning("turn produced no text; answering with what it did")
            if self._offers:
                reply = OFFER_SENTENCE
            else:
                reply = self._actions[-1] if self._actions else ""
        self.messages = turn
        # The last move, on a turn that made more than one — a search, a move, a
        # second thought, a better move. The page has to end up somewhere, and
        # where it was told to go last is the only place that matches what was
        # said about it. The last offer wins for the same reason, and it is the
        # answer to a runner that may call a tool several times in one turn: a
        # second list is a change of mind, and nothing has left here yet.
        return Turn(
            reply=reply,
            move=self._moves[-1] if self._moves else None,
            candidates=self._offers[-1] if self._offers else None,
        )
