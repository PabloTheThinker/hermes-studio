"""Where the desktop app lives, how to open it, and how to update it.

Installed with the one-line installer, the app keeps its own engine and a small
``hermes-studio`` launcher inside it; ``HERMES_STUDIO_EXE`` points at that
launcher whenever it is the one running. Installed with pip/uv, there is no app
here, only the command line.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from hermes_studio import __version__
from hermes_studio.api import HermesStudioError

REPO = "PabloTheThinker/hermes-studio"
INSTALL_SH = f"https://raw.githubusercontent.com/{REPO}/main/scripts/install.sh"
INSTALL_PS1 = f"https://raw.githubusercontent.com/{REPO}/main/scripts/install.ps1"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"


def _engine_dir() -> Path | None:
    """The app's engine folder when this command is the one inside the app."""
    exe = os.environ.get("HERMES_STUDIO_EXE", "")
    if exe and Path(exe).is_file():
        return Path(exe).resolve().parent
    return None


def app_path() -> Path | None:
    """The desktop app's program, if one is installed."""
    candidates: list[Path] = []
    engine = _engine_dir()
    if engine is not None:  # <app>/resources/engine
        root = engine.parent.parent
        candidates += [root / "hermes-studio", root / "Hermes Studio.exe"]
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            candidates.append(Path(local) / "Programs" / "Hermes Studio" / "Hermes Studio.exe")
    else:
        data = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
        candidates.append(data / "hermes-studio" / "app" / "hermes-studio")
    for c in candidates:
        if c.is_file():
            return c
    return None


def how_installed() -> str:
    """'app' (the one-line installer / desktop app) or 'package' (pip, uv, pipx, source)."""
    return "app" if _engine_dir() is not None else "package"


def open_app() -> dict:
    """Start the desktop app in the background."""
    exe = app_path()
    if exe is None:
        raise HermesStudioError(
            "The Hermes Studio app isn't installed on this computer.",
            code="not_found",
            hint=f"Install it: {install_line()}  ·  or open the desk in your browser: hermes-studio studio",
        )
    args = [str(exe)]
    if os.name != "nt":
        args.append("--no-sandbox")
    kw: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kw["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    else:
        kw["start_new_session"] = True
    env = {k: v for k, v in os.environ.items() if k not in ("HERMES_STUDIO_EXE", "PYTHONHOME", "PYTHONPATH")}
    subprocess.Popen(args, env=env, **kw)  # noqa: S603 - fixed program path, no shell
    return {"ok": True, "app": str(exe)}


def install_line() -> str:
    if os.name == "nt":
        return f"irm {INSTALL_PS1} | iex"
    return f"curl -fsSL {INSTALL_SH} | bash"


def latest_version(timeout: float = 15) -> str:
    """The newest published release, e.g. '0.5.2'."""
    req = urllib.request.Request(LATEST_API, headers={"Accept": "application/vnd.github+json", "User-Agent": f"hermes-studio/{__version__}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - fixed https URL
            tag = json.load(r).get("tag_name", "")
    except Exception as exc:
        raise HermesStudioError("Couldn't reach GitHub to check for updates.", code="failed", hint=str(exc)[:200]) from exc
    if not tag:
        raise HermesStudioError("GitHub returned no release.", code="failed")
    return tag.lstrip("v")


def _newer(a: str, b: str) -> bool:
    """True if version a is newer than b."""
    def parts(v: str) -> tuple:
        out = []
        for x in v.split("."):
            digits = "".join(ch for ch in x if ch.isdigit())
            out.append(int(digits) if digits else 0)
        return tuple(out)
    return parts(a) > parts(b)


def check() -> dict:
    latest = latest_version()
    return {"ok": True, "current": __version__, "latest": latest, "update_available": _newer(latest, __version__),
            "installed_as": how_installed()}


def update(check_only: bool = False) -> dict:
    """Update to the latest release the same way it was installed."""
    info = check()
    if check_only or not info["update_available"]:
        return info
    if how_installed() == "package":
        uv, pipx = shutil.which("uv"), shutil.which("pipx")
        hint = ("uv tool upgrade hermes-studio" if uv else "pipx upgrade hermes-studio" if pipx
                else f"pip install -U git+https://github.com/{REPO}")
        raise HermesStudioError(f"Version {info['latest']} is out (you have {__version__}). This copy was installed as a Python package.",
                              code="failed", hint=f"Update it with: {hint}  ·  or get the app: {install_line()}")
    if os.name == "nt":
        argv = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", f"irm {INSTALL_PS1} | iex"]
        proc = subprocess.run(argv)  # noqa: S603 - fixed command
    else:
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "install.sh"
            try:
                with urllib.request.urlopen(INSTALL_SH, timeout=60) as r:  # noqa: S310 - fixed https URL
                    script.write_bytes(r.read())
            except Exception as exc:
                raise HermesStudioError("Couldn't download the installer.", code="failed", hint=str(exc)[:200]) from exc
            env = {k: v for k, v in os.environ.items() if k not in ("HERMES_STUDIO_EXE", "PYTHONHOME", "PYTHONPATH")}
            # stdout of the installer goes to stderr so `--json` keeps one object on stdout.
            proc = subprocess.run(["bash", str(script)], env=env, stdout=sys.stderr)  # noqa: S603, S607
    if proc.returncode != 0:
        raise HermesStudioError("The update didn't finish.", code="failed", hint=f"Run the installer by hand: {install_line()}")
    return {**info, "updated": True, "update_available": False}
