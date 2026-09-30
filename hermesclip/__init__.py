"""Hermes Studio engine (hermesclip): long video in, captioned short clips out. Runs locally; never posts."""

import os as _os
import sys as _sys
from pathlib import Path as _Path

__version__ = "0.5.0"


def _use_bundled_tools() -> None:
    """The desktop app ships FFmpeg next to its Python: <engine>/python + <engine>/bin.

    When that Python is started directly (by an AI app over MCP, or a script), put the
    bundled bin/ on PATH so FFmpeg is found without any setup.
    """
    try:
        prefix = _Path(_sys.prefix)
        tools = prefix.parent / "bin"
        exe = "ffmpeg.exe" if _os.name == "nt" else "ffmpeg"
        if prefix.name == "python" and (tools / exe).is_file():
            path = _os.environ.get("PATH", "")
            if str(tools) not in path.split(_os.pathsep):
                _os.environ["PATH"] = str(tools) + _os.pathsep + path
    except OSError:
        pass


_use_bundled_tools()
