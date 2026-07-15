"""Stop the Token Calculator development server.

Finds the process listening on port 8000 (or the port saved in .server.pid)
and terminates it cleanly.

Usage:
    python stop.py              # Kill server on port 8000
    python stop.py --port 9000  # Kill server on custom port
"""

import os
import sys
import signal
import socket
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
DEFAULT_PORT = 8000


def _find_process_on_port(port: int) -> int | None:
    """Return PID of process listening on the given port, or None."""
    if sys.platform == "win32":
        import subprocess
        try:
            output = subprocess.check_output(
                ["netstat", "-ano"], text=True, timeout=5
            )
            for line in output.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.strip().split()
                    return int(parts[-1])
        except Exception:
            pass
    else:
        import subprocess
        try:
            output = subprocess.check_output(
                ["lsof", "-ti", f":{port}"], text=True, timeout=5
            )
            return int(output.strip())
        except Exception:
            pass
    return None


def _kill_pid(pid: int) -> bool:
    """Kill a process by PID. Returns True on success."""
    try:
        if sys.platform == "win32":
            import subprocess
            subprocess.run(["taskkill", "//F", "//PID", str(pid)],
                           capture_output=True, timeout=10)
        else:
            os.kill(pid, signal.SIGTERM)
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

    if pid_from_file:
        if _kill_pid(pid_from_file):
            pidfile.unlink(missing_ok=True)
            print(f"Stopped server (PID {pid_from_file}).")
            return
        else:
            pidfile.unlink(missing_ok=True)

    # 2. Fall back to port scan
    pid = _find_process_on_port(port)
    if pid:
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
