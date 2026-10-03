"""Project store, lock, tokens and event bus (S3). docs/oplog.md has the op log itself.

A project lives in ``~/.hermes/clips/projects/<project_id>/``::

    base.json       the version-0 doc the log replays from   } the truth (D1)
    oplog.jsonl     one line per applied batch                }
    timeline.json   the doc at the log head                   } caches: never trusted on their
    snapshots/      v000050.json, v000100.json, ...           } own, never an error (D28)
    exports/        .otio files from export_otio
    cache/
    .lock           JSON {pid, port, started_at, engine_version, attach_token_sha256}, held
                    with an OS file lock for as long as the engine runs (D5)
    .attach         the raw mcp:stdio token, mode 0600 (D14)

One engine owns each project (:class:`Engine`). It is the only writer. With the app closed,
:class:`ClosedProject` serves reads from the files, opened read-only, and refuses every write
with ``engine_offline`` (D28(a)).
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import hashlib
import json
import os
import queue
import re
import secrets
import sys
import threading
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any

from hermes_studio import __version__
from hermes_studio import oplog as O
from hermes_studio import timeline as T
from hermes_studio.api import EXIT, HermesStudioError

SNAPSHOT_EVERY = 50
EVENT_QUEUE_MAX = 1024
LOG_HINT = "The project log is damaged; restore the project folder from a backup."
OFFLINE_HINT = "Open Hermes Studio: writes and exports need the app running. Reads work with it closed."
LOCKED_HINT = "Project is open in Hermes Studio; `hermes-studio mcp` attaches to it."
SEQ_RE = re.compile(r"\A(0|[1-9][0-9]*)\Z")  # ASCII digits only (D11, D26)

# --------------------------------------------------------------------------- errors

_EXIT_AS = {
    "failed": "failed",
    "not_found": "not_found",
    "invalid_op": "bad_input",
    "schema_mismatch": "bad_input",
    "invalid_doc": "bad_input",
    "engine_offline": "failed",
    "permission_denied": "failed",
    "needs_approval": "failed",  # S8: not final; the call is parked
}


class ToolError(HermesStudioError):
    """A tool-level refusal with one of Wire's codes (``failed``, ``schema_mismatch``,
    ``invalid_doc``, ``engine_offline``, ``permission_denied``, ``not_found``) and extra fields."""

    def __init__(self, code: str, message: str, *, hint: str = "", **extra: Any) -> None:
        super().__init__(message, code=_EXIT_AS[code], hint=hint)
        self.code = code
        self.extra = extra

    @property
    def exit_code(self) -> int:
        return EXIT[_EXIT_AS[self.code]]

    def as_dict(self) -> dict:
        d = super().as_dict()
        d.update(self.extra)
        return d


def doc_error(doc: Any) -> ToolError | None:
    """``schema_mismatch`` or ``invalid_doc`` for a doc that doesn't validate (stored hash
    included), with ``rule``/``path``/``id?``/``problems`` verbatim from ``validate()``; None if valid."""
    found = T.validate(doc)
    if not found:
        return None
    first = found[0]
    if first["rule"] == "bad_schema":
        got = doc.get("schema_version") if isinstance(doc, dict) else None
        return ToolError(
            "schema_mismatch",
            f"schema_version must be {T.SCHEMA_VERSION!r}",
            rule="bad_schema",
            path="/schema_version",
            expected=T.SCHEMA_VERSION,
            got=got,
        )
    te = T.TimelineError(found)
    extra: dict[str, Any] = {"rule": te.rule, "path": te.path}
    if te.id is not None:
        extra["id"] = te.id
    extra["problems"] = te.problems
    return ToolError("invalid_doc", te.message, hint=te.hint, **extra)


def log_error(n: int, reason: str) -> ToolError:
    """D28(b): a damaged ``oplog.jsonl`` line. No rule, no hash."""
    return ToolError("failed", f"oplog line {n}: {reason}", seq=n, hint=LOG_HINT)


def not_found(project_id: str) -> O.OplogError:
    """The engine's own not_found body for a project that isn't here (oplog.py _check_project_id)."""
    return O.OplogError("not_found", f"no project {project_id!r} here", rule="not_found", path="/project_id", id=project_id)


def offline() -> ToolError:
    return ToolError("engine_offline", "Hermes Studio isn't running, so this project is read-only.", hint=OFFLINE_HINT)


# --------------------------------------------------------------------------- paths


def projects_root() -> Path:
    return Path.home() / ".hermes" / "clips" / "projects"


def project_dir(project_id: str) -> Path | None:
    """The folder for a well-formed id (``ID_RE`` keeps it a single safe path segment)."""
    if not (isinstance(project_id, str) and T.ID_RE.fullmatch(project_id)) or project_id in (".", ".."):
        return None
    return projects_root() / project_id


def _canon_file(doc: dict) -> bytes:
    return (json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def _fsync_dir(d: Path) -> None:
    if os.name == "nt":
        return
    fd = os.open(str(d), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_atomic(path: Path, data: bytes, mode: int = 0o600) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    _fsync_dir(path.parent)


def _log(msg: str) -> None:
    print(f"hermes-studio engine: {msg}", file=sys.stderr, flush=True)


def _seconds(ticks: int) -> float:
    return float(Fraction(ticks, T.TICK_RATE))


# --------------------------------------------------------------------------- reading the files


def read_base(d: Path) -> dict:
    """``base.json``, validated before any Oplog is built (D28(b), §11 row E)."""
    try:
        with open(d / "base.json", "rb") as f:
            raw = f.read()
        doc = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, RecursionError) as e:
        raise ToolError("failed", f"base.json can't be read: {type(e).__name__}", hint=LOG_HINT) from None
    err = doc_error(doc)
    if err is not None:
        raise err
    if "hash" not in doc:  # O2 (Ada 9:02 PM): a stored base must carry its hash, as a stale one fails
        te = T.TimelineError([{"rule": "hash_mismatch", "path": "/hash", "message": "base.json has no stored hash"}])
        raise ToolError("invalid_doc", te.message, hint=te.hint, rule=te.rule, path=te.path, problems=te.problems)
    return doc


@dataclass
class ParsedLog:
    lines: list[dict]  # every complete line, in order
    good_end: int  # byte offset just past the last complete line's '\n' (or its end)
    torn: bool  # the last line has no '\n' and isn't valid JSON
    missing_newline: bool  # the last line is valid JSON with no '\n'


def parse_log(raw: bytes, base_version: int) -> ParsedLog:
    """Parse every line before anything trusts the log (D28(a) step 2): JSON, the line shape
    (``_check_line``) and ``seq``/``base_version`` continuity. A torn final line is reported,
    never raised; any other bad line raises ``failed`` naming it."""
    lines: list[dict] = []
    pos, n, version = 0, 0, base_version
    torn = missing_nl = False
    good_end = 0
    while pos < len(raw):
        nl = raw.find(b"\n", pos)
        last = nl < 0
        chunk = raw[pos:] if last else raw[pos:nl]
        end = len(raw) if last else nl + 1
        n += 1
        pos = end
        if not chunk.strip():
            if not last:
                good_end = end
            continue
        try:
            e = json.loads(chunk.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError):
            if last:
                torn = True
                break
            raise log_error(n, "not valid JSON") from None
        seq = e.get("seq") if isinstance(e, dict) and O._int_arg(e.get("seq")) else n
        try:
            O._check_line(e)
        except ValueError:
            raise log_error(seq, "not an oplog line") from None
        if e["seq"] != len(lines) + 1 or e["base_version"] != version:
            raise log_error(seq, "out of sequence")
        lines.append(e)
        version = e["new_version"]
        good_end = end
        missing_nl = last
    return ParsedLog(lines, good_end, torn, missing_nl)


def _replay_from(doc: dict, lines: list[dict]) -> dict:
    """The doc after ``lines`` (internal ops). Each line is checked exactly as ``Oplog.load``
    checks it: the replayed ``hash``, ``new_version`` and ``inverse`` must equal the stored ones
    (F1), so a bad line is named by its own ``seq``."""
    log = O.Oplog(doc)
    for e in lines:
        try:
            new, _, inverse = log._run(e["ops"], internal=True)
        except (ValueError, HermesStudioError):
            raise log_error(e["seq"], "replay does not reproduce the entry") from None
        if new["hash"] != e["hash"] or new["version"] != e["new_version"] or inverse != e["inverse"]:
            raise log_error(e["seq"], "replay does not reproduce the entry")
        log._entries.append(e)
        log._retire(new)
        log._doc = new
    return log.doc


def _read_json(path: Path) -> Any:
    try:
        with open(path, "rb") as f:
            return json.loads(f.read().decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, RecursionError):
        return None


def doc_at_head(d: Path, base: dict, lines: list[dict]) -> dict:
    """The doc at the log head, read-only (D28(a)): a full replay from ``base.json`` that checks
    every line as ``Oplog.load`` does (F1, Ada 9:02 PM). ``timeline.json`` and snapshots are
    caches for the open engine; a closed read never trusts them, so a tampered middle line gives
    the same ``failed`` body open or closed."""
    del d
    base_doc, _ = T.stamp_hash(base)
    return _replay_from(base_doc, lines)


# --------------------------------------------------------------------------- OS file lock


# Windows byte-range locks are mandatory: a locked byte can't be read by anyone else. The lock
# byte sits far past the JSON body, so other processes can still read .lock (the D6 message
# and the stdio proxy's attach both read it while the engine holds the lock).
LOCK_BYTE = 1 << 30


def _try_lock(fd: int, *, exclusive: bool) -> bool:
    if os.name == "nt":  # Windows: one byte at LOCK_BYTE (msvcrt has no shared lock)
        import msvcrt

        try:
            os.lseek(fd, LOCK_BYTE, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK if exclusive else msvcrt.LK_NBRLCK, 1)
            return True
        except OSError:
            return False
    import fcntl

    try:
        fcntl.flock(fd, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock(fd: int) -> None:
    if os.name == "nt":
        import msvcrt

        with contextlib.suppress(OSError):
            os.lseek(fd, LOCK_BYTE, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(fd, fcntl.LOCK_UN)


def engine_holding(d: Path) -> dict | None:
    """The ``.lock`` contents when a running engine holds the project's OS lock, else None.
    Opens ``.lock`` read-only; never creates or writes anything."""
    try:
        fd = os.open(str(d / ".lock"), os.O_RDONLY)
    except OSError:
        return None
    try:
        if _try_lock(fd, exclusive=False):
            _unlock(fd)
            return None
        info = _read_json(d / ".lock")
        return info if isinstance(info, dict) else {}
    finally:
        os.close(fd)


# --------------------------------------------------------------------------- tokens (D13)

SCOPES = frozenset({"read", "write", "render"})


@dataclass(frozen=True)
class Token:
    kind: str  # "ui", "acp:hermes", "mcp:<name>" or "control"
    scopes: frozenset
    session: O.Session | None  # None for the control token: it is not an actor


class Tokens:
    """Per-launch random 256-bit bearer tokens, held in memory only (by their sha256)."""

    def __init__(self) -> None:
        self._by_hash: dict[str, Token] = {}
        self._lock = threading.Lock()

    def mint(self, kind: str, *, scopes: frozenset | set = SCOPES, user: str = "user", plan: O.PlanContext | None = None) -> str:
        if kind == "ui":
            session = O.Session(O.Actor("human", user))
        elif kind == "acp:hermes":
            session = O.Session(O.Actor("agent", "hermes"), plan if plan is not None else O.PlanContext())
        elif kind.startswith("mcp:"):
            session = O.Session(O.Actor("agent", kind[4:]))
        elif kind == "control":
            session = None
        else:
            raise ValueError(f"unknown token kind {kind!r}")
        return self.adopt(kind, secrets.token_hex(32), scopes=scopes, session=session)

    def adopt(self, kind: str, raw: str, *, scopes: frozenset | set = SCOPES, session: O.Session | None = None) -> str:
        """Register a token made elsewhere (the desktop app makes the ``ui`` token and hands it to
        the engine and the Edit page in memory, S3 §13.3). It must be 64 hex characters."""
        if not (isinstance(raw, str) and re.fullmatch(r"[0-9a-f]{64}", raw)):
            raise ValueError("a token is 64 lowercase hex characters")
        if session is None and kind == "ui":
            session = O.Session(O.Actor("human", "user"))
        with self._lock:
            self._by_hash[_sha(raw)] = Token(kind, frozenset(scopes) & SCOPES, session)
        return raw

    def resolve(self, raw: str | None) -> Token | None:
        if not raw:
            return None
        with self._lock:
            return self._by_hash.get(_sha(raw))


def _sha(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8", "surrogatepass")).hexdigest()


# --------------------------------------------------------------------------- event bus (D9-D11)


class Subscriber:
    """One SSE client: a bounded queue. On overflow it is dropped and must reconnect."""

    def __init__(self) -> None:
        self.q: queue.Queue = queue.Queue(maxsize=EVENT_QUEUE_MAX)
        self.dropped = threading.Event()

    def put(self, event: dict) -> bool:
        try:
            self.q.put_nowait(event)
            return True
        except queue.Full:
            self.dropped.set()
            return False


def event_of(project_id: str, entry: dict) -> dict:
    """``op.applied`` (``undoes`` null) or ``op.undone`` (undo and redo), with the diff record."""
    return {"type": "op.applied" if entry["undoes"] is None else "op.undone", "project_id": project_id, **O._diff_record(entry)}


# --------------------------------------------------------------------------- the engine side


def _iso_now() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class Project:
    """A project the engine owns: its Oplog, its mutex (D3) and its subscribers."""

    def __init__(self, engine: Engine, project_id: str, d: Path, lock_fd: int) -> None:
        self.engine = engine
        self.id = project_id
        self.dir = d
        self.lock_fd = lock_fd
        self.mutex = threading.RLock()  # re-entrant: the S8 gate and S4/S6 notify run under it
        self.log: O.Oplog | None = None
        self.broken: HermesStudioError | None = None  # a damaged store: every tool gets this body
        self.subscribers: list[Subscriber] = []
        self._mode: str | None = None

    # ---- open (D2)

    def load(self) -> None:
        try:
            base = read_base(self.dir)
            path = self.dir / "oplog.jsonl"
            raw = path.read_bytes() if path.exists() else b""
            parsed = parse_log(raw, base["version"])
            if parsed.torn:
                with open(path, "r+b") as f:
                    f.truncate(parsed.good_end)
                    f.flush()
                    os.fsync(f.fileno())
                _log(f"{self.id}: truncated a torn final line in oplog.jsonl at byte {parsed.good_end}")
            elif parsed.missing_newline:
                with open(path, "ab") as f:
                    f.write(b"\n")
                    f.flush()
                    os.fsync(f.fileno())
                _log(f"{self.id}: added the missing final newline to oplog.jsonl")
            if not path.exists():
                path.touch(mode=0o600)
            try:
                self.log = O.Oplog.load(base, path)
            except (ValueError, HermesStudioError) as e:
                # name the line: _replay_from checks each line as load does (F1), so it raises at
                # the bad line's seq. If it somehow doesn't, use the seq load named, never the last line's.
                _replay_from(T.stamp_hash(base)[0], parsed.lines)
                m = re.match(r"oplog line ([0-9]+): (.*)", str(getattr(e, "message", e)))
                if m is None:
                    raise ToolError("failed", "oplog.jsonl can't be replayed", hint=LOG_HINT) from None
                raise log_error(int(m.group(1)), m.group(2)) from None
            self._write_cache(self.log.doc)
        except HermesStudioError as e:
            self.broken = e
            _log(f"{self.id}: not opened: {e.message}")

    def _write_cache(self, doc: dict) -> None:
        """timeline.json (tmp + replace + dir fsync) unless it already holds exactly this doc."""
        data = _canon_file(doc)
        p = self.dir / "timeline.json"
        try:
            if p.exists() and p.read_bytes() == data:
                return
            _write_atomic(p, data)
        except OSError as e:  # a cache: the log is already durable
            _log(f"{self.id}: timeline.json not written: {e}")

    def _write_snapshot(self, doc: dict) -> None:
        try:
            (self.dir / "snapshots").mkdir(exist_ok=True)
            _write_atomic(self.dir / "snapshots" / f"v{doc['version']:06d}.json", _canon_file(doc))
        except OSError as e:
            _log(f"{self.id}: snapshot not written: {e}")

    # ---- reads and writes (all under the mutex)

    def oplog(self) -> O.Oplog:
        if self.broken is not None:
            raise self.broken
        assert self.log is not None
        return self.log

    def write(self, session: O.Session, tool: str, args: Any) -> dict:
        with self.mutex:
            return self.write_locked(session, tool, args)

    @property
    def mode(self) -> str:
        """S8: ask | propose | auto (``mode.json``; Propose when unset)."""
        if self._mode is None:
            from hermes_studio import gate

            self._mode = gate.mode_of(self.dir)
        return self._mode

    def write_locked(self, session: O.Session, tool: str, args: Any, *, gated: bool = True, after: dict | None = None) -> dict:
        log = self.oplog()
        if gated:
            from hermes_studio import gate

            held = gate.gate(self, session, tool, args, after=after)
            if held is not None:  # a parked call the person skipped: the non-error 'skipped' status
                rec = held["skipped"]
                return {"ok": True, "status": "skipped", "pending_id": rec["pending_id"], "summary": rec["summary"]}
        before = len(log._entries)
        res = log.call(session, tool, args)
        if len(log._entries) > before:  # a new entry (a cached retry adds none and emits nothing)
            entry = log._entries[-1]
            doc = log.doc
            self._write_cache(doc)
            if doc["version"] % SNAPSHOT_EVERY == 0:
                self._write_snapshot(doc)
            self._publish(event_of(self.id, entry))
        return res

    def keep_locked(self, session: O.Session, args: dict, body: dict) -> dict:
        """Phase 2 drafts: ``Oplog.call(..., "keep_body")`` with the same commit side effects as a write
        (cache, snapshot, ``op.applied``). A person's act, so the mode gate doesn't apply."""
        log = self.oplog()
        before = len(log._entries)
        res = log.call(session, "keep_body", {**args, "body": body})
        if len(log._entries) > before:
            doc = log.doc
            self._write_cache(doc)
            if doc["version"] % SNAPSHOT_EVERY == 0:
                self._write_snapshot(doc)
            self._publish(event_of(self.id, log._entries[-1]))
        return res

    def _publish(self, event: dict) -> None:
        keep = []
        for s in self.subscribers:
            if s.put(event):
                keep.append(s)
        self.subscribers = keep
        for fn in self.engine.listeners_now():
            with contextlib.suppress(Exception):
                fn(event)

    def notify(self, event: dict) -> None:
        """A transient event for this project's SSE clients only (S4 ``media.*``): no ``seq``, so
        it is never replayed, and /mcp listeners (which follow log entries) don't hear it."""
        with self.mutex:
            keep = [s for s in self.subscribers if s.put(event)]
            self.subscribers = keep

    def subscribe(self, last_id: int | None) -> tuple[Subscriber, list[dict], int | None]:
        """Register a client; return (it, the events after ``last_id`` to replay first, and the
        head seq when ``last_id`` is above the head, for ``stream.reset``)."""
        with self.mutex:
            log = self.oplog()
            sub = Subscriber()
            head = len(log._entries)
            reset = None
            replay: list[dict] = []
            if last_id is not None:
                if last_id > head:
                    reset = head
                else:
                    replay = [event_of(self.id, e) for e in log._entries[last_id:]]
            self.subscribers.append(sub)
            return sub, replay, reset

    def unsubscribe(self, sub: Subscriber) -> None:
        with self.mutex:
            self.subscribers = [s for s in self.subscribers if s is not sub]

    def status(self) -> dict:
        with self.mutex:
            head = self.oplog().head()
            return {**head, "engine": self.engine.info(), "mode": self.mode}

    def export_otio(self) -> dict:
        with self.mutex:
            doc = self.oplog().doc
        out = self.dir / "exports"
        out.mkdir(exist_ok=True)
        path = out / f"{self.id}-v{doc['version']:06d}.otio"
        T.write_otio(doc, str(path))
        with contextlib.suppress(OSError):
            os.chmod(path, 0o600)  # project files are owner-only (Ada, 8:29 PM)
        return {"path": str(path), "timeline_hash": doc["hash"]}

    def close(self) -> None:
        with contextlib.suppress(OSError):
            (self.dir / ".attach").unlink()
        with contextlib.suppress(OSError):
            _unlock(self.lock_fd)
            os.close(self.lock_fd)


