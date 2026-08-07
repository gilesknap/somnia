// The 2am client. Push to talk, let go, get taken back to the passage.
//
// Speech recognition is push-to-talk rather than always-listening on purpose:
// a bedroom is full of speech that was not meant for somnia, and holding a
// button is the one gesture that survives being half asleep.
//
// The book plays here as well. somnia rendered it one file per chapter, but
// nobody listens to a chapter — they listen to a book — so everything below
// counts in global milliseconds, the same clock the search results and the
// agent speak, and which file that lands in is an implementation detail kept
// to three functions.
//
// Most of the controls are not on this page at all. With the screen off the
// book is driven from the lock screen and from whatever is paired over
// Bluetooth, so the media session below is not decoration — for most of the
// night it is the only transport there is.

const transcript = document.getElementById("transcript");
const composer = document.getElementById("composer");
const question = document.getElementById("question");
const talk = document.getElementById("talk");
const restart = document.getElementById("restart");
const statusLine = document.getElementById("status");
const player = document.getElementById("player");
const playerBar = document.getElementById("player-bar");
const bookTitle = document.getElementById("book-title");
const chapterTitle = document.getElementById("chapter-title");
const chapterWord = document.getElementById("chapter-word");
const chapterCount = document.getElementById("chapter-count");
const clock = document.getElementById("clock");
// The position line, which is also the way back to the places somnia last
// found, and the count that says so. It is a control only on the nights there
// is something behind it; see drawPlaces.
const placesOpen = document.getElementById("places-open");
const placesFound = document.getElementById("places-found");
const wholePlayed = document.getElementById("whole-played");
const sleepButton = document.getElementById("sleep");
const playpause = document.getElementById("playpause");
const back30 = document.getElementById("back30");
const fwd30 = document.getElementById("fwd30");
const chapterClock = document.getElementById("chapter-clock");
const prevChapter = document.getElementById("prevchapter");
const nextChapter = document.getElementById("nextchapter");
const candidates = document.getElementById("candidates");
const candidatesBook = document.getElementById("candidates-book");
const summaryLine = document.getElementById("candidates-summary");
const candidateList = document.getElementById("candidate-list");
const candidatesCancel = document.getElementById("candidates-cancel");
// The books panel. `queuePanel` rather than `queue` because "the queue" in this
// file means the rows the server is holding, and the two are not the same thing
// — the panel is a photograph of them, taken every five seconds and only while
// somebody is looking.
const booksButton = document.getElementById("books");
const queuePanel = document.getElementById("queue");
// The card the live rows sit in, and the label over the rows that are over.
// Both are drawn empty in the document and shown only when there is something
// in them: a card with a heading and no rows under it says something should be
// happening, which at 2am is a reason to get up.
const queueWorking = document.getElementById("queue-working");
const queueLive = document.getElementById("queue-live");
const queueEnded = document.getElementById("queue-ended");
const queueGone = document.getElementById("queue-gone");
const queueNote = document.getElementById("queue-note");
const queueSearch = document.getElementById("queue-search");
const queueQuery = document.getElementById("queue-query");
const queueResults = document.getElementById("queue-results");
const queueSaid = document.getElementById("queue-said");
const queueClose = document.getElementById("queue-close");
// What is playing under the panel, at the top of it. `reading` and not `queue`
// because this is the one part of that overlay that is about a book rather than
// about the rows the server is holding, and the two must not be muddled here of
// all places.
const readingNow = document.getElementById("reading-now");
const readingTitle = document.getElementById("reading-title");
const readingMeta = document.getElementById("reading-meta");
const readingTrack = document.getElementById("reading-track");
const readingFill = document.getElementById("reading-fill");
const readingResume = document.getElementById("reading-resume");
// The page's second voice, and the sheet of black over the whole of it.
const toastLine = document.getElementById("toast");
const dimLayer = document.getElementById("dim");

// One conversation per launch of the app. The server holds the history; this
// is only the name it goes by.
let token = sessionStorage.getItem("somnia-token");
if (!token) {
  token = crypto.randomUUID();
  sessionStorage.setItem("somnia-token", token);
}

function say(text, kind) {
  const line = document.createElement("p");
  line.className = `said ${kind}`;
  line.textContent = text;
  transcript.append(line);
  transcript.scrollTop = transcript.scrollHeight;
  return line;
}

// Answers are read, never spoken back. The book is the only thing this page
// says out loud — nothing below turns an answer into speech — because an
// answer read over the book would be somnia interrupting itself, and the phone
// is on a bedside table next to someone who may be asleep again by the time it
// lands.
function setStatus(text) {
  statusLine.textContent = text;
}

// The other voice, and why there are two.
//
// #status above holds the sentences that have to stand: "listening…" for as
// long as a button is held, "tap anywhere to carry on" until somebody does,
// "the rest of this book hasn't been read yet" until they go somewhere it has.
// A line that cleared itself after a few seconds could not hold any of those —
// the instruction would be gone and the state it describes would not.
//
// This holds the other kind: what the press they just made did. It is true
// when it is read and untrue a minute later, so it takes itself off, and it
// happens at the bottom of the screen near the thumb that caused it rather
// than at the top where the reading is.
//
// One box, one sentence. A second one replaces the first in place rather than
// pushing it up a stack: the older sentence is never the one still true, and a
// box that jumped every time a control was pressed would read as an alarm on a
// page whose whole argument is that nothing moves unless it has to.
const TOAST_MS = 2800;

let toastTimer = 0;

function toast(text) {
  clearTimeout(toastTimer);
  toastLine.textContent = text;
  toastLine.hidden = false;
  toastTimer = setTimeout(forgetToast, TOAST_MS);
}

// Emptied as well as hidden, so that "is anything being said?" has one answer
// and not two that can disagree.
function forgetToast() {
  clearTimeout(toastTimer);
  toastTimer = 0;
  toastLine.hidden = true;
  toastLine.textContent = "";
}

// How dark the page takes the room, over and above what the phone will do.
// Android holds its own backlight above a floor and this room is below it, so
// the last of the light comes off in a layer of black over everything.
//
// Beside the sleep timer in localStorage, and for the same reason: it is an
// instruction about the dark that outlives a tab the phone discarded while it
// was in a pocket. Unlike the timer it never goes stale — a room that was dark
// last night is dark tonight.
//
// Nothing on the page writes it yet. The control that would belongs with the
// jump size and the default sleep timer on a settings surface this page does
// not have, and inventing one to carry a single slider is a screen somebody
// has to find in the dark.
const DIM_KEY = "somnia-dim";
const DIM_DEFAULT = 0.12;
// Past this the page stops being readable, and there is nothing on screen to
// turn it back down with. A half-written record must not be able to black out
// the only transport in the room.
const DIM_MAX = 0.6;

function restoreDim() {
  let level = DIM_DEFAULT;
  try {
    const saved = localStorage.getItem(DIM_KEY);
    // `Number(null)` and `Number("")` are both 0, and 0 is a level somebody
    // can mean — so nothing written down has to be told apart from a level of
    // nothing before the range is checked at all, or a page that has never
    // been set opens with no dim on it. NaN fails both comparisons, which is
    // how every other kind of rubbish falls through to the default.
    const asked = saved?.trim() ? Number(saved) : NaN;
    if (asked >= 0 && asked <= DIM_MAX) level = asked;
  } catch (error) {
    // Storage refused. The page ships at 0.12 and this changes nothing.
    console.error(error);
  }
  dimLayer.style.opacity = String(level);
}

restoreDim();

// A short buzz confirms the button caught the press, for a listener who can't
// see much and shouldn't be listening for a beep. Android honours this; iOS
// ignores it, which is why the button also changes colour and pulses.
function buzz(ms) {
  navigator.vibrate?.(ms);
}

async function ask(text) {
  if (!text) return;
  // Whatever the last answer offered is about a question that is over. Leaving
  // it up would put a list of places over a conversation that has moved on, and
  // the row they pressed would be an answer to the question above the one they
  // are looking at.
  closeCandidates();
  say(text, "you");
  question.value = "";
  const pending = say("…", "agent pending");
  const asked = token;
  setStatus("thinking…");
  try {
    const response = await fetch("api/ask", {
      method: "POST",
      headers: { "content-type": "application/json" },
      // The open book travels with the question. Without it the agent could see
      // the three books on the shelf and nothing saying which one was making
      // the sound, so the only honest answer to "where was I" was "which book?"
      // — asked over the book they were listening to, every single turn.
      //
      // Read here rather than captured with `asked`, because it is a fact about
      // the moment the question is sent. `gid` is null until a book is open,
      // and the server treats that as "no book" rather than refusing the turn.
      body: JSON.stringify({ token, question: text, gid }),
    });
    const body = await response.json();
    // They started over while this was in flight: the answer belongs to a
    // conversation that no longer exists, and appearing now would be a reply
    // to a question no longer on the screen.
    if (token !== asked) return;
    if (!response.ok) throw new Error(body.error || "no answer");
    pending.className = "said agent";
    pending.textContent = body.reply || "…nothing to say.";
    // An answer does one of two things and never both. Either the turn knew
    // where they meant and moved the book — the short way round, since the same
    // move arrives as the refusal of the next report within fifteen seconds, so
    // it is only ever a head start and applying it twice costs nothing — or it
    // did not, and hands back the places it is choosing between for them to
    // decide.
    //
    // Both cannot arrive: the move_to tool refuses to run at all once a turn
    // has offered a list, and the server writes "move" only when there is no
    // "candidates". If they ever did, the list wins, because nothing has been
    // moved under a listener who has not chosen yet — and a move that really
    // happened comes back as the refusal of the next report anyway.
    if (body.candidates?.places?.length) showCandidates(body.candidates);
    else follow(body.move);
  } catch (error) {
    pending.className = "said failed";
    pending.textContent = "Couldn't reach somnia. Still here?";
    console.error(error);
  }
  setStatus("");
  transcript.scrollTop = transcript.scrollHeight;
}

composer.addEventListener("submit", (event) => {
  event.preventDefault();
  ask(question.value.trim());
});

// How long `start over` stands asked before the corner forgets it. Long enough
// to read four words and decide, short enough that a phone put down face up
// with the question still on it is not one press from an empty screen. The
// queue's `stop reading this` is the same pattern with a longer fuse, because
// that press ends hours of rendering and this one ends a conversation.
const RESTART_CONFIRM_MS = 3200;

// The wake that will put the label back, or 0 for a corner that is not asking.
// One variable and not two: the label is drawn from it, so "is it armed?" and
// "what does it say?" cannot come apart.
let restartTimer = 0;

function forgetRestart() {
  clearTimeout(restartTimer);
  restartTimer = 0;
  restart.textContent = "start over";
  restart.classList.remove("armed");
}

// Two presses, and the button itself is the question — the same answer the
// queue panel gives, so that the page has one way of asking rather than two.
// Not a confirm dialog: that would be the first thing on this page to take
// focus from anybody, and an overlay over a conversation somebody is about to
// throw away is one more thing to get out of.
restart.addEventListener("click", () => {
  if (!restartTimer) {
    restart.textContent = "sure? tap again";
    restart.classList.add("armed");
    restartTimer = setTimeout(forgetRestart, RESTART_CONFIRM_MS);
    return;
  }
  forgetRestart();
  startOver();
});

// What is thrown away is the conversation, and only the conversation. The book
// keeps playing, keeps its position and keeps its sleep timer: "start over"
// means the questions, not the night. A press here that took somebody back to
// the beginning of a nine-hour book would be the one mistake on this page
// nothing could undo.
function startOver() {
  const stale = token;
  token = crypto.randomUUID();
  sessionStorage.setItem("somnia-token", token);
  fetch("api/forget", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ token: stale }),
  }).catch(() => {});
  // A list left up over a cleared transcript is exactly the stranding this page
  // promises cannot happen: an overlay offering places, with nothing behind it
  // to say what was asked or why. `closeCandidates` takes it off the screen and
  // `forgetPlaces` takes it out of the key, so the position line stops offering
  // a way back to it as well.
  closeCandidates();
  forgetPlaces();
  transcript.replaceChildren();
  setStatus("");
  say("Where do you want to be?", "agent");
  question.focus();
}

// ------------------------------------------------------------------- playing

// How early to start the next chapter. Ingest leaves 500ms of rendered silence
// at the end of every one, so a swap that begins 400ms out is spent inside a
// pause the book already had: the gap between chapters comes out shorter than
// it was written to be rather than longer. Raise this only if the silence
// ingest appends rises with it.
const SWAP_LEAD_S = 0.4;

// What "back a bit" means, in the absence of anyone able to say.
const SEEK_STEP_S = 30;

// How far into a chapter "previous" stops meaning the one before and starts
// meaning the top of this one. The same five seconds every music player has
// used for forty years, and the reason a double press goes back a whole
// chapter while a single one only starts this chapter again.
const CHAPTER_RESTART_MS = 5000;

// The ways to be asleep before the book is, in minutes, with the end of the
// chapter after them and nothing at either end of the list. One tap walks it.
const SLEEP_CHOICES = [null, 15, 30, 45, 60, "chapter"];

// Twenty seconds of getting quieter, ending in silence at the moment the timer
// named — so it begins before that moment, not at it. Long enough that the
// book leaving is not itself the thing that wakes someone, and short enough
// that "fifteen minutes" stays an honest description of fifteen minutes.
const FADE_OUT_MS = 20_000;

// Short, because this is the sound they just asked for.
const FADE_IN_MS = 900;

// The most a rewind ever gives back, and how far behind it a sentence may
// begin and still be worth going to. Beyond that the index has a hole in it,
// and two minutes of a book someone has already heard is not a kindness.
const LONG_REWIND_MS = 30_000;
const SENTENCE_REACH_MS = 45_000;

// How often a playing book says where it has got to. Fifteen seconds is what a
// phone dying costs: few enough writes that a night is a few hundred of them,
// close enough together that waking up never means hearing a chapter twice.
// It is counted on timeupdate rather than by a timer on purpose — a hidden
// page's setInterval is throttled to roughly one wake a minute, so anything
// hung off a timer misbehaves exactly when nobody is watching, whereas
// timeupdate comes off the media pipeline and keeps firing with the screen off.
const HEARTBEAT_MS = 15_000;

// How long to leave a book that is still rendering before asking whether it has
// grown, and the longest that wait ever gets. Kokoro takes minutes over a
// chapter, so asking every few seconds all night would be a hundred requests
// for one answer — but the ask made the moment the audio runs out is the one
// the listener is waiting on, and that one is worth being quick about.
const RENDER_ASK_MS = 5_000;
const RENDER_ASK_MAX_MS = 60_000;

// How long a stall is given to sort itself out before the chapter is put back
// under it, and how long to leave between attempts once something has actually
// failed. Two seconds because a tailnet re-key is usually over before that;
// thirty at the top because a VPS that is down is down, and a phone that
// retried flat out until morning is a phone with no battery in the morning.
const STALL_GRACE_MS = 8_000;
const RETRY_MIN_MS = 2_000;
const RETRY_MAX_MS = 30_000;

// The lock screen, the notification shade and whatever is paired over
// Bluetooth all reach the page through this one object, so it is the whole of
// what somnia can be controlled by while the phone is face down. It is still
// only a courtesy: a browser without one plays the book perfectly well, and
// so every use of it below is guarded rather than assumed.
const session = navigator.mediaSession ?? null;

// Both sizes the installed app ships, so the platform takes the one that fits
// its slot rather than scaling the other. What appears on the lock screen at
// 2am should look like the thing they pressed to get there.
const ARTWORK = [
  { src: "icon-192.png", sizes: "192x192", type: "image/png" },
  { src: "icon-512.png", sizes: "512x512", type: "image/png" },
];

