"""review_checks.py: warning-level scan for environ spreads and hardcoded Hermes paths."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "review_checks",
    Path(__file__).resolve().parents[1] / "scripts" / "review_checks.py",
)
_rc = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_rc)
run_checks = _rc.run_checks
scan_env = _rc.scan_env
scan_paths = _rc.scan_paths
_is_clips_default = _rc._is_clips_default

FIXTURE = '''
import os, subprocess
def bad():
    env = {**os.environ, "A": "1"}
    subprocess.Popen(["x"], env=dict(os.environ))
    other = os.environ.copy()
    home = Path.home() / ".hermes" / "stash"
def good_clips():
    return Path.home() / ".hermes" / "clips" / "library"
def _data_dir():
    home = Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")
    return home / "plugin-data" / "hermes-studio"
'''


def test_planted_environ_spreads_and_paths(tmp_path: Path):
    p = tmp_path / "plant.py"
    p.write_text(FIXTURE)
    env = scan_env(p, FIXTURE)
    assert {w["detail"] for w in env} >= {"{**os.environ} spread", "dict(os.environ)", "os.environ.copy()"}
    assert all("minimal env" in w["message"] for w in env)
    paths = scan_paths(p, FIXTURE)
    details = [w["detail"] for w in paths]
    assert any("stash" in d for d in details)
    assert not any("clips" in d and "library" in d for d in details)
    # sanctioned _data_dir fallback is allowlisted
    assert not any("_data_dir" in d or "plugin-data" in d for d in details)


def test_clips_allowlist():
    assert _is_clips_default('return Path.home() / ".hermes" / "clips"')
    assert _is_clips_default('p = Path.home() / ".hermes" / "clips" / "library"')
    assert _is_clips_default('must be inside ~/.hermes/clips or HERMES_STUDIO_OUT_ROOTS')
    assert not _is_clips_default('Path.home() / ".hermes" / "hermes-studio" / "editor"')
    assert not _is_clips_default('Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")')


def test_current_tree_flags_known_leftovers():
    warnings = run_checks()
    rules = {(w["rule"], w["file"], w["line"]) for w in warnings}
    assert ("environ-spread", "hermes_studio/cli.py", 478) in rules
    assert ("hermes-path", "hermes_studio/editor.py", 35) in rules
    assert ("hermes-path", "hermes_studio/mcp.py", 836) in rules
    # Allowlisted out-root default and the plugin data-dir fallback must stay quiet.
    assert not any(w["file"].endswith("pipeline.py") and w["rule"] == "hermes-path" for w in warnings)
    assert not any("hermes_plugin/hermes-studio/__init__.py" == w["file"] and w["rule"] == "hermes-path" for w in warnings)
