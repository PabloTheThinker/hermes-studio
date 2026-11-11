"""M9: workspace layouts, shortcut sheet, crash-recovery of the op log."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from hermes_studio import editor as E

ROOT = Path(__file__).resolve().parents[1]


def test_shortcut_sheet_and_workspace_live_in_editor_js():
    js = (ROOT / "hermes_studio" / "ui" / "editor.js").read_text()
    assert "function helpMarkup" in js
    assert 'data-act="ws-edit"' in js
    assert 'data-act="ws-colour"' in js
    assert 'data-act="ws-audio"' in js
    assert "const SHORTCUTS" in js
    assert 'setWorkspace(k === "1"' in js
    assert "Empty timeline." in js
    assert "placeFromBin" in js and "wireBinDrop" in js
    assert "Drag bin → timeline" in js
    html = (ROOT / "hermes_studio" / "ui" / "index.html").read_text()
    assert "editor.js?v=" in html


def test_kill_mid_edit_keeps_marker(home, tmp_path):
    """A child process writes a marker, then exits hard; a fresh load still has it."""
    E.create("demo")
    child = tmp_path / "child.py"
    child.write_text(
        "\n".join(
            [
                "import os, sys",
                f"os.environ['HERMES_STUDIO_EDITOR'] = {str(home)!r}",
                f"sys.path.insert(0, {str(ROOT)!r})",
                "from hermes_studio import editor as E",
                "E.add_marker('demo', 1.25, 'survives-crash')",
                "print('wrote')",
                "sys.stdout.flush()",
                "os._exit(0)",
            ]
        )
    )
    env = os.environ.copy()
    env["HERMES_STUDIO_EDITOR"] = str(home)
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    r = subprocess.run([sys.executable, str(child)], env=env, capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr + r.stdout
    assert "wrote" in r.stdout
    labels = [m["label"] for m in E.view(E._log(E._dir("demo")).doc)["markers"]]
    assert "survives-crash" in labels
