"""Abstract base class for all tokenizer implementations."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Literal
import logging

logger = logging.getLogger(__name__)


class TokenizerError(Exception):
    """Base exception for tokenizer layer errors."""
    def __init__(self, message: str, group_id: str, original_exception: Exception | None = None):
        self.group_id = group_id
        self.original_exception = original_exception
        super().__init__(f"[tokenizer:{group_id}] {message}")


class InitializationError(TokenizerError):
    """Raised when a tokenizer fails to initialize."""
    pass


class TokenizationError(TokenizerError):
    """Raised when token counting/encoding fails."""
    pass


class TokenizerBase(ABC):
    """Abstract base class for all tokenizer implementations.

    Subclasses must implement count_tokens(), encode(), and decode().
    The initialize() hook is called by the registry before first use.
    Constructor sets metadata only -- actual library loading happens in initialize().
    """

    def __init__(self, group_id: str, name: str, type: Literal["open", "estimated"] = "open"):
        self._group_id = group_id
        self._name = name
        self._type: Literal["open", "estimated"] = type
        self._available = False
        self._initialized = False

    @property
    def group_id(self) -> str:
        return self._group_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def type(self) -> Literal["open", "estimated"]:
        return self._type

    @property
    def available(self) -> bool:
        return self._available

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Return exact token count for the given text.
        Must return 0 for empty string.
        """
        ...

    @abstractmethod
    def encode(self, text: str) -> list[int]:
        """Encode text to a list of token IDs."""
        ...

    @abstractmethod
    def decode(self, tokens: list[int]) -> str:
        """Decode token IDs back to text."""
        ...

    def initialize(self) -> None:
        """Lazy initialization hook. Called by registry before first use.

        Subclasses override this to load the actual tokenizer engine.
        Default is a no-op for stateless implementations.
        Set self._available = True on success, leave False on failure.
        This method is idempotent -- calling it multiple times is safe.
        """
        if self._initialized:
            return
        self._initialized = True
        self._do_initialize()

    def _do_initialize(self) -> None:
        """Override point for subclasses. Called exactly once by initialize()."""
        pass
