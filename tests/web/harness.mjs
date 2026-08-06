// The page, run without a browser.
//
// app.js is the largest single thing in somnia and, until this file, the only
// part of it no test ever ran: a state machine over one media element that
// does its real work at 2am with the screen off, where nobody is watching and
// nothing can be reproduced afterwards. Everything below exists so that it can
// be driven from a test instead of from a phone.
//
// It is a fake media element rather than a headless browser on purpose. What
// the page has to get right is mostly a *sequence* — metadata before src
// before play, the spurious pause a load fires swallowed, a report built at the
// moment it goes out rather than when it was asked for — and a real element
// decides for itself when to fire any of that, so a browser test can only wait
// and hope. Here every event is fired by hand, in the order the spec says a
// browser fires it, and a mistake in the order is a failing test rather than a
// night that goes quiet.
//
// A real browser still has the last word. Chrome over CDP against a real
// `somnia serve` is what proves the m4a decodes, that Range requests come back
// 206 and that the lock screen really follows; nothing here can prove any of
// that, and it does not try. This is for everything that happens in between.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const APP = fileURLToPath(
  new URL("../../src/somnia/web/app.js", import.meta.url),
);

// The tone book, as tests/tone_book.py seeds it and /api/book/900001 serves it:
// three chapters of exactly eight seconds, so every boundary is a round number
// and an off-by-one in the arithmetic has nowhere to hide. The shape is
// player.Manifest's, field for field — a harness that answered with a shape the
// server cannot produce would be testing a page somnia does not serve.
export const TONE_BOOK = {
  gid: 900001,
  title: "Three Tones",
  authors: "Somnia Test",
  status: "done",
  total_ms: 24000,
  position_ms: null,
  seq: 0,
  heard_to_ms: 24000,
  chapters: [
    {
      idx: 0,
      title: "The First Tone",
      start_ms: 0,
      end_ms: 8000,
      url: "api/audio/900001/0",
    },
    {
      idx: 1,
      title: "The Second Tone",
      start_ms: 8000,
      end_ms: 16000,
      url: "api/audio/900001/1",
    },
    {
      idx: 2,
      title: "The Third Tone",
      start_ms: 16000,
      end_ms: 24000,
      url: "api/audio/900001/2",
    },
  ],
};

// Somewhere else to be taken to. Two chapters, a different length and a
// position of its own, so that a page which quietly kept the first book's
// numbers is caught by any of the three.
export const OTHER_BOOK = {
  gid: 900002,
  title: "Another Book",
  authors: "Somnia Test",
  status: "done",
  total_ms: 16000,
  position_ms: 4000,
  seq: 7,
  heard_to_ms: 16000,
  chapters: [
    {
      idx: 0,
      title: "Elsewhere One",
      start_ms: 0,
      end_ms: 8000,
      url: "api/audio/900002/0",
    },
    {
      idx: 1,
      title: "Elsewhere Two",
      start_ms: 8000,
      end_ms: 16000,
      url: "api/audio/900002/1",
    },
  ],
};

// Rows in the database and no audio yet: the render has started and the first
// chapter has not landed. Being moved to one of these is the shape of the bug
// that left the page playing one book while every clock read another.
export const RENDERING_BOOK = {
  gid: 900003,
  title: "Still Being Read",
  authors: "Somnia Test",
  status: "rendering",
  total_ms: 0,
  position_ms: null,
  seq: 0,
  heard_to_ms: 0,
  chapters: [],
};

// A book somebody could actually fall asleep in. The tone book is twenty-four
// seconds long — shorter than the shortest rewind and a four-hundredth of the
// shortest sleep timer — so anything measured in minutes needs a book measured
// in minutes, and this is it: two half-hour chapters.
export const NIGHT_BOOK = {
  gid: 900004,
  title: "A Long Night",
  authors: "Somnia Test",
  status: "done",
  total_ms: 3_600_000,
  position_ms: 0,
  seq: 0,
  heard_to_ms: 3_600_000,
  chapters: [
    {
      idx: 0,
      title: "The Long First",
      start_ms: 0,
      end_ms: 1_800_000,
      url: "api/audio/900004/0",
    },
    {
      idx: 1,
      title: "The Long Second",
      start_ms: 1_800_000,
      end_ms: 3_600_000,
      url: "api/audio/900004/1",
    },
  ],
};

