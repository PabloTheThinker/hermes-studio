"""CI tests against the same pinned FFmpeg the desktop app ships (Rin's CI-FFMPEG.md)."""

import re
from pathlib import Path

WF = Path(__file__).resolve().parent.parent / ".github" / "workflows"


def _env(text: str, name: str) -> str:
    m = re.search(rf"^\s+{name}:\s*(\S+)\s*$", text, re.M)
    assert m, f"{name} missing"
    return m.group(1)


def test_ci_ffmpeg_pin_matches_desktop():
    ci, desktop = (WF / "ci.yml").read_text(), (WF / "desktop.yml").read_text()
    for name in ("FFMPEG_LINUX_URL", "FFMPEG_LINUX_SHA256"):
        assert _env(ci, name) == _env(desktop, name), f"{name}: ci.yml and desktop.yml differ"
    assert _env(ci, "FFMPEG_VERSION") in _env(ci, "FFMPEG_LINUX_URL")


def _steps() -> dict[str, str]:
    """The test job's steps as raw text, keyed by id (or name). Plain text, so no YAML dependency."""
    job = (WF / "ci.yml").read_text().split("\n  test:\n", 1)[1].split("\n  secrets:\n", 1)[0]
    out = {}
    for block in job.split("\n      - ")[1:]:
        m = re.search(r"^\s*id: (\S+)$", block, re.M) or re.search(r"^(?:name: )?(.+)$", block, re.M)
        out[m.group(1)] = block
    return out


def _field(block: str, name: str) -> str:
    m = re.search(rf"^\s*{name}: (.+)$", block, re.M)
    assert m, name
    return m.group(1).strip()


def test_ci_ffmpeg_cache_key_has_version_and_sha_and_the_sha_is_checked_on_every_run():
    s = _steps()
    key = _field(s["ffmpeg-cache"], "key")
    assert "env.FFMPEG_VERSION" in key and "env.FFMPEG_LINUX_SHA256" in key
    check = next(line for line in s["ffmpeg"].splitlines() if "sha256sum -c" in line)
    assert check.startswith("          echo"), "the sha256 check must run at the top level, not only on a cache miss"
    assert _field(s["ffmpeg"], "timeout-minutes") == "3"


def test_ci_apt_only_in_the_bounded_fallback_and_pip_in_its_own_step():
    s = _steps()
    with_apt = [k for k, v in s.items() if "apt-get" in v]
    assert len(with_apt) == 1
    fb = s[with_apt[0]]
    assert _field(fb, "if") == "steps.ffmpeg.outputs.fallback == 'true'" and _field(fb, "timeout-minutes") == "4"
    pip = s["Python deps"]
    assert _field(pip, "timeout-minutes") == "6" and "--timeout 30 --retries 5" in pip and " -q " not in pip
