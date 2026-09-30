"""hermes-studio — the command line for Hermes Studio.

Built for three kinds of caller:

* people at a terminal: readable output, short errors with the fix, a progress bar;
* scripts and AI agents: ``--json`` on every command prints exactly one JSON object
  on stdout (progress goes to stderr as JSON lines), and exit codes mean something;
* MCP clients (Claude, Grok, Codex, Cursor …): ``hermes-studio mcp`` serves the same
  tools over stdio, and ``hermes-studio mcp install <client>`` wires it up.

Exit codes: 0 ok · 1 the job failed · 2 bad input · 3 missing dependency · 4 not found.
Nothing here posts anywhere.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from hermes_studio import __version__
from hermes_studio.api import (
    ASPECTS,
    CAPTION_POS,
    EXIT,
    FILTERS,
    LAYOUTS,
    MODES,
    PACING,
    PLANS,
    STYLES,
    HermesStudioError,
)

EXAMPLES = """\
examples:
  hermes-studio run talk.mp4                         3 hook-first shorts from a video
  hermes-studio run https://youtu.be/ID -n 5         5 shorts from a link
  hermes-studio run talk.mp4 --mode captions         caption the whole video
  hermes-studio run stream.mp4 --layout split        facecam on top, gameplay below
  hermes-studio list                                 your runs, newest first
  hermes-studio show <id>                            the clips in one run
  hermes-studio doctor                               check FFmpeg, speech, links
  hermes-studio studio                               open the desk in your browser
  hermes-studio mcp install claude                   add the tools to Claude Code

