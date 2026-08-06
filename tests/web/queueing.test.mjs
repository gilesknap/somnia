// The books panel.
//
// The one screen has gained a second overlay, and the argument for it is
// weaker than the argument for the first: a list of places answers a question
// the listener just asked, whereas this is a thing somebody goes looking for.
// So it is held to the same three promises the list is held to, and to two more
// of its own.
//
// The three: the book plays underneath it, nothing has moved while it is up,
// and `close` puts it away having changed nothing at all — including the tap
// that a refused play was waiting for, which the panel borrows and gives back.
//
// The two: it adds books and never opens one, so ADR 3's "changing books is
// done by asking" survives literally; and it costs nothing when nobody is
// looking at it, which means no request before it is opened, no wake after it
// is closed, and no wake at all while the page is in somebody's pocket.
//
// Everything below is about those five. The words on the rows get one test each
// because they are the whole of what the panel is for — at 2am the difference
// between "not responding" and "chapter 4 of 39" is the difference between
// getting up and going back to sleep.

import assert from "node:assert/strict";
import { test } from "node:test";

import { boot, HALF_HEARD, PART_READ, TONE_BOOK } from "./harness.mjs";

// How often the panel asks, in the page's own units. Named here so that a test
// which asserts the wake and a test which fires it cannot drift apart.
const POLL_MS = 5000;

// How long the first press of `stop reading this` stands, before the button
// forgets it was ever asked.
const CONFIRM_MS = 5000;

// A rendering job, as queue.view hands one over: chapters counted from the
// chapters table, a total that is 0 until the parse wrote it down, and a
// `responding` derived from a heartbeat the page never sees.
function job(overrides = {}) {
  return {
    id: 1,
    gid: 271,
    title: "Black Beauty",
    authors: "Anna Sewell",
    state: "rendering",
    place: 0,
    chapters_done: 3,
    chapters_total: 39,
    rendered_ms: 4_320_000,
    stopping: false,
    responding: true,
    error: "",
    submitted_at: "2026-08-06 21:00:00",
    started_at: "2026-08-06 21:00:10",
    ...overrides,
  };
}

function waiting(overrides = {}) {
  return job({
    id: 2,
    gid: 120,
    title: "Treasure Island",
    authors: "Robert Louis Stevenson",
    state: "queued",
    place: 1,
    chapters_done: 0,
    chapters_total: 0,
    rendered_ms: 0,
    started_at: "",
    ...overrides,
  });
}

function entry(overrides = {}) {
  return {
    gid: 120,
    title: "Treasure Island",
    authors: "Robert Louis Stevenson",
    have: null,
    ...overrides,
  };
}

// The page, open on a finished book, having played nothing. Nothing is waiting
// on a timer in this state, which is what makes "the only wake pending is the
// poll" an assertion rather than a hope.
async function opened(t, options) {
  const page = await boot(t, { lastGid: HALF_HEARD.gid, ...options });
  page.audio.ready(1800);
  return page;
}

async function playing(t, options) {
  const page = await opened(t, options);
  page.click("playpause");
  await page.settle();
  return page;
}

// Open the panel and let its first fetch land.
async function books(page) {
  page.click("books");
  await page.settle();
  await page.settle();
  return page;
}

// The rows, as somebody looking at them would read them out. Read out of the
// DOM rather than out of the payload: what the server said is its own business,
// and the only thing worth asserting is what ended up on the screen.
function jobs(page, id = "queue-live") {
  return page.el(id).children.map((li) => {
    const [name, state, stop] = li.children;
    return {
      name: name.textContent,
      state: state.textContent,
      // Null rather than "" so a row with no stop control and a row whose stop
      // control has lost its words cannot be mistaken for each other.
      stop: stop ? stop.textContent : null,
    };
  });
}

function results(page) {
  return page.el("queue-results").children.map((li) => {
    const parts = li.children;
    const mark = parts.find((node) => node.classList.contains("found-have"));
    const add = parts.find((node) => node.classList.contains("found-add"));
    return {
      name: parts[0].textContent,
      have: mark ? mark.textContent : null,
      add: add ? add.textContent : null,
    };
  });
}

// Everything a night is, plus everything a night leaves behind. Close promises
// all of it back unchanged, so all of it is snapshotted — the same shape
// choosing.test.mjs holds cancel to.
function night(page) {
  return {
    probe: page.probe(),
    posts: page.posts.length,
    beacons: page.beacons.length,
    order: page.order.length,
    srcWrites: page.audio.srcWrites.length,
    currentTime: page.audio.currentTime,
    paused: page.audio.paused,
    playCalls: page.audio.playCalls,
  };
}