@dataclass
class Engine:
    """The running app's engine: it owns every project it opened (one OS lock each)."""

    port: int = 0
    tokens: Tokens = field(default_factory=Tokens)
    started_at: str = field(default_factory=_iso_now)
    projects: dict[str, Project] = field(default_factory=dict)
    attach_token: str = ""
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _opening: dict[str, threading.Lock] = field(default_factory=dict)  # one per project being opened
    # callables(event) that hear every project, including ones opened later (GET /mcp, D12)
    listeners: list[Any] = field(default_factory=list)
    _media: Any = None
    ui_token_given: bool = False  # the desktop app supplied the ui token (nothing to print)
    _renders: Any = None

    def __post_init__(self) -> None:
        if not self.attach_token:
            self.attach_token = self.tokens.mint("mcp:stdio")

    def info(self) -> dict:
        return {"pid": os.getpid(), "port": self.port, "started_at": self.started_at}

    @property
    def renders(self) -> Any:
        """The S6 render worker, started on first use."""
        with self._lock:
            if self._renders is None:
                from hermes_studio.render_jobs import RenderJobs

                self._renders = RenderJobs()
            return self._renders

    @property
    def media(self) -> Any:
        """The S4 media worker pool, started on first use."""
        with self._lock:
            if self._media is None:
                from hermes_studio.media_jobs import MediaJobs

                self._media = MediaJobs()
            return self._media

    def listen(self, fn: Any) -> None:
        with self._lock:
            self.listeners.append(fn)

    def unlisten(self, fn: Any) -> None:
        with self._lock:
            self.listeners = [f for f in self.listeners if f is not fn]

    def listeners_now(self) -> list[Any]:
        with self._lock:
            return list(self.listeners)

    def open_all(self) -> None:
        """Open every project folder at startup (a project another engine holds is an error)."""
        root = projects_root()
        if not root.is_dir():
            return
        for name in sorted(os.listdir(root)):
            if project_dir(name) is not None and (root / name / "base.json").is_file():
                self.open(name)

    def open(self, project_id: str) -> Project:
        """Take the project's OS lock and load it. A second engine gets ``failed`` (D6). The load
        (a full replay of the log, long for a long edit) holds only this project's opening lock,
        never the engine's: other projects open and answer meanwhile."""
        with self._lock:
            if project_id in self.projects:
                return self.projects[project_id]
            gate = self._opening.setdefault(project_id, threading.Lock())
        with gate:
            if project_id in self.projects:  # opened while we waited for the gate
                return self.projects[project_id]
            p = self._open_locked(project_id)
            with self._lock:
                self.projects[project_id] = p
                self._opening.pop(project_id, None)
            return p

    def _open_locked(self, project_id: str) -> Project:
        """The OS lock, the lock file and the log load, under the project's opening lock only."""
        d = project_dir(project_id)
        if d is None or not (d / "base.json").is_file():
            raise not_found(project_id)
        fd = os.open(str(d / ".lock"), os.O_RDWR | os.O_CREAT, 0o600)
        if not _try_lock(fd, exclusive=True):
            os.close(fd)
            held = _read_json(d / ".lock") or {}
            raise HermesStudioError(
                f"Project {project_id} is open in another Hermes Studio engine "
                f"(pid {held.get('pid')}, port {held.get('port')}, since {held.get('started_at')}).",
                code="failed",
                hint=LOCKED_HINT,
            )
        body = json.dumps(
            {**self.info(), "engine_version": __version__, "attach_token_sha256": _sha(self.attach_token)},
            sort_keys=True,
        ).encode("ascii")
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, body)
        os.fsync(fd)
        _write_atomic(d / ".attach", self.attach_token.encode("ascii"), mode=0o600)
        with contextlib.suppress(OSError):
            os.chmod(d / ".attach", 0o600)
        p = Project(self, project_id, d, fd)
        p.load()
        return p

    def get(self, project_id: Any) -> Project:
        if isinstance(project_id, str) and project_id in self.projects:
            return self.projects[project_id]
        if not isinstance(project_id, str):
            raise O.Oplog.precheck("get_hash", {"project_id": project_id})
        return self.open(project_id)

    def close(self) -> None:
        with self._lock:
            for p in self.projects.values():
                if self._media is not None:
                    self._media.cancel_project(p.id)  # a running ffmpeg is killed; its status reads cancelled
                if self._renders is not None:
                    self._renders.cancel_project(p.id)
                p.close()
            self.projects.clear()


