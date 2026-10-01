#!/usr/bin/env python3
"""List every third-party source that goes into the bundled FFmpeg and PyAV builds.

Reads the exact pins from
  * BtbN FFmpeg-Builds at the tag in FFMPEG_*_URL (.github/workflows/desktop.yml),
    for the targets we ship (linux64, win64; variant gpl; addin 9.0), and
  * pyav-ffmpeg at the tag PyAV's wheels were built from (scripts/pkg.py),
and prints manifest rows (without sha256) for packaging/third-party-sources.txt.
`scripts/mirror-sources.py --update` then fills in the sha256 column.

Usage: resolve-third-party-sources.py BTBN_DIR BTBN_TAG FFMPEG_COMMIT PYAV_FFMPEG_DIR PYAV_FFMPEG_TAG AV_VERSION

Submodules that are only tests, fuzz corpora or demos are left out (TEST_ONLY below):
they are fetched by the build scripts but never compiled into the shipped binaries.
Needs bash and git (for submodule and tag lookups).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from functools import cache
from pathlib import Path

TARGETS = {"linux64": "ffmpeg-linux64", "win64": "ffmpeg-win64"}
# Submodules fetched by the build scripts but not compiled into the shipped binaries.
TEST_ONLY = {
    "openssl": "*",  # all of them are test, fuzz and interop suites
    "*": {"googletest", "munit", "testdata", "nuklear", "jinja", "markupsafe"},  # tests, demos, codegen
}
BOTH = {"ffmpeg-linux64", "ffmpeg-win64"}
PYAV = {"pyav-linux", "pyav-win"}

ENUM = r"""
set +e
cd "$BTBN"
for S in $(find scripts.d -name '*.sh' | sort); do
  (
    source util/vars.sh "$T" gpl 9.0 >/dev/null 2>&1
    source "variants/${T}-gpl.sh"; source addins/9.0.sh
    SELF="$S"; STAGENAME="$(basename "$S" .sh)"
    source util/dl_functions.sh; source "$S"
    ffbuild_enabled >/dev/null 2>&1 || exit 0
    printf '%s\t%s\n' "$S" "$(ffbuild_dockerdl 2>/dev/null | tr '\n' ';')"
  )