async function search(page, text) {
  page.el("queue-query").value = text;
  page.el("queue-search").fire("submit", { preventDefault() {} });
  await page.settle();
  await page.settle();
}

// ------------------------------------------------------- costing nothing shut

test("nothing asks about the queue until somebody opens the panel", async (t) => {
  const page = await opened(t);
  assert.equal(page.probe().queueUp, false);
  assert.equal(page.probe().queuePolling, false);
  assert.equal(
    page.fetches.some((url) => url.startsWith("api/queue")),
    false,
  );
  // And no wake is pending either: a page nobody has opened the panel on is a
  // page with nothing to do about the queue, all night.
  assert.deepEqual(page.waits(), []);
});

test("opening asks once at once and then every five seconds", async (t) => {
  const page = await opened(t);
  page.queueView([job()]);
  await books(page);
  assert.equal(page.probe().queueUp, true);
  assert.equal(
    page.fetches.filter((url) => url === "api/queue").length,
    1,
    "the panel asks the moment it goes up, rather than five seconds later",
  );
  // The only wake pending is the panel's own, and it is the five seconds the
  // page says it is.
  assert.deepEqual(page.waits(), [POLL_MS]);
  assert.equal(page.wake(POLL_MS), true);
  await page.settle();
  await page.settle();
  assert.equal(page.fetches.filter((url) => url === "api/queue").length, 2);
  assert.deepEqual(page.waits(), [POLL_MS]);
});

test("closing stops the asking and leaves no wake behind", async (t) => {
  const page = await opened(t);
  page.queueView([job()]);
  await books(page);
  page.click("queue-close");
  await page.settle();
  assert.equal(page.probe().queueUp, false);
  assert.equal(page.probe().queuePolling, false);
  // Not merely "stopped": a wake still scheduled is a radio waking every five
  // seconds all night beside somebody asleep.
  assert.deepEqual(page.waits(), []);
  const asked = page.fetches.filter((url) => url === "api/queue").length;
  await page.settle();
  assert.equal(page.fetches.filter((url) => url === "api/queue").length, asked);
});

test("the phone going in a pocket stops it, and coming back starts it", async (t) => {
  const page = await opened(t);
  page.queueView([job()]);
  await books(page);
  const asked = () => page.fetches.filter((url) => url === "api/queue").length;

  page.document.visibilityState = "hidden";
  page.document.fire("visibilitychange");
  await page.settle();
  // A hidden page's timers are throttled to roughly one wake a minute, which is
  // untimely exactly when nobody is watching. Nothing is pending.
  assert.equal(page.probe().queuePolling, false);
  assert.deepEqual(page.waits(), []);
  const quiet = asked();

  page.document.visibilityState = "visible";
  page.document.fire("visibilitychange");
  await page.settle();
  await page.settle();
  // Back in front of them, and the queue may have moved on entirely while the
  // phone was asleep, so this asks now rather than in five seconds.
  assert.equal(asked(), quiet + 1);
  assert.deepEqual(page.waits(), [POLL_MS]);
});

test("a page coming back with the panel shut asks nothing", async (t) => {
  const page = await opened(t);
  page.document.visibilityState = "hidden";
  page.document.fire("visibilitychange");
  page.document.visibilityState = "visible";
  page.document.fire("visibilitychange");
  await page.settle();
  await page.settle();
  assert.equal(
    page.fetches.some((url) => url.startsWith("api/queue")),
    false,
  );
  assert.deepEqual(page.waits(), []);
});

// -------------------------------------------------------------------- inert

test("close leaves a night that never started exactly as it found it", async (t) => {
  const page = await opened(t);
  page.queueView([job(), waiting()]);
  const before = night(page);
  await books(page);
  assert.equal(page.probe().queueUp, true);
  page.click("queue-close");
  await page.settle();
  const after = night(page);
  assert.deepEqual(after.probe, before.probe);
  assert.equal(after.posts, before.posts);
  assert.equal(after.beacons, before.beacons);
  assert.equal(after.order, before.order);
  assert.equal(after.srcWrites, before.srcWrites);
  assert.equal(after.currentTime, before.currentTime);
  assert.equal(after.playCalls, before.playCalls);
  // A book that was only ever opened is still a book that was only ever opened.
  assert.equal(page.probe().untouched, true);
  assert.deepEqual(page.posts, []);
  assert.deepEqual(page.beacons, []);
});

