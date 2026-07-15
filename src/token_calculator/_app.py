"""Prompt Optimization Workstation -- FastAPI Application Factory.

Provides create_app() for standalone deployment or mount as a sub-application.
"""
from __future__ import annotations

import json
import logging
import warnings

# Suppress framework warnings (PyTorch not found, HF deprecations, etc.)
warnings.filterwarnings("ignore", message=".*PyTorch.*not found.*")
warnings.filterwarnings("ignore", module="huggingface_hub")
warnings.filterwarnings("ignore", module="mistral_common")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from token_calculator._models import (
    TokenizeMode,
    TokenizeRequest,
    TokenizeResult,
    TokenizeResponse,
    CompressionChange,
    CompressRequest,
    CompressionResult,
    CostSimulateRequest,
    ModelCostComparison,
    CostSimulateResponse,
    ExportRequest,
    ExportResponse,
)
from token_calculator._pricing import PricingRegistry
from token_calculator._static import setup_static_files

logger = logging.getLogger(__name__)


def _compute_token_cost(tokens: int, mode: TokenizeMode, pricing: dict | None) -> float:
    if pricing is None:
        return 0.0
    if mode == TokenizeMode.cache:
        price_key = "cache_hit"
    else:
        price_key = mode.value
    price_per_million = pricing.get(price_key, 0)
    if price_per_million is None:
        return 0.0
    return round(tokens * price_per_million / 1_000_000, 8)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_app(
    *,
    static_dir: str | None = None,
    cors_origins: list[str] | None = None,
    pricing_registry: PricingRegistry | None = None,
    debug: bool = False,
) -> FastAPI:
    """Create and configure the Prompt Optimization Workstation FastAPI app.

    Args:
        static_dir: Path to frontend static files. None = API-only mode.
        cors_origins: Allowed CORS origins. Defaults to wildcard ["*"].
        pricing_registry: Custom PricingRegistry instance for custom pricing.
        debug: Enable debug-mode logging (verbose tokenizer/compressor output).

    Returns:
        A fully configured FastAPI application ready to serve or mount.
    """
    log_level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(level=log_level, format="%(levelname)-8s %(name)s  %(message)s")

    # Silence noisy third-party loggers
    for noisy in ["transformers", "huggingface_hub", "sentencepiece", "mistral_common",
                   "urllib3", "httpx", "httpcore", "token_calculator._tokenizer_hf"]:
        logging.getLogger(noisy).setLevel(logging.ERROR)

    registry = pricing_registry or PricingRegistry()
    origins = cors_origins or ["*"]

    app = FastAPI(
        title="Prompt Optimization Workstation API",
        description="Token counting, semantic compression, and cost simulation for LLM prompts.",
        version="2.0.0",
    )

    # --- Preload tokenizers on startup (avoid slow first request) ---
    @app.on_event("startup")
    async def _preload_tokenizers():
        """Preload all available tokenizers in the background so the first
        API request doesn't suffer from cold-start latency (5-15s for HF downloads)."""
        import threading
        def _load():
            from token_calculator._tokenizer_registry import preload_all
            logger.info("Preloading tokenizers...")
            results = preload_all()
            ready = sum(1 for v in results.values() if v)
            logger.info(f"Tokenizer preload complete: {ready}/{len(results)} ready")
        t = threading.Thread(target=_load, daemon=True)
        t.start()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -----------------------------------------------------------------------
    # Health check
    # -----------------------------------------------------------------------

    @app.get("/health")
    def health():
        return {"status": "ok"}

    # -----------------------------------------------------------------------
    # GET /api/models — return groups with embedded pricing
    # -----------------------------------------------------------------------

    @app.get("/api/models")
    def get_models():
        result = []
        for g in registry.get_groups():
            rep_model = g["models"][0]
            rep_pricing = registry.get_pricing(rep_model) or {}
            result.append({**g, "pricing": rep_pricing})
        return {"groups": result}

    # -----------------------------------------------------------------------
    # POST /api/tokenize
    # -----------------------------------------------------------------------

    @app.post("/api/tokenize", response_model=TokenizeResponse)
    def tokenize(request: TokenizeRequest):
        char_count = len(request.text)
        results: list[TokenizeResult] = []

        for group_id in request.group_ids:
            from token_calculator._tokenizer_registry import count_tokens as registry_count_tokens
            from token_calculator._pricing import GROUP_TO_REPRESENTATIVE_MODEL

            model_name = GROUP_TO_REPRESENTATIVE_MODEL.get(group_id)
            if model_name is None:
                # Also check the registry
                from token_calculator._tokenizer_registry import TOKENIZER_CONFIG
                if group_id not in TOKENIZER_CONFIG:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Unknown group_id: {group_id!r}. Available: {list(TOKENIZER_CONFIG.keys())}",
                    )
                model_name = group_id

            token_count, is_precise = registry_count_tokens(request.text, group_id)
            pricing = registry.get_pricing(model_name)
            cost = _compute_token_cost(token_count, request.mode, pricing)

            results.append(TokenizeResult(
                group_id=group_id,
                model_name=model_name,
                tokens=token_count,
                cost_usd=cost,
                available=is_precise,
                char_count=char_count,
            ))

        return TokenizeResponse(char_count=char_count, results=results)

    # -----------------------------------------------------------------------
    # POST /api/compress
    # -----------------------------------------------------------------------

    @app.post("/api/compress", response_model=CompressionResult)
    def compress(request: CompressRequest):
        """Compress text using the specified strategy.

        - rule: Local regex-based compression (milliseconds, no API needed)
        - llm: LLM-based semantic compression (requires API key in llm_config)
        """
        from token_calculator._rule_compressor import RuleCompressor
        from token_calculator._llm_compressor import LLMCompressor
        from token_calculator._tokenizer_registry import count_tokens as registry_count_tokens, get_all_group_ids

        text = request.text

        # Select and run compressor
        if request.strategy.value == "llm":
            compressor = LLMCompressor()
            llm_cfg = None
            if request.llm_config:
                llm_cfg = {
                    "provider": request.llm_config.provider,
                    "api_key": request.llm_config.api_key,
                    "model": request.llm_config.model,
                    "target_ratio": request.target_ratio,
                    "api_base": request.llm_config.api_base,
                }
            result = compressor.compress(text, level=request.level.value, llm_config=llm_cfg)
        else:
            compressor = RuleCompressor()
            result = compressor.compress(text, level=request.level.value)

        compressed_text = result["compressed_text"]
        changes = result["changes"]
        stats = result["stats"]

        # Get precise token counts for the two instant tiktoken groups.
        # Counting all 8 groups would trigger cold-start downloads (HF models) on first
        # request, blocking the response for 20+ seconds. The frontend already calls
        # /api/tokenize separately for the user's selected model.
        original_tokens: dict[str, int] = {}
        compressed_tokens: dict[str, int] = {}
        fast_groups = ["o200k_base", "cl100k_base"]
        for gid in fast_groups:
            orig_count, _ = registry_count_tokens(text, gid)
            comp_count, _ = registry_count_tokens(compressed_text, gid)
            original_tokens[gid] = orig_count
            compressed_tokens[gid] = comp_count

        # Calculate savings (use o200k_base as reference, instant via tiktoken)
        default_group = "o200k_base"
        tokens_saved = original_tokens.get(default_group, 0) - compressed_tokens.get(default_group, 0)
        percentage = round((tokens_saved / original_tokens[default_group] * 100), 1) if original_tokens.get(default_group, 0) > 0 else 0.0

        return CompressionResult(
            strategy=request.strategy.value,
            original_text=text,
            compressed_text=compressed_text,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            savings={
                "tokens_saved": tokens_saved,
                "percentage": percentage,
                "estimated_monthly_savings_usd": round(tokens_saved * 0.0000025 * 10000, 2),
            },
            changes=[CompressionChange(**c) for c in changes],
        )

    # -----------------------------------------------------------------------
    # POST /api/cost-simulate
    # -----------------------------------------------------------------------

    @app.post("/api/cost-simulate", response_model=CostSimulateResponse)
    def cost_simulate(request: CostSimulateRequest):
        from token_calculator._cost_simulator import CostSimulator

        for model_id in request.model_ids:
            pricing = registry.get_pricing(model_id)
            if pricing is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Unknown model_id: '{model_id}'.",
                )

        sim = CostSimulator(registry)
        result = sim.simulate(
            monthly_calls=request.monthly_calls,
            avg_input_tokens=request.avg_input_tokens,
            avg_output_tokens=request.avg_output_tokens,
            cache_hit_rate=request.cache_hit_rate,
            compression_ratio=request.compression_ratio,
            model_ids=request.model_ids,
        )
        return CostSimulateResponse(
            monthly_calls=result["monthly_calls"],
            comparisons=[ModelCostComparison(**c) for c in result["comparisons"]],
            best_value_model=result["best_value_model"],
        )

    # -----------------------------------------------------------------------
    # GET /api/pricing
    # -----------------------------------------------------------------------

    @app.get("/api/pricing")
    def get_pricing_endpoint():
        return {"pricing": registry._pricing}

    # -----------------------------------------------------------------------
    # POST /api/export
    # -----------------------------------------------------------------------

    @app.post("/api/export", response_model=ExportResponse)
    def export_text(request: ExportRequest):
        text = request.text
        fmt = request.format
        if fmt == "json":
            text = json.dumps({"compressed_prompt": request.text}, ensure_ascii=False, indent=2)
        elif fmt == "markdown":
            text = "```\n" + request.text + "\n```"
        return ExportResponse(text=text, format=fmt)

    logger.info("Prompt Optimization Workstation API v2.0.0 created")

    # Static files must be mounted LAST so they don't shadow API routes
    if static_dir:
        setup_static_files(app, static_dir)

    return app
