# Installation

somnia has two halves and they have different appetites. The machine that
**renders** books needs Kokoro, torch, ffmpeg and espeak-ng; the machine that
**serves** them needs none of that. Most of the time they are the same VPS, and
that is what the installer assumes.

You need Python 3.11, 3.12 or 3.13 — 3.14 is held back by pysbd, the sentence
splitter, which is unmaintained. If the only python3 on the box is 3.14, the
installer will use one of uv's interpreters instead, or tell you how to get one.

## Install

```bash
curl -fsSLO https://raw.githubusercontent.com/gilesknap/somnia/main/scripts/somnia-install.sh
less somnia-install.sh
bash somnia-install.sh
```

Read it before you run it. It is a couple of hundred lines of shell and you are
about to run it on a machine you care about; this page would tell you to do the
same with anybody else's installer.

It builds a virtual environment in `~/somnia-venv`, installs somnia and the CPU
build of torch, writes a starter `~/somnia.env` with every setting commented out
except the one that has no default, and pulls the Gutenberg catalog. Run it
twice and nothing is harmed: an existing environment is reused, and an existing
settings file is never touched.

It installs from `main` by default, not from the last release — this is the
project's own box-builder, and the box it builds is expected to be ahead. Pass
`--pypi` for the released `somnia-reader` instead.

| Flag | When |
|---|---|
| `--serve-only` | this machine only plays books: no Kokoro, no torch |
| `--venv DIR` | build it somewhere other than `~/somnia-venv` |
| `--ref REF` | install a branch, tag or commit rather than `main` |
| `--pypi` | install the last release from PyPI rather than a git ref |
| `--cuda` | you really do have a GPU |
| `--no-catalog` | skip the ~20MB catalog download |

**ffmpeg and espeak-ng cannot come from pip.** They are the only things the
installer will not fetch for you: it checks, and prints the command for your
package manager if either is missing. Nothing else stops, because an
environment without them is still worth having on a machine that only serves.

## Or by hand

Four commands, and the order of the middle two matters:

```bash
python3 -m venv ~/somnia-venv
source ~/somnia-venv/bin/activate
python3 -m pip install torch --index-url https://download.pytorch.org/whl/cpu
python3 -m pip install "somnia-reader[ml]"
```

Install torch first, from the CPU index and nothing else. `--extra-index-url` is
not enough: pip resolves across both indexes and takes the highest version it
finds, so on the day PyPI carries a newer torch than the CPU index does you get
two gigabytes of CUDA runtime to render a book with. Leave `[ml]` off on any
machine that only serves.

**The package is `somnia-reader`, not `somnia`.** That name was taken on PyPI
before this project existed, by an unrelated AI-agent CLI, so `pip install
somnia` gets you a stranger's package that will not answer to any command on
this site. The extra name is the only thing that changed: `import somnia` and
the `somnia` command are untouched.

## Ahead of the last release

A tagged release is a snapshot, and `main` moves. If you are chasing a fix that
has landed but not been tagged — which the issue will normally say — install
from the repository instead:

```bash
python3 -m pip install "somnia-reader[ml] @ git+https://github.com/gilesknap/somnia.git"
```

or plain `bash somnia-install.sh`, which is already what it does. Torch still
goes in first, from the CPU index; nothing about that changes.

Into an environment that already has somnia in it, that command does nothing at
all and says so cheerfully — see [Upgrade to a new version](../how-to/upgrade.md)
for the uninstall that makes it stick.

(configure)=
## Configure

Everything is environment variables, and every one of them has a working
default except the Anthropic key. `~/somnia.env` is where the installer puts
them and what the how-to guides assume — your shell reads it with `source`, and
the systemd units read it with `EnvironmentFile=`.

Two of them matter on the first day. The rest have defaults that are right until
you have a reason to change them, and are listed in
[Configuration](../reference/configuration.md).

| Variable | Default | What it is |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | The agent's model calls. Required for `somnia ask` and `somnia serve` |
| `SOMNIA_LIBRARY_DIR` | `~/library/audiobooks` | Where rendered chapters are written, and served from |

`SOMNIA_LIBRARY_DIR` is the one that fails quietly. Get it wrong and the server
starts happily, answers questions happily, and 404s every chapter — the real
reason is a warning in the journal, and what you see on the phone is only *that
chapter didn't arrive*. Set it explicitly.

Audiobookshelf is entirely optional now that the page is the player. somnia
writes your position to it when you stop, as a courtesy, and never reads it
except for the one-off `somnia seed-positions`.

## Prove it works

```bash
curl -fsSLO https://raw.githubusercontent.com/gilesknap/somnia/main/scripts/somnia-doctor.sh
bash somnia-doctor.sh
```

```text
somnia doctor

  ok    somnia 0.1.dev45 in /home/you/somnia-venv
  ok    python 3.13.7
  ok    settings from /home/you/somnia.env
  ok    ffmpeg
  ok    espeak-ng
  ok    torch 2.13.0+cpu (CPU)
  ok    ANTHROPIC_API_KEY is set
  ok    catalog: 76421 books to search
  warn  no books added yet — try 'somnia add 271'

0 failed, 1 warned
```

It exits non-zero if anything failed, and it is worth running again after the
first book: it checks that every rendered chapter is still on disk and still
inside `SOMNIA_LIBRARY_DIR`, which is the failure you would otherwise meet at
2am as one chapter that didn't arrive.

[Add a book and ask it something](first-book.md) is what to do next.

## Or run it in a container

Pre-built images with the dependencies already installed are on
[GitHub Container Registry](https://ghcr.io/gilesknap/somnia) — see
[Run in a container](../how-to/run-container.md).
