# PROVE-PR39: post-S2 follow-ups (PR #39)

**Verdict: PASS at c8e5604** (c8e5604ce43f718439022efaba901757fe29474a)
**4bfd71f: FAIL**, now superseded. With apt failing fast, its apt fallback step exits 0 with no ffmpeg installed. c8e5604 fixes that.

Verified read-only by Prove. Final recheck at 17:30 ET on Oct 1.
- Evidence is in `evidence/prove-pr39/4bfd71f/`. The directory keeps its original name; everything in it covers both 4bfd71f and c8e5604.
- All times are ET. API times are UTC, so ET = Z − 4 h.

## Checks

| # | Check | Result | Evidence |
|---|---|---|---|
| 1 | Graph, files, full diff | PASS | 1-full.diff, 7-ci.txt |
| 2 | Probes 2a–2f | PASS, 85/85 | 2-probes.txt |
| 3 | S2 and #38 regression scripts, fuzz | PASS: 0 crashes, 0 violations | 3-regression.txt, 3-fuzz.txt, 3-c2-fuzz-1200.txt |
| 4 | pytest on 3.12, ruff, revert counts | PASS | 6-pytest-and-no-ffmpeg.txt, 6-ruff.txt, 4-revert-counts.txt |
| 5 | ffmpeg CI against the 7-point bar | 4bfd71f FAIL (5d); c8e5604 PASS | 5d-fallback-exit-repro.txt, 5f-pin-test-mutations.txt, 7-*.log |
| 6 | CI on the head, main runs, CodeQL, alerts, final state | PASS | 7-ci.txt |

### The fallback-step finding (4bfd71f, `.github/workflows/ci.yml:78-86`)
**Repro.** I ran the step body exactly as it appears in ci.yml, under `bash -e` (the shell the runner used, per the log line `shell: /usr/bin/bash -e {0}`). The fakes were:
- an `apt-get` that exits 100 immediately;
- `sudo` that just runs its arguments;
- no ffmpeg on PATH.

**4bfd71f: exit code 0.**
- All 3 tries run, then `ffmpeg: command not found`, then `end:`.
- The cause is `ffmpeg -hide_banner -version | head -1` with no pipefail: the pipe's status is `head`'s, which is 0.

**The test suite without ffmpeg.** On a PATH that mirrors /usr/bin minus ffmpeg and ffprobe: 689 passed, 1 skipped (`tests/test_look.py:61: ffmpeg not installed`). So at 4bfd71f the ci job could go green with no ffmpeg at all. The only sign would be one SKIPPED line from `-rs`.

**c8e5604 fixes it.** It adds `set -euo pipefail`, a `command -v ffmpeg || ::error:: … exit 1` check, and `v="$(ffmpeg -version)"`. c8e5604's only parent is 4bfd71f, and it changes only ci.yml (+4/−1).
- **3a, apt fails at once:** Bay's claim holds. Each try is the single list `update && install && break`, and a failing command inside an `&&` list doesn't trigger `set -e`. All 3 tries run (10 s apart), then `::error::ffmpeg not installed after 3 apt attempts`, exit 1, after 30 s.
- **3b, try 1 fails, try 2 installs:** exit 0, and the step prints the version line.
- **3c, try 1's install stalls and `timeout` kills it:** the retry happens, try 2 installs, exit 0.
- **CI probe, run 36927759550 on `ci-probe/apt-fastfail`:** the probe commit e91a2cb differs from c8e5604 only in its probe edits (an unreachable URL, a nonexistent package, and a push trigger for `ci-probe/**`).
  - Handover took 8 s (14:18:26 → 14:18:34 Z-time, i.e. 5:18:26 → 5:18:34 PM ET).
  - All 3 tries logged `E: Unable to locate package ffmpeg-probe-no-such-package`.
  - Then `##[error]ffmpeg not installed after 3 apt attempts` and "Process completed with exit code 1" at 5:19:12 PM. The fallback step took 38 s.
  - Python deps, Lint and Tests were skipped, and the job failed. The branch is deleted.
- The job's 15-minute timeout still bounds the whole run. The step caps are 3, 4 and 6 minutes.
- **Non-blocking (Ada deferred it):** a needless 10 s `sleep` runs after the 3rd failed try.

