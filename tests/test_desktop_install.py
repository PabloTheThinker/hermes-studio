"""The desktop-app side of the command: `app`, `update`, and a stable MCP command path."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from hermes_studio import desktop, mcp
from hermes_studio.api import HermesStudioError

ROOT = Path(__file__).resolve().parents[1]


def fake_app(tmp_path: Path) -> Path:
    """An installed app laid out like ~/.local/share/hermes-studio/app."""
    app = tmp_path / "app"
    engine = app / "resources" / "engine"
    engine.mkdir(parents=True)
    (app / "hermes-studio").write_text("#!/bin/sh\n")
    shim = engine / "hermes-studio"
    shim.write_text("#!/bin/sh\n")
    return shim


def test_mcp_uses_the_launcher_inside_an_installed_app(tmp_path, monkeypatch):
    shim = fake_app(tmp_path)
    monkeypatch.setenv("HERMES_STUDIO_EXE", str(shim))
    assert mcp.client_config() == {"command": str(shim), "args": ["mcp"]}


def test_mcp_never_uses_a_temporary_appimage_mount(tmp_path, monkeypatch):
    mount = tmp_path / ".mount_HermesX" / "resources" / "engine"
    mount.mkdir(parents=True)
    (mount / "hermes-studio").write_text("#!/bin/sh\n")
    monkeypatch.setenv("HERMES_STUDIO_EXE", str(mount / "hermes-studio"))
    assert ".mount_" not in mcp.client_config()["command"]


def test_app_found_next_to_the_engine(tmp_path, monkeypatch):
    shim = fake_app(tmp_path)
    monkeypatch.setenv("HERMES_STUDIO_EXE", str(shim))
    assert desktop.how_installed() == "app"
    assert desktop.app_path() == (tmp_path / "app" / "hermes-studio").resolve()


def test_package_install_has_no_app(tmp_path, monkeypatch):
    monkeypatch.delenv("HERMES_STUDIO_EXE", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert desktop.how_installed() == "package"
    assert desktop.app_path() is None
    with pytest.raises(HermesStudioError) as e:
        desktop.open_app()
    assert e.value.code == "not_found"
    assert "install.sh" in e.value.hint or "install.ps1" in e.value.hint


@pytest.mark.parametrize(("a", "b", "newer"), [
    ("0.5.2", "0.5.1", True), ("0.6.0", "0.5.9", True), ("0.10.0", "0.9.0", True),
    ("0.5.1", "0.5.1", False), ("0.5.0", "0.5.1", False),
])
def test_version_compare(a, b, newer):
    assert desktop._newer(a, b) is newer


def test_update_check_reports_without_changing_anything(monkeypatch):
    monkeypatch.setattr(desktop, "latest_version", lambda timeout=15: "99.0.0")
    res = desktop.update(check_only=True)
    assert res["update_available"] is True and res["latest"] == "99.0.0" and "updated" not in res


def test_package_update_says_how_instead_of_guessing(monkeypatch):
    monkeypatch.delenv("HERMES_STUDIO_EXE", raising=False)
    monkeypatch.setattr(desktop, "latest_version", lambda timeout=15: "99.0.0")
    with pytest.raises(HermesStudioError) as e:
        desktop.update()
    assert "99.0.0" in e.value.message and "Update it with" in e.value.hint


def test_up_to_date_is_a_noop(monkeypatch):
    from hermes_studio import __version__

    monkeypatch.setattr(desktop, "latest_version", lambda timeout=15: __version__)
    res = desktop.update()
    assert res["ok"] and res["update_available"] is False and "updated" not in res


def test_app_command_json_error_when_not_installed(tmp_path):
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "XDG_DATA_HOME": str(tmp_path), "LOCALAPPDATA": str(tmp_path)}
    p = subprocess.run([sys.executable, "-m", "hermes_studio", "app", "--json"], capture_output=True, text=True, cwd=ROOT, env=env, timeout=60)
    assert p.returncode == 4
    body = json.loads(p.stdout)
    assert body["ok"] is False and body["code"] == "not_found"


def test_installers_exist_and_point_at_this_repo():
    sh = (ROOT / "scripts" / "install.sh").read_text()
    ps = (ROOT / "scripts" / "install.ps1").read_text()
    for text in (sh, ps):
        assert "PabloTheThinker/hermes-studio" in text
        assert "SHA256SUMS.txt" in text  # every download is checked
    # Never runs anything as root: sudo only ever appears inside advice text the user reads.
    for line in sh.splitlines():
        code = line.split("#", 1)[0]
        if "sudo" in code and "(no sudo)" not in code:
            assert "fail " in code or "warn " in code, line
    assert desktop.INSTALL_SH.endswith("/scripts/install.sh") and desktop.INSTALL_PS1.endswith("/scripts/install.ps1")
