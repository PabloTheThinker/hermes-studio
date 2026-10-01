#!/usr/bin/env python3
"""Fetch every third-party source archive in packaging/third-party-sources.txt and verify it.

The release job runs this and attaches every archive to the release, so the corresponding
source of the bundled FFmpeg and PyAV builds ships next to the binaries (see NOTICE).

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
COLUMNS = ["component", "version", "used_by", "filename", "sha256", "kind", "source", "rev"]


def read_manifest(path: Path = MANIFEST) -> list[dict[str, str]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            rows.append(dict(zip(COLUMNS, line.split("\t"), strict=True)))
    return rows


def run(*args: str, cwd: str | Path | None = None, env: dict | None = None, clean: str | None = None) -> None:
    for attempt in range(4):
        if clean:
            shutil.rmtree(clean, ignore_errors=True)
        r = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True)
        if r.returncode == 0:
            return
        time.sleep(5 * (attempt + 1))
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
            run("curl", "-fsSL", "--retry", "5", "--retry-all-errors", "-o", str(dest), source)
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
    for r in rows:
        out += [
            f"{r['component']} {r['version']}  [{r['used_by'].replace(',', ', ')}]",
            f"  file:   {r['filename']}",
            f"  source: {how[r['kind']].format(**r)}",
            f"  sha256: {r['sha256']}",
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
            got = sha256(produce(row, args.out))
        except Exception as e:  # noqa: BLE001
            return row, None, str(e)
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
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