let manifest = null;
let gid = null; // which book, once the manifest has said
let current = null; // {idx, chapter} — which file the element is holding
let positionMs = 0;
// How many times the agent has moved this book, as of the last thing we heard
// from the server. Our own reports never raise it, so a higher number coming
// back can only be a move this page has not applied.
let seq = 0;
// Nothing is written until something happens. Opening the app at 2am to ask a
// question is not listening, and a book they only opened must keep its null
// position: "never started" and "at the very beginning" are different answers
// to "where am I?", and only one of them would be true.
let untouched = true;
let sending = false; // one report in flight at a time
let owed = null; // a report that arrived while one was in flight
let lastSentAt = 0;
// How much of the book has really come out of the speaker, counted off the
// media clock rather than off the wall clock. It is the whole of the evidence
// the spoiler guard has, and only this page can give it: a jump moves the
// position without moving this, a phone asleep in a pocket moves neither, and
// a chapter that buffered for ten seconds moves the wall clock and not this.
let playedMs = 0;
// Where that clock was last sampled, or null when the next sample is only a
// baseline. A seek and a chapter swap both move the position with nothing
// played, so the distance either of them moved is never counted as a step.
let playedFrom = null;
// How much of it the server has taken. Only an accepted report spends any:
// a refusal did not raise the mark, and a reply that never arrived may as well
// not have, so either way the next report carries the playback again. A mark
// left behind the position by one lost report never catches up, and a guard
// that has stopped rising is not a guard.
let playedTaken = 0;
// Where to land once the file has a duration to clamp against. It stays set
// until it is applied, so a loadedmetadata that arrives four minutes late —
// after the tailnet came back — still lands in the right place instead of
// starting the chapter from nothing.
let pendingOffsetMs = null;
let swapping = false; // a chapter change is in flight
let weArePausing = false; // tell our own pause from the platform's
let lastPublishedAt = 0; // when the lock screen was last told the time
// When the sound stopped, so that pressing play again can tell a moment's
// silence from a night's. Zero once it has been spent, so the same pause is
// never given back twice.
let lastPauseAt = 0;
// A fade in flight: where the volume came from, where it is going, and whether
// silence is the end of the night at the other side of it.
let fade = null;
let sleepChoice = 0; // an index into SLEEP_CHOICES
// Listening time left before the fade begins, or null when the night has no
// end scheduled.
let sleepLeftMs = null;
let sleepCountedAt = 0;
let sleepSavedAt = 0;
// Where the sentence they stopped in began, found out at the pause.
let sentenceHint = null;
// Whether the sound is meant to be on. `paused` cannot answer that: an element
// whose chapter failed to load is paused, so is one whose buffer ran dry at
// 3am, and the difference between those and a thumb on the pause button is the
// whole of whether the page should be fighting to get the book back.
let wantsSound = false;
// A stall being given a moment, a reload waiting out its backoff, and the boot
// waiting out its own. Zero for "nothing pending", which is what clearTimeout
// takes for an answer.
let stallTimer = 0;
let retryTimer = 0;
let retryDelay = RETRY_MIN_MS;
let bootTimer = 0;
let bootDelay = RETRY_MIN_MS;
// Whether what is on the status line is about the network. Only what this page
// put there is ever taken away again: "goodnight" is about something else and
// is still true.
let troubled = false;
// The book the page has run out of audio on and is waiting to grow, or null:
// which book, how long to leave it before asking again, which chapter it ran
// out after, and whether the sound was on when it did.
let awaiting = null;

// Global milliseconds -> the chapter that owns them, and how far into its file.
// A linear scan: a book is a few hundred chapters and this runs once per seek.
function locate(ms) {
  const chapters = manifest.chapters;
  const t = Math.max(0, Math.min(ms, manifest.total_ms));
  let i = 0;
  while (i + 1 < chapters.length && chapters[i + 1].start_ms <= t) i++;
  return { idx: i, chapter: chapters[i], offset_ms: t - chapters[i].start_ms };
}

// Global offset -> a number this element will accept, clamped by the container.
function toElementSeconds(offset_ms, duration) {
  const s = Math.max(0, offset_ms / 1000);
  if (!Number.isFinite(duration) || duration <= 0) return s;
  // 50ms of headroom: assigning currentTime >= duration lands at the end and
  // fires `ended` at once, which silently skips a whole chapter. The render
  // clock can legitimately exceed the container clock, so this is not
  // hypothetical.
  return Math.min(s, duration - 0.05);
}

// Where the element is, on the book's clock. Clamped to this chapter's own
// span: a decoder that ignores the edit list runs up to one AAC frame past what
// was rendered, and a position reported from inside that padding would claim to
// be in the next chapter.
function toGlobalMs(chapter, currentTime) {
  const t = chapter.start_ms + Math.round(currentTime * 1000);
  return Math.max(chapter.start_ms, Math.min(t, chapter.end_ms));
}

// h:mm:ss, the same shape format_timestamp gives the agent, so what is on the
// screen and what somnia says out of the model agree to the second.
function timestamp(ms) {
  const seconds = Math.floor(Math.max(0, ms) / 1000);
  const mm = String(Math.floor(seconds / 60) % 60).padStart(2, "0");
  const ss = String(seconds % 60).padStart(2, "0");
  return `${Math.floor(seconds / 3600)}:${mm}:${ss}`;
}

// The same clock at chapter scale, which is nearly always minutes. Carrying the
// book's leading "0:" onto a twelve-minute chapter would put the least
// informative digit on the page in the position the eye reads first, and make
// the two clocks on screen look like the same number twice.
function chapterTime(ms) {
  const seconds = Math.floor(Math.max(0, ms) / 1000);
  const ss = String(seconds % 60).padStart(2, "0");
  if (seconds < 3600) return `${Math.floor(seconds / 60)}:${ss}`;
  const mm = String(Math.floor(seconds / 60) % 60).padStart(2, "0");
  return `${Math.floor(seconds / 3600)}:${mm}:${ss}`;
}

function drawPlayer() {
  if (!manifest || !current) return;
  // Which book, above which chapter of it. Drawn every pass rather than once
  // when the book opened, so there is no path — a swap, a refreshed manifest, a
  // move to another book — by which the headline can be left naming the last
  // one. The fallback is the queue panel's, from bookName: a book that has been
  // through nothing but the local catalog may have no name at all, and "book
  // 1342" is a good deal better than an empty line where the title goes.
  bookTitle.textContent = manifest.title || `book ${gid}`;
  chapterTitle.textContent = current.chapter.title;
  const whole = timestamp(manifest.total_ms);
  clock.textContent = `${timestamp(positionMs)} of ${whole}`;
  // And whether that line is a way in to anything, which is a question about
  // the book it has just been drawn for: places belong to the book they were
  // found in, so this is asked on the same pass rather than once when a list
  // was last shown.
  drawPlaces();
  // The same pair as the line above it, drawn instead of written. Clamped both
  // ends: a position past the last chapter — a book re-rendered shorter than
  // the mark somebody left in it — would otherwise run the fill off the end of
  // its track and take the knob with it. A book with no total is drawn empty
  // rather than full, because nobody knowing how long it is does not mean it
  // has been finished.
  const through = manifest.total_ms
    ? Math.min(100, Math.max(0, (positionMs / manifest.total_ms) * 100))
    : 0;
  wholePlayed.style.width = `${through}%`;
  // Off the chapter row and the book's own clock, never off the element's
  // currentTime: that number restarts at zero on every swap, and during one it
  // belongs to whichever of the two chapters the element happens to be holding.
  const into = positionMs - current.chapter.start_ms;
  const length = current.chapter.end_ms - current.chapter.start_ms;
  chapterClock.textContent = `${chapterTime(into)} of ${chapterTime(length)}`;
  // Which chapter of how many, in the gap between the two buttons that change
  // it. The denominator is chapters_total — how many chapters the book HAS, as
  // against how many have been rendered — because a count taken from the
  // chapters that happen to have landed would read "1 of 1" at eleven o'clock
  // and "1 of 2" an hour later, on a book that has forty.
  //
  // 0 means nobody wrote the number down. That is every book rendered before
  // the column existed, which is every book on the box this runs on, so it is
  // not an edge case to be swept up: the count says which chapter they are in
  // and stops, and the word above it goes rather than saying "chapter" twice.
  const total = manifest.chapters_total || 0;
  const number = current.idx + 1;
  chapterWord.hidden = total === 0;
  chapterCount.textContent = total
    ? `${number} of ${total}`
    : `chapter ${number}`;
  // A book still being read grows a chapter at a time, so this is asked every
  // draw rather than once when the manifest lands.
  nextChapter.disabled = !manifest.chapters[current.idx + 1];
  // Which half of the button's drawing shows. A class rather than the glyph it
  // used to hold: how big the symbol is and where in the button it sits are no
  // longer whatever the phone's symbol font happened to think.
  playpause.classList.toggle("playing", !player.paused);
  playpause.setAttribute("aria-label", player.paused ? "Play" : "Pause");
  drawSleep();
  // The books panel says which book this is and offers it back, out of the same
  // three things this function has just drawn from. Here rather than once when
  // the panel goes up, because the agent can move the book — or the sound can
  // cross into the next chapter — while somebody is reading the panel, and a
  // block painted once would then be naming a place the book has left. It costs
  // nothing while the panel is shut; see drawReadingNow.
  drawReadingNow();
}

// What the notification says. The chapter is the title because it is the part
// that changes and the part they are in; the book is the album, which is where
// a phone expects to find the name that stays the same all night.
function announceChapter(chapter) {
  if (!session || typeof MediaMetadata !== "function") return;
  session.metadata = new MediaMetadata({
    title: chapter.title,
    artist: manifest?.authors || "",
    album: manifest?.title || "",
    artwork: ARTWORK,
  });
}

function reportPlaybackState(state) {
  if (session) session.playbackState = state;
}

// The lock screen scrubber, kept honest by the book's own clock.
//
// It is chapter-scale on purpose. A whole-book scrubber on a twelve-hour novel
// gives three minutes to the pixel: useless for the nudge someone actually
// wants, and one sleepy thumb away from flinging them past the spoiler guard
// into the ending. Where they are in the book is the agent's business and the
// API's; what the notification owes them is the chapter, and it names it.
//
// Both numbers are derived from the chapter row and positionMs — the render
// clock, the one the search results and the saved position speak — and not
// from the element. That keeps the arithmetic on `duration` where it belongs,
// in the three conversion functions above, and it means the pair can never be
// the NaN-and-stale-currentTime that setPositionState throws on.
function publishPosition() {
  if (!session?.setPositionState || !current) return;
  const span = (current.chapter.end_ms - current.chapter.start_ms) / 1000;
  if (!(span > 0)) return;
  const into = (positionMs - current.chapter.start_ms) / 1000;
  session.setPositionState({
    duration: span,
    // Clamped rather than trusted: for the few milliseconds between a boundary
    // starting and its metadata arriving, positionMs still belongs to the
    // chapter being left. A throw here would leave the PREVIOUS chapter's
    // state up rather than clearing it, and a scrubber showing the wrong place
    // with complete confidence is worse than one showing nothing.
    position: Math.min(Math.max(into, 0), span),
    playbackRate: player.playbackRate || 1,
  });
}

// A chapter boundary and a seek into another chapter are the same thing, so
// they are the same code path.
function showChapter({ idx, chapter, offset_ms }, { play }) {
  swapping = true;
  current = { idx, chapter };
  // Before the source, and so before play(): the metadata current at the
  // moment playback starts is the one the notification adopts, so setting it
  // afterwards labels the new chapter with the old one's title. Nothing else
  // here is allowed to touch the session during a swap — no pause, no
  // playbackState, no second element — because handing audio focus back even
  // for an instant is what tears the notification down, and once it is gone
  // nothing in this page can get it back.
  announceChapter(chapter);
  pendingOffsetMs = offset_ms; // applied at loadedmetadata, when there is
  player.src = chapter.url; // a duration to clamp against
  if (play) player.play().catch(onPlayRejected);
  drawPlayer();
}

// Every seek arrives here: a transport button now, and the lock screen, a
// Bluetooth skip and the agent moving the book later. Routing them all through
// the global timeline is what lets a thirty-second nudge at the start of
// chapter five land in chapter four, which is what a listener means by "back a
// bit" in a book that only happens to be stored as separate files.
function seekGlobal(ms, { play = null } = {}) {
  if (!manifest) return;
  // The book is going somewhere, so a list of places it might go is answered
  // however it got here — a row, a thumb on −30, the lock screen, or the agent
  // moving the book by the other route while they were still reading. A list
  // left up over a book that has since moved offers rows whose "you are here"
  // is a lie, and the next press acts on it.
  closeCandidates();
  // Somebody meant this — a thumb, a lock screen, or the agent. Whatever
  // happens next is worth recording, even if they never press play.
  untouched = false;
  // Nobody who is asleep skips forward thirty seconds or asks to be taken to
  // the fair, so a jump during the fade is somebody still awake. The sound
  // comes back rather than stopping under them mid-sentence.
  if (fade?.thenSleep) startFade(1, FADE_IN_MS);
  const at = locate(ms);
  positionMs = Math.max(0, Math.min(ms, manifest.total_ms));
  // Every seek in the page comes through here, which is what makes this the
  // one place the played clock has to be set aside: the ground between where
  // they were and where they are going is not ground anybody heard, and
  // counted as a step it would be a skip that paid for itself.
  playedFrom = null;
  // Playback still owed is given up at the same moment, and this is the one
  // place it is right to give it up. It was earned over the ground behind the
  // jump and can only ever justify standing there; carried across, the first
  // report from the far side spends it on the distance instead. That is not
  // hypothetical — an agent move refuses the heartbeat in flight, and the page
  // follows the refusal with a seek, so the two arrive in that order every
  // time: in a real browser the refused report's seven seconds paid for a
  // twelve-second move, and the mark stepped over four seconds nobody heard.
  // The cost is that a jump can leave the mark up to one report behind the
  // furthest they really got, which is the same direction as every other
  // choice here: the guard stops early rather than late.
  playedTaken = playedMs;
  if (
    current &&
    at.idx === current.idx &&
    player.readyState > 0 &&
    !player.error
  ) {
    // Within the file already loaded. This branch is what keeps autoplay policy
    // out of the common case: a seek on a live element needs no permission at
    // all, so it does not ask for any.
    //
    // An element holding an error is not a live one however much of the file it
    // still has: it will not fetch again until it is loaded afresh, so a press
    // of play after the tailnet went would set currentTime on something that
    // was never going to make a sound. Sending it down the other branch is what
    // makes the transport a way back as well.
    player.currentTime = toElementSeconds(at.offset_ms, player.duration);
    if (play === true && player.paused) player.play().catch(onPlayRejected);
  } else {
    showChapter(at, { play: play ?? !player.paused });
  }
  drawPlayer();
}

// `rewind` is true for the two controls a listener presses themselves, and for
// nothing else. A move the agent made lands exactly where it said it would, a
// chapter boundary carries straight on, and opening the app does not start the
// book at all, so none of those want anything given back.
function ensurePlaying({ rewind = false } = {}) {
  const to = rewind ? resumePoint() : positionMs;
  lastPauseAt = 0;
  // From silence, however short the fade. A book coming back at full volume in
  // a dark room is the loudest thing that happens all night, and the sound of
  // it is what someone reaching for the phone at 3am is trying to avoid.
  //
  // Only when it really is stopped: a platform that sends `play` to something
  // already playing fires no play event back, so there would be nothing left
  // to bring the volume up again and the book would go silently on.
  if (rewind && player.paused) player.volume = 0;
  // An element that has reached the end of its file starts the chapter over
  // from nothing if it is simply told to play — so a night that ended on a
  // chapter boundary would begin the morning with the whole chapter again.
  // Going back through the timeline lands on the start of the next one, which
  // is where the book actually is.
  if (player.ended || to !== positionMs) {
    seekGlobal(to, { play: true });
    return;
  }
  player.play().catch(onPlayRejected);
}

function pauseHere() {
  weArePausing = true;
  player.pause();
}

// ------------------------------------------------------- the end of the night

// The two things the Audiobookshelf app did that this page had to learn: stop
// the book before it plays all night, and give back the last thing they heard
// before they stopped taking it in. Still to come, and deliberately not here:
// shaking the phone to buy another quarter of an hour, which needs a motion
// permission and a threshold nobody can guess at from a desk.
//
// Everything below is driven from timeupdate, for the reason given at
// HEARTBEAT_MS: a backgrounded page's timers are throttled to roughly one wake
// a minute, and a fade stepped once a minute is not a fade. timeupdate comes
// off the media pipeline four times a second for as long as there is sound,
// which is exactly as long as either of these has anything to do.

function startFade(to, ms, { thenSleep = false } = {}) {
  fade = { from: player.volume, to, ms, at: Date.now(), thenSleep };
  stepFade();
}

