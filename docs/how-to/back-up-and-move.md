# Back it up, and move it

Two things are irreplaceable, and neither is the software. `somnia.db` holds
where you are in every book, how far you have heard, and the index that makes
semantic seek possible. The library holds hours of rendered audio that cost
hours of CPU. Everything else — the virtual environment, the settings file, the
catalog, and the joined-up copies under `streams` — can be rebuilt in ten
minutes.

## Back up the database while it is running

somnia runs in WAL mode, so copying the file with `cp` while the server is up
can give you a torn database. sqlite's own backup does it safely, and the
virtual environment already has everything needed:

```bash
~/somnia-venv/bin/python - <<'PY'
import sqlite3
src = sqlite3.connect("/home/you/.local/share/somnia/somnia.db")
dst = sqlite3.connect("/backup/somnia.db")
with dst:
    src.backup(dst)
PY
```

The library is ordinary files that are only ever appended to, so it needs
nothing clever:

```bash
rsync -a ~/library/audiobooks/ /backup/audiobooks/
```

A render in progress means a partial chapter in the copy, which the next render
overwrites. It is not a reason to stop the world.

## Move both to another machine

Install somnia on the new box first — [Installation](../tutorials/installation.md)
— then bring the data across, and set `SOMNIA_LIBRARY_DIR` to wherever the
library has landed.

Then there is one thing to fix, and it will not announce itself.

### The paths inside the database

`chapters.audio_file` holds **absolute** paths, written when the chapter was
rendered. Move the library to a different path — a different user, a different
mount, `/srv` instead of `/home` — and every row points somewhere that does not
exist. The server does not fall back to guessing: chapters are looked up in the
database and never by path, and a row resolving outside `SOMNIA_LIBRARY_DIR` is
refused even if the file is there, because a database carried from another
machine can point anywhere.

What you would see is a page that lists your books, answers questions, and
plays nothing.

Stop the server and rewrite the prefix:

```bash
~/somnia-venv/bin/python - <<'PY'
import sqlite3
db = sqlite3.connect("/home/you/.local/share/somnia/somnia.db")
with db:
    n = db.execute(
        "UPDATE chapters SET audio_file = replace(audio_file, ?, ?)",
        ("/home/old/library/audiobooks", "/srv/audiobooks"),
    ).rowcount
print(f"{n} chapters repointed")
PY
```

Then let the doctor confirm it, which is exactly what it is for:

```bash
bash somnia-doctor.sh
```

It checks every chapter row for a file that exists and sits inside
`SOMNIA_LIBRARY_DIR`, and names the first one that does not.

### Audiobookshelf, if you use it

`books.abs_item_id` refers to whatever ABS instance you had configured. If ABS
is not coming with you, point `SOMNIA_ABS_URL` at the new one — or unset
`SOMNIA_ABS_TOKEN` and no client is built at all. There is no need to run
`somnia seed-positions` again: your positions are in the database you just
carried across, and seeding never lowers one anyway.

### What you do not need to move

The catalog is a download: `somnia catalog-update` on the new box rebuilds it.
The virtual environment should be built fresh rather than copied, since it holds
absolute paths of its own.

`SOMNIA_DATA_DIR/streams` is the other one, and it is the one that will tempt
you, because it sits beside `somnia.db` and it is by far the largest thing in
there — roughly the size of the library again, since it holds each book's
chapters joined into the single file the page plays
([ADR 7](../explanations/decisions/0007-cross-a-chapter-without-letting-go.md)).
It is a cache. Every file in it is rebuilt from the library in a second or two
of `ffmpeg -c copy` the first time somebody opens that book, so back it up and
you are paying to store a copy of audio you already backed up, and leave it
behind and you lose nothing at all. If you rsync the data directory rather than
copying `somnia.db` on its own, exclude it.

## Moving the renders somewhere faster

Rendering and serving do not have to be the same machine, and the render host
is the one that wants CPU
([#4](https://github.com/gilesknap/somnia/issues/4)). The catch is the same
one as above: whichever box renders writes absolute paths into the database, so
either both machines see the library at the same path — a shared mount, or the
same directory name on both — or you rewrite the prefix each time you bring a
book across. The same path on both is much the easier of the two.
