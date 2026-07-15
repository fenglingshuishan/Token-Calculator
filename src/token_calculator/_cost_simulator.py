"""Cost simulation engine -- monthly cost projections and model comparisons."""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)


class CostSimulator:
    """Compute monthly/annual cost projections across multiple models.

    Accepts a PricingRegistry for pricing data lookup.
    All amounts are in USD.
    """

    def __init__(self, pricing_registry):
        self._registry = pricing_registry

    def simulate(self, *, monthly_calls=10000, avg_input_tokens=520,
                 compressed_input_tokens=None, avg_output_tokens=200,
                 cache_hit_rate=0.30, compression_ratio=0.65,
                 compression_cost_usd=0.0, model_ids=None):
        """Run cost simulation across specified models.

        Returns dict with comparisons list, best_value_model, monthly_calls.
        """
        if not model_ids:
            model_ids = ["GPT-4o", "DeepSeek V4 Flash", "Qwen 3.7 Plus"]

        comparisons = []
        for model_id in model_ids:
            pricing = self._registry.get_pricing(model_id)
            if pricing is None:
                continue

            comp = self._compare_model(
                model_id, pricing, monthly_calls,
                avg_input_tokens, avg_output_tokens,
                cache_hit_rate, compression_ratio, compressed_input_tokens,
                compression_cost_usd
            )
            if comp is not None:
                comparisons.append(comp)

        if not comparisons:
            return {"comparisons": [], "best_value_model": "", "monthly_calls": monthly_calls}

        best = min(comparisons, key=lambda c: c["after"]["total"])
        return {
            "comparisons": comparisons,
            "best_value_model": best["model_id"],
            "monthly_calls": monthly_calls,
        }

    def _compare_model(self, model_id, pricing, calls, in_tok, out_tok,
                       cache_rate, comp_ratio, compressed_input_tokens=None,
                       compression_cost=0.0):
        input_price = pricing.get("input")
        output_price = pricing.get("output")
        if input_price is None or output_price is None:
            logger.warning(f"Model {model_id} missing input/output pricing, skipping")
            return None
        cache_price = pricing.get("cache_hit")

        def calc(input_tokens, output_tokens):
            if cache_price is not None and cache_rate > 0:
                cached = input_tokens * cache_rate * cache_price / 1_000_000 * calls
                non_cached = input_tokens * (1 - cache_rate) * input_price / 1_000_000 * calls
                input_cost = cached + non_cached
            else:
                input_cost = input_tokens * input_price / 1_000_000 * calls
            output_cost = output_tokens * output_price / 1_000_000 * calls
            total = input_cost + output_cost
            return {
                "input_cost": round(input_cost, 2),
                "output_cost": round(output_cost, 2),
                "total": round(total, 2),
            }

        before = calc(in_tok, out_tok)
        compressed_in = (compressed_input_tokens if compressed_input_tokens is not None
                         else max(0, int(in_tok * comp_ratio)))
        after = calc(compressed_in, out_tok)

        gross_monthly_savings = before["total"] - after["total"]
        monthly_savings = round(gross_monthly_savings - compression_cost, 2)
        yearly_savings = round(monthly_savings * 12, 2)
        savings_pct = round((monthly_savings / before["total"] * 100) if before["total"] > 0 else 0.0, 2)
        per_use_savings = ((in_tok - compressed_in) * input_price / 1_000_000)
        break_even = None
        if compression_cost > 0 and per_use_savings > 0:
            import math
            break_even = math.ceil(compression_cost / per_use_savings)

        return {
            "model_id": model_id,
            "before": before,
            "after": after,
            "compression_cost": round(compression_cost, 8),
            "monthly_savings": monthly_savings,
            "yearly_savings": yearly_savings,
            "savings_percentage": savings_pct,
            "break_even_uses": break_even,
        }
