# PROVE-S1: gate C1, Hermes Studio Slice 1 (PR #35)

> **Current verdict (Thu Oct 1 2026, 11:32 AM ET): PASS at b1b51c1.** See the "Re-verify at b1b51c1" section at the end, which includes one note for Ada. The FAIL below is the original run at fbbb2c0 and is kept for the record.

- **Verifier:** Prove, working independently and read-only. Nothing was pushed, commented, merged, tagged or dispatched.
- **Date:** Thu Oct 1 2026, about 10:50 AM to 11:05 AM ET.
- **PR:** #35 `feat/editor-s1-timeline`. Head `fbbb2c048ec66060946cd5535a9649d3a2fd4039`, re-checked at 11:02 AM ET and unchanged.
- **Base:** main `1d14e01a29e6cf21483f057c9f71affd7a1c0d1d`.
- **Evidence:** `evidence/prove-s1/`. My own scripts are in `evidence/prove-s1/scripts/`.

## Overall: **FAIL** (one validator crash; small fix). The rest of the checklist passes.

`validate()` crashes when a track's `role` is unhashable, such as a list or object. It raises `TypeError` instead of returning `bad_track_role`.

Because of this:
- `canonical_hash()` and `stamp_hash()` raise `TypeError` rather than `TimelineError`.
- This breaks the locked contract "validate() returns list of {rule,path,message,id?}".
- This is exactly the "unchecked inputs" class the C1 code review covers.

Minimal repro (`evidence/prove-s1/repro-unhashable-role.txt`):
```python
from hermes_studio import timeline as T
d = T.new_timeline("p"); d["tracks"][0]["role"] = []
T.validate(d)   # TypeError: unhashable type: 'list'  (timeline.py:366 `if role not in ROLES:`)
```
The same happens for `{}`, `["main"]` and `{"x": 1}`.

Suggested fix: `if not isinstance(role, str) or role not in ROLES:`.

My 20,000-mutation fuzz (`c1-fuzz.txt`) found no other validator crash. All 129 crashes it hit were this one: 80 list, 49 dict.

## Per-item verdicts

| # | Item | Verdict | Evidence |
|---|------|---------|----------|
| 1 | Rejections, one bad doc per rule id, right path | PASS on all 36 rules (47/47 checks). The unhashable-role crash above is a separate bad-input case. | c1-items-run.txt (item 1) |
| 2 | Hash equality: shuffles, anchored items, 0.1+0.2 | PASS 14/14. 300 shuffles give 1 hash; 200 anchored shuffles give 1 hash; six spellings of 0.1+0.2 / 0.3 all give 211680000 ticks and 1 hash. | c1-items-run.txt (item 2) |
| 3 | Exact ticks at 23.976, 24, 25, 29.97, 30, 60 fps and 48 kHz | PASS 21/21 | c1-items-run.txt (item 3) |
| 4 | Version, NFC, unknown fields | PASS 25/25. Another schema_version fails validate and canonical_hash raises; schema_version appears in the canonical bytes; not_nfc and unknown_field are rejected. | c1-items-run.txt (item 4) |
| 5 | Tick rate 705600001 and missing tick_rate | PASS 8/8 (bad_tick_rate) | c1-items-run.txt (item 5) |
| 6 | canonical_hash raises on a bad doc for every rule id | PASS 46/46, all raising TimelineError, including a doc whose only fault is hash_mismatch. Not covered: the role-crash input, which raises TypeError. | c1-items-run.txt (item 6) |
| 7 | Excluded fields (hash, version); stale hash fails | PASS 7/7 | c1-items-run.txt (item 7) |
| 8 | stamp_hash | PASS 49/49. It raises for every other rule; its output validates, and canonical_hash equals the stored hash. | c1-items-run.txt (item 8) |
| 9 | fps: required, bad value, changes hash, 29.97 frame not whole ticks | PASS 12/12 | c1-items-run.txt (item 9) |
| 10 | Drift: no `schema` key, no `overlay` role | PASS. Only negative tests mention them: test_timeline.py:171 (old `schema` key, which must fail bad_schema), :215 (`overlay` role, which must fail bad_track_role) and :557 (asserts `schema` is absent). Every other `overlay` hit is ffmpeg/blend code that predates this PR. The `schema=` hits are Hermes plugin tool schemas, unrelated. docs/timeline.md has neither. | 10-drift.txt |
| 11 | Paths, ids, escaping, duplicates | PASS 58/58, with a note below. Every path resolves segment by segment; ids name exactly one valid item (using dotted ids such as c.2, x.1, k.2, mu.2); m/1 → `/media/m~11`, m~1 → `/media/m~01`, a~/b → `/media/a~0~1b`; 3 copies give 2 duplicate_id errors at the 2nd and 3rd copies, without id. | c1-items-run.txt (item 11), c1-fuzz-shape.txt |
| 12 | Zero or two main tracks | PASS 4/4. Zero gives missing_main_track; a second V1 gives duplicate_id; a main track named V2 gives bad_track_id. All three are stable. | c1-items-run.txt (item 12) |
| 13 | Anchors and fades | PASS 23/23, using Bay's tests plus my own probes: negative and too-long fades, text fades, anchors on a non-main target, chained anchors and negative offsets. | c1-items-run.txt (item 13) |
| 14 | otiotool | PASS. Details below. | 14-otiotool.txt, otio/ |

