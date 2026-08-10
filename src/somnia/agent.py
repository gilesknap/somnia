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

from .config import Config
from .format import format_timestamp
from .queue import QueueRow
from .tools import Library, Moved, Offer, Refused

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
# writes one. That is not a hypothetical shape — `offer_positions` refuses an id
# it has not seen by returning a sentence, and a search that finds nothing
# returns a sentence too, so a turn that keeps rephrasing the same failing call
# is the ordinary failure here and it bills for every hop of it at 2am with
# nothing on the screen.
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

Two kinds of thing get asked here, and which one it is decides the whole turn.
"Take me back to where the horse dies" wants the book moved: find_passage, then
offer_positions with the places that could be it. "Who is Rob Roy" wants a
sentence: recall, and then say it. A question is answered where they already
are — nothing moves, the book carries on playing, and they keep their place in
the night. Getting it wrong that way round is the expensive one: they asked what
a name was and lost the last hour for it. So when you cannot tell which was
meant, answer. An answer costs them nothing, and they can still ask to be taken
there.

You know these books already, and that knowledge is what lets you answer a
question about one. It is bounded by how far they have listened. Everything
behind that line you may talk about freely; nothing in front of it may be said
at all — not a name, not a death, not that somebody turns up later, not that a
question they are asking is one the book answers. Someone who has not appeared
yet gets "he hasn't come up yet in what you've heard" and nothing after it.

You do not know where that line is; it is somewhere different every night and
only a tool can tell you. So look before you speak, and hardest on the question
you are sure you already know the answer to, which is the one it does not occur
to you to look up.

That is the whole of what you have to hold. Where the line falls, and what may
be shown of a place past it, are the tools' business and not yours: a search
simply does not hand you the words of anywhere they have not reached.

Never ask them which place they meant, and never ask whether they mind being
spoiled. Call offer_positions with every passage that could really be it, best
first. If one of them is a place they have already heard and nothing else is
plausible, that takes them straight there — say where they landed, roughly:
"you're back at two hours in, in the chapter about X". Otherwise the places go
on the screen and a thumb answers. Say exactly "{OFFER_SENTENCE}" and nothing
else then — no times, no chapter names, no description of any of them, not even
of the ones they have already heard. The screen says all of that better than a
sentence can.

Being taken somewhere means the page jumps there and plays from it. Never tell
them to press play, and never say whether anything is playing — you do not know.

Both searches return their closest matches however poor they are, so read the
passages you were given and judge whether any is really the moment they meant,
or really about the thing they asked. If none is, say you couldn't find it — or
that it hasn't come up yet in what they have heard — rather than offering four
bad guesses or answering about something else entirely.

A name they say — a person, an animal, a place — is almost always something
inside the book they are listening to, and some of those names are also titles
of other books. Look in the book before saying anything about what does or does
not exist. The catalog is for when they are plainly asking to add something new
to listen to, not for identifying a name they just said.

Only what somnia has rendered exists as audio, and you can only send them to a
passage a search returned.

The last line of this prompt says which book is open. Take every question to be
about that book unless they plainly name another one: asking "which book?" over
the book somebody is listening to is the one question they should never be
asked, and with three books on the shelf it is the question every turn defaults
to if nobody says.

