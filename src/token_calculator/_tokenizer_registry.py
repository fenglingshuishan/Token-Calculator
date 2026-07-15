"""Tokenizer registry -- factory, lazy loading, caching, and fallback."""
from __future__ import annotations
import logging
import threading
from token_calculator._tokenizer_base import TokenizerBase, TokenizerError
from token_calculator._tokenizer_tiktoken import TiktokenTokenizer

logger = logging.getLogger(__name__)

# Module-level cache: group_id -> TokenizerBase instance (even failed ones)
_tokenizer_cache: dict[str, TokenizerBase] = {}
_cache_lock = threading.Lock()

# Lazy imports for optional dependencies
_HfTokenizer = None
_SentencePieceTokenizer = None


def _get_hf_class():
    global _HfTokenizer
    if _HfTokenizer is None:
        from token_calculator._tokenizer_hf import HfTokenizer
        _HfTokenizer = HfTokenizer
    return _HfTokenizer


def _get_sp_class():
    global _SentencePieceTokenizer
    if _SentencePieceTokenizer is None:
        from token_calculator._tokenizer_sentencepiece import SentencePieceTokenizer
        _SentencePieceTokenizer = SentencePieceTokenizer
    return _SentencePieceTokenizer


# Tokenizer configuration: group_id -> {class, config}
TOKENIZER_CONFIG: dict[str, dict] = {
    "o200k_base": {
        "class": "tiktoken",
        "encoding": "o200k_base",
    },
    "cl100k_base": {
        "class": "tiktoken",
        "encoding": "cl100k_base",
    },
    "llama3": {
        "class": "hf",
        "repo_id": "NousResearch/Meta-Llama-3-8B",  # Non-gated mirror
    },
    "qwen": {
        "class": "hf",
        "repo_id": "Qwen/Qwen2.5-7B",
    },
    "deepseek_v4": {
        "class": "hf",
        "repo_id": "deepseek-ai/DeepSeek-V3",
    },
    "glm": {
        "class": "hf",
        "repo_id": "THUDM/glm-4-9b",
    },
    "gemma": {
        "class": "hf",
        "repo_id": "EuroEval/gemma-3-tokenizer",  # Public mirror, no gating
    },
    "mistral": {
        "class": "hf",
        "repo_id": "mistralai/Mistral-7B-v0.1",
    },
}


def get_tokenizer(group_id: str) -> TokenizerBase:
    """Get or create a tokenizer instance for the given group_id.

    Initialized lazily on first call. Cached for the lifetime of the process.
    Returns an available=False instance if initialization fails.
    Raises KeyError if group_id is unknown.
    """
    if group_id in _tokenizer_cache:
        return _tokenizer_cache[group_id]

    with _cache_lock:
        # Double-check after acquiring lock
        if group_id in _tokenizer_cache:
            return _tokenizer_cache[group_id]

        config = TOKENIZER_CONFIG.get(group_id)
        if config is None:
            raise KeyError(f"Unknown group_id: {group_id!r}. Available: {list(TOKENIZER_CONFIG.keys())}")

        class_type = config["class"]
        instance = None

        if class_type == "tiktoken":
            instance = TiktokenTokenizer(group_id, config["encoding"])
        elif class_type == "hf":
            HfTokenizer = _get_hf_class()
            instance = HfTokenizer(group_id, config["repo_id"])
        elif class_type == "sentencepiece":
            SentencePieceTokenizer = _get_sp_class()
            instance = SentencePieceTokenizer(
                group_id,
                hf_repo_id=config.get("hf_repo_id"),
                hf_filename=config.get("hf_filename", "tokenizer.model"),
            )
        else:
            raise ValueError(f"Unknown tokenizer class: {class_type!r} for group_id {group_id!r}")

        # Lazy init -- initialize() may fail gracefully (sets available=False)
        instance.initialize()
        if instance.available:
            logger.info(f"Tokenizer {group_id} initialized successfully")
        else:
            logger.debug(f"Tokenizer {group_id} not available, will use fallback estimation")

        # Cache even failed instances to avoid repeated init attempts
        _tokenizer_cache[group_id] = instance
        return instance


def count_tokens(text: str, group_id: str) -> tuple[int, bool]:
    """Count tokens for text under group_id tokenizer.

    Returns (token_count, is_precise).
    - is_precise=True: count comes from real tokenizer
    - is_precise=False: count is fallback estimate (len*0.25)
    """
    if not text:
        return 0, True
    try:
        tokenizer = get_tokenizer(group_id)
        if tokenizer.available:
            return tokenizer.count_tokens(text), True
    except (TokenizerError, KeyError, Exception):
        pass
    return _estimate_tokens_fallback(text), False


def count_tokens_batch(text: str, group_ids: list[str]) -> list[dict]:
    """Count tokens for text across multiple group_ids.

    Returns list of {group_id, tokens, available} for each group.
    """
    results = []
    for gid in group_ids:
        try:
            count, precise = count_tokens(text, gid)
        except KeyError:
            count, precise = _estimate_tokens_fallback(text), False
        results.append({"group_id": gid, "tokens": count, "available": precise})
    return results


def _estimate_tokens_fallback(text: str) -> int:
    """Rough character-based token estimate (~0.25 tokens per character)."""
    return max(1, int(len(text) * 0.25))


def get_all_group_ids() -> list[str]:
    """Return all configured group IDs."""
    return list(TOKENIZER_CONFIG.keys())


def preload_all() -> dict[str, bool]:
    """Preload and initialize all configured tokenizers.

    Returns dict of group_id -> available status.
    Useful for startup validation and download scripts.

    Note: gemma is intentionally skipped during preload.  Its HuggingFace repo
    (google/gemma-3-4b-it) is gated and Google has not approved access yet.
    Preloading it would trigger a 403 HTTP error on every startup.
    It will be lazily initialized on first API request instead.
    """
    results = {}
    for gid in TOKENIZER_CONFIG:
        try:
            tok = get_tokenizer(gid)
            results[gid] = tok.available
        except Exception:
            results[gid] = False
    return results
