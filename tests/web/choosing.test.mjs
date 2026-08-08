// Places you might be
//
// Some questions have more than one answer, and the old way of saying so was a
// conversation held in the dark by someone half asleep. This is that
// conversation as a list of times a thumb can point at — and everything below
// is about the three promises it makes, because a list of places to jump to is
// the most dangerous thing this page has ever put on the screen.
//
// The promises: nothing has moved while it is up, so cancel can put it away
// having changed nothing at all; a place further on than they have listened
// keeps its words to itself until they ask for them, and asking costs nothing
// and tells nobody; and a row is a seek made by the person holding the phone,
// landing on the millisecond the server named. The first and the last are
// state-machine claims and are asserted as sequences. The middle one is the
// spoiler guard, which is the one invariant in this project that cannot be
// wrong, so it is asserted from both ends: the words are not in the page before
// the press, and pressing raises nothing that the guard can see.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import {
  boot,
  HALF_HEARD,
  OTHER_BOOK,
  RENDERING_BOOK,
  START_MS,
} from "./harness.mjs";

// agent.OFFER_SENTENCE, which is the whole of what the model is allowed to say
// beside a list. It names no place, no chapter, no character and no time.
const OFFER_SENTENCE = "There are a few places that could be it.";

// What is left of the phone with a keyboard over it, for the tests at the foot
// of this file about which screen a question's answer leaves them on. The
// number is not a threshold — see screens.test.mjs, which owns this measurement
// and everything decided from it.
const WITH_KEYBOARD = 420;

// Words from a part of the book they have already heard, and words from a part
// they have not. Distinct on purpose: every assertion about the guard is
// "HIDDEN is nowhere", and two rows sharing a sentence would let a leak hide
// behind a passage it was fine to show.
const HEARD_TEXT =
  "The horse was down in the shafts, and the carter stood over him.";
const HIDDEN_TEXT =
  "He fell as he was led out of the yard, and did not get up again.";

// Two more of the book's own sentences, from parts they have heard. Named
// rather than written out where they are used, because every one of them is
// asserted twice — once as what a row says and once as what the DOM holds.
const RAIN_TEXT = "The water was over the low part of the road.";
const AFTER_TEXT = "Nobody said anything for a long while after that.";

// The mark: how far into this book the sound has really got. The page never
// reads it and never recomputes anything from it — `ahead` arrives already
// decided — so this stands in for the server, applying the rule the server
// applies: `start_ms >= heard_to_ms`, with no slack and no exemption for a
// finished book. Tests that want to prove the page obeys rather than
// calculates build their places by hand instead.
function place(chunk_id, start_ms, text, { chapter_idx, chapter_title }) {
  return {
    chunk_id,
    start_ms,
    chapter_idx,
    chapter_title,
    ahead: start_ms >= HALF_HEARD.heard_to_ms,
    text,
  };
}

const BEHIND = { chapter_idx: 0, chapter_title: "What They Have Heard" };
const BEYOND = { chapter_idx: 1, chapter_title: "What They Have Not" };

// Four places in the open book — the most a list is ever allowed to hold: two
// behind the mark, one exactly on it, and one well past it. The odd
// millisecond on the second is deliberate; it is the one a row is tapped on,
// and a page that rounded a candidate to the second would land four hundred
// milliseconds from the sentence they picked.
function places() {
  return [
    place(11, 300_000, HEARD_TEXT, BEHIND),
    place(12, 1_234_567, RAIN_TEXT, BEHIND),
    place(13, 1_800_000, HIDDEN_TEXT, BEYOND),
    place(14, 2_400_000, AFTER_TEXT, BEYOND),
  ];
}

// A place in the book that is not open, which the server judged against that
// book's own mark and its own listener.
function elsewhere() {
  return {
    chunk_id: 21,
    start_ms: 12_000,
    chapter_idx: 1,
    chapter_title: "Elsewhere Two",
    ahead: false,
    text: "Somewhere else entirely.",
  };
}

function offer(overrides = {}) {
  return {
    gid: HALF_HEARD.gid,
    title: HALF_HEARD.title,
    position_ms: HALF_HEARD.position_ms,
    places: places(),
    ...overrides,
  };
}

// The page, open on the book with the mark in the middle of it, having played
// nothing. This is the state a question is asked from at 2am more often than
// any other: the app was opened to ask something, and opening it is not
// listening.
async function opened(t, options) {
  const page = await boot(t, { lastGid: HALF_HEARD.gid, ...options });
  // The whole book, which is what the element is given: an hour of it, in two
  // half-hour chapters, so a place named an hour in is a place in the file.
  page.audio.ready();
  return page;
}

async function playing(t, options) {
  const page = await opened(t, options);
  page.click("playpause");
  await page.settle();
  return page;
}

// Time passing with the sound on, as stopping.test.mjs counts it: half a second
// at a time, because that is roughly what timeupdate comes off the media
// pipeline at and because the sleep timer refuses to be charged more than two
// seconds for one tick.
function listen(page, ms) {
  for (let left = ms; left > 0; left -= 500) {
    page.tick(Math.min(500, left));
    page.audio.fire("timeupdate");
  }
}

// What an earlier page wrote down before it was discarded.
function armed(choice, leftMs, at = START_MS - 60_000) {
  return { "somnia-sleep": JSON.stringify({ choice, leftMs, at }) };
}

// And what it wrote down about the last question it was asked: the places
// somnia offered, exactly as they were put on the screen. `record` rather than
// `offer()` in the two tests that give it rubbish, because half of what this
// key has to survive is not being a list at all.
function kept(record) {
  return { "somnia-places": JSON.stringify(record) };
}

// The list as somebody looking at it would read it out, top to bottom. Rows are
// read out of the DOM rather than out of the payload on purpose: what the
// payload said is the server's business, and the only thing worth asserting
// here is what ended up on the screen.
//
// A row is two targets now — the reading on the left, `goto` on the right — so
// nothing below counts children by position. Each part is found by the class
// the sheet styles it with, which is the same name the page has to keep for the
// row to look like anything at all.
function part(node, name) {
  for (const child of node.children) {
    if (child.classList.contains(name)) return child;
    const deeper = part(child, name);
    if (deeper) return deeper;
  }
  return null;
}

function rows(page) {
  return page.el("candidate-list").children.map((li) => {
    if (li.classList.contains("here")) {
      // A rule with one composed label on it, and beneath it the caveat about
      // what is under the rule — which is absent when nothing is.
      const [mark, caveat] = li.children;
      return {
        kind: "here",
        label: mark.textContent,
        // The label is one string on purpose, so the time is read back out of
        // it rather than out of a span that only exists for the test.
        when: mark.textContent.split(" · ").at(-1),
        caveat: caveat ? caveat.textContent : null,
      };
    }
    const show = part(li, "candidate-show");
    const what = part(li, "candidate-what");
    const hint = part(li, "candidate-hint");
    return {
      kind: li.classList.contains("ahead") ? "ahead" : "heard",
      when: part(li, "candidate-when").textContent,
      where: part(li, "candidate-where").textContent,
      // Null rather than "" so that a row whose words are withheld and a row
      // whose words happen to be empty cannot be mistaken for each other.
      what: what.hidden ? null : what.textContent,
      revealed: li.classList.contains("revealed"),
      // What the row offers to uncover, or nothing — which is both the state of
      // a row that has already been asked and the state of a row that never had
      // anything withheld.
      hint: hint && !hint.hidden ? hint.textContent : null,
      // The left of the row is a button only where there is something to ask
      // for. A press on the words of a place they have already heard must do
      // nothing at all, and the cheapest way to promise that is for there to be
      // nothing to press.
      asks: show.tagName === "BUTTON",
      goes: Boolean(part(li, "candidate-go")),
    };
  });
}

