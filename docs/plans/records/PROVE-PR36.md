# PROVE-PR36: clean-test polls its own job id (PR #36)

- **Verifier:** Prove, working independently and read-only. Nothing was pushed, commented, merged, tagged or dispatched.
- **When:** Thu Oct 1 2026, 11:55 AM to 12:05 PM ET.
- **PR:** #36 `fix/clean-test-own-job-id`. Head `b315936c7325019e344a60c31ebeee2ef96a677b`, checked at 11:55 AM and 12:03 PM ET; it did not move.
- **Main:** `bbb7216` (the #35 squash).
- **Evidence:** `evidence/prove-pr36/`. My own scripts are in `evidence/prove-pr36/scripts/`.
- **Scratch:** `/workspace/scratch-prove-pr36`, deleted at the end.

## Overall: **PASS**

The 13-minute clean-test step is not caused by the new polling. All of the extra time (about 11 min 20 s) passed before the engine came up, which is before the job helpers run at all. The polling phase itself took the same time as on #36's first run: 57 s vs 57 s.

| # | Check | Verdict | Evidence |
|---|-------|---------|----------|
| 1 | Head, graph, diff, merge tree; pytest, ruff, shellcheck | PASS | 0-pr.txt, 1-graph-diff.txt, 1-tests.txt, 1-shellcheck.txt |
| 2 | Script review, helpers against my fake engine and the real engine, Bay's tests and mutation check | PASS, with 3 notes | 2-*.txt |
| 3 | Timing (Ada's question) | PASS. The extra time is outside the polling; the most likely cause is the container's apt step. | 3-steps.txt, logs/, artifacts/ |
| CI | ci, desktop, CodeQL, alerts | PASS | 0-ci.txt |

## 1. Head, graph, diff and merge tree
- **Merge commit:** b315936 has two parents: 39794a4 (the previous head, whose parent is 1d14e01) and bbb7216 (main, tree a640150).
- **No conflicts or hand edits:** b315936's tree `4a38268` is exactly the result of a fresh `git merge-tree --write-tree 39794a4 bbb7216`.
- **No rebase:** 39794a4 is an ancestor of the head.
- **Ahead/behind:** 2 ahead of main, 0 behind; GitHub reports the PR as clean.
- **Diff vs main:** the three-dot and two-dot diffs against main are both only `scripts/clean-test-linux.sh` and `tests/test_clean_test_script.py`.
- **The merge changed nothing in the PR's own files:** both are identical at 39794a4 and at the head.
- **pytest:** 366 passed locally (Python 3.12, `.[reframe,dev]`); Bay's 6 clean-test tests pass.
- **ruff:** clean.
- **shellcheck 0.11.0:**
  - The helper block passes `shellcheck -s sh` with no findings, and `dash -n` is OK.
  - The full script gives SC2016 (info), because the `su tester -c '…'` body is single-quoted on purpose.
  - The inner body, checked as sh, gives SC2034 for the unused `i` in the engine-port loop.
  - main's script gives the same two findings, so the PR adds no new ones.

## 2. Script review
- **Own job only:** both `head -1` list loops are gone. `submit_job` takes the id from that submit's own response and accepts it only if it matches `[A-Za-z0-9_-]+`. `wait_job` polls only `GET /api/jobs/<that id>`.
- **Clear failures, all `exit 1`, each with a FAIL message:**
  - no id
  - 404 (the job is missing)
  - status `failed` (the message includes the job's error)
  - the poll limit is reached (the message gives the last status and the last HTTP code)
- **Plain sh:** the helpers run under tester's `/bin/sh`. On ubuntu:24.04 that is dash, because useradd's default SHELL is `/bin/sh`.
- **Same limits as the old script:** 240 polls for captions and 300 for clip, 2 s apart (`POLL_SLEEP` defaults to 2).
- **clip-\*.mp4 check:** still present and still fatal.
- **The limit knobs:** the poll limit is wait_job's second argument, and the sleep comes from the `POLL_SLEEP` environment variable. Under `su` the variable isn't passed, so it stays at 2 in CI.

### My fake engine (`2-helpers-fake-engine.txt`): 30/30 pass
These runs use the real helper block, extracted from the script, under dash. The fake engine mimics the field order of `studio.py` responses (id first, then status).
- **Stale finished job listed first:** ignored. Only `/api/jobs/<own id>` was requested, 5 times, until the job completed. A list saying "completed" while the job's own record says "running" is also ignored.
- **Submit with no usable id:** exits 1 with no polling. Covered: a 400 response, a response without a job, an empty body, a numeric id, a null id, an empty id.
- **Malformed ids:** `../etc`, `a b`, `a.b`, `a?x=1` and an HTML 502 page are all rejected as "no job id". Truncated or compact JSON that still contains an id is used.
- **404:** both an immediate 404 and one that appears mid-run produce the "is missing" failure.
- **Failed status:** "failed" with the error text.
- **No early exit on nested status:** a nested `clips[].status: completed` does not end the wait.
- **Never finishes:** with a limit of 5, it stops after exactly 5 polls with "did not finish after 5 polls (last status: running, last HTTP: 200)". `POLL_SLEEP=1` × 3 polls took 3.5 s.
- **Polling that never gives a status:** a 200 with non-JSON times out with "last status: none, last HTTP: 200". If the engine dies, it times out with "last HTTP: 000". A transient 500 is retried.

### The real engine (`2-helpers-real-engine.txt`)
I ran `hermes_studio studio` at b315936 under a scratch HOME and drove it with the helpers under dash:
- **Nonexistent src:** the engine answers 400, and the helpers stop with "submit returned no job id".
- **Garbage .mp4:** the job fails in ffmpeg, and the helpers print "FAIL … failed: "error": …" and exit 1.
- **Unknown id:** 404.
- **Real captions job:** a 15 s test video completed, with the default 2 s sleep.

### Mutation check of Bay's tests (`2-mutation.txt`)
Every helper mutant is killed:

| Mutant | Bay tests failing |
|--------|-------------------|
| M1: `head -1`-style list polling | 4 |
| M2: the same, disguised so the "no list grep" test can't catch it | 3 |
| M3: id taken from the list instead of the submit | 6 |
| M4: failed treated as done | 1 |
| M5: 404 ignored | 1 |
| M6: timeout returns 0 | 1 |
| M7: no id not fatal | 1 |
| M8: off-by-one on the poll limit | 1 |

Three mutants outside the helpers survive Bay's tests, though my own checks above cover them:
- M9: clip-\*.mp4 check removed
- M10: captions limit 240 → 24
- M11: `POLL_SLEEP` default 2 → 20

### Notes (not fails)
1. **No fast-fail on `cancelled`.** The engine has a `cancelled` status, and wait_job keeps polling it until the limit: 8 min for captions, 10 min for clip. The clean test never cancels a job, so this is cosmetic. Suggestion: `cancelled) … exit 1`.
2. **No curl timeout.** curl has no `--max-time`, so a GET that is accepted but never answered blocks wait_job; my run was still blocked after 8 s. The old script had the same gap, and the CI job timeout still bounds it.
3. **Bay's tests don't pin the limits.** They don't check the poll limits, the `POLL_SLEEP` default or the clip-\*.mp4 check. I checked those directly.

## 3. Timing: where did the 13 minutes go?
**What the logs can and can't show.** The step's container output is piped through `grep | tee`, so every line from inside the container carries the same timestamp, the one at the end of the step. To split the step, I used:
- the zip entry times of the `linux-test` artifact files: `clean-01-open.png` is written about 4 s after the engine port answers, and `clean-02-after-job.png` 3 s after the clip job completes;
- each job's `created_at` from the submit responses;
- the step timestamps from the API.

All times are ET.

| Phase (linux job) | #36 first run: desktop 36880765772 @39794a4 (new script, no OTIO) | #35 baseline: desktop 36882413422 @b1b51c1 (old script, with OTIO) | This run: desktop 36885610328 @b315936 (new script, with OTIO) |
|---|---|---|---|
| Runner queue (job created → started) | 2 s (10:59:55 → 10:59:57) | 2 s | 7 s (11:36:56 → 11:37:03) |
| Setup steps 1–8 (checkout, uv, FFmpeg, build engine, AppImage, notices) | 1:41 | 1:41 | 1:39 |
| — of which Build engine (installs opentimelineio 0.18.1 from a wheel, no source build) | 5 s (no OTIO) | 5 s | 5 s |
| Clean-test step total | **1:42** (11:01:39 → 11:03:21) | **3:02** (11:14:11 → 11:17:13) | **13:03** (11:38:43 → 11:51:46) |
| — before the engine is up: image (already cached), apt-get update/install, AppImage extract, Xvfb, engine start, port wait, 4 s sleep. No polling code runs yet. | **0:39** (→ open.png 11:02:18) | **1:59** (→ 11:16:10) | **11:59** (→ open.png 11:50:42) |
| — captions job: submit → completed, polled by id every 2 s | 0:33 (11:02:19 → clip submit 11:02:52) | 0:58 for both jobs, old list polling (11:16:10 → after-job.png 11:17:08) | 0:34 (11:50:43 → clip submit 11:51:17) |
| — clip job: submit → completed (+3 s sleep before the screenshot) | 0:24 (11:02:52 → 11:03:16) | (included above) | 0:23 (11:51:17 → 11:51:40) |
| — teardown, quit check, ldd library check | 0:05 | 0:05 | 0:06 |
| Polls used, estimated at about 2 s each, vs the limit | captions ≈16 of 240, clip ≈11 of 300 | n/a | captions ≈16 of 240, clip ≈10 of 300 |
| Next step, installer test (also an apt-get in a fresh ubuntu:24.04) | 2:49 | 1:48 | 1:19 |

**Conclusion.**
- **Not the polling.** The polling phase took 57 s in this run against 57 s in #36's first run, and the old script's 58 s on main. No job was waited out to its timeout or polled under the wrong id. Each wait ended about 1 s after its job finished, which is within one 2 s poll.
- **Not the engine job.** Captions took 34 s and clip 23 s, the same as before.
- **Not the runner or the install.** The runner queue was 7 s. Setup, including the opentimelineio wheel, took 1:39.
- **So the time went before the engine was up.** All of the roughly 11:20 extra falls in the pre-engine phase, from 11:38:43 to 11:50:42 ET.
- **The bounded parts can't explain it.** The engine-port wait is capped at 90 tries of about 1 s, and the fixed sleeps add 6 s, which is at most about 1:40.
- **The most likely cause is the container's `apt-get update` and `install` from the Ubuntu archive.** It is the only network step in that phase, and it shows how variable it is across the three runs: 0:39, 1:59 and 11:59.
- **The archive had recovered by the next step.** The installer test, which repeats an apt-get in a fresh container, ran normally right afterwards (1:19).
- **The logs can't prove apt directly.** The container's lines carry no timestamps of their own. If Ada wants proof next time, a `date` stamp before and after `apt-get` in clean-test-linux.sh would show it.
- **Under Ada's rule this is the runner or network, not the new polling: PASS.**

## CI at b315936 (`0-ci.txt`)
- **ci 36885610287:** test (366 passed on merge ref 072e10e, b315936 merged into bbb7216; ruff clean) and secrets both succeeded.
- **desktop 36885610328:** changes, linux and windows succeeded. sources, release and publish were skipped.
- **CodeQL 36885603364:** Analyze for actions, python and javascript-typescript all succeeded. All three runs passed on attempt 1.
- **Overall CodeQL check**, reported separately from the Analyze jobs: success, "No new alerts in code changed by this pull request", concluded at 11:37:14 AM ET.
- **Upload timing:** the analyses uploaded at 11:37:12 (actions), 11:37:28 (python) and 11:37:34 (javascript-typescript). As on #35, the overall check concluded before 2 of the 3 analyses existed. All three are uploaded now, each with 0 results.
- **Alerts:** 0 open, 0 dismissed and 0 fixed on refs/pull/36/head, refs/pull/36/merge and the branch. Repo-wide open alerts are only #35–37 (py/path-injection in studio.py on main), all pre-existing.
- **Bay's claim about the Linux clean test is confirmed from the job log** (`logs/linux-b315936-*.log`): "captions job id: 2e2a203deb18 … completed", "clip job id: 7d22e55762d9 … completed", clip-01.mp4 and clip-02.mp4 written, and "LINUX CLEAN TEST PASSED".