const MANIFESTS = new Map(
  [TONE_BOOK, OTHER_BOOK, RENDERING_BOOK, NIGHT_BOOK].map((m) => [
    `api/book/${m.gid}`,
    m,
  ]),
);

// The eight the page registers. A browser throws for an action it has never
// heard of, which is the whole reason registration is wrapped in a try, so the
// fake throws too.
const ACTIONS = [
  "play",
  "pause",
  "stop",
  "seekbackward",
  "seekforward",
  "seekto",
  "previoustrack",
  "nexttrack",
  "skipad",
];

class FakeMediaMetadata {
  constructor(init) {
    Object.assign(this, init);
  }
}

// The page runs in its own vm context, which means its own Object, its own
// Array and its own prototypes: an object built inside it is not deepEqual to
// the same object built out here, however identical it reads. So everything
// handed back across that line is copied into this realm first, and a test can
// compare what it sees with a plain object literal.
function plain(value) {
  return value === undefined ? undefined : JSON.parse(JSON.stringify(value));
}

// The lock screen, the notification shade and whatever is paired over
// Bluetooth. For most of the night this is the only transport there is, so it
// is faked in full rather than stubbed: what it was told, in what order, and
// whether it would have thrown.
class FakeSession {
  constructor(order) {
    this.order = order;
    this.handlers = {};
    this.positions = [];
    this.states = [];
    this._metadata = null;
    this._playbackState = "none";
  }

  get metadata() {
    return this._metadata;
  }

  set metadata(value) {
    this._metadata = plain(value);
    this.order.push(`metadata:${value && value.title}`);
  }

  get playbackState() {
    return this._playbackState;
  }

  set playbackState(value) {
    this._playbackState = value;
    this.states.push(value);
    this.order.push(`state:${value}`);
  }

  setActionHandler(action, fn) {
    if (!ACTIONS.includes(action)) throw new TypeError(`unsupported ${action}`);
    this.handlers[action] = fn;
  }

  // The platform's own validation, reproduced. Every guard around the call in
  // publishPosition exists to keep this from throwing, and a throw here would
  // leave the *previous* chapter's scrubber up rather than clearing it — so a
  // harness that quietly accepted anything would test none of them.
  setPositionState(state) {
    if (!Number.isFinite(state.duration) || state.duration < 0) {
      throw new TypeError(`bad duration ${state.duration}`);
    }
    if (
      !Number.isFinite(state.position) ||
      state.position < 0 ||
      state.position > state.duration
    ) {
      throw new TypeError(`bad position ${state.position} of ${state.duration}`);
    }
    if (!Number.isFinite(state.playbackRate)) {
      throw new TypeError(`bad rate ${state.playbackRate}`);
    }
    this.positions.push(plain(state));
  }

  // The scrubber as it stands, which is the only part of it anyone can see.
  last() {
    return this.positions[this.positions.length - 1];
  }

  // A press on the lock screen, a pillow speaker or a pair of headphones.
  press(action, details) {
    const handler = this.handlers[action];
    if (!handler) throw new Error(`nothing is listening for ${action}`);
    return handler(details);
  }
}

class FakeElement {
  constructor(id) {
    this.id = id;
    this.handlers = {};
    this.textContent = "";
    this.hidden = false;
    this.attributes = {};
    this.style = {};
    // Which half of the play button is showing is a class rather than a glyph,
    // so a class list that can be read back is how a test sees the transport.
    this.classes = new Set();
    this.classList = {
      add: (name) => this.classes.add(name),
      remove: (name) => this.classes.delete(name),
      contains: (name) => this.classes.has(name),
      toggle: (name, on) =>
        (on ?? !this.classes.has(name))
          ? this.classes.add(name)
          : this.classes.delete(name),
    };
  }

