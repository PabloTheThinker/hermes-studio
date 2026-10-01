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
# licenses/<file> -> (a line of the text, minimum length to catch truncation)
LICENSE_TEXTS = {
    "FFmpeg-GPL.txt": ("GNU GENERAL PUBLIC LICENSE\n                       Version 3, 29 June 2007", 30000),
    "LGPL-3.0.txt": ("GNU LESSER GENERAL PUBLIC LICENSE\n                       Version 3, 29 June 2007", 7000),
    "LGPL-2.1.txt": ("GNU LESSER GENERAL PUBLIC LICENSE\n                       Version 2.1, February 1999", 25000),
    "GCC-RLE-3.1.txt": ("GCC RUNTIME LIBRARY EXCEPTION\n\nVersion 3.1, 31 March 2009", 3000),
    "Rust-std-MIT.txt": ("Copyright (c) The Rust Project Contributors", 1000),
    "Rust-std-Apache-2.0.txt": ("Apache License\n                        Version 2.0, January 2004", 9000),
    "winpthreads.txt": ("Copyright (c) 2011 mingw-w64 project", 2500),
    "zlib.txt": ("Permission is granted to anyone to use this software for any purpose", 900),
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
    section = NOTICE.split("\nFFmpeg (bundled program", 1)[1].split("\nPyAV and the FFmpeg libraries", 1)[0]
    commits = re.findall(r"FFmpeg/FFmpeg/(?:commit|archive)/([0-9a-f]{40})", section)
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


@pytest.mark.parametrize("name,header,size", [(n, h, z) for n, (h, z) in LICENSE_TEXTS.items()])
def test_license_texts_are_complete(name, header, size):
    text = (ROOT / "licenses" / name).read_text(encoding="utf-8")
    assert header in text
    assert len(text) > size, f"{name} looks truncated"
    assert f"`{name}`" in (ROOT / "licenses/README.md").read_text()


def test_every_license_text_is_known_and_byte_checked_in_the_app():
    files = {p.name for p in (ROOT / "licenses").iterdir()} - {"README.md"}
    assert files == set(LICENSE_TEXTS), "add new license texts to LICENSE_TEXTS and licenses/README.md"
    for name in ("Rust-std-MIT.txt", "Rust-std-Apache-2.0.txt", "winpthreads.txt", "zlib.txt", "GCC-RLE-3.1.txt"):
        assert f"licenses/{name}" in NOTICE, f"NOTICE must point at licenses/{name}"
    # The AppImage and installer checks compare every file in licenses/ with the shipped copies
    # in resources/ and resources/engine/.
    assert "for f in NOTICE LICENSE licenses/*; do" in DESKTOP_YML
    assert 'Get-ChildItem licenses -File | ForEach-Object { "licenses\\$($_.Name)" }' in DESKTOP_YML
    assert DESKTOP_YML.count("for dir in resources resources/engine; do") == 1
    assert DESKTOP_YML.count('foreach ($dir in "resources", "resources\\engine")') == 1


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
    assert f"opencv-python-headless=={PINS['opencv-python-headless']}" in constraints
    assert BY_COMPONENT["opencv-python-headless"]["version"] == PINS["opencv-python-headless"]
    assert BY_COMPONENT["opencv-python-build"]["version"] == PINS["opencv-python-headless"].rsplit(".", 1)[1]
    assert f"opencv-python/tree/{BY_COMPONENT['opencv-python-build']['version']}" in NOTICE
    assert f"FFmpeg {BY_COMPONENT['opencv-ffmpeg']['version']} shared libraries" in NOTICE
    assert f"opencv_3rdparty commit\n  {BY_COMPONENT['opencv-3rdparty-ffmpeg']['version']}" in NOTICE
    assert f"FFmpeg {BY_COMPONENT['opencv-win-ffmpeg']['version']} (LGPL-2.1-or-later)" in NOTICE


def test_manifest_rows_are_well_formed():
    names = [r["filename"] for r in SOURCES]
    assert len(names) == len(set(names)), "release asset names must be unique"
    for r in SOURCES:
        assert re.fullmatch(r"[0-9a-f]{64}", r["sha256"]), r["filename"]
        assert re.fullmatch(r"[1-9][0-9]*", r["size"]), r["filename"]
        assert r["kind"] in {"url", "git", "svn", "cargo-crates"}, r["filename"]
        assert set(r["used_by"].split(",")) <= set(MIRROR.BUNDLE_GROUPS), r["filename"]
        assert re.fullmatch(r"[\w.+~-]+", r["filename"]) and r["source"].startswith(("https://", "http://", "git://"))
        if r["kind"] in {"git", "cargo-crates"}:
            assert re.fullmatch(r"[0-9a-f]{40}", r["rev"]), r["filename"]


def test_notice_lists_every_mirrored_archive_exactly():
    assert MIRROR.notice_block(SOURCES) in NOTICE, "run: scripts/mirror-sources.py --notice, and paste into NOTICE"
    assert NOTICE.count(MIRROR.NOTICE_BEGIN) == 1


BUNDLES = MIRROR.bundle_plan(SOURCES)
COMMITTED_SUMS = [l.split("  ", 1) for l in (ROOT / "packaging/SOURCES-SHA256SUMS").read_text().splitlines()]


def test_every_archive_is_in_exactly_one_bundle_under_2_gib():
    inner = [r["filename"] for part in BUNDLES.values() for r in part]
    assert sorted(inner) == sorted(r["filename"] for r in SOURCES)
    for name, part in BUNDLES.items():
        assert re.fullmatch(r"sources-[a-z0-9-]+\.tar", name)
        # tar: a 512-byte header (plus a pax header for long names) per file, data padded to 512,
        # end-of-archive blocks and record padding
        size = sum(1024 + -(-int(r["size"]) // 512) * 512 for r in part) + 10240
        assert size <= MIRROR.BUNDLE_LIMIT < 2**31, f"{name} would be {size} bytes: lower BUNDLE_LIMIT or split"
        assert part == sorted(part, key=lambda r: r["filename"])


def test_committed_bundle_sums_match_the_plan():
    assert [n for _, n in COMMITTED_SUMS] == list(BUNDLES), "run: scripts/mirror-sources.py --out DIR --bundles BDIR --update"
    assert all(re.fullmatch(r"[0-9a-f]{64}", h) for h, _ in COMMITTED_SUMS)


def test_notice_names_each_archive_bundle():
    where = MIRROR.bundle_of(SOURCES)
    for r in SOURCES:
        entry = (rf"\n  file:   {re.escape(r['filename'])}\n  source: [^\n]+\n"
                 rf"  sha256: {r['sha256']}\n  bundle: {re.escape(where[r['filename']])}\n")
        assert re.search(entry, NOTICE), f"NOTICE entry for {r['filename']} lacks its sha256 or bundle"
    for name in BUNDLES:
        assert f"bundle: {name}" in NOTICE
    assert "SOURCES-SHA256SUMS" in NOTICE and "under 2 GiB" in NOTICE


def test_sources_job_uploads_every_bundle():
    sources_job = DESKTOP_YML.split("\n  sources:\n", 1)[1].split("\n  linux:\n", 1)[0]
    assert "packaging/resolve-third-party-sources.py" in sources_job and "diff " in sources_job
    assert '"$(pin opencv-python-headless)"' in sources_job and "cut -f1-4,7-" in sources_job
    assert 'scripts/mirror-sources.py --out "$RUNNER_TEMP/sources" --bundles "$RUNNER_TEMP/bundles"' in sources_job
    uploads = re.findall(r"name: (\S+)\n\s+path: \$\{\{ runner\.temp \}\}/bundles/(\S+)\n((?:\s+[\w-]+: .*\n)*)", sources_job)
    assert {(n, p) for n, p, _ in uploads} == {(b.removesuffix(".tar"), b) for b in BUNDLES} | {("SOURCES-SHA256SUMS", "SOURCES-SHA256SUMS")}
    for _, _, opts in uploads:
        assert "retention-days: 3" in opts and "if-no-files-found: error" in opts


def _job(name: str) -> str:
    body = DESKTOP_YML.split(f"\n  {name}:\n", 1)[1]
    return re.split(r"\n(?:\n)?  (?=[#\w])", body, maxsplit=1)[0]


def test_release_job_rebuilds_and_verifies_the_bundles():
    release = _job("release")
    assert "if: startsWith(github.ref, 'refs/tags/v') || github.event_name == 'workflow_dispatch'" in release
    assert "needs: [linux, windows, sources]" in release
    # Rebuilt from the manifest on whatever commit the tag lands on, never taken from other runs.
    assert 'python3 scripts/mirror-sources.py --out "$RUNNER_TEMP/sources" --bundles rel' in release
    assert "cmp rel/SOURCES-SHA256SUMS packaging/SOURCES-SHA256SUMS" in release
    assert "sha256sum -c SOURCES-SHA256SUMS" in release
    assert "pattern: sources-*" not in release and "name: SOURCES-SHA256SUMS" not in release
    assert 'src=("hermes-studio-$want-source.tar.gz" "${bundles[@]}" SOURCES-SHA256SUMS)' in release
    assert '"${src[@]}" > SHA256SUMS.txt' in release
    assert 'assets=("Hermes-Studio-$want.AppImage" "Hermes-Studio-Setup-$want.exe" "${src[@]}" SHA256SUMS.txt)' in release
    assert "release-assets.txt" in release and 'ls -l "${assets[@]}"' in release
    assert "name: release-assets" in release and "retention-days: 3" in release


def test_dry_run_can_never_publish():
    dispatch = DESKTOP_YML.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
    assert re.search(r"workflow_dispatch:.*\n\s+inputs:\n\s+dry_run:\n(\s+\w+: .*\n)*?\s+type: boolean\n\s+default: true", dispatch)
    release, publish = _job("release"), _job("publish")
    # The assembling job holds a read-only token and refuses anything but a tag push or a dry run.
    assert "permissions:\n      contents: read" in release and "contents: write" not in release
    assert '[ "$EVENT" = workflow_dispatch ] && [ "$DRY_RUN" = true ]' in release and "exit 1" in release
    assert "gh release" not in release and "GH_TOKEN" not in release
    # Only publish creates the release, only on a tag push, with exactly the assembled assets.
    assert "if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')" in publish
    assert '[ "$EVENT" = push ] && [[ "$REF" == refs/tags/v* ]]' in publish
    assert "needs: release" in publish and "name: release-assets" in publish
    assert "sha256sum -c SHA256SUMS.txt" in publish and "cmp rel/SOURCES-SHA256SUMS packaging/SOURCES-SHA256SUMS" in publish
    assert "mapfile -t assets < rel/release-assets.txt" in publish and '"${assets[@]}"' in publish
    assert DESKTOP_YML.count("gh release create") == 1 and "gh release create" in publish
    assert DESKTOP_YML.count("contents: write") == 1


def test_publish_is_draft_first_and_never_deletes():
    publish = _job("publish")
    script = publish.split("run: |", 1)[1]
    assert "set -euo pipefail" in script
    steps = [
        # refuse to overwrite an existing release for the tag
        "select(.tag_name == env.TAG)",
        # 1. draft with every asset, notes from docs/releases/<tag>.md
        'gh release create "$TAG" --draft --verify-tag',
        # 2. the draft's asset list, then a fresh download verified against both sums files
        "gh release view \"$TAG\" --json assets",
        '[ "$uploaded" = "$want_list" ]',
        'gh release download "$TAG" --dir "$got"',
        "sha256sum -c SHA256SUMS.txt && sha256sum -c SOURCES-SHA256SUMS",
        "cmp \"$got/SOURCES-SHA256SUMS\" packaging/SOURCES-SHA256SUMS",
        # 3. only then publish
        'gh release edit "$TAG" --draft=false --latest',
    ]
    at = [script.find(x) for x in steps]
    assert all(i >= 0 for i in at), [x for x, i in zip(steps, at) if i < 0]
    assert at == sorted(at), "publish must create a draft, download and verify it, then publish it"
    assert '--notes-file "../$notes"' in script and 'notes="docs/releases/$TAG.md"' in script
    assert '[ "${#assets[@]}" -eq 11 ]' in script and 'rm -rf "$got" && mkdir "$got"' in script
    assert script.count("gh release edit") == 1 and "--latest" not in script.split("gh release edit", 1)[0]
    # Nothing deletes a release, and only the tag's own release is addressed.
    assert not re.search(r"gh release delete|delete-asset|-X\s*DELETE|--method\s+DELETE|--clobber", DESKTOP_YML, re.I)
    assert all('"$TAG"' in line for line in script.splitlines() if re.search(r"gh release (create|view|download|edit)", line))
    assert "trap" not in script


def test_release_notes_log_line_is_honest():
    release = _job("release")
    assert "(empty: generated by GitHub)" not in release
    assert 'if [ -s release-notes.txt ]; then echo "Release notes: $notes"; else' in release


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


# Native library in another wheel (packaging/wheel-libs-*.txt) -> manifest component, or None when it
# is permissively licensed and not mirrored, or "gap" when NOTICE names it under "Not mirrored".
OTHER_WHEEL_LIBS = [
    (r"^opencv_python_headless\.libs/lib(avcodec|avformat|avutil|swresample|swscale)-", "opencv-ffmpeg"),
    (r"^(opencv_python_headless|numpy)\.libs/lib(gfortran|quadmath)-", "opencv-gcc-runtime"),
    (r"^opencv_python_headless\.libs/libdrm-", "pyav-libdrm"),
    (r"^opencv_python_headless\.libs/lib(aom|avif|png16|vpx|crypto|ssl|openblasp-r0)-", None),
    (r"^cv2/opencv_videoio_ffmpeg\d+_64\.dll$", "opencv-win-ffmpeg"),
    (r"^numpy\.libs/libscipy_openblas64_-[0-9a-f]+\.so$", None),
    (r"^numpy\.libs/libscipy_openblas64_-[0-9a-f]+\.dll$", "gap"),  # static GNU Fortran runtime
    (r"^numpy\.libs/msvcp140-", None),
    (r"^ctranslate2\.libs/libgomp-", "gap"),
    (r"^ctranslate2(\.libs/libctranslate2-|/(ctranslate2|cudnn64_9|libiomp5md)\.dll$)", None),
    (r"^pillow\.libs/lib(Xau|avif|brotli(common|dec)|freetype|harfbuzz|jpeg|lcms2|lzma|openjp2|png16|sharpyuv"
     r"|tiff|webp|webpdemux|webpmux|xcb|zstd)-", None),
]


@pytest.mark.parametrize("plat", ["linux", "win"])
def test_every_other_wheel_library_is_mirrored_or_named(plat):
    gaps = NOTICE.split("Not mirrored:", 1)[1].split(MIRROR.NOTICE_BEGIN, 1)[0]
    for lib in _listed(f"wheel-libs-{plat}.txt"):
        hit = [c for pat, c in OTHER_WHEEL_LIBS if re.search(pat, lib)]
        assert len(hit) == 1, f"{lib}: classify it in OTHER_WHEEL_LIBS (source, permissive or gap)"
        comp = hit[0]
        if comp == "gap":
            assert lib.split("/")[0] in gaps, f"{lib} must be named under 'Not mirrored' in NOTICE"
        elif comp:
            assert any(u.endswith(f"-{plat}") for u in BY_COMPONENT[comp]["used_by"].split(",")), f"{lib}: {comp}"
    for comp in ("opencv-python-headless", "opencv-python-build"):
        assert f"opencv-{plat}" in BY_COMPONENT[comp]["used_by"]