agents and scripts: add --json to any command for one JSON object on stdout.
exit codes: 0 ok, 1 failed, 2 bad input, 3 missing dependency, 4 not found.
"""


# --------------------------------------------------------------------------- output


class Out:
    """Human text or machine JSON, decided once per command."""

    def __init__(self, json_mode: bool, quiet: bool = False) -> None:
        self.json = json_mode
        self.quiet = quiet
        self.color = (not json_mode) and sys.stdout.isatty() and not os.environ.get("NO_COLOR") and os.environ.get("TERM") != "dumb"
        self.err_color = sys.stderr.isatty() and not os.environ.get("NO_COLOR") and os.environ.get("TERM") != "dumb"
        self._bar_open = False

    def _c(self, code: str, s: str, stream_tty: bool | None = None) -> str:
        on = self.color if stream_tty is None else stream_tty
        return f"\033[{code}m{s}\033[0m" if on else s

    def amber(self, s: str) -> str:
        return self._c("38;5;215", s)

    def dim(self, s: str) -> str:
        return self._c("2", s)

    def bold(self, s: str) -> str:
        return self._c("1", s)

    def green(self, s: str) -> str:
        return self._c("32", s)

    def red(self, s: str, err: bool = False) -> str:
        return self._c("31", s, self.err_color if err else None)

    def say(self, s: str = "") -> None:
        if not self.json:
            print(s, flush=True)

    def emit(self, obj: dict) -> None:
        if self.json:
            print(json.dumps(obj, ensure_ascii=False, default=str), flush=True)

    def error(self, e: HermesStudioError) -> int:
        self.end_bar()
        if self.json:
            print(json.dumps(e.as_dict(), ensure_ascii=False), flush=True)
        else:
            print(self.red("error: ", err=True) + e.message, file=sys.stderr)
            if e.hint:
                print("  " + e.hint, file=sys.stderr)
        return e.exit_code

    def progress(self, stage: str, pct: float, msg: str) -> None:
        if self.quiet:
            return
        if self.json:
            print(json.dumps({"event": "progress", "stage": stage, "progress": round(pct, 3), "message": msg}), file=sys.stderr, flush=True)
            return
        if sys.stderr.isatty():
            width = 24
            fill = int(round(pct * width))
            bar = "█" * fill + "░" * (width - fill)
            line = f"\r  {self._c('38;5;215', bar, self.err_color)} {pct:4.0%}  {stage:<10} {msg[:60]}"
            print(line.ljust(110), end="", file=sys.stderr, flush=True)
            self._bar_open = True
        else:
            print(f"{stage} {pct:.0%} {msg}", file=sys.stderr, flush=True)

    def end_bar(self) -> None:
        if self._bar_open:
            print(file=sys.stderr, flush=True)
            self._bar_open = False


def _fmt_secs(v) -> str:
    try:
        s = float(v)
    except (TypeError, ValueError):
        return "?"
    m, s = divmod(int(round(s)), 60)
    return f"{m}:{s:02d}"


def _short(path: str) -> str:
    home = str(Path.home())
    return "~" + path[len(home):] if path.startswith(home) else path


# --------------------------------------------------------------------------- parser


class _Parser(argparse.ArgumentParser):
    """argparse, but a bad flag becomes a proper error (JSON when --json is set) with exit 2."""

    def error(self, message: str) -> None:  # type: ignore[override]
        import difflib
        import re

        hint = f"Run: {self.prog} --help"
        m = re.search(r"invalid choice: '([^']*)' \(choose from (.*)\)", message)
        if m:
            options = re.findall(r"'([^']*)'", m.group(2)) or [x.strip() for x in m.group(2).split(",") if x.strip()]
            close = difflib.get_close_matches(m.group(1), options, n=1, cutoff=0.5)
            what = "command" if "<command>" in message or "cmd" in message.split(":")[0] else "value"
            message = f"Unknown {what} '{m.group(1)}'. Choose from: {', '.join(options)}"
            if close:
                hint = f"Did you mean '{close[0]}'?  ·  {hint}"
        raise HermesStudioError(message[0].upper() + message[1:].rstrip(".") + ".", hint=hint)


def _look_args(q: argparse.ArgumentParser) -> None:
    g = q.add_argument_group("look")
    g.add_argument("--face", choices=["top", "bottom"], help="split layout: facecam band on top or bottom")
    g.add_argument("--face-size", type=float, metavar="PCT", help="split layout: face band share of height, 20-60")
    g.add_argument("--face-box", default="", metavar="X,Y,W,H", help="split layout: manual camera box in %% of the source")
    g.add_argument("--filter", choices=FILTERS, help="colour look")
    g.add_argument("--caption-pos", choices=CAPTION_POS, help="where captions sit")
    g.add_argument("--audio", choices=["off", "clean"], help="clean = denoise + loudness to -14 LUFS")
    g.add_argument("--progress-bar", "--progress", dest="progress_bar", action="store_true", help="thin amber progress bar on the clip")
    g.add_argument("--fix", action="append", default=[], metavar="WORD=RIGHT", help="caption word fix, e.g. --fix cloud=Claude (repeatable)")


def _common(q: argparse.ArgumentParser) -> None:
    q.add_argument("--json", action="store_true", help="one JSON object on stdout (for scripts and agents)")


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(
        prog="hermes-studio",
        description="Hermes Studio on the command line. Long video in, captioned shorts out. Runs on this computer. Never posts.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("-V", "--version", action="version", version=f"hermes-studio {__version__}")
    sub = p.add_subparsers(dest="cmd", metavar="<command>", parser_class=_Parser)

    r = sub.add_parser("run", help="make shorts (or captions, reframe, tighten, transcript) from a video or link",
                       description="Make shorts from a video file or link. Clips are saved to your library; --out also copies them somewhere.")
    r.add_argument("src", help="video/audio file or http(s) link (YouTube, X, Twitch, Kick …)")
    r.add_argument("--mode", choices=MODES, default="clip", help="clip = hook-first shorts (default); captions = caption the whole video; reframe; tighten = cut filler; transcript = SRT/VTT/TXT")
    r.add_argument("-n", "--max-clips", type=int, default=3, metavar="N", help="how many shorts (default 3)")
    r.add_argument("--min-sec", type=float, default=12, metavar="S", help="shortest clip, seconds (default 12)")
    r.add_argument("--max-sec", type=float, default=45, metavar="S", help="longest clip, seconds (default 45)")
    r.add_argument("-o", "--out", default="", metavar="DIR", help="also copy the results into DIR")
    r.add_argument("--aspect", choices=ASPECTS, help="output shape (default 9:16)")
    r.add_argument("--layout", choices=LAYOUTS, help="auto picks from the frame; fill = speaker crop; split = facecam + screen; fit = whole frame on blur")
    r.add_argument("--style", choices=STYLES, default="pop", help="caption style (default pop)")
    r.add_argument("--no-captions", action="store_true", help="cut and frame without burning captions")
    r.add_argument("--no-hook", action="store_true", help="no hook title in the first seconds")
    r.add_argument("--prompt", default="", help="what to hunt for, e.g. 'funny moments' or 'the pricing part'")
    r.add_argument("--keywords", default="", help="words to highlight in captions, comma-separated")
    r.add_argument("--whisper", default="fast", help="speech quality: fast (default), balanced, accurate")
    r.add_argument("--recommend", action="store_true", help="look at the source first and pick the settings for you")
    adv = r.add_argument_group("advanced")
    adv.add_argument("--plan", choices=PLANS, default="auto", help="how moments are picked")
    adv.add_argument("--pacing", choices=PACING, help="tight trims pauses (default for clips)")
    adv.add_argument("--transcript", default="", metavar="FILE", help="reuse an existing transcript.json")
    adv.add_argument("--work", default="", metavar="DIR", help="keep working files here")
    adv.add_argument("--live-seconds", type=int, default=None, metavar="S", help="live streams: how much to capture (default 1200)")
    adv.add_argument("--live-from-start", action="store_true", help="YouTube live: capture from the start")
    adv.add_argument("--detach", action="store_true", help="start the job in the background, print its id and return (poll with: hermes-studio show <id>)")
    _look_args(r)
    _common(r)
    r.add_argument("-q", "--quiet", action="store_true", help="no progress output")

    c = sub.add_parser("captions", help="caption a whole video (shortcut for run --mode captions)")
    c.add_argument("src")
    c.add_argument("-o", "--out", default="", metavar="DIR")
    c.add_argument("--style", choices=STYLES, default="pop")
    c.add_argument("--layout", choices=LAYOUTS, default="fit")
    c.add_argument("--aspect", choices=ASPECTS, default="9:16")
    c.add_argument("--whisper", default="fast")
    c.add_argument("--no-hook", action="store_true")
    _look_args(c)
    _common(c)
    c.add_argument("-q", "--quiet", action="store_true")

    ls = sub.add_parser("list", aliases=["ls"], help="your runs, newest first")
    ls.add_argument("-n", "--limit", type=int, default=20, help="how many (default 20, 0 = all)")
    ls.add_argument("--status", choices=["completed", "failed", "running", "queued"], help="only runs with this status")
    ls.add_argument("--out", default="", help=argparse.SUPPRESS)  # legacy: print a manifest.json folder
    _common(ls)

    sh = sub.add_parser("show", help="one run: its clips, files, scores and settings")
    sh.add_argument("id", help="run id (from hermes_studio list)")
    _common(sh)

    op = sub.add_parser("open", help="open a run's folder (or the library) in your file manager")
    op.add_argument("id", nargs="?", default="", help="run id; omit for the whole library")
    _common(op)

    pr = sub.add_parser("probe", help="title, length and live status of a file or link")
    pr.add_argument("src")
    _common(pr)

    rc = sub.add_parser("recommend", help="suggested settings for a file or link")
    rc.add_argument("src")
    _common(rc)

    rs = sub.add_parser("restyle", help="re-render one clip with a new look or new in/out points (old file goes to .trash)")
    rs.add_argument("id", help="run id")
    rs.add_argument("file", help="clip file, e.g. clip-01.mp4")
    rs.add_argument("--layout", choices=LAYOUTS)
    rs.add_argument("--style", choices=STYLES)
    rs.add_argument("--no-captions", action="store_true")
    rs.add_argument("--no-hook", action="store_true")
    rs.add_argument("--start", type=float, help="new start on the source, seconds")
    rs.add_argument("--end", type=float, help="new end on the source, seconds")
    rs.add_argument("--title", default="")
    _look_args(rs)
    _common(rs)

    ed = sub.add_parser("edit", help="trim, split, duplicate, drop or restore a clip file")
    ed.add_argument("src")
    ed.add_argument("--op", choices=["trim", "split", "duplicate", "drop", "restore"], default="trim")
    ed.add_argument("--start", type=float)
    ed.add_argument("--end", type=float)
    ed.add_argument("--at", type=float, help="split point, seconds")
    ed.add_argument("-o", "--out", default="")
    _common(ed)

    nm = sub.add_parser("name", help="AI titles for every clip in a run (local Ollama first), or rename one clip")
    nm.add_argument("id")
    nm.add_argument("--file", default="")
    nm.add_argument("--title", default="")
    _common(nm)

    cp = sub.add_parser("copy", help="titles, description and hashtags for a run (does not post)")
    cp.add_argument("src", help="run id, run folder or transcript.json")
    cp.add_argument("--clip-title", default="")
    _common(cp)

    tr = sub.add_parser("transcribe", help="transcript.json only, no render")
    tr.add_argument("src")
    tr.add_argument("--work", default="")
    tr.add_argument("--whisper", default="fast")
    _common(tr)

    pl = sub.add_parser("plan", help="score clip moments from a transcript.json (no render)")
    pl.add_argument("transcript")
    pl.add_argument("-o", "--out", default="")
    pl.add_argument("-n", "--max-clips", type=int, default=3)
    pl.add_argument("--min-sec", type=float, default=12)
    pl.add_argument("--max-sec", type=float, default=45)
    pl.add_argument("--plan", choices=PLANS, default="heuristic")
    _common(pl)

    tl = sub.add_parser("tools", help="what Studio can do: modes, styles, filters, layouts")
    _common(tl)

    dr = sub.add_parser("doctor", help="check FFmpeg, captions, speech, links and the library")
    _common(dr)

    st = sub.add_parser("studio", help="open the desk in your browser (loopback only)")
    st.add_argument("--host", default="127.0.0.1")
    st.add_argument("--port", type=int, default=3870)
    st.add_argument("--no-browser", action="store_true", help="don't open a browser tab")

    sub.add_parser("organize", help="sort the library into platform folders").add_argument("--json", action="store_true")

    m = sub.add_parser("mcp", help="MCP server for Claude, Grok, Codex, Cursor … (stdio)",
                       description="With no action: serve the Hermes Studio tools over MCP stdio. "
                                   "`install` adds the server to a client; `config` prints the JSON to paste.")
    msub = m.add_subparsers(dest="mcp_cmd", metavar="<action>", parser_class=_Parser)
    msub.add_parser("serve", help="serve over stdio (default)")
    mi = msub.add_parser("install", help="add hermes-studio to an MCP client")
    mi.add_argument("client", choices=["claude", "grok", "codex", "cursor", "hermes"], help="which client")
    mi.add_argument("--scope", choices=["user", "project"], default="user", help="user = every project (default)")
    mi.add_argument("--dry-run", action="store_true", help="print what would run, change nothing")
    _common(mi)
    mc = msub.add_parser("config", help="print the mcpServers JSON block to paste into any client")
    _common(mc)
    return p


# --------------------------------------------------------------------------- commands


def _look(a: argparse.Namespace) -> dict:
    lk: dict = {}
    for k in ("layout", "face", "filter", "caption_pos", "audio"):
        v = getattr(a, k, None)
        if v:
            lk[k] = v
    if getattr(a, "face_size", None):
        lk["face_ratio"] = a.face_size
    if getattr(a, "face_box", ""):
        lk["face_box"] = a.face_box
    if getattr(a, "progress_bar", False):
        lk["progress"] = True
    return lk


def _fixes(a: argparse.Namespace) -> str:
    return ",".join(getattr(a, "fix", []) or [])


def _print_run_result(o: Out, res: dict) -> None:
    items = res.get("items") or []
    files = res.get("clips") or []
    if res.get("ok"):
        n = len(items) or len(files)
        what = "clip" if res.get("mode") == "clip" else "file"
        o.say(o.green("✓ ") + o.bold(f"{n} {what}{'s' if n != 1 else ''}") + f" from {o.bold(res.get('title') or 'source')}" + o.dim(f"  ·  {res.get('seconds', '?')}s"))
        for it in items:
            score = f"{float(it['score']):.1f}" if it.get("score") is not None else "  – "
            o.say(f"  {o.amber(score)}  {_fmt_secs(it.get('seconds'))}  {it.get('title') or it.get('file')}")
            o.say(o.dim(f"        {_short(str(it.get('path')))}"))
        if not items:
            for f in files:
                o.say("  " + _short(f))
        o.say(o.dim(f"  run {res.get('id')}  ·  open it: hermes-studio open {res.get('id')}"))
    else:
        o.say(o.red("✗ ") + (res.get("error") or res.get("message") or "the job failed"))
        o.say(o.dim(f"  run {res.get('id')}  ·  details: hermes-studio show {res.get('id')}"))


def cmd_run(a: argparse.Namespace, o: Out) -> int:
    from hermes_studio import api

    if a.cmd == "captions":
        a.mode, a.max_clips, a.min_sec, a.max_sec = "captions", 1, 12, 45
        a.plan, a.pacing, a.transcript, a.work, a.prompt, a.keywords = "heuristic", "natural", "", "", "", ""
        a.live_seconds, a.live_from_start, a.recommend, a.no_captions, a.detach = None, False, False, False, False
    kw: dict[str, Any] = dict(
        mode=a.mode, out=a.out or None, max_clips=a.max_clips, min_sec=a.min_sec, max_sec=a.max_sec,
        whisper=a.whisper, plan=a.plan, pacing=a.pacing, style=a.style, aspect=a.aspect, layout=a.layout,
        captions=False if a.no_captions else None, hook=False if a.no_hook else None, prompt=a.prompt,
        keywords=a.keywords, look=_look(a), fixes=_fixes(a), transcript=a.transcript or None,
        work=a.work or None, live_seconds=a.live_seconds, live_from_start=a.live_from_start, recommend=a.recommend,
    )
    if a.detach:
        return _detach(a, o, kw)
    api.check_source(a.src)  # fail fast, before any header or job folder
    if not o.json:
        o.say(o.amber("◆ ") + f"{a.mode} · {a.src}")
    on_created = _write_id_file if os.environ.get("HERMES_STUDIO_ID_FILE") else None
    res = api.run(a.src, on_progress=o.progress, on_created=on_created, **kw)
    o.end_bar()
    o.emit(res)
    _print_run_result(o, res)
    return 0 if res.get("ok") else EXIT["failed"]


def _detach(a: argparse.Namespace, o: Out, kw: dict) -> int:
    """Validate now, then run the job in a child process and return its id straight away."""
    import subprocess
    import tempfile
    import time

    from hermes_studio import api

    api.check_source(a.src)
    api.require_ffmpeg()
    fd, id_file = tempfile.mkstemp(prefix="hermes-studio-id-")
    os.close(fd)
    argv = [x for x in sys.argv[1:] if x not in ("--detach", "--json")] if sys.argv[1:2] in (["run"], ["captions"]) else None
    if argv is None:
        raise HermesStudioError("--detach only works from the command line.")
    env = {**os.environ, "HERMES_STUDIO_ID_FILE": id_file}
    kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "env": env}
    if os.name == "nt":
        kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen([sys.executable, "-m", "hermes_studio", *argv, "--quiet"], **kwargs)  # noqa: S603
    job_id = ""
    for _ in range(600):  # the id exists as soon as the job is created (before download)
        job_id = Path(id_file).read_text().strip() if Path(id_file).exists() else ""
        if job_id:
            break
        time.sleep(0.1)
    Path(id_file).unlink(missing_ok=True)
    if not job_id:
        raise HermesStudioError("The background job did not start.", code="failed", hint="Run it without --detach to see the error.")
    o.emit({"ok": True, "id": job_id, "status": "running", "poll": f"hermes-studio show {job_id} --json"})
    o.say(o.amber("◆ ") + f"started run {o.bold(job_id)} in the background")
    o.say(o.dim(f"  check on it: hermes-studio show {job_id}"))
    return 0


def cmd_list(a: argparse.Namespace, o: Out) -> int:
    from hermes_studio import api

    if a.out:  # legacy: print a manifest.json folder
        man = Path(a.out).expanduser() / "manifest.json"
        if not man.is_file():
            raise HermesStudioError(f"No manifest.json in {a.out}", code="not_found")
        print(man.read_text())
        return 0
    res = api.library(limit=a.limit or None, status=a.status)
    o.emit(res)
    if o.json:
        return 0
    if not res["jobs"]:
        o.say("No runs yet. Make one:  hermes-studio run <video or link>")
        return 0
    mark = {"completed": o.green("✓"), "failed": o.red("✗"), "running": o.amber("…"), "queued": o.dim("·")}
    for j in res["jobs"]:
        n = j.get("clips") or 0
        clips = f"{n} clip{'s' if n != 1 else ''}" if j.get("status") == "completed" else (j.get("status") or "")
        when = (j.get("created_at") or "")[:16].replace("T", " ")
        o.say(f"{mark.get(j.get('status'), ' ')} {o.amber(j['id'])}  {when}  {clips:<9} {(j.get('title') or '')[:60]}")
    if res["total"] > len(res["jobs"]):
        o.say(o.dim(f"  … {res['total'] - len(res['jobs'])} more  (hermes-studio list -n 0)"))
    return 0


def cmd_show(a: argparse.Namespace, o: Out) -> int:
    from hermes_studio import api

    res = api.show(a.id)
    o.emit(res)
    if o.json:
        return 0
    o.say(o.bold(res.get("title") or res["id"]) + o.dim(f"  ·  {res.get('status')}  ·  {res.get('mode')}  ·  {res['id']}"))
    o.say(o.dim(f"  source  {res.get('source')}"))
    o.say(o.dim(f"  folder  {_short(str(res.get('dir')))}"))
    if res.get("status") in ("running", "queued"):
        o.say(o.amber(f"  {res.get('message') or 'working'}"))
    if res.get("error"):
        o.say(o.red(f"  {res['error']}"))
    for it in res.get("items") or []:
        score = f"{float(it['score']):.1f}" if it.get("score") is not None else "  – "
        o.say(f"  {o.amber(score)}  {_fmt_secs(it.get('seconds'))}  {it.get('file')}  {it.get('title') or ''}")
    return 0


def cmd_open(a: argparse.Namespace, o: Out) -> int:
    import subprocess

    from hermes_studio import api
    from hermes_studio.pipeline import library_root

    path = Path(api.show(a.id)["dir"]) if a.id else library_root()
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]  # noqa: S606
    else:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        try:
            subprocess.Popen([opener, str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603
        except FileNotFoundError:
            o.say(str(path))
    o.emit({"ok": True, "path": str(path)})
    o.say(_short(str(path)))
    return 0


def cmd_probe(a: argparse.Namespace, o: Out) -> int:
    from hermes_studio import api

    res = api.probe_source(a.src)
    o.emit(res)
    live = o.red(" LIVE") if res.get("is_live") else ""
    o.say(f"{o.bold(res.get('title') or '?')}{live}  {_fmt_secs(res.get('duration')) if res.get('duration') else ''}  {o.dim(res.get('extractor') or '')}")
    return 0


def cmd_recommend(a: argparse.Namespace, o: Out) -> int:
    from hermes_studio import api

    res = api.recommend(a.src)
    o.emit(res)
    r = res["recommendation"]
    o.say(o.bold(res.get("title") or a.src))
    o.say(f"  {r.get('mode')} · {r.get('max_clips')} clips · {r.get('aspect')} · layout {r.get('layout')} · style {r.get('style')}")
    for w in r.get("why") or []:
        o.say(o.dim("  · " + w))
    o.say(o.dim(f"  use it: hermes-studio run {a.src} --recommend"))
    return 0


def cmd_restyle(a: argparse.Namespace, o: Out) -> int:
    from hermes_studio import api

    res = api.restyle(a.id, a.file, look=_look(a), style=a.style, captions=False if a.no_captions else None,
                      hook=False if a.no_hook else None, start=a.start, end=a.end, fixes=_fixes(a), title=a.title or None)
    o.emit(res)
    o.say(o.green("✓ ") + f"restyled {a.file}")
    return 0


def cmd_edit(a: argparse.Namespace, o: Out) -> int:
    from hermes_studio import api

    res = api.edit(a.src, a.op, start=a.start, end=a.end, at=a.at, out=a.out or None)
    o.emit(res)
    for f in res.get("files") or [res.get("file")]:
        o.say(o.green("✓ ") + f"{a.op}  {_short(str(f))}")
    return 0


def cmd_name(a: argparse.Namespace, o: Out) -> int:
    from hermes_studio import api

    res = api.name(a.id, a.file, a.title)
    o.emit(res)
    o.say(o.green("✓ ") + "named")
    for c in res.get("clips") or []:
        if isinstance(c, dict):
            o.say(f"  {c.get('file')}  {c.get('title')}")
    return 0


def cmd_copy(a: argparse.Namespace, o: Out) -> int:
    from hermes_studio import api

    res = api.copy(a.src, a.clip_title)
    o.emit(res)
    if not o.json:
        for k, v in res.items():
            if k == "ok":
                continue
            o.say(o.amber(k))
            o.say("  " + ("\n  ".join(v) if isinstance(v, list) else str(v)))
    return 0


def cmd_transcribe(a: argparse.Namespace, o: Out) -> int:
    from hermes_studio import api

    res = api.transcribe_only(a.src, work=a.work or None, whisper=a.whisper)
    o.emit(res)
    o.say(o.green("✓ ") + f"{res['words']} words · {_fmt_secs(res['duration'])}  {_short(res['transcript'])}")
    return 0


def cmd_plan(a: argparse.Namespace, o: Out) -> int:
    from hermes_studio.plan import plan_grok, plan_heuristic, save_plan
    from hermes_studio.transcribe import load_transcript

    path = Path(a.transcript).expanduser()
    if not path.is_file():
        raise HermesStudioError(f"File not found: {a.transcript}", code="not_found")
    tr = load_transcript(path)
    plans = plan_grok(tr, a.max_clips, a.min_sec, a.max_sec) if a.plan in ("auto", "grok") else None
    plans = plans or plan_heuristic(tr, a.max_clips, a.min_sec, a.max_sec)
    out = Path(a.out).expanduser() if a.out else path.parent / "plan.json"
    save_plan(plans, out)
    clips = [{"start": x.start, "end": x.end, "title": x.title, "score": x.score, "emphasis": x.emphasis} for x in plans]
    o.emit({"ok": True, "plan": str(out), "clips": clips})
    for c in clips:
        score = f"{float(c['score']):.1f}"
        o.say(f"  {o.amber(score)}  {_fmt_secs(c['start'])}–{_fmt_secs(c['end'])}  {c['title']}")
    o.say(o.dim(f"  saved {_short(str(out))}"))
    return 0


def cmd_tools(a: argparse.Namespace, o: Out) -> int:
    from hermes_studio import api

    res = api.tools()
    o.emit(res)
    if o.json:
        return 0
    for t in res.get("tools") or []:
        o.say(f"{o.amber(t.get('id', '')):<22} {t.get('blurb') or t.get('title') or ''}")
    o.say(o.dim(f"styles   {' '.join(res['styles'])}"))
    o.say(o.dim(f"filters  {' '.join(res['filters'])}"))
    o.say(o.dim(f"layouts  {' '.join(LAYOUTS)}   aspects {' '.join(res['aspects'])}"))
    return 0


def cmd_doctor(a: argparse.Namespace, o: Out) -> int:
    from hermes_studio import api

    res = api.doctor()
    o.emit(res)
    if not o.json:
        o.say(o.bold(f"hermes-studio {res['version']}") + o.dim(f"  ·  {res['python']}"))
        for c in res["checks"]:
            mark = o.green("✓") if c["ok"] else (o.red("✗") if c["required"] else o.amber("!"))
            o.say(f"  {mark} {c['name']:<26} {o.dim(c['detail'])}")
            if c.get("fix"):
                o.say(f"      {c['fix']}")
        o.say(o.green("Ready.") if res["ok"] else o.red("Not ready — fix the ✗ lines above."))
    return 0 if res["ok"] else EXIT["missing_dependency"]


def cmd_studio(a: argparse.Namespace, o: Out) -> int:
    import threading
    import webbrowser

    from hermes_studio.studio import serve

    if not a.no_browser and os.environ.get("HERMES_STUDIO_NO_BROWSER") != "1" and sys.stdout.isatty():
        url = f"http://{a.host}:{a.port}/"
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    serve(a.host, a.port)
    return 0


def cmd_organize(a: argparse.Namespace, o: Out) -> int:
    from hermes_studio.pipeline import organize_library

    moved = organize_library()
    o.emit({"ok": True, "moved": moved})
    o.say(o.green("✓ ") + f"library organized ({moved} moved)")
    return 0


def cmd_mcp(a: argparse.Namespace, o: Out) -> int:
    from hermes_studio import mcp

    action = getattr(a, "mcp_cmd", None) or "serve"
    if action == "serve":
        return mcp.serve()
    if action == "config":
        cfg = mcp.client_config()
        print(json.dumps(cfg if o.json else {"mcpServers": {"hermes-studio": cfg}}, indent=None if o.json else 2))
        return 0
    res = mcp.install(a.client, scope=a.scope, dry_run=a.dry_run)
    o.emit(res)
    if not o.json:
        if res.get("dry_run"):
            o.say(o.dim("would run: ") + res.get("command", ""))
        else:
            o.say(o.green("✓ ") + f"hermes-studio added to {a.client}" + (o.dim(f"  ({res['where']})") if res.get("where") else ""))
            if res.get("next"):
                o.say("  " + res["next"])
    return 0 if res.get("ok") else EXIT["failed"]


COMMANDS = {
    "run": cmd_run, "captions": cmd_run, "list": cmd_list, "ls": cmd_list, "show": cmd_show, "open": cmd_open,
    "probe": cmd_probe, "recommend": cmd_recommend, "restyle": cmd_restyle, "edit": cmd_edit, "name": cmd_name,
    "copy": cmd_copy, "transcribe": cmd_transcribe, "plan": cmd_plan, "tools": cmd_tools, "doctor": cmd_doctor,
    "studio": cmd_studio, "organize": cmd_organize, "mcp": cmd_mcp,
}


def _write_id_file(job) -> None:
    path = os.environ.get("HERMES_STUDIO_ID_FILE")
    if path:
        Path(path).write_text(job.id)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    json_mode = "--json" in argv
    o = Out(json_mode, quiet="-q" in argv or "--quiet" in argv)
    parser = build_parser()
    try:
        if not argv:
            parser.print_help()
            return 0
        a = parser.parse_args(argv)
        if not a.cmd:
            parser.print_help()
            return 0
        return COMMANDS[a.cmd](a, o)
    except HermesStudioError as e:
        return o.error(e)
    except KeyboardInterrupt:
        o.end_bar()
        print("\nstopped", file=sys.stderr)
        return 130
    except Exception as e:  # unexpected: short message, full detail only with HERMES_STUDIO_DEBUG=1
        if os.environ.get("HERMES_STUDIO_DEBUG") == "1":
            raise
        msg = str(e).strip().splitlines()[-1] if str(e).strip() else type(e).__name__
        return o.error(HermesStudioError(f"{type(e).__name__}: {msg[:400]}", code="failed",
                                       hint="Run `hermes-studio doctor`. For the full trace: HERMES_STUDIO_DEBUG=1"))


def _old_name(argv: list[str] | None = None) -> int:
    """The old command name. Works, and points people to the new one."""
    print("Note: the command is now 'hermes-studio' (was 'hermesclip'). This still works.", file=sys.stderr)
    return main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
