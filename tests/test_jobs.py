import json
import sqlite3
import time

from deepseek_worker import core, jobs


def wait_for_terminal(manager, job_id):
    for _ in range(100):
        status = manager.status(job_id)["status"]
        if status in jobs.TERMINAL_STATUSES:
            return status
        time.sleep(0.01)
    raise AssertionError("job did not finish")


def valid_result(summary="ok"):
    return {"summary": summary, "patch": "", "tests": [], "assumptions": [], "risks": [], "model": "deepseek-v4-pro", "worker": "deepseek", "changed_files": [], "patch_sha256": "0" * 64}


def test_background_job_persists_result(monkeypatch, tmp_path):
    monkeypatch.setattr(core, "generate_patch", lambda **kwargs: valid_result())
    manager = jobs.PatchJobManager(tmp_path, max_workers=1)
    submitted = manager.submit(task="change", task_name="named task", file_context="context", allowed_paths=["a.py"])
    assert wait_for_terminal(manager, submitted["job_id"]) == "completed"
    assert submitted["task_name"] == "named task"
    first = manager.result(submitted["job_id"])
    second = manager.result(submitted["job_id"])
    assert first["summary"] == second["summary"] == "ok"
    assert manager.status(submitted["job_id"])["result_read_at"] is not None


def test_result_larger_than_two_mib_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(core, "generate_patch", lambda **kwargs: valid_result("x" * (jobs.MAX_RESULT_BYTES + 1)))
    manager = jobs.PatchJobManager(tmp_path, max_workers=1)
    submitted = manager.submit(task="change", file_context="context", allowed_paths=["a.py"])
    assert wait_for_terminal(manager, submitted["job_id"]) == "failed"
    assert manager.status(submitted["job_id"])["error_code"] == "result_too_large"


def test_database_does_not_persist_task_or_context(monkeypatch, tmp_path):
    monkeypatch.setattr(core, "generate_patch", lambda **kwargs: valid_result())
    manager = jobs.PatchJobManager(tmp_path, max_workers=1)
    submitted = manager.submit(task="private full task", task_name="safe name", file_context="private context", allowed_paths=["a.py"])
    assert wait_for_terminal(manager, submitted["job_id"]) == "completed"
    dump = "\n".join(manager._connect().iterdump())
    assert "private full task" not in dump
    assert "private context" not in dump
    assert "safe name" in dump
