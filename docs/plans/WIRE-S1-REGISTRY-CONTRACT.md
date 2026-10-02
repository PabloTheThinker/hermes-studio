# Wire: api.py registry + /mcp contract tests against Slice 1

**Status (S1):** **PINNED; merged.** PR #35 (head `b1b51c1`, `b1b51c117795f56924e12a89fc7bc88fe5dcf3e6`) was merged to main as **`bbb7216`** at 11:34 AM ET. §0 line refs stay at `timeline.py@b1b51c1`.
**S2 status (§1c):** **MERGED.** PR #37 was squash-merged from source `480a220` to main as **`e274051`** at 1:58 PM ET (tree `d924c0e`, the same as `480a220`'s; parent `898f6b9`). §1c line refs stay at `oplog.py@480a220`, which is the same content as main.
**#38 status (§1d):** **MERGED.** PR #38 (crossfade ripple trim) was squash-merged at 3:29 PM ET from head `36f8a87` to main as **`a1922f0`** (single parent `e274051`; tree `286177f`, the same as `36f8a87`'s). §1d line refs stay at `36f8a87`, which is the same content as main.
**#39 status (§1e):** **MERGED.** PR #39 (post-S2 follow-up) was squash-merged at 5:33 PM ET from head **`c8e5604`** to main as **`8d181ed`**. Main has single parent `a1922f0`, and its tree `2f2518d` equals `c8e5604`'s. `c8e5604` is `4bfd71f` plus one CI-only commit (`.github/workflows/ci.yml`), so the §1e line refs at `4bfd71f` still hold on main.
**#40/S2b status (§1f):** **MERGED.** Ada squash-merged PR #40 at 6:16 PM ET from head `c1bbddb` to main as **`c6de84e`** (`c6de84e6355105401f97d28de32bbb9a73b3dba2`). I checked with `gh api`: one parent, `8d181ed`; tree `2eccb5b`, the same as `c1bbddb`'s; PR `merged: true`, `merge_commit_sha` = `c6de84e`. **Current main pin: `c6de84e`.** Issue **#41** (`from_otio` raises a bare `StopIteration` at timeline.py:834) is **not blocking**.
**S3 status:** **PROVISIONAL.** PR #42 (`feat/editor-s3-store-mcp`) has head **`0282e9f`** (`0282e9f86a96c6a7ca7cbbdb687730ce5d585d35`): two commits on `c6de84e` (`d7d9edf`, then `0282e9f` for 0600 files). CI is green. I re-ran the S3 suites + test_oplog at that head in a box venv: 543 pass. Bay is holding the head until Ada rules on his off-spec choices, so the pin may move.
**Date:** 2026-10-01 (ET). **Author:** Wire. Planning only: no code, no PR, no branch.

**Revisions (all times ET):**
- **8:50 AM:** Ada approved and Bay confirmed a top-level `schema_version` and importable `validate()`, `canonical_hash()` and `to_otio()` in `timeline.py`. Glyph's five schema points are approved. I read the five as the room-agreed rules (anchors, fades, implied gaps, no author fields + unique ids + `split_from`, markers); that reading is my assumption, because the list isn't written down here.
- **8:52 AM:** Bay answered four questions:
  - the shape of `validate()` errors: `rule`, `path`, message;
  - track roles, with music as an audio clip on the `music` track;
  - a single `schema_version` field, included in the hash;
  - `unknown_field` rejects unknown fields everywhere.
  These moved out of the open questions.
- **8:53 AM:** Folded in more confirmed Slice 1 facts: integer ticks in flicks with `tick_rate`, order-free lists, and `not_nfc`. Added my seconds-in / ticks+seconds-out tool contract, plus tests for both.
- **8:57 AM:** My decisions as Wire:
  - keep the `_s` suffix on time inputs;
  - use `engine_offline` (as PLAN-MERGED does), not `app_closed`;
  - `export_otio` writes a `.otio` file and returns `{path, timeline_hash}`;
  - writes go only through `timeline_apply` in Phase 1.
  The open questions are now split into "answer in the Slice 1 PR body" and "Slice 2 notes".
- **8:57 AM (cont.):** Bay's answers:
  - a `tick_rate` other than 705600000 fails with rule `bad_tick_rate`;
  - `canonical_hash()` validates first and raises with rule ids, so an invalid doc never hashes;
  - the stored `hash` field and any doc-level revision counter are excluded from the hash.
  My two additions are approved as Wire decisions: `export_otio` is refused with `engine_offline` when the app is closed and writes into `exports/`, and test 41 (now 43) checks its output. The PR-body list is now just rule ids, head SHA, and the exact names of the excluded fields.
- **9:06 AM:** Bay confirmed:
  - the excluded fields are `version` and `hash`, and `validate()` checks that a stored `hash` matches the content;
  - top-level `fps` `[num, den]` is required and included in the hash, and each media entry has its own `fps`;
  - `to_otio()` stays at 705600000/s;
  - there is no `overlay` role in Slice 1.
  I added tests 40 (fps) and 41 (stored hash mismatch), so the later tests moved from 40–55 to 42–57. The PR-body list is now rule ids + head SHA.
- **9:09 AM:** Checked against Bay's PR body (`S1-PR-BODY.md`) and the branch code at `3df0d8e`, read with `gh api`; nothing cloned or changed.
  - Filled in every rule id.
  - Resolved the media-`fps` assumption: the `fps` key is required, and its value may be `null`.
  - Resolved the old A3 (duration counts speed) and three Slice 2 notes (missing fades, marker ids, OTIO details).
  - Fixed tests 24, 37 and 41, which disagreed with the code.
  - Section 0 now lists the facts as checked, with the mismatches flagged (§0.1).
- **9:20 AM:** Re-checked against Bay's new head `5e3e639`, read with `gh api` (nothing cloned or changed), and the updated `S1-PR-BODY.md`. Re-pinned provisionally to `5e3e639`.
  - **Fixed at `5e3e639`:** `validate()` now returns the problem list (and `validate_or_raise()` raises). Paths are RFC 6901 pointers. `canonical_hash()` raises on `hash_mismatch` too. `stamp_hash()` replaces `with_hash`. Problems carry an `id` for items and markers.
  - **Tests:** every path is now in pointer form, and `problems()` is replaced by `validate()`. Test 41 is reverted to expect a raise. New tests 42–45 cover `at_and_anchor`, `anchor_before_zero`, `overlap` and `non_integer_duration`, so the later tests moved from 42–57 to 46–61. Tests 46 and 61 now check that `id` passes through.
- **12:06 PM:** Read PR #37 (S2 oplog) at `ff59093` with `gh api` (read only, nothing pushed or commented): `oplog.py`, `test_oplog.py`, `docs/oplog.md`, and the two notes in `docs/timeline.md`. The new §1c is provisionally pinned there.
  - Ada ruled: `run_id` stays out of the oplog line. Ids are never reused. `inverse_invalid` is only the fallback reason. A stale retry returns the original result. A group undo runs newest first, as one entry. The 7e15 export warning goes with the first slice that touches `to_otio()`.
  - **Edits:**
    - Write tools are now `timeline_apply`, `history_undo` and `history_redo`.
    - `undoes` is `null` or a list of `op_id`s.
    - `run_id` is removed from the tools; it lives in Wire's layer if the ACP bridge needs it.
    - `undo_blocked` has three reasons, `actor`, `dependents` and `inverse_invalid`, all passed through.
    - The 7e15 export warning is added as **PLANNED only**: no field and no test.
  - **Tests:** fixed 53, 54 and 55. Added tests 68–74.
  - **Mismatches at `ff59093`:** listed in §1c.
- **9:02 PM:** 103 (vi-a) RULED by Ada: a GET with a valid length > 0 (even over the cap) gets 400 "request body not allowed" + close; HTTP /mcp gets `-32700` `id:null` + close. Order: TE → valid CL → GET body → cap (POST only). Added the `Content-Length: 2000000` GET case. Still 104 tests and 17/36. Backup: `/workspace/tmp/WIRE-backup-2102.md`.
- **8:58 PM:** Folded in Ada's 8:58 rulings on Prove's pre-gate of #42 (`evidence/prove-s3/0282e9f/PROVE-S3-PRE.md`):
  - **103 (vi), F2:** the D27(d) checks run before routing on every method; three GET rows added.
  - **102 (b2), O1:** the newline-mode line cap.
  - **92, O4:** the path and id are asserted literally.
  - **61(d), F1:** a tampered middle-line `inverse` gets `failed` `seq: 2`, open and closed.
  - **D26 decode:** split the path, then decode each segment.
  - **61, O2:** RULED by Ada at 8:59. A missing `hash` gets `invalid_doc` `hash_mismatch` @ `/hash`, open and closed; only an unreadable or non-JSON file gets `failed` (backup `/workspace/tmp/WIRE-backup-2100.md`).
  - Still 104 tests and 17/36.
  - Backup: `/workspace/tmp/WIRE-backup-2058.md`.
- **8:36 PM:** Added **test 104** (S3+W, Ada approved): GET /mcp gets `resources/updated` for a project opened mid-stream. Before (`0282e9f`), http_engine.py:212 takes a snapshot of the projects at connect.
  - Glyph's decode case is noted under §1i E. There's no numbered D26 route test in the contract.
  - Totals: 104 tests; S3+W is now 12. Rule ids stay 17/36.
  - Backup: `/workspace/tmp/WIRE-backup-2036.md`.
- **8:32 PM:** S3 PR #42 provisionally pinned at `0282e9f`. Checked tests 88–103 against the head's code and tests.
  - **92 fixed (Bay is right):** an NFD `add_marker` label gives the validator's `not_nfc` @ `/markers/<k>/label` with the new marker's `id`, as at `c6de84e` (reproduced: `/markers/1/label`, `id` `mk1`). The contract's `/ops/0/label` was wrong.
  - **94 fixed (Bay is right):** per the S3-SPEC §4 transport table, MCP sessions (HTTP and stdio) carry the token's agent id and `plan=None`, so there's **no step**. Only ACP carries a plan step.
  - **102(a):** added a blank line between frames (Ada 8:32 rejected the blank-line skip).
  - **`get_timeline{summary}`:** deferred to S4. No test requires it.
  - **`edit_text` row:** reworded as an op inside `timeline_apply` (there's no `edit_text` tool).
  - Backup: `/workspace/tmp/WIRE-backup-2032.md`.
- **7:28 PM:** Made 103 (v) firm per Ada's 7:25 Transfer-Encoding ruling.
  - Any TE header, with or without `Content-Length`, is refused **before** the `Content-Length` check, and the body is never read.
  - REST: 400 "unsupported transfer encoding" + close. HTTP /mcp: `-32700` `id:null` + close.
  - Cases: chunked alone; chunked + a bad `Content-Length`; chunked + duplicates.
  - Before: Bay's chunked repro (200, 200; `/mcp` 404).
  - It's a new message string, not a rule id, so counts stay 17/36.
  - Re-diffed against S3-SPEC (backup `/tmp/S3-SPEC.before-te.md`).
  - **Bay's three claims are confirmed:**
    - 102(b) has the 16777217 embedded `id: 9` case.
    - 102(a) merges both malformed lists, plus the same-value duplicate.
    - Spaces and tabs are stripped on both transports (D27(a) `strip(b" \t")`, D27(d)).
  - **OPEN ask for Bay:** §11 row 4 ("parses input differently") doesn't list the Transfer-Encoding change (before: chunked 200 → 200; after: 400 "unsupported transfer encoding" + close). Under Prove's gate, any difference not on §11 is a FAIL, so it needs a line there.
  - **Minor:** the spec's 103 "before" doesn't say that HTTP /mcp is 404 at `c6de84e` (no route).
  - Backup: `/workspace/tmp/WIRE-backup-1928.md`.
- **7:24 PM:** Added a same-value duplicate case to 102(a) (Prove: `Content-Length: 5` twice + an embedded frame → close, never runs). Added 103 (v), `Transfer-Encoding` → "invalid content length" + close, **PENDING Ada**, with Bay's chunked repro (200, 200) as the "before".
  - **Diff vs S3-SPEC (7:21 revision):** D27, tests 101–103 and §11 agree on every rule. The differences are only in case lists:
    - Stdio duplicates: spec 101, contract 102(a). Allowed.
    - 102(b) uses different over-cap values: spec 2097152; contract 16777217 + 1048577.
    - Answer-first wording: spec says "before any body byte"; contract says "before the body finishes".
    - Malformed lists: spec adds empty + stray `\r`/`\v`; contract adds whitespace-only and `٣` on stdio.
    - The spec has no Transfer-Encoding case yet (pending Ada).
  - Stale §1i items 1/4/5 (§11 rows, D27 text) closed by the revision.
  - Backup: `/workspace/tmp/WIRE-backup-1924.md`.
- **7:20 PM:** **Folded in Ada's 7:15–7:20 rulings.**
  - **Yes to all five:**
    - stdio stays in `Content-Length` mode once it's used (102(c));
    - batch order is per op;
    - the `failed` row (existing code; closed-app reads get it for a corrupt log line; HTTP 500);
    - D19 paging (1–200 / 1–500, `history_diff_truncated` at the top level);
    - D8 `project_status` approved and on the C9 allowlist (test 60).
  - **HTTP header check = the stdio check:** `re.fullmatch(rb"[0-9]+")` + the 8-digit cutoff. A failure gets 400 `{"ok": false, "error": "invalid content length"}` + `Connection: close`. That's a new message string, not a rule id (17/36 unchanged). A well-formed over-cap length keeps "request body too large".
  - **Duplicate `Content-Length` headers** (Ada): two or more, even with equal values, are malformed. stdio: `-32700` `id:null` + nonzero exit (test 102 (a), with a same-value `5`/`5` case per Prove 7:24). HTTP: 400 "invalid content length" + close (test 103).
  - **Finding 8 (known gap):** a middle log line with an edited stored hash is caught only by a full replay. Tested with the app open (61(d)).
  - **7:21:** used Bay's corrected "before" for `٣` (read as Latin-1, `int()` raises → length 0) and kept a missing `Content-Length` as an unchanged case (test 103).
  - **Checked at `c6de84e`:**
    - studio.py:149 `int(headers.get("Content-Length") or 0)` accepts `+5` (5), `1_000` (1000), `-1` (→ "too large") and 9 digits (→ "too large").
    - `abc` and `٣` raise and become **0**.
    - `.get()` returns only the **first** of duplicate headers (`get_all` gives both).
  - Backup: `/workspace/tmp/WIRE-backup-1920.md`.
- **7:15 PM:** Fixed stale "pending" text so it cites the 6:56 PM rulings:
  - the `conflict` row (§11 allowed diffs C and D);
  - §1h (j) step 2 (D29 approved);
  - §1i H3 and H4 (envelope reuse ruled; test 100 firm);
  - §1i I items 2–3 (now spec-text updates for Bay).

  Items still pending Ada are unchanged. Backup: `/workspace/tmp/WIRE-backup-1915.md`.
- **7:14 PM:** **Ada approved** a malformed `Content-Length` → the same broken-stream close as over-cap (`-32700` `id:null`, log line, nonzero exit); no stdio skip-ahead; the too-short known limit stands. Pending markers removed from 101 (7) and 102 (a). The answer-first ordering was already ruled at 7:09. §1i J item 3 is updated. Backup: `/workspace/tmp/WIRE-backup-1914.md`.
- **7:09 PM:** **Ada's 7:09 ruling on oversized lengths and HTTP refusals.**
  - **Stdio:** a well-formed `Content-Length` ≤ **16 × `MAX_BODY` = 16777216** is answered with `-32700` first, then drained. Above that, or a digit run longer than 8 (no `int()` call), the stream is broken: `-32700` `id:null`, logged, then the session closes with a nonzero exit. No skip-ahead.
  - **HTTP:** closes the connection on every refusal (over-cap, negative, non-integer length). Status and body are unchanged: REST 400 `{"ok": false, "error": "request body too large"}`, HTTP /mcp `-32700`.
  - **Pending Ada (Prove/Bay):** a malformed header also gets the broken-stream close; stdio never resyncs by scanning; once a stream has used `Content-Length`, it stays in that mode.
  - Tests 101/102 rewritten; **test 103 added** (HTTP keep-alive close-on-refusal, with the `c6de84e` `/api/doctor` repro as the "before").
  - **102(c) verdict:** a too-short length whose leftover bytes form a valid frame is **byte-identical to two real frames** (checked against mcp.py at `c6de84e`), so "never runs" can't be asserted for it. 102(c) now asserts the close only for leftover bytes that don't form a valid header.
  - Total: 103. Backup: `/workspace/tmp/WIRE-backup-1909.md`.
- **7:04 PM:** **Ada (7:03 PM): the `Content-Length` cap is 1048576 bytes, inclusive**, one shared constant: the existing **`MAX_BODY`** (studio.py:38, `1024 * 1024`), used by stdio /mcp, HTTP /mcp and the REST routes.
  - Tests 101/102 are pinned and firm on the numbers, but wait on Bay's next S3-SPEC revision (on hold while Bay asks Pablo something).
  - **Bay's 7:05 D27 direction:** an oversized but well-formed length gets `-32700` *immediately*, and then stdio drains N bytes in small chunks, keeping none and scanning none. The "`-32700` before the body is sent" ordering is **PENDING Ada**.
  - **Checked at `c6de84e`:**
    - `_read_json` (studio.py:147–158) answers an oversized (or negative) length with **400 `{"ok": false, "error": "request body too large"}`**, body unread; 1048576 is accepted.
    - **But the connection stays open (HTTP/1.1, studio.py:236), so the unread body is parsed as the next request:** a `GET /api/doctor` embedded in an oversized body **ran and got 200**.
  - Problems are listed in §1i J.
  - Total unchanged at 102. Backup: `/workspace/tmp/WIRE-backup-1904.md`.
- **6:56 PM:** **Ada ruled on three points.**
  1. **§11 has 12 allowed diffs** (the original 4 + A–H). Row 4 now reads "parses input differently".
  2. **D29 approved.** Test 97 is firm.
  3. **Envelope reuse ruled, not an exemption.** /mcp runs the engine check at L1115–1119 before its op stage. Test 100 is firm. D31's "beats outer stages" now covers only dedupe and `conflict`.
  - **C5:** test 93 gates the after-reload case explicitly.
  - **Prove's D27 additions (a) and (b), accepted by Bay:** tests **101** and **102** added (S3+W). No existing test covered D27; Prove's probe `.out` is checked against mcp.py:293.
  - **S3-SPEC on disk is unchanged since 18:52.** The items that depend on Bay's next revision are listed in §1i I.
  - Total: 102. Backup: `/workspace/tmp/WIRE-backup-1856.md`.
- **6:53 PM:** **Reviewed the S3-SPEC revision** (31 decisions: 26 open, 5 ruled; checked against `c6de84e`; still no branch, **not pinned**).
  - **D28 resolves my blocker in principle**, with 3 asks about the torn tail and the closed-app fast path.
  - **Asks 1–7 answered:** D15, D17, D19, D22, D25, D26, D4.
  - **D29 matches test 97**, which is now firm.
  - **D30 matches test 98.** **D31 matches test 99**, which gains a cached-key subcase. D31's prose still says the /mcp op stage beats outer `unknown_arg`/shape, which contradicts D21 step 3b.
  - **Test 100 added** (envelope order, PENDING Ada).
  - **Tests 58/61/62 re-targeted per D28** (61(c), 61(d) added).
  - **`failed` row added** to the error table (D28/D25).
  - **§11:** the 4 allowed diffs match Ada; A–H cover everything I flagged.
  - Details in **§1i H**. Total: 100. Backup: `/workspace/tmp/WIRE-backup-1853.md`.
- **6:48 PM:** **Ada (18:47 ET) ruled on the 3 differences.**
  1. **Anchor keys: FIXED, not exempted.** The shared helper also checks `anchor`'s keys by name. It's an S3 engine behaviour change, the only one Prove allows. Test **97**; the exact rule and path are PENDING S3-SPEC.
  2. **`trim_clip{dur_s:"x"}` on a clip: named exemption.** Test **98**.
  3. **Batch order: named exemption.** /mcp-stage errors for the whole batch come before the engine. Test **99**.
  - Prove's new byte-identical gate is in §3.
  - **Inconsistencies flagged:**
    - The gate's "only exception" conflicts with other approved or pending S3 engine changes (C5 replay warnings, D10 `hash` in conflict records, D19 cap, history arg checks, D4).
    - The envelope checks vs the /mcp stage.
    - The anchor fix also changes plain HTTP answers.
  - Total: 99. Backup: `/workspace/tmp/WIRE-backup-1848.md`.
- **6:41 PM:** **Ada (18:40 ET) approved D21 and D23.**
  - **D21 (check view):** when an `_s` value fails to convert, /mcp first runs the engine's own op arg check on a check view, and passes back `unknown_arg`/`missing_arg` unchanged. Only then come the both-sent check and the conversions. The old D21 caveat is gone.
  - **D23:** raw tick args pass through, and both sent gives `bad_arg` @ `/ops/k/<arg>_s` after the check pass. It's logged as a named /mcp-only exemption in §1h.
  - **Rule reworded:** "/mcp accepts time in seconds through `_s` args, and raw tick args pass through to the engine."
  - **Test 50:** `history_list` is raw ticks (the same exemption as `get_timeline`).
  - **Tests 95/96 added** (S2+S3+W).
  - **§1i items 5 and 10 settled.**
  - **Checked in Python at `c6de84e`**, simulating the check view against the engine. All 7 orderings give the ruled answers, and the placeholder int never trips the check, because it reads key names only.
  - **Caveats in §1h (j):**
    1. The engine's `Oplog._check_args` (L857) is the **tool-level** check and can't take an op view. The op check is inline in `_apply_one` (L768–771), so "reused, not copied" needs a small engine extraction.
    2. Nested `anchor` keys aren't covered.
    3. `trim_clip{dur_s}` on a clip gives the conversion error before the engine's `bad_arg` @ `/ops/k/id`.
    4. Across a batch, a later op's conversion error is reported before an earlier op's engine-stage error.
  - Backup: `/workspace/tmp/WIRE-backup-1841.md`.
- **6:33 PM:** **Reviewed Bay's S3-SPEC** (`/workspace/desk/hermes-studio/S3-SPEC.md`, 26 decisions, against main `c6de84e`; no branch, so **not pinned**). Bay's 6:34 PM update is included: gaps 4/8 are in §5 rows 4/8 + D10/D19/D20; D26 uses the ASCII regex.
  - Every claim was checked in Python against the `c6de84e` tree (= `c1bbddb`): `mcp.py`, `oplog.py`, `studio.py`, and the `evidence/s3-spec/c5_retry_probe.*` output.
  - Verdicts and asks are in **§1i**. Settled items are cross-referenced in §1a, the error table, the gaps list, test 93 and §3.
  - Test count unchanged (94). Backup: `/workspace/tmp/WIRE-backup-1833.md`.
- **6:24 PM:** **C5 SETTLED (Ada 6:23 PM ET / 18:23).** A forged `step`/`actor` is stripped, gets an `ignored_field` warning and never takes effect; there is no hard-reject rule. Prove reworded the gate (§3). Test 70 is updated to (a) and (b), and tests **93** (the retry edge case, engine) and **94** (C5 on HTTP/ACP/MCP) are added. Total: 94.
  - **Engine at `c6de84e`** (tree = `c1bbddb`; oplog.py lines):
    - Forged fields are stripped in `call` (L848, via `_strip_forged` L1318–1340, `FORGED_FIELDS` L37) **before** dedupe (`_replayed` L933, called at L1120/L1141; `_same_call` L953), so the `client_op_id` fingerprint never includes them.
    - **Live**, an exact retry with the same forged field returns the cached result with the same warning, never a mismatch.
    - **But the cached result replays the *original* call's warnings** (stored at L1109–1110 via `_result` L1313; returned at L951): a retry that **adds** a forged field gets the cached result with **no** warning, and a retry that **removes** it still gets the original's warnings.
    - **After `Oplog.load`, the cache is rebuilt with `warnings: []`** (L1241), so an exact retry with the forged field **loses the warning**.
    - None of these cases is ever `client_op_id_mismatch`.
    - **Prove's edge case is met live but NOT after reload.** The add/remove cases also break (b). This is flagged for Bay (§3).
  - Backup: `/workspace/tmp/WIRE-backup-1824.md`.
- **6:19 PM:** **#40 MERGED** (6:16 PM ET, head `c1bbddb` → main **`c6de84e`**).
  - Checked with `gh api`: one parent, `8d181ed`; tree `2eccb5b` = `c1bbddb`'s (matches Prove); `merged_at` 22:16:31Z = 6:16 PM ET. **Pin moved to main `c6de84e`.**
  - **§1h APPROVED** (Ada 18:16; Bay and Glyph agreed): /mcp rewrites only a tick rule that lands on the converted field, and every other error comes back verbatim.
  - **Issue #41** (the OTIO import `StopIteration` at timeline.py:834, line confirmed in the tarball) is recorded as **not blocking**. It's grouped with the 7e15-tick OTIO warning.
  - **S3:** branches off `c6de84e`, spec-first; no code until Wire, Glyph and Ada confirm. Prove's S3 gates are listed in §3.
  - **Tests added:** **91** (exact /mcp retry with a float `_s`) and **92** (exact /mcp retry with NFD text), both S2+S3+W, checked in the engine at `c1bbddb`. Total: 92.
  - **Wording mismatch:** Prove's C5 gate says forged `actor`/`step` are "rejected". At `c6de84e` the engine **strips them and warns** (`ignored_field`, oplog.py `_strip_forged`) and still applies the write (test 70).
  - Backup: `/workspace/tmp/WIRE-backup-1819.md`.
- **6:11 PM:** **Ada (18:11 ET) ruled. `invalid_args` is removed** from every row, test and the error table.
  - **Exemption:** fields only /mcp sees (`_s` args and the `schema_version` guard) don't have to match an engine answer, but their errors must use **engine rule ids and JSON Pointer paths**.
  - **`group_id: null`** now passes through to the engine, which gives `bad_arg` @ `/group_id`.
  - **`_s` conversion (Bay's corrected wiring):** a `TypeError`/`ValueError` from the helper becomes `bad_arg` @ `/ops/k/<arg>_s`. Otherwise the engine's tick-rule answer comes back with only the path rewritten to the `_s` arg.
  - **`schema_version` guard:** `bad_schema` @ `/schema_version`.
  - **Rewrote:** Tool input conversion, the envelope, the error table, §1g, tests 57, 65, 66 and 67, and test 69's /mcp side. Added test **90** (Prove's S3 inputs). Total: 90.
  - **Verified at `c1bbddb`** (§1h). Two points need Bay/Ada:
    - When the engine's answer isn't at the converted field (e.g. `out_of_range` @ the item, or `too_large` @ `…/at` from a `src_in` trim), the contract keeps the engine path verbatim.
    - `trim_clip{dur}` on a clip is `bad_arg` @ `/ops/k/id` (dur is only for text/transitions).
  - Backup: `/workspace/tmp/WIRE-backup-1811.md`.
- **6:04 PM:** **Ada (18:04 ET) ruled, and Prove added a point.**
  - **New §1g, a general /mcp pre-check rule for every tool:** /mcp checks a field before the engine only when that check gives the engine's own answer: the same rule id, path, `id` field and position in the engine's check order. Everything else goes to the engine as received. I flagged the rows that break the rule in §1g.
  - **`edit_text`:** /mcp pre-checks only `id`, in the engine's order (`unknown_arg`, then `missing_arg` @ `/ops/k/id`, then `bad_arg` @ `/ops/k/id`). `text`/`style` go to the engine unchecked, which **supersedes the 6:01 PM `invalid_args`/`cause` shape**. Test 88 is rewritten, test 87's `text: 5` and `_s` cases are fixed, and test **89** is added (S3+W).
  - **Engine answers checked at `c1bbddb`:** `{id: 5}` gives **`bad_arg` @ `/ops/0/id`, no `id`**; `{id: 5, bogus: 1}` gives `unknown_arg` @ `/ops/0/bogus`; `{id: "zz", text: 5}` gives `not_found` with `id` `zz`; `{id: x1, text: 5}` / `{id: x1, style: 5}` give `wrong_type` @ `/ops/0/text` / `/ops/0/style` with `id` `x1`.
  - Total: 89. Backup: `/workspace/tmp/WIRE-backup-1804.md`.
- **6:01 PM:** *(superseded at 6:04 PM)* **Ada (18:01 ET) and Prove ruled on /mcp schema typing for `edit_text`.** When the /mcp schema rejects a non-string with `invalid_args`, the error carries the **engine-equivalent `path`** and names the **engine rule as `cause`**, so /mcp and HTTP agents can handle it the same way. A non-string `id` gives `/ops/k/id` with `cause` `bad_arg`. A non-string `text` or `style` gives `/ops/k/text` or `/ops/k/style` with `cause` `wrong_type` (Prove's correction: the validator's rule, per spec). I checked this against `c1bbddb`, and the engine gives exactly these rules and paths for int, float, bool, null, list and object values. The rule is recorded in the §1b row, §1f and the `invalid_args` row. Added test **88** (S2b+S3+W, checked at S3 with C5). Total: 88. Backup: `/workspace/tmp/WIRE-backup-1802.md`.
- **5:58 PM:** **S2b PR #40 provisionally pinned at `c1bbddb`** (off `8d181ed`). I read `op_edit_text`, `docs/oplog.md` and the PR body (13 Ada decisions) at `c1bbddb` and reproduced every claim in Python from the tarball. Code, docs and PR body agree; there are no mismatches. Added the `edit_text` §1b row, the §1f section, the `undo_blocked` `op_ids` per-reason wording from the doc note, and tests **81–87** (6 at S2b, 1 at S2b+S3+W). Total: 87. Rules stay 17/36. Backup: `/workspace/tmp/WIRE-backup-1757.md`.
- **5:35 PM:** **#39 MERGED** (head `c8e5604` → main `8d181ed`). I confirmed with `gh api` that `8d181ed`'s parent is `a1922f0` and its tree `2f2518d` equals `c8e5604`'s.
  - **The compare `4bfd71f...c8e5604` is one commit,** `c8e5604`. It's CI only: `set -euo pipefail` and a hard failure if apt didn't install ffmpeg.
  - **Test 69's `group_id: null` case is now satisfied on main.** Test 76's canonical cases and test 80 now run on main. The count is unchanged.
  - **Ada's CI ruling:** recorded in §1e (it isn't met by the merged CI yet).
  - **Next:** S2b, off `8d181ed` (§3).