test("the panel never asks about a book, only about the queue", async (t) => {
  const page = await playing(t);
  const before = page.fetches.length;
  page.queueView([job(), waiting()]);
  await books(page);
  page.wake(POLL_MS);
  await page.settle();
  page.click("queue-close");
  await page.settle();
  // Every request the panel made, and there is nothing else in the list: no
  // api/book, so two in-flight GETs can never leave `current` holding a row
  // from a manifest that is no longer the manifest, and no api/position, which
  // is the one thing on this page that can move somebody backwards.
  assert.deepEqual(
    page.fetches.slice(before),
    ["api/queue", "api/queue"],
    "the panel talks to the queue and to nothing else",
  );
});

test("a book waiting for a touch is still waiting after close", async (t) => {
  const page = await opened(t);
  // The app was backgrounded and the platform refused the sound until it is
  // touched: the real 2am sequence, and the reason showQueue borrows the
  // listener at all.
  page.audio.refuse = "NotAllowedError";
  page.click("playpause");
  await page.settle();
  assert.equal(page.probe().status, "tap anywhere to carry on");
  const playCalls = page.audio.playCalls;

  page.queueView([job()]);
  await books(page);
  // With the listener still armed the first press anywhere on this overlay
  // would have started the book — `close` especially, the one control that
  // promises to change nothing.
  page.document.fire("pointerdown");
  assert.equal(page.audio.playCalls, playCalls);
  assert.equal(page.audio.paused, true);

  page.click("queue-close");
  await page.settle();
  assert.equal(page.probe().status, "tap anywhere to carry on");
  page.audio.refuse = null;
  page.document.fire("pointerdown");
  await page.settle();
  assert.equal(page.audio.paused, false);
});

test("a render finishing under the panel ends nobody's night", async (t) => {
  const page = await playing(t, {
    stored: { "somnia-sleep": JSON.stringify({ choice: 3, leftMs: 1_800_000 }) },
  });
  page.queueView([job()]);
  await books(page);
  const before = page.probe();
  const reports = page.posts.length;
  assert.equal(before.wantsSound, true);

  // The book somebody else's press queued has finished. The panel is a readout
  // of that and nothing else: sharing the ladder that watches THIS book grow
  // would have cleared wantsSound and thrown away the sleep timer because an
  // unrelated render stopped being 'rendering'.
  page.queueView([job({ state: "done", chapters_done: 39 })]);
  page.wake(POLL_MS);
  await page.settle();
  await page.settle();
  assert.equal(page.probe().wantsSound, true);
  assert.equal(page.probe().sleepLeftMs, before.sleepLeftMs);
  assert.equal(page.probe().armed, before.armed);
  assert.equal(page.probe().status, before.status);
  assert.equal(page.posts.length, reports);
});

test("the panel survives an agent answer and a move without closing", async (t) => {
  const page = await playing(t);
  page.queueView([job()]);
  await books(page);

  page.answers({ reply: "Ginger is the chestnut mare in the next box." });
  await page.ask("who is ginger");
  assert.equal(page.probe().queueUp, true);

  // And a move the agent made by the other route, which takes a list of places
  // down because those rows would be lying about where the book is. This panel
  // says nothing about where the book is, holds no payload, and has nothing to
  // be stale about — so none of the six closeCandidates() call sites grows a
  // twin.
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
  assert.equal(page.probe().queueUp, true);
});

// ------------------------------------------------------------------- the words

test("a render says which chapter it is on and how much is ready to play", async (t) => {
  const page = await opened(t);
  page.queueView([job()]);
  await books(page);
  assert.deepEqual(jobs(page), [
    {
      name: "Black Beauty — Anna Sewell",
      // The chapter being worked on, which is the number the journal's
      // "rendering chapter 4/39" line uses, and how much of it can be listened
      // to now. No percentage: chapters differ in length by an order of
      // magnitude, so a bar drawn from 4/39 moves in lurches that read as a
      // stall.
      state: "chapter 4 of 39 · 1h12m read so far",
      stop: "stop reading this",
    },
  ]);
});

test("a book that is only in the line says where in the line it is", async (t) => {
  const page = await opened(t);
  page.queueView([job(), waiting()]);
  await books(page);
  assert.deepEqual(
    jobs(page).map((row) => row.state),
    ["chapter 4 of 39 · 1h12m read so far", "1st in line"],
  );
});

