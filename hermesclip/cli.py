from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from hermesclip.download import fetch
from hermesclip.plan import plan_grok, plan_heuristic, save_plan
from hermesclip.render import probe_duration, render_clip
from hermesclip.transcribe import Transcript, Word, load_transcript, transcribe


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="hermesclip", description="HermesClip — Linux 9:16 clipper")
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="download + transcribe + plan + render")
    _add_run_args(run)

    trp = sub.add_parser("transcribe", help="write transcript.json (no render)")
    trp.add_argument("src")
    trp.add_argument("--work", default="")
    trp.add_argument("--whisper", default="tiny")

    plp = sub.add_parser("plan", help="score clip windows from transcript.json")
    plp.add_argument("transcript")
    plp.add_argument("--out", default="")
    plp.add_argument("--max-clips", type=int, default=3)
    plp.add_argument("--min-sec", type=float, default=12)
    plp.add_argument("--max-sec", type=float, default=45)
    plp.add_argument("--plan", choices=["auto", "heuristic", "grok"], default="heuristic")

    lsp = sub.add_parser("list", help="print manifest.json clips")
    lsp.add_argument("--out", default="")

    args = p.parse_args(argv)
    if args.cmd == "run":
        return _run(args)
    if args.cmd == "transcribe":
        return _transcribe_cmd(args)
    if args.cmd == "plan":
        return _plan_cmd(args)
    if args.cmd == "list":
        return _list_cmd(args)
    return 2


def _add_run_args(run: argparse.ArgumentParser) -> None:
    run.add_argument("src")
    run.add_argument("--out", default="./clips")
    run.add_argument("--max-clips", type=int, default=3)
    run.add_argument("--min-sec", type=float, default=12)
    run.add_argument("--max-sec", type=float, default=45)
    run.add_argument("--whisper", default="tiny")
    run.add_argument("--transcript", default="", help="reuse transcript.json")
    run.add_argument("--plan", choices=["auto", "heuristic", "grok"], default="auto")
    run.add_argument("--pacing", choices=["tight", "natural"], default="tight")
    run.add_argument("--style", choices=["pop", "impact", "clean"], default="pop")
    run.add_argument(
        "--layout",
        choices=["fit", "fill"],
        default="fit",
        help="fit = whole frame on blur. fill = punch-in crop.",
    )
    run.add_argument("--work", default="")


def _work_dir(args_work: str) -> Path:
    work = Path(args_work).expanduser().resolve() if args_work else Path(tempfile.mkdtemp(prefix="hermesclip-"))
    work.mkdir(parents=True, exist_ok=True)
    return work


def _pick_plans(tr: Transcript, args) -> list:
    plans = None
    if args.plan in ("auto", "grok"):
        plans = plan_grok(tr, args.max_clips, args.min_sec, args.max_sec)
        if args.plan == "grok" and not plans:
            print("grok planner unavailable (no XAI_API_KEY); using heuristic", file=sys.stderr)
    if not plans:
        plans = plan_heuristic(tr, args.max_clips, args.min_sec, args.max_sec)
    return plans


def _run(args: argparse.Namespace) -> int:
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    work = _work_dir(args.work)

    video = fetch(args.src, work)
    if args.transcript:
        tr = load_transcript(Path(args.transcript))
    else:
        print(f"transcribe {video} ({args.whisper})", flush=True)
        tr = transcribe(video, work, model_size=args.whisper)
        if not tr.words:
            dur = probe_duration(video)
            tr = Transcript("en", dur, "", [Word("…", 0.0, min(dur, args.max_sec))])

    plans = _pick_plans(tr, args)
    save_plan(plans, work / "plan.json")
    print(json.dumps([{"start": x.start, "end": x.end, "title": x.title, "score": x.score} for x in plans], indent=2), flush=True)

    written = []
    for i, plan in enumerate(plans, 1):
        dest = out_dir / f"clip-{i:02d}.mp4"
        print(f"render {dest.name} {plan.start:.1f}-{plan.end:.1f}s", flush=True)
        render_clip(
            video, plan, tr, dest, work, pacing=args.pacing, style=args.style, layout=args.layout
        )
        written.append(str(dest))
    (out_dir / "manifest.json").write_text(
        json.dumps({"source": str(video), "clips": written, "work": str(work)}, indent=2)
    )
    print("done")
    for w in written:
        print(w)
    return 0


def _transcribe_cmd(args: argparse.Namespace) -> int:
    work = _work_dir(args.work)
    video = fetch(args.src, work)
    print(f"transcribe {video} ({args.whisper})", flush=True)
    tr = transcribe(video, work, model_size=args.whisper)
    path = work / "transcript.json"
    print(json.dumps({"ok": True, "transcript": str(path), "words": len(tr.words), "duration": tr.duration}))
    return 0


def _plan_cmd(args: argparse.Namespace) -> int:
    tr = load_transcript(Path(args.transcript).expanduser())
    plans = _pick_plans(tr, args)
    out = Path(args.out).expanduser() if args.out else Path(args.transcript).expanduser().parent / "plan.json"
    save_plan(plans, out)
    payload = [{"start": x.start, "end": x.end, "title": x.title, "score": x.score, "emphasis": x.emphasis} for x in plans]
    print(json.dumps({"ok": True, "plan": str(out), "clips": payload}, indent=2))
    return 0


def _list_cmd(args: argparse.Namespace) -> int:
    out = Path(args.out).expanduser() if args.out else Path.home() / ".hermes" / "clips"
    man = out / "manifest.json"
    if not man.is_file():
        print(json.dumps({"ok": False, "error": f"no manifest in {out}"}))
        return 1
    print(man.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
