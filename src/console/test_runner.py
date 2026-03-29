"""
TestRunner: launches pytest as a subprocess and streams results.

Runs in the same Python environment so it picks up the installed
packages and uses the correct sys.path.

Results are stored in memory indexed by run_id.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Test file paths relative to the project root
TEST_FILES = [
    "src/tests/test_entry_policy_viability.py",
    "src/tests/test_panel_viability.py",
    "src/tests/test_candidate_generator_repair.py",
    "src/tests/test_replay_validation.py",
    "src/tests/test_runtime_verification.py",
    "src/tests/test_runtime_wiring.py",
    "src/tests/test_learning_layer.py",
    "src/tests/test_validation.py",
    "src/tests/test_phase_6_1_observational.py",
    "src/tests/test_phase_6_2_structural.py",
    "src/tests/test_phase_6_3_natural_open.py",
    "src/tests/test_phase_6_4_double_bottom.py",
    "src/tests/test_phase_7_baseline.py",
    "src/tests/test_replay_manager.py",
]


@dataclass
class TestRunResult:
    run_id: str
    files: list[str]
    status: str           # "pending" | "running" | "done" | "error"
    started_at: str
    finished_at: Optional[str]
    return_code: Optional[int]
    passed: Optional[int]
    failed: Optional[int]
    errors: Optional[int]
    output_lines: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "files": self.files,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "return_code": self.return_code,
            "passed": self.passed,
            "failed": self.failed,
            "errors": self.errors,
            "output_lines": self.output_lines[-500:],  # last 500 lines
            "summary": self.summary,
        }


class TestRunner:
    """Manages pytest subprocess runs."""

    def __init__(self, project_root: str) -> None:
        self._root = Path(project_root)
        self._runs: dict[str, TestRunResult] = {}

    def list_files(self) -> list[dict]:
        """Return list of available test files with existence check."""
        result = []
        for f in TEST_FILES:
            p = self._root / f
            result.append({
                "path": f,
                "exists": p.exists(),
                "name": p.name,
            })
        return result

    async def run(self, files: Optional[list[str]] = None) -> str:
        """
        Launch pytest on the given files (or all files if None).
        Returns run_id for polling.
        """
        run_id = str(uuid.uuid4())[:8]
        selected = files or [f for f in TEST_FILES
                              if (self._root / f).exists()]

        result = TestRunResult(
            run_id=run_id,
            files=selected,
            status="pending",
            started_at=datetime.utcnow().isoformat() + "Z",
            finished_at=None,
            return_code=None,
            passed=None,
            failed=None,
            errors=None,
        )
        self._runs[run_id] = result

        asyncio.create_task(self._run_task(run_id, selected))
        return run_id

    async def _run_task(self, run_id: str, files: list[str]) -> None:
        result = self._runs[run_id]
        result.status = "running"

        cmd = [
            sys.executable, "-m", "pytest",
            "--tb=short", "-q",
            "--no-header",
        ] + files

        env = os.environ.copy()
        env["PYTHONPATH"] = str(self._root / "src")

        logger.info("TestRunner [%s]: running %d files", run_id, len(files))

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(self._root),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            lines = []
            assert proc.stdout is not None
            async for raw_line in proc.stdout:
                line = raw_line.decode("utf-8", errors="replace").rstrip()
                lines.append(line)
                result.output_lines.append(line)

            await proc.wait()
            result.return_code = proc.returncode
            result.status = "done"
            result.finished_at = datetime.utcnow().isoformat() + "Z"

            # Parse summary line
            for line in reversed(lines):
                if "passed" in line or "failed" in line or "error" in line:
                    result.summary = line.strip()
                    # Try to extract counts
                    import re
                    m = re.search(r"(\d+) passed", line)
                    if m:
                        result.passed = int(m.group(1))
                    m = re.search(r"(\d+) failed", line)
                    if m:
                        result.failed = int(m.group(1))
                    m = re.search(r"(\d+) error", line)
                    if m:
                        result.errors = int(m.group(1))
                    break

            logger.info(
                "TestRunner [%s]: done rc=%s summary=%s",
                run_id, result.return_code, result.summary,
            )
        except Exception as e:
            result.status = "error"
            result.finished_at = datetime.utcnow().isoformat() + "Z"
            result.summary = str(e)
            result.output_lines.append(f"ERROR: {e}")
            logger.error("TestRunner [%s]: error: %s", run_id, e)

    def get_result(self, run_id: str) -> Optional[dict]:
        r = self._runs.get(run_id)
        return r.to_dict() if r else None

    def list_results(self) -> list[dict]:
        return [r.to_dict() for r in self._runs.values()]


# Global instance — set by server.py
_test_runner: Optional[TestRunner] = None


def get_test_runner() -> Optional[TestRunner]:
    return _test_runner


def set_test_runner(tr: TestRunner) -> None:
    global _test_runner
    _test_runner = tr