test("a render that has said nothing for five minutes says so", async (t) => {
  const page = await opened(t);
  page.queueView([job({ responding: false })]);
  await books(page);
  // Not "rendering", which would be a claim about a process that may have died
  // with the box. The heartbeat is the only evidence either way and the server
  // has already read it.
  assert.equal(jobs(page)[0].state, "not responding");
});

test("a render that has been asked to stop says it is stopping", async (t) => {
  const page = await opened(t);
  page.queueView([job({ stopping: true })]);
  await books(page);
  // It stays 'rendering' until the child reaches the end of its sentence, and
  // printing that would look like the press had been ignored.
  assert.equal(jobs(page)[0].state, "stopping at the end of this sentence");
});

test("a book whose text has not been parsed yet says so rather than counting", async (t) => {
  const page = await opened(t);
  page.queueView([job({ chapters_total: 0, chapters_done: 0, rendered_ms: 0 })]);
  await books(page);
  // 0 means nobody has written the number down, which is not the same as a
  // book with no chapters — "chapter 1 of 0" is the sentence this exists to
  // stop.
  assert.equal(jobs(page)[0].state, "fetching the text");
});

test("what went wrong is said in the server's own words, under the live rows", async (t) => {
  const page = await opened(t);
  page.queueView([
    job(),
    job({
      id: 9,
      gid: 4321,
      title: "",
      authors: "",
      state: "failed",
      error: "Gutenberg has book 4321 but no HTML edition, so somnia cannot read it.",
    }),
  ]);
  await books(page);
  // Live above, over: the question at 2am is "is anything happening", and it is
  // answered by looking at the top of the panel.
  assert.deepEqual(
    jobs(page).map((row) => row.name),
    ["Black Beauty — Anna Sewell"],
  );
  assert.deepEqual(jobs(page, "queue-gone"), [
    {
      // No name in the catalog and none from the parse, because the parse is
      // what failed.
      name: "book 4321",
      state:
        "Gutenberg has book 4321 but no HTML edition, so somnia cannot read it.",
      // Nothing to stop, and nothing to dismiss either: the row leaves by
      // itself after a day, because after a day a failure is history and
      // history is in the journal.
      stop: null,
    },
  ]);
});

test("a render somebody stopped says whether any of it is playable", async (t) => {
  const page = await opened(t);
  page.queueView([
    job({ id: 5, state: "cancelled", chapters_done: 4 }),
    job({ id: 6, gid: 120, title: "Treasure Island", authors: "", state: "cancelled", chapters_done: 0 }),
  ]);
  await books(page);
  // Two quite different things, and the difference is whether asking for it
  // again is picking something up or starting it.
  assert.deepEqual(
    jobs(page, "queue-gone").map((row) => row.state),
    ["stopped part way — what was read still plays", "taken out of the queue"],
  );
});

// -------------------------------------------------------------------- stopping

test("stopping a render takes two presses", async (t) => {
  const page = await opened(t);
  page.queueView([job()]);
  await books(page);
  page.click("queue-stop-1");
  await page.settle();
  // Nothing has gone anywhere. The button says what the second press will do
  // instead of asking in a dialog, which would be an overlay over an overlay.
  assert.deepEqual(page.stops, []);
  assert.equal(jobs(page)[0].stop, "really stop?");

  page.stopReply({
    ok: true,
    state: "rendering",
    said: "Black Beauty stops at the end of the sentence it is reading.",
  });
  page.click("queue-stop-1");
  await page.settle();
  await page.settle();
  assert.deepEqual(page.stops, ["api/queue/1/stop"]);
  assert.equal(page.el("queue-said").textContent.includes("Black Beauty"), true);
});

test("a stop that was armed and left alone forgets itself", async (t) => {
  const page = await opened(t);
  page.queueView([job()]);
  await books(page);
  page.click("queue-stop-1");
  await page.settle();
  assert.equal(jobs(page)[0].stop, "really stop?");
  // Two things are waiting five seconds here: the poll that redraws the list,
  // and this button forgetting it was asked. The label has to survive the first
  // and give way to the second.
  assert.deepEqual(page.waits(), [POLL_MS, CONFIRM_MS]);
  page.wake(POLL_MS);
  await page.settle();
  await page.settle();
  assert.equal(jobs(page)[0].stop, "really stop?");

  page.wake(CONFIRM_MS);
  await page.settle();
  // Back to what it was, by itself: a button left saying "really stop?" over a
  // book somebody put down is a press away from ending a render nobody meant to
  // end.
  assert.equal(jobs(page)[0].stop, "stop reading this");
  assert.deepEqual(page.stops, []);
});

