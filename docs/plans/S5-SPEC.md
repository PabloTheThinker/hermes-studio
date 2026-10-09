# S5 spec: frame cache, `timeline_frames`, contact sheet, before/after

Status: **draft, built on `feat/editor-s5-frames` (stacked on S4). Not ruled.** Plan of record: PLAN-MERGED.md §4.7 and §5 row 5, SECTION-BAY-ENGINE.md §4. Prove gate: **C10**.

## 1. What S5 adds

| Piece | Where | What it does |
|---|---|---|
| Recipe | `frames.recipe_at(doc, t, width)` | What is visible at `t`: canvas size, output size, the V1 clip (or both clips of a transition with the mix), each with media id, path, duration, the **source frame shown** (snapped to the source frame index), crop, look, fade alpha; the text items on screen (text, style, alpha), bottom of the stack first. Exact fractions as strings, no floats. Audio isn't in it. |
| Key | `frames.key_of` | `sha256(canonical recipe JSON)` + `-<w>x<h>`. A `v` field (`RECIPE_VERSION`) changes every key when the drawing changes. |
| Render | `frames.render` | One `ffmpeg -ss` per video layer on the S4 proxy (else the source), cover-cropped to the canvas aspect; fades blend to black; transitions blend by `mix`; text drawn with Pillow (Archivo, white with a black stroke, lower third). A **preview**: captions and looks are S6. A gap is black. |
| Cache | `frames.FrameCache` | `<project>/cache/frames/<key>.jpg` (0600, tmp + replace). A hit touches the file; after each miss the least recently used frames are dropped until the total is under the cap (`HERMES_FRAME_CACHE_BYTES`, default 2 GiB). |
| Before/after | `frames.entry_frames`, `history_frames` | For one entry: the docs at its base and new versions (rebuilt from the log's checkpoints), the **first changed time** (earliest start of any changed item, or a changed marker's time, in either doc; else 0), and the two recipes there. |
| Tools | `frame_tools.py` | `timeline_frames {at_s[]|at[], width?, images?}` (1–12 times), `timeline_contact_sheet {count?=12 (1–48), from_s?, to_s?, cols?=4, width?, images?}` (the middle of each of `count` equal slots), `history_frames {op_id, width?, images?}`. Results carry refs `{at, at_s, key, cached}`; pixels go only as MCP `image` content blocks, and not at all with `images:false`. |
| REST | `http_engine.py` | `GET /api/projects/<id>/frame?at=<ticks>[&width=]` → `image/jpeg` with `X-Frame-Key` and `X-Frame-Cached`. |

## 2. Decisions

- **D1. C10 as built.** The key depends only on the recipe, so (a) an edit that doesn't change what shows at `t` keeps the key (tested: a move at 40 s and a marker leave the 0.5 s frame cached); (b) entry *n*'s "after" key equals entry *n+1*'s "before" key at the same time (tested); (c) the LRU cap holds (tested with a small cap and a touch).
- **D2 (proposed). Write results are unchanged.** PLAN-MERGED §4 lists `before_frame`/`after_frame` refs in write results. Adding them would change every write answer (an S3 §11-style diff), and a cached retry has no "before" doc of its own, so the refs could differ between a call and its retry (C5 says retries are identical apart from warnings). As built, `history_frames {op_id}` gives the refs on request; the Edit page calls it per `op.applied` card. Ada to rule whether refs must also ride in write results (they could be computed from the entry, at a replay cost per write).
- **D3. Scope and app state.** The three tools need the `render` scope (minted by default since S3, first checked here) and a running engine: making a frame writes the cache, and a closed-app read never writes (D28). Closed app → `engine_offline`, after the project checks.
- **D4. Errors.** Unknown args first (`unknown_arg`), then `width` (32–1080), `images` (bool), the times (`missing_arg` @ `/at_s` when neither is given, `bad_arg` when both are, `bad_arg` @ `/at_s/<i>` for a negative, non-finite or boolean time), `count` 1–48, `cols` 1–12, an empty range (`bad_arg` @ `/to_s`), `op_id` (`missing_arg`/`bad_arg`, `not_found` with `id`).
- **D5. Snapping.** The recipe holds the source frame index and its exact start time, so times inside one source frame share a key. Audio-only media have no frames (a black frame).
- **D6. Not built (later).** Eager card frames on each write (needs D2), `hermes-studio cache clear`, preview segments for transitions/looks (§4.7 "Preview v1"), and a cache size report in `project_status`.

## 3. Engine diffs

None: no op, rule id or write answer changes. `tools/list` has 17 tools (11 timeline + 3 media + 3 frames).

## 4. Tests

`tests/test_s5_frames.py` (27): recipes (visible items only, gaps, text, snapping, transitions), C10 (a)–(c), first-changed time, pixels (video, gap black, fade, text), cache hit/miss and LRU, /mcp end to end on an imported video (images, refs, a hit after an unrelated edit, before/after, contact sheet), 16 refusals, render scope and closed-app checks, REST frame route.
