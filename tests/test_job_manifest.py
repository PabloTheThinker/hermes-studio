"""job.json is rewritten on every progress bump while the Jobs list polls it.

Regression: Job.save() truncated job.json in place, so a list_jobs() at that instant
read "" or half the JSON, skipped the running job, and the newest job vanished from
/api/jobs. The Linux clean-machine test then read the *previous* job's "completed"
as the clip job's and found no clip files (desktop run 36857864110).
"""

import builtins
import errno
import json
import os
import stat
import sys
import threading
from pathlib import Path

import pytest

from hermes_studio import pipeline


def _job(root, job_id, title, status, created):
    return pipeline.Job(
        id=job_id,
        src="/x.mp4",
        title=title,
        status=status,
        created_at=created,
        dir=str(root / "Local files" / f"{title} [{job_id}]"),
    )


def test_running_job_never_drops_out_of_the_list_while_it_saves(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "library_root", lambda: tmp_path)
    _job(tmp_path, "aaaaaaaaaaaa", "captions", "completed", "2026-10-01T11:52:57+00:00").save()
    running = _job(tmp_path, "bbbbbbbbbbbb", "clip", "running", "2026-10-01T11:53:10+00:00")
    running.save()

    stop = threading.Event()

    def bump_forever():
        while not stop.is_set():
            running.progress = (running.progress + 0.01) % 1.0
            running.save()

    writer = threading.Thread(target=bump_forever)
    writer.start()
    try:
        seen = []
        for _ in range(3000):
            jobs = pipeline.list_jobs()
            seen.append([j.id for j in jobs])
            assert pipeline.load_job("bbbbbbbbbbbb") is not None
    finally:
        stop.set()
        writer.join()

    assert all(ids == ["bbbbbbbbbbbb", "aaaaaaaaaaaa"] for ids in seen), "the running job dropped out of list_jobs()"


def test_save_leaves_only_job_json(tmp_path):
    job = _job(tmp_path, "cccccccccccc", "one", "queued", "2026-10-01T12:00:00+00:00")
    job.save()
    job.status = "completed"
    job.save()
    folder = tmp_path / "Local files" / "one [cccccccccccc]"
    assert [p.name for p in folder.iterdir()] == ["job.json"]
    assert json.loads((folder / "job.json").read_text())["status"] == "completed"


# --- _write_atomic hardening: fsync, cleanup on every failure path, modes, concurrency ---


def _saved(tmp_path):
    job = _job(tmp_path, "dddddddddddd", "hard", "running", "2026-10-01T13:00:00+00:00")
    job.message = "old"
    job.save()
    return job, tmp_path / "Local files" / "hard [dddddddddddd]"


def _names(folder):
    return sorted(p.name for p in folder.iterdir())


