"""job.json is rewritten on every progress bump while the Jobs list polls it.

Regression: Job.save() truncated job.json in place, so a list_jobs() at that instant
read "" or half the JSON, skipped the running job, and the newest job vanished from
/api/jobs. The Linux clean-machine test then read the *previous* job's "completed"
as the clip job's and found no clip files (desktop run 36857864110).
"""

import json
import threading

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
