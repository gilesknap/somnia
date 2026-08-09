# Serve the page that plays the book

`somnia serve` runs the 2am surface: a small chat page that talks to the agent,
with the Anthropic key held server-side. It is also the player — the page holds
the book somnia rendered and plays it, which is why asking to be taken
somewhere now ends in sound instead of in an instruction. Voice input uses the
browser's Web Speech API and the lock screen controls need a media session, so
the page must be reached over HTTPS (or localhost); `tailscale serve` provides
both the certificate and the only network path to it.

## Run it

```
$ somnia serve                       # 127.0.0.1:8721 by default
$ somnia serve --host 0.0.0.0 --port 9000
```

It needs the same environment as the rest of somnia, plus a key for the model.
Every setting is in [Configuration](../reference/configuration.md); these are
the ones a served night depends on:

| Variable | Why |
|---|---|
| `ANTHROPIC_API_KEY` | the agent's model calls, paid by you not the phone |
| `SOMNIA_LIBRARY_DIR` | where the rendered chapters are; the page streams them |
| `SOMNIA_DATA_DIR` | where `somnia.db` lives, and where the joined-up copy of each book the page plays is written — sometimes more than one for a book opened mid-render; needs room, not just a path |
| `SOMNIA_ABS_URL`, `SOMNIA_ABS_TOKEN` | optional: keeping Audiobookshelf roughly in step, and the one-off below |
| `SOMNIA_AGENT_MODEL` | another model; the default is Haiku 4.5 |
| `SOMNIA_AGENT_EFFORT` | how hard it may think before answering, on the models that have such a dial; Haiku has not |

