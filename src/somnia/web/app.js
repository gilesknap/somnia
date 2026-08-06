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
const chapterTitle = document.getElementById("chapter-title");
const clock = document.getElementById("clock");
const sleepButton = document.getElementById("sleep");
const playpause = document.getElementById("playpause");
const back30 = document.getElementById("back30");
const fwd30 = document.getElementById("fwd30");

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

// A short buzz confirms the button caught the press, for a listener who can't
// see much and shouldn't be listening for a beep. Android honours this; iOS
// ignores it, which is why the button also changes colour and pulses.
function buzz(ms) {
  navigator.vibrate?.(ms);
}

async function ask(text) {
  if (!text) return;
  say(text, "you");
  question.value = "";
  const pending = say("…", "agent pending");
  const asked = token;
  setStatus("thinking…");
  try {
    const response = await fetch("api/ask", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ token, question: text }),
    });
    const body = await response.json();
    // They started over while this was in flight: the answer belongs to a
    // conversation that no longer exists, and appearing now would be a reply
    // to a question no longer on the screen.
    if (token !== asked) return;
    if (!response.ok) throw new Error(body.error || "no answer");
    pending.className = "said agent";
    pending.textContent = body.reply || "…nothing to say.";
    // The turn moved the book. This is the short way round — the same move
    // arrives as the refusal of the next report within fifteen seconds — so it
    // is only ever a head start, and applying it twice costs nothing.
    follow(body.move);
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

restart.addEventListener("click", async () => {
  const stale = token;
  token = crypto.randomUUID();
  sessionStorage.setItem("somnia-token", token);
  fetch("api/forget", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ token: stale }),
  }).catch(() => {});
  transcript.replaceChildren();
  setStatus("");
  say("Where do you want to be?", "agent");
  question.focus();
});

// ------------------------------------------------------------------- playing

// How early to start the next chapter. Ingest leaves 500ms of rendered silence
// at the end of every one, so a swap that begins 400ms out is spent inside a
// pause the book already had: the gap between chapters comes out shorter than
// it was written to be rather than longer. Raise this only if the silence
// ingest appends rises with it.
const SWAP_LEAD_S = 0.4;

// What "back a bit" means, in the absence of anyone able to say.
const SEEK_STEP_S = 30;

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

function drawPlayer() {
  if (!manifest || !current) return;
  chapterTitle.textContent = current.chapter.title;
  const whole = timestamp(manifest.total_ms);
  clock.textContent = `${timestamp(positionMs)} of ${whole}`;
  // Which half of the button's drawing shows. A class rather than the glyph it
  // used to hold: how big the symbol is and where in the button it sits are no
  // longer whatever the phone's symbol font happened to think.
  playpause.classList.toggle("playing", !player.paused);
  playpause.setAttribute("aria-label", player.paused ? "Play" : "Pause");
  drawSleep();
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
  buzz(10);
});

function drawSleep() {
  const choice = SLEEP_CHOICES[sleepChoice];
  let label = "sleep";
  let spoken = "Sleep timer, off";
  if (fade?.thenSleep) {
    label = "fading";
    spoken = "Sleep timer, fading out";
  } else if (choice === "chapter") {
    label = "chapter end";
    spoken = "Sleep timer, at the end of this chapter";
  } else if (sleepLeftMs !== null) {
    // Rounded up, and never zero: a countdown that says nothing is left has
    // nothing left to say, and by then the sound itself is the announcement.
    const minutes = Math.max(1, Math.ceil(sleepLeftMs / 60_000));
    label = `sleep ${minutes}m`;
    spoken = `Sleep timer, ${minutes} minutes left`;
  }
  sleepButton.textContent = label;
  sleepButton.setAttribute("aria-label", spoken);
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
  setStatus("tap anywhere to carry on");
  document.addEventListener("pointerdown", () => ensurePlaying(), {
    once: true,
  });
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
  handle("previoustrack", () => {
    if (!current) return;
    // Five seconds in, "previous" means the start of this chapter — what it
    // means on every music player anyone has used, and the more forgiving of
    // the two answers for a thumb that missed.
    const previous = manifest.chapters[current.idx - 1];
    const into = positionMs - current.chapter.start_ms;
    seekGlobal(
      into > 5000 || !previous ? current.chapter.start_ms : previous.start_ms,
    );
  });
  handle("nexttrack", () => {
    const next = current && manifest.chapters[current.idx + 1];
    if (next) seekGlobal(next.start_ms);
  });
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
});

// `play` is false at boot and true only when the agent has just moved this
// book: opening the app at 2am to ask a question must not start the book, but
// being taken to a passage in a book that was not even open must.
async function openBook(id, { play = false } = {}) {
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
  positionMs = opening.position_ms ?? 0;
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
      setStatus("nothing rendered yet");
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
        // The render finished, and there was nothing more in it after all.
        stopAwaiting();
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