Never end your turn without saying something. Every action needs a sentence
after it, even when the answer is only "you're there now" — a silent reply is
indistinguishable from a broken app to someone half asleep in the dark.\
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
    Its owner clears it between turns — it belongs to the conversation, while
    the two lists above belong to a single question — and the tools read it to
    refuse a second goto once one has landed, and to refuse a goto at all in a
    turn that has answered a question instead. Since ADR 12 there is one place
    that has to be said rather than two: a move and a list come out of the same
    tool now, so they cannot arrive in either order.
    """
    # Every chunk id any search in this conversation has handed back, including
    # the ones whose words it was not shown. An offer may only name passages
    # that were really found, and this is what proves it: an id the model
    # invented, or read off the wrong line, resolves to words that are not the
    # passage that matched, and a list whose rows are not the search results is
    # worse than no list.
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
        results = library.search_catalog(query)
        if not results.entries:
            return f"Nothing in the Gutenberg catalog matches {query!r}."
        lines = [f"gid {e.gid}: {e.title} — {e.authors}" for e in results.entries[:10]]
        # First, because it changes what the rows below mean. A search that had
        # to correct a misspelling or drop a word has answered a question
        # slightly different from the one that was asked, and the model has to
        # be able to say so — "there is no Shelly, but here is Mary Shelley" is
        # the honest sentence, and it cannot be said if only the rows come back.
        if results.said:
            lines.insert(0, f"({results.said})")
        return "\n".join(lines)

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
    def find_passage(gid: int, description: str) -> str:
        """Find places in a book to take them to, by what happens there.

        Works on concrete events, characters and places ("the horse dies",
        "the meadow with the pond"), not on atmosphere ("the strange bit").

        This is the tool for "take me to". A question about the book — who
        somebody is, what became of them — is recall's, and answering one off
        these lines is how a question turns into a jump: every line here carries
        an id because everything it finds is somewhere to be sent.

        It searches the whole book. Places further on than they have got come
        back as a time and an id with no words and no chapter, because you are
        not told what happens there — you are told that there is a there. Offer
        those like any other; the screen keeps them covered until they ask.

        Args:
            gid: The Gutenberg id of the book.
            description: What happens in the passage they want.
        """
        search = library.find_passage(gid, description)
        # Every id, including the ones whose words are held back below: an id is
        # the only handle the model is ever given on a passage it may not read,
        # and offer_positions checks against this set before it will draw one.
        seen.update(p.chunk_id for p in search.hits)
        if not search.hits:
            return "Nothing like that in this book."
        # The whole of the guard on this side, and it is a line-formatting rule
        # rather than a search parameter — which is what makes it hold on a
        # model that does not read prompts carefully. A passage they have not
        # reached has never been in the context to be narrated out of; there is
        # nothing here for a prompt to have to forbid.
        #
        # The chapter title goes with the words, not with the time: "How Ginger
        # Died" gives away as much as the sentence under it. `position_ms` is on
        # no line at all any more — offers are made by id, so the number the
        # guard most wants to withhold is not printed anywhere.
        lines: list[str] = []
        for p in search.hits:
            when = format_timestamp(p.start_ms)
            if search.ahead(p):
                lines.append(
                    f"[{when}, id={p.chunk_id}] further on than they have got —"
                    " you have not been told what is there."
                )
            else:
                lines.append(
                    f"[{when} in {p.chapter_title!r}, id={p.chunk_id}] {p.text}"
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
        is no id and no position in what comes back, and offer_positions is
        refused afterwards: they asked to be told something, and being told it
        must not cost them their place in the night. If they want taking there
        as well, they will say so, and that is the next turn's question.

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
        """Send them to a place in the book, or put the choice on the screen.

        The way a "take me to" ends — always, however many passages you name.
        Name the ones that could really be the moment they described, best
        first, and this decides what happens to them: one place they have
        already heard takes them straight there, and anything else goes on the
        screen for them to press. You never have to work out which, and you must
        never ask them which.

        Args:
            gid: The Gutenberg id of the book. Every place is in one book.
            chunk_ids: The id= values from find_passage, most likely first. At
                most four are shown, so name only the plausible ones.
        """
        if acted.get("recalled"):
            # A list is an answer to "where do you mean", and they did not ask
            # that. This is the turn where somebody asked a question, and the
            # one thing that must not come of it is the book moving, or a screen
            # full of places they might go instead of the sentence they wanted.
            #
            # Both outcomes are stopped by this one branch now, which is what
            # collapsing the two tools bought: it used to be said twice, once
            # here and once in move_to, and the second one had to be got right
            # before library.move_to wrote anything.
            return (
                "They asked a question, not where they should be. Neither a list"
                " of places nor a jump is an answer — say it in words."
            )
        if acted.get("moved"):
            return (
                "You have already taken them somewhere; do not do it twice."
                " They are where you put them."
            )
        unknown = [i for i in chunk_ids if i not in seen]
        if unknown:
            # Refused outright rather than resolved to whatever is nearest. An
            # id from another conversation, or a number read off the wrong part
            # of a search line, would put words on the screen that are not the
            # passage that matched — and the listener would have no way of
            # knowing that is what happened.
            return (
                f"Passage {unknown[0]} did not come from a search in this"
                " conversation. A passage id is the id= on a find_passage"
                " result line. Search first."
            )
        # A second list is a change of mind and is allowed — the last offer wins
        # and nothing has left here yet — but a *move* under one is not, and it
        # cannot be caught after the fact: library.offer_positions writes before
        # it returns, and by the time a Turn is assembled the row is already on
        # its way to the page. So the fact that a list is up travels down with
        # the call, and the one place behind them comes back as a list of one.
        result = library.offer_positions(
            gid, chunk_ids, may_move=not acted.get("offered")
        )
        if isinstance(result, Refused):
            # Nothing was drawn and nothing was written, so nothing has been
            # spent: the model has just been told the gid or the ids were wrong,
            # which is exactly the moment it should be free to try again.
            return result.reason
        if isinstance(result, Moved):
            # One place, behind them, so the tools took them there rather than
            # asking. The model is told in the same sentence a move has always
            # been reported in, and says where they landed.
            note(result.sentence)
            # A move that landed counts up from zero, so a zero is one that did
            # not — no such book, and nothing for the page to follow.
            if result.seq:
                record(result)
                acted["moved"] = True
            return result.sentence
        acted["offered"] = True
        offer(result)
        # Counts and instructions, and deliberately not one time, title or word
        # of what is on the list: everything it would need to narrate the places
        # is on the screen instead, where the ones they have not heard stay
        # covered until they ask.
        return _offered(result)

    return [
        list_books,
        search_catalog,
        add_book,
        get_position,
        find_passage,
        recall,
        offer_positions,
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
        said = "being rendered now, still fetching the text"
    else:
        said = (
            "being rendered now, chapter"
            f" {min(row.chapters_done + 1, row.chapters_total)} of {row.chapters_total}"
        )
    # Carried through so that somebody who asks how a book is getting on is told
    # the one thing about it that is worth acting on tonight. It is a plain
    # clause about the book, not a number to be turned into a promise.
    return f"{said} ({row.note})" if row.note else said


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
    """The tool layer, on this connection."""
    return Library(cfg, conn)


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
            # the time the runner decided not to run anything,
            # `offer_positions` had already put a screen up — or, on one place
            # behind them, written a position and bumped the seq — and the page
            # had taken a jump the model refused to make and then said nothing
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
