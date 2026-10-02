# Hermes Studio: research for an editor humans and agents both drive

Researched Thu Oct 1, 2026 (ET). Source numbers in [brackets] point to the list at the end. Star counts and last-push dates come from the GitHub API on the same day.

---

## 1. Open-source editors and engines: build on, learn from, or skip

### 1.1 The table

| Project | What it is | License | Health (Oct 2026) | Fit for Hermes Studio |
|---|---|---|---|---|
| **FFmpeg** | The decode/filter/encode toolkit | LGPL-2.1+; becomes GPL with `--enable-gpl` parts such as libx264 [1] | Very active | **Already the engine. Keep it.** Render backend v1 = FFmpeg filter graphs (already in `render.py`) |
| **MLT** | Multitrack engine behind Shotcut and Kdenlive. XML projects of producers, playlists (tracks) and tractors (multitrack) [2] | LGPL-2.1 [3] | Active | **Strong candidate for render backend v2** (transitions, keyframes, many filters). Its XML maps cleanly from a timeline JSON |
| **Shotcut** | Qt desktop NLE on MLT | GPL-3.0 [4] | Active, 15k★ | Learn from it (UX, filter set). Don't fork: GPL plus a C++/Qt codebase |
| **Kdenlive** | KDE NLE on MLT | GPL-3.0 [5] | Active | Learn from it. An agent bridge needs a patched build with D-Bus scripting [22] |
| **OpenShot / libopenshot** | Qt app (GPL-3.0) and a C++ library | libopenshot LGPL-3.0 [6] | Active | Possible library, but a heavier dependency than MLT with less reach |
| **Olive** | Node-based NLE | GPL-3.0 | **Stalled**: last code change Sep 2023, community asking for a fork [7][8] | Skip |
| **Remotion** | React components -> video | **Not OSI open source.** Free for individuals and companies of up to 3 people; companies of 4+ need a paid license, and "video editors / prompt-to-video tools" fall under the paid Automators tier ($0.01 per render, $100/month minimum) [9][10] | Very active, 61k★ | **Avoid as the core** of an open-source editor others will ship. Fine to study |
| **Motion Canvas** | TypeScript code-driven animation | MIT [11] | Active | Good for motion graphics and titles later. Not an NLE |
| **Revideo** | Fork of Motion Canvas with headless rendering, audio and a library-first API (now `midrender/revideo`) [12] | MIT | Active | Option for templated overlays and title cards rendered headless |
| **editly** | Declarative JSON -> video CLI on FFmpeg | MIT [13] | Slow (last push May 2025) | **Learn from it**: proof that a JSON spec is a workable edit description |
| **GStreamer + GES** | Pipelines, plus GStreamer Editing Services (timeline, layers, tracks; `ges-launch` renders) [14] | LGPL | Active | Viable engine, but heavier to package on Windows than FFmpeg/MLT |
| **WebCodecs** | Browser API for low-level encode/decode (`VideoEncoder`/`VideoDecoder`) [15] | W3C standard | Chromium yes, Firefox no (per caniuse) [16] | Fine inside Electron (Chromium). Good for scrubbing and fast previews; not needed for v1 |
| **mediabunny / mp4box.js / ffmpeg.wasm** | In-browser mux/demux and FFmpeg | MPL-2.0 / BSD-3 / MIT | Active | Only if editing ever moves fully into the browser |
| **OpenTimelineIO (OTIO)** | Industry interchange model: Timeline -> Stack -> Tracks -> Clips/Gaps/Transitions, with source ranges; adapters for FCP XML, Kdenlive/MLT and more [17][18] | Apache-2.0 | Active (ASWF) | **Shape our timeline JSON after it** and export to it. That gives Premiere/Resolve/Kdenlive round-trips for free |
| **PySceneDetect** | Shot/cut detection (Content, Adaptive detectors) [19] | BSD-3-Clause | Active | **Use it** for `detect_scenes` |
| **faster-whisper / WhisperX** | Word-timestamp transcription; WhisperX adds alignment and speaker labels | MIT / BSD-2 | Active | faster-whisper is already in. Consider WhisperX-style diarization for "cut speaker B" |
| **OpenCut** | "Open source CapCut alternative", 91k★ | MIT | **Being rewritten from scratch** (Rust core; Editor API, MCP server and headless mode are planned, and outside contributions are closed) [20] | Watch it; don't build on it now |
| **FableCut** | Browser NLE whose whole timeline is one `project.json`; MCP + REST; UI hot-reloads in ~150 ms over server-sent events, so a human and an agent edit together [21] | MIT | Active, 700★ | **Closest prior art to what Pablo wants.** Study its project-file-as-interface design |
| **mcpCut/OrcCut, OpenChatCut, resolve-mcp** | Small MCP-driven editors and bridges (MLT/FFmpeg render, transcript editing, Resolve scripting) [22] | MIT / AGPL-3.0 / MIT | Young | Confirms the pattern: JSON timeline + MCP tools + an MLT or FFmpeg render |