// Volume back to whole, whatever was being done to it. The invariant this
// keeps is that a paused player is always at full volume: nothing else on the
// page has to remember that the sleep timer turned the sound down, and a
// resume by any route — a thumb, the lock screen, the agent — is never silent.
function endFade() {
  fade = null;
  player.volume = 1;
}

function stepFade() {
  if (!fade) return;
  const ratio = fade.ms > 0 ? Math.min(1, (Date.now() - fade.at) / fade.ms) : 1;
  // Ramped on the square root of the volume rather than on the volume itself.
  // Loudness as an ear hears it falls away far more slowly than amplitude
  // does, so a straight line from one to zero stays sounding like full volume
  // for most of its length and then drops off in the last second or two —
  // which is the shape of being woken up, not of falling asleep.
  const from = Math.sqrt(fade.from);
  const level = (from + (Math.sqrt(fade.to) - from) * ratio) ** 2;
  // iOS does not let a page set the volume at all. There this does nothing
  // until the pause at the end of it, which is abrupt, but still puts the book
  // down at the time it was asked to.
  player.volume = Math.min(1, Math.max(0, level));
  if (ratio < 1) return;
  const sleeping = fade.thenSleep;
  fade = null;
  if (sleeping) fallAsleep();
}

function fallAsleep() {
  pauseHere();
  // Only now, with the sound already stopped. Putting the volume back an
  // instant sooner would be twenty seconds of fading out followed by one
  // moment at full volume, which is the one thing this was here to prevent.
  player.volume = 1;
  setStatus("goodnight");
  drawPlayer();
}

// The timer outlives the page, because the page does not outlive the night. A
// backgrounded tab is discarded whenever the phone wants the memory back, and
// reloading is also the first thing anyone does to a page that looks stuck —
// either way a timer kept only in a variable was silently disarmed, with
// nothing on screen to say it had gone, and the book played until morning.
//
// localStorage rather than the sessionStorage the token uses. sessionStorage
// dies with the tab, which is exactly the death this is about; and unlike the
// conversation, which is meant to start fresh every launch, an armed sleep
// timer is an instruction about tonight that nobody has cancelled.
const SLEEP_KEY = "somnia-sleep";

// How often the countdown is written down. The readout is in whole minutes, so
// half a minute of slop after a crash cannot be seen, and this is two writes a
// minute rather than two hundred and forty.
const SLEEP_SAVE_MS = 30_000;

// Older than this and the night it belonged to is over. Someone opening the
// book the following evening is starting a night rather than finishing one, and
// a timer they could not remember setting would end it early for no reason they
// could see.
const SLEEP_STALE_MS = 6 * 3_600_000;

function saveSleep() {
  sleepSavedAt = Date.now();
  try {
    if (SLEEP_CHOICES[sleepChoice] === null) {
      localStorage.removeItem(SLEEP_KEY);
      return;
    }
    const state = { choice: sleepChoice, leftMs: sleepLeftMs, at: Date.now() };
    localStorage.setItem(SLEEP_KEY, JSON.stringify(state));
  } catch (error) {
    // Storage refused or full. The timer still works for as long as this page
    // lives, which is all it ever did before.
    console.error(error);
  }
}

// What they asked for last time this page was alive, if it still stands.
function restoreSleep() {
  let saved = null;
  try {
    saved = JSON.parse(localStorage.getItem(SLEEP_KEY) || "null");
  } catch (error) {
    console.error(error);
  }
  if (!saved || !(Date.now() - saved.at < SLEEP_STALE_MS)) return;
  const choice = SLEEP_CHOICES[saved.choice];
  // Anything else is a half-written record or a list of choices that has
  // changed shape since. Neither is worth ending a night over.
  if (choice === undefined || choice === null) return;
  if (typeof choice === "number" && typeof saved.leftMs !== "number") return;
  sleepChoice = saved.choice;
  sleepLeftMs = typeof choice === "number" ? saved.leftMs : null;
  // Listening time, not clock time — the same rule as while it is counting. The
  // minutes they had left are still the minutes they have left, whether the
  // reload took two seconds or the phone killed the tab an hour ago.
  sleepCountedAt = Date.now();
  drawSleep();
}

function sleepsAtChapterEnd() {
  return SLEEP_CHOICES[sleepChoice] === "chapter";
}

function clearSleep() {
  sleepChoice = 0;
  sleepLeftMs = null;
  saveSleep();
}

sleepButton.addEventListener("click", () => {
  sleepChoice = (sleepChoice + 1) % SLEEP_CHOICES.length;
  const choice = SLEEP_CHOICES[sleepChoice];
  sleepLeftMs = typeof choice === "number" ? choice * 60_000 : null;
  sleepCountedAt = Date.now();
  // A fade already running is the timer having fired. Reaching for the control
  // at all means they are awake enough to have changed their mind about it, so
  // the sound comes back rather than the setting quietly applying to a book
  // that is already going quiet.
  if (fade?.thenSleep) startFade(1, FADE_IN_MS);
  drawSleep();
  saveSleep();
  // Said in the words somebody would use, once, rather than left to be read
  // off a pill that says "sleep 30m". The pill is the readout and this is the
  // answer to the press — including on the sixth press, which takes the timer
  // off again: a box still promising to fade out over a night with no end
  // scheduled is the one lie this control can tell.
  toast(sleepSentence());
  buzz(10);
});

function sleepSentence() {
  const choice = SLEEP_CHOICES[sleepChoice];
  if (choice === null) return "no sleep timer";
  if (choice === "chapter") return "fading out at the end of the chapter";
  return `fading out in ${choice} min`;
}

// What the pill says, and what it says out loud, decided in one place.
//
// The visible label is one pre-assembled string — `sleep timer · 30m` — and
// not a word with a value appended to it. `sleep` on its own was the control's
// name on the nights it was off and a state on the nights it was on, and the
// only thing telling those two readings apart was whether anything followed
// it. Half asleep that is not a distinction anybody makes. Now the pill always
// says both what it is and what it is set to, which is also what makes it the
// one control on the page that can be read without being understood first.
//
// The spoken form is built from the same branch rather than beside it, so a
// state cannot be added to one and forgotten in the other — and it stays a
// sentence rather than the pill's own string, because a screen reader saying
// "sleep timer middle dot thirty m" is not what the pill means.
function drawSleep() {
  const choice = SLEEP_CHOICES[sleepChoice];
  let says = "off";
  let spoken = "off";
  if (fade?.thenSleep) {
    says = "fading";
    spoken = "fading out";
  } else if (choice === "chapter") {
    says = "chapter end";
    spoken = "at the end of this chapter";
  } else if (sleepLeftMs !== null) {
    // Rounded up, and never zero: a countdown that says nothing is left has
    // nothing left to say, and by then the sound itself is the announcement.
    const minutes = Math.max(1, Math.ceil(sleepLeftMs / 60_000));
    says = `${minutes}m`;
    spoken = `${minutes} minutes left`;
  }
  sleepButton.textContent = `sleep timer · ${says}`;
  sleepButton.setAttribute("aria-label", `Sleep timer, ${spoken}`);
  sleepButton.classList.toggle("armed", choice !== null);
}

// The timer counts listening time, not clock time. Someone who pauses to ask a
// question and then reads the answer meant to hear the rest of what they had
// asked for — and a timer that had run out while they read would answer them
// by ending the night, which is the opposite of what pressing play just said.
function countDownToSleep() {
  const now = Date.now();
  // Clamped: a gap this wide was a stall, a chapter arriving slowly or a
  // question being answered, and none of that was anybody listening.
  const spent = Math.min(now - sleepCountedAt, 2_000);
  sleepCountedAt = now;
  // Seeking fires timeupdate whether or not there is any sound, which is the
  // one way a paused book could otherwise be charged for the time.
  if (player.paused || fade || sleepLeftMs === null) return;
  sleepLeftMs -= spent;
  // Written down as it goes, not only when it is set: the tab can be discarded
  // between one timeupdate and the next, and a timer that came back with the
  // whole of its hour still to run would be an hour of book nobody asked for.
  if (now - sleepSavedAt >= SLEEP_SAVE_MS) saveSleep();
  if (sleepLeftMs > FADE_OUT_MS) return;
  // Spent: the fade is the last thing the timer does, and once it has started
  // the control reads as off again. Coming back afterwards is a decision to
  // set another one, which is one tap and takes no thinking about.
  clearSleep();
  startFade(0, FADE_OUT_MS, { thenSleep: true });
}

// How far back to go when they press play again, by how long the book was
// silent. A pause is three unlike things wearing the same name: a moment taken
// to hear something in the room, a question asked and answered, and falling
// asleep with the phone still in a hand. Only the last of them means the last
// thing they took in was well before where the sound stopped.
function rewindFor(silentMs) {
  if (silentMs < 30_000) return 0;
  if (silentMs < 5 * 60_000) return 8_000;
  if (silentMs < 60 * 60_000) return 20_000;
  return LONG_REWIND_MS;
}

function resumePoint() {
  if (!lastPauseAt) return positionMs;
  const back = rewindFor(Date.now() - lastPauseAt);
  const target = Math.max(0, positionMs - back);
  // Only the longest rung snaps. The sentence was looked up half a minute
  // behind where they stopped, because that is where the long rewind lands, so
  // applying it to one of the shorter ones would quietly turn eight seconds
  // back into half a minute back — a rewind three times the size of the one
  // the silence asked for, and it would happen on the most ordinary pause
  // there is.
  if (back < LONG_REWIND_MS) return target;
  if (!sentenceHint || sentenceHint.from !== Math.round(positionMs)) {
    // Nothing was found out at the pause, or the book has been moved since and
    // what was found out is about somewhere else entirely.
    return target;
  }
  // Long enough that they were asleep: land on the start of the sentence
  // rather than in the middle of one. A clause with no beginning is worse than
  // the silence was, and after an hour they have the whole of it to place.
  const extra = target - sentenceHint.start_ms;
  return extra >= 0 && extra <= SENTENCE_REACH_MS ? sentenceHint.start_ms : target;
}

// Asked at the pause and spent at the resume, never the other way round.
// Pressing play has to make a sound now, and a phone that has been face down
// for an hour is the least likely thing on the tailnet to answer quickly.
async function rememberTheSentence() {
  sentenceHint = null;
  if (gid === null) return;
  const from = Math.round(positionMs);
  try {
    const response = await fetch(
      `api/sentence/${gid}/${Math.max(0, from - LONG_REWIND_MS)}`,
    );
    if (!response.ok) return;
    const body = await response.json();
    if (typeof body.start_ms === "number") {
      sentenceHint = { from, start_ms: body.start_ms };
    }
  } catch (error) {
    // Offline, most likely, which is where the night usually ends. The flat
    // rewind above is the whole answer then, and a perfectly good one.
    console.error(error);
  }
}

// The listener waiting for a touch anywhere on the page, or null. Its
// truthiness is the whole of "armed" — a second flag is a second thing to keep
// in step with it, and the one that goes stale is the one that starts the book
// under somebody.
//
// It is a named function held in a variable rather than the anonymous
// once-listener this used to be, purely so it can be taken off again. The
// candidate list is why: a real 2am sequence is app backgrounded, play refused,
// question asked, list arrives, cancel pressed — and with an unremovable
// listener the press that was meant to change nothing starts the book. Cancel
// puts it back afterwards, because by then it is true again.
let tapToResume = null;

function armTapToResume() {
  if (tapToResume) return;
  setStatus("tap anywhere to carry on");
  tapToResume = () => {
    tapToResume = null;
    ensurePlaying();
  };
  document.addEventListener("pointerdown", tapToResume, { once: true });
}

function disarmTapToResume() {
  if (!tapToResume) return;
  document.removeEventListener("pointerdown", tapToResume);
  tapToResume = null;
}

function onPlayRejected(error) {
  // Two unlike failures arrive here. NotAllowedError is the autoplay policy:
  // the sound is welcome, it just wants a touch first, and offering that is
  // the difference between a book that stopped and a book that stopped with
  // nothing on the screen to say why.
  //
  // Everything else — a chapter that would not load, a play abandoned because
  // a newer seek replaced the source — has already been explained by whatever
  // caused it, and arming a tap-to-resume for it would start the book under
  // the next thing they touch, which at 2am is the question box.
  console.error(error);
  if (error?.name !== "NotAllowedError") return;
  armTapToResume();
}

// --------------------------------------------------------------- getting back

// Nothing below is hypothetical. Wifi power save, a DHCP renewal and a
// tailscale re-key each take the tailnet away for a few seconds in the middle
// of the night, and a media element comes back from none of them by itself:
// once it has taken a network error it will never fetch again, and a buffer
// that ran dry with nothing behind it sits there silently until something
// reloads it. With the screen locked, all of that looks the same from the
// outside — a notification that says paused — so the page has to be the thing
// that notices, and it has to say so where they can see it. At 2am a silent
// spinner is worse than a sentence.

function inTrouble(message) {
  troubled = true;
  setStatus(message);
}

// The book is arriving again. Only the network's own message is cleared:
// "goodnight" and "tap anywhere to carry on" are about something else.
function outOfTrouble() {
  clearTimeout(stallTimer);
  clearTimeout(retryTimer);
  stallTimer = 0;
  retryTimer = 0;
  retryDelay = RETRY_MIN_MS;
  if (troubled) setStatus("");
  troubled = false;
}

// Put the chapter back under them, from where they had got to rather than from
// the top of it. Reloading is the whole of the way back — assigning src is what
// makes an element try the network again — and going through locate(positionMs)
// is what makes a five-second drop cost five seconds instead of making them
// hear the last ten minutes again.
function reloadTheChapter() {
  if (!manifest || !current) return;
  inTrouble("still trying to reach the book");
  showChapter(locate(positionMs), { play: wantsSound });
}

// Wait, then try again, waiting longer each time. Bounded at both ends for the
// reason given at RETRY_MIN_MS. Never while they are the ones who stopped it: a
// page that reloaded chapters under a book somebody had put down would be
// spending the battery on nobody.
function retryLater() {
  if (retryTimer || !wantsSound) return;
  // Whatever grace a stall was being given is spent: `waiting` fires just
  // before the error that follows it, so without this every failure leaves two
  // chains reloading the chapter and the backoff below is capped at whichever
  // of them is shorter — which at 4am is a request every eight seconds until
  // the battery goes.
  clearTimeout(stallTimer);
  stallTimer = 0;
  retryTimer = setTimeout(() => {
    retryTimer = 0;
    reloadTheChapter();
  }, retryDelay);
  retryDelay = Math.min(retryDelay * 2, RETRY_MAX_MS);
}

// A buffer that has run dry, or a download that has stopped arriving. Given a
// few seconds before anything is done about it: most of these refill by
// themselves and nobody hears more than a gap, and announcing every ordinary
// rebuffer would put a line on the screen — and in a screen reader's ear,
// through the live region — for something that is already over.
//
// `suspend` and `abort` are deliberately not wired here however much they look
// like they belong: suspend is a full buffer and abort is a swap, which between
// them happen at every chapter boundary all night.
function stalling() {
  if (!wantsSound || stallTimer || retryTimer) return;
  // The grace is for a buffer that is going to refill, and there is nothing
  // left of that story once the page is already fighting for the chapter: a
  // reload that stalls again goes straight onto the ladder instead. Without
  // this the two of them interleave — eight seconds of grace, then the wait,
  // then eight seconds of grace — and the cadence never falls below a request
  // every nineteen seconds however long the night's outage lasts.
  if (troubled) {
    retryLater();
    return;
  }
  stallTimer = setTimeout(() => {
    stallTimer = 0;
    reloadTheChapter();
    // That reload was an attempt like any other, so the next one waits longer.
    // A server that takes the connection and never answers — a proxy black
    // hole, a re-key caught mid-handshake — fires no `error` at all, so
    // nothing else here would ever grow the wait: the new source stalls, this
    // fires again on the same eight seconds, and that is the request every
    // eight seconds until the battery goes that the backoff exists to prevent.
    // Never below the grace this waited out, so the ladder can only be more
    // patient than the stall was, never less.
    retryDelay = Math.max(retryDelay, STALL_GRACE_MS);
    retryLater();
  }, STALL_GRACE_MS);
}

