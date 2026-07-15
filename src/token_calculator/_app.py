"""FastAPI application for the trustworthy prompt economics workbench."""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from token_calculator._compressor_base import CompressionError
from token_calculator._models import (
    CompressionChange, CompressionResult, CompressRequest, CostSimulateRequest,
    CostSimulateResponse, ExportRequest, ExportResponse, ModelCostComparison,
    TokenizeMode, TokenizeRequest, TokenizeResponse, TokenizeResult,
    TokenizerPrepareRequest,
)
from token_calculator._pricing import PricingRegistry
from token_calculator._static import setup_static_files

logger = logging.getLogger(__name__)


def _token_cost(tokens: int, mode: TokenizeMode, pricing: dict | None) -> float:
    if not pricing:
        return 0.0
    key = "cache_hit" if mode == TokenizeMode.cache else mode.value
    price = pricing.get(key)
    return round(tokens * float(price or 0) / 1_000_000, 8)


def _effective_input_price(pricing: dict, cache_rate: float) -> float:
    normal = float(pricing.get("input") or 0)
    cached = pricing.get("cache_hit")
    if cached is None:
        return normal
    return normal * (1 - cache_rate) + float(cached) * cache_rate


def create_app(*, static_dir: str | None = None,
               cors_origins: list[str] | None = None,
               pricing_registry: PricingRegistry | None = None,
               debug: bool = False) -> FastAPI:
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(levelname)-8s %(name)s  %(message)s",
    )
    registry = pricing_registry or PricingRegistry()
    origins = cors_origins or ["http://127.0.0.1:8000", "http://localhost:8000"]
    app = FastAPI(
        title="Prompt Economics Workbench API",
        description="Auditable token counting, conservative cleanup and break-even analysis.",
        version="3.0.0",
    )
    app.add_middleware(
        CORSMiddleware, allow_origins=origins, allow_credentials=False,
        allow_methods=["GET", "POST"], allow_headers=["Content-Type"],
    )
    tokenizer_job = {"state": "idle", "results": {}, "message": ""}

    @app.get("/health")
    async def health():
        return {
            "status": "ok", "version": "3.0.0", "lifecycle": "archived",
            "capabilities": ["tokenize", "safe-cleanup", "llm-compress",
                             "break-even", "export"],
        }

    @app.get("/api/models")
    async def get_models():
        groups = []
        for group in registry.get_groups():
            model = group["models"][0]
            groups.append({
                **group,
                "pricing": registry.get_pricing(model),
                "model_pricing": {name: registry.get_pricing(name) for name in group["models"]},
            })
        return {"groups": groups, "pricing_meta": registry.metadata}

    @app.post("/api/tokenize", response_model=TokenizeResponse)
    async def tokenize(request: TokenizeRequest):
        from token_calculator._tokenizer_registry import TOKENIZER_CONFIG, count_tokens_detailed

        results = []
        for group_id in request.group_ids:
            if group_id not in TOKENIZER_CONFIG:
                raise HTTPException(404, f"未知 tokenizer 分组: {group_id}")
            detail = count_tokens_detailed(request.text, group_id)
            model = registry.get_representative(group_id) or group_id
            results.append(TokenizeResult(
                group_id=group_id, model_name=model, tokens=detail["tokens"],
                char_count=len(request.text),
                cost_usd=_token_cost(detail["tokens"], request.mode,
                                     registry.get_pricing(model)),
                available=detail["precise"], method=detail["method"],
                warning=detail["warning"],
            ))
        return TokenizeResponse(char_count=len(request.text), results=results)

    @app.get("/api/tokenizers/status")
    async def tokenizers_status():
        from token_calculator._tokenizer_registry import tokenizer_status
        return {"tokenizers": tokenizer_status(), "job": dict(tokenizer_job)}

    @app.post("/api/tokenizers/prepare", status_code=202)
    async def tokenizers_prepare(request: TokenizerPrepareRequest,
                                 background_tasks: BackgroundTasks):
        from token_calculator._tokenizer_registry import TOKENIZER_CONFIG, prepare_tokenizers
        targets = request.group_ids or list(TOKENIZER_CONFIG)
        unknown = [group_id for group_id in targets if group_id not in TOKENIZER_CONFIG]
        if unknown:
            raise HTTPException(404, f"未知 tokenizer 分组: {unknown}")
        if tokenizer_job["state"] == "running":
            return {"accepted": False, "job": dict(tokenizer_job)}

        def work():
            tokenizer_job.update(state="running", results={}, message="正在下载公开词表")
            try:
                results = prepare_tokenizers(targets)
                ready = sum(1 for value in results.values() if value)
                tokenizer_job.update(state="completed", results=results,
                                     message=f"{ready}/{len(results)} 个分词器已就绪")
            except Exception as exc:
                logger.exception("Tokenizer preparation failed")
                tokenizer_job.update(state="failed", message=str(exc)[:200])

        tokenizer_job.update(state="queued", results={}, message="任务已加入队列")
        background_tasks.add_task(work)
        return {"accepted": True, "job": dict(tokenizer_job)}

    @app.post("/api/compress", response_model=CompressionResult)
    async def compress(request: CompressRequest):
        from token_calculator._llm_compressor import LLMCompressor
        from token_calculator._quality_guard import validate_compression
        from token_calculator._rule_compressor import RuleCompressor
        from token_calculator._tokenizer_registry import TOKENIZER_CONFIG, count_tokens_detailed

        if request.group_id not in TOKENIZER_CONFIG:
            raise HTTPException(404, f"未知 tokenizer 分组: {request.group_id}")

        try:
            if request.strategy.value == "llm":
                if not request.llm_config:
                    raise HTTPException(422, "LLM 模式需要 llm_config")
                config = request.llm_config.model_dump(mode="json")
                config["target_ratio"] = request.target_ratio
                result = LLMCompressor().compress(request.text, llm_config=config)
            else:
                result = RuleCompressor().compress(request.text, request.level.value)
        except CompressionError as exc:
            raise HTTPException(502, str(exc)) from exc

        attempted_text = result["compressed_text"]
        quality = validate_compression(request.text, attempted_text)
        original = count_tokens_detailed(request.text, request.group_id)
        compressed = count_tokens_detailed(attempted_text, request.group_id)
        status = "completed"
        if not quality["passed"]:
            status = "rejected"
            result["compressed_text"] = request.text
            compressed = original
        elif compressed["tokens"] >= original["tokens"]:
            status = "no_change"
            result["compressed_text"] = request.text
            compressed = original
        precise = original["precise"] and compressed["precise"]
        saved = original["tokens"] - compressed["tokens"]
        percentage = round(saved / original["tokens"] * 100, 2) if original["tokens"] else 0

        model_id = request.model_id or registry.get_representative(request.group_id)
        pricing = registry.get_pricing(model_id) if model_id else None
        if request.economics.target_input_price is not None:
            pricing = dict(pricing or {})
            pricing.update(input=request.economics.target_input_price,
                           cache_hit=None, source="user", as_of="本次输入",
                           verified=True)
        warnings = list(result.get("warnings", []))
        if status == "rejected":
            warnings.append("结果未通过结构校验，已恢复原文：" + "；".join(quality["issues"]))
        elif status == "no_change":
            warnings.append("候选结果没有减少 Token，已保留原文，不计为成功优化。")
        if not precise:
            warnings.append(original["warning"] or "Token 数为估算值。")
        if not pricing:
            warnings.append("所选模型没有可审计价格，无法计算金额。")
        elif not pricing.get("verified"):
            warnings.append("该模型价格没有内置官方来源，请在用于预算前手动复核。")

        compression_cost = 0.0
        compression_cost_known = request.strategy.value == "rule"
        stats = result.get("stats", {})
        if request.strategy.value == "llm":
            llm_config = request.llm_config
            llm_pricing = registry.get_pricing(llm_config.model) or {}
            input_price = (llm_config.input_price if llm_config.input_price is not None
                           else llm_pricing.get("input"))
            output_price = (llm_config.output_price if llm_config.output_price is not None
                            else llm_pricing.get("output"))
            in_usage = stats.get("llm_input_tokens", 0)
            out_usage = stats.get("llm_output_tokens", 0)
            if input_price is not None and output_price is not None and (in_usage or out_usage):
                compression_cost = (in_usage * float(input_price) +
                                    out_usage * float(output_price)) / 1_000_000
                compression_cost_known = True
            else:
                warnings.append("提供商未返回 usage 或缺少压缩模型价格；净收益暂不可判定。")

        per_use_savings = None
        gross_savings = None
        net_savings = None
        break_even = None
        profitable = None
        if pricing:
            effective_price = _effective_input_price(
                pricing, request.economics.cache_hit_rate)
            per_use_savings = saved * effective_price / 1_000_000
            gross_savings = per_use_savings * request.economics.reuse_count
            if compression_cost_known:
                net_savings = gross_savings - compression_cost
                profitable = net_savings > 0
                if compression_cost > 0 and per_use_savings > 0:
                    break_even = math.ceil(compression_cost / per_use_savings)

        economics = {
            "model_id": model_id,
            "reuse_count": request.economics.reuse_count,
            "per_use_savings_usd": per_use_savings,
            "gross_savings_usd": gross_savings,
            "compression_cost_usd": compression_cost if compression_cost_known else None,
            "net_savings_usd": net_savings,
            "break_even_uses": break_even,
            "profitable": profitable,
            "pricing_source": pricing.get("source") if pricing else None,
            "pricing_as_of": pricing.get("as_of") if pricing else None,
        }
        return CompressionResult(
            strategy=request.strategy.value, status=status,
            original_text=request.text, compressed_text=result["compressed_text"],
            original_tokens={request.group_id: original["tokens"]},
            compressed_tokens={request.group_id: compressed["tokens"]},
            token_count_method=original["method"] if precise else "language-aware-estimate",
            savings={"tokens_saved": saved, "percentage": percentage},
            economics=economics, warnings=list(dict.fromkeys(warnings)), quality=quality,
            changes=[CompressionChange(**change) for change in result.get("changes", [])],
        )

    @app.post("/api/cost-simulate", response_model=CostSimulateResponse)
    async def cost_simulate(request: CostSimulateRequest):
        from token_calculator._cost_simulator import CostSimulator
        for model_id in request.model_ids:
            if registry.get_pricing(model_id) is None:
                raise HTTPException(404, f"未知或无价格的模型: {model_id}")
        result = CostSimulator(registry).simulate(
            monthly_calls=request.monthly_calls,
            avg_input_tokens=request.avg_input_tokens,
            compressed_input_tokens=request.compressed_input_tokens,
            avg_output_tokens=request.avg_output_tokens,
            cache_hit_rate=request.cache_hit_rate,
            compression_ratio=request.compression_ratio,
            compression_cost_usd=request.compression_cost_usd,
            model_ids=request.model_ids,
        )
        return CostSimulateResponse(
            monthly_calls=result["monthly_calls"],
            comparisons=[ModelCostComparison(**item) for item in result["comparisons"]],
            best_value_model=result["best_value_model"],
        )

    @app.get("/api/pricing")
    async def pricing():
        return {"pricing": registry.get_all_pricing(), "meta": registry.metadata}

    @app.post("/api/export", response_model=ExportResponse)
    async def export(request: ExportRequest):
        if request.format == "json":
            value = json.dumps({"prompt": request.text}, ensure_ascii=False, indent=2)
        elif request.format == "markdown":
            value = f"```text\n{request.text}\n```"
        else:
            value = request.text
        return ExportResponse(text=value, format=request.format)

    if static_dir:
        path = Path(static_dir)
        if not path.is_dir():
            raise ValueError(f"Static directory does not exist: {static_dir}")
        setup_static_files(app, static_dir)
    return app
