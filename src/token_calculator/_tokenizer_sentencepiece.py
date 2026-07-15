"""SentencePiece-based tokenizer for Google Gemma models."""
from __future__ import annotations
import os
import logging
from token_calculator._tokenizer_base import TokenizerBase, InitializationError, TokenizationError

logger = logging.getLogger(__name__)


class SentencePieceTokenizer(TokenizerBase):
    """Tokenizer for SentencePiece-based models (Google Gemma).

    Requires a .model file. Resolution order:
    1. Explicit model_path (if provided)
    2. Project models/{group_id}/tokenizer.model
    3. Auto-download from HuggingFace Hub (if hf_repo_id configured)
    """

    def __init__(self, group_id: str, model_path: str | None = None,
                 hf_repo_id: str | None = None, hf_filename: str = "tokenizer.model"):
        super().__init__(group_id=group_id, name=f"SPM ({group_id})", type="open")
        self._model_path = model_path
        self._hf_repo_id = hf_repo_id
        self._hf_filename = hf_filename
        self._processor = None

    def _do_initialize(self) -> None:
        try:
            import sentencepiece as spm
        except ImportError:
            logger.warning(f"[tokenizer:{self._group_id}] sentencepiece not installed. Install with: pip install sentencepiece")
            return

        model_file = self._resolve_model_file()
        if model_file is None:
            logger.warning(
                f"[tokenizer:{self._group_id}] Model file not found. "
                f"Place tokenizer.model in models/{self._group_id}/ or set hf_repo_id for auto-download."
            )
            return

        try:
            self._processor = spm.SentencePieceProcessor()
            self._processor.Load(model_file)
            self._available = True
            logger.info(f"SentencePieceTokenizer {self._group_id} loaded from {model_file}")
        except Exception as e:
            logger.warning(f"[tokenizer:{self._group_id}] Failed to load model {model_file}: {e}")

    def _resolve_model_file(self) -> str | None:
        """Look for .model file: explicit path -> models/ dir -> auto-download from HF."""
        # 1. Explicit path
        if self._model_path and os.path.isfile(self._model_path):
            return self._model_path

        # 2. Project models/ directory
        project_path = os.path.join("models", self._group_id, "tokenizer.model")
        if os.path.isfile(project_path):
            return project_path

        # 3. Auto-download from HuggingFace
        if self._hf_repo_id:
            return self._download_from_hf()

        return None

    def _download_from_hf(self) -> str | None:
        """Download tokenizer.model from HuggingFace and save locally."""
        try:
            from huggingface_hub import hf_hub_download
            local_path = hf_hub_download(
                repo_id=self._hf_repo_id,
                filename=self._hf_filename,
                local_dir=f"models/{self._group_id}",
                local_dir_use_symlinks=False,
            )
            logger.info(f"SentencePiece model downloaded to {local_path}")
            return local_path
        except ImportError:
            logger.warning(f"[tokenizer:{self._group_id}] huggingface-hub not installed. Cannot auto-download.")
            return None
        except Exception as e:
            # 403 on gated repos (e.g. google/gemma-3-4b-it) is expected — access not yet granted.
            if "403" in str(e) or "awaiting a review" in str(e).lower():
                logger.info(
                    f"[tokenizer:{self._group_id}] Download skipped — "
                    f"model is gated (access pending review). Using fallback estimation."
                )
            else:
                logger.warning(f"[tokenizer:{self._group_id}] Auto-download failed: {e}")
            return None

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        if not self._available:
            raise InitializationError(f"SentencePieceTokenizer {self._group_id} not initialized", self._group_id)
        try:
            return len(self._processor.EncodeAsIds(text))
        except Exception as e:
            raise TokenizationError(f"Failed to count tokens: {e}", self._group_id, e)

    def encode(self, text: str) -> list[int]:
        if not text:
            return []
        if not self._available:
            raise InitializationError(f"SentencePieceTokenizer {self._group_id} not initialized", self._group_id)
        return self._processor.EncodeAsIds(text)

    def decode(self, tokens: list[int]) -> str:
        if not tokens:
            return ""
        if not self._available:
            raise InitializationError(f"SentencePieceTokenizer {self._group_id} not initialized", self._group_id)
        return self._processor.DecodeIds(tokens)