// Every string anywhere under the overlay, hidden nodes included. The guard's
// claim is not "the words are not visible" but "the words are not there" — a
// screen reader, a selection and a screenshot all reach text that is merely
// hidden, and only text that was never written reaches none of them.
//
// The three roots are walked separately because the fake document has no
// parents: index.html nests them, and here they are three elements the page was
// handed at boot.
function overlayText(page) {
  const found = [];
  const walk = (node) => {
    if (node.textContent) found.push(node.textContent);
    for (const child of node.children) walk(child);
  };
  for (const id of [
    "candidates",
    "candidates-book",
    "candidates-summary",
    "candidate-list",
  ]) {
    walk(page.el(id));
  }
  return found.join(" | ");
}

// Everything a night is, plus everything a night leaves behind. Cancel promises
// all of it back unchanged, so all of it is snapshotted.
function night(page) {
  return {
    probe: page.probe(),
    posts: page.posts.length,
    beacons: page.beacons.length,
    order: page.order.length,
    srcWrites: page.audio.srcWrites.length,
    fetches: page.fetches.length,
    currentTime: page.audio.currentTime,
    paused: page.audio.paused,
    playCalls: page.audio.playCalls,
  };
}

// ------------------------------------------------------------- raising the list

test("an answer with places in it puts them over the page", async (t) => {
  const page = await opened(t);
  page.answers({ reply: OFFER_SENTENCE, candidates: offer() });
  await page.ask("the bit where the horse goes down");
  assert.equal(page.asks.at(-1).question, "the bit where the horse goes down");
  // And which book it was asked about. Without this the agent sees the whole
  // shelf and nothing saying which book is making the sound, so "where was I"
  // comes back as "which book?" — asked over the book being listened to, every
  // turn. It travels with the question rather than being set up once, because
  // the page can open another book between two of them.
  assert.equal(page.asks.at(-1).gid, HALF_HEARD.gid);
  assert.equal(page.probe().candidatesUp, true);
  assert.equal(page.el("candidate-list").children.length, 5);
  // And the sentence is still an answer in the conversation underneath, which
  // is what a listener who cancels is left holding.
  const said = page.el("transcript").children.at(-1);
  assert.equal(said.textContent, OFFER_SENTENCE);
  assert.equal(said.className, "said agent");
});

test("an answer that knew where they meant moves the book and puts nothing up", async (t) => {
  const page = await opened(t);
  page.answers({
    reply: "Taking you there.",
    move: { gid: HALF_HEARD.gid, position_ms: 600_000, seq: 3 },
  });
  await page.ask("take me to the storm");
  // A confident single hit is unchanged behaviour on an unchanged code path:
  // the book moves and there is no overlay to get out of.
  assert.equal(page.probe().candidatesUp, false);
  assert.equal(page.probe().positionMs, 600_000);
  assert.equal(page.probe().seq, 3);
});

test("if a list and a move ever arrived together, the list wins", async (t) => {
  const page = await opened(t);
  // They cannot both arrive: the move_to tool refuses to run at all once a turn
  // has offered, and the server writes "move" only in the else of "candidates".
  // Two independent things would have to fail at once — and if they ever did,
  // the safe reading is that nothing has been moved under a listener who has
  // not chosen yet. A move that really happened comes back as the refusal of
  // the next report within fifteen seconds anyway.
  page.answers({
    reply: OFFER_SENTENCE,
    candidates: offer(),
    move: { gid: HALF_HEARD.gid, position_ms: 600_000, seq: 3 },
  });
  await page.ask("the bit with the cart");
  assert.equal(page.probe().candidatesUp, true);
  assert.equal(page.probe().positionMs, HALF_HEARD.position_ms);
  assert.equal(page.probe().seq, HALF_HEARD.seq);
});

test("an answer that is only words leaves the page alone", async (t) => {
  const page = await opened(t);
  page.answers({ reply: "Ginger is the chestnut mare in the next box." });
  await page.ask("who is ginger");
  assert.equal(page.probe().candidatesUp, false);
  assert.deepEqual(page.posts, []);
});

// ----------------------------------------------------------------- reading it

test("the places are in time order with where they are among them", async (t) => {
  const page = await opened(t);
  page.answers({ reply: OFFER_SENTENCE, candidates: offer() });
  await page.ask("the bit with the cart");
  assert.deepEqual(
    rows(page).map((row) => [row.when, row.kind]),
    [
      ["0:05:00", "heard"],
      // Spliced in among them and not stuck at the top: the whole of what the
      // list answers without reading a word is that everything below this line
      // has not happened yet.
      ["0:16:40", "here"],
      ["0:20:34", "heard"],
      ["0:30:00", "ahead"],
      ["0:40:00", "ahead"],
    ],
  );
  // One composed string on the rule, and under it the sentence the whole
  // arrangement exists to make legible.
  assert.equal(rows(page)[1].label, "you are here · 0:16:40");
  assert.equal(
    rows(page)[1].caveat,
    "anything below this line you may not have heard",
  );
});

test("the places screen says how many places and what they span", async (t) => {
  const page = await opened(t);
  page.answers({ reply: OFFER_SENTENCE, candidates: offer() });
  await page.ask("the bit with the cart");
  // Counted off the payload that drew the rows and nothing else. No
  // denominator: somnia has no idea how many places in this book would have
  // fitted the question, and a "of 7" nobody counted would be read and
  // believed.
  assert.equal(
    page.el("candidates-summary").textContent,
    "4 places between 0:05:00 and 0:40:00",
  );
});

test("one place is not counted as though there were more", async (t) => {
  const page = await opened(t);
  page.answers({
    reply: OFFER_SENTENCE,
    candidates: {
      gid: OTHER_BOOK.gid,
      title: OTHER_BOOK.title,
      position_ms: null,
      places: [elsewhere()],
    },
  });
  await page.ask("the bit in the other book");
  assert.equal(page.el("candidates-summary").textContent, "1 place, at 0:00:12");
});

test("the count goes when the list does", async (t) => {
  const page = await opened(t);
  page.answers({ reply: OFFER_SENTENCE, candidates: offer() });
  await page.ask("the bit with the cart");
  page.click("candidates-cancel");
  // A subhead left standing over an empty list is the page describing something
  // that is not there.
  assert.equal(page.el("candidates-summary").textContent, "");
});

test("a here time past every place is drawn at the bottom", async (t) => {
  const page = await opened(t);
  // Fifty minutes in, and both of the places are behind them.
  page.seek(3_000_000);
  page.answers({
    reply: OFFER_SENTENCE,
    candidates: offer({ places: places().slice(0, 2) }),
  });
  await page.ask("the bit with the cart");
  assert.deepEqual(
    rows(page).map((row) => row.kind),
    ["heard", "heard", "here"],
  );
  assert.equal(rows(page).at(-1).when, "0:50:00");
  // And nothing is said about what is below the line, because nothing is. A
  // warning about an empty screen is prose defending a thing that is not
  // there.
  assert.equal(rows(page).at(-1).caveat, null);
});

