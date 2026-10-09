# S4 spec: media services (probe, proxy, thumbnails, waveform, words → timeline)

Status: **draft, built on `feat/editor-s4-media` (stacked on S3 / PR #42). Not ruled.** Decisions marked **(proposed)** need Ada. Plan of record: PLAN-MERGED.md §5 row 4, SECTION-BAY-ENGINE.md §4 and §6 row 4. Prove gate: *a 20-minute fixture imports with progress*.

## 1. What S4 adds

| Piece | Where | What it does |
|---|---|---|
| `probe(path)` | `media.py` | ffprobe → `{dur (ticks, exact, half up), fps [num,den] or null, width, height (rotation applied), rotation, vfr, has_video, has_audio, video_codec, audio_codec}`. Cover art (`attached_pic`) is not video. |
| `add_media` op | `oplog.py` | The one way media enters a timeline. `path, dur, fps, id?, proxy?`; id is the caller's or the first free `m<n>`. Values are checked by the validator (`/media/<id>/…`). Inverse `delete_media{id}`; its inverse `insert_media{id, media}` (both internal). |
| Import job | `media_jobs.py` | Probe → one `add_media` log entry (summary `Import <file>`) → background stages on a 2-worker pool: `proxy`, `thumbs`, `wave`, and `words` on request. |
| Derived files | `<project>/cache/` | `proxy/<id>.mp4`, `thumbs/<id>.jpg` + `<id>.json`, `wave/<id>.json`, `words/<id>.json`, and `media/<id>.json` (status). All written tmp + replace, 0600. |
| Words → timeline | `media.timeline_words` | Maps source-tick words through every clip that shows them (midpoint inside `src`, span clamped to the clip, scaled by `speed`). |
| Tools | `mcp_timeline.py` | `import_media` (write), `media_status`, `get_transcript` (read; both work with the app closed). |
| REST | `http_engine.py` | `POST /api/projects/<id>/import_media`; `GET …/media/<mid>` (status), `GET …/media/<mid>/{proxy,thumbs,thumbs.json,wave,words}` (files; the proxy supports Range); `GET …/transcript[?media_id=]`. |

## 2. Decisions

- **D1 (proposed). Media is referenced in place, never copied.** `path` is the resolved absolute path of a file that passes the desk's own `local_source` rule (home folder, mounted drives or `HERMES_STUDIO_MEDIA_ROOTS`; video/audio extensions only). URLs are refused at `/path` (download first with `run`). Copying a 20-minute source into every project doubles disk use; SECTION-BAY-ENGINE §7 already flags disk.
- **D2 (proposed). The import is one log entry; derived files are cache.** The proxy, thumbs, wave and words never change the doc (no engine-authored `proxy` write), so replay, hashes and undo are unaffected by background work, and an import is undone like any other entry. `media_status` names the proxy path.
- **D3. Undo of an import while a clip uses it is `undo_blocked`** (the validator's `unknown_media`, through the existing dependents check). No new rule id: counts stay **17 / 36**.
- **D4. Retries.** `import_media` with a `client_op_id` that this actor already used returns the cached write (the engine's dedupe, with the logged `base_version`) and the current status; it starts no second job. Without `client_op_id` the tool makes one (`import-<hex>`).
- **D5. Progress events are transient.** `media.progress {stage, stage_progress, progress}`, `media.failed {stage, error}` and `media.ready {state, failed, stages}` go to the project's SSE clients only, with **no `id:` line**, so `Last-Event-ID` replay (D11) still counts log seqs only and GET /mcp listeners (log entries) don't hear them. Sent at most every 0.25 s per job, plus every stage end. `media_status` (the status file) is the durable record.
- **D6. Overall progress** weights the stages proxy 0.6, thumbs 0.2, wave 0.2, words 1.0 (words only when asked). It is monotonic.
- **D7. Restart.** A `queued`/`running` status that no worker in this engine owns reads as `interrupted` (app closed mid-import, or a closed-app read). Closing the engine kills running FFmpeg (status `cancelled`). **(proposed)** No auto-resume in S4; re-import makes a new media id. A `media_rebuild` tool is S5 material if wanted.
- **D8. Proxy.** H.264 `veryfast` CRF 26, height `min(540, source)` (never upscaled), the source's frame rate forced CFR (`-fps_mode cfr`), a keyframe every 0.5 s (`-g`, `-keyint_min`, no scene cuts), AAC 96k stereo, `+faststart`. Audio-only media get an AAC-only proxy.
- **D9. Thumbnails.** One frame per 2 s, 90 px high (width by aspect, even), tiled 10 across into one JPEG; the index gives `{every_s, count, cols, rows, width, height, sprite}`.
- **D10. Waveform.** Mono 8 kHz decode through a pipe, 100 `[min, max]` pairs per second as ints in −128…127 (`>> 8` of s16). Only peaks are kept.
- **D11. Words.** The existing local Whisper (`transcribe.py`, model `tiny` by default; `whisper` arg: tiny/base/small/medium) → `{w, in, out}` in source ticks, `in < out`, empty words dropped.
- **D12. Errors.** `import_media` checks, in order: unknown args (`unknown_arg` @ `/<arg>`), `stages` (`bad_arg` @ `/stages` or `/stages/<i>`), `whisper` (`bad_arg`), `path` (`bad_arg`; a missing file is `not_found` @ `/path`), probe failures (`bad_input`, ffprobe's last line with the path reduced to the file name). On a closed app it is `engine_offline` after the project checks, as for other writes. Read tools refuse unknown args first, then `media_id` (`not_found` with `id`).
- **D13. Tools list.** `tools/list` now has 14 tools (11 timeline + 3 media). Contract test 89's op list now includes `add_media`.

## 3. §11-style engine diffs vs S3

Only new surface: one public op (`add_media`) and two internal ops (`delete_media`, `insert_media`). No existing op, rule id, error path or line field changes. A log written by S3 replays byte-identically; a log with `add_media` does not load on S3 (`unknown_op`), which is expected for a new op.

## 4. Gate and tests

- **Gate (Prove):** `tests/test_s4_media.py::test_gate_twenty_minute_fixture_imports_with_progress`: a generated 20-minute 640×360 30 fps fixture with audio imports to `ready`; `media_status` progress is monotonic and moves; 600 thumbnails. Runs when `HERMES_SLOW_TESTS=1` (set in `ci.yml`). Local run: **78 s** for the import on the build container.
- Unit and contract: probe (video, audio-only, junk, missing), exact tick conversion, `add_media` undo/redo/reload and `undo_blocked`, 7 bad-arg cases, words mapping (clips, gaps, clamping, speed), end-to-end import over /mcp (files, proxy shape, wave peaks, retry, using the media), SSE events without ids and monotonic progress, audio-only, 9 refusals that leave the head unchanged, project/scope checks, closed-app reads and `interrupted`, REST (actor from the token, files, 404s, traversal, 401).

## 5. Open questions for Ada

1. D1: reference in place (as built) or copy into `<project>/media/`?
2. D7: is `interrupted` + re-import enough for Phase 1, or should open resume unfinished stages?
3. Should `get_timeline{summary:true}` (deferred from S3 to S4) land here or in S5 with the frame cache? Not built yet.
