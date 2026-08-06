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

It needs the same environment as the rest of somnia, plus a key for the model:

| Variable | Why |
|---|---|
| `ANTHROPIC_API_KEY` | the agent's model calls, paid by you not the phone |
| `SOMNIA_LIBRARY_DIR` | where the rendered chapters are; the page streams them |
| `SOMNIA_DATA_DIR` | where `somnia.db` lives, if not the default |
| `SOMNIA_ABS_URL`, `SOMNIA_ABS_TOKEN` | optional: keeping Audiobookshelf roughly in step, and the one-off below |
| `SOMNIA_AGENT_MODEL` | another model; the default is Sonnet 5 |

`SOMNIA_LIBRARY_DIR` is the one that has become load-bearing since the page
became the player, and it fails quietly if it is wrong. Chapters are never
served by path — the request names a book and a chapter number, and the file
comes from the database row — but a row pointing outside the library directory
is refused all the same, because a database carried over from another machine
can point anywhere. What you see on the phone is *that chapter didn't arrive*;
the real reason is a warning in the journal. It defaults to
`~/library/audiobooks`, which is right only if that is genuinely where `somnia
add` put things.

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

`SOMNIA_AGENT_MODEL` overrides Sonnet 5. Haiku was the first choice, on cost,
and mostly held up; set `SOMNIA_AGENT_MODEL=claude-haiku-4-5` to go back to it.

**Keep `--host` as localhost.** The page has no login of any kind: anyone who
can reach it can drive the agent, spend your API credit and listen to your
books. Its only protection is that nothing but `tailscale serve` can reach the
port.

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
started fresh each time it is launched.

## Keep it running

As a systemd **user** service, alongside the rest of somnia:

```ini
# ~/.config/systemd/user/somnia-serve.service
[Unit]
Description=somnia chat page
After=network-online.target

[Service]
EnvironmentFile=%h/somnia.env
ExecStart=%h/.local/bin/somnia serve
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

## Asking it things

Type, or hold the button and speak — it listens only while held, because a
bedroom is full of speech that was not meant for somnia. Answers are read, not
spoken back: the only thing the page makes a sound with is the book.

The button glows and pulses while it is listening, and the phone buzzes when it
starts and stops. Android's own speech recogniser plays a start and stop tone
that no web page can turn off; silencing it means muting system sounds on the
phone.

Ask to be taken somewhere and the book goes there and plays from there. If the
passage is in a book that was not even open, that book opens. Nothing has to be
pressed afterwards.

It will not answer about a part of the book you have not heard. The bound is
the furthest point the page has actually *played through*, not where you are
now — so being taken back to chapter two does not un-hear chapter twenty, and
being taken forward does not unlock what you were carried over. What you get
instead is that the passage is further on than you have got, and an offer to
take you there anyway. Two things follow from measuring it that way. A book
somnia has never played is bounded at its opening minute, so if you get that
answer about a book you have been listening to for a fortnight, the listening
happened in Audiobookshelf and somnia does not know about it — run
`somnia seed-positions`. And skipping forward while the sound is on stops the
mark where it was until you come back behind it, which is the price of one
press of *+30* not marking the rest of the book as heard.

Conversations are held in memory, keyed by a token the page mints when it
starts, and nothing is written to disk. *Start over* drops the history when the
agent has got the wrong end of a mumbled question; restarting the service drops
all of them.

## Playing the book

The page opens the book you were last listening to, at the place you left it,
and does not start it — opening the app at 2am to ask a question is not the
same as asking for the book. Press play when you want it. There is no library
to browse: another book is something you ask for, the same way you ask for a
passage.

On the page there are three buttons: back thirty seconds, play/pause, forward
thirty seconds. Most nights you will use none of them, because the screen is
off. With the phone locked the book is driven from the notification, the lock
screen and whatever is paired over Bluetooth: play, pause, back and forward,
previous and next chapter, and a scrubber. The scrubber covers the chapter, not
the book — three minutes to the pixel across a whole novel is no use for the
nudge you actually want, and one sleepy thumb from the ending.

Pressing play again gives you back a little of what you missed, sized by how
long the sound was off: nothing under half a minute, then eight seconds, twenty
after a few minutes, and half a minute after an hour — and that longest one
lands on the start of the sentence you were in rather than in the middle of it.

**The sleep timer is the word *sleep* next to the clock.** Tapping it walks
fifteen, thirty, forty-five and sixty minutes, then the end of the chapter,
then off again, and it always says which it is on. It counts listening time, so
pausing to ask a question does not spend it. It ends in a twenty-second fade
that reaches silence at the time it named; tapping the control during that fade
brings the sound back, on the grounds that anyone reaching for it is awake
enough to have changed their mind. It is written down as it counts, so a reload
— or the phone throwing the app out of memory while it is in the background —
brings it back with the minutes it had left on it. A timer more than six hours
old is not brought back: opening the book the next evening is starting a night,
not finishing one.

If something else takes the sound — a call, an alarm — the book stops and stays
stopped, and the page says so. If the phone refuses to start audio without
being touched first, the page says *tap anywhere to carry on*, and anywhere
means anywhere.

A book that is still being rendered grows underneath you, and the page keeps
up with it: while the render is running it asks again for the chapter list —
when the audio runs out, and whenever you come back to the app — and carries
on into whatever has landed since. Open one that is three chapters in and it
will play those three, say *waiting for the next chapter to be read*, and go
on when chapter four arrives. A book with nothing rendered at all says *the
first chapter is still being read*, and the player appears when that chapter
lands — already playing if the agent took you to that book, waiting to be
pressed if you only opened the app. A book
whose render is not running and has no audio says *nothing to play yet* and
shows no player: that is a render that died, and it needs `somnia add` again,
not waiting for.

When the tailnet goes — wifi power save and a tailscale re-key both do it for a
few seconds — the page says *the book stopped arriving* and keeps trying,
waiting longer between attempts up to half a minute, and puts the chapter back
where you had got to rather than at the top of it. Opening the app while the
server is unreachable says *couldn't reach the book — trying again*, and does.
It stops the moment you pause — nothing reloads chapters under a book somebody
has put down — and waking the phone, or the wifi coming back, makes it try
again at once, so there is nothing to press.

## Check screen-off playback before you trust a night to it

Everything above rests on an installed PWA being allowed to keep playing with
the screen off, and on its notification surviving a chapter boundary. Both were
confirmed on 2026-08-06 — so this is not an open question, it is the check to
run again on a new phone, after an Android update, or on the first night that
goes quiet. It is a property of the handset, not of this code, and it cannot be
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

Press *Start* and confirm you can hear a tick once a second — the tick is the
cheapest stall detector there is, because you can hear time passing with the
screen off. Lock the phone, leave it two minutes, and wake it. If **shortfall**
is under a couple of seconds, nothing ever stopped it. Then press every button
you own — the lock screen, the pillow speaker, the headphones — and check each
one appears in the log, and use *Agent move* to confirm the book can be moved
and played again with no gesture at all, which is what the agent does every
time it takes you somewhere.

It is a spike and it is meant to read like one. It is served rather than kept
out of the way because a diagnostic nobody can open from the handset is a
diagnostic nobody runs, and this is the one question the whole pivot rests on.
