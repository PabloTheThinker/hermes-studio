# Section: Engine, timeline, edit log, media and render (Bay)

Reviewed: `REPO-AUDIT.md`, `RESEARCH.md`, `PLAN.md`, `SECTION-GLYPH-UX.md`, `SECTION-WIRE-AGENT-INTERFACE.md`, plus `main` @ `be8a877` (PR #32, Oct 1 3:12 AM ET) read with `gh api`: `render.py`, `edit.py`, `pacing.py`, `api.py`, `design.py`, `studio.py`, `mcp.py`, `transcribe.py`, `desktop/main.js`, `.github/workflows/desktop.yml`, `NOTICE`, `pyproject.toml`. No clone, no code.

## 1. What the engine does today, and the stack call
| Piece | Today (file) | Keep / change |
|---|---|---|
| Core | `api.py`: validation, `code`+`hint` errors, exit codes; CLI/MCP/plugin sit on top | Keep. Add `timeline.py` + `oplog.py` behind it |
| Render | `render.py`: one FFmpeg `filter_complex` per clip (trim → concat of keep-intervals → crop/layout → ASS burn-in), `libx264 veryfast crf 20` + AAC | Keep; extend from one source to N clips/tracks |
| Filler cuts | `pacing.py`: `keep_intervals()` → `TimeMap` of kept ranges | Reuse to compile "remove fillers" into timeline ops |
| Edits | `edit.py`: trim/split re-encode **whole files**; drop/restore via `.trash` | Leave for clips; timeline edits never touch media |
| Op pattern | `design.py` `apply_ops()`: list of ops, **index-addressed, no inverses, no version**; undo is client snapshots in `design.js` | Copy the validation style, not the addressing: use stable ids + engine-side inverses |
| Server | `studio.py`: stdlib `ThreadingHTTPServer`, loopback, Host/Origin checks, a 2-worker job queue | Keep; add SSE + project routes. A thread per SSE client is fine locally |
| App link | `desktop/main.js`: Electron spawns `hermes-studio studio --port <free>` from the bundled Python and loads `http://127.0.0.1:<port>/` | Keep. The Edit page talks REST + SSE to the same engine; no IPC to Python |
| Agents | `mcp.py`: stdio, runs `api` **in its own process** | Becomes a proxy to the running engine (Wire) |

**Stack call:** keep Python + subprocess FFmpeg. All heavy work is already in FFmpeg, the packaging and installers already exist, and the core rule "`api.py` first" already holds. No new runtime.

## 2. Timeline model (OTIO-shaped JSON; the engine is the only writer)
```json
{"schema":"hs.timeline/1","id":"p-7f3a","version":13,"hash":"sha256:…","fps":30,"size":[1080,1920],
 "media":{"m1":{"path":"media/talk.mp4","dur":1204.2,"fps":29.97,"proxy":"cache/proxy/m1.mp4"}},
 "tracks":[{"id":"V1","kind":"video","items":[
   {"id":"c1","type":"clip","media":"m1","src":[12.40,31.85],"at":0.0,"props":{"volume":1,"speed":1,"crop":null,"look":null}},
   {"id":"t1","type":"transition","kind":"xfade","between":["c1","c2"],"dur":0.3},
   {"id":"c2","type":"clip","media":"m1","src":[40.10,52.00],"at":19.15}]},
  {"id":"T1","kind":"text","items":[{"id":"x1","type":"text","at":0,"dur":3,"text":"…","style":"pop"}]},
  {"id":"A1","kind":"audio","items":[]}],
 "markers":[]}
```
- `src` = source range in media seconds; `at` = timeline seconds. Gaps are implied by `at`, so there is no gap object. Effects stay a small `props` map in Phase 1, and keyframes come later. OTIO export maps clips to Clip + `source_range` and gaps to Gap.
- **Versioning:** `version` is a monotonic integer. `hash` is the sha256 of canonical JSON without `version` and `hash`, so equal content gives an equal hash, and undo back to the same state gives back the same hash.
- **Single writer:** `projects/<id>/` holds `timeline.json` (atomic tmp+replace, as `design.py` already does), `oplog.jsonl`, `snapshots/` (every 50 versions) and `cache/`. A **per-project lock** (`.lock`: pid, port, token hash; OS file lock) makes one engine the owner. The stdio MCP proxy reads `.lock` and attaches to that engine instead of opening the project itself. That rules out two writers (app + stdio fallback).

## 3. Edit log (shared by agent and human; aligned with Wire)
Each line in `oplog.jsonl` has: `seq`, `op_id`, `client_op_id`, `group_id`, `actor` (**taken from the session token, never from args**), `summary`, `base_version` → `new_version`, `hash`, `ops`, `inverse`, `changed_ids`, `undoes` (or null).

| Op | Inverse (computed by the engine at apply time) |
|---|---|
| `insert_clip` / `add_text` / `add_transition` / `add_marker` / `add_track` | the matching delete/remove (by new id) |
| `delete_clip{ripple}` / `remove_*` | re-insert the stored item at its old place (+ un-ripple) |
| `move_clip`, `trim_clip{ripple}`, `set_props` | the same op with the old values (only the changed keys) |
| `split_clip{id,at}` → `c1a`,`c1b` | `join_clips{a,b}` that restores `c1` with its old id |

- **Groups (Glyph ask 1):** one `timeline_apply` batch is atomic: either all ops apply or none do. "Remove fillers" compiles (via `pacing.keep_intervals`) into **one batch = one entry = one card = one Undo**. Calls that belong together across tool calls share a `group_id`. Undo of a group applies all the inverses in reverse order as **one new entry**.
- **Append-only:** undo/redo appends an inverse entry (`undoes: op_id`) and never rewrites history. Agents may undo only their own entries; humans may undo any. If an inverse no longer applies (a later entry touched the same ids), the result is `undo_blocked` + the dependent `op_id`s, which feeds Glyph's "Restore to before this step".
- **Idempotency:** `(actor, client_op_id)` is unique. A retried call returns the original result and does not apply again.
- **Human edits mid-run:** the engine serialises all writes, so human ops apply at once. The agent's next write has a stale `base_version`, so the engine returns `conflict` with `history_diff` and the **run pauses** (Glyph). It does not silently re-read and retry. The agent's entries that already applied stay in the log and stay undoable.
- **Mode gate (Ask/Propose/Auto) lives in the engine.** A Propose write is **parked** in the engine as `approval.pending`. **Timeout rule is open:** Glyph wants the run to *pause* with the write still parked (never auto-skip), while Wire's draft says it times out to `skipped`. I lean to Glyph (no silent loss), but **Ada makes the final call**.
- **Events:** one append-only bus fed by the log, with a monotonic `seq` (SSE, `Last-Event-ID` replay): `op.applied`, `op.undone`, `timeline.changed`, `approval.pending`, `run.paused`, `job.progress`.

## 4. Decode, preview, encode
- **Import:** `ffprobe` (streams, fps, duration, rotation, VFR flag) → a **proxy** (540p H.264, 0.5 s GOP, CFR, AAC) → **thumb strip** (1 frame/2 s, a 160 px sprite per media) → **waveform** (16 kHz mono peaks to JSON, reusing `transcribe.extract_wav`) → Whisper words (existing). All of these are background jobs on the existing queue.
- **Preview v1:** a sequence player over proxies, plus canvas text/captions (PLAN §2.6). For anything the player can't show exactly (xfade, looks), the engine renders a short 540p **preview segment**, cached by the range's recipe hash.
- **Before/after frames (Glyph ask 2, shared with Wire):** key = `sha256(frame recipe at t)` + size. The recipe is the resolved list of what's visible at `t` (media, src time, props, overlays), not the whole timeline hash. So an edit at 0:40 doesn't invalidate a frame at 0:05, and v12's "after" *is* v13's "before" without extra work. A frame is one `ffmpeg -ss <t> -i proxy -frames:v 1` (plus the overlay draw) to a 320 px JPEG, about 50–150 ms. Card frames are made eagerly at the edit's first changed time; `timeline_frames` / contact sheets make them on demand.
- **Cache:** `~/.hermes/clips/projects/<id>/cache/{proxy,thumbs,wave,frames,preview}`, next to the existing `library/` and `designs/`. Frames and previews are LRU with a 2 GB cap per user (configurable). Proxies, thumbs and waves are kept while their media is referenced. `hermes-studio cache clear` deletes it all.
- **Final render:** one filtergraph built from the timeline (per-clip `trim/atrim` → `xfade`/`acrossfade` or `concat` → `overlay` text → `ass` captions → `amix` of audio tracks → `_encode_tail`). Above about 40 clips, it renders per-segment and joins with the concat demuxer (stream copy) to keep the graph small. Golden tests compare frame hashes/SSIM at fixed times.

## 5. FFmpeg licensing (confirmed by Ada; this is Slice 0)
- `desktop.yml` lines 18-22 pin BtbN `autobuild-2026-09-30-13-08`, **`gpl`** static `n9.0.2-17-g2a571b6068` (win64 + linux64, sha256-pinned). `NOTICE` has no FFmpeg/GPL text. v0.5.0–v0.5.2 shipped without it.
- **Recommendation:**
  - Stay on the **GPL build, as a separate executable** (called only via subprocess, never linked). `render.py`/`edit.py` use `libx264`, which BtbN's `lgpl` variant drops. LGPL would mean OpenH264 or hardware encoders: lower or uneven quality for no licensing gain, since we don't link.
  - **Notice needed:** an FFmpeg section in `NOTICE` (GPL-3.0-or-later as built, plus the list of bundled GPL libs: x264, x265, libass…), the GPL text bundled in the app (`licenses/FFmpeg-GPL.txt`), the exact BtbN release + sha256, and source links: the FFmpeg git tag/commit `2a571b6068` and the BtbN build-script tag. Best practice: also attach a source tarball to each GitHub release (or a 3-year written offer).
  - **Second gap the audit missed:** PyAV wheels (`av>=11,<19`, used by faster-whisper) bundle **LGPL** FFmpeg libs **in-process**. That needs an LGPL notice and a source pointer too.
- Shipping the fix needs a new release and Pablo's yes.

## 6. Phase 2 build slices (one PR each, in order). S ≈ 2–3 days, M ≈ 1 week, L ≈ 2 weeks
| # | Slice | Testable outcome | Size |
|---|---|---|---|
| 0 | FFmpeg/PyAV notices + GPL text in the app + source links | Test: `NOTICE` names the pinned URL/commit; the AppImage/NSIS contain `licenses/` | S |
| 1 | `timeline.py`: schema, validator, canonical hash, OTIO export | Bad docs are rejected with `code`+`hint`; equal content gives an equal hash; `.otio` opens in `otiotool` | M |
| 2 | `oplog.py`: ops + inverses, batches/groups, append-only undo/redo, `client_op_id` dedupe, actor rules | Property test: 1,000 seeded random op runs, and undo-all gives back the original hash; a retry doesn't apply twice | L |
| 3 | Project store, per-project lock, event bus (seq + SSE replay) | Second writer refused; the proxy attaches; reconnect replays missed events | M |
| 4 | Media services: probe, proxy, thumbs, waveform, transcript→timeline mapping | 20-min fixture imports; artifacts exist; jobs show progress | M |
| 5 | Frame cache + `timeline_frames` / contact sheet | Before/after refs on every write result; a cache hit across versions; LRU cap held | M |
| 6 | Render v1 (filtergraph + segment fallback) on the job queue | Golden render of a 3-clip + xfade + text + captions timeline matches by SSIM | L |
| 7 | `transcript_cut` / "remove fillers" as one batch | 40-op cut = 1 entry; one undo restores the hash | S |
| 8 | Engine mode gate (Ask/Propose/Auto, parked writes), shared with Wire | Ask refuses; Propose parks until Apply/Skip; timeout behaves per Ada's rule | M |

Total: 2 S + 5 M + 2 L ≈ **10 engineer-weeks** of engine work. Slices 1–3 are PLAN's Phase 0 exit; 4–8 feed Phase 1. Wire's HTTP MCP endpoint and Glyph's UI build on 3, 5 and 8.

## 7. Gaps and risks
- **VFR phone footage** drifts against the timeline clock. Proxies are forced to CFR and `src` is kept in source seconds; an exact final render needs a check.
- **Big filtergraphs** are slow or fragile; mitigated by the segment+concat fallback (slice 6).
- **Disk:** proxies add about 15% of the source size; there is a cap and `cache clear`, but no per-project quota yet.
- **Undo across media deletion:** the log references media by id; media files are never deleted while any version references them.
- **Timeout rule** (pause vs skip) is unresolved, pending Ada.

## Open questions for Pablo (2)
1. Can we cut **v0.5.3 now** with only the FFmpeg/PyAV license fix (Slice 0), before any editor work?
2. Keep the **GPL FFmpeg (x264, best quality)** as a separate program, or do you want an **LGPL-only** build (OpenH264, lower quality)? I recommend keeping GPL.
