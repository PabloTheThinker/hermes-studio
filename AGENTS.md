# AGENTS.md — using and working on Hermes Studio

Hermes Studio (`hermes-studio`) turns long video into captioned short clips on the local machine. It never uploads or posts.

## Installing it for a user

One line; no admin rights, no Python, no FFmpeg (they ship inside the app). It verifies the download's SHA-256.

```bash
curl -fsSL https://raw.githubusercontent.com/PabloTheThinker/hermes-studio/main/scripts/install.sh | bash          # Linux
irm https://raw.githubusercontent.com/PabloTheThinker/hermes-studio/main/scripts/install.ps1 | iex                  # Windows PowerShell
```

Then `hermes-studio doctor --json` should return `"ok": true`, and `hermes-studio mcp install <claude|grok|codex|cursor|hermes>` wires up the AI app. `hermes-studio update` gets newer releases.

## Using it as an agent

Prefer the MCP server (`hermes-studio mcp`, tools `run`, `show`, `list`, `restyle`, `edit`, `probe`, `recommend`, `copy`, `name`, `tools`, `doctor`). Without MCP, call the CLI with `--json`:

```bash
hermes-studio doctor --json                       # once, if unsure the machine is ready
hermes-studio run <file-or-url> -n 3 --json       # blocks; one JSON object on stdout
hermes-studio run <file-or-url> --detach --json   # returns {"id": …} at once
hermes-studio show <id> --json                    # poll until status is completed | failed
hermes-studio restyle <id> clip-01.mp4 --layout split --filter cinematic --json
hermes-studio copy <id> --json                    # titles, description, hashtags
```

- stdout is exactly one JSON object; progress is JSON lines on stderr. Read `items[].path`, `title`, `score`, `seconds`.
- Exit codes: 0 ok, 1 failed, 2 bad input, 3 missing dependency (run `doctor`), 4 not found. Errors have `code` + `hint`.
- Local files must be under the user's home folder or a mounted drive (a safety rule, not a bug).
- A clip run takes about 20 s per minute of source on a laptop CPU. Use `--detach` for anything long.
- Never post, upload or share clips yourself. Hand the paths to the user.

## Editing a timeline as an agent (the Edit page)

The desk's **Edit** page is a timeline editor that the person and agents share through one engine. Over MCP (stdio or the app's `/mcp`), the timeline tools all take a `project_id`:

- Look: `project_list`, `timeline_outline` (start here: the edit in seconds and plain words, with ids, gaps and markers), `get_timeline` (the exact doc: integer ticks, 705600000 per second), `get_transcript` (for a long talk pass `format: "text"` and a `from_s`/`to_s` window), `timeline_contact_sheet`, `timeline_frames`, `history_diff`, `history_explain` (one entry's change as outline lines removed and added).
- Try: `timeline_check` runs ops exactly as `timeline_apply` would and returns what would change and an outline of the result, or the same refusal, without writing (any mode, Ask too).
- Change: `timeline_apply` (ops in one batch; send `base_version`, `summary` and a fresh `client_op_id`; seconds go in `_s` args such as `at_s`; besides insert/move/trim/split/delete there are `slip_clip`, `roll_edit` and `edit_marker`), `apply_preset` (fades, title and end cards, crossfades, ducking, `close_gaps`), `transcript_cut` (fillers, pauses or ranges as one entry), `import_media`, `history_undo`, `history_redo`. Every change is one entry the person can undo.
- Deliver: `render_timeline`, then `render_status` until `ready`; hand the person the `path`. `render_cancel` stops one.
- **Modes:** in Propose (the default) a write returns `needs_approval` with a `pending_id`. Don't resend it with a new `client_op_id`: wait on `approval_status` until it's `applied`, `skipped` or `failed`. `approval_status {preview: true}` shows what Apply would do now. In Ask mode writes are `permission_denied`. Only the person changes the mode or applies edits.
- A stale `base_version` is `conflict` with `history_diff`: the person edited. Re-read, then decide; don't retry blindly.
- Writes need the app running (`engine_offline` otherwise). Reads work with it closed.

## Working on the code

- One core: `hermes_studio/api.py` (validation, errors, results). `cli.py`, `mcp.py` and the Hermes plugin are thin layers over it. Add behaviour to `api.py`, then expose it.
- Rendering and jobs live in `pipeline.py`; the desk is `studio.py` + `ui/index.html`; the desktop shell is `desktop/`.
- The timeline editor: `timeline.py` (schema, hash), `oplog.py` (the only writer), `project.py` (store, lock, events), `mcp_timeline.py` (tools), `http_engine.py` (REST + `/mcp`), `media*.py`, `frames.py`, `render_timeline.py`, `cuts.py`, `gate.py`, and `ui/edit.js`. Specs are in `docs/plans/S*-SPEC.md`.
- Checks: `.venv/bin/python -m pytest -q` and `ruff check hermes_studio tests hermes_plugin`. `tests/test_cli_contract.py` guards the JSON, exit-code and MCP contracts; keep it green.
- House look: black, warm ink, one amber accent (`#ffc83d`). Plain words.
