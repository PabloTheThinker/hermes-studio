Post-S2 follow-ups (Ada's list, in order, one commit per item; item 3 is three commits). Base: main a1922f0.

## Commits
1. **dc20a2c `key=repr` on the unknown-arg sort** (`_apply_one`, plus the missing-arg sorts). If an op or call has a non-string arg name (`7`, `None`, `1.5`, a tuple, `True`, a frozenset), the result is now `invalid_op` / `unknown_arg`, not a `TypeError`. That holds for mixed key types too. The op path is `/ops/k/<str(key)>`. Covers `timeline_apply`, `history_undo` and `history_redo`. Test: `test_a_non_string_arg_name_is_unknown_arg_not_a_crash` (6 cases).
2. **5b899e7 #36 clean-test items.**
   - `clean-test-linux.sh`: a `cancelled` job fails on its first poll (`FAIL: … cancelled: …`).
   - `clean-test-linux.sh`: every curl has `--max-time` (`CURL_MAX_TIME`, default 10 s, for submit/poll; 5–10 s for the probes).
   - `clean-test-linux.sh`: `apt-get start/done: <UTC>` stamps around apt-get.
   - `clean-test-linux.sh`: the `clip-*.mp4` check is now a marked block the test runs.
   - Same curl/date changes in `clean-test-installer.sh`. `clean-test-windows.js` treats `cancelled` as final.
   - New tests:
     - cancelled job fails fast;
     - a wedged engine costs one bounded poll;
     - every curl is bounded;
     - apt-get is stamped;
     - poll limits (240/300, 2 s) and an exact-limit test;
     - `clip-*.mp4` check (5 cases: other mp4s don't count).
3. **S2 notes.**
   - **fca00a6 same-call equality = canonical JSON.** No `1`/`1.0`/`true` folding and no NFC/NFD folding. This is the same encoding as the log line and `canonical_hash`, which would also hash them differently.
     - A retry that differs only that way is `client_op_id_mismatch`. For the top-level `summary`/`base_version` it's the same `bad_arg` a fresh call gets, because shape checks run first.
     - NaN is never "same".
     - A fresh call can't carry these values at all (`not_integer_ticks`, `not_nfc`).
     - Documented in docs/oplog.md.
   - **13ae44f identical retry, capped.**
     - The doc and retired ids are checkpointed after every 16th entry, both live and in `load`. A retry re-runs ≤ 15 entries from the nearest checkpoint instead of replaying from base.
     - The result is identical. A property test (12 seeds × 30 entries with undo/redo and failures, live and after `load`) checks every checkpoint against a full replay.
     - Run counts are pinned per seq. Retries with omitted or engine-picked ids still match at every seq after `load`.
     - On a box with 500 entries, retrying the last entry took ~1.9 s before and ~30 ms after.
   - **1898681 junk `insert_clip.media`** (unknown string, empty, number, null, list, object, bool) → `invalid_op` / `unknown_media` at `/ops/k/media`, no `id`. Before, it was reported at the doc path. Existing timeline rule, so no new rule id.
4. **66522ec `timeline_apply` with `group_id: null` → `bad_arg` at `/group_id`** (Ada), fresh or on a cached key. Leaving the field out means no group. The old "null group" mismatch test case is now a different-group case, and the fuzz test leaves the field out instead of sending null. Docs updated.
5. **7842758 Doc-only rulings in docs/oplog.md**, with tests pinning current behaviour (no code change):
   - (a) A ripple trim never moves a neighbour that only overlaps the clip without a crossfade of its own. The `m0`/`ma`/`mb` case stays rejected with the **existing** `transition_overlap_mismatch`. This is a known limit; changing it would be an S4 decision.
   - (b) `transition_too_long` is checked before `empty_range`.
   - **No new rule id: 17 op-level, 36 validator.** A test now pins both counts against the docs and `T.RULES`.
6. **4bfd71f CI FFmpeg** (Rin's CI-FFMPEG.md, reviewed):
   - `ci.yml` drops apt ffmpeg and uses the BtbN static build pinned like desktop.yml (`autobuild-2026-09-30-13-08`, n9.0.2-17-g2a571b6068, sha256 `68ee6468…`).
   - Caching and checks:
     - `actions/cache` key = `ffmpeg-linux64-<version>-<sha256>`.
     - The sha256 and version are checked on a cache hit as well as a miss, so a bad cache entry fails the step.
     - libass is checked.
   - The step has a 3-minute timeout. Only an unreachable download (not a bad file) hands over to a hardened apt fallback step (4 minutes, apt timeouts and retries, prints `ffmpeg -version`).
   - pip has its own step: setup-python `cache: pip`, `--timeout 30 --retries 5`, visible output, 6-minute timeout.
   - `start/end` UTC stamps in each install step. Tests run `pytest -q -rs`, so an ffmpeg skip would show. Python 3.12.
   - Changes from Rin's draft:
     - version added to the cache key;
     - the apt fallback wired in only on an unreachable download;
     - the cache-hit flag passed via `env`, not inlined `${{ }}`;
     - curl retries bounded to fit inside 3 minutes;
     - the guard test made YAML-free.
   - `tests/test_ci_ffmpeg_pin.py`:
     - ci.yml pin/sha == desktop.yml;
     - the cache key has version + sha;
     - the sha check is not inside the miss branch;
     - apt only appears in the bounded fallback;
     - pip is its own step.
     - Shown failing on a deliberate sha mismatch and on a URL mismatch locally, then passing.
7. **c8e5604 apt fallback fails when ffmpeg didn't install** (Prove's finding). Before, the fallback step could exit 0 without ffmpeg: there was no pipefail and the loop ended on `sleep`. The step now runs under `set -euo pipefail` and checks `command -v ffmpeg`, failing with `::error::ffmpeg not installed after 3 apt attempts`. Only ci.yml changed.

## Counts
- Tests: **690 passed** locally (main a1922f0: 636). ruff check clean; ruff format clean on every changed file (the 38 files `ruff format --check .` flags are pre-existing on main).
- Rules: **17 op-level (oplog), 36 validator** — unchanged.

## CI evidence
All times ET (Oct 1). Step timings are from the Actions jobs API. Logs are saved under `/workspace/desk/hermes-studio/evidence/followup/`.

- **Before opening:** main a1922f0 push ci **36914624326** passed (CodeQL 36914623009 passed too).
- **Cache miss: ci 36917101183, attempt 1** (PR head 4bfd71f): passed.
  - `FFmpeg cache` 0 s: "Cache not found for input keys: ffmpeg-linux64-n9.0.2-17-g2a571b6068-68ee6468…".
  - `FFmpeg (pinned, sha256-verified)` **11 s** (3:49:27 → 3:49:38 PM). Log shows "cache miss, downloading …"; the download took ~1 s, then `ffmpeg.tar.xz: OK`, `ffmpeg version n9.0.2-17-g2a571b6068-20260930`, `libass ok`. Extracting from the .xz takes most of the ~10 s.
  - Apt fallback: skipped.
  - `Python deps` **19 s**; pip cache not found.
  - `Tests` 54 s: **690 passed** on Python 3.12.14, no SKIPPED lines (`-rs`).
  - Post: "Cache saved with key: ffmpeg-linux64-n9.0.2-17-g2a571b6068-68ee6468…".
  - test job 1m27s in total.
- **Cache hit: ci 36917101183, attempt 2** (re-run of the same commit): passed.
  - `FFmpeg cache` **2 s**: "Cache hit for: ffmpeg-linux64-n9.0.2-17-g2a571b6068-68ee6468…", 144 MB restored.
  - `FFmpeg (pinned, sha256-verified)` **9 s** (3:53:30 → 3:53:39 PM). Log shows "cache hit, using cached archive", then the sha256 `OK` again (it's checked on a hit too), the version and `libass ok`.
  - `Python deps` **15 s**; setup-python pip cache hit, 206 MB.
  - `Tests` 53 s: **690 passed**.
- **Apt fallback forced: ci 36917141392** on the throwaway branch `ci-probe/ffmpeg-fallback` (URL set to `https://127.0.0.1:9/…`). It failed, as allowed, **within its timeout**.
  - The pinned step failed over in **8 s** ("pinned FFmpeg download failed; falling back to apt", `fallback=true`).
  - The `FFmpeg (apt fallback)` step started at 3:49:52 PM. `apt-get update` took 2 s, but the Azure Ubuntu mirror served the 62.8 MB of .debs at about one package per second.
  - `timeout 150` killed attempt 1 at 3:52:28 PM. Attempt 2 started 3:52:38 PM, and the step's 4-minute timeout fired at 3:54:04 PM (**252 s**): "has timed out after 4 minutes".
  - Python deps and Tests were skipped.
  - So today's mirror really was slow, which is the stall this PR stops depending on.
- **Hang check: ci 36917166598** on the throwaway branch `ci-probe/ffmpeg-hang` (`sleep 600` at the start of the pinned step). The **3-minute step timeout fired**: started 3:49:57 PM, "The action 'FFmpeg (pinned, sha256-verified)' has timed out after 3 minutes" at 3:53:10 PM (**193 s**). The job failed in ~3 minutes instead of 15.
- Both probe branches were deleted afterwards. No PRs were opened for them.
- **Pin guard, run locally:** `tests/test_ci_ffmpeg_pin.py` fails when ci.yml's sha (`68ee…`→`69ee…`) or URL (autobuild tag) is changed to differ from desktop.yml ("FFMPEG_LINUX_SHA256: ci.yml and desktop.yml differ" / "FFMPEG_LINUX_URL: …"), and passes when restored (`evidence/followup/pin-test-mismatch.txt`).
- **Also checked locally** with the step script: miss, hit, a bad cache entry (one byte appended → `sha256sum … FAILED`, exit 1, no fallback) and unreachable (→ `fallback=true`).
- **desktop 36917101280: passed.** It ran on this PR because the clean-test scripts changed.
  - linux 5m36s: the clean test shows `apt-get start: 19:51:22Z` / `done: 19:52:00Z` (38 s), both jobs `completed` and `clips written: 2`. The installer test shows apt 37 s.
  - windows 8m09s.
- **CodeQL: passed** (36917097285, Analyze python/js/actions, plus the CodeQL check).
- PR state: MERGEABLE / CLEAN at 4bfd71f.

### After the fix commit c8e5604
- **ci 36927691250: passed.**
  - FFmpeg cache hit 3 s; pinned step 9 s ("cache hit", sha OK, `libass ok`); apt fallback skipped.
  - Python deps 13 s; Tests 44 s: **690 passed**.
- **desktop 36927691377: passed** (linux 4m49s, windows 7m56s).
- **CodeQL 36927686531: passed.**
- **Apt fail-fast forced: ci 36927759550**, on the throwaway branch `ci-probe/apt-fastfail` off c8e5604. BtbN URL unreachable, and the install asks for `ffmpeg-probe-no-such-package`. The branch was deleted afterwards, with no PR.
  - The pinned step handed over in 8 s.
  - All 3 apt attempts failed with `E: Unable to locate package` (5:18:39, 5:18:51 and 5:19:02 PM ET).
  - The step then **exited 1** with `##[error]ffmpeg not installed after 3 apt attempts` at 5:19:12 PM ET. The fallback step took **38 s**, mostly the 10 s sleeps. Python deps, Lint and Tests were skipped.
- **Without ffmpeg** (local, Python 3.12.14, PATH with no ffmpeg/ffprobe, `pytest -q -rs`): **689 passed, 1 skipped**. The skip is `SKIPPED [1] tests/test_look.py:61: ffmpeg not installed`; nothing fails. `test_doctor_json_shape` only checks the shape, so it passes either way. So a missing ffmpeg shows up as a skip, not a failure. In CI the FFmpeg steps now fail before tests run, so tests can't run without ffmpeg there.
- PR state: MERGEABLE / CLEAN at c8e5604.
