"""Tokenizer registry -- factory, lazy loading, caching, and fallback."""
from __future__ import annotations
import logging
import os
import threading
from token_calculator._tokenizer_base import TokenizerBase, TokenizerError
from token_calculator._tokenizer_tiktoken import TiktokenTokenizer

logger = logging.getLogger(__name__)
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

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
        "revision": "315b20096dc791d381d514deb5f8bd9c8d6d3061",
    },
    "qwen": {
        "class": "hf",
        "repo_id": "Qwen/Qwen2.5-7B",
        "revision": "d149729398750b98c0af14eb82c78cfe92750796",
    },
    "deepseek_v4": {
        "class": "hf",
        "repo_id": "deepseek-ai/DeepSeek-V3",
        "revision": "e815299b0bcbac849fa540c768ef21845365c9eb",
    },
    "glm": {
        "class": "hf",
        "repo_id": "THUDM/glm-4-9b",
        "revision": "8cd2b585357ba9e702647ac4e6fa4fafe5cc7bee",
    },
    "gemma": {
        "class": "hf",
        "repo_id": "EuroEval/gemma-3-tokenizer",  # Public mirror, no gating
        "revision": "085af2553c0ca4345bd4b3aedb13b1022f8e274d",
    },
    "mistral": {
        "class": "hf",
        "repo_id": "mistralai/Mistral-7B-v0.1",
        "revision": "27d67f1b5f57dc0953326b2601d68371d40ea8da",
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
            instance = HfTokenizer(group_id, config["repo_id"], config.get("revision"))
        elif class_type == "sentencepiece":
            SentencePieceTokenizer = _get_sp_class()
            instance = SentencePieceTokenizer(
                group_id,
                hf_repo_id=config.get("hf_repo_id"),
                hf_filename=config.get("hf_filename", "tokenizer.model"),
            )
        else:
            raise ValueError(f"Unknown tokenizer class: {class_type!r} for group_id {group_id!r}")

        # Some tokenizer libraries fetch vocabulary data on first use. Never let
        # that network/cache operation block an API request indefinitely.
        import os
        if os.getenv("TOKEN_CALC_ALLOW_DOWNLOAD") == "1":
            # Explicit preparation is allowed to block and report completion.
            instance.initialize()
        else:
            worker = threading.Thread(target=instance.initialize, daemon=True)
            worker.start()
            worker.join(timeout=3.0)
            if worker.is_alive():
                logger.warning("Tokenizer %s initialization timed out; using estimate", group_id)
        if instance.available:
            logger.info(f"Tokenizer {group_id} initialized successfully")
        else:
            logger.debug(f"Tokenizer {group_id} not available, will use fallback estimation")

        # Cache even failed instances to avoid repeated init attempts
        _tokenizer_cache[group_id] = instance
        return instance


def count_tokens_detailed(text: str, group_id: str) -> dict:
    """Count tokens and expose whether the value is exact or estimated.

    An estimate is useful for an offline first run, but must never be presented
    as a tokenizer result.  The language-aware fallback is intentionally
    conservative and includes a warning for callers to display.
    """
    if group_id not in TOKENIZER_CONFIG:
        raise KeyError(f"Unknown group_id: {group_id!r}. Available: {list(TOKENIZER_CONFIG)}")
    if not text:
        return {"tokens": 0, "precise": True, "method": "exact-empty", "warning": None}
    try:
        tokenizer = get_tokenizer(group_id)
        if tokenizer.available:
            return {
                "tokens": tokenizer.count_tokens(text),
                "precise": True,
                "method": f"tokenizer:{group_id}",
                "warning": None,
            }
    except (TokenizerError, ImportError, OSError, RuntimeError, ValueError) as exc:
        logger.info("Tokenizer %s unavailable: %s", group_id, exc)
    return {
        "tokens": _estimate_tokens_fallback(text),
        "precise": False,
        "method": "language-aware-estimate",
        "warning": "分词器不可用；当前数值是语言感知估算，不应用于结算。安装 tokenizer 扩展后可获得精确结果。",
    }


def count_tokens(text: str, group_id: str) -> tuple[int, bool]:
    """Count tokens for text under group_id tokenizer.

    Returns (token_count, is_precise).
    - is_precise=True: count comes from real tokenizer
    - is_precise=False: count is a labelled language-aware estimate
    """
    result = count_tokens_detailed(text, group_id)
    return result["tokens"], result["precise"]


def count_tokens_batch(text: str, group_ids: list[str]) -> list[dict]:
    """Count tokens for text across multiple group_ids.

    Returns list of {group_id, tokens, available} for each group.
    """
    results = []
    for gid in group_ids:
        detail = count_tokens_detailed(text, gid)
        results.append({"group_id": gid, "tokens": detail["tokens"],
                        "available": detail["precise"], "method": detail["method"],
                        "warning": detail["warning"]})
    return results


def _estimate_tokens_fallback(text: str) -> int:
    """Conservative mixed-language estimate, never labelled as precise.

    CJK characters are commonly close to one token while Latin prose averages
    roughly four characters per token.  Punctuation is counted separately.
    """
    import re
    cjk = len(re.findall(r"[\u3400-\u9fff\uf900-\ufaff]", text))
    punctuation = len(re.findall(r"[^\w\s\u3400-\u9fff\uf900-\ufaff]", text))
    other = max(0, len(text) - cjk - punctuation)
    return max(1, round(cjk * 1.05 + other / 4 + punctuation * 0.5))


def get_all_group_ids() -> list[str]:
    """Return all configured group IDs."""
    return list(TOKENIZER_CONFIG.keys())


def reset_tokenizers(group_ids: list[str] | None = None) -> None:
    """Drop cached instances so a failed/offline tokenizer can be retried."""
    targets = group_ids or list(TOKENIZER_CONFIG)
    with _cache_lock:
        for group_id in targets:
            _tokenizer_cache.pop(group_id, None)


def tokenizer_status(group_ids: list[str] | None = None) -> list[dict]:
    """Return honest readiness information using a small local test encode."""
    targets = group_ids or list(TOKENIZER_CONFIG)
    statuses = []
    for group_id in targets:
        if group_id not in TOKENIZER_CONFIG:
            continue
        detail = count_tokens_detailed("Tokenizer readiness check", group_id)
        statuses.append({
            "group_id": group_id,
            "ready": detail["precise"],
            "method": detail["method"],
            "message": "精确分词器已就绪" if detail["precise"] else "尚未缓存，将使用带标签的估算",
        })
    return statuses


def prepare_tokenizers(group_ids: list[str] | None = None) -> dict[str, bool]:
    """Download public tokenizer assets for the requested groups."""
    import os
    targets = group_ids or list(TOKENIZER_CONFIG)
    previous = os.environ.get("TOKEN_CALC_ALLOW_DOWNLOAD")
    os.environ["TOKEN_CALC_ALLOW_DOWNLOAD"] = "1"
    try:
        reset_tokenizers(targets)
        results = {}
        for group_id in targets:
            if group_id not in TOKENIZER_CONFIG:
                results[group_id] = False
                continue
            try:
                results[group_id] = get_tokenizer(group_id).available
            except Exception as exc:
                logger.warning("Could not prepare %s: %s", group_id, exc)
                results[group_id] = False
        return results
    finally:
        if previous is None:
            os.environ.pop("TOKEN_CALC_ALLOW_DOWNLOAD", None)
        else:
            os.environ["TOKEN_CALC_ALLOW_DOWNLOAD"] = previous


def preload_all(include_remote: bool = False) -> dict[str, bool]:
    """Preload and initialize all configured tokenizers.

    Returns dict of group_id -> available status.
    Useful for startup validation and download scripts.

    Note: gemma is intentionally skipped during preload.  Its HuggingFace repo
    (google/gemma-3-4b-it) is gated and Google has not approved access yet.
    Preloading it would trigger a 403 HTTP error on every startup.
    It will be lazily initialized on first API request instead.
    """
    results = {}
    for gid, config in TOKENIZER_CONFIG.items():
        if not include_remote and config["class"] != "tiktoken":
            results[gid] = False
            continue
        try:
            tok = get_tokenizer(gid)
            results[gid] = tok.available
        except Exception:
            results[gid] = False
    return results
