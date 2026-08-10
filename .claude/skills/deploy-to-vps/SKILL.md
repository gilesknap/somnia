---
name: deploy-to-vps
description: Put a ref on the live VPS that Giles actually sleeps to — install, restart, verify, and roll back. Use when asked to deploy, upgrade the VPS, ship a branch or main to the box, or check what version is live.
---

# Deploy to the VPS

The box is `ssh somnia-vps` (Ubuntu, `187.124.114.170`). somnia runs natively
as user `reader` (uid 1004, linger on) — **there is no Docker on it**, despite
the README advertising a ghcr image, and **there is no git checkout**: the box
is not a working copy. Upgrades go through `somnia-install.sh`, never
`git pull`.

| Thing | Where |
|---|---|
| venv | `/home/reader/somnia-venv` |
| settings | `/home/reader/somnia.env` |
| database | `/home/reader/somnia-data/somnia.db` |
| audio | `/home/reader/library/audiobooks` |
| units | `~/.config/systemd/user/somnia-{serve,worker}.service` |
| page | `https://srv1701493.tail2221d6.ts.net:8443` (tailnet only; `:443` is Audiobookshelf, not somnia) |

Only the venv is disposable. Everything else outlives any deploy — which is
why deleting the install cannot touch the books.

## The procedure

**1. Gate on tests.** `gh run list --branch <ref>` — if CI is green on the
exact head SHA, that is the gate. If it is empty (integration branches and
anything ad-hoc never get a run), run both suites yourself from a worktree on
that ref; a merge of five green PRs is not itself green:

```bash
python -m pytest -q          # no --timeout, pytest-timeout is not installed
node --test tests/web        # the .mjs suite; pytest does not run it
```

**2. Snapshot the database.** `sqlite3 … ".backup"`, never `cp` — the DB is in
WAL mode and a plain copy silently misses the `-wal`. There is no downgrade
path, so this is the only way back.

```bash
sudo -u reader sqlite3 /home/reader/somnia-data/somnia.db \
  ".backup /home/reader/attic-<date>/somnia.db.pre-<ref>"
sudo -u reader sqlite3 /home/reader/attic-<date>/somnia.db.pre-<ref> "pragma integrity_check;"
```

**3. Install.** Stage the scripts from the ref being deployed (`git show
origin/<ref>:scripts/somnia-install.sh` — do not touch Giles's working tree),
scp them over, then run as `reader` from `/home/reader`:

```bash
bash somnia-install.sh --ref <branch|tag|commit>
```

It reuses the venv, force-reinstalls somnia only (torch survives), and leaves
`somnia.env` alone. Takes a few minutes — run it detached and poll, don't
block. A branch name with a slash in it is fine.

**4. Restart both units.** Not just the page — a worker left on the old code
renders with it.

```bash
sudo -u reader XDG_RUNTIME_DIR=/run/user/1004 systemctl --user restart somnia-serve somnia-worker
```

**5. Verify.** `somnia-doctor.sh` is the real check — it looks at the install
and the data together and should end `0 failed, 0 warned`. Then confirm the
page over the tailnet, and read the journal for tracebacks. Check the book and
chapter counts came through the migration.

## Foot-guns

**A restart during a render costs a chapter, not the book.** The worker puts an
in-flight book back in the queue at a chapter boundary and resumes within
seconds. Check `somnia-doctor.sh`'s "N books, M fully rendered" before and
after — a mismatch means a render was running, and the journal will say
`resuming <title> at chapter X/Y`. Nothing to fix; just don't mistake it for
damage.

**The units read `somnia.env` wholesale via `EnvironmentFile=`.** Unknown keys
are harmless — `load_config` only reads keys it knows, so settings left behind
by a removed feature go inert rather than failing startup. But check that
before deploying anything that drops a config surface; a stricter loader would
take both services down on restart. `#` comments are fine in that file: both
systemd and the `~/.local/bin/somnia` wrapper's `source` ignore them.

**`~/.local/bin/somnia` is for interactive CLI use only.** It sources
`somnia.env` then execs the venv binary. The services do *not* go through it,
so changing it does not change what they see.

**Keep `~/.cache/huggingface`.** It holds Kokoro-82M and e5-small-v2 — the TTS
and the embedding model. `~/.cache/pip` and `~/.cache/uv` are build cruft worth
~2G and safe to delete; the models are not.

**The SSH key lives on `/cache`, not `/root`.** A devcontainer rebuild wipes
`~/.ssh`. Relink from `/cache/ssh/` (key, `config`, `known_hosts`) rather than
generating a new key and asking Giles to re-authorise it.

## Rolling back

```bash
bash somnia-install.sh --ref <previous>   # then restart both units
```

Code rolls back cleanly. The database does not: migrations only add columns, so
older code ignores what it does not know — but nothing tests that direction.
Restore the pre-deploy snapshot if the schema moved.