// Something happened that might mean the network is back: the browser said so,
// or the page came back in front of them. Whatever is waiting out a backoff is
// worth trying now — the wait was only ever a guess about a network nobody can
// see, and being wrong about it in this direction costs one request.
function tryAgainNow() {
  bootDelay = RETRY_MIN_MS;
  retryDelay = RETRY_MIN_MS;
  if (bootTimer) {
    clearTimeout(bootTimer);
    bootTimer = 0;
    openTheBook();
  }
  if (retryTimer) {
    clearTimeout(retryTimer);
    retryTimer = 0;
    reloadTheChapter();
  }
  if (awaiting) {
    awaiting.delay = RENDER_ASK_MS;
    askForMore();
  }
}

player.addEventListener("waiting", stalling);
player.addEventListener("stalled", stalling);
// The sound is really coming out, which is the only proof worth having. A stall
// that refilled by itself never reloads anything, so this is the one thing that
// says so.
player.addEventListener("playing", outOfTrouble);

// `online` is a hint and never a replacement for the backoff above: the wifi
// coming back is not the tailnet coming back, and a tailscale re-key does not
// touch this event at all. All it means is that there is no point waiting out
// the rest of a wait that was a guess.
window.addEventListener("online", tryAgainNow);

player.addEventListener("loadedmetadata", () => {
  // The server answered with a chapter, which is as much as this page ever
  // knows about the network being back.
  outOfTrouble();
  if (pendingOffsetMs !== null) {
    player.currentTime = toElementSeconds(pendingOffsetMs, player.duration);
    pendingOffsetMs = null;
  }
  swapping = false;
  // A new file, so the last sample belongs to a chapter that is no longer
  // loaded. The four hundred milliseconds a swap steps over are rendered
  // silence and were never listened to; counting them would be the only thing
  // a chapter boundary ever handed the guard.
  playedFrom = null;
  drawPlayer();
  publishPosition();
  // A boundary is a good place to be interrupted at, and the position either
  // side of one differs by a whole chapter. At boot this says nothing, because
  // opening the app has not moved anything.
  sendPosition("chapter");
});

player.addEventListener("timeupdate", () => {
  // While a swap is in flight currentTime can still be reading from the
  // chapter being left, which would report a position they are no longer at.
  if (swapping || !current) return;
  positionMs = toGlobalMs(current.chapter, player.currentTime);
  // Sound came out between the last sample and this one, and this is the only
  // place in the page where that is true: the media clock moves by itself here
  // and is moved by hand everywhere else. Forwards only, and only from a
  // sample left behind by the file still loaded — a rewind is not negative
  // listening, and a baseline that was set aside by a seek or a swap is not a
  // distance anybody heard.
  if (playedFrom !== null && positionMs > playedFrom) {
    playedMs += positionMs - playedFrom;
  }
  playedFrom = positionMs;
  // Both of these are here rather than above the guard so that neither can
  // land in the middle of a chapter change: a fade that finished mid-swap
  // would pause an element that is between two sources, and the pause it
  // caused would be swallowed as the spurious one a src assignment fires.
  // A swap costs a few hundred milliseconds of a twenty-second fade.
  stepFade();
  countDownToSleep();
  drawPlayer();

  // At most once a second. The platform interpolates between these from the
  // playback rate it was given, so telling it more often buys nothing and
  // every one of them is a hop out of the page.
  const now = Date.now();
  if (now - lastPublishedAt >= 1000) {
    lastPublishedAt = now;
    publishPosition();
  }
  if (!player.paused && now - lastSentAt >= HEARTBEAT_MS) sendPosition("tick");

  // Not while the night is set to end here: the whole of what "end of chapter"
  // asks for is that this boundary is not crossed.
  const next = sleepsAtChapterEnd() ? null : manifest.chapters[current.idx + 1];
  const left = player.duration - player.currentTime;
  if (next && !player.paused && Number.isFinite(left) && left <= SWAP_LEAD_S) {
    showChapter(locate(next.start_ms), { play: true });
  }
});

player.addEventListener("seeked", () => {
  if (swapping || !current) return;
  positionMs = toGlobalMs(current.chapter, player.currentTime);
  drawPlayer();
  publishPosition();
  // A jump is the one thing the fifteen-second heartbeat cannot approximate:
  // between one tick and the next they may be an hour away.
  sendPosition("seek");
});

player.addEventListener("play", () => {
  untouched = false;
  // From here the sound is meant to be on, and anything that takes it away is
  // something to get back from rather than something that happened.
  wantsSound = true;
  // The timer measures listening, so it starts counting from here and not from
  // whenever it was last looked at.
  sleepCountedAt = Date.now();
  // Belt and braces on the invariant that a paused player is at full volume:
  // whatever route the sound came back by, it must not come back inaudible.
  if (!fade && player.volume < 1) startFade(1, FADE_IN_MS);
  reportPlaybackState("playing");
  drawPlayer();
  publishPosition();
  // Where the sound came back on, which is the beginning of a stretch of
  // listening. The spoiler guard advances on time that really elapsed with the
  // sound on, so a stretch with no beginning gives it nothing to measure the
  // first heartbeat against and it stops for the rest of the book. Not during a
  // chapter swap: the position is between two files there, and the report at
  // the far side of the swap says the same thing a moment later.
  if (!swapping) sendPosition("play");
});

// Nothing changes the rate yet. The handler is here because the platform
// interpolates the scrubber from the rate it was last given, so the one thing
// that must never happen is a rate change it never hears about.
player.addEventListener("ratechange", publishPosition);

player.addEventListener("pause", () => {
  // A pause means four different things and only one of them is theirs.
  // Assigning src runs the media element load algorithm, which fires one;
  // reaching the end of a chapter fires one before `ended`, per spec; and a
  // chapter that fails to load fires `error` and then a pause after it.
  // Treating any of those as the listener stopping announces that something
  // took the sound at every chapter boundary, and writes that over the true
  // reason in the one case where there is a true reason to give.
  //
  // The guard is also what keeps the notification whole across a boundary:
  // reporting "paused" mid-swap is the platform's cue that the book stopped,
  // and it redraws the button, or worse decides the page is finished with the
  // sound. The state only ever changes here for a pause that really happened.
  if (swapping || player.ended || player.error) return;
  // A pause that got this far is one somebody made — a thumb, the lock screen,
  // the sleep timer, or an alarm taking the sound. None of them is a network to
  // fight, and the retry above stops for all of them.
  wantsSound = false;
  outOfTrouble();
  // How long the sound has been off is the whole of what the resume knows, so
  // it is written down before anything else can take time over it.
  lastPauseAt = Date.now();
  endFade();
  reportPlaybackState("paused");
  drawPlayer();
  publishPosition();
  // Someone who pauses at 2am may not touch the phone again for a week, so
  // this is the position that has to be right, and it is worth a request of
  // its own however recently the last one went.
  sendPosition("pause");
  // While the connection is still warm. If this pause turns out to have been
  // the end of the night, the answer is what stops the morning starting in the
  // middle of a sentence.
  rememberTheSentence();
  if (!weArePausing) {
    // Audio focus went elsewhere: a call, an alarm, another app. Do not
    // resume. An alarm should stop the book, not be talked over.
    setStatus("something else took the sound");
  }
  weArePausing = false;
});

player.addEventListener("ended", () => {
  // The backstop. The lead above normally takes the boundary first; this is
  // for a chapter whose duration never became a number, or a file that runs
  // out sooner than the database says it should. `ended` decides that a
  // chapter is over, never the clock: a truncated encode becomes a skip rather
  // than a book that hangs at 2am.
  if (swapping || !current) return;
  positionMs = current.chapter.end_ms;
  const next = manifest.chapters[current.idx + 1];
  const goodnight = sleepsAtChapterEnd();
  if (next && !goodnight) {
    showChapter(locate(next.start_ms), { play: true });
    return;
  }
  // The sound has stopped, whichever of the three reasons it was. A chapter
  // ending is its own fade — ingest leaves half a second of silence at the end
  // of every one, and the last words of a chapter are a place a book means to
  // be put down — so this way of stopping needs no fading at all.
  //
  // The pause that came with this was swallowed as spurious, quite rightly, so
  // everything that pause would have done has to happen here instead: writing
  // down when the sound stopped, because the morning's rewind is measured from
  // it, and saying so, because otherwise the lock screen goes on offering a
  // pause button for a book that is not playing.
  endFade();
  lastPauseAt = Date.now();
  rememberTheSentence();
  reportPlaybackState("paused");
  sendPosition("ended");
  // gid is null for a book the server has said is gone: there is nothing left
  // to ask about it, and the answer would never change.
  if (!next && !goodnight && gid !== null && manifest.status === "rendering") {
    // Not the end of the book — the end of what has been read of it so far.
    // Saying otherwise here is the lie somebody would act on: they added the
    // book at eleven, chapter one was playable in minutes, and the night ends
    // three chapters into forty-nine with the sleep timer thrown away.
    awaitMore(gid, { play: true, at: current.idx });
    drawPlayer();
    return;
  }
  // Not rendering, and not all here either: a render that was stopped, or that
  // died, or that a deploy shot in the head. Nothing is coming while nobody
  // asks for it, so there is nothing to wait for — but this is still not the
  // end of the book, and saying it was would end the night on a lie somebody
  // would act on. The sleep timer and the fight to keep the sound going are
  // left exactly as they are, because neither has anything to do with the
  // render having stopped.
  if (!next && !goodnight && moreToCome()) {
    setStatus("the rest of this book hasn't been read yet");
    drawPlayer();
    return;
  }
  setStatus(goodnight ? "goodnight" : "that is the end of the book");
  // Nothing is coming. Anything still trying to get the book back is trying for
  // nobody now.
  wantsSound = false;
  clearSleep();
  drawPlayer();
});

player.addEventListener("error", () => {
  // Whatever went wrong, the state machine must not be left mid-swap: with
  // `swapping` stuck on, every later boundary would be ignored.
  swapping = false;
  pendingOffsetMs = null;
  // Same reason as at the end of the book: the pause that follows an error is
  // swallowed, and a notification still showing a pause button for silence is
  // a lie they would have to unlock the phone to see through.
  reportPlaybackState("paused");
  drawPlayer();
  console.error(player.error);
  // Nobody can tell from here whether this is the night ending or five seconds
  // of it, so the page assumes the kinder one for as long as the sound was
  // meant to be on, and keeps trying. A book they had already put down is left
  // where they put it.
  if (!wantsSound) {
    setStatus("that chapter didn't arrive");
    return;
  }
  inTrouble("the book stopped arriving");
  retryLater();
});

playpause.addEventListener("click", () => {
  if (player.paused) ensurePlaying({ rewind: true });
  else pauseHere();
});
const nudge = (seconds) => seekGlobal(positionMs + seconds * 1000);
back30.addEventListener("click", () => nudge(-SEEK_STEP_S));
fwd30.addEventListener("click", () => nudge(SEEK_STEP_S));

// Five seconds in, "previous" means the start of this chapter — what it means
// on every music player anyone has used, and the more forgiving of the two
// answers for a thumb that missed. On the first chapter it is the only answer
// there is, which is why the check is for a previous chapter existing and not
// for the index being zero.
function toPreviousChapter() {
  if (!current) return;
  const previous = manifest.chapters[current.idx - 1];
  const into = positionMs - current.chapter.start_ms;
  seekGlobal(
    into > CHAPTER_RESTART_MS || !previous
      ? current.chapter.start_ms
      : previous.start_ms,
  );
}

function toNextChapter() {
  const next = current && manifest.chapters[current.idx + 1];
  if (next) seekGlobal(next.start_ms);
}

// The same two functions the lock screen and a Bluetooth remote call, so the
// button on the page and the button on a pillow speaker cannot drift apart.
prevChapter.addEventListener("click", toPreviousChapter);
nextChapter.addEventListener("click", toNextChapter);

// All eight of them, whether or not this phone has anything to press. Android
// only surfaces the buttons it has a handler for, so an unregistered nexttrack
// is a pillow speaker whose skip button does nothing at all, and finding that
// out means being awake enough to test it.
function listenForRemoteControls() {
  if (!session?.setActionHandler) return;
  const handle = (action, fn) => {
    try {
      session.setActionHandler(action, fn);
    } catch {
      // A browser that has never heard of this action refuses to take it.
      // That is one button that will not appear, not a reason to stop.
    }
  };
  // The lock screen and a button on a pillow speaker are the same press as the
  // one on this page, made by the same person, and get the same few seconds
  // back — most of the night this is the only one of the two they can reach.
  handle("play", () => ensurePlaying({ rewind: true }));
  handle("pause", () => pauseHere());
  // Stop pauses, and does nothing else. The obvious reading — release the
  // sound, clear the element — is the documented way to dismiss the media
  // notification, and dismissing it face down in a pocket is the one state
  // this page cannot recover from.
  handle("stop", () => pauseHere());
  // The platform says how far it wants to go, and only falls back to our idea
  // of "a bit" when it has no opinion. Both go through the global timeline, so
  // a nudge back from the first seconds of a chapter lands in the one before,
  // which is what "back a bit" means to someone who is listening to a book and
  // not to a pile of files.
  handle("seekbackward", (d) => nudge(-(d?.seekOffset ?? SEEK_STEP_S)));
  handle("seekforward", (d) => nudge(d?.seekOffset ?? SEEK_STEP_S));
  // seekTime comes back on the scale we published, which is this chapter's.
  // This is the one place it is put back on the book's clock.
  handle("seekto", (d) => {
    if (!current || typeof d?.seekTime !== "number") return;
    seekGlobal(current.chapter.start_ms + d.seekTime * 1000);
  });
  handle("previoustrack", toPreviousChapter);
  handle("nexttrack", toNextChapter);
}

listenForRemoteControls();

// ------------------------------------------------------- where they have got to

// The page is the only thing that knows where the sound is while it plays, so
// saying so is not bookkeeping — it is the whole of somnia's memory of the
// night. Everything below is driven by media events for the reason given at
// HEARTBEAT_MS: with the screen off, they are the only events still arriving.

function positionBody(reason) {
  return {
    // Not authentication — there is none here by design. It is so the journal
    // can say which page wrote what.
    token,
    gid,
    position_ms: Math.round(positionMs),
    seq,
    // How much of the book has really played since the last report the server
    // took, which is what the spoiler guard measures this one against. A
    // stretch they listened to moves this by as much as it moves the position;
    // a skip, an agent move or a scrub moves the position and not this. Saying
    // it rather than leaving the server to infer it from the clock is the
    // whole of the difference between the two: the server cannot see a phone
    // that spent four minutes asleep with the sound off, and this page cannot
    // help seeing it.
    played_ms: Math.max(0, Math.round(playedMs - playedTaken)),
    reason,
  };
}

function postPosition(body, { keepalive = false } = {}) {
  return fetch("api/position", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    keepalive,
  });
}

// One at a time, and never retried. A retry delivers a stale position over a
// newer one, and the next heartbeat carries better truth anyway; what must not
// happen is the LAST position being the one that got dropped, which is what
// `owed` is for. It remembers only that something is owed, and the body is
// built afresh when it goes out, so what lands is where they are now.
function sendPosition(reason) {
  if (untouched || !manifest || gid === null) return;
  if (sending) {
    owed = reason;
    return;
  }
  sending = true;
  // Counted from when it went out, not from when it came back: gating the
  // heartbeat on the reply would turn a phone with no signal into a request
  // every few hundred milliseconds, which is the one thing a battery cannot
  // afford at 4am.
  lastSentAt = Date.now();
  // What this report is about to claim, held while it is in flight. Playback
  // that goes out and is not taken has to still be owed when the answer comes
  // back, and by then more of it may have happened.
  const claimed = playedMs;
  // Backgrounded, and the page may be frozen a moment later. keepalive is what
  // lets the request finish without one.
  postPosition(positionBody(reason), { keepalive: reason === "hidden" })
    .then((response) => response.json())
    .then((body) => {
      // Never backwards. A seek gives up whatever was owed at the moment it
      // happens, and an acknowledgement for a report that went out before it
      // would otherwise put that playback back and hand it to the jump.
      if (body?.accepted) playedTaken = Math.max(playedTaken, claimed);
      applyReply(body);
    })
    .catch((error) => console.error(error))
    .finally(() => {
      sending = false;
      const next = owed;
      owed = null;
      if (next) sendPosition(next);
    });
}

