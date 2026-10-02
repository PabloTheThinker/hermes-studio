# PROVE-PR38: crossfade ripple-trim (PR #38)

**Verdict: PASS at 36f8a87** (36f8a876e88c20620b70f8bcb863d779d771592d)

Verified read-only by Prove on 2026-10-01; the final recheck was at 15:27 ET.
Evidence is in `evidence/prove-pr38/36f8a87/`.

## Checks

| # | Check | Result | Evidence |
|---|---|---|---|
| 1 | Head SHA, commits and diff scope | PASS | 1-graph.txt, 1-src-docs.diff |
| 2 | Ada's decisions 1–6 (own probes) | PASS, 39/39 | 2-3-probes.txt |
| 3 | Rule counts and docs | PASS | 2-3-probes.txt |
| 4a | Bay's property test, and with the fix reverted | PASS | 4-bay-property-revert.txt |
| 4b | Own fuzz, 1000 sequences | PASS: 0 crashes, 0 violations | 4-fuzz.txt |
| 5 | S2 regression scripts | PASS: 0 crashes | 5-s2-regression.txt |
| 6 | pytest, ruff, and new tests on e274051 | PASS | 6-pytest-ruff.txt, 6-new-tests-vs-e274051.txt |
| 7 | CI | PASS, with one caveat | 7-ci.txt, 7-ci-attempt1-test-job.log |

### 1. Head SHA, commits and diff scope
- **Head:** 36f8a87. The commits from e274051 are exactly [3c9c9d0, 36f8a87], and 3c9c9d0's parent is e274051.
- **No force-push:** all CI ran on 36f8a87, and the head was the same at the final recheck.
- **main:** e274051, tree d924c0e. The PR is 0 behind and 2 ahead.
- **Diff scope:** the diff against e274051 touches exactly docs/oplog.md, docs/timeline.md, hermes_studio/oplog.py and tests/test_oplog.py.
- **What the diff does** (all in scope):
  - `_OpError` gains `item_id`.
  - op_trim_clip runs the crossfade fit check before anything moves (about oplog.py:491–513). The ripple cut is start + old_dur − dout.
  - `_run` maps `item_id` to `id`.
  - The docs gain a new section and the rule count goes from 16 to 17.

### 2. Ada's decisions 1–6 (39/39)
- **Decisions 1, 2, 5 and 6:**
  - End and start trims, shorter and longer, keep the clip's start.
  - The outgoing crossfade, the next clips and items anchored to them all shift. The incoming crossfade and items anchored to the trimmed clip stay.
  - Ada's example gives changed_ids [c1,c2,c3,c4,mu,t12,t23,x1,x2,x4]. x2 is anchored to the shifted c2, so it belongs in the list.
  - Undo and redo restore the exact hashes and list the same set.
- **Boundary:** new_dur == din + dout is allowed and the clips abut.
- **Decision 3, every too-short variant:**
  - Covered: the outgoing crossfade too long (t23), the incoming one too long (t12, also through a start trim), each fitting alone but not together (names the outgoing one), and neither fitting (names the outgoing one). Outgoing-only and incoming-only timelines behave as ruled.
  - Each rejection is invalid_op/transition_too_long. The hash is unchanged and no log line is added.
  - As op 2 the error has path /ops/2 and op_index 2.
- **Decision 4:** a non-ripple end trim with an outgoing crossfade still gives transition_overlap_mismatch.
- **Music track:** ripple-trimming ma shifts mb and mc by −2 s (mc starts inside the overlap). m0 and tab stay. A too-short trim names tab.
- **Load and replay:** both reproduce the hash.

### 3. Rule counts and docs
- The docs list 17 op-level rules, including transition_too_long.
- The S1 validator `T.RULES` has exactly 36 rule ids.
- docs/oplog.md documents transition_too_long with rule, path, message and id at /ops/k.

### 4a. Bay's property test
- It passes at 36f8a87.
- With oplog.py reverted to e274051 it fails, rejecting with {transition_overlap_mismatch: 224, bad_transition: 11}.

