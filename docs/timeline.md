# Timeline document `hs.timeline/1`

`hermes_studio/timeline.py` holds the schema, validator, canonical hash and OTIO export
(editor slice 1, Prove C1). The engine is the only writer of `timeline.json`. The schema is
frozen after slice 1: any change means `hs.timeline/2`.

## Example

```json
{"schema_version": "hs.timeline/1", "id": "p-7f3a", "version": 13, "hash": "sha256:…",
 "tick_rate": 705600000, "fps": [30, 1], "size": [1080, 1920],
 "media": {"m1": {"path": "media/talk.mp4", "dur": 846720000000, "fps": [30000, 1001], "proxy": "cache/proxy/m1.mp4"}},
 "tracks": [
  {"id": "T1", "role": "text", "items": [
    {"id": "t1", "type": "text", "dur": 2116800000, "text": "Hola", "style": "pop",
     "fade_in": 0, "fade_out": 0, "anchor": {"to": "c2", "offset": 705600000}}]},
  {"id": "V1", "role": "main", "items": [
    {"id": "c1", "type": "clip", "media": "m1", "src": [8467200000, 14112000000], "at": 0, "fade_in": 352800000, "fade_out": 0},
    {"id": "x1", "type": "transition", "kind": "xfade", "between": ["c1", "c2"], "dur": 176400000},
    {"id": "c2", "type": "clip", "media": "m1", "src": [28224000000, 35280000000], "at": 5468400000,
     "fade_in": 0, "fade_out": 0, "split_from": "c0", "props": {"volume": [1, 2], "speed": [1, 1], "crop": null, "look": null}}]},
  {"id": "A1", "role": "voice", "items": []},
  {"id": "A2", "role": "music", "items": []}],
 "markers": [{"id": "k1", "at": 1411200000, "label": "good bit"}]}
```

## Fields

| Where | Field | Rule |
|---|---|---|
| doc | `schema_version` | exactly `"hs.timeline/1"` |
| doc | `id` | project id |
| doc | `version` | integer ≥ 0, monotonic, set by the engine. **Not hashed** |
| doc | `hash` | optional `sha256:<64 hex>`; must match the content when present. **Not hashed** |
| doc | `tick_rate` | exactly `705600000` (flicks) |
| doc | `fps` | timeline frame rate, reduced rational `[num, den]`, a whole number of ticks per frame |
| doc | `size` | `[width, height]`, integers 1–16384 |
| doc | `media` | id → `{path, dur, fps, proxy?}`; `dur` ticks > 0; `fps` rational or `null` (audio) |
| doc | `tracks` | list of `{id, role, items}`, in role order (below) |
| doc | `markers` | list of `{id, at, label}` |
| clip | `id, type:"clip", media, src:[in,out], fade_in, fade_out` | required; `src` in media ticks, `in < out ≤ media.dur` |
| clip | `at` or `anchor` | exactly one; `anchor` only on music tracks |
| clip | `props` | optional `{volume, speed, crop, look}`; defaults `[1,1]`, `[1,1]`, `null`, `null` |
| clip | `split_from` | optional id of the item this was split from (it need not still exist) |
| text | `id, type:"text", dur, text, style, fade_in, fade_out` + `at` or `anchor` | `split_from` optional |
| transition | `id, type:"transition", kind:"xfade", between:[a,b], dur` | on clip tracks only |
| anchor | `{to, offset}` | `to` = a clip on V1; `offset` signed ticks; resolved start ≥ 0 |

Every object is strict: unknown fields are rejected. Times are integer ticks; floats and bools are
rejected anywhere a number is expected. Other fractions are reduced `[num, den]` pairs
(`volume` 0–4, `speed` 1/10–10, `crop` `{x, y, w, h}` in 0–1 inside the frame). Every string must
be NFC-normalized. Ids match `[A-Za-z0-9][A-Za-z0-9_.-]{0,63}` and are unique across the whole doc
(media, tracks, items and markers).

**Tracks.** The roles are exactly `text` (`T<n>`), `main` (`V1`, required, the only video
track), `voice` and `music` (`A<n>`). Text tracks hold text items; the others hold clips and
transitions. Track order is meaningful and fixed: text, main, voice, music; text tracks highest
number first (top of the stack first), audio tracks lowest number first. The default doc is
T1, V1, A1, A2.

**Timing.** A clip lasts `(out − in) / speed` ticks, which must be whole. Fades are plain ticks:
`fade_in`, `fade_out` ≥ 0 and `fade_in + fade_out` ≤ the item's duration. Gaps are implied by `at`;
there is no gap object. On main and voice tracks nothing may overlap, except two
consecutive clips joined by an `xfade` whose `dur` equals their overlap exactly. Text and music
tracks may overlap (their items can be anchored and move with V1).

**Anchors.** A text item, or a clip on a music track, may give `anchor: {to, offset}` instead of
`at`. It starts at `V1 clip.at + offset`, so moving that clip moves it. `resolve(doc)` returns every
item's absolute `(start, end)`.

**Attribution.** No `actor`, `author` or similar field exists; who did what is in the op log.
`actor`, `author`, `created_by`, `modified_by`, `user` and `owner` fail as `attribution_field`
anywhere in the doc.

