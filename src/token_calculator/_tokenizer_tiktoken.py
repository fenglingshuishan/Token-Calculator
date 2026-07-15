"""Tiktoken-based tokenizer for OpenAI models (o200k_base, cl100k_base)."""
from __future__ import annotations
import hashlib
import logging
import os
import tempfile
from pathlib import Path
from token_calculator._tokenizer_base import TokenizerBase, InitializationError, TokenizationError

logger = logging.getLogger(__name__)


class TiktokenTokenizer(TokenizerBase):
    """Tokenizer for OpenAI models using the tiktoken library.

    Supports encodings: o200k_base (GPT-4o, GPT-4.1), cl100k_base (GPT-4, GPT-3.5).
    Pure Python, no network needed -- encoding tables are built into the library.
    """

    def __init__(self, group_id: str, encoding_name: str):
        super().__init__(group_id=group_id, name=f"OpenAI tiktoken ({encoding_name})", type="open")
        self._encoding_name = encoding_name
        self._encoding = None

    def _do_initialize(self) -> None:
        try:
            import tiktoken
            urls = {
                "o200k_base": "https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken",
                "cl100k_base": "https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken",
            }
            url = urls.get(self._encoding_name)
            cache_dir = os.getenv("TIKTOKEN_CACHE_DIR") or os.getenv("DATA_GYM_CACHE_DIR") or os.path.join(tempfile.gettempdir(), "data-gym-cache")
            cached = bool(url and (Path(cache_dir) / hashlib.sha1(url.encode()).hexdigest()).is_file())
            if not cached and os.getenv("TOKEN_CALC_ALLOW_DOWNLOAD") != "1":
                logger.info("Tiktoken data is not cached; returning an estimate without blocking")
                return
            self._encoding = tiktoken.get_encoding(self._encoding_name)
            self._available = True
            logger.info(f"TiktokenTokenizer {self._group_id} initialized with {self._encoding_name}")
        except ImportError:
            logger.warning(f"[tokenizer:{self._group_id}] tiktoken not installed. Install with: pip install tiktoken")
        except ValueError as e:
            logger.warning(f"[tokenizer:{self._group_id}] Unknown tiktoken encoding: {self._encoding_name} - {e}")
        except Exception as e:
            logger.warning(f"[tokenizer:{self._group_id}] Unexpected error loading tiktoken: {e}")

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        if not self._available:
            raise InitializationError(f"TiktokenTokenizer {self._group_id} not initialized", self._group_id)
        try:
            return len(self._encoding.encode(text))
        except Exception as e:
            raise TokenizationError(f"Failed to count tokens: {e}", self._group_id, e)

    def encode(self, text: str) -> list[int]:
        if not text:
            return []
        if not self._available:
            raise InitializationError(f"TiktokenTokenizer {self._group_id} not initialized", self._group_id)
        return self._encoding.encode(text)

    def decode(self, tokens: list[int]) -> str:
        if not tokens:
            return ""
        if not self._available:
            raise InitializationError(f"TiktokenTokenizer {self._group_id} not initialized", self._group_id)
        return self._encoding.decode(tokens)
