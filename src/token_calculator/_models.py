"""Validated API contracts for the prompt economics workbench."""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, HttpUrl


class TokenizeMode(str, Enum):
    input = "input"
    output = "output"
    cache = "cache"


class TokenizeRequest(BaseModel):
    text: str = Field(max_length=200_000)
    group_ids: list[str] = Field(min_length=1, max_length=8)
    mode: TokenizeMode = TokenizeMode.input


class TokenizeResult(BaseModel):
    group_id: str
    model_name: str
    tokens: int = Field(ge=0)
    char_count: int = Field(ge=0)
    cost_usd: float = Field(ge=0)
    available: bool
    method: str
    warning: Optional[str] = None


class TokenizeResponse(BaseModel):
    char_count: int = Field(ge=0)
    results: list[TokenizeResult]


class TokenizerPrepareRequest(BaseModel):
    group_ids: list[str] = Field(default_factory=list, max_length=8)


class CompressionStrategy(str, Enum):
    rule = "rule"
    llm = "llm"


class CompressionLevel(str, Enum):
    light = "light"
    medium = "medium"
    aggressive = "aggressive"


class LLMConfig(BaseModel):
    provider: str = Field(default="openai", pattern=r"^[a-zA-Z0-9_-]{1,32}$")
    api_key: Optional[str] = Field(default=None, max_length=512)
    model: str = Field(default="gpt-4o-mini", min_length=1, max_length=128)
    api_base: Optional[HttpUrl] = None
    input_price: Optional[float] = Field(default=None, ge=0, le=10_000)
    output_price: Optional[float] = Field(default=None, ge=0, le=10_000)


class EconomicsInput(BaseModel):
    reuse_count: int = Field(default=1, ge=1, le=100_000_000)
    expected_output_tokens: int = Field(default=0, ge=0, le=10_000_000)
    cache_hit_rate: float = Field(default=0, ge=0, le=1)
    target_input_price: Optional[float] = Field(default=None, ge=0, le=10_000)


class CompressRequest(BaseModel):
    text: str = Field(min_length=1, max_length=200_000)
    strategy: CompressionStrategy = CompressionStrategy.rule
    level: CompressionLevel = CompressionLevel.medium
    target_ratio: float = Field(default=0.4, ge=0.05, le=0.95)
    group_id: str = Field(default="o200k_base", min_length=1, max_length=64)
    model_id: Optional[str] = Field(default=None, max_length=128)
    llm_config: Optional[LLMConfig] = None
    economics: EconomicsInput = Field(default_factory=EconomicsInput)


class CompressionChange(BaseModel):
    type: str
    rule: str
    original: str
    replaced: str


class CompressionResult(BaseModel):
    strategy: str
    status: str
    original_text: str
    compressed_text: str
    original_tokens: dict[str, int] = Field(default_factory=dict)
    compressed_tokens: dict[str, int] = Field(default_factory=dict)
    token_count_method: str
    savings: dict[str, Any] = Field(default_factory=dict)
    economics: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    quality: dict[str, Any] = Field(default_factory=dict)
    changes: list[CompressionChange] = Field(default_factory=list)


class CostSimulateRequest(BaseModel):
    monthly_calls: int = Field(default=10_000, ge=1, le=100_000_000)
    avg_input_tokens: int = Field(default=520, ge=0, le=10_000_000)
    compressed_input_tokens: Optional[int] = Field(default=None, ge=0, le=10_000_000)
    avg_output_tokens: int = Field(default=200, ge=0, le=10_000_000)
    cache_hit_rate: float = Field(default=0.30, ge=0, le=1)
    compression_ratio: float = Field(default=0.65, ge=0, le=1)
    compression_cost_usd: float = Field(default=0, ge=0, le=1_000_000)
    model_ids: list[str] = Field(default_factory=list, max_length=32)


class ModelCostComparison(BaseModel):
    model_id: str
    before: dict[str, float]
    after: dict[str, float]
    compression_cost: float
    monthly_savings: float
    yearly_savings: float
    savings_percentage: float
    break_even_uses: Optional[int] = None


class CostSimulateResponse(BaseModel):
    monthly_calls: int
    comparisons: list[ModelCostComparison]
    best_value_model: str


class ExportRequest(BaseModel):
    text: str = Field(max_length=200_000)
    format: str = Field(default="plain", pattern=r"^(plain|json|markdown)$")


class ExportResponse(BaseModel):
    text: str
    format: str
