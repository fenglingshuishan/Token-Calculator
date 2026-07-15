"""Installed command-line entry point for the archived workbench."""
from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path


def _frontend_dir() -> Path:
    """Locate frontend assets in a source tree, wheel install, or PyInstaller bundle."""
    candidates = []
    if getattr(sys, "_MEIPASS", None):
        candidates.append(Path(sys._MEIPASS) / "frontend")
    candidates.extend([
        Path(__file__).resolve().parents[2] / "frontend",
        Path(sys.prefix) / "share" / "token-calculator" / "frontend",
        Path(__file__).resolve().parent / "frontend",
    ])
    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate
    searched = "\n".join(f"  - {path}" for path in candidates)
    raise RuntimeError(f"Frontend assets were not found. Searched:\n{searched}")


def _configure_bundled_tokenizer_cache() -> None:
    """Use immutable tokenizer tables embedded in a standalone executable."""
    bundle_root = getattr(sys, "_MEIPASS", None)
    if not bundle_root:
        return
    cache = Path(bundle_root) / "tiktoken_cache"
    if cache.is_dir():
        os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(cache))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="token-calculator",
        description="Archived Prompt Economics Workbench",
    )
    parser.add_argument("--host", default=os.getenv("APP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("APP_PORT", "8000")))
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--version", action="store_true", help="Print the version and exit")
    return parser


def _port_available(host: str, port: int) -> bool:
    with socket.socket() as sock:
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.version:
        from token_calculator import __version__
        print(__version__)
        return 0

    _configure_bundled_tokenizer_cache()

    if not _port_available(args.host, args.port):
        print(f"Port {args.port} is already in use.", file=sys.stderr)
        print(f"Open http://127.0.0.1:{args.port} if the workbench is already running.",
              file=sys.stderr)
        return 2

    import uvicorn
    from token_calculator import create_app

    frontend = _frontend_dir()
    url = f"http://127.0.0.1:{args.port}"
    app = create_app(static_dir=str(frontend), debug=args.debug)
    print(f"Prompt Economics Workbench: {url}")
    print("Archived reference release 3.0.0. Press Ctrl+C to stop.")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="debug" if args.debug else "warning",
        lifespan="off",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