// The last word on a book the page is about to stop being on, sent while gid
// is still that book's. Nothing else would ever say it: the pause a swap fires
// is swallowed as spurious, quite rightly, so a book left behind would keep
// whatever position its last heartbeat happened to catch — up to fifteen
// seconds of a book they were listening to a moment ago.
//
// It goes round sendPosition rather than through it. That one holds a report
// back while another is in flight and builds the body when its turn comes, and
// by then this body would be the book they left written against the gid of the
// one they are now on. Its reply is dropped for the same reason: a refusal
// here is about a book the page has already left, and following it would take
// them straight back to it.
//
// It carries the playback that belongs to this book with it, which is the last
// chance to say it: the stretch between the last heartbeat and here was really
// listened to, and a mark left behind the position they were left at would
// refuse everything they play the next time they open this book. Nothing here
// can hear it being taken, so openBook gives it up on this page's behalf a
// moment later rather than letting the next book claim it too.
function sendPartingPosition() {
  if (untouched || !manifest || gid === null) return;
  postPosition(positionBody("switch")).catch((error) => console.error(error));
}

function applyReply(body) {
  if (!body || body.accepted) return;
  // A refusal answers the report that asked, and that report may be about a
  // book the page has since left: switching books leaves one in flight, and
  // reading its refusal as "go here" would re-open the book they were just
  // taken out of. Only a refusal about the book the page is on has anything to
  // say to it.
  if (body.gid !== gid) return;
  // The agent moved the book while this page was not looking. That is the only
  // thing that can refuse a report, and the refusal says where to go.
  if (body.reason === "moved") follow(body);
  if (body.reason === "gone") {
    // The book is not in the database any more. Whatever is still in the
    // element can play out, but there is nothing left to write to.
    setStatus("that book isn't here any more");
    // And a list of places in it is a list of promises the page can no longer
    // keep: every row would go and fetch a book that has been deleted and come
    // back with "couldn't reach that book". Only when it is that book's list —
    // an offer about some other book is still perfectly good.
    if (offered?.gid === body.gid) closeCandidates();
    gid = null;
  }
}

// The agent decided where the book should be. It arrives by two routes — the
// reply to the question that caused it, and the refusal of the next report —
// and they are the same function because whichever gets here first should win
// and losing either should cost nothing.
function follow(move) {
  if (!move || typeof move.seq !== "number") return;
  if (move.gid !== gid) {
    // A different book. The move was written before the answer came back, so
    // that book's manifest already carries the new position and the new count:
    // opening it *is* following it, and there is nothing else to apply.
    openBook(move.gid, { play: true }).catch((error) => {
      setStatus("couldn't reach that book");
      console.error(error);
    });
    return;
  }
  // Our own book. Our reports never raise the count, so a number higher than
  // the one we hold can only be a move this page has not applied — and one that
  // is not higher has already been applied by the other route.
  if (move.seq <= seq) return;
  seq = move.seq;
  if (typeof move.position_ms !== "number") return;
  // They asked to be taken somewhere, so take them there and play it.
  // Reproducing "now press play yourself" in JavaScript would be a joke.
  seekGlobal(move.position_ms, { play: true });
}

// ------------------------------------------------------ places you might be

// Some questions have more than one answer, and the old way of saying so was a
// conversation: "did you mean the one an hour in, or the one at four hours?"
// read in the dark, by someone half asleep, and answered by typing. This is
// that conversation as a list of times a thumb can point at.
//
// It is an overlay and not a screen. The book plays underneath the whole time,
// nothing has been moved, nothing has been written, and every way out leaves
// the page in a state it was already able to be in. Choosing a row is a seek —
// the same code path as −30, made by the same person — and not a request to the
// server: a chosen row bumps no position_seq, so routing it through follow()
// with an invented count would either do nothing at all or leave this page
// holding a number the database has never had, after which every report for the
// rest of the night is refused and the refusal drags them backwards. The server
// finds out at once anyway, by the route every other seek takes: the element
// fires `seeked` and sendPosition("seek") goes out behind it.
//
// The words matter more than the times. Half of the point of a list rather than
// a sentence is that they read the book's own sentence and recognise it — but a
// place they have not reached yet cannot show its words, or its chapter title
// ("How Ginger Died" is as much of a spoiler as the paragraph under it), so
// those rows say only when they are and that they are ahead, and offer a press
// to find out more.
//
// Going somewhere and finding out what is there are different decisions, and a
// row is two targets rather than one: the reading, which is the whole left of
// the row, and `goto`, which is a pill on the right. Which of the two is the
// bigger one is the ruling this list turns on. It used to be the jump — the row
// itself was the button and the reveal was a small dashed thing under it — and
// that is the wrong way round for a screen read at 2am. The press wanted most
// often is "what is there?", it is the one that can be taken back, and the one
// that cannot be taken back is the one that should have to be aimed at. So the
// reveal is the row and `goto` is the pill beside it. Nothing about that
// changes what either press does: revealing still moves no playback and tells
// nobody, and it is still not possible to arrive somewhere by asking what is
// there.
//
// What the design asked for and this list does not have: a reason per row
// ("most likely · fits what you said") and a source per row ("you paused here,
// awake", "sleep timer faded out here"). The agent returns neither and there is
// nowhere in somnia either could be read from, so neither is drawn. A list of
// places is the one screen on this page where a plausible sentence nobody has
// evidence for is a lie a thumb then acts on.

// The offer currently on screen, or null. It holds the only copy in the page of
// the words of a place they have not heard yet, which is why it is a variable
// and not a rendered thing: those words are never written into the DOM until
// the reveal press, never logged, never passed to say(), and are gone from the
// page entirely the moment the list closes.
//
// It used to be the only copy anywhere, and the comment here used to say so — a
// page discarded with the list up came back with no list, and asking again was
// one press. Asking again is a question put to a model over a tailnet at 2am,
// which is the thing this page exists to spare somebody, so the list is written
// down as well now: see PLACES_KEY below. What closes still forgets what was on
// the screen; what a night keeps is the answer, not the overlay.
let offered = null;

// The last places somnia offered, kept where a discarded tab cannot take them.
//
// Places is the set of places from the last query and nothing else. It is not a
// store of pause points or fade points: somnia already produces exactly this
// list, once, in answer to a question asked in the dark — and until now it
// lived as long as the overlay did, so getting back to the third of four places
// meant asking the same question again.
//
// localStorage, beside the sleep timer and the dim level, and for the same
// reason as the timer: the tab is the thing that does not survive the night. A
// backgrounded page is discarded whenever the phone wants the memory back, and
// the list went with it.
//
// One entry, carrying the gid of the book it is about. A list about a book that
// is not the one open is no places at all — which is what keeps this from
// growing without bound, and what keeps the screen scoped to the book somebody
// is listening to.
//
// It holds the words of places they have not heard yet, and that is worth
// saying out loud. Those words came down with the answer, to this phone, on
// this night; what changes is that they now rest in a key between sessions
// rather than dying with the tab. No new exposure — same device, same answer —
// and whether they ever reach the screen is still the reveal press's decision
// and nobody else's.
const PLACES_KEY = "somnia-places";

// What would be put back on the screen, or null. `offered` is what is on it
// now: the two are the same list while Places is up, and different the moment
// it closes, because closing forgets the screen and this outlives the night.
let remembered = null;

// `start over` throws away the conversation, and the places are an answer to a
// question in it — so they go with it. The comment over startOver draws the line
// this side of: the questions, not the night. The book keeps playing, keeps its
// position and keeps its timer; what is forgotten is everything that was said.
//
// Without this the position line goes on saying `4 places found` after the
// server has been told to forget the question that found them, and pressing it
// opens a list somebody can no longer see the reason for. That is not the same
// case as a confident move, which leaves the list standing on purpose: there the
// conversation is still there to explain it.
function forgetPlaces() {
  remembered = null;
  drawPlaces();
  try {
    localStorage.removeItem(PLACES_KEY);
  } catch (error) {
    console.error(error);
  }
}

function rememberPlaces(list) {
  remembered = list;
  // The position line says how many places there are, and this is the moment
  // there is a different number of them. Waiting for the next pass of
  // drawPlayer would be waiting for the book to play: a page that was only ever
  // opened to ask a question is paused, so nothing else would come, and closing
  // the screen would leave the line saying nothing about the list behind it.
  drawPlaces();
  try {
    localStorage.setItem(PLACES_KEY, JSON.stringify(list));
  } catch (error) {
    // Storage refused, or is full. Places is a convenience over a question that
    // can always be asked again, so nothing else here has to care.
    console.error(error);
  }
}

// What the last page to be alive put in front of somebody. Anything else in
// that key reads as no places rather than as a reason to throw: this runs at
// boot, before there is a screen to say anything on, and the one thing the page
// opening at 2am has to do is open.
function restorePlaces() {
  let saved = null;
  try {
    saved = JSON.parse(localStorage.getItem(PLACES_KEY) || "null");
  } catch (error) {
    console.error(error);
  }
  if (!saved || typeof saved.gid !== "number") return;
  if (!Array.isArray(saved.places) || !saved.places.length) return;
  // Every row is drawn out of these three and a press acts on the first of
  // them, so a record missing any one is a screen of rows reading "Ch NaN" with
  // a goto that seeks to nowhere.
  const whole = saved.places.every(
    (place) =>
      place &&
      typeof place.start_ms === "number" &&
      typeof place.chunk_id === "number" &&
      typeof place.chapter_idx === "number",
  );
  if (whole) remembered = saved;
}

// The remembered list, but only where it is about the book that is open. A list
// about another book is not a wrong list to draw, it is the answer to a
// question about somewhere else, and there is nothing on the position line that
// could say so.
function placesHere() {
  return remembered && gid !== null && remembered.gid === gid
    ? remembered
    : null;
}

// The way back to the last query's places. It goes through showCandidates, the
// same path the answer that first raised them took, because a list restored
// straight into the DOM would be markup: the words of a place they have not
// reached are held in a closure by candidateRow, and chooseCandidate acts on
// `offered` rather than on rows — so a screen built any other way would look
// right and do nothing when pressed.
//
// Nothing here refreshes anything, and a stale `ahead` flag is why that is
// safe. The server decided it against its own mark when the offer was made, and
// that mark only ever rises: a place stored as ahead may since have been
// listened to, and one stored as heard can never have become unheard. So age
// can only over-warn, which costs a press — and the other direction is the one
// thing this page must never do.
function showRemembered() {
  const list = placesHere();
  if (list) showCandidates(list);
}

// The position line, which is the way in when there is anywhere to go and a
// plain readout when there is not.
//
// `disabled` on the nights there are no places, and that is the whole of the
// argument for putting this on a line that already exists rather than giving
// Places a control of its own: after a cold launch on a book nobody has asked
// about there is nothing to open, and a line wearing a rule and a target that
// answered a press by doing nothing is worse in the dark than no way in at all.
// The rule and the count are drawn from the same number, so "does it look
// pressable?" and "is there anything to press?" cannot come apart.
//
// The count is emptied as well as hidden, for the reason the toast is: "is
// anything being offered?" gets one answer and not two that can disagree.
function drawPlaces() {
  const list = placesHere();
  const found = list ? list.places.length : 0;
  // One place is not counted as though there were more, which is the rule the
  // screen this opens already follows: it is the same list said in fewer words.
  placesFound.textContent = found
    ? `${found} ${found === 1 ? "place" : "places"} found`
    : "";
  placesFound.hidden = found === 0;
  placesOpen.disabled = found === 0;
  placesOpen.classList.toggle("openable", found > 0);
}

// Pressed, it puts the last query's places back on the screen. It is the same
// screen an answer raises and every way out of it is the one that was already
// there — including close, which now leaves the count standing behind it,
// because the places did not stop existing when the screen was put away.
placesOpen.addEventListener("click", showRemembered);

// Whether cancel owes the page a tap-to-resume listener, because showing the
// list took one away. See cancelCandidates.
let rearmOnCancel = false;

// Where the book is on this book's clock, drawn into the list so that a glance
// says which rows are behind them and which are ahead. That is the whole point
// of the row: "ahead" as a word is a claim, and a time among other times is
// something anyone can check.
//
// For the book that is open it is this page's own number, because the page is
// the player and the server's copy is up to fifteen seconds stale; for a book
// that is not, it is whatever the server last wrote down. Null means nobody has
// ever started that book, and then there is no row at all — "never started" and
// "at 0:00:00" are different answers, and only one of them would be true. A
// book that is open but untouched reads 0:00:00 here, which is what the clock
// under the transport says as well, so at worst the two agree.
function hereTime(list) {
  return list.gid === gid && manifest ? positionMs : list.position_ms;
}

function chapterLabel(place, { title }) {
  const chapter = `Ch ${place.chapter_idx + 1}`;
  // Ingest numbers chapters from one and so does everybody counting them; the
  // index in the row is zero-based. A book whose chapters were never titled
  // gets the number and nothing else rather than a trailing separator.
  const parts = [chapter];
  if (title && place.chapter_title) parts.push(place.chapter_title);
  if (place.ahead) parts.push("ahead");
  return parts.join(" · ");
}

// What the list is, said in one line above it, and out of nothing but the
// payload that drew the rows. It counts what is on the screen and names the
// first and last time on it — no denominator, because somnia has no idea how
// many places in this book would have fitted the question, and "4 of 7" with a
// 7 nobody counted is a number that would be read and believed.
function candidatesSummary(places) {
  if (!places.length) return "";
  const first = timestamp(places[0].start_ms);
  if (places.length === 1) return `1 place, at ${first}`;
  const last = timestamp(places[places.length - 1].start_ms);
  return `${places.length} places between ${first} and ${last}`;
}

function candidateRow(place) {
  const li = document.createElement("li");
  li.className = place.ahead ? "candidate ahead" : "candidate";

  // Everything known about the place, and the whole left of the row. It is a
  // button only where something is being withheld: on a place they have already
  // heard there is nothing left to ask for, so the words are simply there and
  // the reading is not a control at all. A target that answers a press by doing
  // nothing is worse in the dark than no target — it reads as a page that has
  // stopped responding.
  const show = document.createElement(place.ahead ? "button" : "div");
  show.className = "candidate-show";
  if (place.ahead) {
    show.type = "button";
    show.id = `candidate-show-${place.chunk_id}`;
  }

  const line = document.createElement("p");
  line.className = "candidate-line";

  const when = document.createElement("span");
  when.className = "candidate-when";
  when.textContent = timestamp(place.start_ms);

  const where = document.createElement("span");
  where.className = "candidate-where";
  where.textContent = chapterLabel(place, { title: !place.ahead });

  line.append(when);
  line.append(where);

  const what = document.createElement("p");
  what.className = "candidate-what";
  // A place ahead of where they have listened starts with nothing in it at
  // all — not hidden text, no text. Held in the closure below instead, so that
  // a screen reader cannot read it out, a selection cannot catch it, a
  // screenshot cannot contain it and a scroll cannot bring it into view. The
  // server decided which of those this is; the page does not recompute it and
  // has no opinion about how far they have listened.
  if (place.ahead) what.hidden = true;
  else what.textContent = place.text;

  show.append(line);
  show.append(what);

  if (place.ahead) {
    // The only line on the page that says what a press will cost. Amber,
    // because amber on this page is the warm thing and a warning is one, and
    // said in the row rather than under the list: whether the words are worth
    // uncovering is a question about this place and not about the screen.
    const hint = document.createElement("p");
    hint.className = "candidate-hint";
    hint.textContent = "tap to reveal · may spoil";
    show.append(hint);
    // Five writes to this row's own DOM and nothing else in the whole page: no
    // request, no seek, no report, nothing touched that the spoiler guard
    // measures. The words came down with the answer and were already in hand,
    // which is why there is no endpoint here to fetch them from — a general
    // /api route handing back unheard book text for any chunk id would be a
    // spoiler oracle one guessed integer wide, sitting there for the life of
    // the deployment, and it would put a tailnet round trip on the one press
    // where a control that does nothing for three seconds reads as broken and
    // gets pressed again — with a list on screen, into a row.
    show.addEventListener("click", () => {
      // Once. A second press on a revealed row is a thumb that has already got
      // what it asked for, and the one thing it must never do is put the words
      // back — a reveal that toggled would be a control whose meaning depends
      // on how many times it has been pressed, read by somebody who is not
      // counting.
      if (li.classList.contains("revealed")) return;
      what.textContent = place.text;
      what.hidden = false;
      // The title arrives at the same press and never before it.
      where.textContent = chapterLabel(place, { title: true });
      // The warning has been heeded and is over. What is left saying the row is
      // ahead of them is the word in the chapter line, which stays.
      hint.hidden = true;
      li.classList.add("revealed");
    });
  }
  li.append(show);

  // The other target, and the smaller one on purpose: it is the press that
  // cannot be taken back. 60dp of pill, and the nearest other `goto` is 52px
  // below it — the row's padding twice over and the hairline between, none of
  // which listens for a press. The reveal sits beside the pill and never under
  // it, so nothing catches a low miss except that distance; style.css keeps it,
  // and `.candidate`'s padding is not a spacing choice to be tuned.
  const go = document.createElement("button");
  go.type = "button";
  go.className = "candidate-go";
  go.id = `candidate-go-${place.chunk_id}`;
  // Not "jump": at this size and in this position "jump" reads like the ±30
  // below, and this moves the whole book.
  go.textContent = "goto";
  go.addEventListener("click", () => chooseCandidate(place));
  li.append(go);
  return li;
}

