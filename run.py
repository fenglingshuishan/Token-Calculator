"""Prompt Optimization Workstation — Development Entry Point.

Usage:
    python run.py              # Start on http://127.0.0.1:8000
    python run.py --debug      # Verbose logging
    python run.py --port 9000  # Custom port

If the port is occupied, a clear error is printed and the process exits
with a non-zero code.  Use start.bat to auto-kill a stale server first.
"""

import os
import sys
import signal
from pathlib import Path

# ---------------------------------------------------------------------------
# Suppress noisy framework warnings before any imports touch them.
# Must be set BEFORE importing transformers/token_calculator.
# ---------------------------------------------------------------------------
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
port = 8000
debug = os.environ.get("TOKEN_CALC_DEBUG", "0") == "1"

for i, a in enumerate(sys.argv[1:]):
    if a == "--debug":
        debug = True
    elif a == "--port":
        port = int(sys.argv[i + 2])

# ---------------------------------------------------------------------------
# App  (imported AFTER env vars are set so framework warnings are suppressed)
# ---------------------------------------------------------------------------
from token_calculator import create_app

app = create_app(static_dir=str(PROJECT_ROOT / "frontend"), debug=debug)

signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    pidfile = PROJECT_ROOT / ".server.pid"
    pidfile.write_text(str(os.getpid()))

    print(f"http://127.0.0.1:{port}  {'(debug)' if debug else ''}")

    try:
        uvicorn.run(
            app, host="127.0.0.1", port=port,
            log_level="debug" if debug else "warning",
            access_log=False,
        )
    except OSError as exc:
        print()
        print(f"ERROR: Cannot bind to port {port} — {exc}")
        print()
        print("  The port may be in use by another process.")
        print("  To kill the old process and restart, run:")
        print()
        print(f"      start.bat")
        print()
        print("  Or kill the process manually and retry.")
        print()
        sys.exit(1)
    finally:
        pidfile.unlink(missing_ok=True)
