"""The Phase 2 Q1 eval set: 20 pinned tasks; the reference solutions pass all of them, and the
checks are real (doing nothing passes only the two tasks where nothing is the right answer)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals import run  # noqa: E402
from evals.tasks import SETS, TASKS, TASKS_B  # noqa: E402


def test_twenty_pinned_tasks_with_unique_ids():
    assert len(TASKS) == 20 and len({t.id for t in TASKS}) == 20


def test_reference_solutions_score_20_of_20(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    out = run.run_reference()
    assert out["correct"] == 20, [t for t in out["tasks"] if not t["pass"]]
    assert out["steps"] == 20 and out["undo_rate"] == 0.05


def test_doing_nothing_fails_the_rest(tmp_path, monkeypatch):
    rows = []
    for task in TASKS:
        home = tmp_path / task.id
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))
        eng, proj = run._engine(home)
        try:
            rows.append(run.score(task, proj))
        finally:
            eng.close()
    assert {r["id"] for r in rows if r["pass"]} == {"t14-tighten", "t20-no-change"}


def test_set_b_reference_and_do_nothing(tmp_path, monkeypatch):
    """Set B (slip, roll, markers, close_gaps): the reference passes all six; doing nothing
    passes only the task where refusing is right."""
    monkeypatch.setenv("HOME", str(tmp_path))
    assert SETS["a"] is TASKS and len({t.id for t in TASKS_B} | {t.id for t in TASKS}) == 26
    out = run.run_reference(TASKS_B)
    assert out["correct"] == 6 and out["steps"] == 7, [t for t in out["tasks"] if not t["pass"]]
    rows = []
    for task in TASKS_B:
        home = tmp_path / task.id
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))
        eng, proj = run._engine(home)
        try:
            rows.append(run.score(task, proj))
        finally:
            eng.close()
    assert {r["id"] for r in rows if r["pass"]} == {"b05-impossible-slip"}


def test_set_flag(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert run.main(["--reference", "--set", "b"]) == 0
    assert '"total": 6' in capsys.readouterr().out
