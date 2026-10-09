# S8 spec: engine mode gate (Ask / Propose / Auto, parked writes)

Status: **draft, built on `feat/editor-s8-gate` (stacked on S7). Not ruled.** Plan of record: PLAN-MERGED.md §4.6, Decisions 1–2, §5 row 8; SECTION-WIRE-AGENT-INTERFACE.md §2/Gaps; SECTION-GLYPH-UX.md Steering 1 and 5. Prove gates: **C12 (gate part)**, **E5**, C6 (conflict pauses).

## 1. Behaviour

- **The mode lives in the engine**, per project, in `<project>/mode.json` (0600); `project_status.mode` reports it (open and closed). Unset → **Propose** (Decisions 2).
- **Only agent writes are gated.** A person approves, so `ui` (human) writes always apply. Gated tools: `timeline_apply`, `history_undo`, `history_redo`, and everything built on them: `transcript_cut` (S7) and `import_media` (S4). The gate runs inside `Project.write_locked`, so /mcp, REST, the attached stdio proxy and the S4/S7 tools all pass the same check.
- **Ask:** an agent write is `permission_denied` (REST 403). `transcript_cut` and `import_media` refuse before doing any work.
- **Propose:**
  1. The call is checked exactly as if it were applied (the engine's envelope, `conflict`, ops, validator), on a scratch copy of the log. An invalid or stale write is refused at once and never parked.
  2. A valid one is parked in `<project>/pending/<pending_id>.json` (0600): actor, plan step, tool, `client_op_id`, summary, op count, `base_version`, the call (ticks, after S3's `_s` conversion), and for an import the follow-up (start its media job).
  3. The call returns **`needs_approval`** with `pending_id` (REST **202**; /mcp `isError` with the body), and `approval.pending` (the record without the call) goes to the project's SSE clients.
  4. Nothing is logged and the hash doesn't change until a person answers. **It never times out and never resolves itself** (Decisions 1).
  5. A retry (same actor and `client_op_id`) returns the same `pending_id`; after Apply the engine's dedupe returns the applied result; after Skip it returns `{ok: true, status: "skipped", pending_id, summary}` (the non-error status of PLAN-MERGED §4.5).
- **Resolve:** `approval_resolve {pending_id, decision: apply|skip, rest?}` by a **person** only (agents, ACP Hermes included, get `permission_denied`). Apply runs the parked call through the normal write path with the agent's actor and step (so the entry is the agent's). A conflict at that point (a person edited in between) makes it `failed` with the engine's `conflict` body: the run pauses (C6, E6). `rest: true` applies or skips every other edit the same agent has parked, oldest first. **Exactly once:** answering a resolved edit returns its outcome and changes nothing. `approval.resolved` goes to SSE clients.
- **Auto:** agent writes apply at once.
- **Mode changes:** `set_mode {mode}` by a person; `mode.changed {mode, was}` on SSE.
- **Reads:** `approval_list {all?}` → `{mode, pending}`; `approval_status {pending_id}`. Both work with the app closed. REST: `GET …/approvals[?all=1]`, `GET …/approvals/<pending_id>`, `POST …/approval_resolve`, `POST …/set_mode`.
- **Restart:** parked edits are files, so they survive a restart and can be resolved by the next engine.

## 2. Decisions to rule (Ada)

- **D1 (proposed).** Human writes are never gated, in any mode.
- **D2 (proposed).** Validate before parking (an agent learns about a bad op at once, not after a person approved it).
- **D3 (proposed).** "Apply the rest" means "every edit this agent has parked now", not "switch to Auto for this run". A per-run Auto needs ACP run ids (Wire's Phase 1 ACP client).
- **D4.** The S3–S7 test harness opens projects in Auto (`tests/s3_app.py`), since those contract tests predate the gate; the S8 tests use Propose.
- **D5.** The project mutex is now re-entrant (`RLock`): the gate notifies SSE clients and runs parked calls while holding it.

## 3. Engine diffs

- `project_status.mode` is the mode (was `null` in S3).
- Agent writes in a fresh project are parked, not applied (the Propose default). No op, rule id or log-line change. New error code `needs_approval` (exit code as `failed`).
- `tools/list` has 24 tools.

## 4. Tests

`tests/test_s8_gate.py` (20): default Propose; C12 Ask over plain MCP and REST (and `history_undo`, `transcript_cut`), a person still edits; C12 Propose parks (no entry, same hash, REST 202, listing, retry → same `pending_id`); E5 apply exactly once and the retry gets the result; skip and the retry says skipped; apply the rest per agent (with a stale one failing as `conflict`); a human edit in between → `failed` conflict and the human's op stays; nothing resolves itself; invalid/stale writes refused, not parked; only a person resolves or sets the mode (ACP Hermes too); 6 resolve refusals; Auto applies, `mode.json` persists, SSE order `mode.changed → op.applied → mode.changed → approval.pending`; survives a restart; a transcript cut parks as one edit; an import parks, then builds its media after Apply.