// Not a row and not somewhere to go: a rule drawn across the list at the point
// they have got to. `more` is whether there is anything under it — the sentence
// beneath the rule is about what follows it, and printed with nothing following
// it, it would be a warning about an empty screen.
function hereRow(ms, { more }) {
  const li = document.createElement("li");
  li.className = "candidate here";
  li.setAttribute("aria-current", "true");
  // One string, mono and small: it is a label on a rule rather than something
  // to read, and it is the only place on this screen that is not a place.
  const mark = document.createElement("p");
  mark.className = "section-label here-mark";
  mark.textContent = `you are here · ${timestamp(ms)}`;
  li.append(mark);
  if (more) {
    const caveat = document.createElement("p");
    caveat.className = "here-caveat";
    caveat.textContent = "anything below this line you may not have heard";
    li.append(caveat);
  }
  return li;
}

function showCandidates(list) {
  offered = list;
  // Written down here rather than where the answer arrives, so that what a
  // night remembers is what was actually put in front of somebody: an answer
  // that knew where they meant moved the book and offered nothing, and it
  // leaves the last real list standing.
  rememberPlaces(list);
  candidateList.replaceChildren();

  // Which book, but only when it is not the one playing.
  const elsewhere = list.gid !== gid;
  candidatesBook.textContent = elsewhere ? `in ${list.title}` : "";
  candidatesBook.hidden = !elsewhere;
  summaryLine.textContent = candidatesSummary(list.places);

  const rows = list.places.map(candidateRow);
  const here = hereTime(list);
  if (typeof here === "number") {
    // Spliced in among them in book order, which is the only arrangement that
    // answers the question the list is for without reading a word: everything
    // below this line has not happened yet. The server sorted the places; this
    // is the one row the page decides the place of, and it is painted once and
    // never updated — a number moving under a finger is worse than a number
    // that is a moment old.
    const at = list.places.findIndex((place) => place.start_ms > here);
    const mark = at < 0 ? rows.length : at;
    rows.splice(mark, 0, hereRow(here, { more: mark < rows.length }));
  }
  for (const row of rows) candidateList.append(row);

  candidates.hidden = false;
  // Giving focus up, never taking it. The keyboard is up on exactly the turns
  // that produce a list — they just typed a question — and half the screen
  // being keyboard is how the cancel button ends up somewhere a thumb cannot
  // reach. Nothing here calls focus() on anything: this page does not move the
  // cursor around under people.
  question.blur?.();
  // A book waiting for a touch before it will make a sound would otherwise
  // start on the first press anywhere on this overlay — a row, a reveal, or
  // cancel. Cancel especially: the one control that promises to change nothing
  // would have started the night. Taken off while the list is up and given back
  // by cancel, which is the only way out that leaves the page as it found it.
  rearmOnCancel = tapToResume !== null;
  disarmTapToResume();
}

// The inert close. Everything that takes the list down goes through here, and
// it does nothing but forget: no seek, no report, no request, nothing said, and
// nothing touched that the spoiler guard or the sleep timer can see.
function closeCandidates() {
  candidates.hidden = true;
  // The rows, and with them any words a reveal press put on the screen.
  candidateList.replaceChildren();
  // The line that counted them goes with them. It is only times and a number,
  // but a subhead left standing over an empty list is the page describing
  // something that is not there.
  summaryLine.textContent = "";
  // And the words it did not: the only other copy in the page.
  offered = null;
}

// Cancel, and only cancel. It is three assignments and at most one listener put
// back, and that is the whole of it: no move, no report, no seq bump, no write
// to Audiobookshelf, and nothing said on the status line.
//
// The button says `close` now and this still is the cancel. `cancel` was the
// word while the list read as a question with an answer owed; it is a screen of
// places now, and a screen is left rather than called off. Nothing under the
// word changed — it is still the one way out that gives back the tap the list
// took, and still the only one that has to.
//
// What it deliberately does not undo, because none of it was the list's doing:
// a sleep fade running underneath keeps running, and if it finishes the book
// still goes quiet and still says goodnight — the night was already ending and
// a question about where to go did not change that, so putting the question
// away must not either. Nor does it give back the countdown, which has been
// running the whole time the list was up because the book was playing and they
// were listening to it. A list left up long enough ends the night by itself.
// That looks like a bug and is not one.
function cancelCandidates() {
  const rearm = rearmOnCancel;
  rearmOnCancel = false;
  closeCandidates();
  // True before the list went up and true again now: the book is still paused,
  // still waiting for a touch, and the line that said so was taken down with
  // the listener rather than left lying.
  if (rearm) armTapToResume();
}

candidatesCancel.addEventListener("click", cancelCandidates);

// A row is a seek somebody made, in the book they made it in.
async function chooseCandidate(place) {
  const list = offered;
  if (!list) return;
  // First, so that nothing between here and the seek can leave a list of places
  // over a book that has already gone to one of them.
  closeCandidates();
  if (list.gid === gid && manifest) {
    if (place.start_ms > manifest.total_ms) {
      // The manifest is older than the render: this book grew while the page
      // was holding a photograph of it, and seeking would clamp them to the
      // frontier instead. Only in that case — an unconditional refresh would
      // put a network round trip in front of every press, which is the one
      // thing a transport action on this page never does. The seek happens
      // either way: a refresh that failed leaves them where the page thinks
      // the book ends, which is still nearer than not moving at all.
      await refreshManifest().catch(() => {});
    }
    seekGlobal(place.start_ms, { play: true });
    // On the line after the seek, and never on a timer. The design's prototype
    // waits ~900ms and then says this, which on a real page is a sentence that
    // can outlive what it describes: the agent can move the book by the other
    // route — the refusal of the next report — inside that window, and a toast
    // fired afterwards would be telling them about a press whose effect has
    // been overwritten. Said here it is true when it is written, or it is not
    // written.
    toast("moved · playing");
    return;
  }
  // Another book, which has had nothing written to it: `at` is what carries the
  // chosen place through the switch. If that book is still rendering, openBook
  // waits for its first chapter and the chosen place is lost — said plainly on
  // the status line rather than engineered around, because threading a position
  // through a wait that can last a quarter of an hour is a promise this page
  // cannot keep.
  try {
    await openBook(list.gid, { play: true, at: place.start_ms });
  } catch (error) {
    setStatus("couldn't reach that book");
    console.error(error);
    return;
  }
  // Hung off the swap having happened, for the same reason as above, and it
  // really can not happen: a book whose first chapter has not been rendered yet
  // comes back from openBook having changed nothing but the status line, and
  // the page is still on the book it was on. "moved · playing" over a book that
  // did not move is the one thing a toast must never say.
  if (gid === list.gid) toast("moved · playing");
}

// Told once, as the page dies. fetch does not survive teardown — the document
// is gone before the connection is made — but a beacon is the browser's promise
// to deliver after the page has stopped existing. It is JSON in a Blob because
// that is the only way to give a beacon a content type, and it can read no
// reply at all, which is the other reason a refusal is a 200 with a body.
//
// Nothing can tell this page the beacon landed, so the playback it carries
// stays owed. A page that dies here never sends it again; a page frozen and
// then restored sends it twice, which is the cheaper way round — a stretch
// counted twice lets a jump of a few seconds through once, and a stretch
// dropped leaves the mark behind the position for the rest of the book.
window.addEventListener("pagehide", () => {
  if (untouched || !manifest || gid === null) return;
  const body = JSON.stringify(positionBody("unload"));
  navigator.sendBeacon?.(
    "api/position",
    new Blob([body], { type: "application/json" }),
  );
});

document.addEventListener("visibilitychange", () => {
  // Backgrounded, which on a phone is most of the night. Say so now: from here
  // on the page can be frozen or discarded without warning, and this is the
  // last moment a normal request is certain to be allowed out.
  if (document.visibilityState === "hidden") {
    sendPosition("hidden");
    saveSleep();
    // Nobody is looking at the books panel either, and a poll in a pocket is
    // both throttled to uselessness and a radio wake beside somebody asleep.
    stopQueuePoll();
    return;
  }
  // Back in front of them, and the phone may have been asleep for hours. Two
  // things could have changed while nothing here was running: the network, and
  // the book — a render that was three chapters in when the screen went off
  // can be twenty by now. Both are cheap to ask, and neither answers by itself.
  tryAgainNow();
  if (!awaiting && manifest?.status === "rendering") {
    refreshManifest().catch((error) => console.error(error));
  }
  // And if they left the panel up, whatever it is showing is as old as the
  // sleep was. Asked now rather than in five seconds, for the same reason as
  // the two above: coming back to the app is the moment somebody is looking.
  if (!queuePanel.hidden) pollQueue();
});

// `play` is false at boot and true only when the agent has just moved this
// book: opening the app at 2am to ask a question must not start the book, but
// being taken to a passage in a book that was not even open must.
//
// `at` is where in that book to land, and it exists for exactly one caller: a
// candidate chosen in a book that is not the one open. Everywhere else the
// position comes from the manifest, because by the time openBook is called the
// server has already written it — follow() gets away with opening a book and
// applying nothing for precisely that reason. A chosen row has had nothing
// written anywhere, so without this it would land wherever that book was last
// left. It is applied before the chapter is shown rather than seeked to
// afterwards: a seek onto an element whose src was assigned a moment ago finds
// readyState 0 and swaps the chapter a second time, which is two source
// assignments and the media notification built twice for one press.
async function openBook(id, { play = false, at = null } = {}) {
  const response = await fetch(`api/book/${id}`);
  if (!response.ok) throw new Error(`no book ${id}`);
  // Held to one side until it is known to be playable. Adopting it before the
  // check below left the element playing one book while every clock, seek and
  // boundary read another book's rows: the time said "of 0:00:00", locate()
  // threw on the next press of anything for the rest of the night, and the
  // chapter they were in ended with "that is the end of the book".
  const opening = await response.json();
  if (!opening.chapters.length) {
    // Rows but no audio: the book is still rendering, or the render died.
    // Whatever was playing is still playing, and still the book this page is
    // on, which is the only place left to be.
    if (opening.status === "rendering") {
      // The first chapter is minutes away. Left at that one sentence with the
      // player bar hidden, the page stayed that way for ever, on a book that
      // was playable a quarter of an hour later.
      awaitMore(id, { play });
    } else {
      // Nothing is running, so nothing is coming: the render died, or it never
      // started. Asking again all night would answer the same thing all night.
      stopAwaiting();
      setStatus("nothing to play yet");
    }
    return;
  }
  stopAwaiting();
  // This book is really being adopted now, so whichever book the list was drawn
  // against, it is not the one about to be open — and if it is, the position
  // those rows were drawn around is about to change. Either way the rows are
  // stale and the list goes with them.
  //
  // It is here and not at the top of the function on purpose. openBook is
  // called by the two ladders that ask again on a timer — the boot retry and
  // the wait for a book that is still being read — and neither of those is
  // somebody doing something. A page booted onto a rendering book holds no book
  // at all, which is exactly the state a list about some *other* book can be
  // raised in; from the top of the function, the five-second poll that found
  // nothing new tore that list out from under a thumb with nothing said, and
  // then did it again at ten seconds, and twenty, and on every unlock. A call
  // that adopts nothing must leave the screen alone, and a fetch that failed
  // must too.
  closeCandidates();
  if (gid !== null && gid !== opening.gid) sendPartingPosition();
  // Playback belongs to the book it happened in, and this page is starting
  // again from the server's own record of where that book is — which is what
  // the last report it took said, and so what the mark was raised to. Both
  // clocks restart together or neither does: carried across, the first report
  // of the new book would claim the last seconds of the old one as listening
  // in it, and thrown away without the position it goes with, the mark would
  // be left behind and refuse everything they played afterwards.
  playedTaken = playedMs;
  manifest = opening;
  gid = opening.gid;
  seq = opening.seq ?? 0;
  positionMs = at ?? opening.position_ms ?? 0;
  // Somebody chose this place, which is the same kind of act as a seek and is
  // worth writing down. Opening a book on its own is still not listening, so
  // this stays where it is rather than moving up to the top of the function.
  if (at !== null) untouched = false;
  playerBar.hidden = false;
  showChapter(locate(positionMs), { play });
}

async function openTheBook() {
  clearTimeout(bootTimer);
  bootTimer = 0;
  try {
    const response = await fetch("api/books");
    if (!response.ok) throw new Error("no book list");
    const listing = await response.json();
    const chosen = listing.last_gid ?? listing.books[0]?.gid;
    if (chosen === undefined) {
      // The state that most needs the panel, and the one with no book, no
      // manifest and no gid — so the nudge has to name the control rather than
      // relying on anything on the screen to be about a book.
      setStatus("nothing yet — press books to add one");
      return;
    }
    await openBook(chosen);
    // Reached the server and got a book out of it, so the next thing to go
    // wrong starts its waiting again from the short end.
    bootDelay = RETRY_MIN_MS;
  } catch (error) {
    console.error(error);
    // The service worker serves the shell from cache when the server cannot be
    // reached — on purpose, and it is the right call — so what somebody lands
    // on here is a page that looks perfectly alive with no book in it. Said
    // once and never tried again, it stayed that way until they thought to kill
    // the app and open it afresh, and the 2am screen took away the pull to
    // refresh that was the one gesture that would have fixed it by hand.
    inTrouble("couldn't reach the book — trying again");
    bootTimer = setTimeout(openTheBook, bootDelay);
    bootDelay = Math.min(bootDelay * 2, RETRY_MAX_MS);
  }
}

// ------------------------------------------------------------------- books

// The second overlay, and the one that had to argue hardest for itself.
//
// A book gets added by asking — "add me Treasure Island" — and that still
// works and is still the shortest way to do it. What asking could never do is
// show the answer: a render takes hours, it happens in another process on
// another unit, and until now the only evidence that it was happening at all
// was whether the chapter count was still moving. So this panel exists to watch
// one, and to stop one, and to start one when somebody would rather point than
// speak.
//
// What it deliberately is not is a library browser. Nothing on it opens a book
// and nothing on it switches what is playing — which is what keeps ADR 3's "the
// page opens the book they were last listening to; changing books is done by
// asking" literally true. A catalog search for something to *add* is a
// different act from choosing what to listen to, and the difference is the
// whole reason this is allowed to be a second overlay on a one-screen page.
//
// It does now start the book that is already open. `reading now` at the top of
// it names the book the panel is standing over and offers it back, and that
// press is the play button pressed from up here rather than from behind: the
// only book it can reach is the one already sounding, so nothing is opened and
// nothing is switched. What it costs is that `close` is no longer the only way
// out, and the listener at the foot of this section has to give the borrowed
// tap-to-resume up rather than hand it back.
//
// It costs nothing when it is shut. No request is made before it is opened, its
// poll stops the moment it is closed or the phone goes in a pocket, and it
// holds no payload — so none of the six places that take the candidate list
// down has a twin here, and nothing else on the page has to know it exists.
//
// And it is separate from the ladder that watches THIS book grow, on purpose.
// `awaiting`/`askForMore` conflate "has this book got longer" with "is the
// listener stranded", and when a status stops being 'rendering' they clear
// wantsSound and throw the sleep timer away. Sharing them would end somebody's
// night because a book they queued for tomorrow finished rendering.

// How often the panel asks, while somebody is looking at it. Five seconds is
// slow enough to be nothing on a tailnet and fast enough that a press feels
// answered — and it stops dead the moment nobody is looking, which is the part
// that matters at 2am.
const QUEUE_POLL_MS = 5000;