  addEventListener(type, fn) {
    (this.handlers[type] ||= []).push(fn);
  }

  fire(type, event = {}) {
    for (const fn of [...(this.handlers[type] || [])]) fn(event);
  }

  setAttribute(name, value) {
    this.attributes[name] = value;
  }

  getAttribute(name) {
    return this.attributes[name] ?? null;
  }

  append() {}
  replaceChildren() {}
  focus() {}
}

// One <audio> element for the life of the page, as index.html insists on. The
// events below are fired in the order a browser fires them, and the comments
// say which part of the spec each one is standing in for.
class FakeAudio extends FakeElement {
  constructor(order, clock) {
    super("player");
    this.order = order;
    this.clock = clock;
    this._src = "";
    this.currentTime = 0;
    this.duration = NaN;
    this.paused = true;
    this.ended = false;
    this.readyState = 0;
    this.error = null;
    this.volume = 1;
    this.playbackRate = 1;
    this.srcWrites = [];
    this.playCalls = 0;
    // What play() rejects with, for the two failures onPlayRejected tells
    // apart: the autoplay policy, which is worth offering a tap for, and
    // everything else, which is not.
    this.refuse = null;
  }

  get src() {
    return this._src;
  }

  set src(value) {
    this._src = value;
    this.srcWrites.push(value);
    this.order.push(`src:${value}`);
    this.readyState = 0;
    this.ended = false;
    this.currentTime = 0;
    this.duration = NaN;
    this.error = null;
    // Assigning src runs the media element load algorithm, which pauses a
    // playing element and fires a pause event at it. This is the spurious
    // pause the `swapping` guard exists for, and half the point of this fake.
    if (!this.paused) {
      this.paused = true;
      this.fire("pause");
    }
  }

  play() {
    this.playCalls++;
    if (this.refuse) {
      const error = new Error("refused");
      error.name = this.refuse;
      return Promise.reject(error);
    }
    this.order.push("play");
    this.paused = false;
    this.ended = false;
    this.fire("play");
    return Promise.resolve();
  }

  pause() {
    if (this.paused) return;
    this.paused = true;
    this.fire("pause");
  }

  // Metadata arrived: the point at which there is a duration to clamp a
  // pending offset against. `seeked` follows because landing at that offset is
  // a seek, and the page reports one.
  ready(duration = 8) {
    this.duration = duration;
    this.readyState = 1;
    this.fire("loadedmetadata");
    this.fire("seeked");
  }

  // Sound coming out. The wall clock moves with the element because in a
  // browser it does: the sleep timer counts listening time off Date.now()
  // between timeupdates, so a harness that let the two drift would be testing
  // a timer no phone could ever run.
  advance(seconds) {
    if (this.paused) return;
    this.clock.tick(seconds * 1000);
    this.currentTime = Math.min(this.currentTime + seconds, this.duration);
    this.fire("timeupdate");
    if (this.currentTime >= this.duration) {
      // Per spec, in this order: `ended` already reads true because it is a
      // function of the playback position, the element is paused, `pause`
      // fires, and only then `ended`.
      this.ended = true;
      this.paused = true;
      this.fire("pause");
      this.fire("ended");
    }
  }

  // The chapter stopped arriving: the tailnet went, or the file is not there.
  // A browser fires `error` and then pauses, which is the second pause that
  // must not be read as somebody putting the book down.
  fail() {
    this.error = { code: 2, message: "network" };
    this.fire("error");
    if (!this.paused) {
      this.paused = true;
      this.fire("pause");
    }
  }
}

// Everything app.js asks the clock is Date.now(): the fifteen-second
// heartbeat, the once-a-second gate on the lock screen, how long the sound has
// been off, and how much of the sleep timer is left. Driving it by hand is
// what makes all four observable from a test that runs in a millisecond.
// Where every test's night starts, so that a sleep timer written down by an
// earlier page can be given a time that is neither in the future nor stale.
export const START_MS = 1_700_000_000_000;