test("the position drawn for the open book is this page's, not the server's", async (t) => {
  const page = await playing(t);
  page.seek(1_500_000);
  page.audio.fire("seeked");
  await page.settle();
  // The server's copy is up to fifteen seconds behind, and the page is the
  // player: 0:16:40 is where this book was when the answer was composed, and
  // 0:25:00 is where the sound is.
  page.answers({ reply: OFFER_SENTENCE, candidates: offer() });
  await page.ask("the bit with the cart");
  const here = rows(page).find((row) => row.kind === "here");
  assert.equal(here.when, "0:25:00");
});

test("a book nobody has ever started gets no here row at all", async (t) => {
  const page = await opened(t);
  page.answers({
    reply: OFFER_SENTENCE,
    candidates: {
      gid: OTHER_BOOK.gid,
      title: OTHER_BOOK.title,
      position_ms: null,
      places: [elsewhere()],
    },
  });
  await page.ask("the bit in the other book");
  // "Never started" and "at 0:00:00" are different answers and only one of them
  // would be true.
  assert.deepEqual(
    rows(page).map((row) => row.kind),
    ["heard"],
  );
  // And which book it is, said once, because it is not the one they can hear.
  assert.equal(page.el("candidates-book").hidden, false);
  assert.equal(page.el("candidates-book").textContent, "in Another Book");
});

test("the book they are already listening to is not named at them", async (t) => {
  const page = await opened(t);
  page.answers({ reply: OFFER_SENTENCE, candidates: offer() });
  await page.ask("the bit with the cart");
  assert.equal(page.el("candidates-book").hidden, true);
});

// --------------------------------------------------------------- the guard

test("a place at the mark is ahead of them and the one before it is not", async (t) => {
  const page = await opened(t);
  page.answers({
    reply: OFFER_SENTENCE,
    candidates: offer({
      places: [
        // A millisecond short of the mark, and exactly on it. This is the whole
        // of the boundary: with `>` instead of `>=` the second of these would
        // paint the sentence they have not heard yet in the clear, and on a
        // book nobody has played a second of it would do it to every row.
        place(41, 1_799_999, RAIN_TEXT, BEHIND),
        place(42, 1_800_000, HIDDEN_TEXT, BEYOND),
      ],
    }),
  });
  await page.ask("the bit where the horse goes down");
  const [, before, at] = rows(page);
  // Behind it: the book's own words and the chapter they are in, on the screen
  // at once, because painting them leaks nothing they have not been told. There
  // is no line offering to reveal anything and nothing on the left to press —
  // everything that could be uncovered is already up.
  assert.deepEqual(
    [before.kind, before.where, before.what, before.hint, before.asks],
    ["heard", "Ch 1 · What They Have Heard", RAIN_TEXT, null, false],
  );
  // On it: the sentence they have not heard yet. Nothing of it is drawn — not
  // the words, and not the chapter title, which on a real book is itself a
  // spoiler. What is drawn is the time, the chapter number, the fact that it is
  // ahead, and what pressing would cost.
  assert.deepEqual(
    [at.kind, at.where, at.what, at.hint, at.asks],
    ["ahead", "Ch 2 · ahead", null, "tap to reveal · may spoil", true],
  );
  // And both of them can be gone to. The reveal is the row's other target and
  // never a substitute for this one.
  assert.deepEqual([before.goes, at.goes], [true, true]);
});

test("the words of a place they have not reached are not on the page at all", async (t) => {
  const page = await opened(t);
  page.answers({ reply: OFFER_SENTENCE, candidates: offer() });
  await page.ask("the bit where the horse goes down");
  const text = overlayText(page);
  assert.equal(text.includes(HEARD_TEXT), true);
  // Not hidden, not clamped, not off-screen: never written. A screen reader
  // cannot read out what was never put there, a selection cannot catch it and a
  // screenshot cannot contain it.
  assert.equal(text.includes(HIDDEN_TEXT), false);
  assert.equal(text.includes("What They Have Not"), false);
  // The element the words would go in exists and is empty. Hidden is not the
  // promise; empty is.
  const row = page.el("candidate-list").children[3];
  const shown = part(row, "candidate-what");
  assert.equal(shown.textContent, "");
  assert.equal(shown.hidden, true);
});

test("the page is told what is ahead and does not work it out", async (t) => {
  const page = await opened(t);
  page.answers({
    reply: OFFER_SENTENCE,
    candidates: offer({
      places: [
        // Behind the mark by twenty minutes and marked ahead anyway; and an
        // hour past the mark, marked heard. Whatever the page thinks it knows
        // about how far they have listened — and it holds a number that goes
        // stale within a chapter — its word is the only one there is.
        { ...place(31, 1000, HIDDEN_TEXT, BEHIND), ahead: true },
        { ...place(32, 3_000_000, HEARD_TEXT, BEYOND), ahead: false },
      ],
    }),
  });
  await page.ask("the bit with the cart");
  assert.deepEqual(
    rows(page)
      .filter((row) => row.kind !== "here")
      .map((row) => [row.kind, row.what]),
    [
      ["ahead", null],
      ["heard", HEARD_TEXT],
    ],
  );
  assert.equal(overlayText(page).includes(HIDDEN_TEXT), false);
});

test("the page holds no opinion about how far they have listened", () => {
  // Read off the disc rather than driven, because what this is about is a line
  // of code that must never be written. `ahead` is decided once, on the server,
  // by the code that owns the guard; a page that recomputed it would be a
  // second number able to disagree with the first, and it would disagree on
  // exactly the rows a mistake matters most on — the manifest's mark is stale
  // by construction, since an accepted report returns early and throws away the
  // fresh one, and on a finished book the page holds whatever it saw at boot
  // all night.
  const source = readFileSync(
    fileURLToPath(new URL("../../src/somnia/web/app.js", import.meta.url)),
    "utf8",
  );
  assert.equal(source.includes("heard_to_ms"), false);
});

test("showing a list moves nothing, plays nothing and says nothing was played", async (t) => {
  const page = await opened(t);
  const before = night(page);
  page.answers({ reply: OFFER_SENTENCE, candidates: offer() });
  await page.ask("the bit with the cart");
  const after = night(page);
  // Asking cost one request — the question itself — and the answer cost
  // nothing at all: no seek, no report, no source, nothing touched that the
  // spoiler guard measures.
  assert.equal(after.fetches - before.fetches, 1);
  assert.equal(after.posts, before.posts);
  assert.equal(after.order, before.order);
  assert.equal(after.srcWrites, before.srcWrites);
  // In particular showCandidates never seeks, so a page that was only ever
  // asked a question keeps its "nobody has started this book" and does not
  // turn it into 0:00:00.
  assert.equal(page.probe().untouched, true);
  assert.deepEqual(page.posts, []);
});

// --------------------------------------------------------------- the reveal

test("asking what is there fills in that row and nothing else", async (t) => {
  const page = await playing(t);
  page.answers({ reply: OFFER_SENTENCE, candidates: offer() });
  await page.ask("the bit where the horse goes down");
  page.click("candidate-show-13");
  const revealed = rows(page)[3];
  assert.deepEqual(
    [
      revealed.kind,
      revealed.where,
      revealed.what,
      revealed.revealed,
      revealed.hint,
    ],
    [
      "ahead",
      // The title arrives at the same press and never before it, and the word
      // "ahead" stays, because it still is.
      "Ch 2 · What They Have Not · ahead",
      HIDDEN_TEXT,
      true,
      // The warning has been heeded and is over.
      null,
    ],
  );
  // And the row below it is untouched, which is the difference between a reveal
  // and a change of mind about the whole list.
  assert.equal(rows(page)[4].what, null);
  assert.equal(rows(page)[4].hint, "tap to reveal · may spoil");
});

