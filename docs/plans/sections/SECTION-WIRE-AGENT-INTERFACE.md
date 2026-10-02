# Section: Agent interface — tools, events, undo, permissions (Wire)

Reviewed: `REPO-AUDIT.md`, `RESEARCH.md` §3–5, `PLAN.md` §2–3, `SECTION-GLYPH-UX.md`, and `hermes_studio/mcp.py` on `main` via `gh api` (589 lines; hand-rolled JSON-RPC over stdio, 18 tools, already sets `readOnlyHint`/`destructiveHint`/`openWorldHint` annotations, `notifications/progress`, `structuredContent`). No clone, no code.

I agree with PLAN §3's tool list. This section pins down the **contract** around it so Hermes, other MCP clients and the sidebar all see the same truth.

## 1. Tool contract (every write tool)
- **In:** `project_id`, `base_version`, the ops or args, a user-facing `summary`, optional `group_id` (so a macro such as "remove fillers" is **one** history entry, which is Glyph's ask), and `client_op_id` (idempotency: a retried call after a timeout must not apply twice).
- **Out:** `op_id`, `group_id`, `new_version`, `summary`, `changed_ids`, `before_frame` / `after_frame` (**refs** to engine-cached frames keyed by timeline hash, which is Bay's cache; the image bytes are only sent when the model asks via `timeline_frames`), `warnings`.
- **Errors** (keep the current `code` + `hint`): `conflict` (with `current_version` and a `history_diff` since `base_version`), `invalid_op`, `permission_denied`, `needs_approval`, `undo_blocked` (with the dependent `op_id`s).
- **Actor comes from the session token, never from a tool argument.** That's the AgentDrive lesson: caller-supplied identity gets forged.
- One tool registry in `api.py` generates MCP `tools/list`, the CLI and the Hermes plugin, so the 18-vs-14 drift the audit found can't come back.

## 2. How edit events reach the sidebar
- **One event bus in the engine**, append-only and fed by the op log. Every event has a monotonic `seq` plus `op_id`, `actor` and `version`.
- **UI:** SSE with `op.applied`, `op.undone`, `timeline.changed`, `approval.pending`, `run.paused`, `job.progress`. Reconnecting with `Last-Event-ID` replays from the log, so no card is lost when the app sleeps.
- **Sidebar cards join two streams on `op_id`.** ACP `tool_call` updates give the live "Trimming clip 3…" text. The engine event gives the truth: the version, the thumbnails and whether it applied. A card only shows "done" once the engine event lands.
- **MCP clients:** `notifications/progress` for renders (already implemented), plus an optional `timeline://<project>` resource with `resources/updated`, so non-ACP agents can notice when a human edits.

## 3. Undo
- The log is **append-only**: undo applies the inverse as a **new** entry and never rewrites history, so Prove can replay it.
- `history_undo{op_id | group_id}`: an agent may only undo its **own** entries, while a human can undo anyone's. If the inverse no longer applies cleanly, it returns `undo_blocked` with the dependent entries, which drives Glyph's "Restore to before this step".
- `checkpoint_restore` is a human-only action in Phase 1, because it can drop other actors' work.

## 4. Permissions (enforced in the engine, not only in the sidebar)
Claude, Cursor and Grok connect over MCP and never pass through ACP, so the mode has to live in the engine.
- **Ask:** write tools return `permission_denied`.
- **Propose:** a write parks as `approval.pending`; the UI card's Apply / Skip resolves it, and the call returns applied or `skipped`. For Hermes, ACP `session/request_permission` is the same prompt: Electron passes the approval to the engine, so the user is never asked twice.
- **Auto:** applies live; each step can still be undone.
- **Tokens:** a per-launch bearer token per session with scopes (`read`, `write`, `render`). Loopback only, with the existing Host/Origin checks from `studio.py`. Caps on ops per batch and render size.
- **Never in `tools/list`:** publish, upload, shell, or file writes outside the project. A contract test asserts the exact tool allowlist, the same pattern as the AgentDrive connector's startup check.

## 5. Where AgentDrive fits
**Not in the edit path.** The op log is the project's own history. The optional Phase 2+ use: at the end of a session, ingest one summary event (the request, the plan, which steps were kept and which undone), and read `get_context_pack` at the start of the next session, so Hermes learns habits like "this user always undoes music ducking". It is not a dependency, it waits until AgentDrive is registered and Pablo seals it, and it relies on AgentDrive's redactor because prompts can contain keys.

## Gaps and risks
- `mcp.py` speaks stdio only. Streamable HTTP plus sessions plus resources is a real upgrade: either adopt the official `mcp` Python SDK (recommended) or extend the hand-rolled server. It needs pinned protocol versions either way.
- **Two engines, one project:** if the stdio proxy opens a project headless while the app is running, there are two writers. That needs a per-project lock, with the proxy attaching to the running engine.
- **Approval waits (revised after Glyph's pushback):** a parked Propose write **never** skips or applies itself. The run pauses, the write stays parked in the engine until the person answers, and the header reads "Paused, waiting for you". The MCP call returns `needs_approval` with a `pending_id` instead of hanging, the agent waits on the `approval.pending` and `op.applied` events, and if the ACP request expired, Hermes re-asks for the step after the answer.
- Image cost: return frame refs by default and send pixels only on request (contact sheets over many single frames).

## Open questions for Pablo (2)
1. Can outside agents (Claude, Cursor, Grok) **write** to a project when the app is closed, or only while it's open so a person can watch? I recommend writes only while it's open in Phase 1, with headless writes read-only.
2. Should we retire the native Hermes plugin and run MCP only (recommended), or keep it as a generated shim?

## Size
- **Phase 0:** about 1.5 weeks for the tool schemas and registry, the HTTP endpoint with token and scopes, the stdio proxy with a project lock, the event bus, and the contract tests (allowlist, idempotency, conflict, undo round-trip).
- **Phase 1:** about 2 weeks for the ACP client in Electron, the engine approval gate, and joining cards on `op_id`.
- **Phase 2:** about 1 week for the eval harness hooks (the step and undo counts Prove measures).