class FakeClock {
  constructor() {
    this.ms = START_MS;
  }

  tick(ms) {
    this.ms += ms;
  }

  now() {
    return this.ms;
  }
}

// The sleep timer outlives the page on purpose, so the storage it outlives it
// in has to be real enough to be read back.
class FakeStorage {
  constructor(initial = {}) {
    this.items = new Map(Object.entries(initial));
  }

  getItem(key) {
    return this.items.has(key) ? this.items.get(key) : null;
  }

  setItem(key, value) {
    this.items.set(key, String(value));
  }

  removeItem(key) {
    this.items.delete(key);
  }
}

class FakeBlob {
  constructor(parts, options) {
    this.text = parts.join("");
    this.type = options && options.type;
  }
}

// Appended to app.js before it runs. The page is a script and exports nothing
// — the browser wants one file it can load with one <script> — so this is how
// a test reaches the state machine from inside its own scope, the same place
// the page's own event handlers see it from.
const EPILOGUE = `
globalThis.__page = {
  probe: () => ({
    gid,
    seq,
    positionMs,
    untouched,
    swapping,
    wantsSound,
    idx: current && current.idx,
    chapter: chapterTitle.textContent,
    clock: clock.textContent,
    status: statusLine.textContent,
    sleep: sleepButton.textContent,
    spokenSleep: sleepButton.getAttribute("aria-label"),
    armed: sleepButton.classList.contains("armed"),
    playing: playpause.classList.contains("playing"),
    fading: fade !== null,
    sleepLeftMs,
    volume: player.volume,
  }),
  seekGlobal,
  openBook,
  follow,
  resumePoint,
  // The four pure functions the whole timeline rests on. They are worth
  // reaching for directly: every clamp in them is there because a decoder, a
  // render clock or a book shorter than a thirty-second step disagreed with
  // the arithmetic once, and none of those are reproducible on demand.
  math: { locate, toElementSeconds, toGlobalMs, timestamp, rewindFor },
};
`;

/**
 * Boot the page against a fake browser, and hand back the levers.
 *
 * `t` is the node:test context, and is only used to clear whatever timers the
 * page still has pending when the test ends — the retry backoff and the
 * wait-for-the-render ladder both schedule minutes ahead, and a test that left
 * one running would hold the whole run open.
 */