test("a second press on a revealed row does not put the words back", async (t) => {
  const page = await playing(t);
  page.answers({ reply: OFFER_SENTENCE, candidates: offer() });
  await page.ask("the bit where the horse goes down");
  page.click("candidate-show-13");
  const after = rows(page)[3];
  page.click("candidate-show-13");
  // A control whose meaning depends on how many times it has been pressed,
  // read by somebody who is not counting, is the wrong thing to hand a listener
  // at 2am — and the one direction it must never go in is back.
  assert.deepEqual(rows(page)[3], after);
  assert.equal(page.probe().revealed, 1);
});

test("finding out what is there does not move the book or tell anybody", async (t) => {
  const page = await playing(t);
  page.answers({ reply: OFFER_SENTENCE, candidates: offer() });
  await page.ask("the bit where the horse goes down");
  const before = night(page);
  page.click("candidate-show-13");
  await page.settle();
  const after = night(page);
  // The words came down with the answer and were already in hand, so there is
  // no request here to make — which is also why there is no endpoint anywhere
  // handing back unheard book text for a guessed chunk id.
  assert.equal(after.fetches, before.fetches);
  assert.equal(after.posts, before.posts);
  assert.equal(after.beacons, before.beacons);
  assert.equal(after.order, before.order);
  assert.equal(after.srcWrites, before.srcWrites);
  assert.equal(after.currentTime, before.currentTime);
  // Nothing the mark is measured against moved: the position, the count and the
  // playback that would raise heard_to_ms are all where they were, and there is
  // no reachable path from this press to a write.
  assert.deepEqual(after.probe, { ...before.probe, revealed: 1 });
});

test("the withheld words rest in one key and are said in none", async (t) => {
  const page = await playing(t);
  page.answers({ reply: OFFER_SENTENCE, candidates: offer() });
  await page.ask("the bit where the horse goes down");
  page.click("candidate-show-13");
  // They are written down now, and in exactly one place: the key Places keeps
  // the last query's list in, so that getting back to these four is a press
  // rather than the same question asked again over a tailnet at 2am. The words
  // came down with the answer, to this device, and what changed is that they
  // rest there between sessions instead of dying with the tab.
  //
  // Nowhere else, and that is what this asserts. Not a second copy somebody has
  // to remember to clear, and not the session storage, which holds the name of
  // the conversation and nothing about a book at all.
  const written = [...page.storage.items]
    .filter(([, value]) => value.includes(HIDDEN_TEXT))
    .map(([key]) => key);
  assert.deepEqual(written, ["somnia-places"]);
  assert.equal(
    [...page.storageSession.items.values()].some((value) =>
      value.includes(HIDDEN_TEXT),
    ),
    false,
  );
  // Nor into the conversation, which is the other thing on this page that
  // outlives the list. What is remembered is the answer, not the reading of it:
  // a page that comes back offers the same rows with the same words withheld,
  // and the reveal press is still the only thing that puts them on a screen.
  const said = page.el("transcript").children.map((line) => line.textContent);
  assert.equal(said.some((line) => line.includes(HIDDEN_TEXT)), false);
});

test("closing takes the revealed words away with the rest", async (t) => {
  const page = await playing(t);
  page.answers({ reply: OFFER_SENTENCE, candidates: offer() });
  await page.ask("the bit where the horse goes down");
  page.click("candidate-show-13");
  assert.equal(overlayText(page).includes(HIDDEN_TEXT), true);
  page.click("candidates-cancel");
  assert.equal(page.el("candidate-list").children.length, 0);
  assert.equal(overlayText(page).includes(HIDDEN_TEXT), false);
  assert.equal(page.probe().revealed, 0);
});

// ------------------------------------------------------------- choosing a row

test("a row goes to the millisecond it names and plays it", async (t) => {
  const page = await opened(t);
  page.answers({ reply: OFFER_SENTENCE, candidates: offer() });
  await page.ask("the bit with the cart");
  const srcWrites = page.audio.srcWrites.length;
  const from = page.order.length;
  page.click("candidate-go-12");
  await page.settle();
  // First the list goes, so nothing can leave a list of places over a book that
  // has already gone to one of them.
  assert.equal(page.probe().candidatesUp, false);
  // To the millisecond the row named, and not to the second it was drawn as.
  assert.equal(page.probe().positionMs, 1_234_567);
  // Within the chapter already loaded: one write to the element's clock and no
  // second source. A seek on a live element needs no permission at all, which
  // is what keeps the autoplay policy out of the common case.
  assert.equal(page.audio.currentTime, 1234.567);
  assert.equal(page.audio.srcWrites.length, srcWrites);
  // Reproducing "now press play yourself" in JavaScript would be a joke.
  assert.deepEqual(page.order.slice(from), ["play", "state:playing"]);
  assert.equal(page.audio.paused, false);
  // And it says so once, at the bottom of the screen near the thumb that did
  // it. The screen it was said on has gone, so there is nowhere else it could
  // be said.
  assert.equal(page.probe().toast, "moved · playing");
});

test("the move is announced on the seek and not on a timer", async (t) => {
  const page = await opened(t);
  page.answers({ reply: OFFER_SENTENCE, candidates: offer() });
  await page.ask("the bit with the cart");
  const waits = page.waits().length;
  page.click("candidate-go-12");
  // Nothing was scheduled to make it true later. The design's prototype waits
  // ~900ms and then says this, and on a real page that window is long enough
  // for the agent to move the book by the other route — the refusal of the next
  // report — after which the sentence would be about a press whose effect had
  // been overwritten. The only wake asked for is the toast taking itself off.
  assert.deepEqual(page.waits().slice(waits), [2800]);
  assert.equal(page.probe().positionMs, 1_234_567);
  assert.equal(page.probe().toast, "moved · playing");
});

test("a move that arrived by the other route says nothing about a press", async (t) => {
  const page = await playing(t);
  page.answers({ reply: OFFER_SENTENCE, candidates: offer() });
  await page.ask("the bit with the cart");
  // The agent moved the book itself, which is how a move that really happened
  // always arrives in the end. Nobody pressed `goto`, so nothing is owed a
  // sentence about what their press did.
  page.reply({
    accepted: false,
    gid: HALF_HEARD.gid,
    position_ms: 2_000_000,
    seq: 3,
    reason: "moved",
  });
  page.tick(15_000);
  page.audio.advance(0.5);
  await page.settle();
  assert.equal(page.probe().positionMs, 2_000_000);
  assert.equal(page.probe().toast, "");
});

test("a chosen row is reported as the seek it is, and bumps no count", async (t) => {
  const page = await playing(t);
  page.answers({ reply: OFFER_SENTENCE, candidates: offer() });
  await page.ask("the bit with the cart");
  page.posts.length = 0;
  page.click("candidate-go-12");
  page.audio.fire("seeked");
  await page.settle();
  // No server move, no new endpoint, no invented count: the page keeps the seq
  // it holds and the server hears about it by the route every other seek takes.
  // A fabricated one would either do nothing at all or leave this page holding
  // a number the database has never had, after which every report for the rest
  // of the night is refused and the refusal drags them backwards.
  assert.deepEqual(page.reports(), [[HALF_HEARD.gid, "seek", 1_234_567]]);
  assert.equal(page.posts[0].body.seq, HALF_HEARD.seq);
  // And nothing played to get there. A jump moves the position and not the
  // playback, which is the whole of what the mark is measured against.
  assert.equal(page.posts[0].body.played_ms, 0);
});