## 1. Graph, files and diff
- The commits from a1922f0 (tree 286177f) are exactly: dc20a2c, 5b899e7, fca00a6, 13ae44f, 1898681, 66522ec, 7842758, 4bfd71f, then c8e5604. main is still a1922f0.
- No force-push: every CI run is on these SHAs.
- 9 files (+558/−29) through 4bfd71f: ci.yml, docs/oplog.md, oplog.py, the three clean-test scripts, test_ci_ffmpeg_pin.py, test_clean_test_script.py and test_oplog.py.
- I read the whole diff. Everything matches the commit list. Notes:
  - **dc20a2c.** `unknown_arg` now carries `(k,)` as its key. String keys give the same path as before (`/ops/0/zz`).
  - **fca00a6.** Same-call now compares with `_canon` (sort_keys, `(',', ':')`, `allow_nan=False`). The log line uses `_canon` too. The old code already told 1 from 1.0 and NFC from NFD, so the real change is small. That's why only 1 of its 6 new tests fails with the fix reverted.
  - **13ae44f.** Checkpoints hold a reference to the doc, not a copy. That is safe because `_run` deep-copies and the `doc` property returns a copy. The checkpoint is taken in `_commit` and in `load`.
  - **1898681.** See 2d.
  - **66522ec.** Docs and a one-line check. **7842758.** Docs and pin tests only.
  - **4bfd71f.** As described. The scripts and docs changes match Bay's list.

## 2. Probes (85/85)
**2a. Non-string arg names.**
- Each of 7, None, 1.5, (1, 2), True, frozenset and b'x' as an op key gives `unknown_arg` at `/ops/0/<str(k)>`. Nothing is applied.
- Mixed keys are sorted by repr, so `'zz'` comes before `7` and `None`.
- In one op, an unknown arg beats missing ones. `missing_arg` is ordered by repr.
- Non-string top-level keys on apply, undo and redo all give `invalid_op/unknown_arg`.
- c2b_junk: 0 crashes.

**2b. Same-call equality.**
- These all give `client_op_id_mismatch`: 1 vs 1.0, `ripple` True vs 1, nested 2 vs 2.0 in `props.volume`, and NFC vs NFD in a marker label.
- Key order at the top and in nested objects counts as the same call and returns the cached result.
- On a cached key: summary NFC vs NFD gives `bad_arg /summary`; base_version 0 vs 0.0 gives `bad_arg`; NaN gives a mismatch. No crash in any case.

**2c. Checkpoints.**
- 520 entries, mixing inserts with engine-picked ids, deletes of those ids, undos, and rejected batches in between.
- Every checkpoint equals a full replay of its prefix, and checkpoints sit exactly at every 16th entry.
- `_run` calls for an identical retry match the cap: entry 1 → 1, 15 → 15, 16 → 16, 17 (an undo) → 0, 31 → 15, 32 → 16, 33 → 1, 500 → 4, 520 → 8.
- **F1:** a retry of seq 258 that names its now-retired engine id c205 returns the cached result. Naming a different id gives a mismatch.
- **After load:** same checkpoint seqs and docs, and identical retries of all 70 entries return their results. Undo (17) and redo (18) retries return the cached results.
- **Timing, retry of entry 500:** 51 ms with checkpoints vs 3534 ms with only the base checkpoint.

**2d. `unknown_media` (in scope per Ada).**
- Media values tried, as op 0 and as op 1: 'nope', '', 5, 1.5, None, [], ['m1'], {'m1': 1}, {}, True and False.
- Each gives `invalid_op/unknown_media` at `/ops/k/media`, no id, `op_index` k. The hash is unchanged and no log line is written.
- Valid media on V1, A1 and A2 still applies. A bad track is still reported first (`not_found`). Valid media with an empty src is still `empty_range`.
- **This is not a crash fix.** At a1922f0 every one of those junk values already gave `unknown_media`, at the doc path `/tracks/1/items/6/media` with `id: c5`.
- No accepted input changes. The only change besides path and id: when an op has bad media and bad src or at, media is now reported first.