### Item 14 details
- `to_otio(base())` is read by OTIO 0.18.1.
- `from_otio(read(file)) == normalize(doc)`.
- `otiotool -i ours.otio -o rt.otio` gives byte-equal JSON, from_otio equal to normalize, and an equal canonical_hash.
- All other otiotool commands exit 0: list-clips, tracks and media; verify-media and verify-ranges; inspect; list-versions; video-only and audio-only; the only-tracks and only-clips filters (×4); remove-transitions and remove-effects; trim; flatten video, audio (keep) and all; stack; concat; relink-by-name; copy-media-to-folder; remove-metadata-key; redact; downgrade 0.14.0; and `-o -`.
- `--stats` and `--list-markers` fail with `ValueError: SMPTE timecode does not support this rate`.
- **Control holds:** a hand-written raw-JSON .otio at 705600000/s, with none of our code (one clip, one marker), fails both commands with the same exit code (1) and the same final error line. The same control file at 24/s succeeds.
- Under Ada's ruling this is a Slice 2 note, not a C1 fail.

## CI at fbbb2c0 (`0-ci.txt`)
- **Check runs, all success:** test, secrets, changes, linux, windows, sources, Analyze ×3, and the overall CodeQL check ("No new alerts in code changed by this pull request"). release and publish were skipped, as intended.
- **Workflow runs:** ci 36877179045, desktop 36877179032 and CodeQL 36877173178. All succeeded on attempt 1.
- **Overall CodeQL check, reported separately from Analyze:**
  - The check concluded at 10:33:21 AM ET.
  - The analyses uploaded at 10:33:19 (actions), 10:33:33 (python) and 10:33:54 (javascript-typescript). So 2 of the 3 analyses arrived after the check concluded.
  - All 3 analyses for fbbb2c0 were uploaded and report 0 results.
- **Code-scanning alerts on the PR ref:** 0 open, 0 dismissed, 0 fixed. Repo-wide open alerts are only #35–37 (py/path-injection in studio.py on main), all pre-existing.
- **CI test job:** ran on merge ref ad67f09 with 311 passed and ruff clean.

## Diff and merge with main (`0-diff.txt`, `0-merge.txt`, `0-pytest-*.txt`)
- **Diff:** `git diff 1d14e01...fbbb2c0` (merge base 074c8a7) is exactly the 11 expected files. The two-dot diff also lists pipeline.py and test_job_manifest.py only because the branch is behind main.
- **Merge:** my local test merge of 1d14e01 into fbbb2c0 is commit 92d1280, with no conflicts and nothing pushed.
  - Its tree, c0fba548, is identical to CI's merge ref ad67f09.
  - `git diff 1d14e01 <merge> -- pipeline.py tests/test_job_manifest.py` is empty.
- **pytest:**
  - fbbb2c0: 299 passed (140 in test_timeline.py).
  - Merge: 311 passed (140 timeline).
  - ruff is clean on both.
  - RULES has 36 unique ids, confirming Bay's counts.
- **PR state:** `mergeable_state: behind`. Branch protection is strict, so the branch must be updated before merge.

## Code review and notes (not C1 fails unless stated)
1. **FAIL:** the unhashable `role` crash described above.
2. **Spec wording, for Ada to rule on:**
   - `seconds_to_ticks` rounds half-to-even only for a float, using its exact binary value.
   - For an exact int, Fraction, Decimal or str that is not a whole number of ticks (for example `Fraction(1, 2*705600000)`), it raises ValueError instead of rounding.
   - This behaviour is documented in docs/timeline.md:119, but the locked spec says "rounds half-to-even".