- **4:01 PM:** Added a provisional #39 pin at `4bfd71f` (read only with `gh api` and the source tarball at that head).
  - **Every #39 behaviour this contract relies on matches the code and docs** (§1e).
  - **Follow-up items now satisfied by #39, pending merge:**
    - `group_id: null` gives `bad_arg` (test 69's null case);
    - `key=repr` (the op-level arg-name crash is now `unknown_arg`);
    - canonical-JSON same-call;
    - Ada's two #38 doc rulings.
  - **Tests:** 76 extended (canonical same-call), 80 added (`unknown_media` at the op path).
- **3:31 PM:** **#38 MERGED.** Its pin moved from provisional `36f8a87` to main **`a1922f0`**. I confirmed with `gh api` that main is `a1922f0`, its parent is `e274051`, and its tree `286177f` equals `36f8a87`'s. Test 79 is now pinned to main `a1922f0`.
  - **Ada's doc rulings:** two items, recorded in §1d. Both ship docs-only in Bay's follow-up PR off `a1922f0`.
  - **Follow-up PR order:** recorded in §3.
  - **Test 69's null-`group_id` case:** still waits on the follow-up PR.
- **2:46 PM:** Added a provisional #38 pin at `36f8a87` (read only with `gh api`; checked in Python from the tarball). S2 stays MERGED.
  - **All five of Bay's #38 claims match the code** (§1d).
  - **New `invalid_op` rule `transition_too_long`:** added to the error table and §1d.
  - **Ada's rulings:**
    - 2:17 PM: #38 decisions 1, 2, 4, 5 and 6 confirmed, and the outgoing crossfade wins the tie-break.
    - 2:47 PM, RULED: `transition_too_long` is the 17th op-level rule, the S1 validator stays at 36, and when neither crossfade fits on its own the error points at the outgoing one.
  - **Tests:** added test 79, which needs #38.
- **1:59 PM:** S2 pin changed from provisional to **MERGED** (source `480a220`, main `e274051`). I confirmed the tree match and the parent with `gh api`.
  - **Ada (1:59 PM):** `timeline_apply` with `group_id: null` will give `bad_arg`, the same as undo and redo. To mean "no group", leave the field out. This is **PLANNED** for Bay's post-S2 follow-up PR and isn't on main yet. The /mcp schema and envelope now say `group_id` is an optional non-null string that my layer never sends as `null`.
  - **Order (Ada):** the crossfade ripple-trim PR, then the follow-up PR (including `key=repr` at `oplog.py:700`), then S2b, then S3. S3 doesn't open until `key=repr` is on main.
  - **Tests:** test 69 is extended with the null-`group_id` case, which needs the follow-up PR. The count is unchanged.
- **1:47 PM:** Re-pinned S2 from `2f80bbd` to **`480a220`**. Read with `gh api` and checked in Python from the tarball.
  - **The compare `2f80bbd...480a220` is exactly 2 commits** (`0b459c4`, `480a220`), ahead by 2 and behind by 0. They touch 3 files (`oplog.py`, `test_oplog.py`, `docs/oplog.md`). The PR as a whole still touches only the same 4 files against main.
  - **Folded in:**
    - shape checks before dedupe;
    - the 1–500 ops cap;
    - the rule for exactly one non-null string target (R3/R4);
    - the R2 tool compare;
    - `split_clip` `duplicate_id` @ `/ops/k/ids/i`.
  - **Ada (1:48 PM): the post-load undo-of-undo case is RULED permanent** (by design).
  - **Both §1c open items are closed.** One new minor item: op-level non-string arg names still crash (Python callers only).
  - **Tests:** updated 75 and 76; added 78.
- **1:15 PM:** Re-pinned S2 from `c2a930f` to **`2f80bbd`**. Read with `gh api` and reproduced from the source tarballs.
  - **`2f80bbd` is formatting only:** the ASTs of `oplog.py` and `test_oplog.py` are identical to `aa6f6ce`.
  - **Folded in from `aa6f6ce`:**
    - `id_reused`, `client_op_id_mismatch`, F2 (a non-string id gives `bad_arg` at its own path, before any lookup) and F1 (ids handed out in a batch are retired, including after load and replay).
    - The earlier note that "`not_found` has no `id` when the id isn't a string" is now moot.
    - The /mcp retry rule: resend the exact args with the same `client_op_id`.
  - **Tests:** added 75–77.
  - **New finding:** one crash, in §1c.
- **12:42 PM:** Re-pinned S2 from `ff59093` to **`c2a930f`** (read only with `gh api`, plus the source tarball to reproduce in Python).
  - **All six §1c mismatches are fixed and verified.** Items 1–5 were reproduced in Python; item 6 was checked by reading.
  - **Bay's other changes:**
    - `remove_track` not_found now has path `/ops/k/id`.
    - All three `undo_blocked` reasons share one shape: `reason`, `op_ids`, `path`, `id`.
    - `op_ids` now has a meaning per reason (Glyph).
  - **Tests:** updated 53, 54 and 72–74. Tests 72–74 now pass at `c2a930f`. The blanket `id` check is now scoped to doc problems.
- **10:47 AM:** PR #35 opened at `fbbb2c0`, unchanged from the freeze, so the 9:30 check stands with no new reading. Pinned for good.
- **9:30 AM:** Re-checked against the frozen head `fbbb2c0` and the updated `S1-PR-BODY.md`. Re-pinned provisionally to `fbbb2c0`.
  - **The code changed after `5e3e639`, not just the tests:**
    - `9698aaa` (9:25 AM ET) changed `timeline.py` (+35 −1) and `docs/timeline.md`.
    - `fbbb2c0` (9:29 AM ET) changed tests only.
    - The PR body (L5) lists both correctly.
  - **The code matches the agreed `id` rules** (§0.1, item 9). The `id` rules are now in §0, line refs are shifted +34, and the open "raw ids" question is closed.
  - **Tests:** 5, 18, 19, 46, 52 and 61 adjusted. New test 62 checks duplicate ids at the MCP boundary. A blanket `id` check now applies to every test.
- **11:22 AM:** Re-pinned from `fbbb2c0` to PR #35 head **`b1b51c1`**. Read the compare `fbbb2c0...b1b51c1` with `gh api`; nothing cloned.
  - **Bay's four timeline commits, verified (§0.1 item 10):** `8231d21` (non-string roles and keys, lone surrogates), `10a310d` (`seconds_to_ticks_nearest`), `d702466` (the 2⁵³ cap as `out_of_range`) and `86211b5` (a missing `id`/`type` is `missing_field`).
  - **The merge `b1b51c1` brings in `1d14e01` (#34):** only `pipeline.py` and `tests/test_job_manifest.py`, with no timeline changes.
  - Still 36 rule ids. §0 line refs are moved to `b1b51c1`.
  - **New: "Tool input conversion" (§1).** `_s` inputs go through `seconds_to_ticks_nearest` and errors map to `invalid_args` *(superseded 6:11 PM: `bad_arg`, §1h)*. That replaces the earlier `seconds_to_ticks` wording.
  - **Tests:** extended 3, 15, 22, 26, 29, 30, 31 and 40 with the new rules. Added tests 63–67 for tool input conversion. No existing row expected `wrong_type` for a missing `id`/`type`, so no expected rule had to flip.


**What I checked in the repo (read-only `gh api`):**
- `main` is at `1d14e01` (#34, atomic `job.json` write), and it's merged into the PR head.
- PR #35 (`feat/editor-s1-timeline`, open) is at **`b1b51c1`**. I read `hermes_studio/timeline.py`, `docs/timeline.md` and `tests/test_timeline.py` there, plus the compares `5e3e639...fbbb2c0` and `fbbb2c0...b1b51c1`. I didn't run the test suite.
- Today the tool list is the `TOOLS` list in `hermes_studio/mcp.py` (18 entries). `api.py` has `HermesStudioError` with `code`/`hint` and no registry. The registry described here is new work in my PR, which goes on top of Slice 3 (PLAN-MERGED §5).

## 0. Slice 1 facts this contract relies on

**Checked against `S1-PR-BODY.md` (9:29 AM ET version) and `timeline.py` at `b1b51c1`.** Line refs are `timeline.py@b1b51c1`.

**Document**
- **Top-level fields:** `schema_version` (`"hs.timeline/1"`), `id`, `version`, optional `hash`, `tick_rate`, `fps`, `size` `[w,h]`, `media`, `tracks`, `markers`. Every object is strict.
- **Version field:** `schema_version` is the only schema field, and it **is** in the hash. Any other value, or the old field `schema`, fails as `bad_schema` (L334).
- **Tick rate:** `tick_rate` must be exactly the int 705600000. A missing value, another number, or `705600000.0` fails as `bad_tick_rate` (L337).
- **Frame rate:** required top-level `fps` as a reduced `[num, den]`. Its frames must be whole ticks (`bad_fps`, L351), and it is in the hash.
- **Media `fps`:**
  - Each media entry is `{path, dur, fps, proxy?}`.
  - The `fps` **key is required**; its value is a reduced rational, or `null` for audio-only media (L376).
  - A media `fps` that isn't whole ticks is not rejected.
- **Times are integer ticks:** `at`, `dur`, `src` in/out, `anchor.offset`, `fade_in`, `fade_out`, marker `at` and media `dur`. A float or bool fails as `not_integer_ticks`.
- **The 2⁵³ cap** (`d702466`):
  - A raw tick field above 2⁵³ fails as `too_large` (L243).
  - **Derived values** above 2⁵³ fail as **`out_of_range`**. That covers an item's end, `at` + duration (L527–528), an anchored item's resolved end (L560–561), a clip's duration after speed (L523–524), each part of any `[num, den]` pair including `fps`/media `fps`/speed/volume/crop (L284–285), and `version` (L345–346).
  - **Exactly 2⁵³ is valid**, since every check is `> MAX_TICKS`.
- **Other fractions:** fps, speed, volume and crop are reduced `[num, den]` pairs (`bad_rational`, `out_of_range`). The doc holds no floats.

**Tracks**
- **Roles:** each track has a required `role` in {`text`, `main`, `voice`, `music`}. There is no `overlay` role. Any other value fails as `bad_track_role`, including a non-string such as `[]`, `{}`, `["main"]`, `1`, `null` or `true` (L392, `8231d21`).
- **"Exactly one main" has no rule of its own** (PR body L43, code L399–402, L431):
  - No V1 → `missing_main_track` at `/tracks`.
  - A `main` track with another id, or V1 with another role → `bad_track_id` at `/tracks/<k>/id`.
  - A second V1 → `duplicate_id` at `/tracks/<k>`.
- **Track ids and order:**
  - Ids are `T<n>`, `V1`, `A<n>`.
  - Order is fixed by role (text, main, voice, music); text tracks go highest number first and audio lowest first (`track_order`).
  - Track order is in the hash.
- **What each track holds:** text tracks hold text items; the others hold clips and transitions (`item_not_allowed_on_track`). Music is a clip on a `music` track.

**Anchors**
- **Who can be anchored:** text items and clips on `music` tracks take `anchor {to, offset}` **instead of** `at`.
- **Exactly one of `at` or `anchor`** (`at_and_anchor`, L477–478).
- **Offset:** it may be negative, but the resolved start must be ≥ 0 (`anchor_before_zero`, L559).
- **Other rule ids:** `anchor_target_missing`, `anchor_target_not_main` (the target must be a clip on V1) and `anchor_not_allowed`.

**Fades:** every clip and text item has `fade_in`/`fade_out` (required, ticks, ≥ 0), with sum ≤ the item's duration (`fade_too_long`). A clip's duration is `(out − in) / speed` and must be whole ticks (`non_integer_duration`, L522).

**Gaps, overlaps, ids, authorship, markers**
- **Gaps:** implied by `at`. There is no gap object (`type:"gap"` → `wrong_type`).
- **Missing item `id` or `type`** fails as **`missing_field`** at `<item>/id` or `<item>/type` (L416–418, L425; `86211b5`; it used to be `wrong_type`). A present but unknown `type` is still `wrong_type`.
- **Overlaps:** overlaps on `main`/`voice` tracks fail as `overlap`, reported on the later item (L603). The one exception is an xfade whose `dur` equals the overlap exactly (`transition_overlap_mismatch`, `bad_transition`). Text and music items may overlap.
- **Ids:** unique across the whole doc: media, tracks, items and markers (`duplicate_id` on the 2nd and later copies; format `bad_id`). The id pattern is `[A-Za-z0-9][A-Za-z0-9_.-]{0,63}`, so a valid id never contains `/` or `~`.
- **`split_from`:** optional (`bad_split_from` if it names the item itself).
- **Author fields:** `actor`, `author`, `created_by`, `modified_by`, `user` and `owner` fail as **`attribution_field`** on any object, since every object goes through the same strict-keys check (L228). Authorship comes from the op log.
- **Markers:** `{id, at, label}`. The label may be empty.
- **Strings and keys** (`8231d21`):
  - A string value with a lone surrogate (JSON `"\ud800"`) fails as `wrong_type` (L260–264); it's checked before NFC.
  - In a strict object, a non-string key fails as `unknown_field`. Keys are sorted with `repr`, so mixed key types never raise (L227).
  - **A non-string key in the `media` map** goes through the id check instead, so it fails as **`wrong_type`** at `/media/<key>`, not `unknown_field` (L370).
- **No exceptions from bad input:** `validate()` always returns a list. `canonical_hash()`, `canonical_json()`, `stamp_hash()` and `to_otio()` raise only `TimelineError`.

**Validation API**
- **`validate(doc)`** returns `[{rule, path, message, id?}]`, empty when the doc is valid. It includes the stored-hash check (`hash_mismatch`) (L606).
- **`validate_or_raise(doc)`** returns the doc or raises `TimelineError` (L613).
- **`TimelineError`:**
  - It's a `HermesStudioError` with code `bad_input`.
  - It has `.rule`, `.path` and `.id` (from the first problem), `.rules` (sorted) and `.problems` (== `validate(doc)`).
  - `as_dict()` adds `rule`, `path`, `id` (if present) and `problems` (L94–115).
- **`path`** is an **RFC 6901 JSON Pointer** (`""` = the whole doc), with `~`→`~0` and `/`→`~1` (L118).
  - A missing field's pointer names the field that should be there.
  - Media keys `m/1` and `m~1` fail as `bad_id` at `/media/m~11` and `/media/m~01`.
- **`id` is present only when it names exactly one valid item or marker** (L293–327, `_problems` → `names_one`): the problem is in a track item or marker (or inside one), and that item's id is well-formed (`ID_RE`, NFC) and **used once in the whole doc** (media keys, track ids, item ids and marker ids all count, via `_all_ids`).
  - **`bad_id` and `duplicate_id` never carry `id`.** They rely on `path`, and their messages quote the raw id with `repr` (L274, L360).
  - **`duplicate_id` paths:** a `duplicate_id` goes on the **second and every later copy**, in validator traversal order (media → tracks → items → markers), so three copies give two errors. The message names the first copy's pointer.
  - **Malformed or duplicated ids:** any other problem on an item whose own id is malformed or duplicated also leaves `id` off.
  - **Media, track and doc-level problems** never carry `id` (L217, L411, L441).
  - **Relation errors** carry the anchored item's id (anchor rules), the transition's id, or the later item's id (overlap), each subject to the same "names exactly one" rule.
  - **Path invariant:** whenever `id` is present, `path` equals that item's pointer or starts with it plus `/`, segment by segment. Every pointer is built from whole segments with `_j(item_pointer, …)`, and Bay's blanket helper in `tests/test_timeline.py` (L105–117) asserts it on every test.
- **Staging:** a `bad_schema`, `bad_tick_rate` or missing top-level field stops the validator. Relation checks run only when the structure is clean, and `hash_mismatch` is checked last. **So each rejection fixture carries one fault.**
- **Rule ids (36, unchanged at `b1b51c1`):** `not_object`, `bad_schema`, `bad_tick_rate`, `missing_field`, `unknown_field`, `attribution_field`, `wrong_type`, `not_integer_ticks`, `negative_time`, `too_large`, `bad_rational`, `out_of_range`, `not_nfc`, `bad_id`, `duplicate_id`, `bad_track_id`, `bad_track_role`, `missing_main_track`, `track_order`, `item_not_allowed_on_track`, `unknown_media`, `src_out_of_media`, `empty_range`, `non_integer_duration`, `fade_too_long`, `at_and_anchor`, `anchor_not_allowed`, `anchor_target_missing`, `anchor_target_not_main`, `anchor_before_zero`, `overlap`, `bad_transition`, `transition_overlap_mismatch`, `bad_split_from`, `bad_fps`, `hash_mismatch` (L69–77).

**Hashing**
- **Format:** `canonical_hash(doc)` = `"sha256:" + sha256(canonical_json)`.
- **What `canonical_json` is:** `normalize(doc)` minus `version` and `hash`, dumped with sorted keys, separators `(",", ":")`, `ensure_ascii=False`, as UTF-8.
- **Ordering:** `normalize()` sorts each track's items by **resolved start, then id** (anchored items at their resolved start, a transition at the start of its overlap), and markers by `(at, id)` (L656–657). It fills clip `props` defaults. Track order is not normalized.
- **Excluded fields:** `version` and `hash` are not hashed.
- **`canonical_hash()` / `canonical_json()` raise `TimelineError` on any invalid doc, `hash_mismatch` included** (L670–683).
- **`stamp_hash(doc)`** returns `(copy with the correct hash, hash)`. It validates everything except the stored-hash check, and it's the only way to hash a doc for writing (L684). `with_hash` is gone.

**Helpers and OTIO**
- **`seconds_to_ticks` (strict, L138):**
  - An int, `Fraction`, `Decimal` or `str` must land exactly on a tick, or it raises `ValueError`.
  - **A float still rounds half to even and doesn't raise.** That's unchanged, so "strict raises between ticks" applies to the exact types only.
  - **Never used at `/mcp`.**
- **`seconds_to_ticks_nearest(x)` (new, L160–170, `10a310d`):**
  - It takes int, `Fraction`, `Decimal` or float (a float at its exact binary value).
  - It rounds to the nearest tick, with exact halves going to even, and passes negative values through.
  - It returns `(ticks, Fraction(ticks, 705600000))`.
  - It raises `TypeError` for a bool, any `str` (even `"1"`) or any other type, and `ValueError` for NaN or ±inf (float or `Decimal`).
- **`ticks_to_seconds`:** returns a `Fraction`.
- **Frame helpers:** `ticks_per_frame`, `frames_to_ticks` and `ticks_to_frames`.
- **`to_otio(doc)`:** calls `validate_or_raise` first (L723) and returns an OTIO `Timeline` with `RationalTime(ticks, 705600000)`.
- **`write_otio(doc, path)`:** writes the file.
- **Mapping:** markers become stack markers; fades, props, anchors, `split_from`, ids and the media table go in `metadata["hermes_studio"]`. The round trip `from_otio(to_otio(doc)) == normalize(doc)` holds.
- **otiotool:** `otiotool --stats` and `--list-markers` fail at this rate (known). Contract tests don't use them.

### 0.1 Mismatches

**Fixed at `5e3e639`** (all were open at `3df0d8e`):
1. ~~`validate()` raised instead of returning a list.~~ **Fixed:** `validate()` returns the list and `validate_or_raise()` raises (L606, L613). `problems()` is now internal (`_problems`).
2. ~~JSONPath-style paths, ambiguous for ids containing `.`.~~ **Fixed:** RFC 6901 pointers (L118). Ids with `.` are unambiguous (`/media/m.1/fps`).
3. ~~`canonical_hash()` ignored a stale stored `hash`.~~ **Fixed:** it raises on `hash_mismatch` (L674). `stamp_hash()` is the one call that skips the check.
4. **Author fields fail as `attribution_field`.** Re-checked; unchanged and correct (L228). Test 24 already matches.
5. **Fades also apply to text items.** Re-checked; unchanged. `set_fade` covers text.
6. **"Exactly one main" has no dedicated rule.** Re-checked: `missing_main_track` / `bad_track_id` / `duplicate_id`, as the PR body (L43) now says.
7. **Hash ordering is resolved start, then id.** Re-checked (L656); the PR body (L67) now says the same.
8. **Error code mapping (a Wire-side decision, not a mismatch):** `TimelineError.code` is `bad_input`. MCP maps it to `schema_mismatch` (rule `bad_schema`), to `invalid_op` (inside `timeline_apply`) or to `invalid_doc`. `rule`, `path`, `id` and `problems` pass through verbatim.

9. ~~A raw `id` was attached even when the id was malformed or duplicated (open at `5e3e639`).~~ **Fixed at `fbbb2c0`** (code in `9698aaa`). Checked line by line in the `5e3e639...fbbb2c0` compare:
   - `timeline.py` changes only `_problems` (it now wraps the old body, renamed `_collect`) and adds `_all_ids`.
   - `id` survives only if the rule isn't `bad_id`/`duplicate_id` **and** the id is used once in the doc, matches `ID_RE` and is NFC.
   - `_raise_unless_valid`, and therefore `canonical_hash`, `stamp_hash` and `to_otio`, goes through the same `_problems`.
   - `duplicate_id` placement and the raw-id messages were already that way and are unchanged.
   - `docs/timeline.md` (+5 −2) states the same rules.
   - Nothing else changed in code. The rest of the compare is `tests/test_timeline.py` (+106 −16).

10. **`fbbb2c0...b1b51c1` verified** (every point Bay claimed is in the code):
   - **`8231d21`:**
     - A non-string role gives `bad_track_role` (L392).
     - Mixed-type keys give `unknown_field` (L227).
     - A lone surrogate gives `wrong_type` (L260–264).
     - Hashing raises only `TimelineError`.
     - **Nuance:** a non-string *media-map* key gives `wrong_type`, not `unknown_field` (L370).
   - **`10a310d`:** `seconds_to_ticks_nearest` behaves as claimed (L160–170). **Nuance:** the strict helper (L138) still rounds a float input rather than raising.
   - **`d702466`:** `out_of_range` for item ends (L527–528), anchored ends (L560–561), duration after speed (L523–524), every `[num, den]` part (L284–285) and `version` (L345–346). Exactly 2⁵³ is valid, a raw tick field stays `too_large` (L243), and `RULES` still has 36 ids (L69–77).
   - **`86211b5`:** a missing `type` gives `missing_field` (L416–418). A missing `id` skips the id check (L425) and is reported as `missing_field` by the strict-keys check.
   - **`b1b51c1`:** a merge of `main` that adds only `1d14e01` (#34: `pipeline.py`, `tests/test_job_manifest.py`).

**Remaining** (none blocks pinning):
- **Test counts not verified:** "140 cases" (`S1-PR-BODY.md` L94) and "299 passed" (L122) are Bay's numbers; I didn't run the suite.
- **PR body:** the 9:29 AM ET version still matches on the API, the `id` rules (L27–30), the schema summary, the rulings, the hash definition, the 36 rule ids, OTIO and the Slice 2 notes. I haven't seen a version covering the 11:22 commits. `docs/timeline.md` at `b1b51c1` documents `seconds_to_ticks_nearest`, the 2⁵³ `out_of_range` cap and `missing_field` for a missing `id`/`type`.
- **Wire-side caveat:** an unknown key containing a lone surrogate is reported as `unknown_field`, and its `path` carries that surrogate. The MCP layer must serialize JSON with `ensure_ascii=True` (Python's default) so the response stays valid UTF-8.

**Remaining assumptions** (marked **[A]**): only the Wire-side client `schema_version` guard (test 57 and the `schema_mismatch` row).

---

## 1. Registry outline (Phase 1)

**One registry in `api.py` generates three things:** MCP `tools/list`, the CLI, and the native Hermes plugin (a thin generated wrapper; PLAN §8.4). Each entry holds: `name`, `kind` (read | write), the input JSON Schema, the output schema, MCP annotations, the error codes it can return, and the slice it depends on.

### Tool input conversion

**Rule (Ada 18:40, exact wording):** "/mcp accepts time in seconds through `_s` args, and raw tick args pass through to the engine." Order: see §1h (j).

**Every `/mcp` `_s` input goes through `timeline.seconds_to_ticks_nearest()` exactly once. The strict `seconds_to_ticks()` is never used at `/mcp`.**
- **Field naming (decided):** a `_s` suffix (`at_s`, `fade_in_s`, `fade_out_s`, `offset_s`), so seconds can't be confused with the doc's tick fields.
- **JSON schema (Ada 18:11):** each `_s` field may be *declared* `"type": "number"` for clients, but **nothing is enforced at the schema**. Every value goes to the helper, so a string (even `"1"` or `"1.5"`), `true`/`false`, `null` and lists all get the helper's `TypeError`.
- **Converting values:** `ticks, used = timeline.seconds_to_ticks_nearest(x)` (`c1bbddb` timeline.py L160). It rounds to the nearest tick, with exact halves going to even. The tool layer does no other rounding, clamping or sign check: **negative values pass through**, and the engine's own rule decides.
- **Helper errors (Ada 18:11, Bay's wiring):** a `TypeError` (bool, str, null, list, object) or `ValueError` (NaN, ±inf, including JSON `1e400`, which Python parses as inf) becomes **`invalid_op` `bad_arg` @ `/ops/k/<arg>_s`** (nested: `/ops/k/anchor/offset_s`), with `op_index` and no `id`. Nothing reaches the engine and nothing is applied. `1e308` is finite, so the helper doesn't reject it and the engine answers (`too_large`). `-0.0` becomes tick `0`.
- **Engine passthrough:** the converted ticks go to the engine. **Path rewrite (Bay):** when the engine answers with a tick rule (`too_large` over 2⁵³, `negative_time` on an unsigned field) at the field the `_s` arg was written to (the op path `/ops/k/<arg>` or that doc field), /mcp returns the same `code`, `rule`, `id`, `op_index` and `problems`, with only `path` rewritten to `/ops/k/<arg>_s`. **Any other engine answer** (`out_of_range` @ the item, `fade_too_long`, `empty_range`, `src_out_of_media`, `anchor_before_zero`, `transition_overlap_mismatch`, `non_integer_duration`, a `bad_arg` such as `split_clip` not strictly inside, or a tick rule at a *different* field) comes back verbatim. **No rewrite in that last case (APPROVED, Ada 18:16; §1h).**

**Outputs: exact ticks and seconds**
- **Echoing inputs:** each write result echoes the value actually used for every `_s` input, as `used: {"<arg>": {"ticks": <int>, "seconds": <number>}}` (`used` is my proposed name). `seconds` = `float(Fraction(ticks, 705600000))`, so the agent sees the rounded value rather than the one it sent.
- **Every time field** in any output is `{ "ticks": <int>, "seconds": <number> }` derived the same way, with `tick_rate` at the top level.
- **Round trip:** feeding a returned `seconds` back in gives the same tick (test 30).

**`get_timeline` is the exception**
- It returns the **raw doc in ticks**, exactly as stored, so its `hash` equals the hash of the file.
- (**Deferred to S4.**) `summary=true` adds seconds to the outline, but the raw doc is never rewritten.

**Strings**
- Strings pass through **unchanged**: no NFC normalisation in the tool layer. A non-NFC string comes back as `not_nfc` with its `path`.
- **Splits and speed:** `seconds_to_ticks_nearest()` always lands on a tick, but at speed ≠ 1 that tick can give a half with a non-whole duration. The tool returns `invalid_op` with `non_integer_duration`; it never re-rounds (see the Slice 2 notes).

### What every write takes and returns (PLAN §4.5, plus the above)
- **In (`timeline_apply`):** `project_id`, `base_version`, `ops` (1–500; /mcp accepts time in seconds through `_s` args, and raw tick args pass through to the engine.), `summary` (non-empty NFC, ≤ 200 chars), `client_op_id`, optional `group_id` (a string; my layer never *adds* `null`, and to mean "no group" it leaves the field out). **Ada 18:11:** an agent's `group_id: null` **passes through to the engine**, which gives `invalid_op` `bad_arg` @ `/group_id` (checked at `c1bbddb`). There's also an optional `schema_version` **[A]**, a /mcp-only guard: if it isn't `hs.timeline/1`, /mcp returns `schema_mismatch` with rule **`bad_schema` @ `/schema_version`** (Bay; the validator's existing rule); if it matches, /mcp strips it. The engine would reject it otherwise (`unknown_arg` @ `/schema_version`, checked at `c1bbddb`).
- **Out:** `ok`, `op_id`, `group_id`, `seq`, `new_version`, `hash`, `tick_rate`, `summary`, `changed_ids`, `undoes` (`null`, or a list of `op_id`s), `before_frame`/`after_frame` refs (these are S5 and null before then), and `warnings`. /mcp adds `used` (§ Tool input conversion).
- **Retries (S2 `client_op_id`):**
  - If /mcp retries a write, it must resend **the exact same args with the same `client_op_id`**. An identical retry, even with a now-stale `base_version`, returns the cached result.
  - Any other call under that key gives `invalid_op` / `client_op_id_mismatch` @ `/client_op_id`, with `op_ids` = [the cached entry].
  - The key is (actor, `client_op_id`), shared by `timeline_apply`, `history_undo` and `history_redo`. So an undo must never reuse an apply's key, and every new call gets a fresh `client_op_id`.
  - **/mcp always resends the exact tool on a retry.** It does this even though, after a reload, the engine accepts either undo or redo for an undo-of-undo key (RULED, §1c).
  - The engine checks shape first, so a malformed retry gets `bad_arg` at its path, never `client_op_id_mismatch`.
- **Actor and step** come from the session token, never from an argument. If `actor` or `step` appears in the args or in an op, it's stripped and reported as a `warnings[]` entry `{code:"ignored_field", path, message}`.
- **How writes are exposed:** writes are ops inside `timeline_apply{ops:[…]}`. Each op is a registry entry with its own schema. **Phase 1 publishes only `timeline_apply` for writes; there are no per-op MCP tools.** The registry stays the single source. Revisit in Slice 2 (see the Slice 2 notes).

### Error codes this contract uses

| Code | When | Extra fields |
|---|---|---|
| `schema_mismatch` | The doc fails with rule `bad_schema` (its `schema_version` is missing or isn't `hs.timeline/1`), or a client sends a different `schema_version` (that second check is **[A]**, the /mcp-only guard) | `rule` **`bad_schema`**, `path` **`/schema_version`**, `expected`, `got` (Ada 18:11, Bay) |
| `invalid_doc` | A whole doc fails `validate()`, which includes `hash_mismatch` on a stored doc (on load, or a doc passed to `validate_timeline`) | `rule`, `path`, `id` (when the first problem is in an item or marker), `problems: [{rule, path, message, id?}]`: passed through **verbatim** from `TimelineError.as_dict()` / `validate()` |
| `invalid_op` | An op's args are bad, **or the doc after the op would fail `validate()`**. Nothing is applied | `rule`, `path`, plus `op_index` for op-level errors. **/mcp-only `_s` args (Ada 18:11):** a helper `TypeError`/`ValueError` gives `bad_arg` @ `/ops/k/<arg>_s`; an engine tick rule at the converted field comes back with its path rewritten to the `_s` arg (§ Tool input conversion). There is no `invalid_args` code. Argument errors use the path `/ops/<k>/<arg>` or `/<arg>`. A validator failure adds `id?` and `problems` (verbatim), and its `path` points into the doc. **#39 (merged, main `8d181ed`):** `insert_clip` with junk `media` (unknown or empty string, number, `null`, list, object, bool) gives **`unknown_media` @ `/ops/k/media`**, with `op_index` and **no `id`**, never the doc path. S2 adds two rules. **`id_reused`** @ that id's path (`/ops/k/id`, `/ops/k/ids/i`): a caller named an id that existed earlier in the log or earlier in the same batch; an id in the doc right now is still `duplicate_id`. **`client_op_id_mismatch`** @ `/client_op_id`, with `op_ids` = [the cached entry]. A non-string id (`id`, `track`, an entry of `between`/`ids`, `anchor.to`) gives **`bad_arg`** at its own path, before any lookup. **Checked before dedupe**, each as `bad_arg`: `ops` must have 1–500 entries (`/ops`), each op an object with a string `op` (`/ops/k`); `base_version` an integer ≥ 0; the undo/redo target exactly one non-null string `op_id`/`group_id`. **On main since #39 (`8d181ed`; Ada 1:59 PM):** `timeline_apply{group_id: null}` gives `bad_arg` @ `/group_id`, fresh or on a cached key, checked before dedupe (`/op_id`, `/group_id`, or `""` for neither, both, or a redo by group). `split_clip` id errors are reported at `/ops/k/ids/i`. **#38 (merged, main `a1922f0`):** **`transition_too_long`** @ **`/ops/k`** (the op, not a doc pointer) with `op_index` and **`id` = the crossfade that doesn't fit**. It comes from a ripple trim that leaves the clip too short for its crossfades: it must be longer than each one and at least as long as both together. Tie-break (RULED): if one crossfade doesn't fit on its own, `id` is that one; if neither fits on its own, or each fits alone but not both together, `id` is the **outgoing** crossfade. It has no `problems` list, and nothing is applied |
| `not_found` | An unknown `project_id`, item, track, marker, entry or group | `rule`, `path`, and `id` = the id that wasn't found. Since F2, a non-string id is `bad_arg` and never reaches `not_found`, so `id` is always present. Op-level errors add `op_index`, and `path` is `/ops/<k>/<arg>`; `remove_track` reports `/ops/<k>/id`, while `insert_clip`/`add_text` report `/ops/<k>/track`. Tool-level paths are `/project_id`, `/op_id` and `/group_id`. **This `id` isn't a doc item id**, so the blanket check skips it |
| `needs_approval` | A Propose-mode write is parked. It never applies or skips on its own | `pending_id` |
| `undo_blocked` | The engine refuses an undo or redo. Passed through verbatim | **One shape for all three reasons:** `reason`, `op_ids`, `path` (`/op_id` or `/group_id`, whichever the caller named) and `id` (that op_id or group_id). `op_ids` depends on the reason: **`actor`**: the target entries owned by another actor; **`dependents`**: the later blocking entries in `seq` order, the same as `blocking_op_ids` (sent only for this reason); **`inverse_invalid`** (fallback only): the entries being undone in `seq` order (the target, or every live entry of the group; doc note at `c1bbddb`), plus `rule` and `problems` verbatim from `validate()` |
| `engine_offline` | Any write while the app is closed (Phase 1), including `export_otio`. Reads still work | `hint`: open the app |
| `conflict` | A stale `base_version` (PLAN §4.5, kept) | `current_version`, `history_diff`: records with `new_version > min(base_version, current)`, oldest first. Keys: `seq, op_id, group_id, actor, step?, summary, base_version, new_version, changed_ids, undoes` (oplog.py:834, :924–931; **S3-SPEC §5 row 4, SETTLED**). **S3 (APPROVED: Ada 6:56 PM, §11 allowed diffs C and D):** `hash` is added (D10), and the diff is capped at 200 records (the oldest 200 after `base_version`). **`history_diff_truncated` is always present (`false` when not cut), at the top level next to `history_diff`** (D19 revised). The client pages the rest with `history_diff{since_version: <last record's new_version>}` |
| `permission_denied` | A write in Ask mode, or a missing scope (PLAN §4.5, kept) | n/a |
| `failed` (S3-SPEC D28, D25; **APPROVED, Ada 7:15–7:20**: an existing code; closed-app reads get it for a corrupt log line; **HTTP 500**) | A corrupt `oplog.jsonl` line (not a torn final line, D2): today `load` raises `ValueError` (oplog.py:789, :1232, :1235) or `JSONDecodeError` (:1228). Also unexpected exceptions (mcp.py:486–487). It's an **existing error code** (api.py:25 `EXIT`), **not a rule id** | `error` naming the line, **`seq`**, `hint` ("restore the project folder from a backup"); **no `rule`**, no `hash`. Writes are refused with the same body |

**Naming (decided):** `engine_offline`, matching PLAN-MERGED §4.5.

### 1a. Read tools

| Name | Input | Output | Errors | Depends on |
|---|---|---|---|---|
| `get_timeline` | `project_id` (**`summary?` deferred to S4**, 8:32 PM: not built at `0282e9f`, and no contract test requires it) | the raw doc in ticks (`schema_version`, `tick_rate`, `version`, `hash`, `tracks`, `markers`, `media`). With `summary=true`: an outline with ticks + seconds | `not_found`, `invalid_doc` | S1 `validate()` + S3 store |
| `get_hash` | `project_id` | `{project_id, schema_version, version, hash, seq}`, read in one go under the project mutex via `Oplog.head()` (**S3-SPEC §5 row 6, D3**), or `invalid_doc` with the `rule`/`path` errors if the stored doc is invalid; **never a hash for an invalid doc** | `not_found`, `invalid_doc` | S1 `canonical_hash()`, S3 |
| `list_markers` | `project_id` | `{tick_rate, markers:[{id, at:{ticks,seconds}, label}]}` sorted by `(at, id)` | `not_found` | S1, S3 |
| `export_otio` | `project_id` | writes a `.otio` file into the project's `exports/` folder (Wire decision) and returns `{path, timeline_hash}`; no inline JSON. It doesn't change the timeline and isn't logged as an op. **PLANNED (no field or test yet):** a warning when any tick value is above about 7×10¹⁵, because OTIO 0.18.1's JSON reader misreads such values on read-back (`docs/timeline.md` L164; Ada: warn, don't fix). It belongs to whichever slice first touches `to_otio()`; S2 and S2b don't. Annotations: not read-only, not destructive | `not_found`, `invalid_doc`, `engine_offline` (Wire decision: refused when the app is closed, so the stdio proxy never writes project files, per C7) | S1 `write_otio()` / `to_otio()`, S3 |
| `validate_timeline` | `doc` | `{ok:true, hash}` or `invalid_doc` / `schema_mismatch` | as listed | S1 `validate()` + `canonical_hash()`. **Optional**: lets an agent dry-run the validator |
| `history_list` | `project_id`, `since_version?` (S3-SPEC D19, **APPROVED, Ada 7:15–7:20**: default 0, `limit?` = 50 (1–200); returns `{entries, next_since_version, head_version}`; engine `bad_arg` @ `/since_version` / `/limit`; also `GET …/history`, D26) | entries with `new_version > since_version`: `seq`, `op_id`, `client_op_id`, `group_id`, `actor {kind,id}`, `step?`, `summary`, `base_version`, `new_version`, `hash`, `ops`, `inverse`, `changed_ids`, `undoes`. **No `run_id`** (Ada) | `not_found` | S2 `Oplog.history_list` (§1c), S3 |
| `history_diff` (S3-SPEC D19, **APPROVED, Ada 7:15–7:20**; `history_diff_truncated` at the top level of `conflict`) | `project_id`, `since_version`, `limit?` = 200 (1–500) | `{records, next_since_version, head_version}`. Each record is the conflict diff record + `hash` (D10). Oldest first; the cursor is the last `new_version`, `null` at the head. Bad args are engine `bad_arg` @ `/since_version` / `/limit`. Also `GET /api/projects/<id>/history/diff` (D26) | `not_found`, `invalid_op` | S3 |
| `project_status` (S3-SPEC D8, **APPROVED, Ada 7:15–7:20**; on the C9 allowlist) | `project_id` | `{project_id, schema_version, version, hash, seq, engine:{pid, port, started_at} \| null, mode}` (`mode` is null until S8). Works with the app closed (it reads `.lock`). Must be added to the C9 allowlist (test 60). Also `GET /api/projects/<id>/status` (D26) | `not_found` | S3 |

### 1b. Write ops, inside `timeline_apply`

S2 defines these ops and their inverses (`docs/oplog.md@c2a930f` L73–90). The /mcp rows below convert `_s` inputs to the ticks the engine takes.

| Op | Input | Effect / notes | Errors | Status |
|---|---|---|---|---|
| `add_marker` | `at_s` (≥0), `label` (NFC) | creates `{id, at, label}` | `invalid_op`, + common | In PLAN; S2 |
| `remove_marker` | `id` | removes the marker | `not_found`, + common | **Proposed** (not in PLAN) |
| `split_clip` | `id`, `at_s` (strictly inside the clip after tick conversion) | 2 pieces with unique ids and `split_from: <old id>`; the inverse `join_clips` restores the old id | `not_found`, `invalid_op`, + common | In PLAN; S2 |
| `set_fade` | `id` (a clip **or text item**), `fade_in_s?`, `fade_out_s?` | sets the tick fields; the validator checks ≥0 and sum ≤ duration (`negative_time`, `fade_too_long`) | `not_found`, `invalid_op`, + common | **Proposed** (Slice 2 notes) |
| `set_anchor` | `id` (a text item or a `music` clip), `anchor: {to, offset_s}`, or `null` plus `at_s` | swaps `at` ↔ `anchor` (exactly one; `at_and_anchor`); the target must be a V1 clip; the resolved start must be ≥ 0 | `not_found`, `invalid_op`, + common | **Proposed** (Slice 2 notes) |
| `edit_text` (S2b, #40 merged, main `c6de84e`) | op `edit_text{id, text?, style?}` inside /mcp `timeline_apply` (there's no separate tool; wording corrected 8:32 PM). **No `_s` args.** The tool schema declares `id`, `text` and `style` as strings for clients (documentation). **Enforced (Ada 18:04, §1g):** /mcp pre-checks **only `id`**, and only in the engine's order: `unknown_arg` @ `/ops/k/<arg>`, then `missing_arg` @ `/ops/k/id`, then `bad_arg` @ `/ops/k/id` (no `id`). So the schema must **not** reject unknown args itself (no enforced `additionalProperties:false`) unless it reproduces `unknown_arg` exactly. `text`/`style` go to the engine **unchecked**, with no `anyOf`/`minLength`/type enforcement | edits a text item on any text track. `text`/`style` are **passed through byte for byte** (no normalising, per §1e). Writes go **only via `timeline_apply`**. The inverse is `set_fields` with the old values of the given fields only. **`changed_ids`** is `[id]` when the value changes, and **`[]` for a byte-identical no-op** on apply, undo and redo. The no-op is still an entry (new version, same hash), and an exact retry returns it. **Empty `text` is allowed; empty `style` is not.** `set_fields` is internal-only: a client gets `unknown_op` | engine check order (verbatim through /mcp): `unknown_arg` @ `/ops/k/<arg>`; `missing_arg` @ `/ops/k/id`; `bad_arg` @ `/ops/k/id` for a non-string `id` (no `id` field); `not_found` @ `/ops/k/id` with `id`; `bad_arg` @ `/ops/k/id` with `id` = the item for a clip or transition; **`missing_arg` @ `/ops/k`** (no `id`) when neither field is given (engine message "edit_text needs 'text' and/or 'style'"; /mcp adds the `hint` **"give text or style"**); value errors `wrong_type`/`not_nfc` @ `/ops/k/text` or `/ops/k/style` (naming the tool arg `text`/`style`) **with `id` = the text item, exactly as over HTTP** (`text` is checked first). A non-string `text`/`style` is the engine's `wrong_type`, never a schema error. Undo/redo: `undo_blocked` per the error table | **MERGED** (main `c6de84e`) |
| `delete_clip` | `id`, `ripple?` | removes the item; what happens to anchored items is in the Slice 2 notes | `not_found`, `invalid_op`, + common | In PLAN; S2 |
| `insert_clip`, `move_clip{at_s}`, `trim_clip{ripple}`, `add_text`, `add_transition{xfade}`, `set_props`, `add_track{role}`/`remove_track` | per PLAN §4.5, with time in seconds | same envelope | + common | S2 |
| `history_undo` (a tool, not an op) | `client_op_id`, exactly one of `op_id`/`group_id`, `summary?`, `base_version?` | appends **one** entry whose `undoes` lists the target's `op_id`s (a group: newest first) | `undo_blocked`, `not_found`, `invalid_op` (`already_undone`, `bad_arg`), `conflict`, + common | S2 |
| `history_redo` (a tool, not an op) | `client_op_id`, `op_id` (of an undo entry), `summary?`, `base_version?` | undoes that undo entry as a new entry: `undoes = [that op_id]` | `invalid_op` (`not_an_undo`, `bad_arg`), `undo_blocked`, `not_found`, + common | S2 |

"+ common" for every write means `needs_approval`+`pending_id` (S8), `engine_offline` (S3), `conflict`, `permission_denied`, and `schema_mismatch`.

### 1c. S2 oplog: what /mcp relies on (**MERGED: source `480a220`, main `e274051`**)

Line refs are `oplog.py@480a220`, the same tree as main `e274051`.
- **Single entry point:** `Oplog.call(session, tool, args)` (L766–780). The tools are `timeline_apply`, `history_undo` and `history_redo`; any other tool gives `invalid_op` / `unknown_tool`. Every write, undo and redo is one entry with one `op_id`.
- **Actor and step:**
  - `actor {kind,id}` comes only from `Session` (L999).
  - `step` is logged only for an agent with a plan step (L103–107, L1009–1011).
  - A forged `actor`/`step` in the args or in any op is stripped, with an `ignored_field` warning (L1227–1249). That happens before the dedupe check.
  - **`run_id` isn't in the line (L41–56; Ada).** If the ACP bridge needs it, Wire keeps it keyed off the session and plan step, never from tool args.
- **Entry fields:** `undoes` is `null` for an apply (L1036), or a list of `op_id`s, newest first (L1126).
- **Ids are never reused (Ada):**
  - **Auto ids:** come from `ctx.fresh`, which skips retired ids (L387 for tracks).
  - **F1:** every id present at any point in a batch, or handed out in it, is retired, even when the same batch removed it. `_run` collects them (L930–946) and `_retire` adds them (L965–969); `_commit`, `load` and `replay` all call it (L1019, L1147, L1176).
  - **`id_reused`:** an explicit id that existed earlier in the log or earlier in the same batch is rejected at that id's path (L677–681; called at L294, L385, L514). An id in the doc right now is still `duplicate_id`. Inverses (undo, redo, `load`, `replay`) skip the check.
- **F2, id types:** a non-string `id`, `track`, `between[i]`, `ids[i]` or `anchor.to` in a public op gives `bad_arg` at its own path, before any lookup (L262–286, called at L705). This applies to create ops too: a non-string `id` or `ids[i]` used to give `bad_id` and now gives `bad_arg`.
- **`changed_ids`:** diffs stored JSON **and** resolved start/end (L200–229). So an item that moves because its anchor target moved counts, and the dependents check uses the same set.
- **Shape checks run before dedupe** (`0b459c4`; L1028–1030, L1049–1051). So a junk retry on a cached key gets the same `invalid_op` / `bad_arg` as a fresh call. It never reaches the mismatch comparison or the log replay. The checks are:
  - **`ops`:** a list of **1–500** ops, else `bad_arg` @ `/ops`. That covers 0 or 501 ops and `5`, `null`, `1.5`, `true` or `-1`. Each op must be an object with a string `op`, else `bad_arg` @ `/ops/k` with `op_index` (L823–836).
  - **`base_version`:** an integer ≥ 0, else `bad_arg` @ `/base_version` (L818–821).
  - **`summary`, `group_id` and arg names:** `summary` is NFC with no lone surrogate. Arg names are sorted with `repr`, so a non-string key in the call args no longer crashes (L784–800).
  - **`timeline_apply` `group_id`:** a non-string `group_id` is `bad_arg` today, but `null` is accepted as "no group" (L784–800). **Satisfied on main since #39** (`8d181ed`; `oplog.py@4bfd71f` L1094–1095, `docs/oplog.md` L59, L217): `null` gives `bad_arg` @ `/group_id`, the same as undo and redo, and callers leave the field out instead. /mcp never sends `null` either way.
  - **The undo/redo target** (R3/R4; L838–844): exactly one of `op_id` / `group_id`, and it must be a **non-null string**. A non-string or `null` value is `bad_arg` @ `/op_id` or `/group_id`. Neither or both is `bad_arg` @ `""`, and so is `history_redo{group_id}`. A `null` group never matches ungrouped entries (L1065).
- **Dedupe and retries** (L860–922):
  - The key is (actor, `client_op_id`), checked after forged fields are stripped and shared by all three tools.
  - An identical retry returns the cached result, even with a stale `base_version`. For `timeline_apply`, "identical" means the same `base_version`, `summary` and `group_id`, and the ops re-run on the past doc must reproduce the logged ops. For undo and redo, it means the same target, the same summary (or the tool's default), and the same `base_version` if one is given.
  - **R2:** "identical" always includes the **tool**, even when a `summary` is given. The tool is recorded at commit (L1023) and checked at L868. After `load`, it's derived from the line (`_tool_of`, L1151, L1156). So a redo reusing an undo's key, or the other way round, is a mismatch, live and after `load`.
  - Anything else gives `client_op_id_mismatch` @ `/client_op_id` with `op_ids: [cached op_id]`.
- **RULED (permanent), Ada 1:48 PM ET:** after `load`, a key whose entry is an **undo of an undo entry** accepts a retry by either `history_undo` or `history_redo` (`_tool_of` returns `None`, L1156–1166). That's by design: a redo *is* the undo of an undo entry, so either tool names the same operation with the same effect, and the log line stays locked (no tool field). Live, before a reload, the tool is still compared. /mcp always resends the exact tool on a retry anyway (§1 write envelope).
- **Group undo:** one entry, newest first (L1111, L1126).
- **`undo_blocked`** (L1075–1123): every reason has `reason`, `op_ids`, `path` (`/op_id` | `/group_id`) and `id` (the target named). `op_ids` means something different per reason (Glyph):
  - **`actor`:** the target entries owned by another actor (L1078–1088).
  - **`dependents`:** the blocking later entries in `seq` order, the same list as `blocking_op_ids` (L1101–1110).
  - **`inverse_invalid`** (fallback only): the target entries in `seq` order, plus `rule` and `problems` (L1077, L1112–1123).
  - /mcp passes all three through verbatim.
- **Error shapes:**
  - `OplogError.as_dict()` gives `{ok:false, error, code, hint?, …extra}`.
  - Op errors: `path` = `/ops/<k>/<arg>[/<i>]` (RFC 6901, L930–941).
  - Op-level `not_found` always carries `id` (L934). `remove_track`'s path is `/ops/<k>/id` (L400).
  - Validator failures: S1's `rule`/`path`/`id?`/`problems`, verbatim (L950–960).
  - A non-string `add_track` role gives `bad_track_role` @ `/ops/<k>/role` (L378).
  - A lone surrogate in `summary` gives `bad_arg` @ `/summary` (L800).
- **Wire-side caveats:**
  - Keep `ensure_ascii=True` when serializing responses.
  - In `undo_blocked`, `not_found` and `client_op_id_mismatch`, `id`/`op_ids` are op, group or missing ids, not doc items. The blanket `id` check (§2) applies only to doc problems.
  - **Retry cost:** checking an apply retry re-runs the log up to that entry (L897–903). That's fine for Phase 1, but worth watching on long logs.

**Open at `2f80bbd`: both CLOSED at `480a220`** (re-run in Python from the tarball, 1:47 PM ET):
1. ~~A retry with a non-list `ops` crashes.~~ **Fixed** (`0b459c4`/`480a220`; L1029). On a cached key, `ops` = `5`, `null`, `1.5`, `true`, `-1`, `[]` or 501 ops gives `bad_arg` @ `/ops`, and `[1]`, `[null]` or `[{}]` gives `bad_arg` @ `/ops/0`. Test 76.
2. ~~`split_clip` `duplicate_id` reports `/ops/k/ids`.~~ **Fixed** (`0b459c4`; L512). It now reports `/ops/0/ids/1`, or `/ops/0/ids/0`, at the clashing entry. Test 75.

**New at `480a220`; fixed in #39, merged as main `8d181ed`:**
- **Op-level arg names that aren't strings still crash.** `_apply_one` still sorts unknown op keys without `key=repr` (L700). So an op with mixed-type unknown keys (e.g. `{1: …, "zz": …}`) raises `TypeError`. The fix covered only the call-level args (L785). JSON can't produce non-string keys, so /mcp and JSON-over-HTTP can't hit this; only an in-process Python caller can. **Fixed in #39** (`dc20a2c`; `oplog.py@4bfd71f` L747): a non-string op arg name now gives `invalid_op` / `unknown_arg` @ `/ops/k/<repr>` (e.g. `/ops/0/1`), not a `TypeError` (reproduced). It's on main since `8d181ed`, so this S3 gate is met.

**Mismatches found at `ff59093`: all RESOLVED at `c2a930f` and unchanged at `2f80bbd`** (verified 12:42 PM ET; 1–5 reproduced in Python from the tarball):
1. ~~`changed_ids` misses anchored items that move.~~ **Fixed** (`25a3480`). Test 74.
2. ~~`add_track` reuses a retired id.~~ **Fixed** (`83241b4`). Test 73.
3. ~~`inverse_invalid` loses fields.~~ **Fixed** (`d501916`). Test 72.
4. ~~Op-level `not_found` has no `id`.~~ **Fixed** (`6fe4150`). Since F2, `id` is always present.
5. ~~A non-string role gives `bad_arg`.~~ **Fixed** (`83241b4`).
6. ~~The docstring names `seconds_to_ticks`.~~ **Fixed** (`c2a930f`; L17).

### 1d. #38 crossfade ripple trim (**MERGED: head `36f8a87`, main `a1922f0`**)

Line refs are `oplog.py@36f8a87` / `docs/oplog.md@36f8a87`. I checked every claim in Python from the tarball (2:46 PM ET). **No mismatches.**
1. **Ripple trim with an outgoing crossfade:** confirmed. With `ripple`, the start stays, so an end or start trim moves the clip's end. The ripple point is the crossfade's start (L518), so the next clip, the crossfade and everything after them shift together by the change in duration. The crossfade keeps its `dur` and `between`. With an incoming crossfade, a ripple trim leaves the crossfade in place.
   - Fixture: the base doc with c2 pulled under c1 by 0.5 s, crossfade `t12`. A 1 s end trim of c1 shifts c2, t12, c3 and x1 by −1 s, with t12 still `[c1, c2]` at 0.5 s. The start-trim equivalent gives the same spans. Trimming c2's start leaves t12 and c1 unchanged.
2. **`transition_too_long`:** confirmed (L491–515; item `id` at L970). It's checked before anything moves, and comes back as `invalid_op` @ `/ops/k` with `op_index` k and `id` = the crossfade.
   - Out-only too short gives `t12`.
   - In too short with out fitting gives `t12` (the incoming one).
   - Each fits alone but not both gives the outgoing one (`t23`), and so does neither fitting.
   - Exactly the sum is allowed.
   - In a batch it reports `/ops/1`. The hash is unchanged and no line is added.
   - The op-level rule list has 17 rules (`docs/oplog.md` L148), and `timeline.RULES` still has 36.
3. **Non-ripple end trim with an outgoing crossfade:** confirmed. It still gives `invalid_op` `transition_overlap_mismatch` @ the transition's `/dur` (a validator failure, with `id` `t12` and `problems`).
4. **Anchored items:** confirmed. `x1` (anchored to the shifted c2) moves, and `mu1` (anchored to the trimmed c1) stays.
5. **`changed_ids`:** confirmed. It's `[c1, c2, c3, t12, x1]` on apply, undo and redo, the same each time, and undo restores the hash.

**Rulings:**
- **Ada, 2:17 PM:** decisions 1, 2, 4, 5 and 6 confirmed; the outgoing crossfade wins the tie-break.
- **RULED (Ada, 2:47 PM):** `transition_too_long` is the **17th** op-level rule (not a validator rule; the S1 validator stays at **36**). When neither crossfade fits on its own, `id` is the **outgoing** crossfade.
- Prove is running the check at `36f8a87`.

**Doc rulings (Ada; docs only, shipped in #39 `7842758` at `docs/oplog.md@4bfd71f` L136–148, on main since `8d181ed`):**
1. **A ripple trim on a music track never moves a neighbour that only overlaps the clip.** Music items may overlap, and a plain overlap isn't a crossfade pair. So that case still gets `transition_overlap_mismatch`. It's documented under the existing rule, with **no new rule id**: the oplog stays at **17** rules and the validator at **36**.
2. **`transition_too_long` is checked before `empty_range`.** A ripple trim that's too short for its crossfades reports `transition_too_long`, even if the result would also be an empty range.

Both were reproduced at `4bfd71f`:
- **Music overlap:** ripple-trimming `m0`, which only overlaps `ma` (with crossfade `tab` from `ma` to `mb`), gives `transition_overlap_mismatch` @ `tab`'s `/dur`, `id` `tab`, with the hash unchanged. Without `ripple`, the same trim applies.
- **Empty range:** with a crossfade, a ripple trim to an empty `src` gives `transition_too_long` @ `/ops/0`, `id` `t12`. Without one, it gives `empty_range` @ the clip's `/src`.

**Wire-side caveats:**
- `transition_too_long` carries an item `id` (the crossfade), but its `path` is the op (`/ops/k`), not that item's doc pointer. As an op-level error, it's outside the blanket `id` check (doc problems only).
- /mcp passes it through verbatim, like `fade_too_long`.

### 1e. #39 post-S2 follow-up (**MERGED: head `c8e5604`, main `8d181ed`**)

Commits: `dc20a2c`, `5b899e7`, `fca00a6`, `13ae44f`, `1898681`, `66522ec`, `7842758`, `4bfd71f`. They touch `oplog.py`, `test_oplog.py`, `docs/oplog.md`, the clean-test scripts and their test, `ci.yml`, and the new `test_ci_ffmpeg_pin.py`. Line refs are `oplog.py@4bfd71f` / `docs/oplog.md@4bfd71f`. I checked everything in Python from the tarball (4:01 PM ET). **No mismatches with this contract.**
- **`key=repr`** (`dc20a2c`; L747, plus `missing_arg` at L749 and L838): a non-string op arg name gives `unknown_arg` @ `/ops/k/<repr(key)>`, never a `TypeError`. That's Python callers only, since JSON keys are always strings.
- **#36 CI items** (`5b899e7`): changes to the clean-test scripts only, with no engine surface. I didn't run them.
- **Canonical same-call** (`fca00a6`; `_canon` L138, compared at L944; `docs/oplog.md` L249–256): "equal" now means byte-identical canonical JSON, with no numeric or Unicode folding. Reproduced on a cached key:
  - a float `at` (e.g. `352800000.0`) or an NFD `label` in an op gives `client_op_id_mismatch`;
  - a float or `true` `base_version`, or an NFD `summary`, gives the earlier `bad_arg` (`/base_version`, `/summary`), on apply and undo;
  - an identical retry, including one with a different key order, returns the cache.
- **Checkpoints** (`13ae44f`; L135, L953, L1025–1028, L1086, L1217): a retry re-runs at most 15 entries from the nearest checkpoint. Checkpoints sit at entries 0, 16 and 32 for a 40-entry log, both live and after `load`. All 40 identical retries return the cache, and naming an engine-picked id across a checkpoint still matches. A retry with a changed label is a mismatch.
- **`unknown_media`** (`1898681`; L326–328; `docs/oplog.md` L166–170): `insert_clip` `media` of `"zz"`, `""`, `5`, `null`, `[]`, `{}` or `true` gives `unknown_media` @ `/ops/k/media`, with `op_index` and no `id`. A bad `track` is checked first (`not_found` @ `/ops/k/track`). `unknown_media` is the existing timeline rule, so there's no new id.
- **`group_id: null`** (`66522ec`; L1094–1095, before shape checks and dedupe): `bad_arg` @ `/group_id`, both fresh and on a cached key. Leaving it out still gives an ungrouped entry (`group_id: null` in the result and line), and an identical omitted-field retry returns the cache.
- **Docs** (`7842758`): 17 op-level rules (`docs/oplog.md` L161), with `RULES` still at 36. The two doc rulings are in §1d.
- **CI** (`4bfd71f`, `c8e5604`): the ffmpeg pin, with no engine surface. `c8e5604` makes the apt fallback fail hard (`::error::`) if ffmpeg isn't installed after 3 attempts.
- **Ada's ruling on CI (5:35 PM note):** the apt fallback may install an unpinned ffmpeg version, but it must print a `::warning::` that names that version. **Not yet met at `c8e5604`/`8d181ed`:**
  - `ci.yml` L59 prints `::warning::pinned FFmpeg download failed; falling back to apt`, without the version.
  - After the install, the version line is printed as plain text (L87–88), not as a `::warning::`.
  - This is CI only and doesn't affect any contract test.

**/mcp envelope against #39 (no contradiction):**
- `group_id`: send it only as a non-null string, or leave it out. The engine now enforces the same rule.
- **Retries:** resend the exact tool and args. Canonical same-call makes this strict.
  - /mcp converts `_s` values to ticks before calling the engine, so an agent retry with `at_s: 1` vs `1.0` gives the same ticks and still matches.
  - Every field /mcp passes through unchanged (labels, `summary`, `props`) must be forwarded byte for byte. That means no re-normalising and no int↔float rewriting, or a retry becomes `client_op_id_mismatch`.

### 1f. S2b `edit_text` (**#40 MERGED: head `c1bbddb`, main `c6de84e`, tree `2eccb5b`**)
- **Issue #41 (not blocking):** `from_otio(to_otio(doc))` raises a bare `StopIteration` at timeline.py:834 (`prev = next(...)`, in `from_otio` L808) when a music clip shares an `at` with the outgoing clip of a crossfade. It predates #40 (it also fails on `8d181ed`). Rin scheduled it with the 7e15-tick OTIO warning (§1a `export_otio`), for whichever slice first touches OTIO import or export. It doesn't block S3.
- **Code** (`hermes_studio/oplog.py` @ `c1bbddb`): `_TEXT_FIELDS = ("text", "style")` L666, `op_edit_text` L669, `PUBLIC_OPS` entry L712 (`required {id}`, `optional {text, style}`). Steps 1–2 of the check order come from the generic `_apply_one`/`_check_refs`; steps 3–6 are in `op_edit_text`. Values are checked with `timeline._Checker().string(v, "", empty=(k == "text"))`, so the rules are `wrong_type` (non-string, empty `style`, lone surrogate) and `not_nfc`.
- **Docs** (`docs/oplog.md` @ `c1bbddb`): op table row L87; the `edit_text` block L167 (check order, no normalising, inverse, `changed_ids`/no-op, house rule at L192); the `undo_blocked` `op_ids` per-reason note L214.
- **Verified in Python from the `c1bbddb` tarball** (base fixture):
  - Errors: `unknown_arg` @ `/ops/0/dur`; `missing_arg` @ `/ops/0/id`; `bad_arg` @ `/ops/0/id` with no `id` for `5`/`null`; `not_found` with `id` `zz`; `bad_arg` with `id` `c1` / `t12`; `missing_arg` @ `/ops/0` with no `id`. A clip with neither field gives `bad_arg` (the item type is checked before the fields).
  - Value errors: `wrong_type` @ `/ops/0/text` or `/ops/0/style` with `id` `x1` for `5`, `null`, `["pop"]`, `style: ""` and lone surrogates; `not_nfc` for NFD. `text: ""` is applied. With bad `text` and bad `style` together, the error reports `text`. As op 1 of a batch, the error reports `/ops/1`.
  - Changes: `changed_ids` `[x1]` on apply, undo and redo, and undo/redo restore the hash. The inverse is `{set: {text: "Hi"}, unset: []}` only; other fields are untouched.
  - No-op: `changed_ids` `[]` on apply, undo and redo; version 1 with the same hash; one entry; an exact retry gives the same `op_id` and no new entry.
  - Client `set_fields` gives `unknown_op` @ `/ops/0/op`.
  - Undo blocks: a later edit gives `undo_blocked` `dependents`, with `op_ids` = `blocking_op_ids`. An agent undoing a human edit gets `actor` with `op_ids` = [target].
  - `len(T.RULES)` is 36; the doc lists 17 rules.
- **Rules stay 17/36.**
- **/mcp schema typing:** the Ada 6:01 PM ET (18:01) ruling, with Prove's correction, gave schema rejections a separate error code with an engine path plus `cause` (that code was removed at 6:11 PM). **Superseded by Ada 6:04 PM ET (18:04), §1g:** /mcp pre-checks only `id` (`unknown_arg` → `missing_arg` @ `/ops/k/id` → `bad_arg` @ `/ops/k/id`), and `text`/`style` go to the engine unchecked. **Engine answers checked at `c1bbddb`:**
  - `{id: 5}` gives **`bad_arg` @ `/ops/0/id`, no `id`**; so do `{id: null}` and `{id: 5, text: 5}`.
  - `{id: 5, bogus: 1}` and `{bogus: 1}` give `unknown_arg` @ `/ops/0/bogus`.
  - `{id: "zz", text: 5}` gives `not_found` @ `/ops/0/id` with `id` `zz` (the item is looked up before values are checked).
  - `{id: "c1", text: 5}` gives `bad_arg` with `id` `c1`.
  - With `id` `x1`: `text` = `5` / `1.5` / `true` / `null` / `{}` gives `wrong_type` @ `/ops/0/text`, and `style` = `5` / `false` / `null` / `{}` gives `wrong_type` @ `/ops/0/style`, each with `id` `x1`.
  - The hash is unchanged every time. This matches docs/oplog.md step 6 and PR decisions 4 and 6.
- **House rule (Ada):** an op that needs one of several optional args and gets none returns **`missing_arg` @ `/ops/k`** (no key, no `id`). This is the convention going forward. `set_fade` (still `bad_arg` @ `/ops/k/id`) and the `add_text` value paths (still the doc path) get a **later cleanup**; until then /mcp passes their current shapes through.
- **Code vs docs vs PR body:** no mismatch at `c1bbddb`. The PR reports 742 passed and 52 new tests; I couldn't re-run them here because pytest isn't installed.

### 1g. General /mcp pre-check rule (**RULED: Ada 6:04 PM ET / 18:04, every tool**)
- **Rule:** /mcp checks a field before the engine **only when its check gives the engine's own answer**: the same rule id, path, `id` field (present or absent), and position in the engine's check order. **Everything else goes to the engine as received.** So /mcp and HTTP agents see the same error for the same input. Tool schemas may still *declare* types for clients, but a declared type that isn't reproduced exactly must not be enforced.
- **Unknown args:** a tool schema with enforced `additionalProperties:false` breaks the rule unless /mcp returns the engine's `unknown_arg` at the engine's path (`/<arg>` for tool args, `/ops/k/<arg>` for op args), in the engine's order. The default is not to enforce it and to let the engine answer.
- **Rows that broke it (all resolved by 6:11 PM):**
  1. **`timeline_apply` `group_id: null`:** **FIXED 6:11 PM (Ada).** It passes through to the engine, giving `bad_arg` @ `/group_id` (envelope row, test 69).
  2. **`_s` inputs:** **EXEMPT (Ada 18:11)** as /mcp-only fields, with engine rule ids and JSON Pointer paths: `bad_arg` @ `/ops/k/<arg>_s`, plus the path rewrite for tick rules (tests 65–67, 90).
  3. **Client `schema_version` guard [A]:** **EXEMPT (Ada 18:11)**, using `bad_schema` @ `/schema_version` (Bay; test 57).
  4. **`edit_text` 6:01 PM schema typing** (the removed code with `cause`): **fixed at 6:04 PM** in the §1b row, §1f and test 88.
  5. **Test 87 `_s`-suffixed arg and `text: 5`:** **fixed at 6:04 PM.** Both now get the engine's `unknown_arg` / `wrong_type`.
- **Rows that must stay engine-answered (no /mcp schema constraint allowed):** `ops` 1–500 (engine `bad_arg` @ `/ops`, so no `minItems`/`maxItems`); `base_version` (`bad_arg`); `summary` (checked by the engine, oplog.py L870, so no `minLength`/`maxLength`/NFC check in the schema); the undo/redo `op_id`/`group_id` null or non-string cases (test 78, `bad_arg`); non-string ids in every op (`bad_arg` before lookup); and `actor`/`step`, which the engine itself strips with `ignored_field` (oplog.py L1330, test 70), so /mcp passes them through.
- **Tests:** 88 (`edit_text`) and 89 (every tool).

### 1h. `_s` conversion and the `schema_version` guard: checked at `c1bbddb` (**RULED: Ada 6:11 PM ET / 18:11. APPROVED as written: Ada 18:16, Bay and Glyph agreed**). /mcp rewrites only a tick rule that lands on the converted field; every other error comes back exactly as the engine gives it. The OPEN points below are **closed** that way: no rewrite.
- **(a) `seconds_to_ticks_nearest`** (timeline.py L160–170). Bay's claims hold.
  - `TypeError` for `true`/`false` (bools are checked before the int check), `"1.5"`/`"1"`, `None` and lists.
  - `ValueError` ("seconds must be finite") for NaN, `Infinity` and `-Infinity`.
  - `1e308` is **unchecked**: it returns a 317-digit int tick count.
  - `-0.0` becomes `0` (an int, so the sign is lost).
  - Negatives pass through: `-1` gives −705600000 and `-1.5` gives −1058400000.
  - `1e-12` rounds to `0`.
- **(b) Engine tick rules** (`_Checker.ticks`, L238; `MAX_TICKS = 2**53`, L33). Rule order: `not_integer_ticks`, then **`too_large`** (|v| > 2⁵³), then **`negative_time`** (unless signed), then `empty_range` (positive fields).
  - Over 2⁵³ the rule is **`too_large`**, never `out_of_range`. `out_of_range` comes only from the item-end check (end > 2⁵³, @ the item path, with `id`). It fires at exactly 2⁵³ for `move_clip`/`insert_clip`/`add_text` `at`, `set_anchor` and anchored `dur`.
  - **Only `anchor.offset` allows negatives** (`signed=True`, L485; `set_anchor`/`add_text`/`insert_clip` `offset_s` −1 applies). Every other tick field gives `negative_time`: `at` (marker or item), `dur`, `src[0]`/`src[1]`, `fade_in`/`fade_out`, and transition `dur`.
  - **Paths per op** (−1 / 2⁵³+1):

    | Op and field | −1 | 2⁵³+1 |
    |---|---|---|
    | `add_marker.at` | `/markers/k/at` (id) | doc path (id) |
    | `move_clip.at` | `/ops/0/at` | `T/at` |
    | `split_clip.at` | `/ops/0/at` | `bad_arg` @ `/ops/0/at` (not inside the clip) |
    | `set_fade.fade_in` / `fade_out` | `/ops/0/<field>` | `T/<field>`; at exactly 2⁵³, `fade_too_long` @ `T` |
    | `set_anchor` null + `at` | `/ops/0/at` | `T/at` |
    | `trim_clip.src_in` | `/ops/0/src_in` | **`too_large` @ `T/at`** (the shifted `at`, not `src_in`) |
    | `trim_clip.src_out` | `/ops/0/src_out` | `T/src/1` |
    | `trim_clip.dur` (text) | `/ops/0/dur` | `T/dur`; on a clip, **`bad_arg` @ `/ops/0/id`** for any value |
    | `insert_clip` `at` / `src` / `fade_in` | `/ops/0/at`; the others at the doc path (id) | doc path |
    | `add_text` `at` / `dur` / `fade_out` | `at` at `/ops/0/at`; the others at the doc path | doc path |
    | `add_transition.dur` | doc path | doc path |

    At `1e308` s, every field gives `too_large`, with no crash.
  - **Not quite as Bay put it:**
    1. The engine's answer is often at the **doc path with an item/marker `id`**, not at `/ops/k/<arg>`. The rewrite keeps `id`.
    2. Some answers aren't at the converted field at all: `trim_clip{src_in_s}` over 2⁵³ gives `too_large` @ `T/at`. Non-tick rules triggered by the value (`out_of_range` @ the item at exactly 2⁵³, `fade_too_long`, `empty_range`, `src_out_of_media`, `transition_overlap_mismatch`) aren't tick-rule answers either.

    The contract rewrites only tick rules at the converted field and keeps everything else verbatim. **APPROVED (Ada 18:16; Bay and Glyph agreed).**
- **(j) /mcp arg order for `_s` and raw ticks (APPROVED: Ada 6:40 PM ET / 18:40; S3-SPEC D21, D23)**
  - **Order, per op:**
    1. **Check view.** /mcp takes a copy of the op, drops each `<arg>_s`, and adds a placeholder int `<arg>` **only if the caller didn't send a raw `<arg>`**; a raw value is never overwritten. For `anchor.offset_s`, the copy of `anchor` likewise drops `offset_s` and adds a placeholder `offset` only if there's no raw `offset`.
    2. The engine's **own** op arg check (the shared helper extracted from `_apply_one` L763–771, used by both the engine and /mcp) runs on that view. `unknown_arg`/`missing_arg` come back **unchanged** (engine path `/ops/k/<arg>`, message, `op_index`). **Ada 18:47:** the helper also checks **`anchor`'s keys by name** (allowed `{to, offset}`; both required) when `anchor` is an object, in the engine and in /mcp alike. So an unknown `anchor.zz` or a missing `anchor.to` gets the engine's answer before any `_s` conversion. **APPROVED (D29, Ada 6:56 PM; §11 diff 1; test 97 firm):** `unknown_arg` / `missing_arg` @ `/ops/k/anchor/<key>`, after the op-level arg checks, with no `id` and no `problems`; unknown keys first (sorted), then missing (`offset` before `to`); ahead of that op's `not_found`. A non-object `anchor` (e.g. `null` for `set_anchor`) is left to the op as today.
    3. **Both-sent check:** `<arg>` and `<arg>_s` → `bad_arg` @ `/ops/k/<arg>_s`; `anchor.offset` and `anchor.offset_s` → `bad_arg` @ `/ops/k/anchor/offset_s`.
    4. **Conversion:** a `TypeError`/`ValueError` gives `bad_arg` @ `/ops/k/<arg>_s` (or `/ops/k/anchor/offset_s`).
    5. The engine, then re-pointing (§1h (b)).

    **Envelope first (RULED, Ada 18:56; not an exemption):** before step 1, /mcp runs the engine's own `timeline_apply` envelope check (oplog.py:1115–1119: outer `_check_args` (unknown and missing args, `client_op_id`, `summary`), `group_id: null`, `base_version` type, `ops` shape) through a shared helper, reused, not copied. So envelope errors come first on both paths (test 100).

    **Batch order (named exemption, Ada 18:47; narrowed by the 18:56 envelope ruling):** steps 1–4 run for **every op in the batch, in op order**, before anything reaches the engine. The first /mcp-stage error wins, so a bad `_s` in op 1 is reported ahead of an engine-stage error in op 0 (e.g. `not_found`), and ahead of dedupe (`client_op_id_mismatch`) and `conflict`. It is **not** ahead of the envelope. Within the /mcp stage, op order is kept: an op-0 `unknown_arg` still beats an op-1 bad `_s`. *Wire reading:* each op runs steps 1–4 in turn, rather than all check views first.

    **The old D21 caveat (bad `_s` beating `unknown_arg`) and its exemption are gone.**
  - **Named /mcp-only exemptions (complete list):**
    - **(i) D23 both-sent**, below.
    - **(ii) `trim_clip{dur_s}` on a clip** (Ada 18:47): a bad `dur_s` gives /mcp `bad_arg` @ `/ops/k/dur_s`, while the same op over HTTP with a raw `dur` gives `bad_arg` @ `/ops/k/id` (checked at `c6de84e`: `dur` is only for text and transitions). Conversion runs before the engine's item-type check.
    - **(iii) Batch order** (Ada 18:47), above.
    - The `_s` conversion `bad_arg` and the `schema_version` guard come from the 18:11 exemption.
  - **Named /mcp-only exemption: D23 both-sent.** Raw tick args pass through /mcp to the engine (the engine checks them). Sending both `<arg>` and `<arg>_s` gives `bad_arg` @ `/ops/k/<arg>_s`. The engine has no equivalent answer, so it uses an engine rule id and a JSON Pointer per the 18:11 exemption. It runs **after** the check pass, so `{at, at_s, bogus}` gives `unknown_arg` @ `/ops/k/bogus`.
  - **Checked in Python at `c6de84e`** (`/workspace/tmp/checkview.py`; the view run against the engine's op check, with the first error taken):

    | Op | Answer |
    |---|---|
    | `add_marker{at, at_s, label, bogus}` | `unknown_arg` @ `/ops/0/bogus` |
    | `{at, at_s, label}` | `bad_arg` @ `/ops/0/at_s` |
    | `{at, label}` | applied (raw passthrough) |
    | `{at_s:"x"}` (no `label`) | `missing_arg` @ `/ops/0/label` |
    | `{at_s:"x", label, bogus}` | `unknown_arg` @ `/ops/0/bogus` |
    | `{at_s:"x", label}` | `bad_arg` @ `/ops/0/at_s` |
    | `{label}` (neither) | the engine's `missing_arg` @ `/ops/0/at` |
    | `set_anchor` bad `offset_s` + `bogus` | `unknown_arg` @ `/ops/0/bogus` |
    | `set_anchor` bad `offset_s`, no `id` | `missing_arg` @ `/ops/0/id` |
    | `set_anchor` bad `offset_s` alone | `bad_arg` @ `/ops/0/anchor/offset_s` |
    | `add_text` bad `offset_s`, no `dur` | `missing_arg` @ `/ops/0/dur` |
    | `set_fade{fade_in, fade_in_s, fade_out_s:"x"}` | `bad_arg` @ `/ops/0/fade_in_s` (both-sent comes before conversion) |
  - **Placeholder:** it never trips the check, because the engine's op arg check reads **key names only** (oplog.py L768–771: unknown, then missing), never values. `_check_refs` (L773) only checks id fields.
  - **Caveats (for Bay; behaviour is acceptable under the exemption unless Ada says otherwise):**
    1. **"Reuse `_check_args`" needs an extraction.** `Oplog._check_args` (L857) is the **tool-level** check. On an op view it would flag `op` as `unknown_arg`, use `/<arg>` paths, and then `KeyError` on `client_op_id` (L862). The op-level check is inline in `_apply_one` (L763–771: op shape, `unknown_op`, `unknown_arg`, `missing_arg`), and `_run` adds `/ops/k` + `op_index` (L1013–1022). So S3 should extract L763–771 into one helper that both the engine and /mcp call, with the same `/ops/k` wrapping. This is an engine change for the S3 list.
    2. **CLOSED (Ada 18:47: fixed, not exempted; see step 2 and test 97).** ~~Nested `anchor` keys aren't in the arg check.~~ Old text: A bad `offset_s` plus an unknown nested key (`anchor.zz`) or a missing `anchor.to` gives `bad_arg` @ `/ops/k/anchor/offset_s`. With a valid `offset_s`, the engine answers later at the doc path (`unknown_field` @ `T/anchor/zz`, `missing_field` @ `T/anchor/to`).
    3. **NAMED EXEMPTION (Ada 18:47; test 98).** **`trim_clip{dur_s:"x"}` on a clip** gives `bad_arg` @ `/ops/k/dur_s`. With a valid value, the engine says `bad_arg` @ `/ops/k/id` (`dur` is only for text and transitions).
    4. **NAMED EXEMPTION (Ada 18:47; batch order above; test 99).** **Across a batch:** if /mcp checks and converts every op before calling the engine, op 1's bad `_s` is reported before op 0's engine-stage error (e.g. `not_found`). Arg-name errors still come in op order if the check view runs for every op first.
- **(c) `bad_schema` @ `/schema_version`** exists (timeline.py L70 rule list, raised at L334). It is the validator's first check after `not_object`. It fires when the doc's `schema_version` is missing, isn't a string, or isn't `"hs.timeline/1"`, and it **stops the validator** (with a bad `tick_rate` too, only `bad_schema` is reported). It is a **doc** rule. The engine has no arg-level `schema_version` check: `timeline_apply{schema_version}` gives `unknown_arg` @ `/schema_version`. So the /mcp guard reuses the rule id and pointer, per the exemption.
  - Side note: an extra old field `schema` alongside a valid `schema_version` is `unknown_field` @ `/schema`. It is `bad_schema` only when `schema_version` is missing.
- **`group_id: null`** gives `bad_arg` @ `/group_id` (no `op_index`) at `c1bbddb`.

### 1i. S3-SPEC review (Bay, 6:30 PM, updated 6:34 PM; **spec only, no branch, not pinned**; checked against `c6de84e`)
Verdict key: **CONFIRM** / **CONFIRM + ask** / **BLOCKER** (must be answered before Ada says yes).

**A. Wire's 8 /mcp gaps**
1. **Error mapping: CONFIRM + ask.**
   - §5 row 1 matches mcp.py: engine and tool errors → `isError` (:484–493); `failed` for unexpected exceptions (:486–487); `-32700` (:303), `-32601` (:462) and `-32602` unknown tool (:479) are confirmed.
   - **Not in code today:**
     - `-32600` doesn't exist. A non-object message is silently dropped (:437–438).
     - :467 `params.get("arguments") or {}` turns **any falsy** non-object (`[]`, `""`, `0`, `false`) into `{}`, which contradicts D15 (only missing/`null` → `{}`).
     - `Transport.read` catches only `JSONDecodeError` on the newline path (:300–303; `except` at :302). The LSP path (:299) has no try at all, and a `ValueError` (a >4300-digit number) or `UnicodeDecodeError` escapes `serve()`, so **the stdio server dies**.
   - The spec should list these as S3 fixes.
2. **Warnings closed at `{ignored_field}`: CONFIRM** (§5 row 2; oplog.py:1330).
3. **Undo/redo without `base_version`: CONFIRM** (§5 row 3; `_base_version(required=False)` :919–921, :1144).
4. **Conflict diff: CONFIRM + ask.** §5 row 4 + D10 + D19 define it; the keys match :834. *Ask:* is `history_diff_truncated` **always present** (`false` when not cut) or only when `true`? Is it top-level next to `history_diff`? How should a client fetch the rest (`history_diff{since_version}` paging)?
5. **History paging: CONFIRM + ask** (D19). Today there are no arg checks at all: `history_list("5")`/`(None)` raise `TypeError` once there is an entry, and `-1`, `True` and `1.5` are accepted. *Ask:* D19 must spell out `since_version`: an int ≥ 0, bools refused; above the head → an empty page with a `null` cursor (not `bad_arg`); no upper bound.
6. **`get_hash` with version + hash + seq: CONFIRM** (§5 row 6; new `Oplog.head()` under D3).
7. **`project_id` is the timeline id: CONFIRM** (docs/oplog.md:59–60; oplog.py:881).
8. **`schema_version` guard: CONFIRM** (§5 row 8 + D20: /mcp-only, runs first, `schema_mismatch` `bad_schema` @ `/schema_version`, a matching value stripped; engine `unknown_arg` otherwise at :857).

**B. §1g/§1h and the exemption: CONFIRM + 1 ask** (§6, D21–D23).
- *Ask (D22):* the re-pointing table must cover **every** `_s` arg from the §1h per-op table, not 3 examples. A `T/…` suffix must also match the op's **target or new item** (`id`), not any item.
- **SETTLED (Ada 18:40):** D21 approved with the check view (the caveat is gone), and D23 approved: raw ticks pass through, and both-sent is a named exemption. See §1h (j) and tests 95/96.

  Whole ticks: the helper returns an int (test 91), as §7 states.

**C. C5 replay rules (approved 6:28): CONFIRM.** §4 rules 1–5 match my findings and line refs:
- caching at :1109–1110, replay at :951, `load` rebuilding `[]` at :1241;
- the probe `.out` matches;
- stored warnings never include `ignored_field`; strip warnings come from the current call; stored warnings come first on replay; old lines load with none; no hash or version change; the `warnings` line key is written only when non-empty (`LINE_OPTIONAL`, :56).

Tests 93/94 are mapped (§7).

**D. Bay's bug claims**
- **D17: CONFIRMED.** mcp.py:306 (`Transport.write`) and :488 use `ensure_ascii=False`, then UTF-8 encode, so a lone surrogate in an echoed key or path (e.g. `unknown_arg`) raises `UnicodeEncodeError` and no reply is sent.
  - This doesn't conflict with my note (§0 L298, §1c): that was a **requirement** (`ensure_ascii=True`), not a claim about the code; mcp.py breaks it today.
  - studio.py:123/:249 use the default (`True`), so they're fine.
  - cli.py:95/:100 have the same `ensure_ascii=False` pattern; *ask* to include them.
- **D4: CONFIRMED.** oplog.py:881–888 `id=str(args["project_id"])`: `5` → `not_found` `id:"5"`; also `null` → `id:"None"` and `true` → `id:"True"`. `bad_arg` @ `/project_id` is right. *Ask:* a missing `project_id` at /mcp (D4: required) → `missing_arg` @ `/project_id` (an existing rule; /mcp-only, exempt).

**E. D26 query coercion** (regex `\A(0|[1-9][0-9]*)\Z`, ASCII only; checked in Python):
- `"-1"`, `"007"`, `"+5"`, `" 5"`, `"5 "`, `"5\n"` (`\Z` is strict), `"٣"` and `""` stay strings → engine `bad_arg` @ the param, once D19's checks exist (today: `TypeError`).
- **Huge digit string: ask.** The regex matches, but `int()` raises `ValueError` above 4300 digits (`sys.get_int_max_str_digits()`). The spec must say this passes the raw string (→ engine `bad_arg`), never a 500. At ≤ 4300 digits, `since_version` gives an empty page (no upper bound) and `limit` gives `bad_arg` (above 200/500).
- **/mcp parity: not identical for the same value.** HTTP `"5"` = /mcp `5`; /mcp `"5"` (a JSON string) → `bad_arg`, which HTTP can't send. The same >4300-digit literal over /mcp crashes the stdio reader today (A1). *Ask:* state the HTTP-string ↔ /mcp-int mapping as the parity rule.
- **Glyph's decode case (8:36 PM):** `GET /api/projects/<id>/hash` given the plain id and the POST write route given the **percent-encoded** id must resolve **the same project**.
  - At `0282e9f` they don't agree: GET passes the raw path segment to `ENGINE.get(pid)` (http_engine.py:129–134, no `unquote`), while POST decodes it with `unquote(parts[0])` (http_engine.py:260). An encoded id therefore works on POST and gives `not_found` on GET.
  - **Decode rule (Ada 8:58):** for GET and POST alike, the path is **split on `/` first**, then each segment is percent-decoded. An encoded `/` (`%2F`) therefore stays inside the id and never splits the route.
  - The contract has **no numbered D26 route test**. The build covers D26 in `tests/test_s3_mcp.py:127` (`test_89_history_query_parity`), so this note sits here rather than on a contract row.
- **Repeated param: ask.** `bad_arg` at that path is an HTTP-only check; /mcp has no equivalent, since `json.loads` keeps the **last** duplicate key silently. Prefer: HTTP passes the **list** of raw strings to the engine, which refuses a non-int with `bad_arg` itself (engine-answered, §1g spirit). Document the /mcp duplicate-key behaviour.

**G. Ada 18:47 rulings on the three check-view differences**
- **Anchor keys: the old divergence is CLOSED by the fix.** The shared helper checks `anchor` keys by name in the engine too, so HTTP and /mcp agree, and before `_s` conversion. Today at `c6de84e`, the engine answers these later as validator errors at the doc path, with the item's `id`: `unknown_field` @ `T/anchor/zz`, `missing_field` @ `T/anchor/to` / `T/anchor/offset`, for `set_anchor`, `add_text` and `insert_clip`. *Ask Bay:* fix the rule id, path and order in S3-SPEC. My guess is `unknown_arg`/`missing_arg` @ `/ops/k/anchor/<key>`, no `id`, after the op-level checks.
- **`trim_clip{dur_s}` on a clip** and **batch order** are named exemptions (§1h (j)).

**H. S3-SPEC revision review (6:53 PM; 31 decisions; checked at `c6de84e`)**
1. **D28 (my blocker): CONFIRM, with 3 asks.**
   - **Is `failed` a rule id?** No. It's an **existing error code** (api.py:25 `EXIT`; mcp.py:487), used with **no rule**, like `engine_offline`. That's consistent with "no new rule ids" (17/36). The error table now has a `failed` row.
   - **Is "matches the log head" defined?** Yes: `timeline.json`'s **`hash` and `version`** equal the last log line's `hash`/`new_version` (or `base.json`'s when the log is empty) (D28(a) step 3). `seq` isn't compared; it isn't in the doc.
   - **Test 58:** still covered by D28(a) (read-only closed-app path, O_RDONLY strace) plus `engine_offline`.
   - **Stale base hash** confirmed: `Oplog(base)` with a wrong stored `hash` loads silently (`stamp_hash`, oplog.py:801; timeline.py:684–691); `validate()` gives `hash_mismatch`.
   - **Torn tail vs "corrupt line → `failed`":** torn = the **final** line only, with **no trailing `\n` and not valid JSON** (D2). Today `load` parses the whole file first (`json.loads` per line, :1228), so a torn tail fails the whole load with `JSONDecodeError` (confirmed). Anything else bad, including a bad final line that *has* a newline or is valid JSON, is `failed`.
   - *Ask H1 (closed app vs truncate):* the closed app is read-only (C7), so it can't truncate. It must **skip the torn tail in memory**, and the log head (step 2) is then the previous line. 61(d)'s "truncated on open" applies only to the open app.
   - *Ask H2 (fast path skips the log):* the fast path compares only `timeline.json` with the last line, so a corrupt **middle** line plus a valid cache gives a closed-app read that **succeeds**, while the open app gives `failed`. 61(d) then depends on app state. Either the closed path also checks every line (`_check_line` + sequence, at least), or the spec states this and 61(d) runs open-app only.
   - *Ask H3 (no-newline tail):* a final line that is **valid JSON without `\n`** loads fine today (confirmed). The next append then writes onto the same line, giving a corrupt line on the next load. D2 should add the missing `\n` on open (open app) before any append.
2. **Asks 1–7: CONFIRM.**
   - **D15:** `-32600` for a non-object message; `-32602` for a present non-object `params`/`arguments`, including `null`; the `"arguments" not in params` test. Bay found a 4th case: truthy non-object `params` → `AttributeError`, no reply.
   - **D17** covers cli.py:95/:100.
   - **D19:** an int, not a bool, ≥ 0; no upper bound; empty page above the head; `limit` 1–200 / 1–500; checked in the engine; `history_diff_truncated` always present, at the top level.
   - **D22:** full table, with the target/new-id match. It adds `insert_clip.src_s` (element paths `/ops/k/src_s/<i>`).
   - **D25:** 503 / 202, plus 500 `failed`.
   - **D26:** >4300 digits passes the raw string; a repeated param passes the list to the engine; parity rule stated.
   - **D4:** missing → `missing_arg` @ `/project_id`, as a named exemption.
3. **D21 / D29 / D30 / D31 vs tests 95–99.**
   - **D21:** matches 95/96.
   - **D29: CONFIRM;** test 97 is now firm: `unknown_arg`/`missing_arg` @ `/ops/k/anchor/<key>`, no `id`, no `problems`, unknown keys before missing ones (`offset` before `to`), ahead of same-op `not_found`/`bad_arg`. I confirmed both "before" answers at `c6de84e`. The spec says the shape still needs Ada's OK.
   - **D30:** matches 98.
   - **D31:** matches 99; I added the cached-key subcase.
   - **Inconsistency (ask H4):** D31's prose says the /mcp op stage beats "outer `unknown_arg`, shape, `client_op_id_mismatch`, `base_version`/`conflict`". But D21 step 3b (**RULED: Ada 6:56 PM, envelope reuse, not an exemption**) puts the envelope (outer `_check_args`, `group_id` null, `base_version` type, `ops` shape; L1115–1119) **before** the op stage. Since 3b is ruled, D31 should claim only dedupe and `conflict` (a spec-text fix for Bay).
   - **Also (ask H5):** D21's nested-anchor bullet still says "the engine has no arg-name check inside `anchor` … step 3 runs at the op's top level only". That's stale after D29.
4. **Envelope order: RULED (Ada 6:56 PM): reuse L1115–1119 (D21 step 3b), not an exemption.** Test **100** is firm.
5. **§11: CONFIRM.** The 4 allowed diffs match Ada's 6:49 list. A–H cover everything I flagged: D19 args/shape (A, B), D10 `hash` (C), cap and flag (D), corrupt base (E), corrupt log line + torn tail (F), D4 missing `project_id` (G), D15 protocol answers (H).
   - **D27 input parsing** sits in allowed diff 4 ("output shape") because Ada listed D27 there. It really changes answers (crash → `-32700`); wording only, no new item needed.
   - **The C5 stored-warnings note** is in diff 2 ("always `[]` in S3").
   - **Missing:** nothing found. If H3 is adopted (adding the missing `\n` on open), it's a new engine-side store change and needs a line under F.
6. **Other:**
   - D28's 61(c) open-app rewrite and D2 "rewrite `timeline.json` if its hash differs" agree.
   - D20 (guard on every tool) is still open; test 57 is unchanged until then.
   - No other contradictions with tests 46–100.

**I. Ada 18:56 rulings + what still depends on Bay's next S3-SPEC revision** (the file on disk is unchanged since 18:52)
- **Ruled:** §11 = 12 allowed diffs (row 4 "parses input differently"); D29 approved (test 97 firm); envelope reuse before the /mcp op stage, not an exemption (test 100 firm). D27 (a) and (b) are accepted by Bay (tests 101, 102).
- **Needs Bay's revision (the spec on disk doesn't reflect it yet):**
  1. §11: **done in Bay's 7:21 revision**: 12 rows (1–4 + A–H), row 4 reads "parses input differently".
  2. D29: **approved by Ada at 6:56 PM** (§11 diff 1). Bay's 7:21 revision text now matches (no "pending" left in S3-SPEC).
  3. D21 step 3b: **ruled by Ada at 6:56 PM** (envelope reuse). Bay's 7:21 revision text now matches (no "pending" left in S3-SPEC). D31's prose must drop the outer `unknown_arg`/shape/`base_version` claims (ask H4).
  4. **D27 (a)/(b): CARRIED in Bay's 7:21 revision** (drain/close/header check/duplicates/HTTP close all match; diffs in the 7:24 log). Was: in the 19:00 spec. The cap is ruled (Ada 7:03: `MAX_BODY` 1048576, inclusive). Drain ≤ 16 MiB with answer-first (Ada 7:09), and close on over-cap or malformed with no scanning (Ada 7:09/7:14), are **ruled** (§1i J). The spec text awaits Bay's revision.
  5. **ANSWERED in Bay's 7:21 revision:**
     - H1: a closed app skips a torn tail in memory (§11 F).
     - H2: the fast path vs a corrupt middle line is a known gap (Ada 7:18, finding 8, 61(d)).
     - H3: the open engine writes the missing `\n` (fsynced), and it's listed under §11 F.
     - H5: the nested-anchor bullet in D21 now matches D29.
- **D15 has no contract test yet.** I'll add one once Bay's revision lands, if wanted (§11 diff 12).

**J. Cap, drain and close (Ada 7:03 + 7:09)** (S3-SPEC on disk is the 19:00 version; Bay's next revision is on hold while Bay asks Pablo something)
1. **HTTP keep-alive desync: RULED, fixed (Ada 7:09; test 103).** At `c6de84e`, `_read_json` refuses over-cap or negative lengths without reading the body, and the HTTP/1.1 handler (studio.py:236) keeps the connection open, so the body ran as the next request.
   - **Reproduced:** `/api/doctor` returned 200 after the 400.
   - A non-integer length is read as 0 (studio.py:149–151).
   - **Ruling:** close the connection on every refusal (over-cap, negative, non-integer). Status and body are unchanged.
2. **Drain bound: RULED (Ada 7:09).** Drain only for a well-formed length ≤ 16 × `MAX_BODY` = 16777216, with `-32700` sent **first**.
   - Above that, or a digit run longer than 8 (no `int()`, so the 4300-digit limit can't trigger), the stream is broken: `-32700` `id:null`, logged, then the session closes with a nonzero exit.
   - Residual: the drain is bounded in bytes, not time. A peer that declares 16777216 and stalls holds the session until it sends or closes, and only that session.
   - **Edge:** a 9-digit run with leading zeros (`000000007`) also closes, because the rule counts digits, not value (test 101 (6)). That's consistent with the ruling, and noted.
3. **APPROVED (Ada 7:14 PM ET):** a malformed `Content-Length` (`-1`, `+5`, `1_000`, non-digit) closes the session exactly like over-cap: `-32700` `id:null`, a log line, nonzero exit. **Nothing on stdio skips ahead by scanning.** This supersedes the 6:56 "(b) resync" reading. Tests 101 (7) and 102 (a) are firm. The "once in `Content-Length` mode, stays in it" part (Prove/Bay) wasn't named in the 7:14 ruling; **Ada approved it at 7:15–7:20**, so 102(c) is firm.
   - **7:14 PM ET:** pending removed from 101 (7) and 102 (a). The answer-first ordering (101 (3)/(4)) was already covered by Ada's 7:09 drain ruling ("answered with `-32700` first, then drained"), so it carries no pending marker. **The known limit on too-short lengths stands** (item 4).
4. **102(c) verdict: "never runs" can't be asserted for every too-short length.**
   - Checked against mcp.py at `c6de84e`: `Content-Length: 2` + `{}` followed by `Content-Length: 40\r\n\r\n{call}` is **byte-identical to two legitimate frames**, and `Transport.read` returns `{}` and then the call. No framing rule can tell it from a real client.
   - What can be asserted: leftover bytes that **don't** form a valid header (e.g. `Content-Length: 5` + `{"a":1}`, leaving `1}Content-Length: …` on a non-header line) cause the broken-stream close.
   - At `c6de84e` that input instead raised `JSONDecodeError`, killing the server.
5. **CLOSED by Bay's 7:21 revision** (D27 (b)–(d), §11 row 4). Was: **the spec on disk (19:00) was out of date.** It still has over-cap → skip-ahead resync, and HTTP over-cap → the `-32700` body for all routes. Bay's revision must carry the 7:09 ruling: drain ≤ 16 MiB, close above it, HTTP close-on-refusal, REST body unchanged, HTTP /mcp `-32700`.
6. **HTTP header check + duplicates (Ada 7:15–7:20).** HTTP uses the stdio check: `re.fullmatch(rb"[0-9]+")` + the 8-digit cutoff, exactly one header (`get_all`). A failure gets 400 "invalid content length" + close; a well-formed over-cap length keeps "too large".
   - *Implementation note:* `BaseHTTPRequestHandler` gives header values as Latin-1 `str` with leading whitespace already stripped, but **trailing** spaces kept (`Content-Length:  5 ` → `"5 "`, checked). Strip spaces and tabs and `.encode("latin-1")` before `re.fullmatch(rb…)`, or a legitimate padded value is refused.
   - **Residual:** a missing `Content-Length` stays 0 (unchanged, test 103 (iv)). A body sent without one (e.g. chunked) is still left unread on the connection.
7. Accepted is exactly 1048576 (`length > limit`, studio.py:152; confirmed on HTTP). Stdio must import `MAX_BODY` from studio.py, not copy it.

**F. Contradictions / tests without a spec answer****F. Contradictions / tests without a spec answer**
1. **RESOLVED IN PRINCIPLE by S3-SPEC D28 (6:53; asks in H):** ~~BLOCKER: tests 61/62 vs D1/D2.~~ The tests expect a corrupt stored `timeline.json` (bad `schema_version`, stale `hash`, duplicate ids) to give `schema_mismatch`/`invalid_doc` with no hash. D1/D2 make `timeline.json` a cache that's rewritten on open. The spec doesn't say what closed-app reads (§2 "reads work", test 58) read: `timeline.json` or a replay of `base.json` + log. Nor does it say which error a bad `base.json` / bad log line gives over MCP (`load` raises `ValueError`, :1228–1235). Needs an answer, and then I re-target 61/62.
2. **Test 50 vs D19: SETTLED (Ada 18:40).** `history_list` returns raw ticks, the same exemption as `get_timeline`. Test 50 is updated.
3. **D25** has no status code for `engine_offline` (suggest 503) or `needs_approval` (S8; suggest 202). *Ask.*
4. **D8 `project_status`: APPROVED (Ada 7:15–7:20),** on the C9 allowlist (test 60); §1a row added.
5. **D20:** the guard on *read* tools too. Test 57 only covers writes; I'll extend it once D20 is approved.
6. **No conflicts found** with tests 63–67, 69, 70, 76, 87–94.
7. **RULED (Ada 18:56): reuse the envelope check (L1115–1119) before the /mcp op stage; not an exemption (test 100, firm).** Envelope vs the /mcp stage (18:48). S3-SPEC D21 step 3b recommends the reuse (test 100). Wire recommends reusing the engine's envelope check before /mcp's op stage. The engine checks the `timeline_apply` envelope before any op: tool-level `_check_args` L1115 (unknown/missing tool args, `client_op_id`, `summary`), `group_id: null`, `base_version` type and `ops` shape (L1115–1119). If /mcp converts first, `{summary: ""}` + a bad `at_s` gives /mcp `bad_arg` @ `/ops/0/at_s` but HTTP `bad_arg` @ `/summary` (engine checked at `c6de84e`). *Ask Ada/Bay:* run the engine's envelope checks (reused) before the /mcp op stage, or list this as a fourth named exemption.
8. **CLOSED (Ada 18:56: §11 = 12 allowed diffs, §3 gate 6).** Prove's byte-identical gate (18:48 → widened by Ada 18:49). The allowed list is now: the anchor check, C5 replay warnings, D4, D17/D27. **OPEN (posted 6:51 PM):** D10, D19 and D2 aren't on it yet.
9. **APPROVED (Ada 7:15–7:20): per op.** Matches S3-SPEC D31 / D21 "per op, in op order": the per-op batch-order reading (§1h (j) batch order): each op runs check view → both-sent → conversion in turn, rather than all check views first. S3-SPEC's current full /mcp order (step 4, "per op, in op order") matches this reading.

**Asks to post (Wire → Bay, cc Ada/Glyph):**
1. **Answered: D15 + D27.** A1: add `-32600` (non-object message), fix :467's falsy coercion, catch `ValueError` and decode errors in both read paths (→ `-32700`) as S3 fixes.
2. **Answered: D17.** D17: also cover cli.py:95/:100.
3. **Answered: D19.** D19: `since_version` typing, bounds and above-head behaviour; `history_diff_truncated` presence and placement.
4. **Answered: D22.** D22: the full re-pointing table (all `_s` args) + the target-id match.
5. ~~Ada: explicit OK for the D21 caveat and D23 raw ticks at /mcp.~~ **SETTLED (Ada 18:40):** D21 check view + D23; §1h (j).
6. **Answered: D26.** D26: >4300-digit strings pass raw (no 500); a repeated param passes the list to the engine; state the parity rule.
7. **Answered: D4 (named exemption).** D4: missing `project_id` at /mcp → `missing_arg` @ `/project_id`.
8. **Answered: D28 (3 follow-up asks in H).** ~~Blocker:~~ closed-app read source and corrupt-store errors (tests 58/61/62).
9. **Answered: D25** (503 / 202, plus 500 `failed`). D25: status codes for `engine_offline` / `needs_approval`.
10. ~~Test 50: is `history_list` raw?~~ **SETTLED (Ada 18:40):** raw, like `get_timeline`.

**Gaps in `docs/oplog.md` that /mcp needs:**
- **Error codes** (→ S3-SPEC §5 row 1; see §1i A1): no mapping to MCP error codes or exit codes is documented (`_EXIT_AS`, L99, maps `invalid_op` to `bad_input`, and `conflict`/`undo_blocked` to `failed`). `needs_approval`, `engine_offline` and `permission_denied` are left to Wire, which is expected.
- **The `warnings[]` shape** (→ S3-SPEC §5 row 2: **closed at `{ignored_field}`**): only `ignored_field` is defined. There's no list of other warning codes.
- **Versions:**
  - (→ S3-SPEC §5 row 3, SETTLED: acts on the current version, oplog.py:919–921, :1144) `base_version` is required for `timeline_apply` and optional for undo/redo. The doc doesn't say what an undo without one means (it applies to the current version).
  - (→ S3-SPEC §5 row 4 + D10 + D19) The `conflict` `history_diff` record shape isn't spelled out in the Errors table (it's `history_diff`'s keep-list, L659–660).
- **`history_list` / `history_diff`** (→ S3-SPEC D19 + D26): and no output schema or pagination. `since_version` is the only filter.
- **Read results** (→ S3-SPEC §5 row 6: `get_hash` = `{project_id, schema_version, version, hash, seq}` via `Oplog.head()`): `version` + `hash` together. /mcp's `get_hash` builds that from `doc`.
- **`project_id`** (→ S3-SPEC §5 row 7, SETTLED: the timeline `id`; typing in D4): (L703–705). The doc doesn't say this is the timeline `id` and not a store path.

---

## 2. /mcp contract-test outline

**How the tests run:**
- **At Slice 1** there's no `/mcp` yet. The S1 tests import `validate()`, `validate_or_raise()`, `canonical_hash()`, `stamp_hash()`, `to_otio()`, `seconds_to_ticks()`, `seconds_to_ticks_nearest()`, `ticks_to_seconds()` and `ticks_per_frame()` from `hermes_studio.timeline`, and run them on fixture docs under `tests/fixtures/timeline/` (the folder name is a proposal). Every fixture uses integer ticks.
- **Once `/mcp` lands (my PR, on S3)**, the same fixtures run again through `validate_timeline`, `get_timeline` and `timeline_apply`.

**How to read the results:**
- **Assertions check `rule` + `path` (+ `id` where one is expected) only, never message text.** Rule ids and paths come from `5e3e639`.
- **Paths are RFC 6901 JSON Pointers.** `T` stands for the `/tracks/<i>/items/<j>` pointer of the item under test.
- **id=x** means the problem carries `id: "x"`. **no id** means the `id` key is absent. Fixture ids are well-formed and unique unless the test says otherwise, so item and marker problems carry `id`.
- **Blanket `id` check (on every test, S1 and MCP), doc problems only:** this covers `validate()` problems, `invalid_doc`, and `invalid_op` validator failures plus their `problems`. It doesn't cover `not_found` or `undo_blocked`, whose `id` is a missing id, an op_id or a group_id. Whenever a doc problem has `id`, exactly one item or marker in the doc has that well-formed id, and `path` equals its pointer or starts with that pointer plus `/` (compared segment by segment, so `/tracks/1/items/1` doesn't match `/tracks/1/items/10`). `bad_id` and `duplicate_id` problems never have `id`.
- **valid** means `validate(doc) == []`. **rejected `rule` @ `path`** means `validate(doc)` contains exactly that problem, and `validate_or_raise()` raises `TimelineError` with that `.rule`/`.path`/`.id`.
- **One fault per fixture,** because the validator is staged (§0).
- **When:** S1 = runs against Bay's Slice 1 head. S2/S3/S8 = needs that slice. "+W" = also needs my registry/`/mcp` PR.

### Runs at Slice 1 (tests 1–45)

| # | Input | Expected | Rule exercised |
|---|---|---|---|
| 1 | Minimal valid doc: tracks `T1` text, `V1` main, `A1` voice, `A2` music (in that order); 2 V1 clips, 1 text, 1 marker; `tick_rate` 705600000; `fps` `[30000, 1001]`; `size`; media `m1` with `fps` `[30000, 1001]` | valid; `canonical_hash` matches `sha256:[0-9a-f]{64}` | baseline |
| 2 | A track with no `role` | `missing_field` @ `/tracks/0/role`, no id | role required |
| 3 | A track with `role:"overlay"`, `"broll"`, and the non-strings `[]`, `{}`, `["main"]`, `1`, `null`, `true` | `bad_track_role` @ `/tracks/0/role`, no id, never an exception | role in the allowed set (no overlay) |
| 4 | No `main` track | `missing_main_track` @ `/tracks`, no id | exactly one main |
| 5 | A `main` track with id `V2`; V1 with role `voice`; a second track with id `V1` | `bad_track_id` @ `/tracks/<k>/id`; `bad_track_id` @ `/tracks/<k>/id`; `duplicate_id` @ `/tracks/<k>` (the second V1). All with no id | exactly one main (no dedicated rule) |
| 6 | A text item with `anchor{to:"c1", offset:352800000}` and no `at`, where c1 is on V1; the same with a negative offset that keeps the start ≥ 0 | valid | anchor from `text` ok; offset may be negative |
| 7 | A music clip on `A2` anchored to a V1 clip | valid | anchor from `music` ok |
| 8 | An anchor with `to:"nope"` | `anchor_target_missing` @ `T/anchor/to`, id = the anchored item | anchor → missing clip |
| 9 | An anchor whose `to` is a clip on the voice track `A1` | `anchor_target_not_main` @ `T/anchor/to`, id = the anchored item | target must be a V1 clip |
| 10 | A clip on the voice track `A1` with `anchor` instead of `at` | `anchor_not_allowed` @ `T/anchor`, id = that clip | anchor only from text/music |
| 11 | (a) a V1 clip with `anchor` instead of `at`; (b) a transition with an `anchor` key; (c) a marker with an `anchor` key | (a) `anchor_not_allowed` @ `T/anchor`; (b) `unknown_field` @ `T/anchor`; (c) `unknown_field` @ `/markers/0/anchor`, id = the marker | anchor only from text/music; strict shapes |
| 12 | A clip with fades of 352800000 ticks each (0.5 s), duration 4 s; a text item with the same fades | valid | fades ok (clips and text) |
| 13 | `fade_in: -1` | `negative_time` @ `T/fade_in`, id = the item | fade ≥ 0 |
| 14 | `fade_in + fade_out` = duration, then = duration + 1 tick; repeated at speed `[2, 1]` (duration = `(out − in)/2`) | valid, then `fade_too_long` @ `T` | sum ≤ duration (speed counts) |
| 15 | A clip with no `fade_out`; an item with no `id`; an item with no `type` | `missing_field` @ `T/fade_out` (with id); `missing_field` @ `T/id` (no id); `missing_field` @ `T/type`. **Not `wrong_type`** (`86211b5`) | fades required |
| 16 | V1 clips at 0–4 s and 6–9 s (in ticks) | valid; `to_otio()` has a `Gap` of exactly 1411200000 ticks | gaps implied by `at` |
| 17 | An item with `type:"gap"` | `wrong_type` @ `T/type` | no gap object |
| 18 | (a) The same id `c9` on items in two different tracks; (b) three copies of `c9` (a V1 item, an A1 item, a marker); (c) copy (a), plus a `fade_too_long` on the second `c9`; (d) an item with malformed id `c 9` plus a `fade_too_long`; (e) a normal item with a `fade_too_long` | (a) `duplicate_id` @ the second copy's pointer, **no id**, message contains `'c9'`; (b) exactly **two** `duplicate_id`, @ the A1 item and @ `/markers/<k>`, no id; (c) `fade_too_long` @ that item's pointer, **no id**; (d) `bad_id` @ `T/id` and `fade_too_long` @ `T`, both **no id**; (e) `fade_too_long` with id | ids unique across the doc; `id` only when it names exactly one valid item |
| 19 | A marker id equal to an item id; a media id equal to a track id | `duplicate_id` @ `/markers/0`, and @ the later track's pointer; both **no id** | ids unique across the whole doc |
| 20 | A piece with `split_from:"c1"`; a piece without it; a piece whose `split_from` is its own id | valid; valid; `bad_split_from` @ `T/split_from` | `split_from` optional, not self |
| 21 | A marker missing `label`; a marker with `at:-1` | `missing_field` @ `/markers/0/label`; `negative_time` @ `/markers/0/at`; both with the marker's id | marker `{id,at,label}` |
| 22 | An unknown field at the top level. Python API only: a non-string key `1` among string keys at the top level, and in the `media` map | `unknown_field` @ `/foo`, no id; `unknown_field` @ `/1`, no exception; `wrong_type` @ `/media/1` | unknown fields rejected |
| 23 | An unknown field on a track | `unknown_field` @ `/tracks/0/foo`, no id | ″ |
| 24 | An item with `foo`; an item with `author` (also `actor`, `created_by`, `modified_by`, `user`, `owner`); `owner` at the top level | `unknown_field` @ `T/foo`; `attribution_field` @ `T/author` (with the item's id); `attribution_field` @ `/owner` (no id) | ″ + no author fields anywhere |
| 25 | An unknown field on a marker, and on a media entry; media keys `m.1` (valid), `m/1` and `m~1` | `unknown_field` @ `/markers/0/foo` (with id), and @ `/media/m1/foo` (no id); `m.1` valid; `bad_id` @ `/media/m~11` and @ `/media/m~01` | ″ + pointer escaping |
| 26 | Floats in the doc: `at: 1.5`, `fade_in: 0.0`, `dur: true`. The 2⁵³ cap: `at: 2⁵³+1`; a clip ending at exactly 2⁵³; one ending at 2⁵³+1; an anchored text whose resolved end is 2⁵³+1; `src` at speed `[1,10]` with `(out−in)×10 > 2⁵³`; `version: 2⁵³+1`; `volume: [2⁵³+1, 2⁵³]` | `not_integer_ticks` @ that pointer. Then: `too_large` @ `T/at`; valid; `out_of_range` @ `T` (with id); `out_of_range` @ `T` (with id); `out_of_range` @ `T/src`; `out_of_range` @ `/version`; `out_of_range` @ `T/props/volume` | integer ticks only |
| 27 | `tick_rate` missing; `1000`; `705600000.0` | `bad_tick_rate` @ `/tick_rate` (all three), no id | `tick_rate` required and fixed |
| 28 | Each rate: `[24000,1001]`, 24, 25, `[30000,1001]`, 30, 60 fps and 48000 Hz | `ticks_per_frame(rate)` returns an int (29429400, 29400000, 28224000, 23520000, 23520000, 11760000, 14700); `frames_to_ticks(k, rate)` = `k × ticks_per_frame` | every rate is whole ticks |
| 29 | `seconds_to_ticks(0.1 + 0.2)`, `seconds_to_ticks(0.3)`, `seconds_to_ticks("0.3")`; `seconds_to_ticks_nearest(0.1 + 0.2)`; `seconds_to_ticks_nearest(-0.5)`; `seconds_to_ticks_nearest` on `True`, `"1"`, `None`, `float("nan")`, `float("inf")`, `Decimal("NaN")`; strict `seconds_to_ticks(Fraction(1, 1411200000))` (half a tick) | all equal `211680000`; `(211680000, Fraction(3, 10))`; `(-352800000, Fraction(-1, 2))`; `TypeError` ×3, then `ValueError` ×3; `ValueError` | float input → one exact tick |
| 30 | For sample ticks up to 24 h: `seconds_to_ticks_nearest(float(ticks_to_seconds(t)))[0]` | `== t`; `ticks_to_seconds` returns a `Fraction` | helper round trip (the tool contract relies on it) |
| 31 | A marker `label` and a text `text` written as `"e\u0301"` (not NFC); a marker `label` with a lone surrogate `"\ud800"` (→ `wrong_type` @ `/markers/0/label`, id = the marker) | `not_nfc` @ `/markers/0/label` (id = the marker), and @ `T/text` (id = the text item) | NFC strings |
| 32 | Two docs with equal content built separately; a clip with no `props` vs one with explicit default `props` | equal hash; equal hash | equal content → equal hash |
| 33 | The same doc with its keys shuffled | equal hash | key-order invariance |
| 34 | The same doc with each track's items and the marker list permuted (track order unchanged); separately, `A1` and `A2` swapped | equal hash; the swap gives `track_order` @ `/tracks`, no id | items sort by (resolved start, id), markers by (at, id); track order is meaningful |
| 35 | The same doc with `version` 3 vs 9; with no `hash` vs the `hash` from `stamp_hash()` | equal hash; both valid | `version` and `hash` not hashed |
| 36 | One `at` moved by 1 tick (into a gap) | different hash | hash sensitivity |
| 37 | `schema_version: "hs.timeline/2"`, plus every rejection fixture from tests 2–27, 31, 38, 40–45 | `canonical_hash()` and `canonical_json()` **raise** `TimelineError` (code `bad_input`) with `.problems == validate(doc)`; never a hash | invalid docs never hash |
| 38 | `schema_version` missing; `"hs.timeline/999"`; `1`; the old field `schema` used instead | `bad_schema` @ `/schema_version`, no id; over MCP, `schema_mismatch` | version gate |
| 39 | `to_otio()` on #1; `to_otio()` on an invalid doc | an OTIO `Timeline` with every `RationalTime` = `(doc ticks, 705600000)`, stack markers, and `from_otio(to_otio(doc)) == normalize(doc)`; the invalid doc raises `TimelineError`. Python API only, never `otiotool --stats` or `--list-markers` | OTIO mapping (Prove C1) |
| 40 | Top-level `fps` missing; `30`; `[30.0, 1]`; `[60, 2]`; `[30, 0]`; `[0, 1]`; `[11, 1]`; `[2⁵³+1, 1]` (→ `out_of_range` @ `/fps`); media `fps: [2⁶³, 1]` (→ `out_of_range` @ `/media/m1/fps`). Also valid docs with `fps` `[30,1]` vs `[25,1]`. Media: `fps: null` valid; the `fps` key missing; `fps: [11, 1]` | `missing_field` / `bad_rational` ×4 / `out_of_range` / `bad_fps`, all @ `/fps`, no id; the two valid docs hash differently. Media: valid; `missing_field` @ `/media/m1/fps`; valid | `fps` required, whole-tick frames, in the hash; media `fps` key required, value nullable |
| 41 | A stored `hash` with one hex digit changed (the doc is otherwise valid) | `hash_mismatch` @ `/hash`, no id, from `validate()`; **`canonical_hash()` and `canonical_json()` raise**; `stamp_hash()` returns a corrected copy whose hash validates; `stamp_hash()` on a doc with any other fault still raises | stored hash must match; only `stamp_hash` skips the check |
| 42 | A text item with both `at` and `anchor`; a clip with neither | `at_and_anchor` @ `T`, id = the item (both cases) | exactly one of `at`/`anchor`. **Tool boundary:** `set_anchor` must swap `at` ↔ `anchor` in one op |
| 43 | A text anchored to c1 (`at` = 1 s) with offset −2 s; then offset −1 s exactly | `anchor_before_zero` @ `T/anchor`, id = the text; then valid (start = 0) | resolved start ≥ 0. **Tool boundary:** a `move_clip` of c1 toward 0 can make its anchored items invalid (test 52) |
| 44 | Two V1 clips overlapping by 1 tick, no transition; the same on voice track `A1`; the same on music `A2` and on `T1`; V1 clips joined by an xfade whose `dur` = the overlap, then `dur` = overlap − 1 | `overlap` @ the later item's pointer, id = the later item (V1 and A1); valid (A2, T1); valid; `transition_overlap_mismatch` @ `T/dur` (id = the transition) | overlap rules. **Tool boundary:** `insert_clip`/`move_clip` that collide return `invalid_op` with `overlap` |
| 45 | A clip at speed `[3, 1]` whose `src` length isn't divisible by 3; the same length at speed `[1, 1]` | `non_integer_duration` @ `T/src`, id = the clip; valid | whole-tick duration at speed. **Tool boundary:** `split_clip`/`trim_clip` with `at_s` at speed ≠ 1 return `invalid_op` with this rule, never a re-rounded tick |

### Needs a later slice (tests 46–103)

| # | Input | Expected | Rule exercised | When |
|---|---|---|---|---|
| 46 | Over `/mcp`: `validate_timeline` with a non-NFC marker label; `add_marker{label:"e\u0301"}` | `invalid_doc` / `invalid_op` with top-level `rule:"not_nfc"`, `path:"/markers/0/label"`, **`id`: the marker's id** (present because that id is well-formed and unique), and the same `{rule, path, message, id}` entry in `problems`, all byte-identical to `validate(doc)` / `TimelineError.as_dict()`. Also: a media-level fault (`bad_id` @ `/media/m~11`) comes back with **no `id` key**. Nothing applied | NFC + `rule`/`path`/`id` passthrough (`id` present only for items and markers) | S3+W (write: S2) |
| 47 | `get_timeline` vs `canonical_hash(timeline.json on disk)` vs `get_hash` vs `export_otio`'s `timeline_hash` | all four hashes are equal; the returned doc is in ticks and has no floats; `export_otio`'s `path` is inside the project's `exports/` and opens in `opentimelineio` (Wire decision) | `get_timeline` = raw doc | S3+W |
| 48 | Read a clip's `at.seconds` from the summary and a marker's from `list_markers`, then `move_clip{at_s}` / `add_marker{at_s}` with those values | the resulting ticks are identical to what was read | read-then-write round trip | S2+S3+W |
| 49 | `add_marker{at_s: 0.1+0.2}` vs `{at_s: 0.3}` | both store `211680000` (one `seconds_to_ticks_nearest` call); no extra rounding in the tool layer | one conversion only | S2+S3+W |
| 50 | Check the output schemas of every registry entry | every time field is `{ticks, seconds}` and `tick_rate` is present. **Exempt (raw ticks, exactly as stored): `get_timeline` (raw doc) and `history_list` (full log lines whose `ops`/`inverse` hold raw ticks; Ada 18:40)** | output contract | S3+W |
| 51 | `split_clip`, then `get_timeline`, then undo | 2 pieces with unique ids and `split_from`; undo gives back the pre-split hash | split + undo | S2 |
| 52 | `set_fade` making the sum > duration; `set_anchor` to a voice clip; `move_clip` of c1 that pushes an item anchored to it below 0 | `invalid_op` with `fade_too_long` / `anchor_target_not_main` / `anchor_before_zero`, with its pointer and `id` (for the last one, the **anchored** item's id, not c1's; present only because that id is unique and well-formed); hash unchanged | the validator runs after the op | S2 |
| 53 | `delete_clip` on a clip with an anchored text; undo; redo; `delete_clip{id:"zz"}` | the anchored items become an absolute `at` at the same start in the same entry, and their ids are in `changed_ids`. Undo re-anchors them, and undo and redo report the same `changed_ids`. Never an `anchor_target_missing` doc. Unknown id: `not_found` @ `/ops/0/id`, `id: "zz"`, `op_index` 0 | anchor integrity on delete; not_found shape | S2 |
| 54 | Agent `history_undo{op_id}` of a human's op; a human undoing an agent's op | `undo_blocked`, `reason:"actor"`, `op_ids` = [the human's op_id] (the entries owned by another actor), `path:"/op_id"`, `id` = that op_id, **no `blocking_op_ids`**; hash unchanged. The human's undo is applied | actor rule (C5); shared `undo_blocked` shape | S2 |
| 55 | `history_list` after a human op, an agent op with plan step 3, and an agent op with no plan step | actors are `{kind,id}` from the session. `step: 3` only on the agent op with a plan step. **No `run_id` key on any entry** | authorship from the log | S2 |
| 56 | Retry with the same `client_op_id` | same `op_id`, applied once | dedupe (C5) | S2 |
| 57 | A write carrying a stale `schema_version` (`"hs.timeline/2"`, `1`, `null`); then one carrying `"hs.timeline/1"` | `schema_mismatch` with rule **`bad_schema` @ `/schema_version`**, `expected`/`got`; nothing applied, and the engine is never called. The matching value is stripped and the write applies (never the engine's `unknown_arg` @ `/schema_version`) | client guard **[A]**, using the engine rule id (Ada 18:11, Bay) | S3+W |
| 58 | App closed: stdio `get_timeline`, then `add_marker` | the read works, served by the **read-only closed-app path (S3-SPEC D28(a))**: `timeline.json` if it validates and its `hash` + `version` equal the log head, otherwise a replay of `base.json` + log. The write and `export_otio` give `engine_offline`. strace shows only `O_RDONLY` opens of `base.json`, `oplog.jsonl`, `timeline.json` and `snapshots/`, with no write opens (C7) | app-closed rule | S3 |
| 59 | Propose mode: `add_marker` | `needs_approval` + `pending_id`; hash unchanged, nothing logged; still parked after a timeout; Apply → applied once; repeating the `pending_id` → no-op | Propose park (E5) | **S8** (written now, expected to fail until then) |
| 60 | Generate the plugin and CLI from the registry, then diff against `tools/list` | identical names and input schemas; no `publish\|upload\|post\|shell\|exec`. The C9 allowlist includes **`project_status`** (D8, approved by Ada 7:15–7:20) | generated plugin = registry (C9) | S3+W |
| 61 | **Re-targeted per S3-SPEC D28(b).** (a) unknown `schema_version` and (b) a stale stored `hash`, each written into **`base.json`** (empty log). (c) the same faults written into **`timeline.json` only** (base and log intact). (d) a corrupt **middle** log line (bad `hash`, unknown key, bad JSON), and separately a torn **final** line. Each case: MCP `get_hash`, `get_timeline`, `export_otio`, with the app open and closed | (a) `schema_mismatch` `bad_schema` @ `/schema_version`. (b) `invalid_doc` `hash_mismatch` @ `/hash`, **no `id`**, `rule`/`path`/`problems` verbatim; the store must `validate()` `base.json` before `Oplog`, because `Oplog.__init__` re-stamps (oplog.py:801 `stamp_hash`; confirmed: a stale-hash base loads silently today). No `hash`/`timeline_hash` in any response, no `.otio` written. (c) **succeeds**, with the hash of the log head; the closed app writes nothing, and the open app rewrites the file on open. (d) middle line: **`failed`** with `seq`, no hash, writes refused. **Finding 8 (known gap, Ada 7:15–7:20):** a middle line whose stored `hash` was edited (valid JSON and shape) is caught **only by a full replay** ("replay does not reproduce the entry", oplog.py:1234–1235), so this case runs with the **app open**. The closed-app fast path (cache valid + head match) can serve it (§1i H2). **F1 (Ada 8:58), tampered `inverse` on a middle line:** a 5-line log whose seq 2 `inverse` was edited (hash and version left intact) gets **`failed` with `seq: 2`**, both with the app **open** and **closed**. `doc_at_head` uses the same per-line check as `Oplog.load` (which compares `inverse`), and the code never falls back to the last line's seq. Before (`0282e9f`): open → `failed` `seq: 5` (`project.py:465–469` falls back to `len(lines)`); closed → the doc is served (`_replay_from`, project.py:233–246, compares only `hash`/`new_version` at :241). `c6de84e`'s `Oplog.load` refused it as line 2. **O2 (RULED, Ada 8:59):** a `base.json` with **no `hash` key** gets **`invalid_doc` `hash_mismatch` @ `/hash`**, the same answer as a stale hash, with the app **open** and **closed**. Only a `base.json` that can't be read or isn't JSON gets `failed`. Before (`0282e9f`): the file was accepted (project.py:171 `read_base`). Torn final line: the open app truncates it on open (D2) and reads succeed; the closed app must skip it **in memory** without writing (§1i H ask 1) | invalid stores never hash; caches never error | S3+W |
| 62 | Over `/mcp`: `validate_timeline` with a doc holding three copies of id `c9` (a V1 clip, an A1 clip, a marker); then the same doc stored as **`base.json`** (empty log; re-targeted per S3-SPEC D28(b)) and read with `get_timeline` | `invalid_doc`. The top level and every `problems` entry have **no `id` key**. Exactly two `duplicate_id` entries, whose `path`s are the 2nd and 3rd copies' pointers (`/tracks/<A1>/items/<j>` and `/markers/<k>`), never the first copy's. The messages quote `'c9'`. Byte-identical to `validate(doc)`; no hash returned. The same doc in `timeline.json` only is a 61(c) success case | `id` only when it names exactly one valid item, at the MCP boundary | S3+W |
| 63 | `add_marker{at_s: 1/3}` (JSON `0.3333333333333333`); `add_marker{at_s: 1/11}` (`0.09090909090909091`) | applied. `used.at_s` = `{ticks: 235200000, seconds: 0.3333333333333333}`; then `{ticks: 64145455, seconds: float(Fraction(64145455, 705600000))}`, where the echoed seconds differ from the input. The stored marker `at` = `used.at_s.ticks` | rounds once; echoes the value used | S2+S3+W |
| 64 | `add_marker{at_s: 0.0009765625}` (= 1/1024 s = exactly 689062.5 ticks); `{at_s: 0.0029296875}` (= 2067187.5 ticks) | stored `at` 689062, then 2067188; `used` echoes both | an exact half tick rounds to even | S2+S3+W |
| 65 | `add_marker` with `at_s` = `NaN`, `Infinity`, `-Infinity`, `1e400` (parsed as inf), `true`, `"1"`, `null`; `set_anchor{anchor:{to:"c2", offset_s:"1"}}` | each gives `invalid_op` **`bad_arg` @ `/ops/0/at_s`** (nested: `/ops/0/anchor/offset_s`), `op_index` 0, no `id`. The engine is never called, nothing is applied and the hash is unchanged | helper `TypeError`/`ValueError` → `bad_arg` at the `_s` arg (Ada 18:11) | S2+S3+W |
| 66 | `add_marker{at_s: -0.5}`; `set_anchor{to:"c1", offset_s: -0.5}` with c1 at 1 s; the same with c1 at 0.25 s | passed through as −352800000. Then `invalid_op` `negative_time` with the engine's `id` (the new marker), **path rewritten from `/markers/<k>/at` to `/ops/0/at_s`**. The set_anchor case is applied (start 0.5 s). The last case gives `anchor_before_zero` @ `T/anchor` (id = the text), **verbatim** (not a tick rule) | negatives reach the engine, and the engine rule decides | S2+S3+W |
| 67 | `move_clip{at_s: 12765305}` on a 4 s clip (end > 2⁵³ ticks ≈ 12765305.06 s); `move_clip{at_s: 12765306}` | `invalid_op` `out_of_range` @ `T` (id = the clip), **verbatim** (not at the converted field; §1h APPROVED). Then **`too_large` @ `/ops/0/at_s`** (engine `T/at`, path rewritten; id = the clip). Hash unchanged | 2⁵³ cap; tick-rule path rewrite | S2+S3+W |
| 68 | `history_redo{op_id}` of an undo entry; `history_redo` on a non-undo entry; `history_redo{group_id}` | applied, with `undoes: [<undo op_id>]` and summary `Redo: …`; `invalid_op` `not_an_undo` @ `/op_id`; `invalid_op` `bad_arg` @ `""` | redo tool | S2 |
| 69 | Two applies in `group_id:"g1"`, then `history_undo{group_id:"g1"}`; plain applies | **one** entry with `undoes: [op2, op1]` (newest first) and the hash from before the group; every apply has `undoes: null`. A stale-`base_version` retry with the same `client_op_id` returns the original result. `timeline_apply{group_id: null}` gives `invalid_op` `bad_arg` @ `/group_id`, fresh and on a cached key. **That case is satisfied on main** (#39, `8d181ed`; rechecked at `c1bbddb`). **/mcp side (Ada 18:11):** the same null sent through /mcp reaches the engine and returns the identical `bad_arg` @ `/group_id` (S3+W part) | `undoes` list; group undo; stale retry | S2 |
| 70 | **C5 (Ada 18:23).** `timeline_apply` with `actor:{kind:"human",id:"x"}` in the args and `step: 9` in op 0, from an agent session with plan step 3; the same on `history_undo`/`history_redo` (`step: 7` in the args) | applied. **(a)** The logged actor is the session's agent (`{kind:"agent", id:"hermes"}`) and `step: 3`. The history entry and the `oplog.jsonl` line keep **no trace of the forged values**: no `human`/`x`, no `9`/`7`, and the logged `ops` have no `step` key. **(b)** `warnings` = `ignored_field` @ `/actor` and @ `/ops/0/step` (undo/redo: @ `/step`), each naming the field's path. No hard reject. All of this holds at `c6de84e` | forged fields stripped, warned, never take effect | S2 |
| 71 | op1 edits c3, op2 and op3 touch c3 later, then `history_undo{op_id: op1}` | `undo_blocked`, `reason:"dependents"`, `blocking_op_ids: [op2, op3]` (in `seq` order) = `op_ids`. A later undo/redo pair doesn't count | dependents | S2 |
| 72 | Over `/mcp`: `move_clip c3` to 20 s (op A); `insert_clip` a 4 s clip at 11 s on V1 (op B: `changed_ids` [c4], doesn't mention c3); `history_undo{op_id: A}`. Then the same with A = a group `g1` of two entries | `undo_blocked`, `reason:"inverse_invalid"`, `op_ids: [A]`, `path:"/op_id"`, `id: A`, `rule:"overlap"`, `problems` verbatim (`overlap` @ `/tracks/1/items/3`, id `c4`). Group: `op_ids` = both entries in `seq` order, `path:"/group_id"`, `id:"g1"`. Passed through unchanged | `inverse_invalid` passthrough (the fallback) | S2+S3+W |
| 73 | `add_track{role:"voice"}` (gets `A3`), `remove_track A3`, `add_track{role:"voice"}`, `remove_track A4`; `Oplog.load` from the file; `add_track{role:"voice"}`. Also `add_track{role: []}` / `1` / `null`; `remove_track{id:"Q9"}` | `A3`, then **`A4`**, then after load **`A5`** (ids never reused). `bad_track_role` @ `/ops/0/role`. `not_found` @ `/ops/0/id`, `id:"Q9"` | ids never reused; op error paths | S2 |
| 74 | `move_clip c2` while `x1` is anchored to `c2`, then undo and redo; a start trim of `c2`; a ripple trim of `c1`; then `move_clip c2` (A), `set_fade x1` (B), `history_undo{op_id: A}` | `[c2, x1]` for the move, its undo and its redo. `[c2, x1]` for the start trim. `[c1, c2, c3, x1]` for the ripple trim. The undo of A gives `undo_blocked`, `reason:"dependents"`, `blocking_op_ids = op_ids = [B]`, `path:"/op_id"`, `id: A` | `changed_ids` include items that move on screen | S2 |
| 75 | `delete_clip c3`, then `add_marker{id:"c3"}`; one batch `add_marker{id:"q1"}`, `remove_marker q1`, `add_marker{id:"q1"}`; one batch `add_marker` (engine picks `mk1`), `remove_marker mk1`, `add_marker{id:"mk1"}`; `split_clip{ids:["p9","c3"]}` after c3 was deleted; `split_clip{ids:["p9","c2"]}` and `{ids:["c2","p9"]}` (c2 is in the doc); `add_marker{id:"c2"}` (c2 is in the doc); undo of the delete; then `add_marker` (auto) after a batch that created and removed `mk1`, live, after `Oplog.load`, and via `replay` | `id_reused` @ `/ops/0/id`; `id_reused` @ `/ops/2/id`; `id_reused` @ `/ops/2/id`; `id_reused` @ `/ops/0/ids/1`; `duplicate_id` @ `/ops/0/ids/1` and `/ops/0/ids/0` (at the entry); **`duplicate_id`** @ `/ops/0/id`; the undo restores `c3` (no `id_reused` check on inverses); the auto id is `mk2` live and after load, and an explicit `mk1` after load gives `id_reused` | `id_reused`; F1 retirement | S2 |
| 76 | Over `/mcp` and the engine: apply A with `client_op_id:"k"`; another apply; retry A unchanged (stale `base_version`); retry A naming the engine-picked id; retry A plus forged `actor`/`step`; retry A with a different label; `history_undo` with `client_op_id:"k"`; an undo `"u1"`, retried unchanged; `history_redo` reusing `"u1"`, with and without `summary`; a redo `"r1"`, then `history_undo` reusing `"r1"`; the same key from another actor. Engine only: retries of `"k"` with `ops` = `5` / `null` / `1.5` / `true` / `-1` / `[]` / 501 ops / `[1]` / `[null]`, and with `base_version:"0"` / `-1`. **#39 (canonical same-call):** retries of `"c"` (an `add_marker` at 1 s with label `"é"`) with `at` sent as the float `352800000.0`, an NFD label, a float or `true` `base_version`, an NFD `summary`, or the same op with its keys in a different order | first three retries: the cached result, same `op_id`, no new line. The different label gives `client_op_id_mismatch` @ `/client_op_id`, `op_ids:[A]`. The undo on `"k"` is a mismatch. The `"u1"` retry returns the cache. The redo on `"u1"` is a mismatch even with a `summary` (R2). The undo on `"r1"` is a mismatch. The other actor's call is independent. The junk retries give **`bad_arg`**: `/ops` for the non-lists, `[]` and 501; `/ops/0` with `op_index` 0 for `[1]` and `[null]`; `/base_version`. Never a mismatch or a crash. **#39:** the float `at` and the NFD label give `client_op_id_mismatch` (`op_ids:[c's op]`). The float/`true` `base_version` and NFD `summary` give `bad_arg` (`/base_version`, `/summary`) because shape checks come first. The reordered keys return the cache. These cases run on main since #39 (`8d181ed`) | `client_op_id` retry contract; shape checks before dedupe | S2+S3+W |
| 77 | Non-string ids: `move_clip{id:5}`, `remove_track{id:null}`, `insert_clip{track:["V1"]}`, `add_marker{id:7}`, `split_clip{ids:["p1",3]}`, `add_transition{between:["c1",2]}`, `set_anchor{anchor:{to:true}}`, `add_track{id:{}}` | each gives `invalid_op` **`bad_arg`** at its own path: `/ops/0/id`, `/ops/0/id`, `/ops/0/track`, `/ops/0/id`, `/ops/0/ids/1`, `/ops/0/between/1`, `/ops/0/anchor/to`, `/ops/0/id`. Never `not_found` or `bad_id`; hash unchanged | F2 id types | S2 |
| 78 | Undo/redo targets: `history_undo` with `{op_id:null}`, `{group_id:null}`, `{op_id:5}`, `{}`, `{op_id, group_id}`; `history_redo{group_id:"g"}`. The same junk on a cached `client_op_id`. Then via a log file: apply a, undo u (`"u1"`), redo r of u (`"r1"`), undo uu of r (`"uu1"`); `Oplog.load`; retry `"u1"` as `history_redo`; retry `"r1"` and `"uu1"` with either tool (same target and summary); live, before the reload, `"uu1"` as `history_redo` | `bad_arg` @ `/op_id`, `/group_id`, `/op_id`, `""`, `""`, `""`, and the same on the cached key. A `null` group never matches ungrouped entries. After load: `"u1"` as redo is a **mismatch** (R2 after load). `"r1"`/`"uu1"` with **either** tool returns the cached result (**RULED permanent**: an undo of an undo entry is a redo). Live: `"uu1"` as redo is a mismatch | R3/R4 target rule; R2 after load; the ruled undo-of-undo equivalence | S2 |
| 79 | **On main `a1922f0`** (#38 merged). Using Bay's `xfade_log` fixture (c2 pulled under c1 by 0.5 s, crossfade `t12`; optionally c3 under c2 with `t23`): a ripple end trim of c1 (`src_out` 3 s) and a ripple start trim (`src_in` 1 s), each with undo and redo; a ripple start trim of c2 (incoming `t12`); a non-ripple end trim of c1; too-short ripple trims (c1 to 0.5 s; c2 to 0.75 s and 0.25 s with `t12`=`t23`=0.5 s; c2 to 1 s with `t12`=1 s, `t23`=0.5 s; c2 to exactly 1 s with both 0.5 s); the c1 case as op 1 of a batch | the c1 trims: applied, with c2, `t12`, c3 and x1 shifted −1 s, `t12` keeping `dur` 0.5 s and `[c1, c2]`, `mu1` unchanged, and `changed_ids` = `[c1, c2, c3, t12, x1]` on apply, undo and redo; undo restores the hash. The c2 start trim: `t12` and c1 unchanged, `changed_ids` `[c2, c3]`. The non-ripple trim: `transition_overlap_mismatch` (validator, id `t12`). Too short: `invalid_op` **`transition_too_long`** @ `/ops/0`, `op_index` 0, with `id` = `t12`; `t23` (each fits alone, not both); `t23` (neither fits: the outgoing one, RULED); `t12` (the incoming one doesn't fit). Exactly the sum is applied. The batch reports `/ops/1`, `op_index` 1. The hash is unchanged on every refusal | crossfade ripple trim; `transition_too_long` shape and tie-break | S2 + #38 |
| 80 | **On main `8d181ed`** (#39 merged). `insert_clip` on V1 with `media` = `"zz"`, `""`, `5`, `null`, `[]`, `{}`, `true`; then a bad `track` together with bad `media` | each gives `invalid_op` **`unknown_media` @ `/ops/0/media`**, `op_index` 0, **no `id`**, hash unchanged (never the doc path `/tracks/…/media`). Bad track + bad media gives `not_found` @ `/ops/0/track`, `id` = the track | `unknown_media` at the op's own arg | S2 |
| 81 | **On main `c6de84e`** (#40 merged). `edit_text` on `x1` with `text` = `"Yo"`; then `style` = `"bold"` alone; then a non-ASCII NFC string with an emoji; then `text` = `""` | each is applied with `changed_ids` `[x1]`. Only the given field changes (the other field, `dur`, the fades and the anchor are untouched). The stored value is byte-identical to the input (no normalising). Empty text is accepted | `edit_text` basics, byte for byte | S2b |
| 82 | **On main `c6de84e`** (#40 merged). in order: an extra arg `dur`; no `id`; `id` = `5` and `null`; `id` = `"zz"`; `id` = clip `c1`; `id` = a transition `t12`; `id` = `x1` with neither `text` nor `style`; `id` = `c1` with neither; and the `style: ""` case as op 1 of a batch | `invalid_op` `unknown_arg` @ `/ops/0/dur`; `missing_arg` @ `/ops/0/id`; `bad_arg` @ `/ops/0/id` with **no `id`**; `not_found` @ `/ops/0/id` with `id` `zz`; `bad_arg` @ `/ops/0/id` with `id` `c1` / `t12`; **`missing_arg` @ `/ops/0`** with no `id`; `bad_arg` with `id` `c1` (the item type is checked before the fields); the batch reports `/ops/1`, `op_index` 1. The hash is unchanged every time | check order and paths; house rule | S2b |
| 83 | **On main `c6de84e`** (#40 merged). `text` = `5`, `null`; `style` = `["pop"]`, `""`; `text` with a lone surrogate; `style` with a lone surrogate; NFD `text` and `style`; bad `text` and bad `style` together | `invalid_op` `wrong_type` @ `/ops/0/text` or `/ops/0/style` with `id` `x1`; NFD gives **`not_nfc`** at the same paths; both bad together reports `text`. The hash is unchanged | value checks; empty `style` is refused | S2b |
| 84 | **On main `c6de84e`** (#40 merged). edit `x1` `text` → `"Yo"`, then undo, then redo; read the entry's `inverse`; send a client op `set_fields` | `changed_ids` `[x1]` on apply, undo and redo. Undo restores the original hash and redo restores the edited hash. `inverse` = `[{op: set_fields, id: x1, set: {text: "Hi"}, unset: []}]` (only the given field). The client `set_fields` gives `unknown_op` @ `/ops/0/op` | inverse, undo/redo, `set_fields` internal-only | S2b |
| 85 | **On main `c6de84e`** (#40 merged). edit `x1` with its current `text` and `style` (a byte-identical no-op); retry with the same `client_op_id` and args; undo it; redo the undo | `changed_ids` `[]` on apply, undo and redo. Apply creates an entry with a **new version and the same hash**. The exact retry returns the same `op_id` with no new entry | no-op still makes an entry | S2b |
| 86 | **On main `c6de84e`** (#40 merged). two human edits on `x1`, then undo the first; a human edit undone by an agent; an `inverse_invalid` fallback if one can be built | `undo_blocked` **`dependents`** with `op_ids` = `blocking_op_ids` = [the later edit], in `seq` order; **`actor`** with `op_ids` = [the target]; `inverse_invalid` with `op_ids` = the entries being undone. Every reason has `path` `/op_id` and `id` = the target | `undo_blocked` `op_ids` per reason (doc note) | S2b |
| 87 | **On main `c6de84e`** (#40 merged). Through /mcp: `edit_text{id: x1}` with neither field; `{text: <NFD>}`; `{style: ""}`; `{text: 5}`; `{text: <NFC non-ASCII>}` sent twice with the same `client_op_id`, then a retry whose `text` is the NFD form of it; an `_s`-suffixed arg | neither field: `invalid_op` `missing_arg` @ `/ops/0`, no `id`, with the engine message verbatim and the /mcp `hint` **"give text or style"**. NFD: `not_nfc` and empty style: `wrong_type`, each at `/ops/0/text` / `/ops/0/style` with `id` `x1`, verbatim. `text: 5`: the engine's `invalid_op` `wrong_type` @ `/ops/0/text` with `id` `x1`, exactly as over HTTP (§1g). The NFC text reaches the engine byte for byte; the same-args retry returns the same `op_id`. The NFD-variant retry is a `client_op_id` mismatch (no normalising). The `_s` arg (e.g. `text_s`) gives the engine's `unknown_arg` @ `/ops/0/text_s` (§1g) | /mcp mapping for `edit_text` | S2b + S3 + W |
| 88 | **On main `c6de84e`** (#40 merged; checked at S3 with C5). The same calls through /mcp `edit_text` and through HTTP `timeline_apply`: `{id: 5}`, `{id: true}`, `{id: null}`, `{id: ["x1"]}`, each with `text: "a"`; **Prove's cases:** `{id: 5, bogus: 1}`; `{id: 5}` with no fields; `{id: "zz", text: 5}`; `{id: x1, text: 5}`, `{id: x1, style: 5}`, `{id: x1, text: null}`, `{id: x1, style: {}}` | the /mcp `id` pre-check matches the engine: **`invalid_op` `bad_arg` @ `/ops/0/id`, no `id`**, `op_index` 0, never a schema error. `{id: 5, bogus: 1}` gives **`unknown_arg` @ `/ops/0/bogus`**, the same as HTTP (it comes before `bad_arg`). `{id: 5}` gives **`bad_arg` @ `/ops/0/id`, no `id`** (engine answer at `c1bbddb`; `bad_arg` comes before the missing-field check). `{id: "zz", text: 5}` gives **`not_found` @ `/ops/0/id`, `id` `zz`**. Non-string `text`/`style` give **`wrong_type` @ `/ops/0/text` / `/ops/0/style` with `id` `x1`**. /mcp and HTTP errors are identical in `code`, `rule`, `path`, `op_index` and `id` presence. Hash and version are unchanged | /mcp `edit_text` pre-check = engine answer (Ada 18:04, Prove's cases) | S2b + S3 + W |
| 89 | Checked by Prove at S3 with C5. For **every** tool in `tools/list`, send the same malformed inputs through /mcp and HTTP: an unknown tool arg and an unknown op arg; a missing required arg; a non-string id in every op; `timeline_apply` with `ops` `[]` and 501 ops, `base_version: "0"`, `summary: ""` / 201 chars / NFD, `group_id: null`; `history_undo{op_id: null}`; `history_redo{op_id: 5}`; forged `actor`/`step`. Also inspect each tool's input schema | every /mcp error equals the engine's in `code`, `rule`, `path`, `id` presence and which error wins when several apply. /mcp never answers with a non-engine code or rule. Forged `actor`/`step` give the engine's `ignored_field` warnings. No enforced `additionalProperties:false`, `minItems`/`maxItems`, `minLength`/`maxLength` or non-null type on an engine field unless /mcp reproduces the engine answer exactly. The `_s` and `schema_version` fields follow the 6:11 PM exemption (tests 57, 65, 90) | general /mcp pre-check rule (Ada 18:04) | S3+W |
| 90 | Prove's S3 inputs, checked at S3. Through /mcp, `add_marker{at_s: v}` and `set_fade{id: c1, fade_in_s: v}` for v = `true`, `false`, `NaN`, `Infinity`, `-Infinity`, `1e308`, `-0.0`, `-1`, `-1.5`, `"1.5"`; also `set_anchor{anchor:{to:"c2", offset_s: -1}}` | `true`/`false`/`"1.5"` (`TypeError`) and `NaN`/`±Infinity` (`ValueError`) each give **`bad_arg` @ `/ops/0/at_s`** (or `/ops/0/fade_in_s`), with no engine call. `1e308` is not rejected by the helper: the engine gives **`too_large`**, path rewritten to the `_s` arg, with the engine's `id`. `-0.0` is applied as tick `0`, with `used.<arg>` = `{ticks: 0, seconds: 0}`. `-1`/`-1.5` reach the engine as −705600000 / −1058400000 and give **`negative_time`**, path rewritten to the `_s` arg. A negative `offset_s` is applied (the only signed tick field). Hash unchanged on every refusal | `_s` conversion end to end (Ada 18:11, Bay's wiring) | S2+S3+W |
| 91 | Prove's S3 gate. Through /mcp: `add_marker{at_s: 0.3333333333333333, label: "m"}` with `client_op_id:"f"`; the exact same call again; another apply; the exact same call again (stale `base_version`); also `move_clip{id: c3, at_s: 10.000000000000002}` sent twice under one key | each exact retry returns the cached result (same `op_id`, same `new_version`, no new entry), **never `client_op_id_mismatch`**. /mcp converts the same float to the same **int** tick every time (235200000) and forwards ints only. Forwarding the float tick `235200000.0` would be a mismatch (engine, checked at `c1bbddb`), so /mcp must never do that | exact retry with a float `_s` never mismatches | S2+S3+W |
| 92 | Prove's S3 gate. Through /mcp, under `client_op_id:"n"`: `edit_text{id: x1, text: <NFD "Olé">}`, then the exact same call; `add_marker{label: <NFD>}` and an NFD `summary`, each sent twice; then `edit_text{id: x1, text: "Olé"}` (NFC) under `"n"`, sent twice | each NFD call gives the engine's answer both times: `not_nfc` @ `/ops/0/text` with `id` `x1`, or, for the NFD marker label, the validator's **`not_nfc` @ `/markers/<k>/label` with the new marker's `id`** (as at `c6de84e`: `/markers/1/label`, `id` `mk1`; corrected 8:32 PM, Bay right). **The test asserts the literal path and id (O4, Ada 8:58):** `rule` `not_nfc`, `path` `/markers/1/label`, `id` `mk1`, not just parity with REST. At `0282e9f`, tests/test_s3_mcp.py:245–249 pins only `rule` + REST parity, or `bad_arg` @ `/summary`. The retry gets the same error, **never `client_op_id_mismatch`**, and a refused call doesn't reserve the key. The NFC call then applies under `"n"`, and its exact retry returns the cache. No normalising anywhere (engine checked at `c1bbddb`) | exact retry with NFD text never mismatches | S2+S3+W |
| 93 | **C5 retry edge case (Prove; Ada 18:23; target = S3-SPEC §4 APPROVED rules 1–5, Ada+Prove 6:28 PM).** Engine, with a log file. Apply A (forged `actor` + op `step`) under `"k"`; (i) an exact retry; (ii) a retry of A with the forged fields removed; (iii) A with a different forged `step` value; (iv) a clean apply B under `"c"`, then B plus a forged `actor`; (v) `Oplog.load`, then the exact retry of A; (vi) the same for `history_undo{step}` | none of them is ever `client_op_id_mismatch`: each returns the cached result (same `op_id`, no new entry, no new line), because forged fields are stripped before the fingerprint (L848 before L933/L953). **Expected warnings: those of the current call** (the forged field's path whenever this call carries one, and none when it doesn't). **At `c6de84e`:** (i), (iii) and (vi) are met live. **(ii) NOT MET:** it echoes A's stale warnings. **(iv) NOT MET:** no warning, so the forged `actor` is silently ignored. **(v) NOT MET:** the cache is rebuilt with `warnings: []` (L1241), so the warning is lost after reload. Cause: the replay returns the stored result's warnings (L951, L1109–1110) instead of this call's (L848). **Prove's S3 gate (§11 diff 2, APPROVED rules 1–5):** at the S3 head, every case gives `warnings` = stored result warnings (always `[]` in S3) + **this call's own** strip warnings, **live and after `Oplog.load`**. Explicit after-reload cases: (v) the exact retry → the warning; (vii) after load, a retry that drops the forged field → none; (viii) after load, B plus a forged `actor` → that warning. The log file stays byte-identical (no `warnings` key in S3) | exact retry + forged field: cache + own warnings, live and after reload | S2 |
| 94 | **C5 gate (Prove's wording, Ada 18:23).** The test-70 calls, plus the test-93 exact retry, over **HTTP, ACP and MCP**, each with its own transport session per S3-SPEC §4 (corrected 8:32 PM, Bay right). ACP: agent `hermes`, plan step 3. MCP over HTTP or attached stdio: the token's agent id (e.g. `stdio`), `plan=None`, **no step**. HTTP REST: the token's session | on every path: **(a)** the write lands with **that transport's** session actor and step (no `step` key at all on MCP), and the history entry (`history_list`, log line) keeps no trace of the forged value; **(b)** `ignored_field` names the field's path (`/actor`, `/ops/0/step`, `/step`), passed through verbatim by each layer. The exact retry gives the cached result plus the same warning, never `client_op_id_mismatch`. Identical results across the three paths, apart from actor/step and ids. **PASS needs all three** | C5 on every write path | S2+S3+W |
| 95 | **/mcp `_s` order (Ada 18:40; §1h (j)).** `add_marker` with: (a) `{at: 705600000, at_s: 1, label, bogus: 1}`; (b) `{at, at_s, label}`; (c) `{at: 705600000, label}`; (d) `{at_s: "x"}` with no `label`; (e) `{at_s: "x", label, bogus: 1}`; (f) `{at_s: "x", label}`; plus `set_fade{id: c1, fade_in: 0, fade_in_s: 0, fade_out_s: "x"}` | (a) **`unknown_arg` @ `/ops/0/bogus`**, unchanged from the engine. (b) **`bad_arg` @ `/ops/0/at_s`** (both-sent, D23 exemption). (c) applied with `at` = 705600000 (raw passthrough). (d) **`missing_arg` @ `/ops/0/label`**. (e) **`unknown_arg` @ `/ops/0/bogus`**. (f) **`bad_arg` @ `/ops/0/at_s`**, with no engine call. `set_fade`: `bad_arg` @ `/ops/0/fade_in_s` (both-sent comes before conversion). Each error has `op_index` 0 and the hash is unchanged. The `unknown_arg`/`missing_arg` bodies are byte-identical to HTTP `timeline_apply` sent the check view | check view → both-sent → conversion | S2+S3+W |
| 96 | **The same order for `anchor.offset_s`** (Ada 18:40). `set_anchor` on x1 with: (a) `anchor: {to: c2, offset: 0, offset_s: 1}` + `bogus: 1`; (b) `anchor: {to: c2, offset: 0, offset_s: 1}`; (c) `anchor: {to: c2, offset: 705600000}`; (d) `anchor: {to: c2, offset_s: "x"}` with no `id`; (e) `{id: x1, anchor: {to: c2, offset_s: "x"}, bogus: 1}`; (f) `{id: x1, anchor: {to: c2, offset_s: "x"}}`; plus `add_text` with a bad `offset_s` and no `dur` | (a) `unknown_arg` @ `/ops/0/bogus`. (b) **`bad_arg` @ `/ops/0/anchor/offset_s`** (both-sent). (c) applied (raw passthrough). (d) `missing_arg` @ `/ops/0/id`. (e) `unknown_arg` @ `/ops/0/bogus`. (f) **`bad_arg` @ `/ops/0/anchor/offset_s`**, with no engine call. `add_text`: `missing_arg` @ `/ops/0/dur`. Hash unchanged on every refusal. Nested anchor keys: see test 97 (fixed, Ada 18:47) | `offset_s` order | S2+S3+W |
| 97 | **Anchor keys checked by name (Ada 18:47; S3 engine change, the only one Prove allows).** Over HTTP `timeline_apply` and over /mcp, for `set_anchor` on x1, `add_text` and `insert_clip` (A2 music): (a) `anchor: {to: c2, offset_s: "x", zz: 1}` (HTTP: `offset: 0` instead of `offset_s`); (b) `anchor: {offset_s: "x"}` (HTTP: `{offset: 0}`); (c) the same with a valid `offset_s` / `offset`; (d) `anchor: {to: c2, offset_s: "x"}` + op-level `bogus: 1` | **FIRM: D29 APPROVED (Ada 18:56)**, S3-SPEC §11 diff 1, helper step 5: (a) **`unknown_arg` @ `/ops/0/anchor/zz`** and (b) **`missing_arg` @ `/ops/0/anchor/to`**, each with `op_index` 0 and no `id`. They're identical over HTTP and /mcp, and on /mcp they come **before** the `offset_s` conversion (never `bad_arg` @ `/ops/0/anchor/offset_s`). (c) The same answers. (d) The op-level `unknown_arg` @ `/ops/0/bogus` comes first. (e) Order and same-op precedence (D29): `{to: c2, zz: 1}` with no offset gives `unknown_arg` @ `.../anchor/zz` (unknown keys before missing ones); `{}` gives `missing_arg` @ `.../anchor/offset` (`offset` before `to`); `set_anchor{id: "zz", anchor: {offset: 0}}` gives **`missing_arg` @ `/ops/0/anchor/to`**, ahead of `not_found` (today: `not_found` @ `/ops/0/id`); `set_anchor{id: x1, anchor: {to: 5}}` gives `missing_arg` @ `/ops/0/anchor/offset` (today: `bad_arg` @ `/ops/0/anchor/to`). Both "today" answers were confirmed at `c6de84e`. `anchor: null` and non-dict anchors keep today's answers. Hash unchanged. At `c6de84e` these were validator errors at the doc path (`unknown_field` @ `T/anchor/zz`, `missing_field` @ `T/anchor/to`, with `id`); this change is the gate's one allowed difference | anchor-key check, HTTP = /mcp | S2+S3+W |
| 98 | **Named exemption: `trim_clip{dur_s}` on a clip** (Ada 18:47). /mcp `trim_clip{id: c1, dur_s: "x"}`; HTTP `trim_clip{id: c1, dur: 705600000}`; /mcp `trim_clip{id: c1, dur_s: 1}` | /mcp: **`bad_arg` @ `/ops/0/dur_s`**, with no engine call. HTTP: **`bad_arg` @ `/ops/0/id`**, no `id` (as at `c6de84e`). A valid `dur_s` on /mcp reaches the engine and gives that same `bad_arg` @ `/ops/0/id`. Hash unchanged | §1h (j) exemption (ii) | S2+S3+W |
| 99 | **Named exemption: batch order** (Ada 18:47). One `timeline_apply` with op 0 `move_clip{id: "zz", at_s: 0}` and op 1 `add_marker{at_s: "x", label}`; the same with op 0 `move_clip{id: "zz", at_s: 0, bogus: 1}`; HTTP with op 0 `move_clip{id: "zz", at: 0}` + op 1 `add_marker{at: 0, label}` | /mcp: **`bad_arg` @ `/ops/1/at_s`**, `op_index` 1; op 0's engine `not_found` is never reached. With op 0's `bogus`: `unknown_arg` @ `/ops/0/bogus` (the /mcp stage keeps op order). HTTP: `not_found` @ `/ops/0/id`, `id: "zz"` (as at `c6de84e`). **Cached key (S3-SPEC D31):** after an applied call under `"k"`, a different call under `"k"` with a bad `at_s` gives `bad_arg` @ `/ops/0/at_s`, not `client_op_id_mismatch` (dedupe comes after the /mcp op stage). Nothing applied | §1h (j) exemption (iii); S3-SPEC D31 | S2+S3+W |
| 100 | **Envelope before the /mcp op stage (RULED, Ada 18:56; S3-SPEC D21 step 3b; not an exemption). FIRM.** `timeline_apply{summary: "", ops: [add_marker{at_s: "x", label}]}` over /mcp; the same with `at: 0` over HTTP. Also an unknown top-level arg (`bogus: 1`) + a bad `at_s`; `group_id: null` + a bad `at_s`; `base_version: "0"` + a bad `at_s`; `ops: [5, {add_marker, at_s: "x"}]` | both paths give **`bad_arg` @ `/summary`** (the engine's envelope check, oplog.py:1115–1119, reused through a shared helper, not copied). Likewise `unknown_arg` @ `/bogus`, `bad_arg` @ `/group_id`, `bad_arg` @ `/base_version`, and `bad_arg` @ `/ops/0` with `op_index` 0, each ahead of the `_s` error and identical on both paths. Dedupe (`client_op_id_mismatch`) and `conflict` still come **after** the /mcp op stage (test 99). | envelope order | S2+S3+W |
| 101 | **D27 parse robustness, cap and drain bound (Ada 7:03 + 7:09).** One source: **`MAX_BODY` = 1048576** (studio.py:38, inclusive); drain bound **16 × `MAX_BODY` = 16777216**. **FIRM on the numbers; waits on Bay's next S3-SPEC revision (on hold).** Stdio /mcp. Newline framing: a 5000-digit integer line; an invalid UTF-8 line (`0xff`); then `ping`. `Content-Length` framing, each case in a **fresh session**: (1) a header with a bad JSON body, then `ping`; (2) **`Content-Length: 1048576`** with a valid body of exactly that size, then `ping`; (3) **`1048577`**; (4) **`16777216`**; (5) **`16777217`**; (6) a **9-digit** length (e.g. `100000000`, and `000000007`); (7) **malformed values (Ada 7:14):** `-1`, `+5`, `1_000`, `abc`, whitespace-only, `٣` (stdio **duplicate headers are covered once, in 102(a)**; Bay's spec puts them in its 101, and either is fine per the 7:21 note). An **8-digit** length is read by value: `00000007` + a 7-byte body is answered normally (S3-SPEC test 101). HTTP: covered in test 103 | Newline framing: each bad line gets **exactly one `-32700`** `id:null`, and the next `ping` is answered (at `c6de84e` the 5000-digit and bad-UTF-8 lines **exit 1**, Prove's probe). (1) `-32700`, framing still in step, `ping` answered (at `c6de84e`: exit 1). (2) **accepted** and processed. (3) and (4) **answered first, then drained:** `-32700` `id:null` arrives **before** the client finishes the body (N far larger than what's sent, write end left open). The client then sends the rest; exactly N bytes are read in small chunks, none kept, none scanned for headers; the next real frame is answered. (5) **broken stream:** `-32700` `id:null`, logged, then the session closes with a **nonzero exit**; nothing after it is read as a call. (6) **broken stream, with no `int()` call** (the test asserts the digit run is rejected by length, so even `000000007` closes). (7) **(Ada 7:14):** the same broken-stream close (`-32700` `id:null`, a log line, nonzero exit), never a skip-ahead; at `c6de84e`, `-1` reads to EOF (probe `neg`), and `abc` exits 1. Known limit: a `validate_timeline` doc over 1 MiB is refused (`-32700`) | parse errors never crash /mcp; cap, drain bound, broken-stream close | S3+W |
| 102 | **D27: embedded calls never run (Ada 7:09; malformed-header close approved by Ada 7:14).** Stdio, `Content-Length` framing, each in a fresh session: (a) **malformed header:** `Content-Length: -1` (also `+5`, `1_000`, `abc`), and **duplicate headers**: `Content-Length: 5` **twice, same value** (Prove 7:24) and `5` + `7`; plus **a blank line between frames** (Ada 8:32 PM rejected the blank-line skip): a valid frame, then `\r\n`, then a full framed call. Each is followed by body lines including a full framed call (`Content-Length: 40` + blank line + `{"jsonrpc":"2.0","id":5,"method":"tools/call",…}`) and a bare newline-JSON call id 6. (b) **over-cap length:** `Content-Length: 16777217`, followed by an embedded framed call id 9 and more bytes; plus `Content-Length: 1048577` whose drained body contains an embedded framed `ping` id 10, padded to exactly 1048577 bytes, then a real framed `ping` id 11. (b2) **newline mode, an over-long line (O1, Ada 8:58):** before any `Content-Length` is seen, a single line longer than `MAX_BODY` (e.g. 3 MiB, no newline until the end) holding a `tools/call`. The reader takes at most `MAX_BODY + 1` bytes per line. (c) **too-short length:** `Content-Length: 5`, body `{"a":1}`, so the leftover `1}` runs into a line that isn't a header (`1}Content-Length: 40`); also Prove's `short` case: `Content-Length: 2`, body `{}{"jsonrpc":"2.0","id":7,"method":"ping"}` | (a) **blank line between frames (Ada 8:32):** after the first frame is answered, the `\r\n` isn't a valid header, so `-32700` `id:null`, a stderr log, a nonzero exit, and the following framed call never runs (at `0282e9f`, mcp.py:319–320 skips it and the call runs, reproduced). (a) **duplicates (Ada 7:15–7:20; same-value case Prove 7:24):** two or more `Content-Length` lines in one header block, **even with the same value** (`5`/`5` and `5`/`7`), give `-32700` `id:null`, a log line and a nonzero exit (a broken-stream close). **The embedded framed call id 5 and the newline call id 6 never run.** (a), the other malformed values **(Ada 7:14):** `-32700` `id:null`, a log line, then the broken-stream close (nonzero exit). **No reply for id 5 or 6; no tool runs; no skip-ahead.** (b) `16777217`: `-32700`, broken-stream close, **id 9 never runs**. `1048577`: `-32700`, the body is **drained, not scanned**, so **id 10 never runs**, and id 11 is answered. (b2) **`-32700` `id:null`, a stderr log, a nonzero exit; the line is never parsed** and its call never runs. Before (`0282e9f`): the 3 MiB line was read whole and answered (mcp.py:331, unbounded `readline()`; Prove `probes/out_stdio_head.jsonl`, `readline_got: 3145787`). (c) **Leftover bytes that don't form a valid header cause the broken-stream close:** the stream stays in `Content-Length` mode (APPROVED, Ada 7:15–7:20), so a non-header line outside a declared body is never parsed as newline JSON. No reply for id 7; for the `{}` body, `-32600` (D15) first. **Limit (verified against mcp.py framing at `c6de84e`):** if the leftover bytes *are* a valid frame (e.g. `Content-Length: 2` + `{}` followed by `Content-Length: 40\r\n\r\n{call}`), the byte stream is **identical to two real frames**, and the server correctly runs the second (`Transport.read` returned `{}` and then the call). "Never runs" can't be asserted for that case | no embedded call ever runs | S3+W |
| 103 | **HTTP refusals (Ada 7:09 + 7:15–7:20).** One header check for HTTP and stdio: after stripping surrounding spaces and tabs, the value must match `re.fullmatch(rb"[0-9]+")` with **at most 8 digits** (no `int()` beyond that), and there must be **exactly one** `Content-Length` header (read with `headers.get_all("Content-Length")`; `.get()` returns only the first). **Before (`c6de84e`, reproduced):** studio.py:149 `int(headers.get("Content-Length") or 0)`: `+5` → 5 (accepted), `1_000` → 1000 (accepted), `-1` → "request body too large", a 9-digit value → "too large", `abc` and `٣` (UTF-8 read as Latin-1, so `int()` raises) → **0** (the body is left unread, parsed as `{}`), duplicate headers → the **first** value silently. On one keep-alive connection, `POST /api/restyle` with `Content-Length: 1048577` and a body starting `GET /api/doctor HTTP/1.1…` gave 400, then **200 from `/api/doctor`** (smuggled), then 414. **After**, to a REST JSON route and to HTTP /mcp: (i) `abc`, `-1`, `+5`, `1_000`, `٣`, a 9-digit length, and **duplicate headers** (`5`/`5`, `5`/`7`); (ii) a well-formed `1048577`; (iii) `1048576`; (iv) **no `Content-Length` header**; (vi) **every HTTP method, not only POST (F2, Ada 8:58).** The D27(d) checks run **before routing**: Transfer-Encoding first, then exactly one valid `Content-Length`. A **GET** also gets 400 + close, with the body never read, for a length **above 0**. Rows: (vi-a) `GET /api/doctor` with a valid `Content-Length` > 0 whose body holds `GET /api/doctor HTTP/1.1…`, plus a GET with `Content-Length: 2000000` (over the cap); (vi-b) a GET with `Content-Length: abc` + the embedded GET; (vi-c) a GET with `Transfer-Encoding: chunked` + the embedded GET. **Before (`0282e9f`; Prove's `evidence/prove-s3/0282e9f/probes/out_http_head.jsonl`, rows "GET + …"):** on `/api/doctor`, (vi-a) and (vi-b) got **200, then 200** (the embedded GET ran); (vi-c) got one 200 and the connection closed; `/api/projects/p1/timeline` got 404, then 200. GET requests never call `body_length` (studio.py:324–334 → http_engine.py:123); (v) **`Transfer-Encoding` (RULED, Ada 7:25; FIRM)**, each carrying the embedded `GET /api/doctor`: `Transfer-Encoding: chunked` alone; chunked + a bad `Content-Length` (`abc`); chunked + duplicate `Content-Length` headers (`5`/`5`). Before for (v), from Bay's repro `evidence/s3-spec/http_chunked_smuggle_probe.py`/`.out` at `c6de84e`: a chunked `POST /api/design` with no `Content-Length` returned **200, then 200**. TE is ignored, the length reads as 0 and the body as `{}`, and the GET runs as a second request. `POST /mcp` returned **404**, because there's no HTTP /mcp route at `c6de84e`, so every HTTP /mcp "before" in this test is 404 | (i) REST: **400 `{"ok": false, "error": "invalid content length"}`** (a new message string, not a rule id; counts stay 17/36); HTTP /mcp: 400 with `-32700`. (ii) REST: 400 `{"ok": false, "error": "request body too large"}`; HTTP /mcp: 400 `-32700`. Every refusal in (i)–(ii) sends **`Connection: close`** and closes: **exactly one response per connection, and the embedded `/api/doctor` never runs.** (iii) accepted; the connection stays usable. (iv) **unchanged:** read as 0 (body `{}`), as at `c6de84e`. (v) **Transfer-Encoding is checked first**, before any `Content-Length` check, and the body is never read. REST: exactly one **400 `{"ok": false, "error": "unsupported transfer encoding"}`**; HTTP /mcp: 400 `-32700` `id:null`. Both send `Connection: close` and close. **The two mixed cases get the Transfer-Encoding answer, not "invalid content length".** `/api/doctor` never runs. It's a new message string, not a rule id, so counts stay 17/36. (vi) Each GET row: **exactly one 400 + `Connection: close`, and `/api/doctor` never runs**. (vi-a) **RULED (Ada 9:02):** REST **400 `{"ok": false, "error": "request body not allowed"}`** + close; HTTP /mcp `-32700` `id:null` + close. That includes a GET over the cap: `Content-Length: 2000000` gets "request body not allowed", **not** "request body too large". **Check order, every method:** (1) Transfer-Encoding, (2) a valid `Content-Length`, (3) the GET body rule, (4) the size cap, which only a POST reaches. It's a new message string, not a rule id (104 tests, 17/36). (vi-b) **"invalid content length"**. (vi-c) **"unsupported transfer encoding"**. A GET with no `Content-Length` or `Content-Length: 0` is unchanged | HTTP refusals never desync; one header check | S3+W |
| 104 | **GET /mcp follows projects opened mid-stream (Ada approved, 8:36 PM).** Open a GET /mcp stream (read-scoped token). After the stream has started, open a new project, then write to it (a valid `timeline_apply`) | The open stream gets **`notifications/resources/updated`** with `uri` `timeline://<new id>`. **Before (`0282e9f`):** no event, because http_engine.py:212 takes a snapshot of `ENGINE.projects` at connect and only attaches listeners to those projects (Glyph). Glyph's id-decode case is **not** part of this test (see §1i E) | GET /mcp sees every project, including ones opened later | S3+W |

**Totals:** 104 tests. **45 run at Slice 1** (1–45). Of the other 59: 18 need S2 (51–56, 68–71, 73–75, 77–80, 93), **6 need S2b (81–86)**, 13 need S3 or S3+W (46, 47, 50, 57, 58, 60, 61, 62, 89, 101–104; the write half of 46 also needs S2), 19 need S2+S3+W (48, 49, 63–67, 72, 76, 90–92, 94–100), **2 need S2b+S3+W (87, 88)**, and 1 needs S8 (59). Tests 68–80 match main `8d181ed`; tests 81–88 match main `c6de84e` (#40 merged; tree = `c1bbddb`), including test 69's `group_id: null` case and test 76's canonical cases.

---

## 3. Open questions / dependencies

**Bay: PR #35**
1. **Head SHA:** pinned at `b1b51c1` (after the C1 fix and the merge with main). Re-pin if the head moves.
2. **PR body:** add the 11:22 changes (`seconds_to_ticks_nearest`, the 2⁵³ `out_of_range` cap, `missing_field` for a missing `id`/`type`, and type-safe roles, keys and strings), or point to `docs/timeline.md` as the record.

**Order (Ada, 1:59 PM):**
1. ~~The crossfade ripple-trim PR.~~ **Done:** #38 merged as `a1922f0` (3:29 PM).
2. ~~Bay's post-S2 follow-up PR~~ **Done:** #39 merged at 5:33 PM (head `c8e5604` → main `8d181ed`; §1e). Its commits followed this order:
   1. the `key=repr` fix (`oplog.py:700`);
   2. the #36 items;
   3. the S2 notes;
   4. `timeline_apply{group_id: null}` → `bad_arg` (test 69's null case waits on this);
   5. Ada's #38 doc rulings (§1d; docs only);
   6. CI-FFMPEG.
3. **S2b: MERGED** as #40 (head `c1bbddb` → main **`c6de84e`**, 6:16 PM ET; see §1f). The `edit_text` §1b row and tests 81–88 are added (88 covers the /mcp `id` pre-check, Ada 18:04); test 89 covers the general §1g rule.
   - **Scope:** `edit_text` for text items on any text track (PR decision; originally T1) (`text` + `style`, with inverse, undo and redo), plus the `undo_blocked` `op_ids` doc note (what `op_ids` means for each reason, as in §1c).
   - **Process:** Bay posts the spec decisions, and **Wire confirms them before the PR opens**. Then I add the `edit_text` registry row (§1b) and its tests.
4. **S3: next. It branches off `c6de84e` and is spec-first: no code until Wire, Glyph and Ada confirm the spec.** Bay posted **S3-SPEC** (6:30 PM, D1–D26; no new rule ids, 17/36); Glyph confirmed the UI side. **Wire review (§1i): confirm with asks, 1 blocker (closed-app read source / corrupt store vs tests 58/61/62).** Not pinned: there's no branch yet. The `key=repr` gate has been met since `8d181ed`. Issue #41 doesn't block it.
   - **Prove's S3 gates:**
     1. **C5 (SETTLED, Ada 6:23 PM ET / 18:23; Prove's rewording):** a forged `step`/`actor` is stripped, gets `ignored_field` and never takes effect; there is no hard-reject rule. **PASS needs HTTP, ACP and MCP each to show:** (a) the write lands with the session's actor and step, and its history entry keeps no trace of the forged value; (b) the `ignored_field` warning names the field's path. **Edge case (Prove):** an exact retry carrying the same forged field gets the cached result plus the same warning, never `client_op_id_mismatch` (tests 70, 93, 94). *(The 6:19 PM wording flag is closed.)*
        - **Engine gap at `c6de84e` (for Bay):** replays return the original call's warnings (oplog.py L951, L1109–1110), and `Oplog.load` caches `warnings: []` (L1241). So the edge case is met live but fails after a reload, a retry that adds a forged field gets no warning, and one that removes it gets stale ones. Suggested fix: on a replay, return the cached result with `warnings` replaced by this call's strip warnings (L848). Test 93 (ii, iv, v) fails until then.
     2. An exact retry via /mcp **never** gives `client_op_id_mismatch`, including with a float `_s` (test 91) and NFD text (test 92); see also 76 and 87.
     3. The `_s` inputs (tests 65–67, 90).
     4. The §1g ordering calls (tests 88, 89).
     5. Tests 88–90 pass.
     6. **Byte-identical engine answers (Prove 18:47; widened by Ada 6:49 PM, then 6:56 PM ET):** at the S3 head, every engine answer for the same input must be byte-identical to `c6de84e`: `code`, `rule`, `path`, `id`, `op_index` and problem order. **The allowed differences are exactly these 12 (S3-SPEC §11):**
        1. the anchor-key check (D29, test 97);
        2. the C5 replay warnings: a retry gets its own strip warnings, live and after a reload, and stored warnings survive a reload (test 93);
        3. D4: `project_id: 5` gives `bad_arg`;
        4. **D17/D27, which parse input differently:** a bad line gets `-32700` and the server keeps running, HTTP gets 400, and output is written with `ensure_ascii=True` (tests 101, 102);
        5. (A) the history arg checks (D19);
        6. (B) the history return shape (D19);
        7. (C) `hash` in `history_diff` records (D10);
        8. (D) the conflict-diff cap and `history_diff_truncated` (D19);
        9. (E) corrupt `base.json` (D28; tests 61, 62);
        10. (F) a corrupt log line, and the torn tail (D28, D2; test 61(d));
        11. (G) a missing `project_id` gives `missing_arg` (D4);
        12. (H) D15's protocol answers.

        **Any other difference is a FAIL.** Prove verifies it by replaying the S2/S2b fuzz corpora and regressions against both commits. The 6:51 OPEN items (D10, D19, D2) are **closed** by this list.

**Bay: PR #38 (crossfade ripple trim), MERGED**
1. **Head SHA:** merged from `36f8a87` as main `a1922f0` (same tree, `286177f`). No mismatches (§1d). Its doc rulings follow in the follow-up PR.

**Bay: PR #37 (S2), MERGED**
1. **Head SHA:** merged from `480a220` as main `e274051` (same tree, `d924c0e`). No further re-pin; re-check §1c against the follow-up PR when it opens.
3. ~~The non-list `ops` retry crash and the `split_clip` path~~ are fixed at `480a220`. `key=repr` in `_apply_one` (L700 at `480a220`) is **fixed in #39** (`dc20a2c`), on main since `8d181ed`.
2. ~~Fix §1c mismatches 1–6.~~ All resolved at `c2a930f`.

**PLANNED (no field, no test):** a `export_otio` warning when any tick value is above about 7×10¹⁵ (OTIO 0.18.1 JSON read-back bug; Ada: warn, don't fix). It goes with whichever slice first touches `to_otio()`, not S2 or S2b.

**Slice 2 notes**
- **Anchors after edits:** Bay's note says deleting a V1 clip must remove anchored items or convert them to `at` (test 53). Still open: which piece of a split V1 clip keeps its anchored items?
- **Splits at speed ≠ 1:** `split_clip` must pick tick positions where both halves have whole-tick durations. Decide whether the tool snaps or returns `non_integer_duration`. My default is to return the error and never round silently.
- **Fade and anchor ops:** new `set_fade`/`set_anchor` ops, or a generic `set_fields`? `set_props` doesn't cover top-level fields. `set_fade` must cover text items.
- **`media.proxy` in the hash:** a finished proxy job changes the hash without an op (Bay's note). That affects `get_hash` stability and conflict detection on the Wire side.
- **Per-op MCP tools:** revisit once the S2 op set is final. Phase 1 ships `timeline_apply` only.
- **Frame index in time outputs (proposal, not Slice 1):** tool outputs could add `frame` (= ticks ÷ `ticks_per_frame(fps)`) next to `ticks` and `seconds`.
- **otiotool at 705600000/s:** `--stats` and `--list-markers` fail at this rate. A frame-rate export would fix `--stats` but wouldn't round-trip. Until it's decided, no contract test relies on them.
- **Overlay role:** Bay proposes `overlay` (V<n>, n ≥ 2) for `hs.timeline/2`. The registry's `add_track{role}` stays at the four roles until then.