### 1.2 What this means

- **Nobody offers an engine we can drop in that is both permissively licensed and agent-ready.** The open NLEs are GPL desktop apps. OpenCut is mid-rewrite. Remotion's license doesn't fit an open-source editor.
- **The winning shape across the new projects is the same:** a timeline as one JSON document, a small set of validated edit operations, a push channel so the UI updates live, and FFmpeg or MLT to render. Hermes Studio already has every piece except the timeline document and the push channel.
- **License rule for us:** link only LGPL/MIT/BSD/Apache libraries. Call GPL tools (GPL FFmpeg build, MLT's `melt` with GPL plugins) as separate programs, and ship their notices and source links.

---

## 2. How AI-native editors work

| Product | The core idea | What to borrow |
|---|---|---|
| **Descript** | Transcribe, then **edit video by editing the text**: deleting or moving words changes the video. Underlord, its AI co-editor, works from the transcript (remove filler, tighten, captions, clips) and does best when given context such as scenes, script selections, speakers or timestamps [23][24][25] | Transcript as a first-class editing surface, kept in sync with the timeline. Let users attach a selection as context for the agent |
| **CapCut** | Auto Captions, Remove Filler Words, Auto Cut / Smart Cut (beat- or speech-aware), script-to-video [26][27] | One-click "macro" ops built from small primitive ops |
| **Runway (Aleph 2.0)** | Generative, in-context edits on a 2-30 s clip from a prompt ("Change X to Y. Keep Z unchanged"), with optional reference frames [28] | Later: generative ops are just another tool that returns a new media asset onto the timeline. The non-generative timeline stays the source of truth |
| **OpusClip** | ClipAnything finds moments from visual, audio and sentiment cues and prompts. Its Virality Score (0-99) covers hook, flow, value, trend. ReframeAnything tracks subjects [29] | Hermes Studio already does a local version (BridgeClip rubric, face framing). Feed those scores to the agent as data |
| **Captions (Mirage)** | "AI Edit" turns raw footage into an edited video (captions, B-roll, music, transitions) from a prompt or preset style; AI eye contact [30] | Style presets as named op bundles the agent can apply and the user can undo as one group |

**Common pattern:** the model never pushes pixels around directly. It reads **structured state** (transcript, scenes, scores, timeline) and issues **edit commands**. The app applies them, shows them and can reverse them. Generative video is an add-on that produces new clips.

---

## 3. What an agent needs to edit video end to end

1. **The timeline as structured data.** One JSON document (OTIO-shaped [17]) with a version number. The agent reads it with `timeline_get` (or as an MCP resource [31]).
2. **An action API.** Small, validated, ID-based ops: insert, move, trim, split, delete, ripple-delete, set property, add text/caption, add transition, keyframe. Batched ops apply as one atomic, all-or-nothing step. This is the same idea as `design.apply_ops()` already in the repo.
3. **Undo/redo and diff.** Every applied batch becomes an entry in an **op log** with its actor (user / agent name), a description and its inverse. The UI and the agent can both ask for a human-readable diff ("clip 3 trimmed 4.2 s from its end, everything after it moved left 4.2 s").
4. **Eyes.** The model must see what it did. Tools return **thumbnails, contact sheets (a grid of frames across a range) and single frames** as MCP image content [32]. Hermes routes images straight to vision-capable models and falls back to an auxiliary vision model otherwise [33].
5. **Ears / text.** Word-level transcript with speaker labels, mapped onto timeline time, so "cut every 'um'" or "remove the part about pricing" become text queries that turn into ranges.
6. **Scene and shot structure.** Scene cuts (PySceneDetect [19]), silence ranges, faces/speakers and the existing clip scores, all as data.
7. **Render and verify.** A quick low-res preview render and a final render as background jobs with progress, then `probe` the output. This matches the repo's detach-and-poll model.
8. **Guardrails.** Bounds checks (no clip past its source length), path rules (home folder only, as today), a cap on ops per batch, and **no publishing, ever** (house rule).

---

## 4. Hermes Agent: how it would plug in

Hermes Agent (Nous Research, MIT, ~250k★ [34]) has two directions that matter here.

### 4.1 Hermes calls our tools (we are the MCP server)

- Hermes reads `mcp_servers` from `~/.hermes/config.yaml`. It supports **stdio** (`command`/`args`) and **HTTP** (`url` + `headers`) servers, per-tool `include`/`exclude` filters, timeouts, `lazy` start, and `notifications/tools/list_changed` [35][36].
- Tools are registered as `mcp_<server>_<tool>` (for example `mcp_hermes_studio_timeline_apply`). Resources and prompts get utility wrappers when the server supports them [35].
- Hermes strips invisible Unicode tag characters from tool results and passes through vendor `_meta`. It supports MCP **elicitation** (a server can ask the user a structured question through Hermes's approval surface) and **sampling** [35].
- `hermes-studio mcp install hermes` already writes this config. Hermes Studio also ships a native plugin (`register(ctx)` -> `ctx.register_tool(name, toolset, schema, handler)` [37]). **Recommendation: make MCP the one surface** and keep the plugin as a thin shim or retire it, so tools don't drift (see audit §7).
- Image results: Hermes's vision routing returns pixels to vision-capable models [33], so `timeline_frames` / `timeline_contact_sheet` can return MCP `image` content blocks.

### 4.2 Our app talks to Hermes (the chat sidebar is a client)

Hermes offers three ways for a host app to drive it, all on the same `AIAgent` core [38]:

| Protocol | Transport | What the sidebar gets | Fit |
|---|---|---|---|
| **ACP** (`hermes acp`) | JSON-RPC over stdio | Sessions, prompts, **streamed message chunks, tool-call events, permission requests**, fork, cancel; tool output rendered as ACP `Diff`/`ToolCall` blocks [38][39] | **Best default.** It is an open standard (Apache-2.0 [40]), so the same sidebar also works with other ACP agents later. That covers "any AI model" |
| **TUI gateway** JSON-RPC | stdio or WebSocket | Everything: `prompt.submit`, `session.steer`, `session.interrupt`, `session.branch`, streamed `tool.start/complete`, server-to-client `approval`/`clarify` requests [38] | Richest, but Hermes-specific |
| **API server** | HTTP + SSE (OpenAI-compatible, plus `/v1/runs` with events, approval, steer, stop) [38][41] | Needs `hermes gateway` running and an API key; loopback by default | Good fallback for "bring any OpenAI-compatible model or endpoint" |

ACP details that line up with "watch, approve, undo" [42][43]:
- `session/update` streams `tool_call` / `tool_call_update` entries, which the sidebar shows live as "Trimming clip 3...".
- `session/request_permission` lets the client approve or reject a tool call. Hermes adds "allow for this session" [39].
- **Agent plans** (`plan` updates with entries and status) let the sidebar show the step list.
- Tool-call content can carry **diffs**. We will send our own human-readable timeline diff text.

**The loop:** the Electron app spawns `hermes acp` and passes it our MCP server (ACP sessions accept MCP servers; Hermes also loads them from `config.yaml` [39]). The user types "tighten the intro and add captions". Hermes plans, then calls `mcp_hermes_studio_*` tools. Each call hits **our engine**, which applies ops and pushes the new timeline to the UI. The sidebar shows each step with Approve / Undo.

---

## 5. Agent-in-the-loop UX patterns for the chat sidebar

- **Cursor:** the agent applies edits and shows them as a diff you accept or reject. **Restore Checkpoint** on any earlier chat message rolls files back to that point. Checkpoints are local and separate from Git [44][45].
- **VS Code Copilot agent mode:** per-file inline diffs with **Keep / Undo**, accept-all or reject-all, and **Restore Checkpoint** on a past request (later requests are removed). It warns that checkpoints don't undo external side effects [46][47].
- **Descript Underlord:** attach selections (scenes, script text, speakers, timestamps) as context [25].
- **ACP / Zed-style panels:** a streaming message, a plan list with statuses, tool-call cards and permission prompts [42][43].
- **FableCut:** the timeline updates live while the agent edits (SSE). Watching *is* the UX [21].

**What Hermes Studio should do (taken from the above):**
1. **Every agent edit is a card** in the sidebar: what changed in plain words, a thumbnail before and after, and **Undo** (plus **Redo**).
2. **Plan first for multi-step requests.** Show the step list; the user can approve all, step through, or edit the plan.
3. **Modes:** *Ask* (agent reads only), *Propose* (agent edits a **draft branch**; the user clicks Keep or Discard), *Auto* (edits apply live; each one can still be undone). Default: *Propose*.
4. **Checkpoints** at every user message. "Restore to here" rolls the timeline back.
5. **Human in command:** user input always wins. If the user edits while the agent works, the agent's next op is checked against the new version and rejected if stale. A visible **Stop** button sends `session/cancel`.
6. **Highlight on the timeline:** clips the agent touched get a coloured outline and a tag with the agent's name, and the playhead jumps there.
7. **Selection as context:** select clips or transcript text, then "Ask Hermes about this".
8. **No external side effects without a prompt:** rendering to disk is fine. Uploading or posting is never available to the agent.

---

## Sources

1. FFmpeg, "License and Legal Considerations." https://ffmpeg.org/legal.html
2. MLT, "MLT XML" documentation. https://www.mltframework.org/docs/mltxml/
3. mltframework/mlt (LGPL-2.1). https://github.com/mltframework/mlt
4. mltframework/shotcut (GPL-3.0). https://github.com/mltframework/shotcut
5. KDE/kdenlive (GPL-3.0). https://github.com/KDE/kdenlive
6. OpenShot/libopenshot (LGPL-3.0). https://github.com/OpenShot/libopenshot
7. Olive releases ("The last code change is from 2023-09-24"). https://github.com/olive-editor/olive/releases
8. Olive discussion #2390, "Olive's Future." https://github.com/olive-editor/olive/discussions/2390
9. Remotion License FAQ. https://www.remotion.dev/docs/license-pricing-compliance/faq
10. Remotion LICENSE.md. https://github.com/remotion-dev/remotion/blob/HEAD/LICENSE.md
11. motion-canvas/motion-canvas (MIT). https://github.com/motion-canvas/motion-canvas
12. Revideo docs and README. https://midrender.com/revideo , https://github.com/midrender/revideo
13. mifi/editly (MIT). https://github.com/mifi/editly
14. GStreamer Editing Services docs. https://gstreamer.freedesktop.org/documentation/gst-editing-services/ ; ges-launch: https://gstreamer.freedesktop.org/documentation/tools/ges-launch.html
15. MDN, WebCodecs API. https://developer.mozilla.org/en-US/docs/Web/API/WebCodecs_API
16. Can I use: WebCodecs. https://caniuse.com/webcodecs
17. OpenTimelineIO, "Timeline Structure." https://opentimelineio.readthedocs.io/en/latest/tutorials/otio-timeline-structure.html
18. OpenTimelineIO, "Adapters." https://opentimelineio.readthedocs.io/en/latest/tutorials/adapters.html
19. PySceneDetect detectors and API. https://www.scenedetect.com/docs/latest/api/detectors.html
20. OpenCut README ("being rewritten from the ground up"). https://github.com/OpenCut-app/OpenCut
21. FableCut README. https://github.com/ronak-create/FableCut
22. Prior-art MCP editors: https://github.com/musyta-labs/mcpCut (now OrcCut), https://github.com/afeibuhuifei/OpenChatCut , https://github.com/jenkinsm13/resolve-mcp
23. Descript, "Edit video by typing." https://www.descript.com/video-editing
24. Descript Help, "Underlord: your AI co-editor." https://help.descript.com/hc/en-us/articles/36803785502221
25. Descript blog, "Context beats wording." https://www.descript.com/blog/article/the-secret-to-better-ai-video-editing-context-not-prompts
26. CapCut, AI tools. https://www.capcut.com/resource/capcut-ai
27. CapCut Help, "How to use Auto Cut." https://www.capcut.com/help/how-to-use-auto-cut
28. Runway, Aleph 2.0 and Prompting Guide. https://runway.com/product/aleph-2 , https://help.runwayml.com/hc/en-us/articles/52150503729171
29. OpusClip ClipAnything and Virality Score. https://www.opus.pro/clipanything , https://help.opus.pro/docs/article/virality-score
30. Captions, AI Edit. https://www.captions.ai/features/automatic-video-editor
31. MCP spec 2025-11-25, Resources. https://modelcontextprotocol.io/specification/2025-11-25/server/resources
32. MCP spec 2025-11-25, Tools (image content, structuredContent). https://modelcontextprotocol.io/specification/2025-11-25/server/tools
33. Hermes Agent, "Vision & Image Paste." https://hermes-agent.nousresearch.com/docs/user-guide/features/vision
34. NousResearch/hermes-agent (MIT). https://github.com/NousResearch/hermes-agent
35. Hermes Agent, "MCP." https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp
36. Hermes Agent, "MCP Config Reference." https://hermes-agent.nousresearch.com/docs/reference/mcp-config-reference
37. Hermes Agent, "Plugins." https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins
38. Hermes Agent, "Programmatic Integration" (ACP, TUI gateway, API server). https://hermes-agent.nousresearch.com/docs/developer-guide/programmatic-integration
39. Hermes Agent, "ACP Host Integration." https://hermes-agent.nousresearch.com/docs/user-guide/features/acp
40. agentclientprotocol/agent-client-protocol (Apache-2.0). https://github.com/agentclientprotocol/agent-client-protocol
41. Hermes Agent, "API Server." https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server
42. ACP, "Tool Calls." https://agentclientprotocol.com/protocol/v2/tool-calls
43. ACP, "Agent Plan." https://agentclientprotocol.com/protocol/v2/agent-plan
44. Cursor docs, Agent overview (checkpoints). https://cursor.com/docs/agent/overview
45. Cursor help, Agent (review diffs, accept/reject). https://cursor.com/help/ai-features/agent
46. VS Code, "Review and revert agent changes." https://code.visualstudio.com/docs/agents/run/review-code-edits
47. VS Code, "Chat checkpoints." https://code.visualstudio.com/docs/chat/chat-checkpoints
