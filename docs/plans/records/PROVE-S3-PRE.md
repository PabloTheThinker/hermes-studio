# PROVE S3 PRE-GATE — PR #42 @ 0282e9f (NOT a verdict)

Prove (independent verifier), Thu Oct 1 2026, ~8:55 PM ET. PR #42 `feat/editor-s3-store-mcp`, head
`0282e9f86a96c6a7ca7cbbdb687730ce5d585d35` (re-checked 8:52 PM ET: still the head, OPEN/MERGEABLE, 2 commits on
`c6de84e`). Spec: `S3-SPEC.md` (§11 = the only allowed engine-answer diffs). Contract: `WIRE-S1-REGISTRY-CONTRACT.md`.
Work done in throwaway detached worktrees of `/workspace/hermes-studio-s2b` (head + base), since removed. Nothing pushed,
commented or merged. Paths below are relative to this directory.

## Result per check

| # | Check | Result |
|---|---|---|
| 1 | Full suite; 17/36 | **PASS**: 923 passed, 0 skipped (`tests/pytest-head.txt`); `ruff check` clean; 17 op-level / 36 validator rule ids (p39 at head, `gate/stdout/head/p39_probes.stdout`); no new rule-id literal in code (`bad_schema` is one of the 36) |
| 2 | Replay gate + per-row probes | **PASS for the replay; FAIL on one targeted row-F probe (F1)**. 21 corpora, 0 diffs outside §11 |
| 3 | C5 over HTTP / ACP / MCP | **PASS**, live and after an engine restart, on 5 paths |
| 4 | D27 stdio | **PASS**; blank-line skip confirmed present (known pending fix) |
| 5 | HTTP 103 | **PASS** on the listed matrix; **F2**: GET routes are not covered |
| 6 | Contract 88–103 | **PASS**: every number present, 181/181 S3 tests pass; minor coverage gaps noted |
| 7 | Other spec-vs-code | F1, F2 and observations O1–O4 below |

## Findings

**F1 (row F / D28(a)): a tampered `inverse` on a middle line names the wrong line when open, and isn't detected when closed.**
- Repro: a 5-line log with line seq 2's `inverse` edited (hash and version left intact).
- `c6de84e` `Oplog.load` refuses it: "oplog line 2: replay does not reproduce the entry".
- At head:
  - **Open app**: `failed`, `seq: 5`, "oplog line 5: …". It names the wrong line; §11 F says `n` is the bad line's seq.
  - **Closed-app read**: serves the doc normally (`get_hash` OK at v5), unlike the open app. That breaks F's "the same `failed` body whether the app is closed or open" and D28(a) step 4, which says the closed read replays via `Oplog.load`.
- Cause:
  - `project.py:233–246` `_replay_from` compares only `hash`/`new_version` (:241), never `inverse`, which `Oplog.load` does check.
  - The open path at `project.py:465–469` calls `_replay_from` after `Oplog.load` fails. `_replay_from` finds nothing, so the code falls back to `log_error(len(parsed.lines))`.
  - The closed path (`doc_at_head`, `project.py:278–296`) uses `_replay_from` directly.
