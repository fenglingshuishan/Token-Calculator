#!/usr/bin/env python3
"""Stop the Prompt Economics Workbench server.

Finds the process listening on port 8000 (or the port saved in .server.pid)
and terminates it cleanly.

Usage:
    ./stop.py              # Stop server on port 8000
    ./stop.py --port 9000  # Stop server on custom port
"""

import os
import sys
import signal
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
DEFAULT_PORT = 8000


def _find_process_on_port(port: int) -> list[int]:
    """Return PIDs listening on the given port."""
    if sys.platform == "win32":
        import subprocess
        try:
            output = subprocess.check_output(
                ["netstat", "-ano"], text=True, timeout=5
            )
            for line in output.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.strip().split()
                    return [int(parts[-1])]
        except Exception:
            pass
    else:
        import subprocess
        try:
            output = subprocess.check_output(
                ["lsof", "-ti", f":{port}"], text=True, timeout=5
            )
            return [int(value) for value in output.split() if value.isdigit()]
        except Exception:
            pass
    return []


def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _is_workbench_process(pid: int) -> bool:
    """Do not let a stale pid file terminate an unrelated process."""
    if sys.platform == "win32":
        return True
    try:
        command = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
    except OSError:
        return False
    return "token-calculator" in command and "run.py" in command


def _kill_pid(pid: int) -> bool:
    """Kill a process by PID. Returns True on success."""
    try:
        if sys.platform == "win32":
            import subprocess
            subprocess.run(["taskkill", "//F", "//PID", str(pid)],
                           capture_output=True, timeout=10)
        else:
            os.kill(pid, signal.SIGTERM)
            for _ in range(30):
                if not _is_running(pid):
                    return True
                time.sleep(0.1)
            os.kill(pid, signal.SIGKILL)
        return True
    except Exception:
        return False


def main():
    port = DEFAULT_PORT
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--port" and i + 1 < len(args):
            port = int(args[i + 1])
            i += 1
        i += 1

    # 1. Try .server.pid file first
    pidfile = PROJECT_ROOT / ".server.pid"
    pid_from_file = None
    if pidfile.is_file():
        try:
            pid_from_file = int(pidfile.read_text().strip())
        except ValueError:
            pass

    if pid_from_file and _is_workbench_process(pid_from_file):
        if _kill_pid(pid_from_file):
            pidfile.unlink(missing_ok=True)
            print(f"Stopped server (PID {pid_from_file}).")
            return
        else:
            pidfile.unlink(missing_ok=True)

    # 2. Fall back to port scan
    pids = _find_process_on_port(port)
    for pid in pids:
        if _kill_pid(pid):
            pidfile.unlink(missing_ok=True)
            print(f"Stopped server on port {port} (PID {pid}).")
            return
        else:
            print(f"Found process PID {pid} on port {port}, but could not kill it.")
            sys.exit(1)

    print(f"No server found on port {port}.")
    pidfile.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