test("an armed stop survives the list being redrawn under it", async (t) => {
  const page = await opened(t);
  page.queueView([job()]);
  await books(page);
  page.click("queue-stop-1");
  await page.settle();
  // The poll lands between the two presses, which at five seconds each is not a
  // corner case but the ordinary way this goes.
  page.queueView([job({ chapters_done: 4 })]);
  page.wake(POLL_MS);
  await page.settle();
  await page.settle();
  assert.equal(jobs(page)[0].state, "chapter 5 of 39 · 1h12m read so far");
  assert.equal(jobs(page)[0].stop, "really stop?");
  page.click("queue-stop-1");
  await page.settle();
  assert.deepEqual(page.stops, ["api/queue/1/stop"]);
});

test("a row is a readout and not a target", async (t) => {
  const page = await opened(t);
  page.queueView([job()]);
  await books(page);
  const before = night(page);
  page.el("job-1").fire("click");
  await page.settle();
  // The only pressable thing on a row is its own action, so there is nothing to
  // mis-hit into: no seek, no book opened, no request of any kind.
  assert.deepEqual(page.stops, []);
  assert.deepEqual(night(page), before);
});

// --------------------------------------------------------------- adding a book

test("a search asks once per press, not once per keystroke", async (t) => {
  const page = await opened(t);
  page.queueView([]);
  await books(page);
  page.catalogEntries([entry()]);
  await search(page, "treasure island");
  assert.deepEqual(page.searches, ["api/catalog?q=treasure%20island"]);
  assert.deepEqual(results(page), [
    {
      name: "Treasure Island — Robert Louis Stevenson",
      have: null,
      add: "add this book",
    },
  ]);
});

test("a book somnia already has is marked and offers no button", async (t) => {
  const page = await opened(t);
  page.queueView([]);
  await books(page);
  page.catalogEntries([
    entry({ gid: 271, title: "Black Beauty", have: "rendering" }),
    entry({ gid: 11, title: "Alice", have: "done" }),
    entry({ gid: 120, have: "queued" }),
  ]);
  await search(page, "b");
  assert.deepEqual(
    results(page).map((row) => [row.have, row.add]),
    [
      // A press that was never available cannot be a press that did nothing,
      // and at 2am those two feel completely different.
      ["being read now", null],
      ["already here", null],
      ["in the queue", null],
    ],
  );
});

test("a render that died is offered again, because that retry was impossible", async (t) => {
  const page = await opened(t);
  page.queueView([]);
  await books(page);
  page.catalogEntries([entry({ have: "pending" })]);
  await search(page, "treasure");
  assert.deepEqual(results(page), [
    {
      name: "Treasure Island — Robert Louis Stevenson",
      have: "part rendered",
      add: "finish this one",
    },
  ]);
});

test("a press queues the book once and says where it landed", async (t) => {
  const page = await opened(t);
  page.queueView([]);
  await books(page);
  page.catalogEntries([entry()]);
  await search(page, "treasure");
  page.submitReply({
    ok: true,
    id: 2,
    said: "Treasure Island is in the queue, behind one other book.",
  });
  page.queueView([job(), waiting()]);
  page.click("queue-add-120");
  await page.settle();
  await page.settle();
  await page.settle();
  assert.deepEqual(page.submits, [{ gid: 120 }]);
  assert.equal(
    page.el("queue-said").textContent,
    "Treasure Island is in the queue, behind one other book.",
  );
  // The row it just made is on the screen without waiting out the poll, and the
  // result it was pressed on no longer offers a press.
  assert.deepEqual(
    jobs(page).map((row) => row.state),
    ["chapter 4 of 39 · 1h12m read so far", "1st in line"],
  );
  assert.deepEqual(
    results(page).map((row) => [row.have, row.add]),
    [["in the queue", null]],
  );
});

test("a book cannot be queued twice by pressing twice", async (t) => {
  const page = await opened(t);
  page.queueView([]);
  await books(page);
  page.catalogEntries([entry()]);
  await search(page, "treasure");
  page.click("queue-add-120");
  page.click("queue-add-120");
  await page.settle();
  await page.settle();
  await page.settle();
  assert.deepEqual(page.submits, [{ gid: 120 }]);
});