- Fix idea: compare the replayed `inverse` in `_replay_from` (or reuse `Oplog.load`'s per-line check), and never fall back to `len(lines)`.
- Evidence: `probes/show_store.txt` §"F middle line (seq 2) tampered inverse"; `probes/p_store.py`; `probes/out_store_head.jsonl`.

**F2 (D27(d)/(e)): GET requests never go through `body_length`, so HTTP smuggling still works via GET.**
- `studio.py:324–334` `do_GET` goes to `http_engine.get` (`http_engine.py:123`) or to static routes without ever calling `body_length` (`studio.py:151`).
- Results:
  - `GET /api/doctor` with `Content-Length: 46` and body `GET /api/doctor …`: **200, then 200**, so the embedded request runs on the same connection.
  - `Content-Length: abc` + embedded GET: 200, 200.
  - `GET /api/projects/p1/timeline` + CL body: 404, then 200.
  - `Transfer-Encoding: chunked` on a GET: not refused.
- The spec says "a request with **any** `Transfer-Encoding` … gets 400" plus a close. Test 103 covers POST only.
- Likely pre-existing for GET at `c6de84e`, so this may be a scope call for Ada, but it is the same hole D27 closes for POST.
- Evidence: `probes/out_http_head.jsonl` (rows "GET + …"); `probes/p_http.py`.

### Observations (not blocking; for Ada/Bay)
- **O1 (D27, newline framing): no size cap.** `mcp.py:331` uses an unbounded `self.inp.readline()`. A 3 MiB newline-framed message is read whole and answered (`probes/out_stdio_head.jsonl`, last row, `readline_got: 3145787`). MAX_BODY is applied only under Content-Length. The spec doesn't explicitly require a newline cap.
- **O2 (row E): a base.json with no `hash` key is accepted.** `validate()` doesn't flag it (`project.py:171` `read_base`). Row E's after-text names only a *stale* hash, so this is within the spec text. Was the "or missing" in the before-text meant to carry over?
- **O3 (format): `ruff format --check` fails on 8 files that were clean at c6de84e.** They are http_engine.py, mcp_timeline.py, project.py, tests/test_oplog.py and tests/test_s3_{http,mcp,stdio,store}.py (`tests/ruff.txt`). CI runs only `ruff check`.
- **O4 (test coverage vs contract; my probes cover all of these and they pass):**
  - 102(a) (`tests/test_s3_stdio.py:179–182`) omits empty, whitespace-only, `٣`, and `5` + stray `\r`/`\v`.
  - 103's TE list (`tests/test_s3_http.py:63`) omits TE + `abc` and TE + duplicate CL.
  - 92 pins the NFD marker label only by `rule` + REST parity, not the literal `/markers/1/label` + `mk1` (`tests/test_s3_mcp.py:245–249`).
  - 94 doesn't exercise HTTP /mcp with a plain agent token (no step) and never retries after a restart (`tests/test_s3_mcp.py:291–312`).
  - Bay's "flags" on 92/94 match the contract's "corrected 8:32 PM, Bay right" notes; the tests follow the corrected wording.

### Known pending fixes (already being fixed; confirmed present at 0282e9f)
- **Blank-line skip between Content-Length frames** (rejected by Ada): `mcp.py:319–320` (`if line in (b"\r\n", b"\n"): continue`). Empirically, CRLF, LF and 3 blank lines between two frames are all skipped, and both frames are answered (`probes/out_stdio_head.jsonl`, "blank …" rows).
- **Windows .lock test**: `tests/test_s3_store.py:337–356` reads `.lock` while the OS lock is held. On Windows, msvcrt byte-locks it (`project.py:304–308`).
- **GET project-id decode**: `studio.py:328` unquotes the whole path before `http_engine.py:129` splits it, so a `%2F` in an id splits. (POST `rest_post` unquotes `parts[0]` after the split.)
- **GET /mcp mid-stream follow**: `http_engine.py:212–215` snapshots `ENGINE.projects` when the stream opens, so projects opened later are never followed.

## Check 2 detail: replay gate
- **What was replayed:**
  - Recorder: `gate/rec.py` wraps `Oplog.call`, `history_list`/`history_diff`, `Oplog.load` and `replay`. It records top-level calls only (base's conflict path calls `history_diff` internally). At head it pages `history_*` for old-style callers.
  - Corpora, all run on c6de84e and 0282e9f with c6de84e's test helpers:
    - S2: c2_probes, c2b_probes, c2b_junk, c2c_probes, c2_order, c2_fuzz ×1200;
    - S2b: p38_probes, p38_m0, p38_fuzz ×1000, p39_probes, p40_probes, p40_fuzz ×1500;
    - Bay's fuzz_gate, seeds 1–8 × 3000;
    - c6de84e's tests/test_oplog.py + test_timeline.py under pytest.
- **Classifier:** `gate/classify.py` compares call by call. Random engine op_ids are normalised by order of first appearance.
- **Result (`gate/classify_full.out`):** 0 UNCLASSIFIED in 20 corpora. The diffs by row:

  | Row | Diffs |
  |---|---|
  | 2 | 3427 |
  | C+D | 1002 |
  | 3 | 132 |
  | 1 | 86 |

- **The pytest corpus:**
  - main's `test_call_is_the_only_way_to_write` fails at head at its public-surface assert. The four extra `Oplog` methods (`head`, `precheck`, `check_apply_envelope`, `check_undo_envelope`) are spec'd new surface (§5 row 6, §1h step 7, line 489), and head's copy of the test lists them.
  - That stops the test before its `TypeError` call, so the streams were re-aligned after dropping that one call (`gate/classify_pytest_realigned.out`).
  - Diffs by row: 2 ×2, 3 ×187, C+D ×2.
  - The only leftover is the tmp-path name in a FileNotFoundError message (`tmp-base` vs `tmp-head`), an artifact.
- **Each §11 row's after-behavior, shown by targeted probes:**
  - **Row 1** (`probes/side_engine.txt`):
    - `unknown_arg` / `missing_arg` @ `/ops/k/anchor/<key>`, no `id`/`problems`, `offset` before `to`.
    - Beats `not_found` and `bad_arg`.
    - Unchanged for non-dict anchors, `null`, internal undo.
  - **Row 2:** own strip warnings on an exact retry; `[]` on a clean retry; live and after `Oplog.load`. Log bytes are identical to base.
  - **Row 3:** `bad_arg` @ `/project_id` with no `id` for 5, null, true, [], {}, 1.5. A string is still `not_found` with its `id`.
  - **Row 4** (`probes/out_stdio_*.jsonl`, `probes/out_mcp_head.jsonl`):
    - Before: huge, badutf8 and lspbad give exit 1.
    - After: -32700 and the session goes on.
    - A lone surrogate in an id or tool name is answered with `\u` escapes, ASCII-only, on stdio and HTTP.
  - **Row A:** bounds and order hold (unknown, missing, project_id, since, limit). Above the head gives an empty page.
  - **Row B:** page shape OK. The paged walk is complete, and the items are byte-identical to base (`probes/p_rowBD_bytes.py`).
  - **Row C:** `hash` appears in records and in the conflict `history_diff`.
  - **Row D:** the conflict holds the oldest 200; `history_diff_truncated` is true/false. Byte-identical to base apart from the cut.
  - **Row E:** schema_mismatch with expected/got; hash_mismatch @ /hash with no `id`; duplicate_id ×2; failed for non-JSON, bad UTF-8 and empty; `not_object`. The same body on every read and write, closed and open, with no hash.
  - **Row F:** torn tail and missing newline OK. Middle bad JSON, unknown key, out of sequence and tampered hashes are OK in both states. **The tampered inverse fails (F1).**
  - **Row G** (`probes/out_mcp_head.jsonl`):
    - /mcp (HTTP, closed-app stdio, attached stdio): a missing `project_id` gives `missing_arg` @ `/project_id`, before unknown args and type errors, on every tool.
  - **Row H:**
    - array, string, number, null, `{}`, no method, method 5 → -32600 with `id: null` (HTTP 400);
    - `params` `[]`, `""`, 0, false, [1], null, "x" → -32602 with the id;
    - `arguments` null, [], "", 0, false, [1], "x" → -32602;
    - a missing `params` is OK;
    - a notification with bad params gets no reply on stdio, 202 on HTTP.

## Check 3 detail: C5 (`probes/p_mcp.py`, `probes/out_mcp_head.jsonl`, "C5 …" rows)
- **Paths:** REST + ACP token, REST + agent token, HTTP /mcp + agent, HTTP /mcp + ACP, attached stdio.
- **Calls, all with a forged `actor` and a forged `step` on op 1:**
  - the forged apply;
  - an exact retry;
  - a clean retry;
  - an undo with a forged `step`;
  - a clean undo retry;
  - then an engine restart (`Oplog.load`): a forged retry, a clean retry and a forged undo retry.
- **Every path:**
  - Warnings are `[/actor, /ops/1/step]` on the first call and on forged retries; `[/step]` on undo; `[]` on clean retries.
  - It's the same op_id and the same fields apart from warnings, both live and after the restart.
  - The log is unchanged by retries. It holds the transport's actor (hermes with step 3 / claude / stdio, no step), never an op-level `step`, `"x"` or `human`.
- Results are identical across all 5 paths.

## Check 4 detail: D27 stdio (`probes/p_stdio.py`, `probes/out_stdio_head.jsonl`; `_base` = before)
- **Crash probes:**
  - huge, badutf8, lspbad → -32700, then the next message is answered, exit 0;
  - neg → -32700, close, exit 1;
  - short → -32600 then -32700, close, exit 1, id 7 never runs.
- **Boundaries:**
  - 1048576 → accepted.
  - 1048577 and 16777216 → -32700 **before any body byte is sent** (staged). The drain reads at most 65536 bytes per call (stdin wrapped, `read_req` max 65536), and id 10 is answered.
  - 16777217, 100000000, 000000007 → -32700, a stderr line, exit 1.
  - 00000007 → read as 7.
- **Malformed:** -1, +5, 1_000, abc, empty, whitespace, ٣, ٣٣, `5\r`, `5\v`, and duplicates 5/5 and 5/7 all give -32700 with `id: null`, a stderr line and exit 1. The embedded id 9/99 never runs.
- **102(b):** a 2097152-byte body holding an id 9 frame → -32700, id 10 answered, id 9 never runs. 16777217 → close.
- No read over 64 KiB during a drain. Bodies ≤ MAX_BODY are read in one `read(n)`, which the spec allows.

## Check 5 detail: HTTP 103 (`probes/p_http.py`, `probes/out_http_head.jsonl`)
- **Routes and cases:**
  - Routes: `/api/restyle`, `/api/projects/p1/timeline_apply` and `/mcp`.
  - Cases: oversize 1048577 with the /api/doctor smuggle; -1, abc, +5, 1_000, ٣ (UTF-8 bytes), 100000000, 000000007; duplicates 5/5 and 5/7; TE chunked alone, + abc, + duplicate CL, CL-before-TE order, TE twice, TE identity.
- **Results:**
  - Exactly one response, `Connection: close`, socket closed, `/api/doctor` never answered.
  - REST bodies are exactly `request body too large`, `invalid content length` or `unsupported transfer encoding`.
  - /mcp gives 400 with -32700 and `id: null`.
  - 1048576 is accepted with keep-alive. A missing CL is unchanged (read as 0; on /mcp an empty body gives -32700).
  - A missing token gives 401, and an unknown project route gives 404; both close.
- **GET gap:** F2.

## Check 6 detail (`tests/pytest-s3-verbose.txt`)
| Contract tests | Matching test functions |
|---|---|
| 88 | 11 |
| 89 | 49 |
| 90 | 7 |
| 91–96 | 1 each, except 94 = 2 |
| 97 | 4 |
| 98, 99 | 1 each |
| 100 | 5 |
| 101 | 18 |
| 102 | 11 |
| 103 | 42 |

All pass (181 passed in test_s3_*). Gaps: O4.