test("choosing a place they have not heard raises the mark only by what then plays", async (t) => {
  const page = await playing(t);
  page.answers({ reply: OFFER_SENTENCE, candidates: offer() });
  await page.ask("the bit where the horse goes down");
  page.click("candidate-show-13");
  page.posts.length = 0;
  page.click("candidate-go-13");
  await page.settle();
  // A place they have never played, arrived at — inside the book already
  // loaded, so there is nothing to fetch and nothing to wait for.
  page.audio.arrived();
  for (let turn = 0; turn < 3; turn++) await page.settle();
  assert.equal(page.probe().positionMs, 1_800_000);
  // Not one millisecond of it is claimed as listened to. Going somewhere is not
  // hearing it, and this is the direction the guard exists for.
  assert.equal(page.posts.length > 0, true);
  for (const post of page.posts) assert.equal(post.body.played_ms, 0);
  // The other direction, which the same file has to prove: a guard that never
  // rises is not a fix. Three seconds of book really come out of the speaker
  // and the next report says so — two of them, because the first sample after
  // a jump is the baseline the rest are measured from and nobody heard the
  // ground behind it.
  page.posts.length = 0;
  page.audio.advance(1);
  page.audio.advance(1);
  page.tick(15_000);
  page.audio.advance(1);
  await page.settle();
  assert.equal(page.posts.length, 1);
  assert.deepEqual(
    [page.posts[0].body.reason, page.posts[0].body.played_ms],
    ["tick", 2000],
  );
  assert.equal(page.posts[0].body.position_ms, 1_803_000);
});

test("a row in another book opens that book and lands in the right place", async (t) => {
  const page = await playing(t);
  page.answers({
    reply: OFFER_SENTENCE,
    candidates: {
      gid: OTHER_BOOK.gid,
      title: OTHER_BOOK.title,
      position_ms: OTHER_BOOK.position_ms,
      places: [elsewhere()],
    },
  });
  await page.ask("the bit in the other book");
  const from = page.order.length;
  const srcWrites = page.audio.srcWrites.length;
  page.click("candidate-go-21");
  for (let turn = 0; turn < 3; turn++) await page.settle();
  page.audio.ready();
  assert.equal(page.probe().gid, OTHER_BOOK.gid);
  // The chosen place, and not the 0:00:04 that book was last left at: nothing
  // has been written to it, so `at` is the only thing carrying the choice
  // through the switch.
  assert.equal(page.probe().positionMs, 12_000);
  assert.equal(page.probe().seq, OTHER_BOOK.seq);
  assert.equal(page.probe().clock, "0:00:12 of 0:00:16");
  // One source and one notification for one press. Another book is the one
  // press that does still load something — it is a different book, so a
  // different file — and seeking after the load instead of before it would show
  // the chapter twice and build the media notification twice.
  assert.deepEqual(page.audio.srcWrites.slice(srcWrites), [
    "api/stream/900002/2",
  ]);
  assert.deepEqual(
    page.order.slice(from).filter((step) => step.startsWith("metadata:")),
    ["metadata:Elsewhere Two"],
  );
  assert.equal(page.audio.paused, false);
  assert.equal(page.probe().toast, "moved · playing");
});

test("a row in a book that has not been read yet moves nothing and says so", async (t) => {
  const page = await playing(t);
  page.answers({
    reply: OFFER_SENTENCE,
    candidates: {
      gid: RENDERING_BOOK.gid,
      title: RENDERING_BOOK.title,
      position_ms: null,
      places: [{ ...elsewhere(), chunk_id: 31 }],
    },
  });
  await page.ask("the bit in the book being read");
  page.click("candidate-go-31");
  for (let turn = 0; turn < 3; turn++) await page.settle();
  // The book has rows and no audio, so openBook adopts nothing and this page is
  // still on the book it was on. "moved · playing" over a book that did not
  // move is the one thing a toast must never say — the standing sentence on the
  // status line is the true one, and it is the only thing said.
  assert.equal(page.probe().gid, HALF_HEARD.gid);
  assert.equal(page.probe().toast, "");
  assert.equal(page.probe().status, "the first chapter is still being read");
});

// --------------------------------------------------- back to the book it moved

// The screen a question is asked on is not the screen its answer is about. A
// question moves the book, and the book is on the player — so the last thing
// every route through here does is put the page back on it, and none of them
// used to.
//
// It was hidden for as long as it was because one route does it by accident:
// raising the list blurs the composer, a blur is the way off the chat screen,
// and a question typed with a keyboard up therefore landed back on the player
// without anybody having written that down. The microphone takes no focus, so
// there was no blur to ride, and a question asked by voice ended with the book
// moved and the conversation still over it. `follow` had neither — a single hit
// moves the book with no list to raise and no blur to fire, so a typed search
// that found one place left the page on the transcript too.
//
// So it is said once, by name, at both places where a question moves a book.

// A question asked out loud: the finger goes down on the microphone and nothing
// else happens to the page. No focus, no keyboard, nothing to measure — which is
// what made this the route the accident never covered.
function askedByVoice(page) {
  page.touch("talk");
  assert.equal(page.probe().screen, "chat");
}

// And the same question typed, with a keyboard up over it. `page.ask` fires the
// composer's submit and no browser is here to move focus for it, so this is the
// state a real phone is in at the moment the answer lands.
function askedByTyping(page) {
  page.touch("question");
  page.focus("question");
  page.resize(WITH_KEYBOARD);
  assert.equal(page.probe().screen, "chat");
}

for (const [how, arrive] of [
  ["by voice", askedByVoice],
  ["by typing", askedByTyping],
]) {
  test(`a row chosen after a question asked ${how} lands back on the book`, async (t) => {
    const page = await opened(t);
    page.answers({ reply: OFFER_SENTENCE, candidates: offer() });
    arrive(page);
    await page.ask("the bit with the cart");
    page.click("candidate-go-12");
    await page.settle();
    assert.equal(page.probe().positionMs, 1_234_567);
    // The book moved, so the book is what is on the screen. A page left on the
    // transcript here is a seek somebody made and cannot see the result of.
    assert.equal(page.probe().screen, "player");
    assert.equal(page.probe().keyboardUp, false);
  });

  test(`a single hit after a question asked ${how} lands back on the book`, async (t) => {
    const page = await opened(t);
    page.answers({
      reply: "Taking you there.",
      move: { gid: HALF_HEARD.gid, position_ms: 600_000, seq: 3 },
    });
    arrive(page);
    await page.ask("take me to the storm");
    assert.equal(page.probe().positionMs, 600_000);
    // No list was ever raised, so there is no close and no blur to arrive by
    // accident. This is the route that was wrong on both ways of asking.
    assert.equal(page.probe().candidatesUp, false);
    assert.equal(page.probe().screen, "player");
    assert.equal(page.probe().keyboardUp, false);
  });
}

// A row in another book is the same claim: the page went somewhere, and where it
// went is on the player.
test("a row in another book lands back on the book as well", async (t) => {
  const page = await opened(t);
  page.answers({
    reply: OFFER_SENTENCE,
    candidates: {
      gid: OTHER_BOOK.gid,
      title: OTHER_BOOK.title,
      position_ms: null,
      places: [elsewhere()],
    },
  });
  askedByVoice(page);
  await page.ask("the bit in the other book");
  page.click("candidate-go-21");
  for (let turn = 0; turn < 3; turn++) await page.settle();
  assert.equal(page.probe().gid, OTHER_BOOK.gid);
  assert.equal(page.probe().screen, "player");
});

