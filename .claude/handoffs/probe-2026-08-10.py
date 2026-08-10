"""The three scenarios this session has to make work, against the real books.

Runs on the VPS with PYTHONPATH pointing at an rsync'd branch, and
SOMNIA_DATA_DIR at a `VACUUM INTO` snapshot — it moves books, so it must never
see the live database.

    python -u probe.py [reps]
"""

import sys
import time
from typing import Any

from anthropic import Anthropic

from somnia.agent import Conversation, open_library
from somnia.config import load_config
from somnia.db import connect
from somnia.format import format_timestamp

cfg = load_config()
assert "evaldata" in str(cfg.db_path), f"refusing to run against {cfg.db_path}"

conn = connect(cfg.db_path, cross_thread=True)
lib = open_library(cfg, conn)
_ = lib.embedder
client = Anthropic(api_key=cfg.anthropic_api_key or None)

DRACULA = 45839
BEAUTY = 271
REPS = int(sys.argv[1]) if len(sys.argv) > 1 else 3


def seek(gid: int, ms: int) -> None:
    """What the page does: the position moves, the seq does not."""
    with conn:
        conn.execute("UPDATE books SET position_ms = ? WHERE gid = ?", (ms, gid))


def calls(conversation: Conversation) -> list[str]:
    return [
        block.name
        for message in conversation.messages
        if message.get("role") == "assistant"
        for block in message.get("content", [])
        if getattr(block, "type", None) == "tool_use"
    ]


def turn(conversation: Conversation, question: str, gid: int) -> dict[str, Any]:
    before = len(calls(conversation))
    started = time.perf_counter()
    answer = conversation.ask(question, gid)
    took = time.perf_counter() - started
    return {
        "q": question,
        "reply": answer.reply,
        "tools": calls(conversation)[before:],
        "move": answer.move,
        "offer": answer.candidates,
        "took": took,
    }


def show(result: dict[str, Any]) -> None:
    print(f"    > {result['q']}")
    print(f"      tools: {result['tools']}  ({result['took']:.1f}s)")
    print(f"      said:  {result['reply']}")
    if result["move"]:
        moved = result["move"]
        print(f"      MOVED to {format_timestamp(moved.position_ms)} seq={moved.seq}")
    if result["offer"]:
        for place in result["offer"].places:
            where = "AHEAD" if place.ahead else f"ch{place.chapter_idx + 1}"
            print(f"      place: {format_timestamp(place.start_ms)} {where}")


def chapter_at(gid: int, ms: int) -> str:
    row = conn.execute(
        "SELECT idx FROM chapters WHERE book_gid = ? AND start_ms <= ?"
        " ORDER BY start_ms DESC LIMIT 1",
        (gid, ms),
    ).fetchone()
    return f"ch{row['idx'] + 1}" if row else "?"


def scenario_stale_position() -> bool:
    """Move them, let the page move them again, ask to go back. #116."""
    print("\n--- 1. goto, page seek, goto again (Dracula) ---")
    seek(DRACULA, 6243367)
    conversation = Conversation(cfg, lib, client)
    show(turn(conversation, "go to chapter 2", DRACULA))
    seek(DRACULA, 5580015)
    print("      [page seek to 1:33:00, ch4 — nothing said in the conversation]")
    second = turn(conversation, "take me back to chapter 2", DRACULA)
    show(second)
    landed = second["move"] and chapter_at(DRACULA, second["move"].position_ms) == "ch2"
    print(f"      => {'PASS' if landed else 'FAIL'} (wanted a move back to ch2)")
    return bool(landed)


def scenario_one_hit() -> bool:
    """One passage is really the hare's death, so one place, so a move."""
    print("\n--- 2. where the hare dies (Black Beauty) ---")
    seek(BEAUTY, 2717118)
    conversation = Conversation(cfg, lib, client)
    result = turn(conversation, "take me to where the hare dies", BEAUTY)
    show(result)
    one = bool(result["move"]) or (result["offer"] and len(result["offer"].places) == 1)
    print(f"      => {'PASS' if one else 'FAIL'} (wanted exactly one place)")
    return bool(one)


def scenario_four_hits() -> bool:
    """Dogs are all over chapter 1, so an honest list of four."""
    print("\n--- 3. where dogs are mentioned (Black Beauty) ---")
    seek(BEAUTY, 2717118)
    conversation = Conversation(cfg, lib, client)
    result = turn(conversation, "take me to where dogs are mentioned", BEAUTY)
    show(result)
    places: list[Any] = result["offer"].places if result["offer"] else []
    # All in one chapter, which is chapter 2 "The Hunt" and not chapter 1: the
    # dogs in Black Beauty are the hunt's dogs, and the only other passage the
    # search likes is a bad-language argument in chapter 10 that is not about a
    # dog at all. Four places in one chapter is the honest answer here.
    good = len(places) == 4 and len({p.chapter_idx for p in places}) == 1
    print(f"      => {'PASS' if good else 'FAIL'} (wanted four places, one chapter)")
    return bool(good)


def raw_searches() -> None:
    """What the model is actually handed, before any judgement of it."""
    print("\n--- what find_passage returns ---")
    for gid, query in ((BEAUTY, "the hare dies"), (BEAUTY, "dogs are mentioned")):
        print(f"  {query!r}:")
        for hit in lib.find_passage(gid, query).hits:
            print(
                f"    d={hit.distance:.4f} ch{hit.chapter_idx + 1}"
                f" {format_timestamp(hit.start_ms)} — {hit.text[:90]}"
            )


def main() -> None:
    print(f"{cfg.db_path}  model={cfg.agent_model}  reps={REPS}")
    raw_searches()
    scores = {"stale": 0, "one": 0, "four": 0}
    for _ in range(REPS):
        scores["stale"] += scenario_stale_position()
        scores["one"] += scenario_one_hit()
        scores["four"] += scenario_four_hits()
    print(f"\n{'=' * 60}")
    for name, got in scores.items():
        print(f"  {name:8s} {got}/{REPS}")


if __name__ == "__main__":
    main()
