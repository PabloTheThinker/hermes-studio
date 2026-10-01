#!/usr/bin/env python3
"""Fetch every third-party source archive in packaging/third-party-sources.txt, verify it, and
pack the archives into the source bundles the release attaches.

The `sources` CI job runs this and uploads the bundles; the release job attaches those
exact bundles, so the corresponding source of the bundled FFmpeg, PyAV and OpenCV builds
ships next to the binaries (see NOTICE).

Bundles: each archive goes into one bundle, chosen by the binaries that use it (BUNDLE_GROUPS):
sources-<group>.tar when only one group uses it, sources-ffmpeg.tar when both BtbN FFmpeg builds
(and nothing else) use it, sources-common.tar when other groups share it. A group
over BUNDLE_LIMIT is split into sources-<group>-1.tar, -2, ... (archives in filename order).
Bundles are plain tars with fixed metadata and order, so they rebuild byte for byte; their
sha256s are committed in packaging/SOURCES-SHA256SUMS.

Kinds:
  url           download SOURCE as is.
  git           `git archive --format=tar` of commit REV fetched from SOURCE (for forges
                without a stable commit tarball). Deterministic for a given commit.
  svn           `svn export` of SOURCE at revision REV, packed as a normalized tar.
  cargo-crates  every crates.io .crate file locked by the Cargo.lock of SOURCE at REV (the
                Rust crates compiled into the library), each checked against the lock's
                checksum, plus that Cargo.lock, packed as a normalized tar.

  mirror-sources.py --out DIR            fetch all, fail on any sha256 mismatch
  mirror-sources.py --out DIR --update   fetch all, write the sha256 column back
  mirror-sources.py --out DIR --only NAME[,NAME...]
  mirror-sources.py --notice             print the archive list that NOTICE carries
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "packaging" / "third-party-sources.txt"
SUMS = ROOT / "packaging" / "SOURCES-SHA256SUMS"
COLUMNS = ["component", "version", "used_by", "filename", "sha256", "size", "kind", "source", "rev"]
# Which bundle group each used_by tag belongs to.
BUNDLE_GROUPS = {
    "ffmpeg-linux64": "ffmpeg-linux64",
    "ffmpeg-win64": "ffmpeg-win64",
    "pyav-linux": "pyav",
    "pyav-win": "pyav",
    "opencv-linux": "opencv",
    "opencv-win": "opencv",
    "numpy-linux": "numpy",
    # Electron's own FFmpeg (one archive for both platforms) goes with the shared archives.
    "electron-linux": "common",
    "electron-win": "common",
}
# GitHub refuses release assets of 2 GiB or more; stay well under it.
BUNDLE_LIMIT = 2_000_000_000


def read_manifest(path: Path = MANIFEST) -> list[dict[str, str]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            rows.append(dict(zip(COLUMNS, line.split("\t"), strict=True)))
    return rows


def run(*args: str, cwd: str | Path | None = None, env: dict | None = None, clean: str | None = None) -> None:
    # Forges (gitlab.freedesktop.org in particular) answer 502/504 for minutes at a time:
    # retry for about 7 minutes before giving up.
    for attempt in range(8):
        if clean:
            shutil.rmtree(clean, ignore_errors=True)
        r = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True)
        if r.returncode == 0:
            return
        if attempt < 7:
            time.sleep(min(90, 10 * 2**attempt))
    raise RuntimeError(f"{' '.join(args)} failed:\n{r.stderr[-2000:]}")


def normalized_tar(src: Path, dest: Path, prefix: str) -> None:
    """A tar that depends only on the file tree: sorted, fixed mtime/owner, normalized modes."""
    def norm(ti: tarfile.TarInfo) -> tarfile.TarInfo:
        ti.mtime, ti.uid, ti.gid, ti.uname, ti.gname = 0, 0, 0, "", ""
        ti.mode = 0o755 if (ti.isdir() or ti.mode & 0o111) else 0o644
        return ti

    with tarfile.open(dest, "w", format=tarfile.PAX_FORMAT) as tar:
        for path in sorted(src.rglob("*"), key=lambda p: p.relative_to(src).as_posix()):
            rel = path.relative_to(src).as_posix()
            if rel.split("/")[0] in {".svn", ".git"}:
                continue
            tar.add(path, arcname=f"{prefix}/{rel}", recursive=False, filter=norm)


CRATES_IO = "registry+https://github.com/rust-lang/crates.io-index"


def fetch_crates(lock: Path, dest_dir: Path) -> None:
    pkgs = [p for p in tomllib.loads(lock.read_text())["package"] if p.get("source")]
    if any(p["source"] != CRATES_IO for p in pkgs):
        raise RuntimeError(f"{lock}: non-crates.io sources are not supported")

    def get(p):
        name = f"{p['name']}-{p['version']}.crate"
        url = f"https://static.crates.io/crates/{p['name']}/{name}"
        for attempt in range(4):
            try:
                data = urllib.request.urlopen(url, timeout=60).read()
                break
            except OSError:
                if attempt == 3:
                    raise
                time.sleep(5 * (attempt + 1))
        if hashlib.sha256(data).hexdigest() != p["checksum"]:
            raise RuntimeError(f"{name}: checksum does not match Cargo.lock")
        (dest_dir / name).write_bytes(data)

    with ThreadPoolExecutor(16) as pool:
        list(pool.map(get, pkgs))


def produce(row: dict[str, str], out: Path) -> Path:
    dest = out / row["filename"]
    stem = row["filename"].removesuffix(".tar")
    kind, source, rev = row["kind"], row["source"], row["rev"]
    with tempfile.TemporaryDirectory(prefix="mirror-") as tmp:
        if kind == "url":
            run("curl", "-fsSL", "--retry", "5", "--retry-all-errors", "--retry-delay", "10", "-o", str(dest), source)
        elif kind == "git":
            run("git", "init", "-q", tmp)
            run("git", "fetch", "-q", "--depth=1", "--no-tags", source, rev, cwd=tmp)
            run("git", "-c", "tar.umask=0022", "archive", "--format=tar", f"--prefix={stem}/",
                "-o", str(dest), "FETCH_HEAD", cwd=tmp)
        elif kind == "svn":
            # Same anonymous login the BtbN script uses (svn.xvid.org asks for one).
            run("svn", "export", "-q", "--non-interactive", "--username", "anonymous", "--password", "", "-r", rev, f"{source}@{rev}", f"{tmp}/src", clean=f"{tmp}/src")
            normalized_tar(Path(tmp, "src"), dest, stem)
        elif kind == "cargo-crates":
            run("git", "init", "-q", f"{tmp}/src")
            run("git", "fetch", "-q", "--depth=1", "--no-tags", source, rev, cwd=f"{tmp}/src")
            run("git", "checkout", "-q", "FETCH_HEAD", cwd=f"{tmp}/src")
            crates = Path(tmp, "crates")
            crates.mkdir()
            shutil.copy(Path(tmp, "src", "Cargo.lock"), crates / "Cargo.lock")
            fetch_crates(crates / "Cargo.lock", crates)
            normalized_tar(crates, dest, stem)
        else:
            raise ValueError(f"unknown kind {kind}")
    return dest


def bundle_plan(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    """Bundle file name -> its rows (in filename order), deterministic from the manifest."""
    groups: dict[str, list[dict[str, str]]] = {}
    for r in rows:
        g = {BUNDLE_GROUPS[u] for u in r["used_by"].split(",")}
        name = g.pop() if len(g) == 1 else "ffmpeg" if all(x.startswith("ffmpeg-") for x in g) else "common"
        groups.setdefault(name, []).append(r)
    plan: dict[str, list[dict[str, str]]] = {}
    for g in sorted(groups):
        parts: list[list[dict[str, str]]] = [[]]
        total = 0
        for r in sorted(groups[g], key=lambda r: r["filename"]):
            need = int(r["size"]) + 4096  # header (+ pax header) and padding
            if parts[-1] and total + need > BUNDLE_LIMIT:
                parts.append([])
                total = 0
            parts[-1].append(r)
            total += need
        for i, part in enumerate(parts, 1):
            plan[f"sources-{g}.tar" if len(parts) == 1 else f"sources-{g}-{i}.tar"] = part
    return plan


def bundle_of(rows: list[dict[str, str]]) -> dict[str, str]:
    return {r["filename"]: name for name, part in bundle_plan(rows).items() for r in part}


def write_bundle(name: str, rows: list[dict[str, str]], src: Path, dest: Path) -> None:
    """Plain tar of the archives under <bundle stem>/, fixed order and metadata."""
    stem = name.removesuffix(".tar")
    with tarfile.open(dest / name, "w", format=tarfile.PAX_FORMAT) as tar:
        for r in rows:
            path = src / r["filename"]
            ti = tarfile.TarInfo(f"{stem}/{r['filename']}")
            ti.size, ti.mode, ti.mtime, ti.uid, ti.gid, ti.uname, ti.gname = path.stat().st_size, 0o644, 0, 0, 0, "", ""
            with path.open("rb") as f:
                tar.addfile(ti, f)
    if (dest / name).stat().st_size >= 2**31:
        raise RuntimeError(f"{name} is 2 GiB or more")


NOTICE_BEGIN = "--- begin mirrored source archives (generated by scripts/mirror-sources.py --notice) ---"
NOTICE_END = "--- end mirrored source archives ---"


def notice_block(rows: list[dict[str, str]]) -> str:
    how = {
        "url": "{source}",
        "git": "git archive of commit {rev} from {source}",
        "svn": "svn export of {source} at revision {rev} (normalized tar)",
        "cargo-crates": "every crates.io crate in the Cargo.lock of {source} at commit {rev} (normalized tar)",
    }
    out = [NOTICE_BEGIN]
    where = bundle_of(rows)
    for r in rows:
        out += [
            f"{r['component']} {r['version']}  [{r['used_by'].replace(',', ', ')}]",
            f"  file:   {r['filename']}",
            f"  source: {how[r['kind']].format(**r)}",
            f"  sha256: {r['sha256']}",
            f"  bundle: {where[r['filename']]}",
        ]
    out.append(NOTICE_END)
    return "\n".join(out) + "\n"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path)
    ap.add_argument("--notice", action="store_true")
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--bundles", type=Path)
    ap.add_argument("--only")
    ap.add_argument("--jobs", type=int, default=6)
    args = ap.parse_args()
    if args.notice:
        sys.stdout.write(notice_block(read_manifest()))
        return 0
    if not args.out:
        ap.error("--out is required")
    args.out.mkdir(parents=True, exist_ok=True)
    rows = read_manifest()
    todo = [r for r in rows if not args.only or r["component"] in args.only.split(",")]

    def one(row):
        try:
            path = produce(row, args.out)
            got = sha256(path)
        except Exception as e:  # noqa: BLE001
            return row, None, str(e)
        if args.update:
            row["size"] = str(path.stat().st_size)
        elif str(path.stat().st_size) != row["size"]:
            return row, None, f"size {path.stat().st_size}, manifest says {row['size']}"
        return row, got, None

    bad = 0
    with ThreadPoolExecutor(args.jobs) as pool:
        for row, got, err in pool.map(one, todo):
            if err:
                bad += 1
                print(f"FAIL  {row['filename']}: {err}", file=sys.stderr)
            elif args.update:
                row["sha256"] = got
                print(f"sha   {got}  {row['filename']}")
            elif got != row["sha256"]:
                bad += 1
                print(f"MISMATCH {row['filename']}: want {row['sha256']} got {got}", file=sys.stderr)
            else:
                print(f"ok    {got}  {row['filename']}")
    if args.update:
        head = [line for line in MANIFEST.read_text().splitlines() if line.startswith("#")]
        MANIFEST.write_text("\n".join(head + ["\t".join(r[c] for c in COLUMNS) for r in rows]) + "\n")
    print(f"{len(todo) - bad}/{len(todo)} archives verified", file=sys.stderr)
    if bad or not args.bundles:
        return 1 if bad else 0
    if args.only:
        ap.error("--bundles needs every archive (no --only)")
    args.bundles.mkdir(parents=True, exist_ok=True)
    lines = []
    for name, part in bundle_plan(rows).items():
        write_bundle(name, part, args.out, args.bundles)
        lines.append(f"{sha256(args.bundles / name)}  {name}")
        print(f"bundle {lines[-1]}  ({(args.bundles / name).stat().st_size} bytes, {len(part)} archives)")
    sums = "\n".join(lines) + "\n"
    (args.bundles / "SOURCES-SHA256SUMS").write_text(sums)
    if args.update:
        SUMS.write_text(sums)
    elif sums != SUMS.read_text():
        print(f"bundles do not match {SUMS.relative_to(ROOT)}:\n{sums}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