// The other half of the rule, and the half that keeps it from being a page that
// throws people off the conversation for asking a question. Only a book that
// moved may take the screen; an answer made of words is a turn in a conversation
// somebody is in the middle of having.
test("an answer that only says something leaves them on the conversation", async (t) => {
  const page = await opened(t);
  page.answers({ reply: "Ginger is the chestnut mare in the next box." });
  askedByVoice(page);
  await page.ask("who is ginger");
  assert.equal(page.probe().screen, "chat");
});

// A list raised by voice is a list over the conversation, and closing it puts
// the conversation back. `close` is the one way out that promises to change
// nothing, and the screen underneath is one of the things it must not change —
// somebody who looked at four places and decided against all of them is still in
// the middle of asking.
test("closing the places leaves the screen it was raised over", async (t) => {
  const page = await opened(t);
  page.answers({ reply: OFFER_SENTENCE, candidates: offer() });
  askedByVoice(page);
  await page.ask("the bit with the cart");
  assert.equal(page.probe().screen, "chat");
  page.click("candidates-cancel");
  assert.equal(page.probe().screen, "chat");
});

// And a move that nobody on this page just asked for may not take the screen
// either. The refusal of the next report is how the agent moves a book by
// itself, it can land fifteen seconds into the question after the one that
// caused it, and a page that changed screens on it would take the keyboard away
// from somebody mid-sentence.
test("a move arriving by the other route leaves the screen alone", async (t) => {
  const page = await playing(t);
  askedByTyping(page);
  page.reply({
    accepted: false,
    gid: HALF_HEARD.gid,
    position_ms: 2_000_000,
    seq: 3,
    reason: "moved",
  });
  page.tick(15_000);
  page.audio.advance(0.5);
  await page.settle();
  assert.equal(page.probe().positionMs, 2_000_000);
  assert.equal(page.probe().screen, "chat");
});

// -------------------------------------------------------------------- cancel

test("cancel leaves a night that never started exactly as it found it", async (t) => {
  const page = await opened(t);
  const before = night(page);
  page.answers({ reply: OFFER_SENTENCE, candidates: offer() });
  await page.ask("the bit with the cart");
  assert.equal(page.probe().candidatesUp, true);
  const raised = night(page);
  page.click("candidates-cancel");
  const after = night(page);
  assert.deepEqual(after.probe, before.probe);
  assert.equal(after.posts, before.posts);
  assert.equal(after.beacons, before.beacons);
  assert.equal(after.order, before.order);
  assert.equal(after.srcWrites, before.srcWrites);
  // And it asked nothing of anybody on the way out: three assignments and, at
  // most, one listener put back.
  assert.equal(after.fetches, raised.fetches);
  // A book that was only ever opened is still a book that was only ever opened.
  assert.equal(page.probe().untouched, true);
  assert.deepEqual(page.posts, []);
  await page.settle();
  page.tick(60_000);
  await page.settle();
  assert.deepEqual(page.probe(), before.probe);
  assert.deepEqual(page.posts, []);
  assert.deepEqual(page.beacons, []);
});

test("cancel leaves a fade that was already running still running", async (t) => {
  const page = await playing(t, { stored: armed(1, 25_000) });
  listen(page, 6000);
  assert.equal(page.probe().fading, true);
  const before = night(page);
  assert.equal(before.probe.volume < 1, true);
  page.answers({ reply: OFFER_SENTENCE, candidates: offer() });
  await page.ask("the bit with the cart");
  const raised = night(page);
  page.click("candidates-cancel");
  const after = night(page);
  assert.equal(after.fetches, raised.fetches);
  // The night was already ending. A question about where to go did not change
  // that, so putting the question away must not change it either — not the
  // fade, not the volume it had reached, and not the minutes left on the timer,
  // which have been counting the whole time because the book was playing and
  // they were listening to it.
  assert.deepEqual(after.probe, before.probe);
  assert.equal(after.probe.fading, true);
  assert.equal(after.probe.sleepLeftMs, before.probe.sleepLeftMs);
  assert.equal(after.posts, before.posts);
  assert.equal(after.beacons, before.beacons);
  assert.equal(after.order, before.order);
  assert.equal(after.srcWrites, before.srcWrites);
  assert.equal(after.currentTime, before.currentTime);
  assert.equal(after.playCalls, before.playCalls);
  await page.settle();
  page.tick(1000);
  await page.settle();
  assert.deepEqual(page.probe(), before.probe);
  assert.equal(page.posts.length, before.posts);
});

test("cancel gives back the tap the list took away", async (t) => {
  const page = await opened(t);
  // The app was backgrounded and the platform refused the sound until it is
  // touched: the real 2am sequence this refactor exists for.
  page.audio.refuse = "NotAllowedError";
  page.click("playpause");
  await page.settle();
  assert.equal(page.probe().status, "tap anywhere to carry on");
  const playCalls = page.audio.playCalls;

  page.answers({ reply: OFFER_SENTENCE, candidates: offer() });
  await page.ask("the bit with the cart");
  // With the listener still armed, the first press anywhere on this overlay —
  // a row, a reveal, or cancel itself — would have started the book. Cancel
  // especially: the one control that promises to change nothing.
  page.document.fire("pointerdown");
  assert.equal(page.audio.playCalls, playCalls);
  assert.equal(page.audio.paused, true);

  page.click("candidates-cancel");
  // True before the list went up and true again now, and the line that says so
  // came back with the listener rather than being left lying.
  assert.equal(page.probe().status, "tap anywhere to carry on");
  page.audio.refuse = null;
  page.document.fire("pointerdown");
  await page.settle();
  assert.equal(page.audio.paused, false);
});

// -------------------------------------------------- the list is never left up

test("a move arriving while they are still reading takes the list down", async (t) => {
  const page = await playing(t);
  page.answers({ reply: OFFER_SENTENCE, candidates: offer() });
  await page.ask("the bit with the cart");
  assert.equal(page.probe().candidatesUp, true);
  // The agent moved the book by the other route: the refusal of the next
  // report, which is how a move that really happened always arrives in the end.
  page.reply({
    accepted: false,
    gid: HALF_HEARD.gid,
    position_ms: 2_000_000,
    seq: 3,
    reason: "moved",
  });
  page.tick(15_000);
  page.audio.advance(0.5);
  await page.settle();
  // A list left over a book that has since moved offers rows whose "you are
  // here" is a lie, and the next press acts on it.
  assert.equal(page.probe().candidatesUp, false);
  assert.equal(page.probe().positionMs, 2_000_000);
  assert.equal(page.el("candidate-list").children.length, 0);
});

test("a thumb on the transport takes the list down too", async (t) => {
  const page = await playing(t);
  page.answers({ reply: OFFER_SENTENCE, candidates: offer() });
  await page.ask("the bit with the cart");
  page.click("back30");
  assert.equal(page.probe().candidatesUp, false);
});

test("asking again puts the last answer's list away first", async (t) => {
  const page = await opened(t);
  page.answers({ reply: OFFER_SENTENCE, candidates: offer() });
  await page.ask("the bit with the cart");
  page.answers({ reply: "I couldn't find that." });
  await page.ask("no, the other one");
  // The rows would have been an answer to the question above the one they are
  // looking at.
  assert.equal(page.probe().candidatesUp, false);
  assert.equal(page.el("candidate-list").children.length, 0);
});

