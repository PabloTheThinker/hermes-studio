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
    cap.add_argument("--layout", choices=["auto", "fit", "fill", "split"], default="fit")
    _add_look_args(cap)
    cap.add_argument("--aspect", choices=["9:16", "16:9", "1:1", "4:5"], default="9:16")
    cap.add_argument("--no-hook", action="store_true")

    edt = sub.add_parser("edit", help="trim or split an existing clip (local; does not post)")
    edt.add_argument("src")
    edt.add_argument("--op", choices=["trim", "split", "duplicate", "drop", "restore"], default="trim")
    edt.add_argument("--start", type=float, default=None)
    edt.add_argument("--end", type=float, default=None)
    edt.add_argument("--at", type=float, default=None, help="split point in seconds")
    edt.add_argument("--out", default="")

    sub.add_parser("organize", help="sort the library into platform folders (YouTube, Twitch, Kick, X, Local files …)")
    nmp = sub.add_parser("name", help="AI-name every clip in a library run (Opus-style titles; local Ollama first)")
    nmp.add_argument("job", help="library job id")
    nmp.add_argument("--file", default="", help="rename one clip file instead")
    nmp.add_argument("--title", default="", help="title for --file")
    cop = sub.add_parser("copy", help="titles / description / hashtags from a job or transcript (does not post)")
    cop.add_argument("src", help="job directory, job id, or transcript.json")
    cop.add_argument("--clip-title", default="")

    rsp = sub.add_parser("restyle", help="re-render one clip with a new look or new in/out points (old file goes to .trash)")
    rsp.add_argument("job", help="library job id")
    rsp.add_argument("file", help="clip file, e.g. clip-01.mp4")
    rsp.add_argument("--layout", choices=["auto", "fit", "fill", "split"], default=None)
    _add_look_args(rsp)
    rsp.add_argument("--style", choices=["pop", "impact", "clean", "glow", "neon", "boxed"], default=None)
    rsp.add_argument("--no-captions", action="store_true")
    rsp.add_argument("--no-hook", action="store_true")
    rsp.add_argument("--start", type=float, default=None, help="new start on the source, seconds")
    rsp.add_argument("--end", type=float, default=None, help="new end on the source, seconds")
    rsp.add_argument("--title", default="")

    args = p.parse_args(argv)
    if args.cmd == "restyle":
        from hermesclip.pipeline import restyle_clip

        res = restyle_clip(
            args.job, args.file, look=_look_from(args), style=args.style,
            captions=False if args.no_captions else None, hook=False if args.no_hook else None,
            start=args.start, end=args.end, fixes=_fixes_from(args), title=args.title or None,
        )
        print(json.dumps(res, indent=2))
        return 0 if res.get("ok") else 1
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
    if args.cmd == "edit":
        return _edit_cmd(args)
    if args.cmd == "organize":
        from hermesclip.pipeline import organize_library

        print(json.dumps({"ok": True, "moved": organize_library()}, indent=2))
        return 0
    if args.cmd == "name":
        from hermesclip.pipeline import name_job, rename_clip

        res = rename_clip(args.job, args.file, args.title) if args.file else name_job(args.job)
        print(json.dumps(res, indent=2))
        return 0 if res.get("ok") else 1
    if args.cmd == "copy":
        return _copy_cmd(args)
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



def _add_look_args(q: argparse.ArgumentParser, default_layout: str | None = "auto") -> None:
    q.add_argument("--face", choices=["top", "bottom"], default=None, help="split: facecam band on top or bottom")
    q.add_argument("--face-size", type=float, default=None, help="split: face band share of height, 20-60 (%%)")
    q.add_argument("--face-box", default="", help="split: manual camera box x,y,w,h in %% of the source (e.g. 76,64,22,30)")
    q.add_argument("--filter", default=None, choices=["none", "punch", "warm", "cool", "cinematic", "vintage", "bw", "bright"])
    q.add_argument("--caption-pos", default=None, choices=["auto", "top", "middle", "bottom"])
    q.add_argument("--audio", default=None, choices=["off", "clean"], help="clean = denoise + loudness to -14 LUFS")
    q.add_argument("--progress", action="store_true", help="thin amber progress bar")
    q.add_argument("--fix", action="append", default=[], help="word fix, e.g. --fix cloud=Claude (repeatable)")


def _look_from(args: argparse.Namespace) -> dict:
    lk = {}
    if getattr(args, "layout", None):
        lk["layout"] = args.layout
    for k, a in (("face", "face"), ("filter", "filter"), ("caption_pos", "caption_pos"), ("audio", "audio")):
        v = getattr(args, a, None)
        if v:
            lk[k] = v
    if getattr(args, "face_size", None):
        lk["face_ratio"] = args.face_size
    if getattr(args, "face_box", ""):
        lk["face_box"] = args.face_box
    if getattr(args, "progress", False):
        lk["progress"] = True
    return lk


def _fixes_from(args: argparse.Namespace) -> str:
    return ",".join(getattr(args, "fix", []) or [])