# --------------------------------------------------------------------------- the closed app


class ClosedProject:
    """Reads with the app closed (D28(a)): files opened read-only, nothing ever written."""

    def __init__(self, project_id: str) -> None:
        d = project_dir(project_id)
        if d is None or not os.path.isfile(d / "base.json"):
            raise not_found(project_id)
        self.id = project_id
        self.dir = d
        base = read_base(d)
        try:
            with open(d / "oplog.jsonl", "rb") as f:
                raw = f.read()
        except FileNotFoundError:
            raw = b""
        except OSError as e:
            raise ToolError("failed", f"oplog.jsonl can't be read: {type(e).__name__}", hint=LOG_HINT) from None
        parsed = parse_log(raw, base["version"])
        doc = doc_at_head(d, base, parsed.lines)
        log = O.Oplog(base)
        log._entries = parsed.lines
        log._doc = doc
        self.log = log

    def oplog(self) -> O.Oplog:
        return self.log

    def status(self) -> dict:
        held = engine_holding(self.dir)
        engine = None if held is None else {k: held.get(k) for k in ("pid", "port", "started_at")}
        from hermes_studio import gate

        return {**self.log.head(), "engine": engine, "mode": gate.mode_of(self.dir)}


def list_markers(doc: dict) -> dict:
    marks = sorted(doc["markers"], key=lambda m: (m["at"], m["id"]))
    return {
        "tick_rate": T.TICK_RATE,
        "markers": [{"id": m["id"], "at": {"ticks": m["at"], "seconds": _seconds(m["at"])}, "label": m["label"]} for m in marks],
    }


