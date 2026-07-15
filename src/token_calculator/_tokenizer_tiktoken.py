"""Tiktoken-based tokenizer for OpenAI models (o200k_base, cl100k_base)."""
from __future__ import annotations
import logging
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