def _add_run_args(run: argparse.ArgumentParser) -> None:
    run.add_argument("src")
    run.add_argument("--out", default="./clips")
    run.add_argument("--max-clips", type=int, default=3)
    run.add_argument("--min-sec", type=float, default=12)
    run.add_argument("--max-sec", type=float, default=45)
    run.add_argument("--whisper", default="tiny", help="fast | balanced | accurate, or a faster-whisper model name")
    run.add_argument("--transcript", default="", help="reuse transcript.json")
    run.add_argument("--plan", choices=["auto", "heuristic", "grok"], default="auto")
    run.add_argument("--pacing", choices=["tight", "natural"], default="tight")
    run.add_argument("--prompt", default="", help="ClipAnything-lite hunt words")
    run.add_argument("--keywords", default="", help="Words to highlight in captions (Opus-style)")
    run.add_argument("--recommend", action="store_true", help="Hermes picks settings after analyzing the source")
    run.add_argument("--mode", choices=["clip", "captions", "reframe", "tighten", "transcript"], default="clip")
    run.add_argument("--no-hook", action="store_true")
    run.add_argument("--aspect", choices=["9:16", "16:9", "1:1", "4:5", "source"], default="9:16")
    run.add_argument("--style", choices=["pop", "impact", "clean", "glow", "neon", "boxed"], default="pop")
    run.add_argument("--no-captions", action="store_true", help="Cut and frame without burning captions")
    run.add_argument(
        "--layout",
        choices=["auto", "fit", "fill", "split"],
        default="auto",
        help="auto = Hermes picks from the frame. fit = whole frame on blur. fill = speaker crop. split = facecam band + screen.",
    )
    _add_look_args(run)
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
    kwargs = dict(
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
        keywords=getattr(args, "keywords", "") or "",
        captions=not getattr(args, "no_captions", False),
        look=_look_from(args),
        fixes=_fixes_from(args),
        on_progress=lambda stage, pct, msg: print(f"{stage} {pct:.0%} {msg}", flush=True),
    )
    if getattr(args, "recommend", False):
        from hermesclip.recommend import recommend_for

        _info, rec = recommend_for(args.src)
        print(json.dumps({"recommend": rec.as_job()}, indent=2), flush=True)
        kwargs.update(
            max_clips=rec.max_clips,
            pacing=rec.pacing,
            style=rec.style,
            plan=rec.plan,
            layout=rec.layout,
            live_seconds=rec.live_seconds,
            min_sec=rec.min_sec,
            max_sec=rec.max_sec,
            prompt=rec.prompt or kwargs["prompt"],
            hook=rec.hook,
            mode=rec.mode,
            aspect=rec.aspect,
            captions=rec.captions,
            keywords=rec.keywords or kwargs.get("keywords") or "",
        )
    result = run_once(args.src, out_dir, **kwargs)
    print(json.dumps(result, indent=2), flush=True)
    print("done")
    for w in result.get("clips") or []:
        print(w)
    return 0


def _edit_cmd(args: argparse.Namespace) -> int:
    from hermesclip.edit import drop_file, duplicate_file, restore_file, split_file, trim_file

    src = Path(args.src).expanduser()
    op = getattr(args, "op", "trim") or "trim"
    try:
        if op == "split":
            at = args.at
            if at is None:
                print(json.dumps({"ok": False, "error": "--at is required for split"}))
                return 1
            a, b = split_file(src, float(at))
            print(json.dumps({"ok": True, "op": "split", "files": [str(a), str(b)]}))
            return 0
        if op == "duplicate":
            path = duplicate_file(src, Path(args.out).expanduser() if args.out else None)
            print(json.dumps({"ok": True, "op": "duplicate", "file": str(path)}))
            return 0
        if op == "drop":
            path = drop_file(src)
            print(json.dumps({"ok": True, "op": "drop", "file": str(path)}))
            return 0
        if op == "restore":
            path, _meta = restore_file(src)
            print(json.dumps({"ok": True, "op": "restore", "file": str(path)}))
            return 0
        if args.start is None or args.end is None:
            print(json.dumps({"ok": False, "error": "--start and --end are required for trim"}))
            return 1
        dest = Path(args.out).expanduser() if args.out else src.with_name(src.stem + "-trim" + src.suffix)
        path = trim_file(src, dest, float(args.start), float(args.end))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)[-1200:]}))
        return 1
    print(json.dumps({"ok": True, "op": "trim", "file": str(path)}))
    return 0


def _copy_cmd(args: argparse.Namespace) -> int:
    from hermesclip.copy import copy_from_job_dir, copy_pack
    from hermesclip.pipeline import job_dir, load_job

    src = Path(args.src).expanduser()
    try:
        if src.is_dir():
            pack = copy_from_job_dir(src, args.clip_title)
        elif src.name == "transcript.json" and src.is_file():
            text = json.loads(src.read_text()).get("text") or ""
            pack = copy_pack(src.parent.name, text, args.clip_title)
        else:
            job = load_job(args.src)
            if not job:
                root = job_dir(args.src)
                if root and root.is_dir():
                    pack = copy_from_job_dir(root, args.clip_title)
                else:
                    print(json.dumps({"ok": False, "error": "not a job dir or id"}))
                    return 1
            else:
                pack = copy_from_job_dir(Path(job.dir), args.clip_title)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)[-1200:]}))
        return 1
    print(json.dumps({"ok": True, **pack}, indent=2))
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
