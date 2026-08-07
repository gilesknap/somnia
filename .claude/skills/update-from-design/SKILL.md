---
name: update-from-design
description: Pull the latest Claude Design handoff for somnia, diff it against the last one, and apply only what changed. Use when Giles says the design has tweaks or updates, asks to update from Claude Design, or mentions a new version of the handoff.
---

# Update somnia from Claude Design

The handoff is a **written spec**, not a picture, and it gets revised. This is
how to take a revision without re-reading it or guessing what moved.

## The project, and why it looks missing

    projectId: 7cae092a-04f8-4319-b510-86b2f73f853a   ("Somnia Night Reading App")

**`DesignSync list_projects` returns `[]` for it. That is not a failure.** It
lists only `PROJECT_TYPE_DESIGN_SYSTEM` projects; this one is
`PROJECT_TYPE_PROJECT` and can never be enumerated. `get_project`, `list_files`
and `get_file` against the UUID all work. Do not send Giles round `/design-login`
again — it is already granted and it will not help.

Files in the project:

| path | what it is |
|---|---|
| `design_handoff_somnia_night_client/README.md` | the spec — read this first, it is far cheaper than the prototype and states sizes in dp |
| `Somnia.dc.html` | the prototype: player, wake, chat, places, books |
| `support.js` | helpers the prototype imports |
| `android-frame.jsx` | presentation bezel — ignore entirely |

## 1. Diff, don't re-read

The last fetch is kept at `.claude/design/somnia-redesign/`. That copy exists to
be diffed against — it is the whole reason this is cheap.

```bash
cd .claude/design
cp -r somnia-redesign somnia-redesign.prev
# ...fetch README.md (and the prototype if a screen changed) over the top...
diff -u somnia-redesign.prev/README.md somnia-redesign/README.md
rm -rf somnia-redesign.prev
```

On 2026-08-07 that reported *55 lines added, nothing removed, three new
sections* — which was the entire answer, with no need to re-read 16KB.

Fetching costs context (`get_file` returns the whole file), so where a revision
is additive, apply the new sections to the local copy with `Edit` rather than
rewriting the file wholesale.

## 2. Apply, honouring what has already been decided

Read `docs/` and the comments in `index.html` before changing layout. Standing
rulings from Giles that a fresh handoff will not know about:

- **Take the look, not the capabilities.** Where the design wants data somnia
  does not have, record it on issue #20 and draw the screen against what exists.
  Never fake it with placeholder data.
- **Places is the last query's results**, not a store of pause/fade marks. See
  issue #20's plan comment. Do not propose a marks table.
- **No whole-book scrubbing.** The progress hairline is a readout with no tap
  target: 360px across a nine-hour book is ~90 seconds to the pixel, and a
  sleepy thumb lands past the spoiler guard in a book he has not read.
- Comments that defend a layout or decision that no longer holds are defects.
  Rewrite them or delete them in the same change.

## 3. Check — all of it

```bash
node --test tests/web/*.test.mjs     # the glob matters: `node --test tests/web`
                                      # resolves the directory as a module on
                                      # Node 22 and fails with MODULE_NOT_FOUND,
                                      # which reads exactly like a broken suite
.venv/bin/python -m pytest -q
```

Then use the **render-screens** skill: snapshot, render both sizes, `measure.py`,
and *read the PNGs*. Looking and measuring catch different things — a page that
read as fine by eye had four of six gaps wrong.

If a new element only appears when `app.js` runs, add it to `snapshot.py`'s
FIXTURE. `app.js` does not run in a snapshot, so anything it draws is invisible
to every future render until it is faked there.

## 4. Deploy to the VPS

The box runs an editable install from a git checkout at `/home/reader/somnia`,
currently on `feat/apply-redesign`. Every git command there needs
`HOME=/home/reader` or the checkout is refused as dubiously owned.

```bash
ssh root@187.124.114.170 '
runuser -u reader -- env HOME=/home/reader git -C /home/reader/somnia fetch origin <branch>
runuser -u reader -- env HOME=/home/reader git -C /home/reader/somnia reset --hard origin/<branch>
systemctl --user -M reader@ restart somnia-serve
'
```

**Verify over the tailnet URL, not localhost.** He reads it at
`https://srv1701493.tail2221d6.ts.net:8443`; `127.0.0.1:8721` is a different path
and checking it once produced a confident "deployed and verified" while he was
looking at a stale tab.

```bash
curl -sk https://srv1701493.tail2221d6.ts.net:8443/style.css | wc -c
```

No reinstall is needed while dependencies are unchanged — web assets are served
straight from the checkout. Check nothing is mid-render before restarting
`somnia-worker`; `somnia-serve` alone is enough for a web-only change.
