# Installation

somnia has two halves and they have different appetites. The machine that
**renders** books needs Kokoro, torch and ffmpeg; the machine that **serves**
them needs none of that. Most of the time they are the same VPS, and that is
fine — install the full thing once.

## Before you start

You need Python 3.11, 3.12 or 3.13. (3.14 is held back by pysbd, the sentence
splitter, which is unmaintained.)

```
$ python3 --version
```

The render host also needs two system packages: **ffmpeg**, which encodes each
chapter, and **espeak-ng**, which Kokoro uses for phonemes.

```
$ sudo apt install ffmpeg espeak-ng
```

## Install

Into a virtual environment, so nothing else on the machine is disturbed:

```
$ python3 -m venv ~/somnia-venv
$ source ~/somnia-venv/bin/activate
$ python3 -m pip install "somnia[ml]"
```

The `[ml]` extra is Kokoro and sentence-transformers, which pull in torch. On a
CPU-only box — which the VPS almost certainly is — take the CPU wheel rather
than the CUDA one, or you will download two gigabytes of GPU runtime to render
a book with:

```
$ python3 -m pip install "somnia[ml]" \
    --extra-index-url https://download.pytorch.org/whl/cpu
```

Leave `[ml]` off on any machine that only serves. For an unreleased fix:

```
$ python3 -m pip install "git+https://github.com/gilesknap/somnia.git"
```

Check it landed:

```
$ somnia --version
```

## Configure

Everything is environment variables, and every one of them has a working
default except the Anthropic key. Put them somewhere both your shell and your
systemd units can read — `~/somnia.env` is what the how-to guides assume.

| Variable | Default | What it is |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | The agent's model calls. Required for `somnia ask` and `somnia serve` |
| `SOMNIA_DATA_DIR` | `~/.local/share/somnia` | Where `somnia.db` lives |
| `SOMNIA_LIBRARY_DIR` | `~/library/audiobooks` | Where rendered chapters are written, and served from |
| `SOMNIA_VOICE` | `af_heart` | The Kokoro voice |
| `SOMNIA_AGENT_MODEL` | `claude-sonnet-5` | The model behind the conversation |
| `SOMNIA_EMBED_MODEL` | `intfloat/e5-small-v2` | Must be 384-dimensional |
| `SOMNIA_ABS_URL` | `http://127.0.0.1:13378` | Audiobookshelf, if you run one |
| `SOMNIA_ABS_TOKEN` | — | Unset means no ABS client is built at all |
| `SOMNIA_ABS_LIBRARY_ID` | — | From `somnia libraries` |

`SOMNIA_LIBRARY_DIR` is the one that fails quietly. Get it wrong and the server
starts happily, answers questions happily, and 404s every chapter — the real
reason is a warning in the journal, and what you see on the phone is only *that
chapter didn't arrive*. Set it explicitly.

Audiobookshelf is entirely optional now that the page is the player. somnia
writes your position to it when you stop, as a courtesy, and never reads it
except for the one-off `somnia seed-positions`.

## Prove it works

Pull the Gutenberg catalog — a ~20MB CSV, imported into FTS5, after which
browsing is offline:

```
$ somnia catalog-update
catalog updated: 76421 books
$ somnia search "black beauty"
   271  Black Beauty — Sewell, Anna
```

If that printed a book, the database is writable and the catalog is loaded.
[Add a book and ask it something](first-book.md) is what to do next.

## Or run it in a container

Pre-built images with the dependencies already installed are on
[GitHub Container Registry](https://ghcr.io/gilesknap/somnia) — see
[Run in a container](../how-to/run-container.md).
