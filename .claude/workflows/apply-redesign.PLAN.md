# Applying the redesign — plan

Written 2026-08-06. Companion to `.claude/workflows/apply-redesign.js`.
Read this first if you are picking the job up in a fresh context.

## The job

A redesign of somnia's page exists, made in Claude Design. It carries layout
changes, some changes to the flow, and "a couple of new minor features". It has
to become the real page — drawn, wired, tested — landing as one commit per
slice rather than one large diff.

## Step 0 — getting the design (RESOLVED)

`DesignSync list_projects` returns `[]` even after `/design consent` and
`/design-login` both succeed. That is not an auth failure: **`list_projects`
only lists `PROJECT_TYPE_DESIGN_SYSTEM` projects.** This one is
`PROJECT_TYPE_PROJECT` ("Somnia Night Reading App"), so it can never be
enumerated — but `get_project` / `list_files` / `get_file` against its UUID work
perfectly.

    projectId: 7cae092a-04f8-4319-b510-86b2f73f853a

The workflow's first phase fetches the files to disk itself, so this is handled.

## The handoff, and what it actually is

Not a picture — a **written spec**. `design_handoff_somnia_night_client/README.md`
is a per-screen diff with sizes in dp, and it is far cheaper to read than the
prototype HTML. Five screens: Player, **Wake (new)**, Chat, **Places (new)**,
Books, plus a global design system (one accent hue, one serif, a new full-screen
dim overlay, a toast).

It agrees with us on the measure — 360x780 at a 20px root — and adds a hard
rule: **the player must not scroll at that size, and nothing tappable goes below
44dp.**

### Where the spec is wrong about this codebase

The README opens with "Nothing here asks for new backend work, new data, or new
capabilities." That holds for Books and **breaks on Places**:

- **Places wants marks** — `{position, source, snippet}`, a standing list for
  the current book, reachable any time, where `source` is *how the mark was
  found* ("you paused here, awake", "sleep timer faded out here", "steady
  listening ended").
- **somnia has `Candidate`** (`src/somnia/tools.py:78`) — a *search result*,
  produced only as an answer to a question. No provenance field, no standing
  list, and the cap is 4 places against the design's 7.

That is a real design decision for the user, deferred with a question rather
than invented.

Smaller, already settled with the user:

- **Queue statuses** (`queued` / `fetching text` / `narrating` / `ready`) are
  display labels, not states. They map onto the real ones —
  `queued`→`queued`, `rendering`→`narrating`, `done`→`ready` — and
  `fetching text` simply never shows. A label map in `app.js`, no backend.
- **The queue progress hairline** has a real fraction already, and it does not
  need backend work. `QueueRow` (`src/somnia/queue.py:161`) carries
  `chapters_done` and `chapters_total`, and `queue_view` already serves them.
  `chapters_done` is counted from the `chapters` table rather than kept as a
  counter, because a chapters row exists only once its m4a does — it cannot
  claim a chapter is listenable before it is. Rendering chapters is the bulk of
  the work, so it is an honest bar.

  The trap: `chapters_total` is **0 for every book rendered before that column
  existed, and 0 means "nobody wrote it down"**, not "no chapters". The hairline
  must check for 0 and draw nothing, rather than a 0% bar claiming a book has
  not started when nobody knows.

One happy accident: somnia's existing `ahead` flag and the design's spoiler rule
("tap to reveal · may spoil", the "you are here" divider) are the same idea
reached independently.

## Step 1 — run the workflow

```
Workflow({
  scriptPath: '.claude/workflows/apply-redesign.js',
  args: {
    projectId: '7cae092a-04f8-4319-b510-86b2f73f853a',
    outDir: '<repo>/.claude/design/somnia-redesign',
    branch: 'feat/apply-redesign',
  },
})
```

Five phases. The full reasoning is commented in the script; the short version:

- **Read the delta** — one agent per screen, concurrent and mutually blind,
  each classifying differences as layout / flow / new-feature / removal / copy
  / unclear.
- **Plan the slices** — one agent, needs every delta at once to order them.
  Vertical slices: markup + wiring + test together, each leaving the page
  working.
- **Build** — **sequential, by design.** somnia is one page; every slice lands
  in the same `index.html` / `style.css` / `app.js`. Parallel builders would
  produce colliding branches, not slices. Each slice commits green.
- **Verify** — two lenses per slice, concurrent, run while the next slice
  waits. `dark` judges it as someone half-asleep and one-handed; `wiring`
  follows every new control to its listener to catch silently dead buttons.
  Blockers are fixed before the next slice stacks on top.
- **Report** — what landed, what was deferred, what never got built.

## What will need the user, mid-flight

The workflow is built to stop rather than guess, so expect these:

- **The new features.** A static mock cannot show what happens on press. Any
  new feature needing a server endpoint gets **deferred**, not invented — a
  control with nothing behind it is a decision, not a task.
- **Ambiguities** flagged by the screen readers land in `deferred` too.

Both come back in the final report. Neither should be resolved by guessing.

## Non-negotiables the workflow enforces

- **Render at 360x780 with a 20px root**, never 412x892/16px. A round of
  mockups was already thrown away over this. The tell that the render is right:
  "Where do you want to be?" nearly fills its line. Half-width means the wrong
  phone.
- **Agents must Read the PNGs**, not reason from the CSS. Reporting on a layout
  nobody opened would make the whole exercise worthless.
- **Checks per slice**: `node --test tests/web`, `pytest`, and both renders
  (360x780 control, 360x470 chat with the keyboard up).
- **Comments must follow the layout.** `index.html`'s comments record *why*
  each control sits where it does — the dead band under the chapter strip, the
  sleep timer kept a thumb's width from the transport. If a slice moves one,
  the comment is rewritten or deleted. Prose defending a layout that no longer
  exists is a defect.

## Delivery

Slice per screen, a commit each, per the user's choice. Push and PR per the
user's global rules: HTTPS + `gh` credential helper, never SSH; `gh pr create
--head <branch> --base main`; gate merges with
`gh pr checks <n> --watch && gh pr merge <n> --merge --delete-branch`.
