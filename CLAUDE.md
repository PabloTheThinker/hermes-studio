# AGENTS.md — using and working on Hermes Studio

Hermes Studio (`hermes-studio`) turns long video into captioned short clips on the local machine. It never uploads or posts.

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

## Working on the code

- One core: `hermes_studio/api.py` (validation, errors, results). `cli.py`, `mcp.py` and the Hermes plugin are thin layers over it. Add behaviour to `api.py`, then expose it.
- Rendering and jobs live in `pipeline.py`; the desk is `studio.py` + `ui/index.html`; the desktop shell is `desktop/`.
- Checks: `.venv/bin/python -m pytest -q` and `ruff check hermes_studio tests hermes_plugin`. `tests/test_cli_contract.py` guards the JSON, exit-code and MCP contracts; keep it green.
- House look: black, warm ink, one amber accent (`#ffc83d`). Plain words.
