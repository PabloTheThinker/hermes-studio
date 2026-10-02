# S3 rulings addendum (Ada, 2026-10-01)
The S3-SPEC.md in this folder was restored from a backup taken before the last rulings. Where this addendum and S3-SPEC.md disagree, this addendum wins. Prove's S3 gate checks against both. Contract: 104 tests. Rule ids stay at 17 oplog / 36 validator. Message strings are not rule ids.

## Rulings made after the backup (8:28 to 9:02 PM ET)
- **F1 (row F):** `_replay_from` and `doc_at_head` check every line exactly as `Oplog.load` does, `inverse` included. A tampered middle line gets `failed` with `seq: 2`, whether the app is open or closed.
- **O2 (row E):** a `base.json` with a stale hash or no `hash` key gets `invalid_doc` `hash_mismatch` at `/hash`, whether the app is open or closed. Other `validate()` faults get `invalid_doc` exactly as reported. Only a file that is unreadable or not JSON gets `failed`.
- **stdio:** remove the blank-line skip (mcp.py:319–320). In Content-Length mode, anything between frames that is not a valid header, a blank line included, gets -32700 with id null, a stderr log and a nonzero exit. No skip-ahead anywhere.
- **O1, newline mode:** read at most `MAX_BODY + 1` bytes per line. A longer line gets -32700 with id null, a stderr log and a nonzero exit, and is never parsed (test 102(b2)).
- **HTTP: every method runs these checks before routing, in this order:**
  1. Any `Transfer-Encoding` gets 400 `{"ok":false,"error":"unsupported transfer encoding"}`.
  2. Content-Length must be exactly one valid value, read with `get_all`, using the same strip, fullmatch and 8-digit rule as stdio. An invalid value, `-1` or a duplicate gets 400 `{"ok":false,"error":"invalid content length"}`.
  3. A GET with a valid length above 0, even one over the cap, gets 400 `{"ok":false,"error":"request body not allowed"}`. The body is never read.
  4. Over the cap (only a POST gets this far) gets "request body too large".
  - On HTTP /mcp, each of these refusals is -32700 with id null instead of the REST body. Every refusal sends `Connection: close`.
  - A GET with no length or a length of 0 is unchanged.
- **§11 row 4** adds the GET checks (before: 200 then 200 on /api/doctor; a chunked GET got 200 and a close) and the newline cap (before: a 3 MiB line was read and answered).
- **Path decoding:** split the path first, then decode each segment, the same way on GET and POST.
- **`ruff format --check`** passes on the files the PR touches.

## §13 As built (approved at 8:28)
- **Projects:** `create_project` is test-only. Every project opens at startup, a new one opens on first use, and opening replays the full log.
- **Tokens:** the ui token's human id is "user".
  - The control token gets `permission_denied` on every tool and has no PlanContext.step API.
  - Include a scope table for each token kind.
  - Token delivery is out of S3. When it's built, the Electron preload passes the token in memory, never through a URL or localStorage.
- **REST writes:** `POST /api/projects/<id>/{timeline_apply,history_undo,history_redo}`.
- **`used`:** keyed by the `_s` argument name. The last op wins, anchors go under `offset_s`, and `src_s` is a list.
- **Exports:** `exports/<id>-v%06d.otio`.
- **HTTP /mcp:** -32600 gets a 400 and notifications get a 202. GET /mcp streams every project and picks up projects opened mid-stream (test 104).
- **Error order:** engine_offline stays where it's built, and project-id checks run before the engine. Write out the full order.
- **Files:** project files are owner-only (0600).
- **Deferred:** `get_timeline{summary:true}` moves to S4.

## Tests owed in the S3 commit
- **89:** use real ops with valid args, plus the ops whose id is optional, so every case reaches bad_arg at /ops/0/id.
- **92:** assert `/markers/1/label` and `mk1` literally.
- **94:** the actor is agent/stdio with no plan step.
- **101:** add a stray `\r`.
- **102(a):** both malformed-header lists, `5` sent twice with an embedded frame, whitespace-only, stdio ٣, an empty value, and a blank line between frames.
- **102(b):** 16777217 with an embedded frame.
- **102(b2):** the newline cap.
- **103(v):** chunked alone, chunked with abc, and chunked with a duplicate 5/5.
- **103(vi):** a GET with an embedded request, with abc, with chunked, and with `Content-Length: 2000000`.
- **104:** a mid-stream project gets `resources/updated`.
- **D26 route test:** add the decode case.
- **Windows:** a byte-range `.lock` test in the windows job. It blocks the merge.
- **Evidence:** one probe for each §11 row in evidence/s3-build/s11_rows/.
