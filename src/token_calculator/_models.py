"""Pydantic request/response models for the Prompt Optimization Workstation API."""
from __future__ import annotations

from pydantic import BaseModel
from typing import Optional
from enum import Enum


class TokenizeMode(str, Enum):
    input = "input"
    output = "output"
    cache = "cache"


class TokenizeRequest(BaseModel):
    text: str
    group_ids: list[str]
    mode: TokenizeMode = TokenizeMode.input


class TokenizeResult(BaseModel):
    group_id: str
    model_name: str
    tokens: int
    char_count: int = 0
    cost_usd: float
    available: bool = True


class TokenizeResponse(BaseModel):
    char_count: int
    results: list[TokenizeResult]


class CompressionStrategy(str, Enum):
    rule = "rule"
    llm = "llm"


class CompressionLevel(str, Enum):
    light = "light"
    medium = "medium"
    aggressive = "aggressive"


class LLMConfig(BaseModel):
    provider: str = "openai"
    api_key: Optional[str] = None
    model: str = "gpt-4o-mini"
    api_base: Optional[str] = None


class CompressRequest(BaseModel):
    text: str
    strategy: CompressionStrategy = CompressionStrategy.rule
    level: CompressionLevel = CompressionLevel.medium
    target_ratio: float = 0.4
    llm_config: Optional[LLMConfig] = None


class CompressionChange(BaseModel):
    type: str
    rule: str
    original: str
    replaced: str


class CompressionResult(BaseModel):
    strategy: str
    original_text: str
    compressed_text: str
    original_tokens: dict[str, int] = {}
    compressed_tokens: dict[str, int] = {}
    savings: dict = {}
    changes: list[CompressionChange] = []


class CostSimulateRequest(BaseModel):
    monthly_calls: int = 10000
    avg_input_tokens: int = 520
    avg_output_tokens: int = 200
    cache_hit_rate: float = 0.30
    compression_ratio: float = 0.65
    model_ids: list[str] = []


class ModelCostComparison(BaseModel):
    model_id: str
    before: dict
    after: dict
    monthly_savings: float
    yearly_savings: float
    savings_percentage: float


class CostSimulateResponse(BaseModel):
    monthly_calls: int
    comparisons: list[ModelCostComparison]
    best_value_model: str


class ExportRequest(BaseModel):
    text: str
    format: str = "plain"


class ExportResponse(BaseModel):
    text: str
    format: str
