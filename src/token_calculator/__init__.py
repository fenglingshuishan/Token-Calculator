"""Archived Token Calculator -- token counting, compression, cost simulation.

Usage:
    from token_calculator import create_app
    app = create_app(static_dir="./frontend")

    # Or mount to existing FastAPI app:
    main_app.mount("/tools/token-calc", create_app(static_dir=None))
"""

from token_calculator._app import create_app
from token_calculator._pricing import PricingRegistry
from token_calculator._tokenizer_registry import (
    get_tokenizer,
    count_tokens,
    count_tokens_batch,
    get_all_group_ids,
    preload_all,
)
from token_calculator._rule_compressor import RuleCompressor
from token_calculator._llm_compressor import LLMCompressor
from token_calculator._cost_simulator import CostSimulator

__all__ = [
    "create_app",
    "PricingRegistry",
    "get_tokenizer",
    "count_tokens",
    "count_tokens_batch",
    "get_all_group_ids",
    "preload_all",
    "RuleCompressor",
    "LLMCompressor",
    "CostSimulator",
]
__version__ = "3.0.0"
