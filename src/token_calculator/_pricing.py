"""Model pricing database and model group registry.

Price unit: USD per 1M tokens.
Updated July 2026 -- only currently active models.
"""
from __future__ import annotations

_DEFAULT_PRICING: dict[str, dict] = {
    # OpenAI GPT-5.6 Luna / GPT-4.1 / GPT-4o family (o200k_base)
    "GPT-5.6 Luna":     {"input": 1.00,  "output": 6.00,  "cache_hit": 0.10},
    "GPT-4.1":          {"input": 2.00,  "output": 8.00,  "cache_hit": 1.00},
    "GPT-4.1-mini":     {"input": 0.40,  "output": 1.60,  "cache_hit": 0.20},
    "GPT-4.1-nano":     {"input": 0.10,  "output": 0.40,  "cache_hit": 0.05},
    "GPT-4o":           {"input": 2.50,  "output": 10.00, "cache_hit": 1.25},
    "GPT-4o-mini":      {"input": 0.15,  "output": 0.60,  "cache_hit": 0.075},
    "o4-mini":          {"input": 1.10,  "output": 4.40,  "cache_hit": 0.55},
    # OpenAI GPT-4 legacy (cl100k_base)
    "GPT-4":            {"input": 30.00, "output": 60.00, "cache_hit": None},
    "GPT-4-turbo":      {"input": 10.00, "output": 30.00, "cache_hit": None},
    "text-embedding-3-small": {"input": 0.02, "output": 0.02, "cache_hit": None},
    "text-embedding-3-large": {"input": 0.13, "output": 0.13, "cache_hit": None},
    # Meta Llama
    "Llama 4 Maverick": {"input": 0.27,  "output": 0.85,  "cache_hit": 0.09},
    "Llama 4 Scout":    {"input": 0.11,  "output": 0.34,  "cache_hit": 0.05},
    "Llama 3.3 70B":    {"input": 0.30,  "output": 0.80,  "cache_hit": 0.08},
    # Alibaba Qwen
    "Qwen 3.7 Plus":    {"input": 0.32,  "output": 1.28,  "cache_hit": 0.10},
    "Qwen3-235B":       {"input": 0.18,  "output": 0.54,  "cache_hit": None},
    "Qwen 3.6 27B":     {"input": 0.29,  "output": 3.20,  "cache_hit": None},
    # DeepSeek V4
    "DeepSeek V4 Flash":{"input": 0.14,  "output": 0.28,  "cache_hit": 0.0028},
    "DeepSeek V4 Pro":  {"input": 0.435, "output": 0.87,  "cache_hit": 0.0087},
    # Mistral
    "Mistral Large 3":  {"input": 0.50,  "output": 1.50,  "cache_hit": 0.25},
    "Mistral Small 4":  {"input": 0.15,  "output": 0.60,  "cache_hit": 0.075},
    "Mistral Medium 3.5":{"input": 1.50,  "output": 7.50,  "cache_hit": 0.75},
    # Google Gemma
    "Gemma 4 12B":      {"input": 0.15,  "output": 0.60,  "cache_hit": 0.10},
    "Gemma 3 27B":      {"input": 0.15,  "output": 0.60,  "cache_hit": 0.10},
    # Zhipu GLM
    "GLM-4.7":          {"input": 0.60,  "output": 2.20,  "cache_hit": 0.11},
    "GLM-4.5":          {"input": 0.50,  "output": 2.00,  "cache_hit": 0.10},
    "GLM-4.5-Air":      {"input": 0.20,  "output": 1.10,  "cache_hit": 0.05},
}

