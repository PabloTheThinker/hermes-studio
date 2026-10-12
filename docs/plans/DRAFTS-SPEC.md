# Phase 2 Q2: draft branches

Status: **draft, built on `feat/editor-drafts` (stacked on `feat/editor-polish`). Not ruled; it adds one internal op and one engine tool, so it needs Ada.** Gate (SECTION-PROVE-ACCEPTANCE Q2): *Discard returns the main hash exactly; Keep equals replaying the branch.*

## Behaviour (`drafts.py`)

- `draft_new {project_id}`: copies the main timeline at its head into a new project `<main>.d<6 hex>` (version 0, mode **Auto**: a draft is a sandbox) with `draft.json {main, from_version, from_hash, created, by, state: "open"}`. Agents may start drafts in Propose and Auto, not in Ask. A draft can't have drafts.
- The draft is an ordinary project: every tool works on its `project_id`, with its own log, undo and cards.
- `draft_keep {project_id: <draft>, summary?, client_op_id?}` (**a person only**): the main's media, tracks and markers become the draft's in **one entry** with the person as actor. If the main moved since `from_version`, it's the engine's `conflict` (the person re-drafts or discards). The draft is marked `kept` with the entry's `op_id`.
- `draft_discard {project_id: <draft>}` (**a person only**): closes and deletes the draft. The main never changed, so its hash is exactly what it was.
- `draft_list {project_id: <main>}`: the main's drafts and their state.
- **Edit page:** the main's sidebar has *Start a draft* and lists open drafts; inside a draft, a banner offers *Keep (one undo)* and *Discard*.

## Engine additions (for Ada)

- Internal op **`replace_body {media, tracks, markers}`**; its inverse is `replace_body` with the old values. Replays and undoes like any internal op.
- **`Oplog.call(session, "keep_body", {client_op_id, summary, base_version, body, group_id?})`**: one `replace_body` op as one entry (dedupe on `client_op_id`, `conflict` on a stale `base_version`, the validator on the result). `call` stays the only way to write (S2's invariant test is unchanged). No MCP tool or REST route maps to `keep_body`; only `draft_keep` (a person) reaches it, through `Project.keep_locked` (cache, snapshot, `op.applied` like any write).
- No rule id changes (17 / 36). `tools/list`: 31.

## Tests

`tests/test_drafts.py` (6): Discard leaves the main hash exactly; Keep makes the main's body equal to the draft's, equal to replaying the draft's own ops, in one entry that reloads and that one undo reverses; a second keep is refused; Keep after the main moved is `conflict`; only a person keeps or discards; listing, drafts of drafts, Ask mode, unknown args; `keep_body` retry and bad args.
