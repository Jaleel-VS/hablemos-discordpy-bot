"""Run the wcbet settlement integration tests against a throwaway Docker Postgres.

Drives Docker via subprocess (works in this sandbox even though the
`docker` *shell* command is allowlisted-off — subprocess is not). The
container is ephemeral (`--rm`) on a non-standard port so it can't clash
with anything, and is always torn down at the end.

Prereqs: the Docker daemon must be running (e.g. start OrbStack / Docker
Desktop). Usage:

    python scripts/run_pg_integration_tests.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid

IMAGE = "postgres:17-alpine"
PORT = 54329
CONTAINER = f"wcbet-pgtest-{uuid.uuid4().hex[:8]}"
DB_URL = f"postgresql://postgres@localhost:{PORT}/postgres"


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def daemon_up() -> bool:
    out = _run(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=15)
    return out.returncode == 0


def start_container() -> None:
    print(f"Pulling/starting {IMAGE} as {CONTAINER} on :{PORT} ...")
    out = _run([
        "docker", "run", "-d", "--rm",
        "--name", CONTAINER,
        "-e", "POSTGRES_HOST_AUTH_METHOD=trust",
        "-p", f"{PORT}:5432",
        IMAGE,
    ], timeout=120)
    if out.returncode != 0:
        raise RuntimeError(f"docker run failed:\n{out.stderr}")


def wait_ready(timeout_s: int = 60) -> None:
    print("Waiting for Postgres to accept connections ...")
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        out = _run(["docker", "exec", CONTAINER, "pg_isready", "-U", "postgres"], timeout=10)
        if out.returncode == 0:
            time.sleep(1)  # small grace after pg_isready
            print("Postgres is ready.")
            return
        time.sleep(1)
    raise RuntimeError("Postgres did not become ready in time")


def stop_container() -> None:
    print(f"Stopping {CONTAINER} ...")
    _run(["docker", "stop", CONTAINER], timeout=30)


def main() -> int:
    if not daemon_up():
        print(
            "Docker daemon is not running. Start OrbStack / Docker Desktop "
            "(e.g. `orb start`) and re-run.",
            file=sys.stderr,
        )
        return 2

    start_container()
    try:
        wait_ready()
        print("Running integration tests ...")
        result = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                "tests/wcbet/test_settlement_integration.py", "-v",
            ],
            env={**os.environ, "TEST_DATABASE_URL": DB_URL},
        )
        return result.returncode
    finally:
        stop_container()


if __name__ == "__main__":
    raise SystemExit(main())
