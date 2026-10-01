"""NOTICE and the license texts must match what the desktop app ships, and must ship.

The app bundles FFmpeg (GPL) and PyAV/OpenCV wheels that carry FFmpeg libraries.
These checks fail when a pin changes without NOTICE, or when packaging drops the files.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NOTICE = (ROOT / "NOTICE").read_text(encoding="utf-8")
DESKTOP_YML = (ROOT / ".github/workflows/desktop.yml").read_text(encoding="utf-8")
SHIPPED = ["NOTICE", "LICENSE", "licenses"]
LICENSE_TEXTS = {
    "FFmpeg-GPL.txt": "GNU GENERAL PUBLIC LICENSE\n                       Version 3, 29 June 2007",
    "LGPL-3.0.txt": "GNU LESSER GENERAL PUBLIC LICENSE\n                       Version 3, 29 June 2007",
    "LGPL-2.1.txt": "GNU LESSER GENERAL PUBLIC LICENSE\n                       Version 2.1, February 1999",
}


def workflow_env(name: str) -> str:
    m = re.search(rf"^\s+{name}:\s*(\S+)\s*$", DESKTOP_YML, re.M)
    assert m, f"{name} missing from desktop.yml"
    return m.group(1)


@pytest.mark.parametrize("platform", ["WIN", "LINUX"])
def test_notice_names_the_pinned_ffmpeg_download(platform):
    url = workflow_env(f"FFMPEG_{platform}_URL")
    sha = workflow_env(f"FFMPEG_{platform}_SHA256")
    assert url in NOTICE, "FFMPEG_*_URL changed: update the FFmpeg section of NOTICE"
    assert sha in NOTICE, "FFMPEG_*_SHA256 changed: update the FFmpeg section of NOTICE"
    tag = url.split("/")[7]
    build = re.search(r"ffmpeg-(n[\w.]+-\d+-g[0-9a-f]+)-", url).group(1)
    assert f"Release:         {tag}" in NOTICE
    assert f"releases/tag/{tag}" in NOTICE and f"tree/{tag}" in NOTICE
    assert f"Version string:  {build}" in NOTICE


def test_notice_links_the_exact_ffmpeg_commit():
    url = workflow_env("FFMPEG_LINUX_URL")
    short = re.search(r"-g([0-9a-f]+)-", url).group(1)
    commits = re.findall(r"FFmpeg/FFmpeg/(?:commit|archive)/([0-9a-f]{40})", NOTICE)
    assert commits, "NOTICE must link FFmpeg source by full commit, not just the tag"
    assert all(c.startswith(short) for c in commits), f"NOTICE commit is not g{short}"
    assert "GPL-3.0-or-later" in NOTICE and "separate programs" in NOTICE


def test_notice_names_the_pinned_wheels():
    pins = dict(
        line.split("==")
        for line in (ROOT / "packaging/engine-constraints.txt").read_text().splitlines()
        if "==" in line and not line.startswith("#")
    )
    assert set(pins) == {"av", "opencv-python-headless"}
    assert f"PyAV {pins['av']} (BSD-3-Clause)" in NOTICE
    assert f"PyAV-Org/PyAV/tree/v{pins['av']}" in NOTICE
    assert f"opencv-python-headless {pins['opencv-python-headless']}" in NOTICE
    assert "libx264 and libx265" in NOTICE  # the GPL parts of the PyAV wheel


@pytest.mark.parametrize("name,header", LICENSE_TEXTS.items())
def test_license_texts_are_complete(name, header):
    text = (ROOT / "licenses" / name).read_text(encoding="utf-8")
    assert header in text
    assert len(text) > 7000, f"{name} looks truncated"
    assert name in NOTICE or name in (ROOT / "licenses/README.md").read_text()


@pytest.mark.parametrize("platform", ["linux", "win", "mac"])
def test_app_resources_carry_notice_and_licenses(platform):
    cfg = json.loads((ROOT / "electron-builder.json").read_text())
    extra = {(e["from"], e["to"]) for e in cfg[platform]["extraResources"]}
    for f in SHIPPED:
        assert (f, f) in extra, f"electron-builder {platform}.extraResources must ship {f}"


@pytest.mark.parametrize(
    "script,needles",
    [
        (
            "scripts/build-engine-linux.sh",
            ['cp "$ROOT/NOTICE" "$ROOT/LICENSE" "$OUT/"', 'cp -r "$ROOT/licenses" "$OUT/licenses"'],
        ),
        (
            "scripts/build-engine-windows.ps1",
            ['Copy-Item "$Root\\NOTICE", "$Root\\LICENSE" "$Out\\"', 'Copy-Item -Recurse "$Root\\licenses" "$Out\\licenses"'],
        ),
    ],
)
def test_engine_build_copies_notices_and_pins_wheels(script, needles):
    text = (ROOT / script).read_text(encoding="utf-8")
    for n in needles + ["engine-constraints.txt", "NOTICE does not name"]:
        assert n in text, f"{script} lost: {n}"


def test_release_attaches_source():
    assert "git -C .. archive" in DESKTOP_YML
    assert '"${src[@]}" SHA256SUMS.txt' in DESKTOP_YML


def test_versions_agree():
    want = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    found = {
        "package.json": json.loads((ROOT / "package.json").read_text())["version"],
        "hermes_studio/__init__.py": re.search(
            r'__version__ = "([^"]+)"', (ROOT / "hermes_studio/__init__.py").read_text()
        ).group(1),
        "plugin.yaml": re.search(
            r"^version:\s*\"?([\w.]+)", (ROOT / "hermes_plugin/hermes-studio/plugin.yaml").read_text(), re.M
        ).group(1),
        "plugin __init__.py": re.search(
            r'__plugin_version__ = "([^"]+)"', (ROOT / "hermes_plugin/hermes-studio/__init__.py").read_text()
        ).group(1),
    }
    assert found == dict.fromkeys(found, want)
    assert (ROOT / f"docs/releases/v{want}.md").exists()


# --- Mirrored third-party sources -------------------------------------------------------------

def _mirror_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("mirror_sources", ROOT / "scripts/mirror-sources.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MIRROR = _mirror_module()
MANIFEST_PATH = ROOT / "packaging/third-party-sources.txt"
SOURCES = MIRROR.read_manifest(MANIFEST_PATH)
BY_COMPONENT = {r["component"]: r for r in SOURCES}
PINS = dict(
    re.findall(r"^# ([\w-]+): (\S+)$", MANIFEST_PATH.read_text(), re.M)
)

# ffmpeg -buildconf flag -> manifest components that provide it ("" = no third-party library).
FFMPEG_FLAG_SOURCES = {
    "amf": ["amf"], "avisynth": ["avisynth"], "chromaprint": ["chromaprint", "fftw3"],
    "cuda-llvm": ["ffnvcodec"], "ffnvcodec": ["ffnvcodec"], "fontconfig": ["fontconfig"],
    "frei0r": ["frei0r"], "gmp": ["gmp"], "iconv": ["libiconv", "gnulib"], "libaom": ["aom"],
    "libaribb24": ["libaribb24"], "libaribcaption": ["libaribcaption"],
    "libass": ["libass", "libunibreak"], "libbluray": ["libbluray", "libudfread"],
    "libdav1d": ["dav1d"], "libdavs2": ["davs2"], "libdrm": ["libdrm", "libpciaccess"],
    "libdvdnav": ["libdvdnav"], "libdvdread": ["libdvdread", "libdvdcss"],
    "libfreetype": ["freetype", "libpng", "brotli"], "libfribidi": ["fribidi"], "libgme": ["gme"],
    "libharfbuzz": ["harfbuzz"], "libjxl": ["libjxl", "libjxl--highway", "lcms2"],
    "libkvazaar": ["kvazaar"], "liblcevc-dec": ["lcevcdec"], "libmp3lame": ["libmp3lame"],
    "liboapv": ["openapv"], "libopencore-amrnb": ["opencore-amr"], "libopencore-amrwb": ["opencore-amr"],
    "libopenh264": ["openh264"], "libopenjpeg": ["openjpeg"], "libopenmpt": ["openmpt", "libogg", "libvorbis"],
    "libopus": ["libopus", "libopus--model"],
    "libplacebo": ["libplacebo", "libplacebo--glad", "libplacebo--fast_float", "shaderc", "spirv-cross"],
    "libpulse": ["pulseaudio"], "librav1e": ["rav1e", "rav1e--crates"],
    "librist": ["librist", "mbedtls", "mbedtls--tf-psa-crypto"],
    "librsvg": ["librsvg", "librsvg--crates", "cairo", "pango", "glib", "pixman", "libffi", "pcre2"],
    "librubberband": ["rubberband", "libsamplerate", "fftw3"], "libsnappy": ["snappy"],
    "libsoxr": ["soxr"], "libsrt": ["srt", "openssl"], "libssh": ["libssh", "openssl"],
    "libsvtav1": ["svtav1"], "libtheora": ["libtheora"], "libtwolame": ["twolame"],
    "libuavs3d": ["uavs3d"], "libvidstab": ["vidstab"], "libvmaf": ["vmaf"],
    "libvorbis": ["libvorbis", "libogg"], "libvpl": ["onevpl"], "libvpx": ["libvpx"],
    "libvvenc": ["vvenc"], "libwebp": ["libwebp"], "libx264": ["x264"], "libx265": ["x265"],
    "libxavs2": ["xavs2"], "libxcb": ["libxcb", "libxau"], "libxml2": ["libxml2"],
    "libxvid": ["xvid"], "libzimg": ["zimg", "zimg--graphengine"], "libzmq": ["libzmq"],
    "libzvbi": ["zvbi"], "lv2": ["lilv", "lv2", "serd", "sord", "sratom", "zix"], "lzma": ["xz"],
    "openal": ["openal"], "opencl": ["opencl", "OpenCL-ICD-Loader"], "openssl": ["openssl"],
    "pthreads": ["mingw"], "sdl2": ["sdl"], "vaapi": ["libva"], "vulkan": ["vulkan-loader"],
    "xlib": ["libx11", "libxext", "libxv"], "zlib": ["zlib"],
    # configure switches, not libraries
    "gpl": [], "version3": [], "schannel": [],  # schannel is the Windows system TLS API
}

# Library in a PyAV wheel's av.libs/ (hash suffix removed) -> manifest component.
WHEEL_LIB_SOURCES = [
    (r"^(lib)?(avcodec|avdevice|avfilter|avformat|avutil|swresample|swscale)\b", "pyav-ffmpeg"),
    (r"^libSvtAv1Enc", "pyav-libsvtav1"), (r"^libdav1d", "pyav-dav1d"), (r"^libmp3lame", "pyav-lame"),
    (r"^libopencore-amr", "pyav-opencore-amr"), (r"^libopus", "pyav-opus"),
    (r"^lib(sharpyuv|webp|webpmux)\b", "pyav-webp"), (r"^libvpl", "pyav-libvpl"), (r"^libvpx", "pyav-vpx"),
    (r"^libx264", "pyav-x264"), (r"^libx265", "pyav-x265"), (r"^libasound", "pyav-alsa-lib"),
    (r"^libgmp", "pyav-gmp"), (r"^libgnutls", "pyav-gnutls"), (r"^lib(nettle|hogweed)", "pyav-nettle"),
    (r"^libunistring", "pyav-unistring"), (r"^libxcb", "pyav-libxcb"), (r"^libXau", "pyav-libXau"),
    (r"^libdrm", "pyav-libdrm"), (r"^lib(gcc_s_seh|stdc\+\+)", "pyav-msys2-gcc"),
    (r"^libiconv", "pyav-msys2-libiconv"), (r"^zlib1", "pyav-zlib"),
]
WHEEL_LIB_GAPS = {"libwinpthread-1.dll"}  # named under "Not mirrored" in NOTICE


def _listed(name: str) -> list[str]:
    return [l.strip() for l in (ROOT / "packaging" / name).read_text().splitlines() if l.strip() and not l.startswith("#")]


def test_manifest_pins_follow_the_build_pins():
    url = workflow_env("FFMPEG_LINUX_URL")
    assert PINS["btbn-tag"] == url.split("/")[7], "regenerate packaging/third-party-sources.txt for the new BtbN tag"
    assert PINS["ffmpeg-commit"].startswith(re.search(r"-g([0-9a-f]+)-", url).group(1))
    assert f"FFmpeg/FFmpeg/archive/{PINS['ffmpeg-commit']}" in NOTICE
    constraints = (ROOT / "packaging/engine-constraints.txt").read_text()
    assert f"av=={PINS['av']}" in constraints, "regenerate packaging/third-party-sources.txt for the new PyAV"
    assert f"pyav-ffmpeg/tree/{PINS['pyav-ffmpeg-tag']}" in NOTICE
    assert BY_COMPONENT["ffmpeg"]["rev"] == PINS["ffmpeg-commit"]
    assert BY_COMPONENT["btbn-ffmpeg-builds"]["version"] == PINS["btbn-tag"]
    assert BY_COMPONENT["pyav"]["version"] == PINS["av"]
    assert BY_COMPONENT["pyav-ffmpeg-build"]["version"] == PINS["pyav-ffmpeg-tag"]


def test_manifest_rows_are_well_formed():
    names = [r["filename"] for r in SOURCES]
    assert len(names) == len(set(names)), "release asset names must be unique"
    for r in SOURCES:
        assert re.fullmatch(r"[0-9a-f]{64}", r["sha256"]), r["filename"]
        assert r["kind"] in {"url", "git", "svn", "cargo-crates"}, r["filename"]
        assert set(r["used_by"].split(",")) <= {"ffmpeg-linux64", "ffmpeg-win64", "pyav-linux", "pyav-win"}
        assert re.fullmatch(r"[\w.+~-]+", r["filename"]) and r["source"].startswith(("https://", "http://", "git://"))
        if r["kind"] in {"git", "cargo-crates"}:
            assert re.fullmatch(r"[0-9a-f]{40}", r["rev"]), r["filename"]


def test_notice_lists_every_mirrored_archive_exactly():
    assert MIRROR.notice_block(SOURCES) in NOTICE, "run: scripts/mirror-sources.py --notice, and paste into NOTICE"
    assert NOTICE.count(MIRROR.NOTICE_BEGIN) == 1


def test_release_job_attaches_every_mirrored_archive():
    release = DESKTOP_YML.split("\n  release:\n", 1)[1]
    assert "needs: [linux, windows, sources]" in release
    assert "scripts/mirror-sources.py --out third-party" in release
    assert "packaging/third-party-sources.txt | cut -f4" in release
    assert 'src=("hermes-studio-$want-source.tar.gz" "${third[@]}")' in release
    assert '"${src[@]}" > SHA256SUMS.txt' in release and '"${src[@]}" SHA256SUMS.txt' in release
    sources_job = DESKTOP_YML.split("\n  sources:\n", 1)[1].split("\n  linux:\n", 1)[0]
    assert "packaging/resolve-third-party-sources.py" in sources_job and "diff " in sources_job
    assert "scripts/mirror-sources.py --out" in sources_job


@pytest.mark.parametrize("target", ["linux64", "win64"])
def test_every_ffmpeg_library_is_mirrored(target):
    flags = [f.removeprefix("--enable-") for f in _listed(f"ffmpeg-buildconf-{target}.txt") if f.startswith("--enable-")]
    missing = [f for f in flags if f not in FFMPEG_FLAG_SOURCES]
    assert not missing, f"new ffmpeg library flags, add them to FFMPEG_FLAG_SOURCES and the manifest: {missing}"
    for flag in flags:
        for comp in FFMPEG_FLAG_SOURCES[flag]:
            assert comp in BY_COMPONENT, f"--enable-{flag}: {comp} not in third-party-sources.txt"
            assert f"ffmpeg-{target}" in BY_COMPONENT[comp]["used_by"], f"{comp} not marked for {target}"
    assert f"ffmpeg-{target}" in BY_COMPONENT["gcc"]["used_by"]  # static libstdc++/libgcc/libgomp


@pytest.mark.parametrize("plat", ["linux", "win"])
def test_every_pyav_wheel_library_is_mirrored(plat):
    for lib in _listed(f"pyav-wheel-libs-{plat}.txt"):
        if lib in WHEEL_LIB_GAPS:
            assert lib in NOTICE.split("Not mirrored:", 1)[1], f"{lib} must be named as a gap in NOTICE"
            continue
        comp = next((c for pat, c in WHEEL_LIB_SOURCES if re.search(pat, lib)), None)
        assert comp, f"{lib}: unknown library in the PyAV wheel, add its source"
        assert f"pyav-{plat}" in BY_COMPONENT[comp]["used_by"], f"{lib}: {comp} not marked for pyav-{plat}"
    for comp in ("pyav", "pyav-ffmpeg-build"):
        assert f"pyav-{plat}" in BY_COMPONENT[comp]["used_by"]