// How long the first press of `stop reading this` stands before the button
// forgets it was ever asked. Long enough to read the label and decide, short
// enough that a panel left open does not have a live stop on it.
const STOP_CONFIRM_MS = 5000;

// The two states a job can be stopped in, which are also the two that go in the
// top list. Everything else has already happened.
const QUEUE_LIVE = ["queued", "rendering"];

// What somnia already has, said as something to read rather than as a status.
// A book on 'pending' is a render that died or was stopped, and it is the one
// marked state that is still worth offering: retrying it was impossible until
// the queue existed, and it is now the ordinary way to pick a book back up.
const HAVE_WORDS = {
  done: "already here",
  rendering: "being read now",
  queued: "in the queue",
  pending: "part rendered",
};
const HAVE_ALREADY = ["done", "rendering", "queued"];

// Which stage a row is at, in one word, in the corner of the row. It is the
// design's status column, and there is one entry here for each state the queue
// actually has and not one more. In particular there is no "fetching text":
// the design drew a pipeline with a fetch step in it, and somnia's queue has no
// such state to report. A book whose text has not been parsed is still
// `rendering` to the server, and what it is doing is said in the line under the
// name, where it can be honest about not knowing the count.
//
// The word and the line under it are two different things on purpose. This says
// which stage the row is at and does not change while it is at that stage; the
// line says what is actually happening inside it — which chapter, how much can
// be listened to, whether anything has been heard from it in five minutes.
const JOB_STAGE = {
  queued: "queued",
  rendering: "narrating",
  done: "ready",
  failed: "failed",
  cancelled: "stopped",
};

let queuePoll = 0; // the wake this panel is waiting on, or 0 for none
let queueRows = []; // the last list the server gave us, drawn as it stands
let queueFound = []; // the last search, and what has since been done about it
// The progress hairline of each row that has one, kept by job id across
// redraws. The list is rebuilt from scratch every five seconds, and a bar
// created a moment ago has no width to move from — so a fill that was made
// fresh each time would jump, and the 500ms the design asks for would be a
// transition that never once runs. Reusing the element is the whole of what
// makes it slide.
let jobFills = new Map();
// Which stop control is asking for its second press, and the wake that will
// make it forget. It lives here rather than on the button because the list is
// redrawn under it every five seconds, and a confirmation that a poll can
// cancel is a confirmation that expires at random.
let stopArmed = null;
let submitting = 0; // one submit in flight at a time, by gid
// Whether close owes the page a tap-to-resume listener, because opening the
// panel took one away. Exactly the borrow cancelCandidates makes, for exactly
// the same reason: with the listener still armed the first press anywhere on
// this overlay starts the book, and close — the one control that promises to
// change nothing — is where a thumb goes first.
//
// `pick it up` is the one press that clears this instead of spending it: that
// press is itself the touch the platform was waiting for, so what close would
// hand back is a listener over a book that is already sounding.
let rearmOnQueueClose = false;

function ordinal(n) {
  const tens = n % 100;
  const suffix =
    tens > 3 && tens < 21 ? "th" : ["th", "st", "nd", "rd"][n % 10] || "th";
  return `${n}${suffix}`;
}

// How much of a book can be listened to now, in the units somebody thinking
// about bedtime thinks in. Empty under a minute, because "0m read so far" reads
// as a stall and a render that has just started is not stalled.
function howMuch(ms) {
  const minutes = Math.floor(Math.max(0, ms) / 60_000);
  if (minutes < 1) return "";
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return hours ? `${hours}h${String(rest).padStart(2, "0")}m` : `${rest}m`;
}

function bookName(row) {
  // A book that has been through nothing but the local catalog may have no name
  // at all, and "book 1342" is a good deal better than an empty pair of quotes
  // in a sentence read at 2am. The server says the same thing in its own
  // readout, from queue._name.
  const name = row.title || `book ${row.gid}`;
  return row.authors ? `${name} — ${row.authors}` : name;
}

// -------------------------------------------------- what is playing under it

// Who wrote it, out of the one field the catalog has.
//
// Gutenberg's `authors` is already `Surname, Forename, dates` — the form the
// design asks for — so one name needs nothing done to it at all. Several arrive
// as one string with semicolons in it, and printed as they come that is a run
// of commas and semicolons with nothing in it to say where one person ends and
// the next begins: `Collins, Wilkie, 1824-1889; Reade, Charles, 1814-1884` is
// two people and reads as one long list of somethings. Split on the semicolon
// and set between them the separator this page already uses to hold two unlike
// things apart on one line, and the eye has somewhere to stop.
//
// Empties are dropped rather than trimmed away afterwards, because the field
// comes with a trailing semicolon often enough to matter and a name followed by
// a lone separator reads as a second author whose name is missing.
function whoWrote(authors) {
  return String(authors || "")
    .split(";")
    .map((one) => one.trim())
    .filter(Boolean)
    .join(" · ");
}

// The block at the top of the books panel: which book is playing under it, how
// far in, and the one press that goes back to it.
//
// Everything here comes off the manifest and the position this page is already
// holding. Nothing is fetched, nothing is stored, and nothing on the server
// knows this block exists — which is what lets it be redrawn on every pass of
// drawPlayer without costing anything, and what makes it impossible for it to
// disagree with the player behind the panel.
//
// Nothing at all while the panel is shut. drawPlayer runs four times a second
// with the sound on and most of that is spent with nobody looking at this.
function drawReadingNow() {
  if (queuePanel.hidden) return;
  // No book open — a somnia that has never rendered anything, or a book still
  // waiting on its first chapter. The whole block goes, label and all, which is
  // the rule the card of live rows already follows: a heading over nothing is a
  // claim that something should be there, and at 2am that is a reason to get up
  // and look for it.
  if (!manifest || !current) {
    readingNow.hidden = true;
    return;
  }
  readingNow.hidden = false;
  // The same fallback drawPlayer uses for the headline, for the same reason: a
  // book that has been through nothing but the local catalog may have no name,
  // and "book 1342" beats an empty line where the title goes.
  const name = manifest.title || `book ${gid}`;
  const who = whoWrote(manifest.authors);
  readingTitle.textContent = who ? `${name} — ${who}` : name;
  // The player's own count, drawn again here rather than read off the screen:
  // 0 means nobody wrote the total down — every book rendered before that
  // column existed — so it says `chapter 4` and stops, and never `4 of 0`.
  const total = manifest.chapters_total || 0;
  const number = current.idx + 1;
  const which = total ? `chapter ${number} of ${total}` : `chapter ${number}`;
  // `in` and not the design's `listened`, and the difference is not a word.
  // Nothing anywhere stores how long anybody has listened for: ADR 3 dropped
  // Audiobookshelf's session history on purpose at the pivot, and what is left
  // is a position and the reasons the page gives when it reports one. So this
  // is how far into the book the mark is, said as such. Empty under a minute,
  // from howMuch, because "0m in" reads as a book nobody has started.
  const into = howMuch(positionMs);
  readingMeta.textContent = into ? `${which} · ${into} in` : which;
  // The same fraction drawn rather than stated — and nothing at all while the
  // book is still arriving. total_ms is how much audio exists, which on a
  // finished book is how long the book is and on one still being read is not:
  // a bar drawn from it reaches the end at chapter five of thirty-seven and
  // then walks backwards as the rest lands. Both halves of "still arriving"
  // count, because a render that was stopped part way leaves exactly the same
  // short timeline as one that is still going.
  const arriving = manifest.status === "rendering" || moreToCome();
  const whole = !arriving && manifest.total_ms > 0;
  readingTrack.hidden = !whole;
  if (whole) {
    const through = Math.min(1, positionMs / manifest.total_ms);
    // One decimal place, as the job rows use, so that a redraw of the same
    // position is the same string and the bar does not shiver on a rounding
    // error four times a second.
    readingFill.style.width = `${Math.round(through * 1000) / 10}%`;
  }
  // Where the press will take them, in the book's own clock — the same string
  // the player's position readout shows, so the panel and the screen behind it
  // name one place. A book already sounding has nothing to start, and the label
  // says so instead of offering a time that is a moment out of date by the time
  // it is read.
  readingResume.textContent = player.paused
    ? `pick it up at ${timestamp(positionMs)}`
    : "back to it · playing";
}

// One job, in one line, for somebody who wants to know whether to wait up.
//
// Two of these are not states at all. A render whose heartbeat has gone quiet
// says so, because "rendering" would be a claim about a process that may have
// died with the box; and one that has been asked to stop says it is stopping,
// because it stays 'rendering' until the child reaches the end of its sentence
// and saying "rendering" there looks like the press was ignored.
//
// No percentage and no time remaining, in words. Chapters differ in length by
// an order of magnitude, so a number drawn from 4 of 39 is not a fraction of
// the work and reading it as one is how a render looks stalled, and the only
// honest denominator for a time estimate does not exist until the last chapter
// has been encoded. The hairline under this line is the same fraction drawn
// rather than stated, which is as much as it can honestly claim: something is
// moving, and this is roughly where it has got to.
function jobWords(row) {
  if (row.state === "queued") {
    return row.place > 0 ? `${ordinal(row.place)} in line` : "waiting its turn";
  }
  if (row.state === "rendering") {
    if (row.stopping) return "stopping at the end of this sentence";
    if (!row.responding) return "not responding";
    // 0 means nobody has written the number down yet — the fetch and the parse
    // are what produce it — and it is what every book rendered before that
    // column existed says as well. "chapter 1 of 0" is the sentence this
    // prevents.
    if (!row.chapters_total) return "fetching the text";
    // The chapter being worked on, not the count that is finished: the same
    // number, and the same meaning, as the "rendering chapter 4/39" line the
    // renderer writes to the journal, so the two can be read side by side.
    const chapter = Math.min(row.chapters_done + 1, row.chapters_total);
    const words = `chapter ${chapter} of ${row.chapters_total}`;
    const ready = howMuch(row.rendered_ms);
    return ready ? `${words} · ${ready} read so far` : words;
  }
  if (row.state === "failed") return row.error || "something went wrong";
  if (row.state === "cancelled") {
    // Two quite different things end up here. A book taken out of the line
    // never started and nothing of it exists; a render stopped at chapter four
    // left four chapters that play perfectly well, and somebody deciding
    // whether to ask for it again needs to know which of those they have.
    return row.chapters_done
      ? "stopped part way — what was read still plays"
      : "taken out of the queue";
  }
  return "all of it is here";
}

function stopControl(row) {
  const armed = stopArmed?.id === row.id;
  const button = document.createElement("button");
  button.type = "button";
  button.className = armed ? "job-stop armed" : "job-stop";
  // Set at creation, as candidateRow does, or nothing in a test can reach it.
  button.id = `queue-stop-${row.id}`;
  // Two presses, and the button itself is the question. Not a confirm dialog:
  // that is an overlay over an overlay, which is a route wearing a hat, and it
  // would be the first thing on this page to take focus from anybody.
  button.textContent = armed ? "really stop?" : "stop reading this";
  button.addEventListener("click", () => pressStop(row));
  return button;
}

// How far through the chapters this row is, drawn as a hairline — and nothing
// at all when nobody has written the total down.
//
// That guard is the whole reason this is a function. chapters_total is 0 until
// the parse has run, and it is 0 for ever on every book rendered before the
// column existed, so a bar drawn from it would sit at 0% on a render that is
// working perfectly well. An empty track is a lie somebody acts on at 2am; no
// track at all is the truth, and the line above says what is going on instead.
//
// It is a hairline and not a percentage for the reason `jobWords` gives no
// percentage either: chapters differ in length by an order of magnitude, so
// this creeps and lurches. As a 2dp rule that is a thing moving, which is all
// it is claiming to be; as a number it would be a promise about time.
function jobProgress(row) {
  if (!row.chapters_total) return null;
  const track = document.createElement("div");
  track.className = "job-track";
  // Kept from the last redraw where there was one, so the width animates
  // instead of appearing. See jobFills.
  let fill = jobFills.get(row.id);
  if (!fill) {
    fill = document.createElement("div");
    fill.className = "job-fill";
  }
  jobFills.set(row.id, fill);
  const done = Math.min(row.chapters_done, row.chapters_total);
  // One decimal place, so that a chapter landing moves it by a number rather
  // than by a rounding error, and so that two renders of the same row are the
  // same string.
  fill.style.width = `${Math.round((done / row.chapters_total) * 1000) / 10}%`;
  track.append(fill);
  return track;
}

function jobRow(row) {
  const live = QUEUE_LIVE.includes(row.state);
  const li = document.createElement("li");
  li.className = live ? "job" : "job gone";
  li.id = `job-${row.id}`;
  // The name, and in the corner of the same line the stage it is at. One line
  // and two ends of it, because the question this panel is opened with is "is
  // anything happening", and the answer to that is a single word beside a
  // title.
  const line = document.createElement("p");
  line.className = "job-line";
  const name = document.createElement("span");
  name.className = "job-name";
  name.textContent = bookName(row);
  const stage = document.createElement("span");
  // Amber only while it is really being read. A render whose heartbeat has
  // gone quiet, or one that has been asked to stop, is still `rendering` to
  // the server and still says `narrating` here — but it is no longer the warm
  // thing on the panel, because the line under it is about to say something
  // that is not good news.
  const warm = row.state === "rendering" && row.responding && !row.stopping;
  stage.className = warm ? "job-stage now" : "job-stage";
  stage.textContent = JOB_STAGE[row.state] || row.state;
  line.append(name);
  line.append(stage);
  const state = document.createElement("p");
  state.className = "job-state";
  state.textContent = jobWords(row);
  // No listener on the row itself. A row is a readout, so the only pressable
  // thing on it is its own action and there is nothing to mis-hit into.
  li.append(line);
  li.append(state);
  const track = jobProgress(row);
  if (track) li.append(track);
  if (live) li.append(stopControl(row));
  return li;
}

function drawQueue() {
  const live = queueRows.filter((row) => QUEUE_LIVE.includes(row.state));
  const over = queueRows.filter((row) => !QUEUE_LIVE.includes(row.state));
  // Whatever is on the screen after this, and nothing else. A bar kept for a
  // row that has left the list is a bar that would slide from somebody else's
  // progress if that id ever came back.
  const kept = new Map();
  for (const row of queueRows) {
    if (jobFills.has(row.id)) kept.set(row.id, jobFills.get(row.id));
  }
  jobFills = kept;
  queueLive.replaceChildren(...live.map(jobRow));
  // The card holds the live rows and goes with them. A heading over nothing is
  // a claim that something should be there.
  queueWorking.hidden = !live.length;
  // What went wrong, under what is happening. There is no dismiss control for
  // these and no count of them: `view` drops a terminal row after a day, which
  // is when a failure stops being news and becomes something the journal has.
  queueGone.replaceChildren(...over.map(jobRow));
  queueEnded.hidden = !over.length;
}

// A book the catalog found: what it is called, who wrote it, and the one press
// that can be made about it.
//
// The title and the author are two lines rather than one string now. The design
// asks for `Author · year · formats` under the title and somnia's catalog has
// the first of those three and neither of the others, so what is under the
// title is the author and whatever the panel already knows about the book —
// and no cover art, here or anywhere: a cover is a bright rectangle in a dark
// room, and four lines of text are read faster half asleep.
function foundRow(entry) {
  const li = document.createElement("li");
  li.className = "found";
  li.id = `found-${entry.gid}`;
  const text = document.createElement("div");
  text.className = "found-text";
  const name = document.createElement("p");
  name.className = "found-name";
  name.textContent = entry.title || `book ${entry.gid}`;
  text.append(name);
  const meta = document.createElement("p");
  meta.className = "found-meta";
  const by = document.createElement("span");
  by.className = "found-by";
  by.textContent = entry.authors || "";
  meta.append(by);
  const already = HAVE_WORDS[entry.have];
  if (already) {
    // Why there is no press to make, in the line that already exists rather
    // than as a pill on the right: a pill that cannot be pressed is a button
    // that does nothing, which is the one thing this row is arranged to avoid.
    const mark = document.createElement("span");
    mark.className = "found-have";
    mark.textContent = already;
    meta.append(mark);
  }
  text.append(meta);
  li.append(text);
  // A book that is already here, or already coming, is marked rather than
  // offered and then refused: a press that was never available cannot be a
  // press that did nothing, and at 2am those two feel completely different.
  if (HAVE_ALREADY.includes(entry.have)) return li;
  const add = document.createElement("button");
  add.type = "button";
  // The one warm press on the panel, and only for a render that died: picking
  // a half-read book back up is the thing somebody came here having already
  // decided to do, and it was impossible from this page until the queue
  // existed. Adding something new is a plain pill.
  const resume = entry.have === "pending";
  add.className = resume ? "found-add again" : "found-add";
  add.id = `queue-add-${entry.gid}`;
  add.textContent = resume ? "finish this one" : "add this book";
  add.addEventListener("click", () => addBook(entry, add));
  li.append(add);
  return li;
}