`SOMNIA_LIBRARY_DIR` is load-bearing since the page became the player, and it
fails quietly: everything starts, the agent answers, and every chapter 404s
with the reason only in the journal. It defaults to `~/library/audiobooks`,
which is right only if that is genuinely where `somnia add` put things —
[Configuration](#config-fail-quietly) has why.

Audiobookshelf is now optional. somnia writes your position to it when you
stop, as a courtesy, so the ABS app finds roughly the right place if you open
it somewhere else — but nothing reads it while a night is running, and a write
that fails is logged and forgotten. Leave `SOMNIA_ABS_TOKEN` unset and no ABS
client is built at all.

Run `somnia seed-positions` once before the first night, if you have been
listening in Audiobookshelf. It is the one thing that reads ABS: it takes
where you had got to in each book, and how far you had heard, and puts them in
somnia's own database, so the page opens the book you were actually in rather
than the one added most recently, at the beginning. It says what it did for
every book, it never moves a position backwards, and running it again changes
nothing — so if you are unsure whether it worked, run it again.

`SOMNIA_AGENT_MODEL` overrides Haiku 4.5. Haiku is the default because over 85
trial questions on nuc2 it matched Sonnet 5 on every routing case, answered in
half the time and cost a fifth as much. It lost the job once, for reading a
character's name as the title of a book somnia does not have — it did not do
that once in five tries at the same question, but five tries is not proof, and
`SOMNIA_AGENT_MODEL=claude-sonnet-5` is the way back if it ever does it again.

### If a question takes too long to come back

Almost none of the wait is somnia: a search of the book is a tenth of a second
and the rest is the model, so this is the one setting that really moves it. If
you are on Sonnet, going back to the default Haiku roughly halves the wait.

On Sonnet there is a second, smaller dial: `SOMNIA_AGENT_EFFORT=low` tells it
to think less before answering, against a default of `medium` that is already
below what the API would do on its own, and is worth perhaps another second.
It does nothing on Haiku, which has no such dial — somnia asks the API which
models take one and simply does not send it where it would be refused.

Restart `somnia-serve` after either.

One wait is not the model and does not respond to any of that: the **first**
question of the night that searches a book used to sit for twelve seconds while
the embedding model loaded. That now happens as the server starts, so the cost
lands where nobody is waiting — but it means `somnia serve` is busy for those
twelve seconds after it starts answering. The page, the book and the audio are
all served throughout; only a search waits, and only if one is asked for that
early.

**Keep `--host` as localhost.** The page has no login of any kind: anyone who
can reach it can drive the agent, spend your API credit, listen to your books,
and start or stop hours of rendering. Its only protection is that nothing but
`tailscale serve` can reach the port.

## Publish it on the tailnet

Audiobookshelf usually already holds port 443, so give the chat page its own:

```
$ tailscale serve --bg --https 8443 http://127.0.0.1:8721
$ tailscale serve status
```

The page is then at `https://<node>.<tailnet>.ts.net:8443/`, reachable from
your own devices and from nowhere else. The whole night goes over that path now
— the audio as well as the questions — so a phone that drops off the tailnet at
3am loses the book. Nothing is downloaded ahead of time.

## Install it on the phone

Open the page in Chrome and use *Add to home screen*. It installs as a
standalone app with its own icon, which is one tap in the dark instead of a
browser and a URL, and it is worth doing for more than the icon: an installed
app is the shape the media notification and the screen-off playback were built
for and tested in.

Nothing else is needed. The page keeps no login, and the conversation is
started fresh each time it is launched. What it does once it is there — the
asking, the player, and the three screens behind the corners — is
[Use the page at night](use-the-page-at-night.md).

## Keep it running

As a systemd **user** service, alongside the rest of somnia:

```ini
# ~/.config/systemd/user/somnia-serve.service
[Unit]
Description=somnia chat page
After=network-online.target

[Service]
EnvironmentFile=%h/somnia.env
ExecStart=%h/somnia-venv/bin/somnia serve
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```

The environment file must carry `SOMNIA_LIBRARY_DIR` if the library is not in
the default place. A unit that lacks it starts perfectly happily, answers
questions perfectly happily, and 404s every chapter.

```
$ loginctl enable-linger $USER          # survive logout
$ systemctl --user daemon-reload
$ systemctl --user enable --now somnia-serve
$ curl -s localhost:8721/api/health     # {"ok": true}
```

## Check screen-off playback before you trust a night to it

Playing a book through the night rests on an installed PWA being allowed to
keep playing with the screen off, and on its notification surviving a chapter
boundary. The first was confirmed on 2026-08-06 and is not an open question; it
is the check to run again on a new phone, after an Android update, or on the
first night that goes quiet. The second was confirmed on the same night on the
phone's own speaker, and that turned out not to settle it — over Bluetooth the
notification is torn down and rebuilt at every boundary, and some nights it does
not come back. That was issue #31, and it is closed: the player now loads the
whole book from one URL
([ADR 7](../explanations/decisions/0007-cross-a-chapter-without-letting-go.md)),
and on 2026-08-08 a boundary was crossed over Bluetooth with the card up. Both
are properties of the handset rather than of this code, and neither can be
tested from a desk.

It is checked with a page of its own, which generates its own audio so it needs
no library, swaps chapters the way the player does, and writes every
media-session event to a log held in local storage — so the evidence survives
the page being discarded, which is one of the things being tested for.

It is served alongside the app, at:

```
https://<node>.<tailnet>.ts.net:8443/spike-background-audio.html
```

Open that on the phone. The line under the readout says whether it is running
as a browser tab or as an installed app; the installed case is the one
everything rests on, and it is the one Android treats more generously, so a tab
that keeps playing is good news for both while a tab that stops is not by itself
proof about the app.

In *Tone chapters*, press *Start* and confirm you can hear a tick once a second
— the tick is the cheapest stall detector there is, because you can hear time
passing with the screen off. Lock the phone, leave it two minutes, and wake it.
If **shortfall** is under a couple of seconds, nothing ever stopped it. Then
press every button you own — the lock screen, the pillow speaker, the headphones
— and check each one appears in the log, and use *Agent move* to confirm the
book can be moved and played again with no gesture at all, which is what the
agent does every time it takes you somewhere.

That mode is also a demonstration of the bug: it gives the element a new file at
every chapter, exactly as the player did before ADR 7, and as it still does with
`?chapters`, and **src writes** on the readout counts the teardowns.

### Whether one file can carry a whole book

*Whole book* is the mode that exercises the mechanism ADR 7 chose, and it is
what to run on a new phone, after an Android update, and for the two checks
ADR 7 leaves open: hours of a 161MB progressive resource, and a frontier wait.
It loads a real book — the longest one somnia has, or `?gid=<gid>` for a
particular one — from a single URL, `/api/stream/{gid}/{n}`, and never touches
the element again: a chapter boundary becomes arithmetic on the render clock,
and the only thing that happens is that the notification is renamed. `?book` on
the URL starts the page in this mode, so a home-screen shortcut can go straight
to it in the dark.

It has to be run over Bluetooth with the screen locked, because that is the
route the last check got wrong. Watch **src writes** stay at 1 all night; watch
**chapter changes** climb without it moving. Then look at the notification
across a boundary — no log can see this, and it is the whole question: does the
panel keep the same session and simply change its title, or does it blink out
and come back?

Four other things are worth doing while it is up, all of them nightly in the
real player:

- *Seek to the middle*, which is the morning resume: the log says how long the
  seek took and how long until sound came back.
- Watch **holding** — the byte ranges Chrome has kept. If the first range goes
  on starting at 0 all night, the phone is holding the whole book.
- Turn the tailnet off for half a minute and back on. A stall shows as
  **shortfall**; whether the phone had to fetch the book again shows in
  **holding**, and the other half of that answer is in the server's own log —
  `journalctl --user -u somnia-serve -f` shows a second `GET /api/stream/...`
  if Chrome threw the book away and asked for it again.
- Press the pillow speaker's skip and its scrubber. The panel is told the
  *chapter's* length and not the book's, so what those buttons move by is the
  question, and the log writes down what the panel was told each time.

It is a spike and it is meant to read like one. It is served rather than kept
out of the way because a diagnostic nobody can open from the handset is a
diagnostic nobody runs, and these are the two questions the whole pivot rests
on.

### Asking the same question of the real player

The player itself now loads the whole book from one URL, so the spike is no
longer the only place the question can be asked. To compare the two ways on the
same night, over the same speaker, open the app with `?chapters` on the address:

```
https://<node>.<tailnet>.ts.net:8443/?chapters
```

That plays the book a file at a time, the way it played before — a load at every
boundary, which is the bug — while the app opened normally plays it from one
file. Nothing else about the page differs, and nothing is remembered: it is a
property of the address, so closing the tab is the whole of undoing it.

Listen across a boundary each way, locked, over Bluetooth. The answer is what
the notification does, and there is nothing on any screen or in any log that can
stand in for it.
