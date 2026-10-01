"""packaging/resolve-third-party-sources.py: parsing of BtbN download commands."""

from __future__ import annotations

import importlib.util
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("resolve_sources", ROOT / "packaging/resolve-third-party-sources.py")
RESOLVE = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(RESOLVE)


@pytest.mark.parametrize(
    "dl,want",
    [
        # the forms BtbN's scripts use
        ("git-mini-clone \"u\" \"r\" x;git submodule update --init --recursive --depth=1 lib/sfparse;", ["lib/sfparse"]),
        ("git submodule update --init --recursive --depth 1 --recommend-shallow third_party/highway;",
         ["third_party/highway"]),
        ("git submodule update --init --recursive --depth=1 a/b c.d/e-f_g;", ["a/b", "c.d/e-f_g"]),
        ("git submodule update --init --recursive --depth=1;", None),
        ("git submodule update --init --recursive --depth=1 --filter=blob:none;", None),
        # only the path words right before the ";" count
        ("git submodule update a/b --init;", None),
        ("git submodule update --init a/b x c/d;", ["c/d"]),
        ("git submodule update --init a/b ;", None),
        ("git submodule update --init a/b", None),  # no ";"
        ("git submodule updatea/b c/d;", ["c/d"]),  # glued to the command, not an argument
        ("git submodule update\ta/b\nc/d;", ["a/b", "c/d"]),
        ("echo; git submodule update --init; git submodule update --init x/y;", ["x/y"]),
        ("git clone u; cd x;", None),
    ],
)
def test_submodule_paths(dl, want):
    assert RESOLVE.submodule_paths(dl) == want


@pytest.mark.parametrize(
    "dl",
    [
        "submodule update" + " a/b" * 50_000 + " x",  # many path words, then no ";"
        "submodule update" + " a/" * 50_000 + "!;",  # near-misses
        "submodule update " + "a/" * 100_000 + ";",  # one huge word
        "submodule update" * 20_000,
    ],
)
def test_submodule_paths_is_linear_on_adversarial_input(dl):
    start = time.perf_counter()
    RESOLVE.submodule_paths(dl)
    assert time.perf_counter() - start < 1.0