export async function boot(t, options = {}) {
  const {
    lastGid = 900001,
    reply = { accepted: true },
    sentenceStart = null,
    stored = {},
  } = options;

  // Everything the element and the media session did, in the order they did
  // it. A boundary is only correct as a sequence, so order is the assertion.
  const order = [];
  const clock = new FakeClock();
  const session = new FakeSession(order);
  const audio = new FakeAudio(order, clock);
  const localStorage = new FakeStorage(stored);

  const elements = new Map([["player", audio]]);
  const el = (id) => {
    if (!elements.has(id)) elements.set(id, new FakeElement(id));
    return elements.get(id);
  };

  const fetches = [];
  const posts = [];
  const beacons = [];
  const sentenceAsks = [];
  let positionReply = reply;
  let holding = false;
  let dropping = false;
  const held = [];

  const fakeWindow = new FakeElement("window");
  const fakeDocument = new FakeElement("document");
  fakeDocument.getElementById = el;
  fakeDocument.visibilityState = "visible";

  // Cleared when the test ends. The page has no idea it is in one, and it is
  // entitled to be waiting five seconds for a chapter that will never come.
  const timers = new Set();

  const context = {
    console: { error() {}, log() {}, warn() {} },
    document: fakeDocument,
    window: fakeWindow,
    localStorage,
    sessionStorage: new FakeStorage(),
    crypto: { randomUUID: () => "test-token" },
    Blob: FakeBlob,
    MediaMetadata: FakeMediaMetadata,
    Date: { now: () => clock.now() },
    navigator: {
      language: "en-GB",
      mediaSession: session,
      vibrate() {},
      sendBeacon(url, blob) {
        beacons.push({ url, type: blob.type, body: JSON.parse(blob.text) });
        return true;
      },
    },
    setTimeout: (fn, ms) => {
      const id = setTimeout(() => {
        timers.delete(id);
        fn();
      }, ms);
      timers.add(id);
      return id;
    },
    clearTimeout: (id) => {
      timers.delete(id);
      clearTimeout(id);
    },
    fetch: async (url, init) => {
      fetches.push(url);
      if (url === "api/books") {
        return json({
          last_gid: lastGid,
          books: [...MANIFESTS.values()].map((m) => ({ gid: m.gid })),
        });
      }
      if (MANIFESTS.has(url)) return json(MANIFESTS.get(url));
      if (url.startsWith("api/sentence/")) {
        sentenceAsks.push(url);
        return json({ start_ms: sentenceStart });
      }
      if (url === "api/position") {
        // A report that never gets out at all, which is a different thing from
        // one that is answered late: the page is told nothing, so whatever it
        // was carrying is still owed. Held is the tailnet being slow; this is
        // the tailnet being gone.
        if (dropping) throw new Error("no route to host");
        const answer = positionReply;
        posts.push({
          body: JSON.parse(init.body),
          keepalive: Boolean(init.keepalive),
        });
        // A report that has gone out and not come back: 2am, tailnet asleep.
        // Holding one is the only way to see what the page does with a reply
        // that arrives about a book it has since left. What it is answered
        // with is read at release rather than here, because that is when the
        // server would decide it — and because the interesting refusals are
        // about things that had not happened yet when the report went out.
        if (holding) {
          return new Promise((resolve) => {
            held.push(() => resolve(json(positionReply)));
          });
        }
        return json(answer);
      }
      return { ok: false, json: async () => ({ error: "no such thing" }) };
    },
  };
  context.globalThis = context;
  vm.createContext(context);
  vm.runInContext(readFileSync(APP, "utf8") + EPILOGUE, context);

  // One turn of the microtask queue per await. Two is what boot costs: the
  // book list, then the manifest.
  const settle = () => new Promise((resolve) => setTimeout(resolve, 0));
  await settle();
  await settle();

  const page = {
    audio,
    session,
    storage: localStorage,
    // The two least testable moments of the night are the last two: the page
    // being backgrounded, and the page dying. Both are events on these.
    window: fakeWindow,
    document: fakeDocument,
    el,
    order,
    posts,
    beacons,
    fetches,
    sentenceAsks,
    settle,
    tick: (ms) => clock.tick(ms),
    probe: () => plain(context.__page.probe()),
    // The state machine itself, for the moves that arrive from the agent
    // rather than from a thumb.
    seek: (...args) => context.__page.seekGlobal(...args),
    openBook: (...args) => context.__page.openBook(...args),
    follow: (...args) => context.__page.follow(...args),
    resumePoint: () => context.__page.resumePoint(),
    math: Object.fromEntries(
      Object.entries(context.__page.math).map(([name, fn]) => [
        name,
        (...args) => plain(fn(...args)),
      ]),
    ),
    click: (id) => el(id).fire("click"),
    press: (...args) => session.press(...args),
    reply: (answer) => {
      positionReply = answer;
    },
    hold: (on) => {
      holding = on;
    },
    drop: (on) => {
      dropping = on;
    },
    // Let every held report come back at once, oldest first.
    release: () => {
      while (held.length) held.shift()();
    },
    // Only the reports, only the interesting fields, in order — which is how
    // every assertion about them reads.
    reports: () =>
      posts.map((p) => [p.body.gid, p.body.reason, p.body.position_ms]),
    stop: () => {
      for (const id of timers) clearTimeout(id);
      timers.clear();
    },
  };
  t?.after(page.stop);
  return page;
}

function json(body) {
  return { ok: true, json: async () => body };
}