_DEFAULT_GROUPS: list[dict] = [
    {
        "group_id": "o200k_base", "type": "open", "library": "tiktoken",
        "encoding": "o200k_base", "display_name": "OpenAI (o200k_base)",
        "provider": "OpenAI",
        "models": ["GPT-5.6 Luna", "GPT-4.1", "GPT-4.1-mini", "GPT-4.1-nano", "GPT-4o", "GPT-4o-mini", "o4-mini"],
        "max_tokens": 1000000, "vocab_size": 200064,
    },
    {
        "group_id": "cl100k_base", "type": "open", "library": "tiktoken",
        "encoding": "cl100k_base", "display_name": "OpenAI Legacy + Embeddings (cl100k_base)",
        "provider": "OpenAI",
        "models": ["GPT-4-turbo", "GPT-4", "text-embedding-3-small", "text-embedding-3-large"],
        "max_tokens": 128000, "vocab_size": 100256,
    },
    {
        "group_id": "llama3", "type": "open", "library": "transformers",
        "encoding": "llama3", "repo_id": "meta-llama/Llama-3.1-8B", "display_name": "Meta Llama 4",
        "provider": "Meta",
        "models": ["Llama 4 Maverick", "Llama 4 Scout", "Llama 3.3 70B"],
        "max_tokens": 128000, "vocab_size": 128256,
    },
    {
        "group_id": "qwen", "type": "open", "library": "transformers",
        "encoding": "qwen", "repo_id": "Qwen/Qwen2.5-7B", "display_name": "Alibaba Qwen 3",
        "provider": "Alibaba",
        "models": ["Qwen 3.7 Plus", "Qwen3-235B", "Qwen 3.6 27B"],
        "max_tokens": 131072, "vocab_size": 151936,
    },
    {
        "group_id": "deepseek_v4", "type": "open", "library": "transformers",
        "encoding": "deepseek_v4", "repo_id": "deepseek-ai/DeepSeek-V3", "display_name": "DeepSeek V4",
        "provider": "DeepSeek",
        "models": ["DeepSeek V4 Flash", "DeepSeek V4 Pro"],
        "max_tokens": 1000000, "vocab_size": 129280,
    },
    {
        "group_id": "mistral", "type": "open", "library": "transformers",
        "encoding": "mistral", "repo_id": "mistralai/Mistral-7B-v0.1", "display_name": "Mistral AI",
        "provider": "Mistral AI",
        "models": ["Mistral Large 3", "Mistral Small 4", "Mistral Medium 3.5"],
        "max_tokens": 262000, "vocab_size": 131072,
    },
    {
        "group_id": "gemma", "type": "open", "library": "transformers",
        "encoding": "gemma", "repo_id": "EuroEval/gemma-3-tokenizer", "display_name": "Google Gemma",
        "provider": "Google",
        "models": ["Gemma 4 12B", "Gemma 3 27B"],
        "max_tokens": 128000, "vocab_size": 256128,
    },
    {
        "group_id": "glm", "type": "open", "library": "transformers",
        "encoding": "glm", "repo_id": "THUDM/glm-4-9b", "display_name": "Z.ai GLM-4.7",
        "provider": "Zhipu AI",
        "models": ["GLM-4.7", "GLM-4.5", "GLM-4.5-Air"],
        "max_tokens": 200000, "vocab_size": 65024,
    },
]


class PricingRegistry:
    """Pricing and model group registry with custom override support.

    Wraps the default pricing data and allows injection of custom pricing
    dictionaries or model group lists via the factory function or class methods.
    """

    def __init__(self, pricing=None, model_groups=None):
        self._pricing = pricing if pricing is not None else _DEFAULT_PRICING.copy()
        self._groups = model_groups if model_groups is not None else list(_DEFAULT_GROUPS)
        self._rebuild_index()

    def _rebuild_index(self):
        self._group_map = {g["group_id"]: g for g in self._groups}
        self._repr_model = {g["group_id"]: g["models"][0] for g in self._groups}

    def get_pricing(self, model_name: str) -> dict | None:
        return self._pricing.get(model_name)

    def get_groups(self) -> list[dict]:
        return list(self._groups)

    def get_representative(self, group_id: str) -> str | None:
        return self._repr_model.get(group_id)

    @classmethod
    def from_dict(cls, pricing: dict) -> "PricingRegistry":
        return cls(pricing=pricing)

    def merge_pricing(self, overrides: dict) -> "PricingRegistry":
        self._pricing.update(overrides)
        return self


# Backward-compatible module-level interface
PRICING = _DEFAULT_PRICING
MODEL_GROUPS = _DEFAULT_GROUPS
GROUP_TO_REPRESENTATIVE_MODEL: dict[str, str] = {
    g["group_id"]: g["models"][0] for g in _DEFAULT_GROUPS
}


def get_pricing(model_name: str) -> dict | None:
    """Return pricing dict for a given model name, or None if not found."""
    return _DEFAULT_PRICING.get(model_name)
