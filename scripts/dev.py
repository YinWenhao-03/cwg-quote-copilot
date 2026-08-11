from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
processes: list[subprocess.Popen[str]] = []


def stop_all(*_: object) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()
    for process in processes:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
    raise SystemExit(0)


def main() -> None:
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    commands = [
        (["uv", "run", "--project", "backend", "uvicorn", "app.main:app", "--reload", "--port", "8000"], ROOT),
        (["pnpm", "--dir", "frontend", "dev"], ROOT),
    ]
    signal.signal(signal.SIGINT, stop_all)
    signal.signal(signal.SIGTERM, stop_all)
    for command, cwd in commands:
        processes.append(subprocess.Popen(command, cwd=cwd, env=env, text=True))
    exit_code = processes[-1].wait()
    stop_all()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
