# S6 spec: render v1 (filter graph + segment fallback)

Status: **draft, built on `feat/editor-s6-render` (stacked on S5). Not ruled.** Plan of record: PLAN-MERGED.md §4.8 and §5 row 6, SECTION-BAY-ENGINE.md §4. Prove gate: **C11** (and E4's ffprobe/SSIM checks).

## 1. What S6 adds

| Piece | Where | What it does |
|---|---|---|
| Graph | `render_timeline.plan` | **Video pass:** a black canvas (`color`, the doc's size and fps, the window's length); each V1 clip from its **own seeked input** (`-ss src_in -t len -i`), speed (`setpts`), `fps`, crop, cover-scale to the canvas, fades to black, and for the incoming clip of a transition an **alpha fade-in over the overlap**, then trimmed to the window and overlaid at its time (`eof_action=pass`). Text items and caption words are one ASS file burned last (`subtitles`). **Audio pass:** every clip on every track with audio, its own seeked input, `atempo` chain for speed, volume, fades, transition fades (in for the incoming, out for the outgoing clip), `adelay` to its time, `amix normalize=0`, padded to length, to a 48 kHz WAV. |
| Encode | `render_timeline._encode` | Audio pass first (≈5% of the bar), then the video pass muxing the WAV: libx264 `veryfast` **CRF 18**, yuv420p, the doc's frame rate, AAC 160k 48 kHz, `-t` = the window's length, `+faststart`. |
| Segments | `render_timeline.windows` | Over `SEGMENT_OVER` (40) V1 clips, the timeline is cut at every 40th clip start (never strictly inside a transition); each window renders with the same code (items built whole, then trimmed), then the concat demuxer joins them with stream copy. |
| Jobs | `render_jobs.py` | One render at a time per engine. `render_id` = `v<version>-<w>x<h>[-cap]`; output `exports/<project>-<render_id>.mp4` (0600); status `cache/render/<render_id>.json`; `render.progress`/`render.ready`/`render.failed` SSE events without ids. Asking again for the same version, size and captions returns the existing job or file (`reused: true`). States: queued, running, ready, failed, cancelled (engine closed), interrupted (no worker owns it), missing (file deleted). |
| Tools | `mcp_timeline.py` | `render_timeline {width?, height?, captions?=true}` (render scope, app running) and `render_status {render_id}` (read; works with the app closed). |
| REST | `http_engine.py` | `POST …/render_timeline`; `GET …/renders/<rid>` (status) and `GET …/renders/<rid>/file` (mp4, Range; 409 until ready). |

## 2. Decisions

- **D1. Two passes.** One graph that pulls video and audio from the same seeked inputs stalls FFmpeg 6.1 (observed: frame 126 of 240, then no progress). Audio is a separate pass to a WAV; the video pass muxes it. The audio pass is cheap (no video decode).
- **D2. One input per clip.** Reusing one input for several clips makes the decoders wait on each other; per-clip `-ss`/`-t` inputs decode independently and seek fast and frame-accurately.
- **D3. Transitions as alpha fades.** `xfade` needs both clips as whole streams laid end to end; an alpha fade-in of the incoming clip over its overlap with the outgoing one gives the same crossfade with the overlay model, and works inside windows.
- **D4 (proposed). CRF 18.** At the clip pipeline's CRF 20 the five C11 timestamps scored 0.977–0.981 against the source; at CRF 18, 0.993–0.994. Final renders are the deliverable, so CRF 18.
- **D5. C11's SSIM method.** References are cut from the **source** by an independent FFmpeg command (cover scale + crop) and converted to **4:2:0**, the delivery format: a straight-to-RGB reference keeps full-resolution chroma and scores ~0.979 even against a *lossless* 4:2:0 encode of the same frame. Prove's E4 wording ("reference frames from the same pinned build") is satisfied a stricter way.
- **D6. Captions.** `captions: true` (default) burns the words `get_transcript` returns (S4 words mapped through the clips); none → no captions, and the `-cap` suffix is dropped. Style: one built-in look (bottom, white, bold); text items use `pop`/`impact`-like styles at 72% height. Matching the clip pipeline's caption looks (`captions.STYLES`) is a follow-up.
- **D7. Not in the doc, not in the log.** A render writes `exports/` and `cache/`; it never changes the timeline (like S3's `export_otio`).
- **D8 (proposed). One render at a time.** FFmpeg already uses every core; a queue keeps the desk responsive.

## 3. Engine diffs

None. `tools/list` has 19 tools.

## 4. Gate and tests

`tests/test_s6_render.py` (12). **C11:** 3 clips (16 s 1280×720 30 fps source with audio), a 1 s crossfade, a 0.5 s fade out, a title, a caption word, rendered at 1080×1920: 1 h264 + 1 aac stream, video duration 8.000 s (±1 frame), 240 frames (±1), SSIM ≥ 0.98 at 1.5, 3.5, 4.5, 5.5 and 7.2 s (measured 0.993–0.994), the crossfade midpoint differs from both clips, the title is drawn, and a repeat request reuses the render. Also: small size without captions, monotonic progress events without ids, 5 refusals, empty timeline, scope, closed app, window cuts, a segmented render with the right frame count, REST status/file/Range/traversal/scope.