**Exactly one main track.** There is no separate rule: no V1 is `missing_main_track`, a `main`
track with another id (or V1 with another role) is `bad_track_id`, and a second V1 is
`duplicate_id`.

## API

| Call | Returns |
|---|---|
| `validate(doc)` | list of problems `{rule, path, message, id?}`; empty when valid. A stored `hash` must match |
| `validate_or_raise(doc)` | `doc`, or raises `TimelineError` (code `bad_input`; `.problems` as above, `.rule`, `.path`, `.id` of the first, `.rules` sorted) |
| `canonical_json(doc)` / `canonical_hash(doc)` | bytes / `"sha256:<hex>"`; raise `TimelineError` for any invalid doc, `hash_mismatch` included |
| `stamp_hash(doc)` | `(copy with the correct hash set, hash)`: validates everything except the stored-hash check. Use it whenever a doc is hashed for writing |
| `resolve(doc)`, `normalize(doc)`, `new_timeline(id)` | absolute item times; canonical form; an empty T1/V1/A1/A2 doc |
| `to_otio(doc)`, `write_otio(doc, path)`, `from_otio(tl)` | see OTIO below |

`path` is an RFC 6901 JSON Pointer into the doc (`""` is the whole doc), e.g. `/media/m.1/fps` or
`/tracks/0/items/2/fade_in`, with `~` written `~0` and `/` written `~1`. Valid ids can't contain
`/` or `~`, so escaping only shows up in paths for invalid keys (a media key `m/1` fails as
`bad_id` at `/media/m~11`). For a missing field the pointer names the field that should be there.
`id` is set when the problem is in a track item or marker (or inside one) and names it; it is
omitted otherwise.

## Canonical hash

`canonical_hash(doc)` = `"sha256:" + sha256(canonical_json(doc)).hexdigest()`, where
`canonical_json` is:

1. Full validation, the stored-hash check included. An invalid doc raises `TimelineError` with the
   rule ids; nothing invalid is ever hashed. (`stamp_hash` skips only the stored-hash check.)
2. `normalize(doc)`: clip `props` filled with defaults; each track's items sorted by resolved
   start, then id (anchored items have no raw `at`, so they sort at their resolved start; a
   transition sorts at the start of its overlap); markers sorted by `(at, id)`. Item and marker list order is not meaningful; track
   order is (it is fixed by role and checked).
3. Drop `version` and `hash`. Everything else, including `schema_version`, is hashed (any other
   `schema_version` value fails validation first).
4. `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)`, UTF-8. The doc has no
   floats, so no number formatting choices remain. Strings are hashed as given (they must already
   be NFC).

## Time helpers

`seconds_to_ticks(x)` is exact for int, `Fraction`, `Decimal` and str (`"19.15"`, `"1001/30000"`)
and raises if the value is not a whole number of ticks; a float is taken at its exact binary
value and rounded half to even. `ticks_to_seconds(t)` returns a `Fraction`. `ticks_per_frame`,
`frames_to_ticks`, `ticks_to_frames` are exact at 24000/1001, 24, 25, 30000/1001, 30, 60 fps and
48 kHz, and raise for rates that are not.

## OTIO

`to_otio(doc)` / `write_otio(doc, path)` / `from_otio(timeline)`. Times are
`RationalTime(ticks, 705600000)`. Clips map to Clip + `source_range` (start = `src` in, duration =
timeline duration) with an `ExternalReference`; speed adds a `LinearTimeWarp`. Gaps map to Gap. An
xfade is a Transition at the start of the overlap (`in_offset` 0, `out_offset` dur), with the
outgoing clip trimmed by dur. Text items are clips with a `GeneratorReference`
(`hermes_studio.text`). Tracks whose items overlap are split into lanes (`A2`, `A2.1`). Markers go
on the top-level stack. Fades, props, anchors, `split_from` and the media table travel in
`metadata["hermes_studio"]`, so `from_otio(to_otio(doc)) == normalize(doc)`.

`otiotool` reads the file and its `--list-tracks`, `--list-clips`, `--list-media`,
`--verify-ranges`, `--inspect` and `-o` phases work. `--stats` and `--list-markers` print SMPTE
timecode, which OTIO 0.18 only formats at standard frame rates, so they stop with "SMPTE timecode
does not support this rate" at the tick rate.

## Rule ids

`not_object`, `bad_schema`, `bad_tick_rate`, `missing_field`, `unknown_field`, `attribution_field`,
`wrong_type`, `not_integer_ticks`, `negative_time`, `too_large`, `bad_rational`, `out_of_range`,
`not_nfc`, `bad_id`, `duplicate_id`, `bad_track_id`, `bad_track_role`, `missing_main_track`,
`track_order`, `item_not_allowed_on_track`, `unknown_media`, `src_out_of_media`, `empty_range`,
`non_integer_duration`, `fade_too_long`, `at_and_anchor`, `anchor_not_allowed`,
`anchor_target_missing`, `anchor_target_not_main`, `anchor_before_zero`, `overlap`,
`bad_transition`, `transition_overlap_mismatch`, `bad_split_from`, `bad_fps`, `hash_mismatch`.