def test_write_failing_midway_leaves_no_tmp_and_old_job_json_intact(tmp_path, monkeypatch):
    job, folder = _saved(tmp_path)
    before = (folder / "job.json").read_text()
    real_open = builtins.open

    class HalfWriter:
        def __init__(self, f):
            self._f = f

        def write(self, text):
            self._f.write(text[: len(text) // 2])
            self._f.flush()
            raise OSError(errno.ENOSPC, "No space left on device")

        def __getattr__(self, name):
            return getattr(self._f, name)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self._f.close()

    def fake_open(file, mode="r", *a, **k):
        f = real_open(file, mode, *a, **k)
        return HalfWriter(f) if str(file).endswith(".tmp") else f

    monkeypatch.setattr(builtins, "open", fake_open)
    job.message = "new"
    with pytest.raises(OSError) as e:
        job.save()
    assert e.value.errno == errno.ENOSPC
    monkeypatch.undo()
    assert _names(folder) == ["job.json"]
    assert (folder / "job.json").read_text() == before


def test_replace_raising_oserror_leaves_no_tmp_and_reraises(tmp_path, monkeypatch):
    job, folder = _saved(tmp_path)
    before = (folder / "job.json").read_text()

    def boom(src, dst):
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    monkeypatch.setattr(os, "replace", boom)
    job.message = "new"
    with pytest.raises(OSError) as e:
        job.save()
    assert e.value.errno == errno.EXDEV
    monkeypatch.undo()
    assert _names(folder) == ["job.json"]
    assert (folder / "job.json").read_text() == before


def test_permission_retries_are_bounded_then_clean_up_and_reraise(tmp_path, monkeypatch):
    job, folder = _saved(tmp_path)
    before = (folder / "job.json").read_text()
    calls = []
    sleeps = []

    def locked(src, dst):
        calls.append(src)
        raise PermissionError(errno.EACCES, "file in use")

    monkeypatch.setattr(os, "replace", locked)
    monkeypatch.setattr(pipeline.time, "sleep", lambda s: sleeps.append(s))
    job.message = "new"
    with pytest.raises(PermissionError):
        job.save()
    monkeypatch.undo()
    assert len(calls) == 20
    assert sum(sleeps) == pytest.approx(0.19)
    assert _names(folder) == ["job.json"]
    assert (folder / "job.json").read_text() == before


def test_only_permission_error_is_retried(tmp_path, monkeypatch):
    job, folder = _saved(tmp_path)
    calls = []

    def flaky(src, dst, _real=os.replace):
        calls.append(src)
        if len(calls) < 3:
            raise PermissionError(errno.EACCES, "file in use")
        return _real(src, dst)

    monkeypatch.setattr(os, "replace", flaky)
    monkeypatch.setattr(pipeline.time, "sleep", lambda s: None)
    job.message = "new"
    job.save()
    monkeypatch.undo()
    assert len(calls) == 3
    assert _names(folder) == ["job.json"]
    assert json.loads((folder / "job.json").read_text())["message"] == "new"


def test_fsync_happens_before_replace(tmp_path, monkeypatch):
    job, folder = _saved(tmp_path)
    events = []
    real_fsync, real_replace = os.fsync, os.replace

    def fsync(fd):
        events.append(("fsync", stat.S_ISDIR(os.fstat(fd).st_mode)))
        return real_fsync(fd)

    def replace(src, dst):
        events.append(("replace", None))
        return real_replace(src, dst)

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "replace", replace)
    job.save()
    monkeypatch.undo()
    assert events[0] == ("fsync", False), "the temp file must be fsynced first"
    assert events.index(("replace", None)) > 0
    if os.name != "nt":
        assert events[-1] == ("fsync", True), "the folder is fsynced after the rename on POSIX"


def test_each_save_uses_a_unique_hidden_tmp_name_in_the_same_folder(tmp_path, monkeypatch):
    job, folder = _saved(tmp_path)
    seen = []
    real_replace = os.replace

    def replace(src, dst):
        seen.append(Path(src))
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", replace)
    for _ in range(50):
        job.save()
    monkeypatch.undo()
    assert len(set(seen)) == 50
    assert all(p.parent == folder and p.name.startswith(".job.json.") and p.suffix == ".tmp" for p in seen)


def test_list_jobs_ignores_tmp_and_dotfile_leftovers(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "library_root", lambda: tmp_path)
    job, folder = _saved(tmp_path)
    (folder / ".job.json.123.deadbeef.tmp").write_text('{"id": "zzzzzzzzzzzz", "src"')  # half-written leftover
    (folder / ".job.json").write_text("{}")
    (folder / "job.json.tmp").write_text("not json")
    stray = tmp_path / "Local files" / "stray [eeeeeeeeeeee]"
    stray.mkdir()
    (stray / ".job.json.9.cafebabe.tmp").write_text(json.dumps({"id": "eeeeeeeeeeee", "src": "x", "title": "t"}))
    assert [j.id for j in pipeline.list_jobs()] == ["dddddddddddd"]
    assert pipeline.load_job("eeeeeeeeeeee") is None
    assert pipeline.load_job("dddddddddddd").message == "old"


def test_two_threads_saving_the_same_job(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "library_root", lambda: tmp_path)
    folder = tmp_path / "Local files" / "both [ffffffffffff]"
    errors = []
    start = threading.Barrier(3)

    def writer(tag):
        job = pipeline.Job(
            id="ffffffffffff",
            src="/x.mp4",
            title="both",
            status="running",
            created_at="2026-10-01T13:00:00+00:00",
            dir=str(folder),
        )
        start.wait()
        try:
            for i in range(400):
                job.message = f"{tag}-{i}"
                job.save()
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(t,)) for t in ("A", "B")]
    for t in threads:
        t.start()
    start.wait()
    reads = 0
    while any(t.is_alive() for t in threads):
        p = folder / "job.json"
        if p.exists():
            data = json.loads(p.read_text())  # must always parse
            tag, _, n = data["message"].partition("-")
            assert tag in ("A", "B") and n.isdigit()
            assert data["id"] == "ffffffffffff"
            reads += 1
    for t in threads:
        t.join()
    assert not errors, errors
    assert reads > 0
    final = json.loads((folder / "job.json").read_text())
    assert final["message"] in ("A-399", "B-399")
    assert _names(folder) == ["job.json"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")
def test_save_keeps_an_existing_job_json_mode(tmp_path):
    job, folder = _saved(tmp_path)
    os.chmod(folder / "job.json", 0o640)
    job.message = "new"
    job.save()
    assert stat.S_IMODE((folder / "job.json").stat().st_mode) == 0o640
    assert json.loads((folder / "job.json").read_text())["message"] == "new"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")
def test_new_job_json_gets_the_umask_default_not_0600(tmp_path):
    old = os.umask(0o022)
    try:
        job, folder = _saved(tmp_path)
        assert stat.S_IMODE((folder / "job.json").stat().st_mode) == 0o644
        job.save()
        assert stat.S_IMODE((folder / "job.json").stat().st_mode) == 0o644
    finally:
        os.umask(old)
