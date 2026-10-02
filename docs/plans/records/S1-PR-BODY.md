Title: Editor Slice 1: timeline schema, validator, canonical hash, OTIO export

Branch `feat/editor-s1-timeline` → `main` (branched from 074c8a7, v0.5.3; main 1d14e01 merged in). Plan: PLAN-MERGED.md §4.2 and §5 slice 1, Prove gate C1. Full spec: `docs/timeline.md`.

Head: `b1b51c117795f56924e12a89fc7bc88fe5dcf3e6`. Commits:
- cbebd79 (slice 1); 3df0d8e (`schema` renamed to `schema_version`, `overlay` role removed); 5e3e639 (problem list API, JSON Pointer paths, item ids, `stamp_hash`); 9698aaa (`id` only when it names exactly one valid item); fbbb2c0 (tests only: blanket id check, three-copy duplicate test).
- After Prove's C1 review: 8231d21 (a wrong-type role, a non-string key or a lone surrogate is a problem, never an exception); 10a310d (`seconds_to_ticks_nearest`; `seconds_to_ticks` stays strict); d702466 (values past 2⁵³ fail as `out_of_range`); 86211b5 (a missing item `id` or `type` is `missing_field`).
- b1b51c1: a normal merge of `origin/main` at 1d14e01 (PR #34), with no conflicts. `git diff origin/main...HEAD --name-only` is still only the 11 S1 files.

## What's in it

- `hermes_studio/timeline.py`: schema `hs.timeline/1`, `validate()` / `validate_or_raise()`, `normalize()`, `canonical_json()`, `canonical_hash()`, `stamp_hash()`, `resolve()` (absolute times, anchors followed), `new_timeline()`, time helpers, `to_otio()` / `from_otio()` / `write_otio()`.
- `opentimelineio==0.18.1` (Apache-2.0) is a dependency (`>=0.18.1,<0.19` in pyproject, pinned in `packaging/engine-constraints.txt`). Its wheels add only `_otio` / `_opentime` extension modules and no `.libs` folder, so the wheel-library lists don't change.
  - NOTICE gets an OpenTimelineIO section (with its NOTICE text).
  - New `licenses/OpenTimelineIO.txt` holds the Apache-2.0 text plus the Imath, RapidJSON and pybind11 licenses compiled into its core, from the submodules at v0.18.1.
  - Both engine builds now import it and assert that NOTICE names the installed version.
- NOTICE attributes OpenCut classic (MIT, commit cf5e79e9) for two patterns: the half-open overlap test and the per-track-kind capability table. Its MIT text is included and no code was copied. Nothing comes from Kdenlive, Shotcut, Olive, OpenShot or LosslessCut, and a test checks timeline.py names none of them.
- NOTICE is still one repo file copied to `resources/` and `resources/engine/`, so both copies stay byte-identical (Windows gets CRLF via autocrlf, as before). `tests/test_notices.py` is updated and green.

## API

| Call | Returns |
|---|---|
| `validate(doc)` | a list of problems `{rule, path, message, id?}`, empty when the doc is valid (the stored-hash check included) |
| `validate_or_raise(doc)` | the doc, or raises `TimelineError` (code `bad_input`; `.problems` in the same shape, plus `.rule`, `.path` and `.id` of the first problem and `.rules` sorted) |
| `canonical_json(doc)` / `canonical_hash(doc)` | bytes / `"sha256:<hex>"`; raise `TimelineError` on **any** invalid doc, `hash_mismatch` included |
| `stamp_hash(doc)` | `(copy with the correct hash set, hash)`: validates everything except the stored-hash check. This is the way to hash a doc for writing (it replaces `with_hash`) |

- **`path`:** an RFC 6901 JSON Pointer (`""` = the whole doc), e.g. `/media/m.1/fps` or `/tracks/0/items/2/fade_in`, with `~` → `~0` and `/` → `~1`. A valid id can't contain `/` or `~` (`[A-Za-z0-9][A-Za-z0-9_.-]{0,63}`), so escaping only matters in paths for invalid keys: a media key `m/1` fails as `bad_id` at `/media/m~11`. For a missing field, the pointer names the field that should be there.
- **`id`:** present only when it names exactly one valid item, i.e. the problem is in a track item or marker (or inside one) whose id is well-formed and used once in the whole doc.
  - `bad_id` and `duplicate_id` never carry `id`; they rely on `path`, and the message quotes the raw id.
  - A `duplicate_id` path points at the second and later copies, not the first.
  - Any other problem on an item whose own id is malformed or duplicated anywhere in the doc also leaves `id` off.
- **`problems()`:** removed. It is internal now (`_problems`).

## Schema summary

Top level: `schema_version` ("hs.timeline/1"), `id`, `version`, optional `hash`, `tick_rate` (705600000), `fps` [num,den], `size` [w,h], `media` {id: {path, dur, fps, proxy?}}, `tracks` [{id, role, items}], `markers` [{id, at, label}].

| Item | Required | Optional |
|---|---|---|
| clip | id, type, media, src [in,out], fade_in, fade_out, and `at` or `anchor` | props {volume, speed, crop, look}, split_from |
| text | id, type, dur, text, style, fade_in, fade_out, and `at` or `anchor` | split_from |
| transition | id, type, kind "xfade", between [a,b], dur | — |

Track roles are exactly `text` (T<n>), `main` (V1, required, the only video track), `voice` (A<n>) and `music` (A<n>). "Exactly one main" has no rule of its own: no V1 is `missing_main_track`, a `main` track with another id (or V1 with another role) is `bad_track_id`, and a second V1 is `duplicate_id`. Every object is strict: unknown fields are rejected, and a missing required field is `missing_field` at the pointer of the absent key. That includes an item's `id` or `type` (they used to report `wrong_type`); a `type` with a wrong value is still `wrong_type`.

## Robustness (after Prove's C1 review)

`validate()` always returns a list, and `canonical_hash()` / `stamp_hash()` / `to_otio()` raise only `TimelineError`, whatever the input:
- **Track role of the wrong type** (`[]`, `{}`, `["main"]`, `{"x":1}`, `1`, `None`, `True`): it used to raise `TypeError` (unhashable). It is now `bad_track_role` at `/tracks/<i>/role`.
- **Non-string object keys** (possible from Python, not JSON): sorting mixed key types raised `TypeError`. Such a key is now `unknown_field`.
- **Lone surrogates** (e.g. JSON `"\ud800"`): the doc validated, then `canonical_hash` raised `UnicodeEncodeError`. Such a string is now `wrong_type`.
- **Fuzz:** 20,000 random type mutations of a valid doc on the merged tree gave **0 crashes**. `validate()` returned a list every time, and `canonical_hash` / `stamp_hash` raised only `TimelineError`. Before the fix, 5,000 mutations hit the three sites above: the role (300), mixed keys (3) and surrogates (2).

## Desk rulings → fields

- **(a) Anchors:** text items and clips on music tracks take `anchor: {to, offset}` instead of `at`. The item starts at `V1 clip.at + offset`, so it moves with that clip; `resolve()` returns absolute times.
  - Rejected: a missing target (`anchor_target_missing`), a target that isn't a clip on V1 (`anchor_target_not_main`), an anchor on any other item (`anchor_not_allowed`), giving both `at` and `anchor` or neither (`at_and_anchor`), and a resolved start before 0 (`anchor_before_zero`).
- **(b) Fades:** every clip and text item has `fade_in` and `fade_out` as integer ticks, each ≥ 0, with `fade_in + fade_out` ≤ the duration (`fade_too_long`). Keyframe objects are rejected.
- **(c) V1 gaps:** gaps are allowed and implied by `at`; there is no gap object. Overlaps on main and voice tracks are rejected (`overlap`). The only exception is two consecutive clips joined by an `xfade` whose `dur` equals their overlap exactly (`transition_overlap_mismatch`); this follows the plan's own example, where c2 starts 0.3 s before c1 ends.
- **Glyph 1:** there are no author or actor fields. `actor`, `author`, `created_by`, `modified_by`, `user` and `owner` fail as `attribution_field` anywhere in the doc.
- **Glyph 2:** ids are unique across the whole doc, including media, tracks, items and markers (`duplicate_id`). `split_from` is optional (`bad_split_from` if it points at the item itself).
- **Glyph 3:** the anchor is as in (a).
- **Glyph 4:** fades are as in (b).
- **Glyph 5:** markers are `{id, at, label}`, with ids unique across the doc.

## Canonical hash definition

- **Time:** integer ticks only. `tick_rate` must be exactly 705600000 (flicks); any other value, including 705600000.0, fails as `bad_tick_rate` (tested with 1000, 48000, a float, and a missing value).
  - Every time value must be an int. That covers at, dur, src in/out, anchor offset, fade_in, fade_out, marker at and media dur; a float or bool fails as `not_integer_ticks`.
  - Other fractions (fps, speed, volume, crop) are reduced `[num, den]` pairs, so the doc holds no floats at all.
  - A clip's `(out − in) / speed` must be whole ticks (`non_integer_duration`).
- **The 2⁵³ cap:** a raw tick field above 2⁵³ still fails as `too_large`. Derived values above 2⁵³ fail as `out_of_range`. This reuses the existing id, so there's no new rule id. Those values are an item's end (`at` + duration, or an anchored item's resolved end), a clip's duration `(out − in) / speed` (e.g. speed [1,10] on a 2⁵²+1 source), each part of a `[num, den]` pair (e.g. a media fps of [2⁶³, 1]) and `version`. An end exactly at 2⁵³ is valid. So no value that big ever reaches `canonical_hash()` or `to_otio()`.
- **Helpers:**
  - `seconds_to_ticks` stays strict: exact for int, Fraction, Decimal and str, and raises `ValueError` if the result isn't whole ticks. A float is taken at its exact binary value and rounded half to even.
  - `seconds_to_ticks_nearest(x)` is the rounding helper. It takes int, Fraction, Decimal or float, never a str (not even `"1"`), and rounds to the nearest tick with exact halves going to even. Negative values pass through. It returns `(ticks, seconds_used)`, where `seconds_used = Fraction(ticks, 705600000)` is the exact time the tick stands for. It raises `TypeError` for a bool, a str or any other non-number, and `ValueError` for NaN and ±infinity (float or Decimal).
  - `ticks_to_seconds` returns a Fraction.
  - The frame helpers are exact for 24000/1001, 24, 25, 30000/1001, 30 and 60 fps and 48 kHz, each tested as a whole number of ticks.
- **Order:** item list order and marker list order aren't meaningful. `normalize()` sorts each track's items by **resolved start, then id**; anchored items have no raw `at`, so they sort at their resolved start, and a transition sorts at the start of its overlap. Markers sort by `(at, id)`.
  - Track order is meaningful and fixed by role: text, main, voice, music. Text tracks are listed highest number first and audio lowest first; anything else fails as `track_order`.
  - Clip `props` are filled with defaults, so omitted and explicit default props hash the same.
- **Strings:** any string that isn't NFC-normalized fails as `not_nfc` (tested with a decomposed é).
- **Serialization:** `canonical_json` = `json.dumps(normalize(doc) minus version and hash, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` as UTF-8. `canonical_hash` = `"sha256:" + sha256(canonical_json).hexdigest()`.
- **`version` and stored `hash`:** the plan has both fields (§4.2: "`hash` is the sha256 of canonical JSON, leaving out `version` and `hash`"). Both are excluded from the hash; a test changes them and checks the hash stays the same.
  - `validate()` and `canonical_hash()` both check that a stored `hash` matches the content (`hash_mismatch`); `stamp_hash()` writes the correct one.
- **`schema_version`:** it is part of the hash, but any value other than "hs.timeline/1" fails validation first (`bad_schema`; a doc using the old field name `schema` fails the same way).
- **Invalid docs:** `canonical_hash(doc)` refuses any invalid doc, a stale stored hash (`hash_mismatch`) included. It raises `TimelineError` (a `HermesStudioError`, code `bad_input`) carrying `.rule`, `.rules`, `.path`, `.id` and `.problems`; this is tested. `stamp_hash` is the only hashing call that skips the stored-hash check.
- **Rule ids (36, unchanged):** `not_object`, `bad_schema`, `bad_tick_rate`, `missing_field`, `unknown_field`, `attribution_field`, `wrong_type`, `not_integer_ticks`, `negative_time`, `too_large`, `bad_rational`, `out_of_range`, `not_nfc`, `bad_id`, `duplicate_id`, `bad_track_id`, `bad_track_role`, `missing_main_track`, `track_order`, `item_not_allowed_on_track`, `unknown_media`, `src_out_of_media`, `empty_range`, `non_integer_duration`, `fade_too_long`, `at_and_anchor`, `anchor_not_allowed`, `anchor_target_missing`, `anchor_target_not_main`, `anchor_before_zero`, `overlap`, `bad_transition`, `transition_overlap_mismatch`, `bad_split_from`, `bad_fps`, `hash_mismatch`.

## OTIO

- **Times:** `RationalTime(ticks, 705600000)` throughout.
- **Mapping:**
  - Clip → Clip + `source_range` + `ExternalReference`; speed → `LinearTimeWarp`.
  - Gap → Gap.
  - xfade → Transition at the start of the overlap (`in_offset` 0, `out_offset` dur), with the outgoing clip trimmed by dur.
  - Text → Clip + `GeneratorReference("hermes_studio.text")`.
  - Text and music tracks that overlap are split into lanes (A2, A2.1).
  - Markers → stack markers.
- **Metadata:** whatever OTIO has no field for travels in `metadata["hermes_studio"]`.
- **Round trip:** `from_otio(to_otio(doc)) == normalize(doc)` holds exactly, including through a file and through `otiotool -o`.
- **otiotool:** `--list-tracks --list-clips --list-media --verify-ranges --inspect -o` all succeed. `--stats` and `--list-markers` stop with "SMPTE timecode does not support this rate": OTIO 0.18 only formats timecode at standard frame rates, not at the flicks rate.

## Tests

`tests/test_timeline.py` has 189 cases:
- **Validator:** 82 rejection cases (including `overlay` as a role and a second video track), each mapped to a rule, plus a check that every rule id has at least one case. They cover a bad or missing schema version, bad tick_rate, missing and unknown fields, attribution fields, floats and bools as ticks, negative at and durations, empty or out-of-media src, rationals, NFC, ids and duplicates, track roles, ids and order, the anchor rules, fades, V1, voice and nested overlaps, transitions, split_from and a stale hash.
- **Rulings:** V1 gaps allowed; xfade as the only V1 overlap; text and music overlaps allowed; anchors following their V1 clip after a move; fades up to the duration.
- **Time:**
  - 7 rates as whole ticks; inexact rates refused.
  - `seconds_to_ticks` exact, with float rounding, and still raising between two ticks.
  - `seconds_to_ticks_nearest`:
    - exact halves round to even (Fraction, Decimal and float);
    - -0.5 passes through;
    - it reports the seconds used;
    - it rejects NaN, ±inf, `True`/`False`, `"1"`, `"0.5"`, `None`, a list and a complex number.
- **Robustness:**
  - a role of `[]`, `{}`, `["main"]`, `{"x":1}`, `1`, `None` or `True` gives `bad_track_role` at the right pointer, and `canonical_hash` and `stamp_hash` raise `TimelineError`;
  - non-string keys give `unknown_field`;
  - lone surrogates in a style, text, marker label or media path give `wrong_type`;
  - a missing `id` or `type` on a clip, text, transition or music clip gives `missing_field` (with the item's `id` only when `type` is the missing key).
- **The 2⁵³ cap:** a scaled source, a text end, an anchored end, media and top-level fps parts, a volume part and `version` each give `out_of_range` at the right pointer and with the right `id`. `canonical_hash`, `stamp_hash` and `to_otio` all raise, and an end exactly at 2⁵³ is valid.
- **Hash:**
  - documented canonical bytes
  - equal hashes under key order, item order, marker order and default props
  - 11 mutations giving different hashes
  - version and stored hash not hashed
  - invalid docs refused
  - undo restoring the hash
  - track order meaningful
- **OTIO:** mapping checks; lossless round trip with hash and version; empty timeline; otiotool (runs when installed: it is in CI, since the dependency installs `otiotool`); the docs example validates.

`tests/test_notices.py`: OpenTimelineIO pin, NOTICE section and license text, and the OpenCut attribution.

- **API:** `validate`, `canonical_hash`, `to_otio`, `seconds_to_ticks` and `seconds_to_ticks_nearest` import from `hermes_studio.timeline`. Every rejection case also checks the problem shape (`{rule, path, message, id?}`), that the path is a JSON Pointer that resolves into the doc, and that `TimelineError.problems == validate(doc)`.
- **Paths and ids:**
  - the pointer helper escapes `~` → `~0` and `/` → `~1`
  - `/media/m.1/fps` resolves for a valid id with a dot
  - media keys `m/1` and `m~1` fail as `bad_id` at `/media/m~11` and `/media/m~01`
  - 10 cases check the exact path, and that `id` is present for items and markers and absent for media, track and doc problems
  - "exactly one main" surfaces as the three rules above
  - `bad_id` has no `id`; `duplicate_id` has no `id` and its path points at the second copy; a fade error on a duplicated-id (or malformed-id) item has no `id`; a fade error on a normal item keeps its `id`
  - three copies of one id give exactly two `duplicate_id` errors, at the 2nd and 3rd copies, with no `id`
  - **blanket id check:** every test validates through one helper, which asserts that whenever a problem has `id`, exactly one item or marker in the doc has that valid id, and `path` is that item's pointer or starts with it plus `/`
- **stamp_hash:** a doc whose only problem is `hash_mismatch` makes `canonical_hash` and `canonical_json` raise, `stamp_hash` fixes it, and `stamp_hash` still refuses any other problem.

Full suite on the merged tree (b1b51c1): ruff clean, **360 passed**. That's 348 on the branch plus main's 12 `test_job_manifest.py` cases.

CI on b1b51c1, all success: ci 36882413402 (test, secrets), desktop 36882413422 (linux, windows, sources), CodeQL 36882406311 (actions, javascript-typescript, python, and the alerts check).

## Open questions

- `otiotool --stats` and `--list-markers` fail at 705600000/s: they print SMPTE timecode, which OTIO 0.18 only formats at standard frame rates ("SMPTE timecode does not support this rate"). The other otiotool commands pass (`-i`, `--list-tracks`, `--list-clips`, `--list-media`, `--verify-ranges`, `--inspect`, `-o`). An export at the frame rate would make `--stats` work but would not round-trip exactly, so it's a Slice 2 decision.

## Slice 2 notes

- **Proposal: an `overlay` track role** (V<n>, n ≥ 2, clips and transitions, no overlaps, listed above V1 with the highest number first) for B-roll and picture-in-picture. It is not in the locked `hs.timeline/1`, so it needs `hs.timeline/2`.
- Deleting a V1 clip that anchored items point at must remove those items or convert them to absolute `at`.
- Track mute, lock and hide flags aren't in the schema.
- Decide whether `media.proxy` should stay in the hash (a finished proxy job currently changes it without an op).
- `split_clip` must pick tick positions where both halves have a whole-tick duration at the clip's speed.
