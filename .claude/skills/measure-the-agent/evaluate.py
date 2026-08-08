"""How long a question takes, and whether the agent is still doing the job.

Read SKILL.md beside this before changing it — the shape of this file is mostly
the five traps it exists to avoid, and none of them announce themselves.

Prints verdicts and counts. It never prints what the model said on a case that
touches the spoiler guard, because the person reading this output is the person
who is 51 minutes into the book.

    python -u evaluate.py [reps]
"""

import json
import statistics
import sys
import time
from collections import defaultdict
from collections.abc import Callable

from anthropic import Anthropic

from somnia.agent import OFFER_SENTENCE, Conversation, open_library
from somnia.config import AgentEffort, load_config
from somnia.db import connect
from somnia.tools import format_timestamp

cfg = load_config()
# The whole reason this line is here: half the cases below move the book, and a
# move is a real write. Point SOMNIA_DATA_DIR at a `VACUUM INTO` snapshot.
assert "evaldata" in str(cfg.db_path), (
    f"refusing to run against {cfg.db_path} — take a snapshot first:\n"
    "  VACUUM INTO '/tmp/evaldata/somnia.db'\n"
    "then run with SOMNIA_DATA_DIR=/tmp/evaldata"
)

conn = connect(cfg.db_path, cross_thread=True)
lib = open_library(cfg, conn)
_ = lib.embedder  # pay the twelve seconds before anything is timed
client = Anthropic(api_key=cfg.anthropic_api_key or None)

GID = 271  # Black Beauty
HEARD_MS = lib.heard_to_ms(GID)
REPS = int(sys.argv[1]) if len(sys.argv) > 1 else 5

# The effort level is a wish, not an instruction: `effort_for` asks the API
# whether each model has the dial and quietly drops it where it has not, which
# is why Haiku can be listed here with a level it will never be sent.
MODELS: list[tuple[str, str, AgentEffort]] = [
    ("sonnet-5 (medium)", "claude-sonnet-5", "medium"),
    ("haiku-4.5", "claude-haiku-4-5", "medium"),
]

Tools = list[str]
MOVED = {"move_to", "offer_positions"}


def no_move(tools: Tools) -> bool:
    return not MOVED & set(tools)


def moves(tools: Tools) -> bool:
    return bool(MOVED & set(tools))


def no_catalog(tools: Tools) -> bool:
    return "search_catalog" not in tools


def anything(tools: Tools) -> bool:
    """The spoiler cases are about the words, not about which tools ran."""
    return True


def catalogs(tools: Tools) -> bool:
    return "search_catalog" in tools


# (name, question, judge the reply for spoilers, what the tool calls must be)
CASES: list[tuple[str, str, bool, Callable[[Tools], bool]]] = [
    # The failure that demoted Haiku in 9b26bb6: a name they said is something
    # in the book, not a book in the catalog. The regression case for any model.
    ("name not catalog: Rob Roy", "who is Rob Roy", True, no_catalog),
    ("name not catalog: Birtwick", "what is Birtwick", True, no_catalog),
    ("name not catalog: Merrylegs", "tell me about Merrylegs", True, no_catalog),
    ("name not catalog: garbled", "whos that squire fellow", True, no_catalog),
    # A question is answered where they are. Getting this backwards is the
    # expensive one: they asked what a name was and lost the hour.
    ("question, no move: who", "who is Ginger", True, no_move),
    ("question, no move: became of", "what happened to Ginger", True, no_move),
    ("question, no move: why", "why was Black Beauty sold", True, no_move),
    (
        "question, no move: half asleep",
        "wait who was the one with the bad temper",
        True,
        no_move,
    ),
    # Plainly a move, including the way it is actually said at 2am.
    (
        "move: a described moment",
        "take me back to where the horse bolts with the cart",
        False,
        moves,
    ),
    (
        "move: the beginning",
        "take me right back to the start of the book",
        False,
        moves,
    ),
    (
        "move: garbled 2am",
        "put me back at the bit with the hunt and the dogs",
        False,
        moves,
    ),
    # The catalog, when it really is the catalog.
    (
        "catalog when asked to add",
        "can you add Treasure Island to my books",
        False,
        catalogs,
    ),
    # Straight at the spoiler guard.
    ("spoiler: the ending", "how does the book end", True, anything),
    (
        "spoiler: a fate ahead",
        "what happens to Ginger in the end",
        True,
        anything,
    ),
    (
        "spoiler: turns out ok",
        "does Black Beauty find a good home in the end",
        True,
        anything,
    ),
    ("spoiler: someone not met yet", "who is Jerry Barker", True, anything),
    # Something ahead of the mark is answered in words, never as a list of
    # places to go instead.
    ("no list for a question ahead", "when does Ginger die", True, no_move),
]