3. **Missing `id` or `type` on an item:**
   - A missing `id` reports both `wrong_type` and `missing_field` at the same path.
   - A missing `type` reports only `wrong_type`, at a path that names the absent key.
   - That is allowed by the documented "missing field pointer names the field" rule, but the rule id should be `missing_field`. Cosmetic. (`c1-fuzz-shape.txt`, 597 cases, all of this kind.)
4. **Exactness at extreme ranges (Slice 2 note):** MAX_TICKS = 2^53 bounds each field, not sums or OTIO parsing.
   - Above about 7×10^15 ticks (about 118 days), OTIO's JSON reader gets odd values wrong by about 1 tick. For example, at = 9007198549140991 reads back …990. This is OTIO's own behaviour (`probe-otio-json-precision.txt`). The in-memory round trip is exact.
   - With speed [1,10] and src out = 2^52+1, the timeline duration exceeds 2^53. The doc validates, but to_otio → from_otio raises ValueError.
   - Media fps numerator 2^63 validates, but to_otio raises ValueError (out of OTIO's int64 range).
   - So the comment at timeline.py:30, "every tick count up to this is exact", only holds for in-memory OTIO. Suggestion: bound media fps, and item end or span, to a safe limit. (`probe-big*.txt`, `probe-speed.txt`)
5. **Media fps** is checked only as a positive reduced rational. Whole ticks per frame are enforced only for the top-level fps; for example, media fps [2997,100] is accepted. This matches the spec, which only covers the top-level fps; noted only.
6. **Floats:**
   - The doc itself has no float paths.
   - `to_otio` writes LinearTimeWarp `time_scalar = sp[0]/sp[1]` as a float. The exact speed is kept in metadata, and from_otio uses that metadata. Speeds [1,3] and [7,3] round-trip exactly.
   - `_ticks` uses `rescaled_to(TICK_RATE).value`, which is exact at our own rate.
7. **License and NOTICE: PASS** (`license-check.txt`).
   - The OpenTimelineIO.txt LICENSE and NOTICE sections match the wheel's dist-info/licenses files, apart from blank-line and whitespace differences.
   - The Imath, RapidJSON and pybind11 texts match the upstream files at the exact submodule SHAs pinned by OTIO v0.18.1 (fbcfb98, 24b5e7a, a2e59f0), ignoring whitespace.
   - NOTICE has an OpenTimelineIO 0.18.1 section that reproduces OTIO's NOTICE, plus the OpenCut classic MIT attribution with the full permission text.
   - The pins agree across pyproject (`>=0.18.1,<0.19`), engine-constraints (`==0.18.1`) and the build-script NOTICE asserts.

## Independent harness
My own scripts are in `evidence/prove-s1/scripts/`, all written for this run:
- `c1lib.py`: base doc with dotted ids, a strict RFC 6901 resolver and problem-shape checks.
- `c1_items.py`: items 1–9 and 11–13.
- `c1_fuzz.py`: 20k random mutations.
- `fz3.py`: groups the problem-shape exceptions.
- `c1_otio.py`: item 14 plus the controls.
- `c1_probe_*.py`: range and speed probes.

They ran in a scratch venv with `.[reframe,dev]` and opentimelineio 0.18.1.


---

# Re-verify at b1b51c1 (Thu Oct 1 2026, 11:23 AM to 11:32 AM ET)

- **Head:** `b1b51c117795f56924e12a89fc7bc88fe5dcf3e6`. Checked at 11:23 AM ET and again at 11:32 AM ET; it did not move.
- **Main:** still `1d14e01`.
- **Ground rules:** read-only. Nothing was pushed, commented, merged, tagged or dispatched.
- **Evidence:** `evidence/prove-s1/b1b51c1/`. Scripts are in `evidence/prove-s1/b1b51c1/scripts/`.
- **Scratch:** `/workspace/scratch-prove-s1b`, deleted at the end.

## Overall: **PASS** (one note for Ada, which is not a crash and not a silent acceptance)

| # | Check | Verdict | Evidence |
|---|-------|---------|----------|
| 1 | Head, CI, merge state | PASS. Details below. | 0-pr.txt, 0-ci.txt |
| 2 | Diff vs main, commit graph | PASS. Details below. | 0-diff-graph.txt |
| 3 | pytest, ruff, rule ids | PASS. 360 passed (189 in test_timeline.py); ruff 0.16.9 clean; 36 unique rule ids, out_of_range reused and no new id. | 3-pytest.txt |
| 4 | My C1 scripts and fuzz | PASS. Details below. | 4-*.txt |
| 5 | The rulings | PASS, 93/93 checks, with one note for Ada. Details below. | 5-rulings.txt, 5-probe-*.txt |
| 6 | otiotool (item 14) | PASS, 34/34. Details below. | 6-otiotool.txt, otio/ |

### 1. Head, CI and merge state
- PR state: open, `mergeable_state: clean`. The PR body was updated at 11:23:05 AM ET; it covers seconds_to_ticks_nearest, the 2^53 cap (out_of_range vs too_large) and missing_field (0-pr-body.txt).
- **Runs:** ci 36882413402 (test, secrets), desktop 36882413422 (changes, linux, windows, sources; release and publish skipped) and CodeQL 36882406311 (Analyze for actions, python and javascript-typescript). All succeeded on attempt 1 for head b1b51c1.
- **Overall CodeQL check:** success, "No new alerts in code changed by this pull request", completed at 11:12:51 AM ET.
- **Upload timing:** the analyses were uploaded at 11:12:50 (actions), 11:13:04 (python) and 11:13:06 (javascript-typescript). As at fbbb2c0, the overall check concluded before 2 of the 3 analyses existed. All three are uploaded now, for refs/pull/35/head, with 0 results.
- **Alerts:** 0 open, 0 dismissed and 0 fixed on refs/pull/35/head, the merge ref and the branch. Repo-wide open alerts are only #35–37 (py/path-injection in studio.py on main), all pre-existing.
- **Branch protection:** strict, requiring test, secrets, CodeQL, linux and windows. All required checks pass.

### 2. Diff vs main and commit graph
- `git diff 1d14e01...b1b51c1` (merge base is now 1d14e01) and the two-dot tree diff `1d14e01 b1b51c1` are the same 11 S1 files.
- pipeline.py and test_job_manifest.py are identical to main.
- b1b51c1 is a true two-parent merge: parent 1 is 86211b5 (the S1 tip), parent 2 is 1d14e01.
- Its tree `a640150` equals `git merge-tree --write-tree 86211b5 1d14e01`, so there are no manual edits in the merge.
- fbbb2c0 is an ancestor, so there was no rebase or force-push. The new commits are 8231d21, 10a310d, d702466 and 86211b5.
- Since fbbb2c0, only timeline.py, docs/timeline.md and test_timeline.py changed (10-drift-license.txt). The license, NOTICE, packaging and script files are unchanged.

### 4. My C1 scripts and fuzz
- **c1_items.py:** every item still passes (items 1–9 and 11–13, the same counts as before). No expected values needed changing.
- **Original c1_fuzz.py (20k mutations):** 0 crashes, 0 malformed problems, 0 OTIO in-memory mismatches.
  - At fbbb2c0 this fuzz reported 597 path-shape exceptions for a missing id or type. They are gone, because those cases are now missing_field.
- **New c1_fuzz2.py:** 20k mutations (seed 99) plus 30k (seed 7).
  - Mutations covered: non-str roles; non-str and mixed-type keys; lone surrogates in values and keys; huge ints (±2^53±1, 2^63, 2^64, 10^30); bools in int slots; values near 2^53, including anchor offsets.
  - Results: 0 crash classes and 0 malformed problems. canonical_hash fails exactly when validate() finds a problem, and the only exception either hash function raised was TimelineError. Every doc that validated round-trips through to_otio → from_otio in memory, 2,579 in all.
- **Harness changes, stated:**
  - c1lib's resolver now resolves a non-str key by `str(key)`. That is how b1b51c1 names such keys in paths, and such keys only exist in Python-built docs. id_index skips non-str media keys.
  - In my property test, the .otio-string round trip is now counted separately as INFO, instead of sharing a try block with the in-memory check.

### 5. The rulings
- **Roles:** `[]`, `{}`, `["main"]`, 1, 0, None, True, False, 1.0, "Main" and `{"main":1}` all give bad_track_role at /tracks/0/role. canonical_hash and stamp_hash raise only TimelineError.
- **Mixed-type keys** on an item, the doc, props or a track give unknown_field. A non-str media key gives wrong_type (Ada (b)). Hashing raises TimelineError. There are no crashes elsewhere either: fuzz2 had about 9.7k key mutations with 0 crashes.
- **Lone surrogates:**
  - In any of 150 string-value cases (\ud800, \udfff or x\udc00y in every string field of my base doc), the doc is rejected and both hash functions raise TimelineError.
  - A surrogate in a key is rejected as unknown_field (Ada (c)).
  - A surrogate pair spelled as two code units is wrong_type; a real U+1F600 is valid.
- **seconds_to_ticks_nearest:**
  - Exact halves go to even in both directions: ±1/2 tick → 0, 3/2 → 2, 5/2 → 2, −3/2 → −2.
  - Fraction(1,3) and the float 1/3 both give 235200000. 0.0416667 works as a float and as a Decimal.
  - Returned seconds are a Fraction equal to ticks/705600000 exactly.
  - 20k random Fractions and 20k random floats each equal round-half-even of the exact value.
  - TypeError for True, False, "1", "0.5", None, [], b"1", {} and 1j.
  - ValueError for float NaN and ±inf, and Decimal NaN, ±Infinity and sNaN.
  - -0.5 passes through as −352800000.
- **Strict seconds_to_ticks**, tested with exact inputs only (Ada (a)): it raises ValueError between ticks for Fraction(1,2S), Fraction(1,11), "1/11", Decimal("1E-10") and Decimal("0.0416667"). An int is always whole ticks.
  - Change: I used 1/11 because 1/3 s is exactly 235200000 ticks.
- **out_of_range:**
  - All of these now fail as out_of_range: speed [1,10] on a 2^52+1 source, media fps [2^63,1], and fps [1,2^53+1].
  - These are valid: fps [2^53,1]; a clip end of exactly 2^53; a speed-1/2 end of exactly 2^53; an anchored resolved end of exactly 2^53; version 2^53.
  - These fail as out_of_range: a clip end of 2^53+1; a speed-1/2 end of 2^53+1; an anchored resolved end of 2^53+1 (on mu.1, with id); an anchor offset of 2^53 whose resolved end passes the cap; version 2^53+1 at /version.
  - Raw tick fields above 2^53 (at, media dur, anchor offset) fail as too_large.
- **Round-trip property:** 2,221 valid docs with values near the cap (speeds, anchors, huge media fps) all round-trip to_otio → from_otio exactly in memory, and canonical_hash works at the cap.
- **missing_field:** a missing id or type on a clip, text item, transition or marker gives missing_field at the key's pointer, never wrong_type.
- **Docs:** docs/timeline.md now says too_large covers raw ticks and out_of_range covers ends, scaled durations, [num,den] parts and version. It also documents seconds_to_ticks_nearest. seconds_to_ticks_nearest imports from hermes_studio.timeline.

### 6. otiotool (item 14)
- Exact round trip through `otiotool -i -o` (byte-equal JSON, equal hash), and every other command exits 0.
- --stats and --list-markers fail with "SMPTE timecode does not support this rate". The no-code 705600000/s control fails the same way, and the 24/s control succeeds. So this remains a Slice 2 note under Ada's ruling.

## Note for Ada (not a fail)
A lone surrogate in an enum or reference string is reported by that field's own rule, not wrong_type:

| Field | Rule reported |
|-------|---------------|
| schema_version | bad_schema |
| track role | bad_track_role |
| item media | unknown_media |
| transition kind | bad_transition |
| transition between[i] | bad_transition at /between |

All other string fields give wrong_type: id, type, text, label, path, proxy, anchor.to, look, style strings and the media key. In every case the doc is rejected and hashing raises TimelineError.

docs/timeline.md says a lone surrogate "fails as `wrong_type`", and the steer said "a lone surrogate in a string value gives wrong_type". So either the doc wording needs a qualifier, or those five checks need to run the surrogate test first.

Repro:
```python
d = T.new_timeline("p"); d["tracks"][0]["role"] = "text\ud800"; T.validate(d)  # bad_track_role, not wrong_type
```

## Slice 2 notes, unchanged
1. OTIO 0.18.1's JSON reader misreads odd values above about 7×10^15 ticks, for example at = 2^53−S−1. In my property test, 462 of 2,221 cap-adjacent valid docs did not survive a round trip through an .otio JSON string (38 ValueError, 22 TimelineError, the rest differ), although every one is exact in memory. This is OTIO's own behaviour (prove-s1/probe-otio-json-precision.txt). The docs' line "no value that big ever reaches to_otio()" holds for in-memory export only.
2. otiotool --stats and --list-markers fail at 705600000/s, as ruled.
3. The overall CodeQL check concludes before all analyses upload.
