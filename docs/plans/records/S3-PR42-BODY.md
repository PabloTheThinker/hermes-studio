## S3: project store, timeline engine over HTTP, /mcp timeline tools

Builds `S3-SPEC.md` as approved by Ada (2026-10-01, 7:33 PM ET; all 31 decisions), against Wire's contract (tests 1–103). Branched from `c6de84e`.

### What's in the slice
- **Project store** (`hermes_studio/project.py`): `~/.hermes/clips/projects/<id>/` holds `base.json` + `oplog.jsonl` as the source of truth, with `timeline.json` as a cache and `snapshots/` every 50 versions.
  - Commit order: line fsync → cache → snapshot → event (D1, D2).
  - Recovery: a torn tail is truncated on open; a missing final newline is repaired before the next append; a corrupt line gives `failed{seq}`.
  - Read-only closed-app reads (D28).
- **Single writer** (D5, D6, D14): `.lock` holds `{pid, port, started_at, engine_version, attach_token_sha256}`; a second engine is refused with `failed` + hint. The stdio proxy gets a 0600 `.attach`.
- **Tokens** (D13): `ui`, `acp:hermes`, `mcp:<name>` and `control`, with read/write scopes. The actor always comes from the token.
- **Event bus + SSE** (D9, D11, D12):
  - Event ids are seqs, with `Last-Event-ID` replay, `stream.reset` and slow-client drop.
  - `GET /mcp` streams resource updates.
  - stdio `resources/subscribe` follows the engine.
- **HTTP** (`hermes_studio/http_engine.py`):
  - `GET /api/projects/<id>/{status,hash,history,history/diff,events}` (D26 query parsing).
  - `POST /api/projects/<id>/{timeline_apply,history_undo,history_redo}`.
  - `POST /mcp`.
- **/mcp timeline tools** (`hermes_studio/mcp_timeline.py`): 11 tools on HTTP /mcp and stdio, all going through one `Oplog.call` path.
  - `_s` conversion and the check-view → both-sent → conversion order (D21–D23, D29–D31).
  - The envelope check comes before the op stage.
  - Errors are repointed to the `_s` arg.
  - Schemas enforce nothing the engine doesn't.
- **D27 framing** (`hermes_studio/jsonrpc.py`, `mcp.py`, `studio.py`):
  - One Content-Length check for stdio and HTTP: `fullmatch [0-9]+` after `strip(b" \t")`, at most 8 digits.
  - `MAX_BODY` is imported from `studio.py`.
  - Over-cap bodies get -32700 first, then a 16×`MAX_BODY` drain in ≤64 KiB chunks, unscanned.
  - Malformed or duplicate headers: -32700 id null, a stderr line, and a nonzero exit.
  - HTTP checks `Transfer-Encoding` first (400 `unsupported transfer encoding`) and then requires exactly one `Content-Length` (`get_all`). Every body refusal sends `Connection: close` with `close_connection=True`; HTTP /mcp answers with -32700.
- **D17**: protocol output is `ensure_ascii=True` (mcp.py, cli.py).

Rule-id counts are unchanged at **17 oplog / 36 validator**. "invalid content length" and "unsupported transfer encoding" are messages, not rule ids.

### Tests → spec
| Tests | File | Spec |
|---|---|---|
| 93 (C5 retry, live + after load), D4, D10/D19 paging, conflict cap, head, D29 helper step 5 | `tests/test_s3_store.py` | §4 rules 1–5, D4, D10, D19, D29; §11 rows 1, 2, 3, A–D |
| Store: commit order, snapshots, torn tail, missing newline, corrupt line (61d), base.json faults (61), bad cache (61c), closed-app reads (58), lock/attach (D5/D6/D14), serialized writes (D3), events (D9/D11), tokens (D13) | `tests/test_s3_store.py` | §1–§3, D1–D3, D5, D6, D9, D11, D13, D14, D28; §11 rows E, F |
| 88, 89, 90, 91, 92, 95, 96, 97, 98, 99, 100; auth/scopes, HTTP /mcp protocol, SSE, `used` | `tests/test_s3_mcp.py` | §1g/§1h, D16, D21–D23, D26, D29–D31; §11 rows 1, G |
| 94 (C5 over HTTP REST + ACP-token /mcp) | `tests/test_s3_mcp.py` | §4 transport table, D13 |
| 94 (C5 over the attached stdio proxy), D28 closed-app stdio | `tests/test_s3_stdio.py` | D14, D28 |
| 101, 102, D15, D17 | `tests/test_s3_stdio.py` | D15, D17, D27; §11 rows 4, H |
| 103 (REST and HTTP /mcp refusals, exact cap, no Content-Length) | `tests/test_s3_http.py` | D27(d)/(e); §11 row 4 |

### §11 allowed replay diffs (the only engine behavior changes)
1. Anchor keys are checked by name (D29, helper step 5, public runs only).
2. C5 replay warnings: stored result warnings (always `[]` in S3) followed by this call's own strip warnings, live and after reload. No S3 line changes.
3. D4: a non-string `project_id` gives `bad_arg` @ `/project_id` with no `id`.
4. D17 + D27: input parsing and framing, and ASCII output.

- A. History arg checks (D19 order).
- B. History return shape `{entries|records, next_since_version, head_version}`.
- C. `hash` in `history_diff` records.
- D. Conflict cap of 200, plus `history_diff_truncated`.
- E. Corrupt `base.json`: `schema_mismatch`, `invalid_doc` or `failed`, with no hash.
- F. Corrupt log line and torn tail / missing newline: `failed{seq}`, truncate or repair on open, read-only when closed.
- G. A missing `project_id` at /mcp gives `missing_arg` first.
- H. D15 protocol answers.

**Differential gate:** a seeded random corpus was replayed through `Oplog.call` at `c6de84e` and at this head (6 seeds × 4000 calls). The only differing answers are row 1 anchor-key errors, and the final hashes are identical.

### Evidence
`/workspace/desk/hermes-studio/evidence/s3-build/` (on the build box): the smuggling probes re-run at this head, an engine-path newline probe, and the fuzz gate summary.

