# Descript teardown (proprietary SaaS; reference only)

**What it is:** a transcript-first ("edit like a doc") audio/video editor with an agentic AI co-editor, **Underlord (beta)**.
**Sources:** [help.descript.com](https://help.descript.com/llms.txt) pages fetched as Markdown on Oct 1, 2026, plus descript.com marketing pages.
**Install:** none (an account is required).
**Screenshots:** `screenshots/descript/` holds 14 official images:
- 10 from descript.com marketing (01–10)
- 4 from the help center (11–14): the editor interface tour, the Underlord model picker, the Underlord Revert button and the filler-words review sidebar

## 1. UI/UX

- **Editor areas** ([The editor interface](https://help.descript.com/descript-tour/the-editor-interface)); see `11-editor-interface-tour-help.png`:
  - **Script editor:** the transcript is the primary edit surface.
  - **Scene editor:** the visual canvas.
  - **Timeline:** "a more traditional view with audio waveforms", optional (toggle with Shift+Cmd+S).
  - **Right sidebar** with panels: Project, Scene, Layer, Elements, Media, **AI Tools**, **Underlord**.
- **The Underlord chat lives in the right sidebar, next to the script.** Open any project, click the Underlord icon in the right-hand sidebar and chat ([Underlord](https://help.descript.com/getting-started/underlord-beta-your-ai-co-editor-in-descript)). See:
  - `01-underlord-chat-beside-transcript-editor.png`
  - `02-meet-underlord-agent-panel.png`
  - `03-underlord-prompt-panel.png`
  - `12-underlord-model-picker.png`
  - A model picker (cube icon) offers multiple vendor models.
- **Agent undo** ([Revert](https://help.descript.com/ai-assistant/revert); `13-underlord-revert-button.png`):
  - Underlord "creates checkpoints before making changes", shown in the chat "just before edits are applied".
  - Each response has a **Revert** button in its action bar (alongside thumbs up/down).
  - There is also normal Undo (Cmd/Ctrl+Z) and Version History.
  - Checkpoints last only for the session; after a refresh, use Version History.
- **Scenes:** the script is divided into scenes that control which visuals appear (help: Scenes overview).

## 2. Functions

| Area | Descript |
|---|---|
| Text-based editing | Delete text to delete media; cut/paste sentences to move media; non-destructive with "Restore removed media"; **Ignore** (strike through but keep visible); **Remove from transcript** (keep media, hide text); Correct mode; wordbar for word timing ([Edit like a doc](https://help.descript.com/getting-started/edit-like-a-doc)) |
| Filler words | Auto-detected (English only), underlined in light blue; review sidebar with per-instance **Delete / Delete and replace with gap / Ignore / Remove from transcript**; "Avoid harsh cuts" option ([Filler words](https://help.descript.com/script-editing/filler-words); `14-remove-filler-words-sidebar.png`) |
| AI tools | Studio Sound, Remove Filler Words, Shorten Word Gaps, Edit for Clarity, and more in the AI Tools panel |
| Underlord tasks (examples from help) | Styled captions, splitting into N clips under 1 min, finding social clips and reformatting to vertical, pan/zoom animations, fades, zoom cuts, translation, Studio Sound, ducking other layers, slides-to-video with TTS/avatars |
| Timeline tools | Select A, Range R, **Blade B**, Hand H, **Slip Y** (all "or hold"); split S; replace with gap clip Shift+Delete ([Keyboard shortcuts](https://help.descript.com/descript-tour/keyboard-shortcuts)) |
| Layers/scenes | Layers (video, image, text, shapes, captions), scene layouts, transitions, properties panel (`10-properties-panel-adjustments.png`) |
| Captions | Captions layer with styles |
| Outside access | **Descript MCP** for Claude, ChatGPT, Cursor or a custom connector; Descript API; Zapier ([Descript MCP](https://help.descript.com/api-and-mcp/mcp)). The MCP can import media, edit with Underlord, manage projects, publish a web link, and export transcripts (txt/md/html/rtf/srt) |
| Billing | Underlord prompts use AI credits; non-deterministic cost (help note) |

## 3. Keyboard model

From [Keyboard shortcuts](https://help.descript.com/descript-tour/keyboard-shortcuts):

- **Context:** single-letter shortcuts work only in the Script Editor when Write or Correct mode is off. Opt/Ctrl+/ shows the list.
- **Playback:**
  - Space play/pause; Shift+Space play from cursor
  - ←/→ step a frame
  - **Shift+J / Shift+K / Shift+L** decrease / reset / increase playback speed (not classic JKL shuttle)
- **Timeline tools:** A select, R range, B blade, H hand, Y slip, S split.
- **Other:** Cmd/Ctrl+K "Search actions" (a command palette). In the script, hold Z / X + click to fix capitalization or punctuation, and C corrects.

## 4. Lessons for Hermes Studio (closest product analogue)

1. **Validation.** Descript ships what the plan proposes: a transcript-first editor plus an agent chat in the right sidebar plus an MCP for outside agents. Hermes Studio's differentiators have to be **local/offline + open source (MIT) + Propose-by-default with per-op cards + one engine shared by humans, Hermes (ACP) and any MCP client**. Descript's MCP goes through its cloud login and its edits cost AI credits.
2. **Copy these UX details:**
   - per-response **Revert** in the chat, with a checkpoint shown *before* edits (our per-card Undo plus a checkpoint per message)
   - the filler-word review list with per-item actions (our Remove-fillers card should expand into this list)
   - **Ignore = strike-through but kept**, which matches the plan's "cut words are struck through"
   - "Delete and replace with gap" as an explicit option
   - a Cmd+K action search
3. **Avoid** their caveat ("Underlord might overpromise… follow you into workflows it's not equipped to complete"). Our engine-enforced modes and allowlisted tools are the structural answer; keep that front and centre in the UI.