test("starting over leaves no list over the cleared conversation", async (t) => {
  const page = await opened(t);
  page.answers({ reply: OFFER_SENTENCE, candidates: offer() });
  await page.ask("the bit with the cart");
  page.click("restart");
  await page.settle();
  // An overlay offering places, with nothing behind it to say what was asked or
  // why, is exactly the stranding this page promises cannot happen.
  assert.equal(page.probe().candidatesUp, false);
  assert.equal(overlayText(page).includes(HEARD_TEXT), false);
});

test("a list about a book that has gone is taken down with it", async (t) => {
  const page = await playing(t);
  page.answers({ reply: OFFER_SENTENCE, candidates: offer() });
  await page.ask("the bit with the cart");
  page.reply({ accepted: false, gid: HALF_HEARD.gid, reason: "gone" });
  page.tick(15_000);
  page.audio.advance(0.5);
  await page.settle();
  // Every row would fetch a book that has been deleted and come back with
  // "couldn't reach that book".
  assert.equal(page.probe().status, "that book isn't here any more");
  assert.equal(page.probe().candidatesUp, false);
});

test("opening a book really takes the list down with it", async (t) => {
  const page = await playing(t);
  page.answers({ reply: OFFER_SENTENCE, candidates: offer() });
  await page.ask("the bit with the cart");
  assert.equal(page.probe().candidatesUp, true);
  // The other book is adopted, so the rows — and the "you are here" among them
  // — are about a book that is not on the screen any more.
  await page.openBook(OTHER_BOOK.gid);
  assert.equal(page.probe().gid, OTHER_BOOK.gid);
  assert.equal(page.probe().candidatesUp, false);
  assert.equal(page.el("candidate-list").children.length, 0);
  assert.equal(overlayText(page).includes(HEARD_TEXT), false);
});

// ------------------------------------------ and never taken down by a timer

test("the poll for a book still being read leaves a list alone", async (t) => {
  // Booted onto the only book in the library, which has no audio yet: the page
  // holds no book at all and is asking again every few seconds for the first
  // chapter. It is the one state in which every list that can appear is about
  // some other book — and the state the retry ladders run in.
  const page = await boot(t, { lastGid: RENDERING_BOOK.gid });
  assert.equal(page.probe().gid, null);
  assert.equal(page.probe().status, "the first chapter is still being read");

  page.answers({
    reply: OFFER_SENTENCE,
    candidates: offer({ places: [places()[0], places()[2]] }),
  });
  await page.ask("the bit with the cart");
  const before = rows(page);
  assert.equal(page.probe().candidatesUp, true);

  // The network coming back, which is the fastest of the several things that
  // ask again: the visibility change when the phone is unlocked and the five,
  // ten and twenty second waits all arrive down the same path. None of them is
  // somebody doing something, and a poll that found no new chapter has nothing
  // to say to a list somebody is in the middle of reading.
  page.window.fire("online");
  for (let turn = 0; turn < 4; turn++) await page.settle();
  assert.equal(page.probe().gid, null);
  assert.equal(page.probe().candidatesUp, true);
  assert.deepEqual(rows(page), before);

  // Still whole, not merely still up: the words a reveal press exists to hand
  // over are held beside the rows, and a list torn down and left on the screen
  // would have lost them.
  page.click("candidate-show-13");
  assert.equal(rows(page)[2].what, HIDDEN_TEXT);
});

// ------------------------------------------------- the places from last time
//
// Places is the last query's results and nothing else. Somnia produces that
// list once, in answer to a question asked in the dark, and until now it lived
// as long as the overlay did: a page discarded in a pocket came back with
// nothing, and getting to the third of four places meant asking the same
// question again, of a model, over a tailnet, at 2am.
//
// So the list is written down. Everything below is about the three ways that
// can be got wrong: a list restored as markup that does nothing when pressed, a
// list about a book nobody is listening to, and anything at all in that key
// stopping the page from opening.

test("the places a question put up are written down", async (t) => {
  const page = await opened(t);
  page.answers({ reply: OFFER_SENTENCE, candidates: offer() });
  await page.ask("the bit with the cart");
  const saved = JSON.parse(page.storage.items.get("somnia-places"));
  // Which book, and which places, in the order they were drawn in. The gid is
  // what makes this one entry rather than a growing pile: places about a book
  // that is not open are no places at all.
  assert.equal(saved.gid, HALF_HEARD.gid);
  assert.deepEqual(
    saved.places.map((place) => place.chunk_id),
    [11, 12, 13, 14],
  );
});

test("closing the screen leaves the places to come back to", async (t) => {
  const page = await opened(t);
  page.answers({ reply: OFFER_SENTENCE, candidates: offer() });
  await page.ask("the bit with the cart");
  page.click("candidates-cancel");
  assert.equal(page.probe().candidatesUp, false);
  // Close puts the screen away and forgets what was on it. What it must not do
  // is throw away the answer behind it: the list is the thing that cost a
  // question, and the screen is only a way of reading it.
  page.openPlaces();
  assert.equal(page.probe().candidatesUp, true);
  assert.equal(page.el("candidate-list").children.length, 5);
});

test("a page discarded overnight offers the last query's places again", async (t) => {
  const page = await opened(t, { stored: kept(offer()) });
  // Nothing is on the screen at boot: the page opens on the book, as it always
  // has, and the places are something to be asked for.
  assert.equal(page.probe().candidatesUp, false);
  page.openPlaces();
  assert.deepEqual(
    rows(page).map((row) => [row.when, row.kind]),
    [
      ["0:05:00", "heard"],
      ["0:16:40", "here"],
      ["0:20:34", "heard"],
      ["0:30:00", "ahead"],
      ["0:40:00", "ahead"],
    ],
  );
  // Drawn against where this page is now, not against the position the answer
  // was composed at: the rule goes where the book has got to tonight.
  assert.equal(rows(page)[1].label, "you are here · 0:16:40");
});

test("a place restored from storage is one a thumb can act on", async (t) => {
  const page = await opened(t, { stored: kept(offer()) });
  page.openPlaces();
  page.click("candidate-go-12");
  await page.settle();
  // The whole of why the list is restored into the variable the page chooses
  // from and not into the markup. chooseCandidate opens with `const list =
  // offered; if (!list) return;`, so a screen of rows rebuilt as markup would
  // look exactly like this one and do nothing at all when pressed - at 2am,
  // with no way to tell why.
  assert.equal(page.probe().candidatesUp, false);
  assert.equal(page.probe().positionMs, 1_234_567);
  assert.equal(page.audio.paused, false);
  assert.equal(page.probe().toast, "moved · playing");
});

test("places kept overnight still keep their words back until the press", async (t) => {
  const page = await opened(t, { stored: kept(offer()) });
  page.openPlaces();
  // The guard does not weaken by being slept on. Restoring goes through the
  // same path the answer took, so the words of a place they have not reached
  // are held beside the row rather than written into it.
  const text = overlayText(page);
  assert.equal(text.includes(HEARD_TEXT), true);
  assert.equal(text.includes(HIDDEN_TEXT), false);
  assert.equal(text.includes("What They Have Not"), false);
  page.click("candidate-show-13");
  assert.equal(rows(page)[3].what, HIDDEN_TEXT);
});

