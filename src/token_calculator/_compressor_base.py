"""Abstract base class for all compression engines."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Literal
import logging

logger = logging.getLogger(__name__)


class CompressionError(Exception):
    """Base exception for compressor layer errors."""
    def __init__(self, message: str, strategy: str, original_exception: Exception | None = None):
        self.strategy = strategy
        self.original_exception = original_exception
        super().__init__(f"[compressor:{strategy}] {message}")


class CompressorBase(ABC):
    """Abstract base class for all compression strategies.

    Subclasses must implement compress().
    Each strategy returns a dict with compressed_text, changes, and stats.
    """

    def __init__(self, strategy: str, name: str):
        self._strategy = strategy
        self._name = name

    @property
    def strategy(self) -> str:
        return self._strategy

    @property
    def name(self) -> str:
        return self._name

    @abstractmethod
    def compress(self, text: str, level: Literal["light", "medium", "aggressive"] = "medium") -> dict:
        """Compress the given text and return result dict.

        Returns:
            {
                "compressed_text": str,
                "changes": [{"type": "rule", "rule": str, "original": str, "replaced": str}, ...],
                "stats": {"original_chars": int, "compressed_chars": int, "operations_count": int}
            }
        """
        ...
