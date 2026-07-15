# PyInstaller recipe used by the release workflow.
import hashlib
import tempfile
from pathlib import Path

ROOT = Path(SPECPATH)
TIKTOKEN_CACHE = Path(tempfile.gettempdir()) / "data-gym-cache"
TIKTOKEN_URLS = (
    "https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken",
    "https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken",
)
tokenizer_tables = []
for url in TIKTOKEN_URLS:
    table = TIKTOKEN_CACHE / hashlib.sha1(url.encode()).hexdigest()
    if not table.is_file():
        raise SystemExit(
            f"Missing {table}. Prime both tiktoken encodings before running PyInstaller."
        )
    tokenizer_tables.append((str(table), "tiktoken_cache"))

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=[(str(ROOT / "frontend"), "frontend"), *tokenizer_tables],
    hiddenimports=["tiktoken_ext.openai_public"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["transformers", "torch", "tensorflow", "sentencepiece"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="token-calculator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