test("places about another book are no places for this one", async (t) => {
  const page = await opened(t, {
    stored: kept({
      gid: OTHER_BOOK.gid,
      title: OTHER_BOOK.title,
      position_ms: OTHER_BOOK.position_ms,
      places: [elsewhere()],
    }),
  });
  page.openPlaces();
  // The screen is scoped to the book being listened to. A list about somewhere
  // else is not a wrong list, it is the answer to a question about another
  // book - and there is nothing on the player to say so.
  assert.equal(page.probe().candidatesUp, false);
  assert.equal(page.el("candidate-list").children.length, 0);
});

test("anything else in that key is no places, and the page still opens", async (t) => {
  // A write cut off by the tab being killed, a record from a shape this page
  // has never had, and a list with a row missing the number a press acts on.
  // The page opening is the one thing that must survive all of them: it is the
  // only transport in the room, and there is no screen yet to say anything on.
  for (const rubbish of [
    "{",
    "null",
    '{"gid":900005}',
    '{"gid":900005,"places":[]}',
    '{"gid":900005,"places":[{"start_ms":300000,"chapter_idx":0}]}',
    '{"gid":"900005","places":[{"start_ms":1,"chunk_id":1,"chapter_idx":0}]}',
  ]) {
    const page = await opened(t, { stored: { "somnia-places": rubbish } });
    assert.equal(page.probe().gid, HALF_HEARD.gid);
    assert.equal(page.probe().clock, "0:16:40 of 1:00:00");
    page.openPlaces();
    assert.equal(page.probe().candidatesUp, false);
  }
});

// ------------------------------------------------- the position line as a way in
//
// The line under the book's title reads `1:12:08 of 9:41:33` on every night,
// and on the nights there are places it is also the way back to them. What is
// asserted here is mostly the other half of that: with nothing to open it is
// the plain readout it always was, because a line wearing a rule and a target
// that answers a press by doing nothing is the thing this page's comments argue
// against most often — and after a cold launch on a book nobody has asked about
// it is the ordinary case, not an edge one.

// What the line is offering, read the way somebody looking at it would: the
// count if there is one, and whether the whole thing is a control at all.
function line(page) {
  const found = page.el("places-found");
  return {
    // The position itself, which is what this line is for and what must not
    // change whatever else does.
    clock: page.el("clock").textContent,
    // Null rather than "" so that a count nobody can see and a count that
    // happens to be empty cannot be mistaken for each other.
    found: found.hidden ? null : found.textContent,
    // Emptied as well as hidden: two ways of asking "is anything offered?" that
    // could disagree is one too many.
    written: found.textContent,
    opens: !page.el("places-open").disabled,
    // The dotted rule, which is the only thing on the line that says it can be
    // pressed. It is a class because the sheet draws it, and because "does it
    // look pressable?" and "is there anything to press?" have to be the same
    // question.
    ruled: page.el("places-open").classList.contains("openable"),
  };
}

test("a book nobody has asked about leaves the position line alone", async (t) => {
  const page = await opened(t);
  assert.deepEqual(line(page), {
    clock: "0:16:40 of 1:00:00",
    found: null,
    written: "",
    opens: false,
    ruled: false,
  });
});

test("a list found puts a count under the position and opens from it", async (t) => {
  const page = await opened(t);
  page.answers({ reply: OFFER_SENTENCE, candidates: offer() });
  await page.ask("the bit with the cart");
  page.click("candidates-cancel");
  // Said as a fact about the last question rather than as an instruction, and
  // the position it is under is untouched.
  assert.deepEqual(line(page), {
    clock: "0:16:40 of 1:00:00",
    found: "4 places found",
    written: "4 places found",
    opens: true,
    ruled: true,
  });
  page.click("places-open");
  assert.equal(page.probe().candidatesUp, true);
  assert.equal(page.el("candidate-list").children.length, 5);
  // And it is the same screen, not a picture of one: the rows can be gone to.
  page.click("candidate-go-12");
  await page.settle();
  assert.equal(page.probe().positionMs, 1_234_567);
});

test("one place found is said in the singular, as the screen says it", async (t) => {
  const page = await opened(t, {
    stored: kept(offer({ places: [places()[0]] })),
  });
  assert.equal(line(page).found, "1 place found");
});

test("a night that comes back offers the places without a question", async (t) => {
  const page = await opened(t, { stored: kept(offer()) });
  // The count is on the line before anything is asked, which is the whole of
  // what the last night left behind.
  assert.equal(line(page).found, "4 places found");
  page.click("places-open");
  assert.equal(page.probe().candidatesUp, true);
});

test("places found in another book leave this book's line plain", async (t) => {
  const page = await opened(t);
  page.answers({
    reply: OFFER_SENTENCE,
    candidates: {
      gid: OTHER_BOOK.gid,
      title: OTHER_BOOK.title,
      position_ms: null,
      places: [elsewhere()],
    },
  });
  await page.ask("the bit in the other book");
  page.click("candidates-cancel");
  // The line is under the title of the book that is playing, and the places are
  // in one that is not. A count there would be a promise about this book.
  assert.equal(line(page).found, null);
  assert.equal(line(page).opens, false);
  page.click("places-open");
  assert.equal(page.probe().candidatesUp, false);
});

test("the count goes with the book it was about", async (t) => {
  const page = await playing(t);
  page.answers({ reply: OFFER_SENTENCE, candidates: offer() });
  await page.ask("the bit with the cart");
  page.click("candidates-cancel");
  assert.equal(line(page).found, "4 places found");
  await page.openBook(OTHER_BOOK.gid);
  page.audio.ready();
  // Another book, and the places were about the last one. Left standing, the
  // count would be four places in a book that is no longer on the screen.
  assert.deepEqual(line(page), {
    clock: "0:00:04 of 0:00:16",
    found: null,
    written: "",
    opens: false,
    ruled: false,
  });
});

test("an answer that knew where they meant leaves the last places standing", async (t) => {
  const page = await opened(t, { stored: kept(offer()) });
  page.answers({
    reply: "Taking you there.",
    move: { gid: HALF_HEARD.gid, position_ms: 600_000, seq: 3 },
  });
  await page.ask("take me to the storm");
  assert.equal(page.probe().positionMs, 600_000);
  // A confident move offered nothing, so there is nothing new to remember and
  // the last real list is still the last real list. Clearing it here would mean
  // one question somnia happened to be sure about threw away the answer to the
  // one before it.
  page.openPlaces();
  assert.equal(page.probe().candidatesUp, true);
  assert.equal(page.el("candidate-list").children.length, 5);
});

// `start over` is the one press that throws something away, and what it throws
// away is everything that was said. The places were an answer to something
// said, so they go too — otherwise the position line keeps offering a way back
// to a list whose question has been forgotten at both ends of the tailnet.
//
// Not the same case as a confident move, which leaves the list standing on
// purpose: there the conversation is still on the screen to explain it.
test("start over takes the remembered places with the conversation", async (t) => {
  const page = await opened(t);
  page.answers({ reply: OFFER_SENTENCE, candidates: offer() });
  await page.ask("the bit with the cart");
  page.click("candidates-cancel");
  assert.equal(line(page).found, "4 places found");

  page.click("restart");

  // The line is plain again: no count, no rule, and nothing to press.
  assert.deepEqual(line(page), {
    clock: "0:16:40 of 1:00:00",
    found: null,
    written: "",
    opens: false,
    ruled: false,
  });
  assert.equal(page.storage.items.get("somnia-places"), undefined);
});
