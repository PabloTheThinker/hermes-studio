#!/usr/bin/env python3
"""Warning-level checks for repeat review findings (teknium1 / review 2).

Default mode always exits 0 so CI stays green. Use --strict to fail.
Each message states the root cause and the fix.

  python scripts/review_checks.py
  python scripts/review_checks.py --strict
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = (ROOT / "hermes_studio", ROOT / "hermes_plugin")

# The Studio library default is ~/.hermes/clips (and folders under it). This is the
# documented out-root until every caller goes through one helper; it is not a stray
# hardcoding of the Hermes home itself. Mentions of that default in user-facing
# errors and tool descriptions are also allowed.
CAUSES = {
    "environ-spread": (
        "Root cause: spreading the parent environment into an engine or helper subprocess "
        "forwards secrets and agent settings the child does not need (review 2, item 3). "
        "Fix: pass a minimal env (PATH, HOME, LANG, TMPDIR, PYTHONPATH when set, plus the "
        "HERMES_STUDIO_* variables the child reads). Do not use {**os.environ}, dict(os.environ), "
        "or os.environ.copy() as the subprocess env."
    ),
    "hermes-path": (
        "Root cause: a hardcoded ~/.hermes or .hermes/ literal bypasses the sanctioned home "
        "resolver (get_hermes_home / HERMES_HOME, used by the plugin data dir), so cues and "
        "logs can land in the wrong profile. Fix: resolve Hermes home through that helper "
        "(or HERMES_HOME). The out-root default ~/.hermes/clips is allowlisted: that is the "
        "documented Studio library path, not a second home resolver."
    ),
}


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _warn(rule: str, path: Path, line: int, detail: str) -> dict:
    return {
        "rule": rule,
        "file": _rel(path),
        "line": line,
        "detail": detail,
        "message": f"{_rel(path)}:{line} {detail}. {CAUSES[rule]}",
    }


def _is_clips_default(text: str) -> bool:
    """True when the literal is the allowlisted Studio out-root (~/.hermes/clips) or a path under it."""
    if "~/.hermes/clips" in text or ".hermes/clips" in text:
        return True
    # Path.home() / ".hermes" / "clips" [/ "library" | "projects" | ...]
    has_home = '".hermes"' in text or "'.hermes'" in text
    has_clips = '"clips"' in text or "'clips'" in text
    return has_home and has_clips


def _is_sanctioned_home_fallback(text: str, func_stack: list[str]) -> bool:
    """The one sanctioned resolver may fall back to HERMES_HOME or Path.home() / '.hermes'."""
    if any(name in {"_data_dir", "get_hermes_home"} for name in func_stack):
        if "HERMES_HOME" in text and (".hermes" in text or "~/.hermes" in text):
            return True
    return False


class _EnvVisitor(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.warnings: list[dict] = []
        self.func_stack: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.func_stack.append(node.name)
        self.generic_visit(node)
        self.func_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Dict(self, node: ast.Dict) -> None:
        for key, val in zip(node.keys, node.values, strict=True):
            # {**os.environ} is a Dict with key=None (or a Starred in some versions).
            if key is None and self._is_environ(val):
                self.warnings.append(_warn("environ-spread", self.path, node.lineno, "{**os.environ} spread"))
            if isinstance(key, ast.Starred) and self._is_environ(key.value):
                self.warnings.append(_warn("environ-spread", self.path, node.lineno, "{**os.environ} spread"))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # dict(os.environ) or os.environ.copy()
        func = node.func
        if isinstance(func, ast.Name) and func.id == "dict" and node.args:
            if self._is_environ(node.args[0]):
                self.warnings.append(_warn("environ-spread", self.path, node.lineno, "dict(os.environ)"))
        if isinstance(func, ast.Attribute) and func.attr == "copy" and self._is_environ(func.value):
            self.warnings.append(_warn("environ-spread", self.path, node.lineno, "os.environ.copy()"))
        self.generic_visit(node)

    def _is_environ(self, node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Attribute)
            and node.attr == "environ"
            and isinstance(node.value, ast.Name)
            and node.value.id in {"os", "_os"}
        )


def scan_env(path: Path, source: str) -> list[dict]:
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []
    v = _EnvVisitor(path)
    v.visit(tree)
    return v.warnings


def scan_paths(path: Path, source: str) -> list[dict]:
    warnings: list[dict] = []
    # Track simple def names by walking lines is enough for the allowlist.
    func = ""
    for i, raw in enumerate(source.splitlines(), 1):
        line = raw.strip()
        if line.startswith("def ") or line.startswith("async def "):
            name = line.split("(", 1)[0].split()[-1]
            func = name
        # Path literals
        interesting = "~/.hermes" in raw or ".hermes/" in raw or '".hermes"' in raw or "'.hermes'" in raw
        if not interesting:
            continue
        # Comments that only describe the allowlist are fine if they talk about clips
        # or the sanctioned resolver.
        if _is_clips_default(raw):
            continue
        if _is_sanctioned_home_fallback(raw, [func]):
            continue
        warnings.append(_warn("hermes-path", path, i, f"hardcoded Hermes path literal: {raw.strip()[:120]}"))
    return warnings


def run_checks(root: Path = ROOT) -> list[dict]:
    warnings: list[dict] = []
    dirs = [root / "hermes_studio", root / "hermes_plugin"]
    for d in dirs:
        if not d.exists():
            continue
        for path in sorted(d.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            warnings.extend(scan_env(path, text))
            warnings.extend(scan_paths(path, text))
    return warnings


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--strict", action="store_true", help="exit 1 when warnings exist")
    args = p.parse_args(argv)
    warnings = run_checks()
    for w in warnings:
        print(f"WARNING {w['rule']} {w['message']}")
    print(f"review-checks: {len(warnings)} warning(s) (warning mode; does not fail CI)")
    if args.strict and warnings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