done
"""


def sh(*args: str, cwd: str | None = None) -> str:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout


@cache
def resolve_rev(repo: str, rev: str) -> str:
    if re.fullmatch(r"[0-9a-f]{40}", rev):
        return rev
    out = sh("git", "ls-remote", repo, f"refs/tags/{rev}", f"refs/tags/{rev}^{{}}")
    refs = dict(line.split("\t")[::-1] for line in out.splitlines())
    return refs.get(f"refs/tags/{rev}^{{}}") or refs[f"refs/tags/{rev}"]


@cache
def fetch(repo: str, rev: str) -> str:
    d = tempfile.mkdtemp(prefix="src-")
    sh("git", "init", "-q", d)
    sh("git", "fetch", "-q", "--depth=1", repo, rev, cwd=d)
    sh("git", "checkout", "-q", "FETCH_HEAD", cwd=d)
    return d


def submodules(repo: str, rev: str, only: list[str] | None = None) -> list[tuple[str, str, str]]:
    """(path, url, commit) for each submodule at rev, recursively."""
    d = fetch(repo, rev)
    out = []
    gm = Path(d, ".gitmodules")
    if gm.exists():
        cfg = sh("git", "config", "-f", ".gitmodules", "--get-regexp", r"submodule\..*\.(path|url)", cwd=d)
        mods: dict[str, dict[str, str]] = {}
        for line in cfg.splitlines():
            key, val = line.split(" ", 1)
            name, attr = key[len("submodule."):].rsplit(".", 1)
            mods.setdefault(name, {})[attr] = val
        for m in mods.values():
            if only and m["path"] not in only:
                continue
            url = m["url"]
            if url.startswith(("../", "./")):
                base, rel = repo, url
                while rel.startswith(("../", "./")):
                    if rel.startswith("../"):
                        base = base.rsplit("/", 1)[0]
                    rel = rel.split("/", 1)[1]
                url = f"{base}/{rel}"
            tree = sh("git", "ls-tree", "HEAD", m["path"], cwd=d).split()
            if not tree or tree[1] != "commit":
                continue
            out.append((m["path"], url, tree[2]))
            out += [(f"{m['path']}/{p}", u, c) for p, u, c in submodules(url, tree[2])]
    return out


def shaderc_deps(rev: str) -> list[tuple[str, str, str]]:
    d = fetch("https://github.com/google/shaderc.git", rev)
    deps = Path(d, "DEPS").read_text()
    vars_ = dict(re.findall(r"'(\w+)':\s*'([^']+)'", deps.split("deps = {")[0]))
    out = []
    for path, url in re.findall(r"'(third_party/[\w-]+)':\s*Var\('google_git'\)\s*\+\s*'([^']+)'", deps):
        url = vars_["google_git"] + url.replace("@' + Var('", "@{").replace("')", "}")
        repo, _, var = url.partition("@")
        rev_ = vars_.get(var.strip("{}"), var)
        name = Path(path).name
        if name in {"googletest", "effcee", "re2", "abseil_cpp", "abseil-cpp"}:
            continue  # tests only (SHADERC_SKIP_TESTS=ON)
        out.append((path, repo, rev_))
    return out


def btbn(btbn_dir: str) -> dict[tuple[str, str], dict]:
    found: dict[tuple[str, str], dict] = {}

    def add(name, repo, rev, target, via=""):
        repo = repo.removesuffix("/")
        rev = resolve_rev(repo, rev)
        e = found.setdefault((repo, rev), {"name": name, "repo": repo, "rev": rev, "used": set(), "via": via})
        e["used"].add(TARGETS[target])

    for target in TARGETS:
        out = subprocess.run(["bash", "-c", ENUM], env={**os.environ, "BTBN": btbn_dir, "T": target},
                             check=True, capture_output=True, text=True).stdout
        for line in out.splitlines():
            script, dl = line.split("\t")
            stage = re.sub(r"^\d+-", "", Path(script).stem)
            pairs = re.findall(r'git-mini-clone "([^"]+)" "([^"]+)"', dl)
            pairs += re.findall(r"git clone[^'\"]*['\"]([^'\"]+)['\"][^;]*?git (?:-C \w+ )?checkout \"([0-9a-f]{40})\"", dl)
            svn = re.findall(r"svn [^;]*?checkout [^;]*?'(\w+://[^'@]+)@(\d+)'", dl)
            for i, (repo, rev) in enumerate(pairs):
                name = stage if i == 0 else Path(repo).name.removesuffix(".git")
                add(name, repo, rev, target)
                if "submodule update" in dl and i == 0:
                    only = re.search(r"submodule update[^;]*?((?:\s+[\w./-]+/[\w./-]+)+);", dl)
                    skip = TEST_ONLY.get(stage, TEST_ONLY["*"])
                    for path, url, c in submodules(repo, resolve_rev(repo, rev), only.group(1).split() if only else None):
                        if skip == "*" or Path(path).name in skip:
                            continue
                        add(f"{stage}--{Path(path).name}", url, c, target, via=f"{stage} submodule {path}")
                if "git-sync-deps" in dl:
                    for path, url, c in shaderc_deps(rev):
                        add(f"{stage}--{Path(path).name}", url, c, target, via=f"{stage} DEPS {path}")
            for url, rev in svn:
                key = (url, rev)
                e = found.setdefault(key, {"name": stage, "repo": url, "rev": rev, "used": set(), "svn": True, "via": ""})
                e["used"].add(TARGETS[target])
            if "proxy-libintl" in dl:
                d = fetch(pairs[0][0], resolve_rev(*pairs[0]))
                wrap = Path(d, "subprojects/proxy-libintl.wrap").read_text()
                url = re.search(r"^source_url\s*=\s*(\S+)", wrap, re.M).group(1)
                h = re.search(r"^source_hash\s*=\s*(\S+)", wrap, re.M).group(1)
                ver = re.search(r"^directory\s*=\s*\S+-([\d.]+)", wrap, re.M).group(1)
                e = found.setdefault((url, "-"), {"name": "glib--proxy-libintl", "url": url, "sha": h, "version": ver,
                                                  "used": set(), "via": "glib meson subproject proxy-libintl"})
                e["used"].add(TARGETS[target])
            if "cargo vendor" in dl or stage == "rav1e":
                key = ("cargo-crates:" + pairs[0][0], pairs[0][1])
                e = found.setdefault(key, {"name": f"{stage}--crates", "repo": pairs[0][0], "rev": resolve_rev(*pairs[0]),
                                           "used": set(), "cargo": True, "via": f"{stage} Cargo.lock crates"})
                e["used"].add(TARGETS[target])
            if stage == "libopus":
                d = fetch(pairs[0][0], pairs[0][1])
                h = re.search(r'download_model\.sh "([0-9a-f]{64})"', Path(d, "autogen.sh").read_text()).group(1)
                key = (f"https://media.xiph.org/opus/models/opus_data-{h}.tar.gz", "-")
                e = found.setdefault(key, {"name": "libopus--model", "url": key[0], "sha": h, "version": h[:12],
                                           "used": set(), "via": "opus autogen.sh model"})
                e["used"].add(TARGETS[target])
    return found


def row(component, version, used, filename, kind, source, rev, sha="-"):
    return f"{component}\t{version}\t{','.join(sorted(used))}\t{filename}\t{sha}\t{kind}\t{source}\t{rev}"


def extras(btbn_tag, ffmpeg_commit, pyav_tag, av_version):
    """Sources outside the per-library scripts: FFmpeg itself, the build recipes, the
    toolchain runtime linked into the binaries, and what auditwheel/MSYS2 add to the wheels."""
    import json
    import urllib.request
    btbn_rev = resolve_rev("https://github.com/BtbN/FFmpeg-Builds.git", btbn_tag)
    pyav_rev = resolve_rev("https://github.com/PyAV-Org/pyav-ffmpeg.git", pyav_tag)
    pypi = json.load(urllib.request.urlopen(f"https://pypi.org/pypi/av/{av_version}/json"))
    sdist = next(f for f in pypi["urls"] if f["packagetype"] == "sdist")
    alma = "https://vault.almalinux.org/8.10/AppStream/Source/Packages"
    msys = "https://repo.msys2.org/mingw/sources"
    return [
        ("ffmpeg", ffmpeg_commit, BOTH, f"ffmpeg-{ffmpeg_commit}.tar.gz",
         f"https://github.com/FFmpeg/FFmpeg/archive/{ffmpeg_commit}.tar.gz", ffmpeg_commit, "-"),
        ("btbn-ffmpeg-builds", btbn_tag, BOTH, f"btbn-ffmpeg-builds-{btbn_tag}.tar.gz",
         f"https://github.com/BtbN/FFmpeg-Builds/archive/{btbn_rev}.tar.gz", btbn_rev, "-"),
        ("gcc", "16.2.0", BOTH, "gcc-16.2.0.tar.xz",
         "https://ftp.gnu.org/gnu/gcc/gcc-16.2.0/gcc-16.2.0.tar.xz", "-", "-"),
        ("pyav", av_version, PYAV, sdist["filename"], sdist["url"], "-", sdist["digests"]["sha256"]),
        ("pyav-ffmpeg-build", pyav_tag, PYAV, f"pyav-ffmpeg-{pyav_tag}.tar.gz",
         f"https://github.com/PyAV-Org/pyav-ffmpeg/archive/{pyav_rev}.tar.gz", pyav_rev, "-"),
        ("pyav-libxcb", "1.13.1-1.el8", {"pyav-linux"}, "libxcb-1.13.1-1.el8.src.rpm",
         f"{alma}/libxcb-1.13.1-1.el8.src.rpm", "-", "-"),
        ("pyav-libXau", "1.0.9-3.el8", {"pyav-linux"}, "libXau-1.0.9-3.el8.src.rpm",
         f"{alma}/libXau-1.0.9-3.el8.src.rpm", "-", "-"),
        ("pyav-libdrm", "2.4.115-2.el8", {"pyav-linux"}, "libdrm-2.4.115-2.el8.src.rpm",
         f"{alma}/libdrm-2.4.115-2.el8.src.rpm", "-", "-"),
        ("pyav-msys2-gcc", "16.1.0-5", {"pyav-win"}, "mingw-w64-gcc-16.1.0-5.src.tar.zst",
         f"{msys}/mingw-w64-gcc-16.1.0-5.src.tar.zst", "-", "-"),
        ("pyav-msys2-libiconv", "1.19-1", {"pyav-win"}, "mingw-w64-libiconv-1.19-1.src.tar.zst",
         f"{msys}/mingw-w64-libiconv-1.19-1.src.tar.zst", "-", "-"),
        ("pyav-zlib", "1.3.2", {"pyav-win"}, "zlib-1.3.2.tar.gz",
         "https://zlib.net/fossils/zlib-1.3.2.tar.gz", "-", "-"),
    ]


def main() -> None:
    btbn_dir, btbn_tag, ffmpeg_commit, pyav_dir, pyav_tag, av_version = sys.argv[1:7]
    rows = [row(c, v, u, f, "url", s, r, sha) for c, v, u, f, s, r, sha in
            extras(btbn_tag, ffmpeg_commit, pyav_tag, av_version)]
    for e in sorted(btbn(btbn_dir).values(), key=lambda e: e["name"]):
        if "url" in e:
            rows.append(row(e["name"], e["version"], e["used"], f"{e['name']}-{Path(e['url']).name}", "url", e["url"], "-", e["sha"]))
        elif e.get("svn"):
            rows.append(row(e["name"], f"r{e['rev']}", e["used"], f"{e['name']}-svn-r{e['rev']}.tar", "svn", e["repo"], e["rev"]))
        elif e.get("cargo"):
            rows.append(row(e["name"], e["rev"], e["used"], f"{e['name']}-{e['rev']}.tar", "cargo-crates", e["repo"], e["rev"]))
        else:
            gh = re.fullmatch(r"https://github\.com/([^/]+)/([^/]+?)(\.git)?", e["repo"])
            if gh:
                url = f"https://github.com/{gh.group(1)}/{gh.group(2)}/archive/{e['rev']}.tar.gz"
                rows.append(row(e["name"], e["rev"], e["used"], f"{e['name']}-{e['rev']}.tar.gz", "url", url, e["rev"]))
            else:
                rows.append(row(e["name"], e["rev"], e["used"], f"{e['name']}-{e['rev']}.tar", "git", e["repo"], e["rev"]))
    # pyav-ffmpeg packages built for the x86_64 Linux and Windows wheels.
    pkg = Path(pyav_dir, "scripts/pkg.py").read_text()
    for block in pkg.split("Package(")[1:]:
        name, url, sha = re.search(r'name="([^"]+)",\s*source_url="([^"]+)",\s*sha256="([0-9a-f]{64})"', block).groups()
        if name == "nasm":
            continue  # assembler, build tool only
        used = {"pyav-linux"} if name in {"alsa-lib", "gmp", "unistring", "nettle", "gnutls"} else {"pyav-linux", "pyav-win"}
        fname = re.search(r'source_filename="([^"]+)"', block)
        fname = fname.group(1) if fname else Path(url).name
        if not fname.lower().startswith(name.split("-")[0][:3].lower()):
            fname = f"{name}-{fname}"
        version = re.search(r"(\d+(?:\.\d+)+|[0-9a-f]{40})", Path(url).name.replace("x265_", "x265-")).group(1)
        rows.append(row(f"pyav-{name}", version, used, f"pyav-{fname}", "url", url, "-", sha))
    print("\n".join(rows))


if __name__ == "__main__":
    main()
