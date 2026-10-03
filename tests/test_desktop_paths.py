"""desktop/paths.js renderFile: "Show in folder" only reveals an .mp4 directly in one project's
exports/ (run under Node; skipped where Node isn't installed)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs Node")


def render_file(root: Path, pid: str, rel: str) -> str | None:
    js = f"process.stdout.write(JSON.stringify(require({json.dumps(str(ROOT / 'desktop' / 'paths.js'))}).renderFile(...{json.dumps([str(root), pid, rel])})))"
    return json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)


def test_only_an_mp4_in_that_projects_exports(tmp_path):
    root = tmp_path / "projects"
    (root / "p1" / "exports" / "deep").mkdir(parents=True)
    good = root / "p1" / "exports" / "p1-v000001-540x960.mp4"
    good.write_bytes(b"x")
    (root / "p1" / "base.json").write_text("{}")
    (root / "p1" / "exports" / "deep" / "x.mp4").write_bytes(b"x")
    (tmp_path / "exports").mkdir()
    (tmp_path / "exports" / "x.mp4").write_bytes(b"x")  # what ".." would reach
    (tmp_path / "secret.mp4").write_bytes(b"x")
    os.symlink(tmp_path / "secret.mp4", root / "p1" / "exports" / "link.mp4")
    assert render_file(root, "p1", "exports/p1-v000001-540x960.mp4") == str(good.resolve())
    for pid, rel in [
        ("..", "exports/x.mp4"),
        ("D:", "exports/x.mp4"),
        ("p1", "../../exports/x.mp4"),
        ("p1", "exports/link.mp4"),  # a link out of exports
        ("p1", "base.json"),
        ("p1", "exports/deep/x.mp4"),
        ("p1", str(tmp_path / "secret.mp4")),
        ("p2", "exports/p1-v000001-540x960.mp4"),
    ]:
        assert render_file(root, pid, rel) is None, (pid, rel)