PRESETS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080), "4:5": (1080, 1350)}


def new_project(engine: Engine, args: Any) -> dict:
    """``project_new {shape?: 9:16 | 16:9 | 1:1 | 4:5, fps?: 24 | 25 | 30 | 50 | 60}``: an empty
    timeline with an engine-picked id (``p-<hex>``), opened at once. Returns its status."""
    if not isinstance(args, dict):
        raise O.OplogError("invalid_op", "arguments must be an object", rule="bad_arg", path="")
    for k in sorted(args, key=repr):
        if k not in ("shape", "fps"):
            raise O.OplogError("invalid_op", f"unknown argument '{k}'", rule="unknown_arg", path=f"/{k}")
    shape = args.get("shape", "9:16")
    if shape not in PRESETS:
        raise O.OplogError("invalid_op", "shape is one of " + ", ".join(PRESETS), rule="bad_arg", path="/shape")
    fps = args.get("fps", 30)
    if not O._int_arg(fps) or fps not in (24, 25, 30, 50, 60):
        raise O.OplogError("invalid_op", "fps is 24, 25, 30, 50 or 60", rule="bad_arg", path="/fps")
    pid = "p-" + secrets.token_hex(4)
    doc = T.new_timeline(pid)
    doc["size"], doc["fps"] = list(PRESETS[shape]), [fps, 1]
    create_project(doc)
    return engine.get(pid).status()


