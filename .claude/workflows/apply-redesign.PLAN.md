# Applying the redesign — plan

Written 2026-08-06. Companion to `.claude/workflows/apply-redesign.js`.
Read this first if you are picking the job up in a fresh context.

## The job

A redesign of somnia's page exists, made in Claude Design. It carries layout
changes, some changes to the flow, and "a couple of new minor features". It has
to become the real page — drawn, wired, tested — landing as one commit per
slice rather than one large diff.

## Step 0 — get the design on disk (BLOCKING)

**This is the only thing standing in the way, and it was not resolved before the
user went AFK.**

What was tried and what happened:

| Attempt | Result |
|---|---|
| `DesignSync list_projects` | `[]` |
| `/design consent` + `/design-login`, then `list_projects` again | `[]` — still empty after both authorizations |
| `Artifact action:list scope:all` | Only 4 artifacts, all published by Claude in earlier sessions (old proposals, not the redesign) |

`list_projects` returns only design-system projects the user can **write** to.
An org-owned project, or a project that is not
`PROJECT_TYPE_DESIGN_SYSTEM`, is invisible to it. So the empty list does not
mean the redesign is not there — it means it cannot be enumerated from here.

Ways in, best first:

1. **Project UUID.** If the user supplies the claude.ai/design project URL, pull
   the UUID out of it and call `DesignSync get_project` then `list_files`
   directly. This works even when `list_projects` cannot enumerate it — worth
   trying before anything else.
2. **A URL to fetch.** If the redesign was published as artifacts or any
   shareable page, `WebFetch` each screen and save the HTML/CSS locally.
3. **A local export.** The user saves the screens to a directory and names the
   path. No auth in the loop; most reliable.

Whichever route, the outcome is the same: **the redesigned screens as files in
one directory.** Everything downstream reads from disk, not from the API.

Do not start without it. There is nothing safe to assume about a redesign you
have not seen, and a plausible invention would be indistinguishable from the
real thing until the user looked at it.

## Step 1 — run the workflow

```
Workflow({
  name: 'apply-redesign',
  args: {
    designDir: '<absolute path to the exported screens>',
    screens: ['<file>.html', ...],
    notes: '<whatever the user said about the redesign and its new features>',
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
