"""HuggingFace transformers-based tokenizer for Llama, Qwen, DeepSeek, GLM."""
from __future__ import annotations
import logging
from token_calculator._tokenizer_base import TokenizerBase, InitializationError, TokenizationError

logger = logging.getLogger(__name__)


class HfTokenizer(TokenizerBase):
    """Tokenizer for HuggingFace transformer models.

    Uses AutoTokenizer.from_pretrained() with use_fast=True.
    The Rust-based tokenizers library is used -- PyTorch is NOT required.
    Tokenizer files are cached in ~/.cache/huggingface/hub/ by default.
    """

    def __init__(self, group_id: str, repo_id: str):
        super().__init__(group_id=group_id, name=f"HF ({repo_id})", type="open")
        self._repo_id = repo_id
        self._tokenizer = None

    def _do_initialize(self) -> None:
        try:
            from transformers import AutoTokenizer
            # Only enable trust_remote_code for models that genuinely need custom tokenizer code.
            # Default to False for safety — executing arbitrary code from model repos is a security risk.
            _trust_remote = self._repo_id and "THUDM/glm" in self._repo_id
            self._tokenizer = AutoTokenizer.from_pretrained(
                self._repo_id,
                use_fast=True,
                trust_remote_code=_trust_remote,
            )
            self._available = True
            logger.info(f"HfTokenizer {self._group_id} loaded from {self._repo_id}")
        except ImportError:
            logger.warning(
                f"[tokenizer:{self._group_id}] transformers not installed. "
                f"Install with: pip install transformers"
            )
        except OSError as e:
            logger.warning(
                f"[tokenizer:{self._group_id}] Cannot load tokenizer from {self._repo_id}: {e}. "
                f"This may require huggingface-cli login for gated models."
            )
        except Exception as e:
            logger.warning(f"[tokenizer:{self._group_id}] Unexpected error loading {self._repo_id}: {e}")

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        if not self._available:
            raise InitializationError(f"HfTokenizer {self._group_id} not initialized", self._group_id)
        try:
            # Use encode() for best compatibility across all HF tokenizers
            # (some tokenizers like GLM's ChatGLM don't support return_length=True)
            return len(self._tokenizer.encode(text))
        except Exception as e:
            raise TokenizationError(f"Failed to count tokens: {e}", self._group_id, e)

    def encode(self, text: str) -> list[int]:
        if not text:
            return []
        if not self._available:
            raise InitializationError(f"HfTokenizer {self._group_id} not initialized", self._group_id)
        return self._tokenizer.encode(text)

    def decode(self, tokens: list[int]) -> str:
        if not tokens:
            return ""
        if not self._available:
            raise InitializationError(f"HfTokenizer {self._group_id} not initialized", self._group_id)
        return self._tokenizer.decode(tokens)