**2e. group_id null.**
- `timeline_apply` with `group_id: null` gives `bad_arg /group_id`, both fresh and on a cached key, with nothing applied.
- Omitting group_id applies with `group_id: null` on the entry. A string group applies.
- `history_undo` with `group_id: null` is still `bad_arg /group_id`, as ruled before.

**2f. Docs and counts.**
- Op-level rules: 17, the same set as a1922f0. `T.RULES`: 36.
- The docs carry the `transition_too_long`-before-`empty_range` ruling, the known limit under the existing `transition_overlap_mismatch` rule, `/ops/k/media`, and group_id null as `bad_arg`.

## 3. Regression and fuzz (0 crashes, 0 violations)
- S2 scripts:
  - c2_probes 78/78
  - c2b_probes 76/76
  - c2b_junk: 190 shapes × 4, 0 crashes
  - c2c_probes 132/132
  - c2_order: 1 distinct result over 50 runs; the sort order held on 2156/2156
- c2_fuzz 1200 sequences: 0 crashes, 0 violations, 2737 retries after load returned their cached results.
- #38 scripts: p38_probes 39/39. p38_m0 behaves as before (the documented known limit).
- p38_fuzz 1000 sequences: 0 crashes, 0 violations, 992 loads.
  - Rejection rules seen: empty_range 1160, bad_transition 694, transition_overlap_mismatch 686, transition_too_long 442, bad_arg 413, overlap 85, fade_too_long 27, negative_time 10.
  - All 137 ripple trims rejected by the validator are the m0 known limit.

## 4. pytest, ruff, revert counts
- pytest at c8e5604 on Python 3.12.14: **690 passed**. Without ffmpeg: **689 passed, 1 skipped** (test_look.py:61), which confirms Bay's figure.
- `ruff check .` is clean, and so is ruff on the CI paths.
- `ruff format --check` passes on the 4 changed .py files. Repo-wide, 38 files would be reformatted, the same 38 as on a1922f0.
- New tests failing with that commit's fix reverted:

  | Commit | New tests failing on revert |
  |---|---|
  | dc20a2c | 6/6 |
  | 5b899e7 | 10/11 |
  | fca00a6 | 1/6 (the others pin behaviour that already held) |
  | 13ae44f | 14/14 |
  | 1898681 | 9/9 |
  | 66522ec | 1/1 |
  | 7842758 | 0/4 (doc-only; these pin current behaviour) |
  | 4bfd71f | 3/3 (test_ci_ffmpeg_pin.py with ci.yml reverted) |

## 5. ffmpeg CI against the 7-point bar
- **a. sha256 on hit and miss.** Pass. The check runs after the hit/miss branch. The logs show `ffmpeg.tar.xz: OK` on the miss (4bfd71f attempt 1), the hit (attempt 2) and on c8e5604 (also a hit).
- **b. Cache key.** Pass. It is `ffmpeg-linux64-<version>-<sha256>`.
- **c. Real miss and hit logs.** Pass.
  - Miss, 36917101183 attempt 1: ffmpeg step 11 s (3:49:27–3:49:38 PM), download about 1 s, then OK, version n9.0.2-17-g2a571b6068, libass ok, and the cache saved.
  - Hit, attempt 2: restore 2 s (144 MB), step 9 s (3:53:30–3:53:39 PM).
  - c8e5604, run 36927691250: hit, step 9 s (5:17:54–5:18:03 PM), fallback skipped, deps 13 s, ruff "All checks passed!", **690 passed** on CPython 3.12.14.
- **d. Fallback within its timeout.**
  - **4bfd71f: FAIL** (see the finding above).
  - **Run 36917141392, as Bay described it.** There are two steps:
    - The pinned step (3-minute timeout) got 4 curl errors (7) and handed over after 8 s (3:49:44–3:49:52 PM).
    - The apt fallback step (4-minute timeout) started at 3:49:52. Try 1's install began at about 3:49:58, and "apt attempt 1 failed or stalled" appeared at 3:52:28. That is 150 s, consistent with `timeout 150`; the log itself says only "failed or stalled", not "timeout".
    - Try 2 started at 3:52:38. At 3:54:04 the log reads "has timed out after 4 minutes", naming the step: 252 s.
    - The job failed, with deps, Lint and Tests skipped.
  - **c8e5604: PASS** (3a–3c, plus the CI probe above).
