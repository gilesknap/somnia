# Keep a long render running

Rendering a book takes hours and somnia does one at a time. The thing that does
them is `somnia worker`: a supervisor that watches the queue, starts one child
per book, and waits for it. Run it as a systemd user unit and you can forget
about it — books asked for from the page, from the agent or from a terminal all
land in the same line, and it empties it.

Before starting one, check the machine can actually finish it:

```bash
bash somnia-doctor.sh
```

ffmpeg, espeak-ng and a CPU torch all have to be there, and a book needs roughly
30MB of disk an hour at the default bitrate — **double that for a book you
actually listen to**, because opening one in the page joins its chapters into a
second copy under `SOMNIA_DATA_DIR/streams`, which is how a chapter boundary
stopped taking the lock screen down with it
([ADR 7](../explanations/decisions/0007-cross-a-chapter-without-letting-go.md)).
That copy is a cache and can be deleted at any time the page is not open; it
costs a second or two of `ffmpeg -c copy` to make again.

Listening to a book *while it renders* costs more than double, and how much more
depends entirely on how fast the box is. A join is named by how many chapters it
holds, so every time the listener catches up with the render a new one is
written and the old one is left behind — on a box that renders barely faster
than it is read, that is a join of the first chapter, of the first two, of the
first three, all night. Nothing reaps them yet. If a data directory is larger
than you can account for, that is where it went, and `rm -r` on
`SOMNIA_DATA_DIR/streams` with the page shut is the whole of the cure.

## The worker unit

```ini
# ~/.config/systemd/user/somnia-worker.service
[Unit]
Description=somnia render worker
After=network-online.target

[Service]
Type=simple
EnvironmentFile=%h/somnia.env
ExecStart=%h/somnia-venv/bin/somnia worker
Restart=always
RestartSec=30
# A stop has to wait for the sentence being spoken, not the chapter being
# rendered: the child finishes its sentence, puts the book back in the queue
# and exits. Ninety seconds is far more than that needs and far less than a
# chapter, which is the point — a chapter killed part way through is the one
# death that can leave the index holding words the player cannot see.
TimeoutStopSec=90
# The page must never wait behind Kokoro on two cores. This is why the renderer
# is a separate unit at all.
Nice=10
CPUWeight=20

[Install]
WantedBy=default.target
```

```bash
loginctl enable-linger $USER            # survive logging out
systemctl --user daemon-reload
systemctl --user enable --now somnia-worker
journalctl --user -u somnia-worker -f
```

`Restart=always` is new, and it used to be forbidden in bold. What earned it:
re-rendering a chapter now **replaces** that chapter's passages in the index
rather than adding a second copy of every one of them, a render resumes at the
first chapter that has no row rather than at chapter one, and a job that is
interrupted three times is given up on with a sentence rather than retried all
night. Those three together are [#11](https://github.com/gilesknap/somnia/issues/11)
closed, and until they landed an automatic restart would have industrialised it.

Deploying is now **two** restarts — `somnia-serve` and `somnia-worker` — and
they are independent on purpose: restarting the page's unit no longer touches a
render, which it silently killed every time before.

## Watching it

```bash
somnia queue
journalctl --user -u somnia-worker -f
somnia find 271 "any phrase from an early chapter"
```

`somnia queue` is the quick answer: what is rendering, what is behind it, what
died overnight, and which chapter of how many. The journal is the child's own
output — `rendering chapter 3/34` per chapter, and the whole traceback of
anything that broke. The third is the real end-to-end check, and the more
interesting one: it only answers once a chapter has been rendered *and*
indexed, so it says the pipeline works rather than that a process is alive. The
page will already be playing chapter one by then — a book is listenable while
the rest of it is still being read.

What that looks like on the phone if the listener catches up with the renderer
is a **pause**, not an ending: the sound stops a fraction before the end of what
has been rendered, the lock screen card stays up with a play button on it, and
the book carries on by itself when the next chapter lands. It is deliberate, and
the reason is that letting the audio actually run out is what takes the card
down and ends the night —
[ADR 7](../explanations/decisions/0007-cross-a-chapter-without-letting-go.md).
So a silent phone with a paused card at 1am usually means the renderer, not the
network, and `somnia queue` is the thing to look at.

## Stopping one

```bash
somnia queue stop 4
```

A book that was only waiting goes immediately. A render that is running is only
*asked*: nothing signals it and nothing kills it, so it reads to the end of the
sentence it is on and stops on the next chapter boundary, which takes about
twenty seconds. Every chapter it had already finished stays exactly where it is
and stays playable, and asking for the book again resumes at the next one.

`systemctl --user stop somnia-worker` is the other kind of stop, and means
something different: nobody stopped wanting the book, so it goes back into the
queue rather than being cancelled, and the worker picks it up again when it
starts. The chapter that was in flight is lost — minutes of Kokoro — because
the child will not gamble on finishing a chapter inside the stop timeout.

## Renders the agent starts

When `serve` is running the agent can ask for a book itself, and since it goes
through the same queue as everything else, two things that used to be true no
longer are.

It no longer spawns anything, so its renders are not invisible any more. They
run under `somnia-worker` like every other render, which means
`journalctl --user -u somnia-worker` has the chapter lines and the tracebacks
for books nobody started by hand — the first time an agent-started render has
left a trace anywhere.

And it no longer refuses a book somnia already has in *any* state. A book
rendered in full is still refused, and so is one already in the queue, but a
render that died, was stopped, or was killed by a reboot can be asked for again
— which is the retry that was impossible before, and which is safe now only
because a resume adds no second copy of anything.

## By hand, without the unit

```bash
somnia add 271
```

This puts the book in the queue and then renders the head of the line itself,
under exactly the same claim the worker's child takes. So it refuses in the
first second — with a sentence pointing at `somnia queue` — if the worker is
already rendering something, rather than becoming a second renderer on two
cores. `somnia worker --once` is the same thing without submitting anything:
take the next book in the line, render it, exit.

Both run in the foreground and die with the terminal, so use `tmux` if you are
going to close it:

```bash
tmux new -s render 'somnia add 271'
tmux attach -t render
```

Fine for one book you are watching. The unit is better for anything you want a
journal of afterwards, and it is the only thing that empties a queue by itself.