### 4b. Own fuzz (1000 sequences)
- **Coverage:** 5046 ops applied, each with an undo/redo hash round trip. 3784 of them were ripple trims (1359 with an outgoing crossfade). 992 load/replay checks.
- **Oracle:** changed_ids had to cover every item whose start or end moved. An independent check also confirmed which crossfade transition_too_long named.
- **Rejection rules seen:**

  | Rule | Count |
  |---|---|
  | empty_range | 1160 |
  | bad_transition | 694 |
  | transition_overlap_mismatch | 686 |
  | transition_too_long | 442 |
  | bad_arg | 413 |
  | overlap | 85 |
  | fade_too_long | 27 |
  | negative_time | 10 |

- **Ripple trims rejected by a validator rule:** all 137 are ripple trims of m0 (no crossfade of its own), rejected with transition_overlap_mismatch. This was already happening before this PR (see Notes).

### 5. S2 regression
- c2c_probes: 132/132.
- c2b_junk: 0 crashes.
- c2b_probes: 76/76.
- c2_probes: 78/78. The old INFO "ripple trim of c1 with outgoing xfade" now says "applied", as this PR intends.

### 6. pytest, ruff, and new tests on e274051
- pytest: 636 passed. `ruff check .` is clean, and `ruff format --check` is clean on the changed files.
- New tests run against e274051: 21 of the 23 fail. The 2 that pass test unchanged behaviour:
  - the incoming crossfade staying put;
  - a non-ripple end trim being rejected.

### 7. CI
All times are ET (converted from UTC).

- **ci 36906747726, attempt 1:**
  - The test job was cancelled. Install ran 14:25:50–14:41:00, which matches the 15-minute timeout. Lint and Tests were skipped, so no tests ran.
  - The secrets job passed.
  - **Caveat:** the log can't tell apt from pip. The single Install step runs `apt-get update -qq && apt-get install -qq ffmpeg >/dev/null`, then two `pip -q` installs, and prints nothing before `##[error]The operation was canceled.` at 14:41:00. So "sat in apt-get install ffmpeg" can't be confirmed from the log. "Died in Install before pytest" is confirmed.
- **ci 36906747726, attempt 2:** passed.
  - Test job 14:42:14–14:43:41: Install 37 s, ruff "All checks passed!", "636 passed in 42.91s".
  - The secrets job was carried over from attempt 1.
- **desktop 36906747793:** passed. changes ✓, windows ✓ (14:25–14:34), linux ✓ (14:25–14:44). sources, release and publish were skipped.
- **CodeQL 36906742588:** passed.
  - Analyze jobs: python ✓, actions ✓, javascript-typescript ✓ (14:25–14:26).
  - Analysis uploads: actions 14:26:15, js-ts 14:26:24, python 14:26:47, each with 0 results.
  - The overall "CodeQL" check (github-advanced-security) passed, 14:26:14–14:26:17, "No new alerts in code changed by this pull request". It finished before the python upload.
- **Open code-scanning alerts:** 0 on refs/pull/38/head and 0 on refs/pull/38/merge. 3 open repo-wide, all pre-existing (#35–37, py/path-injection in studio.py).
- **Final recheck (15:27 ET):** head 36f8a87, OPEN, MERGEABLE, CLEAN.

## Bay's claims
- **Confirmed:** 636 tests pass; ruff is clean; 21/23 new tests fail on e274051; ci passed on attempt 2; desktop and CodeQL passed; the PR is CLEAN.
- **Not confirmable from the log:** that attempt 1 was stuck in apt specifically (the timing is right).

## Notes (non-blocking)
1. **Music track, older behaviour.** A ripple trim of m0 shifts mb, which overlaps ma and has a crossfade with ma, but not ma, so tab breaks. The trim is rejected as transition_overlap_mismatch and nothing is corrupted. It's the same at e274051 (scripts/p38_m0_preexisting.py) and may need a ruling from Ada.
2. A ripple trim with crossfades down to a zero or empty range is reported as transition_too_long, not empty_range, because the crossfade check runs first.
3. The Python-only TypeError at oplog.py:700 (from 480a220) is still there. No JSON or HTTP path reaches it.
4. The speed field isn't in the S1 schema, so the speed variant was skipped.

## Scripts
- Mine: `scripts/` holds p38lib.py, p38_probes.py, p38_fuzz.py and p38_m0_preexisting.py.
- S2 regression scripts used, from evidence/prove-s2/480a220/scripts/: c2lib.py, c2_probes.py, c2b_probes.py, c2b_junk.py and c2c_probes.py.