JUDGE = "claude-opus-5"
# Structured, because asked for "CLEAN or LEAK: <reason>" in prose it writes
# "LEAK: none — reveals nothing later" and a naive parser scores that a leak.
SCHEMA = {
    "type": "object",
    "properties": {
        "reveals_later_events": {"type": "boolean"},
        "category": {
            "type": "string",
            "description": "Five words naming the KIND of leak, never the plot. "
            "Empty string when there is no leak.",
        },
    },
    "required": ["reveals_later_events", "category"],
    "additionalProperties": False,
}
JUDGE_PROMPT = """\
You are checking one sentence for spoilers, for a bedtime audiobook reader.

The book is Black Beauty by Anna Sewell. The listener has heard the first
{heard} of it — roughly the first sixth. They are still in the early chapters
at Birtwick Park.

Here is what an assistant said to them:
<reply>
{reply}
</reply>

Set reveals_later_events to true if and only if that reply states or strongly
implies something from Black Beauty that happens AFTER the first {heard}.
Naming a character who has not appeared yet, a death, an injury, a sale, a
reunion, or how the book ends all count if they lie ahead of that point.

These are NOT leaks, and must be false:
  - saying the thing has not come up yet in what they have heard
  - declining to say, or saying it could not be found
  - anything about the early Birtwick chapters
  - a bare sentence with no plot content at all
"""


def judge(reply: str) -> tuple[bool, str]:
    """True when the reply is safe, plus the category of any leak.

    max_tokens is generous because Opus 5 thinks by default and the cap covers
    thinking and text together: too small and the message comes back with no
    text block at all.
    """
    message = client.messages.create(
        model=JUDGE,
        max_tokens=8000,
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[
            {
                "role": "user",
                "content": JUDGE_PROMPT.format(
                    heard=format_timestamp(HEARD_MS), reply=reply
                ),
            }
        ],
    )
    text = next((b.text for b in message.content if b.type == "text"), "")
    if not text:
        raise RuntimeError(f"judge said nothing; stop_reason={message.stop_reason}")
    verdict = json.loads(text)
    return (not verdict["reveals_later_events"]), verdict["category"]


def ask(model: str, effort: AgentEffort, question: str) -> tuple[str, Tools, float]:
    """One turn, timed, with the tool calls it made.

    Deliberately through :meth:`Conversation.ask` rather than driving the tool
    runner here. An earlier version of this built its own runner so it could
    vary the model, and in doing so it stopped exercising the two things most
    worth measuring — the split prompt and :func:`effort_for`, which is what
    decides whether an effort level is sent at all. A harness that reimplements
    the code path is measuring the harness.

    The tool calls come out of ``conversation.messages``, which the turn mirrors
    its own history into, so nothing private is reached for to get them.
    """
    settings = load_config()
    settings.agent_model = model
    settings.agent_effort = effort
    conversation = Conversation(settings, lib, client)

    started = time.perf_counter()
    turn = conversation.ask(question, GID)
    took = time.perf_counter() - started

    tools = [
        block.name
        for message in conversation.messages
        if message.get("role") == "assistant"
        for block in message.get("content", [])
        if getattr(block, "type", None) == "tool_use"
    ]
    return turn.reply, tools, took


def main() -> None:
    print(
        f"{cfg.db_path}\nBlack Beauty, heard to {format_timestamp(HEARD_MS)};"
        f" {REPS} tries per case\n"
    )
    scores: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    times: dict[str, list[float]] = defaultdict(list)

    for label, model, effort in MODELS:
        print(f"\n{'=' * 70}\n{label}\n{'=' * 70}")
        for name, question, judged, routed_well in CASES:
            routed = safe = spoke = 0
            notes: list[str] = []
            for _ in range(REPS):
                reply, tools, took = ask(model, effort, question)
                times[label].append(took)
                if routed_well(tools):
                    routed += 1
                else:
                    notes.append(f"routed to {tools or '[]'}")
                if judged:
                    clean, why = judge(reply)
                    safe += clean
                    if not clean:
                        notes.append(f"spoiler — {why}")
                else:
                    safe += 1
                if "offer_positions" in tools and OFFER_SENTENCE not in reply:
                    notes.append("offered a list without the offer sentence")
                else:
                    spoke += 1
            scores[label]["routed"] += routed
            scores[label]["safe"] += safe
            scores[label]["n"] += REPS
            bad = routed < REPS or safe < REPS or spoke < REPS
            print(
                f"  {'FAIL' if bad else 'ok  '} route {routed}/{REPS}"
                f"  safe {safe}/{REPS}  {name}"
            )
            for note in dict.fromkeys(notes):
                print(f"         - {note}")

    print(f"\n{'=' * 70}\nsummary\n{'=' * 70}")
    for label, _, _ in MODELS:
        got, taken = scores[label], sorted(times[label])
        print(
            f"  {label:20s} routing {got['routed']:3d}/{got['n']}"
            f"   spoiler-safe {got['safe']:3d}/{got['n']}"
            f"   median {statistics.median(taken):5.2f}s"
            f"   p90 {taken[int(len(taken) * 0.9)]:5.2f}s"
        )


if __name__ == "__main__":
    main()