def _modified(d: Path) -> float:
    """When the project last changed (its log or base), in seconds since the epoch."""
    times = []
    for f in ("oplog.jsonl", "base.json"):
        try:
            times.append((d / f).stat().st_mtime)
        except OSError:
            pass
    return round(max(times, default=0.0), 3)


def list_projects(engine: Engine | None) -> dict:
    """Every project folder with a ``base.json``: its status (open in this engine) or a closed read,
    with ``modified`` (when its log or base last changed, epoch seconds), in name order."""
    out = []
    root = projects_root()
    try:
        names = sorted(os.listdir(root))
    except OSError:
        names = []
    for name in names:
        if not (T.ID_RE.fullmatch(name) and name not in (".", "..") and (root / name / "base.json").is_file()):
            continue
        try:
            proj = engine.get(name) if engine is not None else ClosedProject(name)
            st = proj.status()
            doc = proj.oplog().doc if engine is None else None
            if doc is None:
                with proj.mutex:
                    doc = proj.oplog().doc
            out.append(
                {
                    **st,
                    "size": doc["size"],
                    "fps": doc["fps"],
                    "media": len(doc["media"]),
                    "items": sum(len(t["items"]) for t in doc["tracks"]),
                    "end": max((e for _, e in T.resolve(doc).values()), default=0),
                    "modified": _modified(root / name),
                }
            )
        except HermesStudioError as e:
            out.append({"project_id": name, "error": e.as_dict()})
    return {"projects": out}


def create_project(base: dict) -> Path:
    """Write a new project folder holding ``base`` (a valid version-0 doc) and an empty log.
    For tests and tooling: no tool or route creates projects in S3."""
    err = doc_error(T.stamp_hash(base)[0])
    if err is not None:
        raise err
    d = project_dir(base["id"])
    if d is None:
        raise ValueError("bad project id")
    d.mkdir(parents=True, exist_ok=False)
    for sub in ("snapshots", "exports", "cache"):
        (d / sub).mkdir()
    _write_atomic(d / "base.json", _canon_file(T.stamp_hash(base)[0]))
    (d / "oplog.jsonl").touch(mode=0o600)
    return d
