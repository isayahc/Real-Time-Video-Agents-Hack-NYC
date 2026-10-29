"""Verify batch failure semantics and preservation without paid cloud calls."""
from pathlib import Path
import json
import subprocess
from typing import TextIO

import pytest

from scripts import run_so101_job as job


@pytest.mark.parametrize("fail", [False, True])
def test_job_preserves_receipt_and_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                          fail: bool) -> None:
    """Failed simulation steps remain failed and retain their diagnostic output."""
    output = tmp_path / "mounted"
    output.mkdir()
    calls: list[list[str]] = []

    def execute(command: list[str], log: TextIO, timeout: float) -> None:
        """Stand in for a simulator process that can fail after logging."""
        calls.append(command)
        log.write("simulator diagnostic\n")
        assert timeout > 0
        if fail:
            raise subprocess.CalledProcessError(7, command)

    monkeypatch.setattr(job, "execute", execute)
    if fail:
        with pytest.raises(subprocess.CalledProcessError):
            job.run_job(tmp_path, tmp_path, output, tmp_path / "work")
    else:
        job.run_job(tmp_path, tmp_path, output, tmp_path / "work")
    destination, = output.iterdir()
    report = json.loads((destination / "job.json").read_text())
    assert report["status"] == ("failed" if fail else "verified_simulation")
    assert report["live_inference"] is False
    assert report["completed_steps"] == (0 if fail else 6)
    assert "simulator diagnostic" in (destination / "job.log").read_text()
    assert len(calls) == (1 if fail else 6)


def test_missing_output_fails_before_simulation(tmp_path: Path) -> None:
    """Never silently create an output mount that might be ephemeral."""
    with pytest.raises(ValueError, match="mount"):
        job.run_job(tmp_path, tmp_path, tmp_path / "missing", tmp_path / "work")
    assert not (tmp_path / "work").exists()