function drawResults() {
  queueResults.replaceChildren(...queueFound.map(foundRow));
}

// ------------------------------------------------------------- asking about it

async function pollQueue() {
  clearTimeout(queuePoll);
  queuePoll = 0;
  try {
    const response = await fetch("api/queue");
    if (!response.ok) throw new Error("no queue");
    const body = await response.json();
    queueRows = body.items || [];
    queueNote.textContent = "";
    drawQueue();
  } catch (error) {
    // Whatever was last drawn stays on the screen and the doubt is written
    // under it. Emptying the list would be the one lie this panel can tell: an
    // empty queue and an unreachable server look identical and mean opposite
    // things, and only one of them is a reason to go to sleep.
    console.error(error);
    queueNote.textContent = "couldn't reach somnia";
  }
  scheduleQueuePoll();
}

// Only while somebody is looking, and only while the panel is up. A hidden
// page's timers are throttled to roughly one wake a minute, so a poll left
// running in a pocket is both untimely and a radio wake beside somebody asleep
// — worst of both. It is asked again in full when the page comes back.
function scheduleQueuePoll() {
  clearTimeout(queuePoll);
  queuePoll = 0;
  if (queuePanel.hidden || document.visibilityState === "hidden") return;
  queuePoll = setTimeout(pollQueue, QUEUE_POLL_MS);
}

function stopQueuePoll() {
  clearTimeout(queuePoll);
  queuePoll = 0;
}

// ------------------------------------------------------------------ stopping

function forgetStop() {
  if (!stopArmed) return;
  clearTimeout(stopArmed.timer);
  stopArmed = null;
}

function pressStop(row) {
  if (stopArmed?.id !== row.id) {
    forgetStop();
    stopArmed = {
      id: row.id,
      timer: setTimeout(() => {
        stopArmed = null;
        drawQueue();
      }, STOP_CONFIRM_MS),
    };
    // Redrawn rather than relabelled in place, so that the label a poll paints
    // and the label a press paints come from the same line of code.
    drawQueue();
    return;
  }
  forgetStop();
  askToStop(row.id);
}

async function askToStop(id) {
  try {
    const response = await fetch(`api/queue/${id}/stop`, { method: "POST" });
    // Read whatever came back, whatever the status was. A job that ended a
    // second ago is answered 200 with a sentence and a job that never existed
    // is answered 404 with the same shape, and the sentence is the point of
    // both.
    const body = await response.json();
    queueSaid.textContent = body.said || "";
  } catch (error) {
    console.error(error);
    queueSaid.textContent = "couldn't reach somnia — nothing has been stopped";
    return;
  }
  // A stop takes about twenty seconds to land — one heartbeat plus the sentence
  // in flight — so this is not the answer, it is the row starting to say
  // "stopping".
  await pollQueue();
}

// ------------------------------------------------------------------- adding

async function findBooks() {
  const wanted = queueQuery.value.trim();
  if (!wanted) return;
  queueSaid.textContent = "";
  try {
    // One request per press. A round trip per keystroke would be fifteen
    // requests for one answer over a tailnet, and the search is an offline FTS5
    // query on the server's own disk, so there is nothing to be gained by
    // starting it early.
    const response = await fetch(`api/catalog?q=${encodeURIComponent(wanted)}`);
    if (!response.ok) throw new Error("no catalog");
    const body = await response.json();
    queueFound = body.entries || [];
    drawResults();
    if (!queueFound.length) queueSaid.textContent = "nothing in the catalog";
  } catch (error) {
    console.error(error);
    queueSaid.textContent = "couldn't reach somnia";
  }
}

async function addBook(entry, button) {
  // One at a time, and the guard is set before the first await: two presses a
  // frame apart are the ordinary way a thumb double-taps something that has not
  // answered yet.
  if (submitting) return;
  submitting = entry.gid;
  button.disabled = true;
  try {
    const response = await fetch("api/queue", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ gid: entry.gid }),
    });
    const body = await response.json();
    // Taken or refused, the server said a sentence and the sentence is the
    // answer — the same string the agent's add_book returns, from the same
    // function, so the panel and the voice cannot disagree about what happened.
    queueSaid.textContent = body.said || "";
    if (body.ok) {
      entry.have = "queued";
      drawResults();
    } else {
      button.disabled = false;
    }
  } catch (error) {
    // Nothing landed, and no optimistic row is drawn: a queue entry that never
    // existed on the server is exactly the state a wrong press must not be able
    // to leave behind. The press comes back, because trying again is the whole
    // of what there is to do about it.
    console.error(error);
    queueSaid.textContent = "couldn't reach somnia — nothing has been added";
    button.disabled = false;
    submitting = 0;
    return;
  }
  submitting = 0;
  // So the row it just made is on the screen now rather than in five seconds.
  await pollQueue();
}

// ------------------------------------------------------- opening and closing

function showQueue() {
  if (!queuePanel.hidden) return;
  queuePanel.hidden = false;
  // Giving focus up, never taking it — and in particular never focusing the
  // search box. Focusing it pops the keyboard, and the keyboard changes the
  // geometry the fixed overlay just measured itself against, so the panel would
  // arrive with its way out somewhere under the letters.
  question.blur?.();
  queueQuery.blur?.();
  rearmOnQueueClose = tapToResume !== null;
  disarmTapToResume();
  // Before the first request comes back, so the answer to "which book is this
  // standing over?" is on the screen the moment the panel is, rather than five
  // seconds later with the queue. It is drawn from what this page already
  // holds, so there is nothing to wait for.
  drawReadingNow();
  pollQueue();
}

// The inert close. It forgets everything the panel was holding and gives back
// the one thing it borrowed, and that is the whole of it: no seek, no report,
// no seq bump, nothing said on the status line, and nothing touched that the
// spoiler guard or the sleep timer can see. A fade running underneath keeps
// running and the countdown keeps counting, for the same reason cancel leaves
// them alone — the night was already ending and looking at a list of books did
// not change that.
function hideQueue() {
  if (queuePanel.hidden) return;
  queuePanel.hidden = true;
  stopQueuePoll();
  forgetStop();
  queueRows = [];
  queueFound = [];
  jobFills = new Map();
  queueLive.replaceChildren();
  queueWorking.hidden = true;
  queueGone.replaceChildren();
  queueEnded.hidden = true;
  queueResults.replaceChildren();
  queueNote.textContent = "";
  queueSaid.textContent = "";
  queueQuery.value = "";
  const rearm = rearmOnQueueClose;
  rearmOnQueueClose = false;
  // True before the panel went up and true again now: the book is still paused,
  // still waiting for a touch, and the line that said so came back with the
  // listener rather than being left lying.
  if (rearm) armTapToResume();
}

booksButton.addEventListener("click", showQueue);
queueClose.addEventListener("click", hideQueue);

// The one press on this panel that touches the book, and the only way out of it
// other than `close`.
//
// The order of the three lines matters and the first of them is the whole of
// why this is not just a call to hideQueue. showQueue borrows the tap-to-resume
// listener a refused play left armed, and close hands it back, because after
// close the book really is still paused and still waiting for a touch. This
// press is not close: it *is* that touch. Handed back here, the listener would
// be sitting over a book that is now sounding, and the next thing pressed
// anywhere on the page — the question box, the transport, the microphone —
// would start it a second time.
//
// Then the panel goes, because the question it was opened with has just been
// answered and a panel left standing over a book that has started playing is
// one more thing to get out of in the dark.
//
// Then the sound, by exactly the route the play button takes: the same rewind
// for the same silence, the same fade up from nothing, the same landing on the
// start of a sentence after an hour. A second kind of resume is a second thing
// to reason about at 2am, and this one would be the one nobody tested. Only
// when it is really stopped — the label already said `back to it · playing`
// rather than offering a time, and there is nothing there to start.
readingResume.addEventListener("click", () => {
  rearmOnQueueClose = false;
  hideQueue();
  if (player.paused) ensurePlaying({ rewind: true });
});
queueSearch.addEventListener("submit", (event) => {
  event.preventDefault();
  findBooks();
});

// -------------------------------------------- a book that is still being read

// somnia renders a book chapter by chapter and the whole point of that is that
// listening can start when chapter one is ready. So a manifest is a photograph
// of a book that is still arriving: ingest writes each chapter row as it
// finishes and bumps total_ms with it. Fetched once at boot and never again,
// chapter three of forty-nine ended the night with "that is the end of the
// book", the sleep timer thrown away and the phone silent — and a book opened
// before its first chapter landed showed no player at all, for ever.
//
// Only the timeline is taken. position_ms and seq in the reply are the server's
// record of what this page last told it, which is up to fifteen seconds behind
// where the sound actually is, so adopting them mid-chapter would drag the
// listener backwards every time the book grew.
// Whether this book has chapters that have not been read yet — as against
// being over.
//
// `status === 'rendering'` answers the live case and nothing else: a render
// that was stopped, or killed by a reboot, or that failed at chapter four of
// thirty-nine leaves a book that is not growing and is not finished either, and
// before there was a denominator the page had nothing to tell that from the end
// of a novel. It would say "that is the end of the book", clear wantsSound and
// throw the sleep timer away, three chapters into thirty-nine.
//
// 0 means nobody wrote the number down — which is every book rendered before
// the column existed, including every book on the box this runs on — so it is
// read as "don't know" and the old sentence stands.
function moreToCome() {
  const total = manifest?.chapters_total || 0;
  return total > 0 && manifest.chapters.length < total;
}

async function refreshManifest() {
  if (gid === null || !manifest) return false;
  const response = await fetch(`api/book/${gid}`);
  if (!response.ok) throw new Error(`no book ${gid}`);
  const fresh = await response.json();
  // The page moved to another book while this was in flight, or the answer has
  // fewer chapters in it than the page is already playing — a book somebody is
  // re-rendering, say. Neither is something to adopt underneath a listener: the
  // chapter the element is holding might not be in it.
  if (fresh.gid !== gid || fresh.chapters.length < manifest.chapters.length) {
    return false;
  }
  const grew = fresh.chapters.length > manifest.chapters.length;
  manifest = fresh;
  // The element is holding a chapter object from the manifest just replaced.
  // Pointing it at the row of the same index in the new one keeps every clock
  // on the page reading off one manifest — the numbers are the same today, but
  // a page holding rows from two fetches at once is a bug waiting for the day
  // they are not.
  if (current) {
    current = { idx: current.idx, chapter: fresh.chapters[current.idx] };
  }
  drawPlayer();
  return grew;
}

// Wait for the book to grow, and carry on when it does. `at` is the chapter the
// audio ran out after, or null when there was no audio at all yet.
function awaitMore(id, { play = false, at = null } = {}) {
  if (awaiting?.gid === id) return;
  stopAwaiting();
  awaiting = { gid: id, delay: RENDER_ASK_MS, play, at, timer: 0 };
  setStatus(
    at === null
      ? "the first chapter is still being read"
      : "waiting for the next chapter to be read",
  );
  awaiting.timer = setTimeout(askForMore, awaiting.delay);
}

// Whoever stops the waiting takes the message down with it — the chapter has
// either arrived or is never going to, and either way the page is not waiting
// for it any more. Anything with something else to say says it afterwards.
function stopAwaiting() {
  if (!awaiting) return;
  clearTimeout(awaiting.timer);
  awaiting = null;
  setStatus("");
}

async function askForMore() {
  const waiting = awaiting;
  if (!waiting) return;
  // It may have been called early — by the network coming back, or by the page
  // coming back in front of them — so whatever was scheduled is stale.
  clearTimeout(waiting.timer);
  try {
    if (gid === waiting.gid && manifest) {
      if (await refreshManifest()) {
        stopAwaiting();
        // Only if they are still standing where the audio ran out. If they went
        // somewhere else in the meantime, the longer timeline was all they
        // needed: the boundary at the end of wherever they are now will take
        // them into the new chapter by itself.
        if (player.ended && current?.idx === waiting.at) {
          const next = manifest.chapters[waiting.at + 1];
          if (next) showChapter(locate(next.start_ms), { play: waiting.play });
        }
        return;
      }
      if (manifest.status !== "rendering") {
        stopAwaiting();
        // The render stopped without finishing the book — cancelled, killed, or
        // failed — and the chapters it did not get to are still missing. That is
        // not the end of the book, so nothing here ends the night: the sleep
        // timer is left running and the page is left wanting the sound back.
        if (moreToCome()) {
          setStatus("the rest of this book hasn't been read yet");
          return;
        }
        // The render finished, and there was nothing more in it after all.
        setStatus("that is the end of the book");
        wantsSound = false;
        clearSleep();
        return;
      }
    } else {
      // Nothing of this book is open yet, so there is no timeline to extend:
      // the first chapter arriving is the page opening the book at last.
      await openBook(waiting.gid, { play: waiting.play });
      if (awaiting !== waiting) return;
    }
  } catch (error) {
    // The tailnet, most likely. Asking again is already the plan.
    console.error(error);
  }
  waiting.delay = Math.min(waiting.delay * 2, RENDER_ASK_MAX_MS);
  waiting.timer = setTimeout(askForMore, waiting.delay);
}

restoreSleep();
// Before the book, because the book is what decides whether the places are
// about it: openBook draws the player the moment a manifest lands, and a list
// read out of storage a turn later would be a count that appeared on the
// position line after somebody had already looked at it.
restorePlaces();
openTheBook();

// ------------------------------------------------------------------ speaking

const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;

if (!Recognition) {
  // No Web Speech API here — the phone keyboard's own dictation still works.
  talk.hidden = true;
} else {
  const recognition = new Recognition();
  recognition.lang = navigator.language || "en-GB";
  recognition.interimResults = true;
  recognition.continuous = false;
  let listening = false;
  let heard = "";

  recognition.addEventListener("result", (event) => {
    let interim = "";
    heard = "";
    for (const result of event.results) {
      if (result.isFinal) heard += result[0].transcript;
      else interim += result[0].transcript;
    }
    question.value = (heard + interim).trim();
  });

  recognition.addEventListener("end", () => {
    listening = false;
    talk.classList.remove("listening");
    setStatus("");
    buzz(10);
    const said = (heard || question.value).trim();
    heard = "";
    ask(said);
  });

  recognition.addEventListener("error", (event) => {
    // "no-speech" and "aborted" are just a held button that heard nothing.
    if (event.error !== "no-speech" && event.error !== "aborted") {
      console.error(event.error);
    }
    heard = "";
    question.value = "";
    setStatus("");
  });

  const start = (event) => {
    event.preventDefault();
    if (listening) return;
    heard = "";
    question.value = "";
    try {
      recognition.start();
      listening = true;
      talk.classList.add("listening");
      setStatus("listening…");
      buzz(15);
    } catch {
      // Already starting — the previous session hasn't finished releasing.
    }
  };

  const stop = () => {
    if (listening) recognition.stop();
  };

  talk.addEventListener("pointerdown", start);
  talk.addEventListener("pointerup", stop);
  talk.addEventListener("pointercancel", stop);
  talk.addEventListener("pointerleave", stop);
  talk.addEventListener("contextmenu", (event) => event.preventDefault());
}

// ------------------------------------------------------------------ keyboard

// Not every browser shrinks the page for the on-screen keyboard, and the ones
// that do disagree about when. Following the visual viewport keeps the
// composer above the keyboard and the transcript scrollable to both ends.
const viewport = window.visualViewport;
if (viewport) {
  const fit = () => {
    document.body.style.height = `${viewport.height}px`;
    transcript.scrollTop = transcript.scrollHeight;
  };
  viewport.addEventListener("resize", fit);
  // The keyboard animates in, so measure after it has settled.
  question.addEventListener("focus", () => setTimeout(fit, 250));
  question.addEventListener("blur", () => setTimeout(fit, 250));
}

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}