- **e. Hang probe, 36917166598.** Pass. The 3-minute timeout fired at 193 s ("The action 'FFmpeg (pinned, sha256-verified)' has timed out after 3 minutes").
- **f. Pin test on mismatches**, checked on edited copies. It fails on:
  - the ci.yml sha;
  - the ci.yml URL tag;
  - the desktop.yml sha;
  - a version missing from the URL;
  - the sha missing from the cache key;
  - the sha check moved into a branch;
  - step timeouts 3→30 and 4→40;
  - pip `-q`.

  **Gap:** it still passes when the fallback body is put back to the buggy 4bfd71f version. Nothing guards the fix. Bay's `pin-test-mismatch.txt` matches what I saw.
- **g. 3.12 in CI.** Pass. CPython 3.12.14, 690 passed.
- **Probe branches:** `ci-probe/ffmpeg-fallback`, `ci-probe/ffmpeg-hang` and `ci-probe/apt-fastfail` are all deleted. Only `main` and `fix/post-s2-followups` remain.
- **Bay's saved logs** in `evidence/followup/` are in a different export format (lines prefixed `job<TAB>step<TAB>`). They have the same key lines as the logs I fetched.

## 6. CI on the head, main, CodeQL, alerts, final state
- **c8e5604:**
  - ci 36927691250 passed (test and secrets).
  - desktop 36927691377 passed: linux 5:17:53–5:22:42, windows 5:17:53–5:25:49; sources, release and publish skipped.
  - CodeQL run 36927686531 passed. The Analyze jobs (actions, python, javascript-typescript) ran 5:17:43–5:18:48.
  - Analysis uploads: actions 5:18:12, js-ts 5:18:31, python 5:18:39, each with 0 results.
  - The overall **CodeQL** check (github-advanced-security) passed 5:18:11–5:18:13 with "No new alerts in code changed by this pull request". It finished before the js-ts and python uploads.
- **4bfd71f:** ci, desktop and CodeQL (36917097285) all passed. Its overall CodeQL check also finished (3:49:52) before the python upload (3:50:13).
- **Alerts:** 0 open on refs/pull/39/head and 0 on refs/pull/39/merge. 3 open repo-wide, all older (#35–37 py/path-injection in studio.py).
- **main a1922f0:** ci 36914624326 and CodeQL 36914623009 passed.
- **Final (17:30 ET):** head c8e5604, OPEN, MERGEABLE, **CLEAN**.

## Notes (none blocking)
1. **No pin test covers the fallback exit.** A follow-up could assert that the fallback block contains `set -euo pipefail` (or `pipefail`) and a `command -v ffmpeg` check that ends in `exit 1`.
2. **Trailing `sleep 10` after the 3rd try** (ci.yml:85 at c8e5604). Ada deferred it to the next ci.yml PR. Suggestion: `[ "$i" -lt 3 ] && sleep 10`.
3. **No ffmpeg version or libass check on the fallback path.** apt installs ffmpeg 6.1.1, not the pinned n9.0.2. That's acceptable for a fallback, but tests would run on a different ffmpeg.
4. **Inner retries vs the step cap.** At worst 3 × (90 + 150 + 10) s, far more than the 4-minute step cap. The step cap is the real bound, and it worked (252 s).
5. **1898681 changes the error shape, not what's accepted.** Path and id change, and media is now reported before bad src or at.
6. **fca00a6 is mostly a refactor.** The behaviour visible in my probes was the same at a1922f0, including the NaN mismatch.
7. Harmless BrokenPipe tracebacks from the fake server in `test_clean_test_script.py` show up in the no-ffmpeg run. All tests passed.

## Scripts
- `scripts/` has: p39_probes.py, p38lib.py, run.sh (the fallback harness), step-old.sh, step-new.sh, fallback-fakes-bin/ (apt-get, sudo, timeout), revert.sh and pyt.sh.
- Also re-run: the S2 scripts in `evidence/prove-s2/480a220/scripts/`, and the #38 scripts in `evidence/prove-pr38/36f8a87/scripts/`.
