from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from hermesclip.download import LIVE_DEFAULT_SEC, probe
from hermesclip.pipeline import run_once
from hermesclip.plan import plan_grok, plan_heuristic, save_plan
from hermesclip.transcribe import load_transcript, transcribe
from hermesclip.download import fetch as fetch_src


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="hermesclip", description="Hermes Studio — HermesClip")
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

    lsp = sub.add_parser("list", help="print library or a manifest.json folder")
    lsp.add_argument("--out", default="")

    prp = sub.add_parser("probe", help="title / live flag for a URL or file")
    prp.add_argument("src")

    stu = sub.add_parser("studio", help="localhost Create / Library / Jobs (loopback)")
    stu.add_argument("--host", default="127.0.0.1")
    stu.add_argument("--port", type=int, default=3870)

    cap = sub.add_parser("captions", help="burn captions on the full video (no clip planner)")
    cap.add_argument("src")
    cap.add_argument("--out", default="./clips")
    cap.add_argument("--whisper", default="tiny")
    cap.add_argument("--style", choices=["pop", "impact", "clean", "glow", "neon", "boxed"], default="pop")
    cap.add_argument("--layout", choices=["fit", "fill"], default="fit")
    cap.add_argument("--aspect", choices=["9:16", "16:9", "1:1"], default="9:16")
    cap.add_argument("--no-hook", action="store_true")

    args = p.parse_args(argv)
    if args.cmd == "run":
        return _run(args)
    if args.cmd == "captions":
        args.mode = "captions"
        args.max_clips = 1
        args.min_sec = 12
        args.max_sec = 1e9
        args.plan = "heuristic"
        args.pacing = "natural"
        args.transcript = ""
        args.work = ""
        args.live_seconds = LIVE_DEFAULT_SEC
        args.live_from_start = False
        args.prompt = ""
        return _run(args)
    if args.cmd == "transcribe":
        return _transcribe_cmd(args)
    if args.cmd == "plan":
        return _plan_cmd(args)
    if args.cmd == "list":
        return _list_cmd(args)
    if args.cmd == "probe":
        return _probe_cmd(args)
    if args.cmd == "studio":
        from hermesclip.studio import serve

        serve(args.host, args.port)
        return 0
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
    run.add_argument("--prompt", default="", help="ClipAnything-lite hunt words")
    run.add_argument("--mode", choices=["clip", "captions"], default="clip")
    run.add_argument("--no-hook", action="store_true")
    run.add_argument("--aspect", choices=["9:16", "16:9", "1:1"], default="9:16")
    run.add_argument("--style", choices=["pop", "impact", "clean", "glow", "neon", "boxed"], default="pop")
    run.add_argument(
        "--layout",
        choices=["fit", "fill"],
        default="fit",
        help="fit = whole frame on blur. fill = punch-in crop.",
    )
    run.add_argument("--work", default="")
    run.add_argument(
        "--live-seconds",
        type=int,
        default=LIVE_DEFAULT_SEC,
        help="If the source is live, capture this many seconds (max 7200).",
    )
    run.add_argument("--live-from-start", action="store_true", help="YouTube live: from stream start")


def _run(args: argparse.Namespace) -> int:
    out_dir = Path(args.out).expanduser().resolve()
    work = Path(args.work).expanduser().resolve() if args.work else None
    result = run_once(
        args.src,
        out_dir,
        max_clips=args.max_clips,
        whisper=args.whisper,
        pacing=args.pacing,
        style=args.style,
        plan=args.plan,
        layout=args.layout,
        work=work,
        live_seconds=args.live_seconds,
        live_from_start=args.live_from_start,
        transcript=Path(args.transcript).expanduser() if args.transcript else None,
        min_sec=args.min_sec,
        max_sec=args.max_sec,
        prompt=getattr(args, "prompt", "") or "",
        hook=not getattr(args, "no_hook", False),
        mode=getattr(args, "mode", "clip"),
        aspect=getattr(args, "aspect", "9:16"),
        on_progress=lambda stage, pct, msg: print(f"{stage} {pct:.0%} {msg}", flush=True),
    )
    print(json.dumps(result, indent=2), flush=True)
    print("done")
    for w in result.get("clips") or []:
        print(w)
    return 0


def _transcribe_cmd(args: argparse.Namespace) -> int:
    import tempfile

    work = Path(args.work).expanduser().resolve() if args.work else Path(tempfile.mkdtemp(prefix="hermesclip-"))
    work.mkdir(parents=True, exist_ok=True)
    video = fetch_src(args.src, work)
    print(f"transcribe {video} ({args.whisper})", flush=True)
    tr = transcribe(video, work, model_size=args.whisper)
    path = work / "transcript.json"
    print(json.dumps({"ok": True, "transcript": str(path), "words": len(tr.words), "duration": tr.duration}))
    return 0


def _plan_cmd(args: argparse.Namespace) -> int:
    tr = load_transcript(Path(args.transcript).expanduser())
    plans = None
    if args.plan in ("auto", "grok"):
        plans = plan_grok(tr, args.max_clips, args.min_sec, args.max_sec)
    if not plans:
        plans = plan_heuristic(tr, args.max_clips, args.min_sec, args.max_sec)
    out = Path(args.out).expanduser() if args.out else Path(args.transcript).expanduser().parent / "plan.json"
    save_plan(plans, out)
    payload = [{"start": x.start, "end": x.end, "title": x.title, "score": x.score, "emphasis": x.emphasis} for x in plans]
    print(json.dumps({"ok": True, "plan": str(out), "clips": payload}, indent=2))
    return 0


def _list_cmd(args: argparse.Namespace) -> int:
    from hermesclip.pipeline import import_legacy, list_jobs

    if args.out:
        out = Path(args.out).expanduser()
        man = out / "manifest.json"
        if not man.is_file():
            print(json.dumps({"ok": False, "error": f"no manifest in {out}"}))
            return 1
        print(man.read_text())
        return 0
    import_legacy()
    jobs = [
        {
            "id": j.id,
            "title": j.title,
            "status": j.status,
            "clips": len(j.clips or []),
            "dir": j.dir,
            "is_live": j.is_live,
        }
        for j in list_jobs()
    ]
    print(json.dumps({"ok": True, "jobs": jobs}, indent=2))
    return 0


def _probe_cmd(args: argparse.Namespace) -> int:
    try:
        info = probe(args.src)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)[-800:]}))
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "title": info.title,
                "is_live": info.is_live,
                "live_status": info.live_status,
                "duration": info.duration,
                "extractor": info.extractor,
                "id": info.video_id,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
