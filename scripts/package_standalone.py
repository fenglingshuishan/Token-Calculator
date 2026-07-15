"""Create a deterministic zip around a PyInstaller executable."""
from __future__ import annotations

import argparse
import shutil
import stat
import tempfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", required=True)
    parser.add_argument("--version", default="3.0.0")
    parser.add_argument("--dist", default="dist")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    dist = root / args.dist
    executable = dist / ("token-calculator.exe" if args.platform == "windows-x64"
                         else "token-calculator")
    if not executable.is_file():
        raise SystemExit(f"PyInstaller output not found: {executable}")

    archive_name = f"token-calculator-{args.version}-{args.platform}"
    output_dir = root / "release-assets"
    output_dir.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        staging = Path(temp) / archive_name
        staging.mkdir()
        target = staging / executable.name
        shutil.copy2(executable, target)
        if args.platform != "windows-x64":
            target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        for name in ("README.md", "README.zh-CN.md", "LICENSE", "CHANGELOG.md"):
            shutil.copy2(root / name, staging / name)
        shutil.make_archive(str(output_dir / archive_name), "zip", staging.parent, staging.name)
    print(output_dir / f"{archive_name}.zip")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
