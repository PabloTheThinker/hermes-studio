# Opus / BridgeClip / HermesClip map

OpusClip is cloud: ClipAnything, ReframeAnything, virality 0–99, auto-post, MCP with schedule. We do **not** call Opus MCP or post.

BridgeClip macOS is Electron + OpenRouter + Zernio. We remake the **job** on Linux localhost: download → Whisper → hook planner → FFmpeg. No npm, no their GitHub push.

Hermes Agent integration is the **standalone plugin** (`hermesclip_*` tools), not MCP. Same contract as other house plugins: JSON string handlers, merge `plugins.enabled`, new session for tools. Do not bounce the gateway.

Local remakes of Opus product surface:
- Virality chip = hook/standalone/arc score ×100 (heuristic, not their model)
- Hunt prompt = ClipAnything-lite keyword boost
- Aspects 9:16 / 1:1 / 16:9
- Fit Classic vs Fill crop (speaker Haar crop when opencv is installed)
- Header: search, New clip, running count, Local · no post
- Best recommendation after analysis
- Social copy pack (no post)

Not remade (on purpose): auto-post, brand templates, AI B-roll, AI voiceover, social scheduler, per-frame cloud reframe tracker.

Editing now: trim, captions, hook overlay, speaker-fill. Timeline editor stays parked until Pablo asks.