test("a refusal is an answer and is shown as one", async (t) => {
  const page = await opened(t);
  page.queueView([]);
  await books(page);
  page.catalogEntries([entry()]);
  await search(page, "treasure");
  // 200 with a sentence, as /api/queue answers: a refusal is the answer
  // somebody reads twice, and a throw in a fetch wrapper would have skipped it.
  page.submitReply({
    ok: false,
    id: 0,
    said: "Treasure Island is already here, all of it.",
  });
  page.click("queue-add-120");
  await page.settle();
  await page.settle();
  await page.settle();
  assert.equal(
    page.el("queue-said").textContent,
    "Treasure Island is already here, all of it.",
  );
});

// ------------------------------------------------------------ offline honesty

test("a queue that cannot be reached leaves the last list up and says so", async (t) => {
  const page = await opened(t);
  page.queueView([job()]);
  await books(page);
  const drawn = jobs(page);

  page.unreachable({ queue: true });
  page.wake(POLL_MS);
  await page.settle();
  await page.settle();
  // An empty queue and an unreachable server look identical and mean opposite
  // things, so the list is left exactly as it was and the doubt is said
  // underneath it.
  assert.deepEqual(jobs(page), drawn);
  assert.equal(page.el("queue-note").textContent, "couldn't reach somnia");
  // And it keeps asking: the tailnet coming back is the ordinary case.
  assert.deepEqual(page.waits(), [POLL_MS]);

  page.unreachable({ queue: false });
  page.queueView([job({ chapters_done: 5 })]);
  page.wake(POLL_MS);
  await page.settle();
  await page.settle();
  assert.equal(page.el("queue-note").textContent, "");
  assert.equal(jobs(page)[0].state, "chapter 6 of 39 · 1h12m read so far");
});

test("a submit that never landed draws no row and says nothing was added", async (t) => {
  const page = await opened(t);
  page.queueView([]);
  await books(page);
  page.catalogEntries([entry()]);
  await search(page, "treasure");
  page.unreachable({ submit: true });
  page.click("queue-add-120");
  await page.settle();
  await page.settle();
  assert.equal(
    page.el("queue-said").textContent,
    "couldn't reach somnia — nothing has been added",
  );
  // No optimistic row. A queue entry that never existed on the server is
  // exactly the state a wrong press must not be able to leave behind.
  assert.deepEqual(jobs(page), []);
  // And the press is available again, because trying again is the whole of what
  // there is to do about it.
  assert.equal(results(page)[0].add, "add this book");
});

test("a search that cannot be reached says so rather than saying nothing", async (t) => {
  const page = await opened(t);
  page.queueView([]);
  await books(page);
  page.unreachable({ catalog: true });
  await search(page, "treasure");
  assert.equal(page.el("queue-said").textContent, "couldn't reach somnia");
  assert.deepEqual(results(page), []);
});

// ------------------------------------------------- what the denominator buys

test("running out of audio part way through a book does not call it the end", async (t) => {
  // A render that stopped at chapter one of three and is not running: the
  // manifest is the whole truth about it, and before chapters_total existed
  // there was nothing in that truth to tell this from a finished book.
  const page = await boot(t, { lastGid: PART_READ.gid });
  page.audio.ready(8);
  page.click("playpause");
  await page.settle();
  page.audio.advance(8);
  await page.settle();
  assert.equal(page.probe().status, "the rest of this book hasn't been read yet");
  // The sleep timer and the fight to keep the sound going are left alone: the
  // night is not over, there is simply nothing more to play yet.
  assert.equal(page.probe().wantsSound, true);
});

test("running out of audio at the end of a finished book still says so", async (t) => {
  const page = await boot(t, { lastGid: TONE_BOOK.gid });
  page.audio.ready(8);
  page.click("playpause");
  await page.settle();
  for (let chapter = 0; chapter < 3; chapter++) {
    page.audio.advance(8);
    await page.settle();
    page.audio.ready(8);
    await page.settle();
  }
  assert.equal(page.probe().status, "that is the end of the book");
  assert.equal(page.probe().wantsSound, false);
});

test("an empty library says where to add one", async (t) => {
  const page = await boot(t, { lastGid: null, library: [] });
  // The one state that most needs the panel, and the one with no book, no
  // manifest and no gid to press anything about.
  assert.equal(page.probe().status, "nothing yet — press books to add one");
});
